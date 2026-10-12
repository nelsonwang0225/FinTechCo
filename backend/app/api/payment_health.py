"""GET /api/payment-health: completed-attempt performance for a period and channel against each channel's baseline,
recorded failure signals, and recovery per payment.

Read-only and derived on every request. Attempt figures count attempts created in the period (the Attempts tab's anchor);
recovery counts payments created in the period (the Payments list's anchor), so every drill-down list matches its figure.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import period_info, resolve_period
from app.api.payments import list_item
from app.api.schemas.payment_health import (
    AttemptStats,
    BaselineRange,
    ChannelHealth,
    FailureSignal,
    HealthRules,
    HealthSummary,
    PaymentHealthResponse,
    Recovery,
    TrendPoint,
    UnresolvedPayments,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS, HEALTH_ASSESSMENT_LABELS
from app.core.tz import chicago_day, chicago_range
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q
from app.db.queries import payments as payments_q
from app.db.queries.common import Page

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]
UNRESOLVED_PREVIEW = 10


def stats(counts: health.Counts) -> AttemptStats:
    return AttemptStats(
        succeeded=counts.succeeded, failed=counts.failed, pending=counts.pending, completed=counts.completed, success_rate_bps=counts.rate_bps
    )


def add(counts: health.Counts, outcome: str, n: int = 1) -> health.Counts:
    return health.Counts(
        succeeded=counts.succeeded + (n if outcome == "succeeded" else 0),
        failed=counts.failed + (n if outcome == "failed" else 0),
        pending=counts.pending + (n if outcome == "pending" else 0),
    )


def total(by_channel: dict[str, health.Counts], channel: str | None) -> health.Counts:
    if channel:
        return by_channel[channel]
    return health.Counts(
        succeeded=sum(c.succeeded for c in by_channel.values()),
        failed=sum(c.failed for c in by_channel.values()),
        pending=sum(c.pending for c in by_channel.values()),
    )


def recovery(rows: list[sqlite3.Row]) -> Recovery:
    counts: Counter[str] = Counter()
    cents: Counter[str] = Counter()
    for row in rows:
        if row["succeeded_attempt_id"] is not None:
            groups = ["recovered"]
            if health.recovered_within(row["created_at"], row["succeeded_at"]):
                groups.append("within")
        elif row["status"] == "pending":
            groups = ["retry_pending"]
        else:
            groups = ["unresolved"]
        for group in ["affected", *groups]:
            counts[group] += 1
            cents[group] += row["amount_cents"]
    return Recovery(
        affected_payments=counts["affected"],
        affected_cents=cents["affected"],
        recovered_payments=counts["recovered"],
        recovered_cents=cents["recovered"],
        recovered_within_window_payments=counts["within"],
        recovered_within_window_cents=cents["within"],
        unresolved_payments=counts["unresolved"],
        unresolved_cents=cents["unresolved"],
        retry_pending_payments=counts["retry_pending"],
        retry_pending_cents=cents["retry_pending"],
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
    base_from, base_to = health.baseline_days(resolved.from_day)
    base_start, base_end = chicago_range(base_from, base_to)
    baseline_period = periods.Period(preset="custom", from_day=base_from, to_day=base_to, start=base_start, end=base_end)

    # Attempt-level figures: every channel, so the channel table and attention summary ignore the channel filter.
    period_by_channel = {c: health.Counts() for c in CHANNEL_LABELS}
    days = periods.day_buckets(resolved)
    by_day = {d: health.Counts() for d in days}
    signals: Counter[str] = Counter()
    for row in health_q.attempt_rows(merchant_id, conn, resolved.start, resolved.end):
        period_by_channel[row["channel"]] = add(period_by_channel[row["channel"]], row["outcome"])
        if channel and row["channel"] != channel:
            continue
        day = chicago_day(row["created_at"])
        by_day[day] = add(by_day[day], row["outcome"])
        if row["outcome"] == "failed":
            signals[row["failure_code"]] += 1

    baseline_by_channel = {c: health.Counts() for c in CHANNEL_LABELS}
    for row in health_q.outcome_counts(merchant_id, conn, base_start, base_end):
        baseline_by_channel[row["channel"]] = add(baseline_by_channel[row["channel"]], row["outcome"], row["n"])

    scoped_period, scoped_baseline = total(period_by_channel, channel), total(baseline_by_channel, channel)

    unresolved_rows, unresolved_total = payments_q.list_payments(
        merchant_id,
        conn,
        payments_q.PaymentFilters(start=resolved.start, end=resolved.end, status="failed", channel=channel),
        Page(page=1, page_size=UNRESOLVED_PREVIEW),
    )

    return PaymentHealthResponse(
        period=period_info(resolved),
        baseline=BaselineRange(from_date=base_from.isoformat(), to_date=base_to.isoformat(), range_label=baseline_period.range_label),
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else None,
        rules=HealthRules(
            baseline_days=health.BASELINE_DAYS,
            degraded_drop_bps=health.DEGRADED_DROP_BPS,
            min_period_completed=health.MIN_PERIOD_COMPLETED,
            min_baseline_completed=health.MIN_BASELINE_COMPLETED,
            low_volume_day_completed=health.LOW_VOLUME_DAY_COMPLETED,
            recovery_window_seconds=health.RECOVERY_WINDOW_SECONDS,
        ),
        summary=HealthSummary(
            period=stats(scoped_period), baseline=stats(scoped_baseline), delta_bps=health.delta_bps(scoped_period, scoped_baseline)
        ),
        channels=[
            ChannelHealth(
                channel=c,
                label=label,
                period=stats(period_by_channel[c]),
                baseline=stats(baseline_by_channel[c]),
                delta_bps=health.delta_bps(period_by_channel[c], baseline_by_channel[c]),
                assessment=(assessment := health.assess(period_by_channel[c], baseline_by_channel[c])),
                assessment_label=HEALTH_ASSESSMENT_LABELS[assessment],
            )
            for c, label in CHANNEL_LABELS.items()
        ],
        trend=[
            TrendPoint(
                day=d.isoformat(),
                succeeded=by_day[d].succeeded,
                failed=by_day[d].failed,
                pending=by_day[d].pending,
                completed=by_day[d].completed,
                success_rate_bps=by_day[d].rate_bps,
                low_volume=health.is_low_volume_day(by_day[d]),
            )
            for d in days
        ],
        failure_signals=[
            FailureSignal(failure_code=code, label=FAILURE_CODE_LABELS.get(code, code), failed_attempts=n)
            for code, n in sorted(signals.items(), key=lambda item: (-item[1], item[0]))
        ],
        recovery=recovery(health_q.affected_payments(merchant_id, conn, resolved.start, resolved.end, channel)),
        unresolved_payments=UnresolvedPayments(items=[list_item(r) for r in unresolved_rows], total=unresolved_total),
    )
