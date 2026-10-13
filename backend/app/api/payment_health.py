"""GET /api/payment-health: completed-attempt success against a per-channel baseline, recorded failure signals and
per-payment recovery for one period and channel.

Read-only and derived on every request from payment and payment_attempt rows. Attempt figures use
payment_attempt.created_at like the Attempts tab; affected/recovered/unresolved use payment.created_at like the Payments
list, and the unresolved list is the Payments list query itself (status=failed), so each drill-down shows the same rows.
The rules live in app/core/health.py and are returned in `rules` so the page states them.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import period_info, resolve_period
from app.api.payments import list_item
from app.api.schemas.payment_health import (
    Attention,
    AttemptStats,
    ChannelHealth,
    FailureSignal,
    HealthRules,
    PaymentHealthResponse,
    Recovery,
    ScopeSummary,
    TrendPoint,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS
from app.core.tz import chicago_day, parse_iso
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q
from app.db.queries import payments as payments_q
from app.db.queries.common import Page

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

CHANNELS: tuple[str, ...] = tuple(CHANNEL_LABELS)
ALL_CHANNELS_LABEL = "All channels"
UNRESOLVED_LIST_SIZE = 10
VERDICT_LABELS: dict[str, str] = {
    "degraded": "Degraded",
    "not_degraded": "No significant degradation",
    "insufficient_data": "Not enough data",
    "no_data": "No completed attempts",
}


def _counts_by_channel(rows: list[sqlite3.Row]) -> dict[str, health.Counts]:
    raw: dict[str, dict[str, int]] = defaultdict(lambda: {"succeeded": 0, "failed": 0, "pending": 0})
    for row in rows:
        raw[row["channel"]][row["outcome"]] += int(row["attempts"])
    return {ch: health.Counts(**raw[ch]) for ch in CHANNELS}


def _stats(counts: health.Counts) -> AttemptStats:
    return AttemptStats(
        succeeded=counts.succeeded, failed=counts.failed, pending=counts.pending, completed=counts.completed, success_rate_bp=health.rate_bp(counts)
    )


def _attention(channels: list[ChannelHealth]) -> Attention:
    degraded = [c.channel for c in channels if c.verdict == "degraded"]
    if degraded:
        verdict = "degraded"
    elif any(c.verdict == "not_degraded" for c in channels):
        verdict = "no_degradation"
    elif any(c.period.completed for c in channels):
        verdict = "not_enough_data"
    else:
        verdict = "no_data"
    return Attention(verdict=verdict, degraded_channels=degraded)


def _trend(rows: list[sqlite3.Row], days: list[date]) -> list[TrendPoint]:
    raw: dict[date, dict[str, int]] = {d: {"succeeded": 0, "failed": 0, "pending": 0} for d in days}
    for row in rows:
        day = chicago_day(row["created_at"])
        if day in raw:
            raw[day][row["outcome"]] += 1
    points = []
    for d in days:
        counts = health.Counts(**raw[d])
        points.append(
            TrendPoint(
                day=d.isoformat(),
                succeeded=counts.succeeded,
                failed=counts.failed,
                pending=counts.pending,
                completed=counts.completed,
                success_rate_bp=health.rate_bp(counts),
                low_volume=0 < counts.completed < health.LOW_VOLUME_DAY_COMPLETED,
            )
        )
    return points


def _recovery(rows: list[sqlite3.Row]) -> Recovery:
    totals: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        amount = int(row["amount_cents"])
        totals["affected"] += 1
        totals["affected_cents"] += amount
        totals["failed_attempts"] += int(row["failed_attempts"])
        if row["succeeded_at"] is not None:
            totals["recovered"] += 1
            totals["recovered_cents"] += amount
            elapsed = (parse_iso(row["succeeded_at"]) - parse_iso(row["first_attempt_at"])).total_seconds()
            if elapsed <= health.RECOVERY_WINDOW_SECONDS:
                totals["within"] += 1
                totals["within_cents"] += amount
        elif row["latest_outcome"] == "pending":
            totals["retry_pending"] += 1
            totals["retry_pending_cents"] += amount
        else:
            totals["unresolved"] += 1
            totals["unresolved_cents"] += amount
    return Recovery(
        currency="USD",
        affected_payments=totals["affected"],
        affected_cents=totals["affected_cents"],
        failed_attempts=totals["failed_attempts"],
        recovered_payments=totals["recovered"],
        recovered_cents=totals["recovered_cents"],
        recovered_within_window_payments=totals["within"],
        recovered_within_window_cents=totals["within_cents"],
        unresolved_payments=totals["unresolved"],
        unresolved_cents=totals["unresolved_cents"],
        retry_pending_payments=totals["retry_pending"],
        retry_pending_cents=totals["retry_pending_cents"],
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
    baseline = health.baseline_period(resolved)

    current = _counts_by_channel(health_q.attempt_counts_by_channel(merchant_id, conn, resolved.start, resolved.end))
    prior = _counts_by_channel(health_q.attempt_counts_by_channel(merchant_id, conn, baseline.start, baseline.end))
    channels = []
    for ch in CHANNELS:
        verdict = health.evaluate(current[ch], prior[ch])
        channels.append(
            ChannelHealth(
                channel=ch,
                channel_label=CHANNEL_LABELS[ch],
                period=_stats(current[ch]),
                baseline=_stats(prior[ch]),
                change_bp=health.change_bp(current[ch], prior[ch]),
                verdict=verdict,
                verdict_label=VERDICT_LABELS[verdict],
            )
        )

    scope_current = current[channel] if channel else sum(current.values(), health.Counts())
    scope_prior = prior[channel] if channel else sum(prior.values(), health.Counts())

    unresolved_rows, unresolved_total = payments_q.list_payments(
        merchant_id,
        conn,
        payments_q.PaymentFilters(start=resolved.start, end=resolved.end, status="failed", channel=channel),
        Page(page=1, page_size=UNRESOLVED_LIST_SIZE),
    )

    return PaymentHealthResponse(
        period=period_info(resolved),
        baseline_period=period_info(baseline),
        rules=HealthRules(
            baseline_days=health.BASELINE_DAYS,
            degraded_drop_bp=health.DEGRADED_DROP_BP,
            min_period_completed=health.MIN_PERIOD_COMPLETED,
            min_baseline_completed=health.MIN_BASELINE_COMPLETED,
            low_volume_day_completed=health.LOW_VOLUME_DAY_COMPLETED,
            recovery_window_minutes=health.RECOVERY_WINDOW_SECONDS // 60,
        ),
        summary=ScopeSummary(
            channel=channel,
            channel_label=CHANNEL_LABELS[channel] if channel else ALL_CHANNELS_LABEL,
            period=_stats(scope_current),
            baseline=_stats(scope_prior),
            change_bp=health.change_bp(scope_current, scope_prior),
        ),
        attention=_attention(channels),
        channels=channels,
        trend=_trend(health_q.attempt_outcomes(merchant_id, conn, resolved.start, resolved.end, channel), periods.day_buckets(resolved)),
        failure_signals=[
            FailureSignal(code=r["failure_code"], label=FAILURE_CODE_LABELS.get(r["failure_code"], r["failure_code"]), attempts=r["attempts"], payments=r["payments"])
            for r in health_q.failure_signals(merchant_id, conn, resolved.start, resolved.end, channel)
        ],
        recovery=_recovery(health_q.affected_payments(merchant_id, conn, resolved.start, resolved.end, channel)),
        unresolved_payments=[list_item(r) for r in unresolved_rows],
        unresolved_total=unresolved_total,
    )
