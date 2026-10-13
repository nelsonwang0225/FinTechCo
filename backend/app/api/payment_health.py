"""GET /api/payment-health: completed-attempt performance against a per-channel baseline, recorded failure signals and
per-payment recovery for a period, computed on each request from attempt and payment rows.

Attempt figures (rates, trend, channels, failure signals) count payment_attempt rows by their created_at, the same
anchor as the Attempts tab. Recovery counts payments by payment.created_at, the same anchor as the Payments list, so
the unresolved total equals the Payments list filtered to status=failed for the same period and channel.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import now_iso, period_info, resolve_period
from app.api.payments import list_item
from app.api.schemas.payment_health import (
    AttemptStats,
    BaselineInfo,
    ChannelHealth,
    FailureSignal,
    HealthSummary,
    PaymentHealthResponse,
    RecoverySummary,
    Thresholds,
    TrendPoint,
    UnresolvedPayments,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS
from app.core.tz import chicago_day, chicago_range
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q
from app.db.queries import payments as payments_q
from app.db.queries.common import Page

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]
UNRESOLVED_PREVIEW = 10

ASSESSMENT_LABELS: dict[str, str] = {
    "degraded": "Degraded",
    "not_degraded": "No significant degradation",
    "insufficient_data": "Not enough data",
    "no_completed_attempts": "No completed attempts",
}


def stats(counts: health.AttemptCounts) -> AttemptStats:
    return AttemptStats(
        succeeded=counts.succeeded,
        failed=counts.failed,
        pending=counts.pending,
        completed=counts.completed,
        success_rate_bps=health.rate_bps(counts.succeeded, counts.completed),
    )


def counts_by_channel(rows: list[sqlite3.Row]) -> dict[str, health.AttemptCounts]:
    tallies: dict[str, Counter[str]] = {c: Counter() for c in CHANNEL_LABELS}
    for r in rows:
        tallies[r["channel"]][r["outcome"]] += r["n"]
    return {c: health.AttemptCounts(t["succeeded"], t["failed"], t["pending"]) for c, t in tallies.items()}


def total(counts: list[health.AttemptCounts]) -> health.AttemptCounts:
    out = health.AttemptCounts()
    for c in counts:
        out = out + c
    return out


def trend(rows: list[sqlite3.Row], period: periods.Period) -> list[TrendPoint]:
    by_day: dict[date, Counter[str]] = {d: Counter() for d in periods.day_buckets(period)}
    for r in rows:
        by_day[chicago_day(r["created_at"])][r["outcome"]] += 1
    points = []
    for day, t in by_day.items():
        counts = health.AttemptCounts(t["succeeded"], t["failed"], t["pending"])
        points.append(
            TrendPoint(
                date=day.isoformat(),
                succeeded=counts.succeeded,
                failed=counts.failed,
                pending=counts.pending,
                completed=counts.completed,
                success_rate_bps=health.rate_bps(counts.succeeded, counts.completed),
                low_volume=0 < counts.completed < health.LOW_VOLUME_DAY_ATTEMPTS,
            )
        )
    return points


def recovery(rows: list[sqlite3.Row]) -> RecoverySummary:
    count: Counter[str] = Counter()
    value: Counter[str] = Counter()
    within = 0
    for r in rows:
        state = health.recovery_state(r["succeeded_attempt_id"], r["latest_outcome"])
        count[state] += 1
        value[state] += r["amount_cents"]
        if state == "recovered" and health.recovered_within_window(r["first_attempt_at"], r["succeeded_at"]):
            within += 1
    return RecoverySummary(
        affected_payments=len(rows),
        recovered_payments=count["recovered"],
        recovered_within_window_payments=within,
        unresolved_payments=count["unresolved"],
        awaiting_outcome_payments=count["awaiting_outcome"],
        affected_value_cents=sum(r["amount_cents"] for r in rows),
        recovered_value_cents=value["recovered"],
        unresolved_value_cents=value["unresolved"],
        awaiting_outcome_value_cents=value["awaiting_outcome"],
        currency="USD",
    )


@router.get("", response_model=PaymentHealthResponse)
def get_payment_health(
    principal: Principal = Depends(require("payments:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    channel: Channel | None = None,
) -> PaymentHealthResponse:
    merchant_id = principal.merchant_id
    resolved = resolve_period(conn, period, from_date, to_date)
    baseline_from = resolved.from_day - timedelta(days=health.BASELINE_DAYS)
    baseline_to = resolved.from_day - timedelta(days=1)
    baseline_start, baseline_end = chicago_range(baseline_from, baseline_to)

    period_counts = counts_by_channel(health_q.outcome_counts(merchant_id, conn, resolved.start, resolved.end))
    baseline_counts = counts_by_channel(health_q.outcome_counts(merchant_id, conn, baseline_start, baseline_end))

    channels = []
    for c, label in CHANNEL_LABELS.items():
        verdict = health.assess(period_counts[c], baseline_counts[c])
        channels.append(
            ChannelHealth(
                channel=c,
                channel_label=label,
                period=stats(period_counts[c]),
                baseline=stats(baseline_counts[c]),
                change_bps=health.change_bps(period_counts[c], baseline_counts[c]),
                assessment=verdict,
                assessment_label=ASSESSMENT_LABELS[verdict],
            )
        )

    scope = [channel] if channel else list(CHANNEL_LABELS)
    scoped_period = total([period_counts[c] for c in scope])
    scoped_baseline = total([baseline_counts[c] for c in scope])
    verdict = health.assess(scoped_period, scoped_baseline)

    signals = [
        FailureSignal(failure_code=r["failure_code"], label=FAILURE_CODE_LABELS.get(r["failure_code"], r["failure_code"]), failed_attempts=r["n"])
        for r in health_q.failure_code_counts(merchant_id, conn, resolved.start, resolved.end, channel)
    ]

    unresolved_filters = payments_q.PaymentFilters(start=resolved.start, end=resolved.end, status="failed", channel=channel, sort="created_at", direction="desc")
    unresolved_rows, unresolved_total = payments_q.list_payments(merchant_id, conn, unresolved_filters, Page(page=1, page_size=UNRESOLVED_PREVIEW))

    return PaymentHealthResponse(
        as_of=now_iso(conn),
        period=period_info(resolved),
        baseline=BaselineInfo(
            from_date=baseline_from.isoformat(),
            to_date=baseline_to.isoformat(),
            range_label=periods.Period("custom", baseline_from, baseline_to, baseline_start, baseline_end).range_label,
            days=health.BASELINE_DAYS,
        ),
        channel=channel,
        thresholds=Thresholds(
            min_completed_attempts=health.MIN_COMPLETED_ATTEMPTS,
            degradation_points=health.DEGRADATION_POINTS,
            low_volume_day_attempts=health.LOW_VOLUME_DAY_ATTEMPTS,
            baseline_days=health.BASELINE_DAYS,
            recovery_window_minutes=int(health.RECOVERY_WINDOW.total_seconds() // 60),
        ),
        summary=HealthSummary(
            period=stats(scoped_period),
            baseline=stats(scoped_baseline),
            change_bps=health.change_bps(scoped_period, scoped_baseline),
            assessment=verdict,
            assessment_label=ASSESSMENT_LABELS[verdict],
        ),
        channels=channels,
        trend=trend(health_q.attempt_outcomes(merchant_id, conn, resolved.start, resolved.end, channel), resolved),
        failure_signals=signals,
        recovery=recovery(health_q.affected_payments(merchant_id, conn, resolved.start, resolved.end, channel)),
        unresolved=UnresolvedPayments(items=[list_item(r) for r in unresolved_rows], total=unresolved_total),
    )
