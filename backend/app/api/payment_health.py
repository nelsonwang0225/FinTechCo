"""GET /api/payment-health: completed-attempt success against each channel's own baseline, recorded failure signals and
per-payment recovery for a period.

Rules, deterministic and returned with every response as ``thresholds``:
- Success rate = succeeded / (succeeded + failed) attempts, in basis points rounded half-up. Pending attempts are counted
  but never enter the denominator; with no completed attempts there is no rate.
- Baseline = the same channel over the 30 Chicago days before the period.
- A channel is evaluated only when the period has MIN_PERIOD_COMPLETED and the baseline MIN_BASELINE_COMPLETED completed
  attempts; it is degraded when its rate is DEGRADED_DROP_BPS or more below its baseline.
- Affected = a payment created in the period with at least one failed attempt; recovered = an affected payment with a
  succeeded attempt (at any time); unresolved = affected with no succeeded attempt. Value is the payment amount, once.
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
    BaselinePeriod,
    ChannelHealth,
    DailyPoint,
    Evaluation,
    FailureSignal,
    OutcomeCounts,
    PaymentHealthResponse,
    Recovery,
    ScopeSummary,
    Thresholds,
    UnresolvedPayment,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import periods
from app.core.labels import CHANNEL_LABELS, FAILURE_SIGNAL_LABELS, HEALTH_EVALUATION_LABELS, PAYMENT_STATUS_LABELS
from app.core.money import CURRENCY
from app.core.tz import chicago_day, chicago_range, parse_iso
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

BASELINE_DAYS = 30
MIN_PERIOD_COMPLETED = 50
MIN_BASELINE_COMPLETED = 100
DEGRADED_DROP_BPS = 1000
LOW_VOLUME_DAY_COMPLETED = 10
RECOVERY_WINDOW = timedelta(hours=1)
UNRESOLVED_LIMIT = 10
ALL_CHANNELS_LABEL = "All channels"


def success_rate_bps(succeeded: int, completed: int) -> int | None:
    """succeeded / completed in basis points, integer half-up; None when nothing completed."""
    if completed == 0:
        return None
    return (succeeded * 20000 + completed) // (2 * completed)


def outcome_counts(succeeded: int, failed: int, pending: int) -> OutcomeCounts:
    completed = succeeded + failed
    return OutcomeCounts(succeeded=succeeded, failed=failed, pending=pending, completed=completed, success_rate_bps=success_rate_bps(succeeded, completed))


def evaluate(period: OutcomeCounts, baseline: OutcomeCounts) -> tuple[Evaluation, int | None]:
    drop = None
    if period.success_rate_bps is not None and baseline.success_rate_bps is not None:
        drop = baseline.success_rate_bps - period.success_rate_bps
    if period.completed == 0:
        return "no_completed", drop
    if period.completed < MIN_PERIOD_COMPLETED or baseline.completed < MIN_BASELINE_COMPLETED:
        return "insufficient_volume", drop
    assert drop is not None
    return ("degraded" if drop >= DEGRADED_DROP_BPS else "not_degraded"), drop


def channel_health(channel: str, period: OutcomeCounts, baseline: OutcomeCounts) -> ChannelHealth:
    evaluation, drop = evaluate(period, baseline)
    return ChannelHealth(
        channel=channel,
        channel_label=CHANNEL_LABELS[channel],
        period=period,
        baseline=baseline,
        drop_bps=drop,
        evaluation=evaluation,
        evaluation_label=HEALTH_EVALUATION_LABELS[evaluation],
    )


def counts_by_channel(rows: list[sqlite3.Row]) -> dict[str, OutcomeCounts]:
    return {r["channel"]: outcome_counts(r["succeeded"] or 0, r["failed"] or 0, r["pending"] or 0) for r in rows}


def total(counts: list[OutcomeCounts]) -> OutcomeCounts:
    return outcome_counts(sum(c.succeeded for c in counts), sum(c.failed for c in counts), sum(c.pending for c in counts))


def attention_for(scope: list[ChannelHealth], scope_period: OutcomeCounts) -> Attention:
    degraded = [c for c in scope if c.evaluation == "degraded"]
    not_evaluated = [c for c in scope if c.evaluation in ("insufficient_volume", "no_completed") and (c.period.completed or c.period.pending)]
    status: Evaluation
    if degraded:
        status = "degraded"
    elif scope_period.completed == 0:
        status = "no_completed"
    elif any(c.evaluation == "not_degraded" for c in scope):
        status = "not_degraded"
    else:
        status = "insufficient_volume"
    return Attention(status=status, status_label=HEALTH_EVALUATION_LABELS[status], degraded=degraded, not_evaluated=not_evaluated)


def daily_points(rows: list[sqlite3.Row], days: list[date]) -> list[DailyPoint]:
    by_day: dict[date, Counter[str]] = {d: Counter() for d in days}
    for row in rows:
        by_day[chicago_day(row["created_at"])][row["outcome"]] += 1
    points = []
    for day in days:
        c = by_day[day]
        completed = c["succeeded"] + c["failed"]
        points.append(
            DailyPoint(
                day=day.isoformat(),
                succeeded=c["succeeded"],
                failed=c["failed"],
                pending=c["pending"],
                success_rate_bps=success_rate_bps(c["succeeded"], completed),
                low_volume=0 < completed < LOW_VOLUME_DAY_COMPLETED,
            )
        )
    return points


def recovery_for(rows: list[sqlite3.Row]) -> Recovery:
    recovered = [r for r in rows if r["succeeded_attempt_id"] is not None]
    unresolved = [r for r in rows if r["succeeded_attempt_id"] is None]
    within = [r for r in recovered if parse_iso(r["succeeded_at"]) - parse_iso(r["first_attempt_at"]) <= RECOVERY_WINDOW]
    return Recovery(
        affected_payments=len(rows),
        recovered_payments=len(recovered),
        recovered_within_window=len(within),
        unresolved_payments=len(unresolved),
        unresolved_retry_pending=sum(1 for r in unresolved if r["latest_outcome"] == "pending"),
        affected_cents=sum(r["amount_cents"] for r in rows),
        recovered_cents=sum(r["amount_cents"] for r in recovered),
        unresolved_cents=sum(r["amount_cents"] for r in unresolved),
        currency=CURRENCY,
    )


def unresolved_item(row: sqlite3.Row) -> UnresolvedPayment:
    return UnresolvedPayment(
        id=row["id"],
        order_reference=row["order_reference"],
        created_at=row["created_at"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        channel=row["channel"],
        channel_label=CHANNEL_LABELS[row["channel"]],
        status=row["status"],
        status_label=PAYMENT_STATUS_LABELS[row["status"]],
        failed_attempts=row["failed_attempts"],
        last_failure_code=row["last_failure_code"],
        last_failure_label=FAILURE_SIGNAL_LABELS.get(row["last_failure_code"], row["last_failure_code"]),
        customer=customer_ref(row),
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
    baseline_from = resolved.from_day - timedelta(days=BASELINE_DAYS)
    baseline_to = resolved.from_day - timedelta(days=1)
    baseline_start, baseline_end = chicago_range(baseline_from, baseline_to)
    baseline = periods.Period(preset="custom", from_day=baseline_from, to_day=baseline_to, start=baseline_start, end=baseline_end)

    period_counts = counts_by_channel(health_q.outcome_counts_by_channel(merchant_id, conn, resolved.start, resolved.end))
    baseline_counts = counts_by_channel(health_q.outcome_counts_by_channel(merchant_id, conn, baseline_start, baseline_end))
    empty = outcome_counts(0, 0, 0)
    channels = [
        channel_health(ch, period_counts.get(ch, empty), baseline_counts.get(ch, empty))
        for ch in CHANNEL_LABELS
        if ch in period_counts or ch in baseline_counts or ch == channel
    ]
    scope = [c for c in channels if channel is None or c.channel == channel]
    summary = ScopeSummary(period=total([c.period for c in scope]), baseline=total([c.baseline for c in scope]))

    affected = health_q.affected_payments(merchant_id, conn, resolved.start, resolved.end, channel)
    signals = health_q.failure_signal_counts(merchant_id, conn, resolved.start, resolved.end, channel)
    return PaymentHealthResponse(
        period=period_info(resolved),
        baseline_period=BaselinePeriod(from_date=baseline_from.isoformat(), to_date=baseline_to.isoformat(), range_label=baseline.range_label),
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else ALL_CHANNELS_LABEL,
        thresholds=Thresholds(
            baseline_days=BASELINE_DAYS,
            min_period_completed=MIN_PERIOD_COMPLETED,
            min_baseline_completed=MIN_BASELINE_COMPLETED,
            degraded_drop_bps=DEGRADED_DROP_BPS,
            low_volume_day_completed=LOW_VOLUME_DAY_COMPLETED,
            recovery_window_minutes=int(RECOVERY_WINDOW.total_seconds()) // 60,
        ),
        summary=summary,
        attention=attention_for(scope, summary.period),
        channels=channels,
        daily=daily_points(health_q.attempt_outcomes(merchant_id, conn, resolved.start, resolved.end, channel), periods.day_buckets(resolved)),
        failure_signals=[
            FailureSignal(code=r["failure_code"], label=FAILURE_SIGNAL_LABELS.get(r["failure_code"], r["failure_code"]), failed_attempts=r["failed_attempts"])
            for r in signals
        ],
        recovery=recovery_for(affected),
        unresolved=[unresolved_item(r) for r in affected if r["succeeded_attempt_id"] is None][:UNRESOLVED_LIMIT],
    )
