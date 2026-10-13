"""GET /api/payment-health: completed-attempt performance, per-channel degradation and per-payment recovery for a period.

Attempt metrics count attempts created in the period (pending ones shown, excluded from rates). Each channel is compared
with the same channel over the BASELINE_DAYS Chicago days before the period, under the fixed rules in core/health.py.
Recovery counts payments created in the period that had a failed attempt, once per payment, at the payment amount.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import period_info, resolve_period
from app.api.payments import customer_ref
from app.api.schemas.payment_health import (
    Attention,
    AttemptMetrics,
    ChannelHealth,
    FailureSignal,
    FailureSignalsResponse,
    HealthRules,
    PaymentHealthResponse,
    Recovery,
    ScopeHealth,
    TrendPoint,
    UnresolvedPayment,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import clock, health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS
from app.core.tz import chicago_day, to_iso
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]
UNRESOLVED_LIMIT = 10


def metrics(counts: health.OutcomeCounts) -> AttemptMetrics:
    return AttemptMetrics(
        succeeded=counts.succeeded,
        failed=counts.failed,
        pending=counts.pending,
        completed=counts.completed,
        success_rate_bps=health.success_rate_bps(counts),
        failure_rate_bps=health.rate_bps(counts.failed, counts.completed),
    )


def change_bps(period: health.OutcomeCounts, baseline: health.OutcomeCounts) -> int | None:
    current, reference = health.success_rate_bps(period), health.success_rate_bps(baseline)
    return None if current is None or reference is None else current - reference


def counts_by_channel(rows: list[sqlite3.Row]) -> dict[str, health.OutcomeCounts]:
    tally: dict[str, Counter[str]] = {}
    for row in rows:
        tally.setdefault(row["channel"], Counter())[row["outcome"]] += row["n"]
    return {ch: health.OutcomeCounts(c["succeeded"], c["failed"], c["pending"]) for ch, c in tally.items()}


def baseline_period(conn: sqlite3.Connection, period: periods.Period) -> periods.Period:
    """The BASELINE_DAYS Chicago days immediately before the period."""
    to_day = period.from_day - timedelta(days=1)
    return periods.resolve("custom", clock.now(conn), to_day - timedelta(days=health.BASELINE_DAYS - 1), to_day)


def channel_health(channel: str, period: health.OutcomeCounts, baseline: health.OutcomeCounts) -> ChannelHealth:
    verdict = health.verdict(period, baseline)
    return ChannelHealth(
        channel=channel,
        channel_label=CHANNEL_LABELS[channel],
        period=metrics(period),
        baseline=metrics(baseline),
        change_bps=change_bps(period, baseline),
        verdict=verdict,
        verdict_label=health.VERDICT_LABELS[verdict],
    )


def attention(scope: health.OutcomeCounts, channels: list[ChannelHealth]) -> Attention:
    degraded = [c for c in channels if c.verdict == "degraded"]
    insufficient = [c.channel for c in channels if c.verdict == "insufficient_data"]
    if scope.completed == 0:
        state = "no_data"
    elif degraded:
        state = "degraded"
    elif any(c.verdict == "ok" for c in channels):
        state = "ok"
    else:
        state = "insufficient_data"
    return Attention(state=state, degraded_channels=degraded, insufficient_channels=insufficient)


def trend(rows: list[sqlite3.Row], days: list[date], today: date) -> list[TrendPoint]:
    tally: dict[date, Counter[str]] = {d: Counter() for d in days}
    for row in rows:
        tally[chicago_day(row["created_at"])][row["outcome"]] += 1
    points = []
    for d in days:
        c = health.OutcomeCounts(tally[d]["succeeded"], tally[d]["failed"], tally[d]["pending"])
        points.append(
            TrendPoint(
                day=d.isoformat(),
                succeeded=c.succeeded,
                failed=c.failed,
                pending=c.pending,
                success_rate_bps=health.success_rate_bps(c),
                low_volume=0 < c.completed < health.LOW_VOLUME_DAY_COMPLETED,
                partial=d == today,
            )
        )
    return points


def recovery(rows: list[sqlite3.Row]) -> Recovery:
    counts: Counter[str] = Counter()
    cents: Counter[str] = Counter()

    def add(group: str, amount: int) -> None:
        counts[group] += 1
        cents[group] += amount

    for row in rows:
        add("affected", row["amount_cents"])
        if row["succeeded_at"] is not None:
            add("recovered", row["amount_cents"])
            if health.recovered_quickly(row["created_at"], row["succeeded_at"]):
                add("quick", row["amount_cents"])
        elif row["status"] == "pending":
            add("in_progress", row["amount_cents"])
        else:
            add("unresolved", row["amount_cents"])
    return Recovery(
        affected_count=counts["affected"],
        affected_cents=cents["affected"],
        recovered_count=counts["recovered"],
        recovered_cents=cents["recovered"],
        recovered_within_hour_count=counts["quick"],
        recovered_within_hour_cents=cents["quick"],
        unresolved_count=counts["unresolved"],
        unresolved_cents=cents["unresolved"],
        in_progress_count=counts["in_progress"],
        in_progress_cents=cents["in_progress"],
        currency="USD",
    )


def failure_signals(merchant_id: str, conn: sqlite3.Connection, period: periods.Period, channel: str | None) -> list[FailureSignal]:
    return [
        FailureSignal(code=r["failure_code"], label=FAILURE_CODE_LABELS[r["failure_code"]], count=r["n"])
        for r in health_q.failure_signal_counts(merchant_id, conn, period.start, period.end, channel)
    ]


def unresolved_item(row: sqlite3.Row) -> UnresolvedPayment:
    return UnresolvedPayment(
        id=row["id"],
        order_reference=row["order_reference"],
        created_at=row["created_at"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        channel=row["channel"],
        channel_label=CHANNEL_LABELS[row["channel"]],
        customer=customer_ref(row),
        failed_attempts=row["failed_attempts"],
        last_failure_code=row["last_failure_code"],
        last_failure_label=FAILURE_CODE_LABELS[row["last_failure_code"]],
        last_attempt_at=row["latest_attempt_at"],
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
    now = clock.now(conn)
    resolved = resolve_period(conn, period, from_date, to_date)
    base = baseline_period(conn, resolved)

    current_by_channel = counts_by_channel(health_q.outcome_counts(merchant_id, conn, resolved.start, resolved.end))
    baseline_by_channel = counts_by_channel(health_q.outcome_counts(merchant_id, conn, base.start, base.end))
    in_scope = [ch for ch in CHANNEL_LABELS if (channel is None or ch == channel) and (ch in current_by_channel or ch in baseline_by_channel)]
    empty = health.OutcomeCounts()
    channels = [channel_health(ch, current_by_channel.get(ch, empty), baseline_by_channel.get(ch, empty)) for ch in in_scope]

    scope_current = sum((current_by_channel.get(ch, empty) for ch in in_scope), empty)
    scope_baseline = sum((baseline_by_channel.get(ch, empty) for ch in in_scope), empty)

    signals = failure_signals(merchant_id, conn, resolved, channel)

    return PaymentHealthResponse(
        period=period_info(resolved),
        baseline_period=period_info(base),
        channel=channel,
        as_of=to_iso(now),
        rules=HealthRules(
            baseline_days=health.BASELINE_DAYS,
            min_period_completed=health.MIN_PERIOD_COMPLETED,
            min_baseline_completed=health.MIN_BASELINE_COMPLETED,
            degraded_drop_bps=health.DEGRADED_DROP_BPS,
            low_volume_day_completed=health.LOW_VOLUME_DAY_COMPLETED,
            quick_recovery_minutes=int(health.QUICK_RECOVERY.total_seconds()) // 60,
        ),
        scope=ScopeHealth(period=metrics(scope_current), baseline=metrics(scope_baseline), change_bps=change_bps(scope_current, scope_baseline)),
        attention=attention(scope_current, channels),
        channels=channels,
        trend=trend(health_q.attempt_times(merchant_id, conn, resolved.start, resolved.end, channel), periods.day_buckets(resolved), chicago_day(now)),
        failure_signals=signals,
        recovery=recovery(health_q.affected_payments(merchant_id, conn, resolved.start, resolved.end, channel)),
        unresolved_payments=[unresolved_item(r) for r in health_q.unresolved_payments(merchant_id, conn, resolved.start, resolved.end, channel, UNRESOLVED_LIMIT)],
    )


@router.get("/failure-signals", response_model=FailureSignalsResponse)
def get_failure_signals(
    principal: Principal = Depends(require("payments:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    channel: Channel | None = None,
) -> FailureSignalsResponse:
    """The recorded failure signals on failed attempts in the period, for the Attempts tab's filter."""
    resolved = resolve_period(conn, period, from_date, to_date)
    return FailureSignalsResponse(period=period_info(resolved), channel=channel, signals=failure_signals(principal.merchant_id, conn, resolved, channel))
