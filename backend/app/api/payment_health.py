"""GET /api/payment-health: completed-attempt performance against each channel's own baseline, recorded failure
signals and per-payment recovery for a period.

Attempt figures count attempts created in the period (as the Attempts tab does); recovery counts payments created in
the period that had a failed attempt (as the Payments list does). Every figure is derived from base records on each
request; the rules and thresholds live in app.core.health.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import now_iso, period_info, resolve_period
from app.api.payments import customer_ref
from app.api.schemas.payment_health import (
    Attention,
    AttemptSummary,
    BaselineInfo,
    ChannelHealth,
    DegradedChannel,
    FailureSignal,
    HealthRules,
    PaymentHealthResponse,
    Recovery,
    TrendDay,
    UnresolvedPayment,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import clock, health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS
from app.core.money import CURRENCY
from app.core.tz import chicago_day, chicago_range, parse_iso
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

ALL_CHANNELS_LABEL = "All channels"
ASSESSMENT_LABELS: dict[str, str] = {
    "degraded": "Degraded",
    "not_degraded": "No significant change",
    "insufficient_volume": "Not enough attempts",
}


def _outcome_counts(rows: list[sqlite3.Row]) -> dict[str, Counter[str]]:
    by_channel: dict[str, Counter[str]] = {}
    for r in rows:
        by_channel.setdefault(r["channel"], Counter())[r["outcome"]] += r["attempts"]
    return by_channel


def _summary(current: Counter[str], baseline: Counter[str]) -> AttemptSummary:
    completed = current["succeeded"] + current["failed"]
    baseline_completed = baseline["succeeded"] + baseline["failed"]
    rate = health.rate_bp(current["succeeded"], completed)
    baseline_rate = health.rate_bp(baseline["succeeded"], baseline_completed)
    return AttemptSummary(
        succeeded=current["succeeded"],
        failed=current["failed"],
        pending=current["pending"],
        completed=completed,
        success_rate_bp=rate,
        baseline_succeeded=baseline["succeeded"],
        baseline_failed=baseline["failed"],
        baseline_completed=baseline_completed,
        baseline_success_rate_bp=baseline_rate,
        change_bp=None if rate is None or baseline_rate is None else rate - baseline_rate,
    )


def _trend(rows: list[sqlite3.Row], period: periods.Period, today: date) -> list[TrendDay]:
    per_day: dict[date, Counter[str]] = {}
    for r in rows:
        per_day.setdefault(chicago_day(r["created_at"]), Counter())[r["outcome"]] += 1
    days = []
    for day in periods.day_buckets(period):
        c = per_day.get(day, Counter())
        completed = c["succeeded"] + c["failed"]
        days.append(
            TrendDay(
                date=day.isoformat(),
                succeeded=c["succeeded"],
                failed=c["failed"],
                pending=c["pending"],
                completed=completed,
                success_rate_bp=health.rate_bp(c["succeeded"], completed),
                low_volume=completed < health.LOW_VOLUME_DAY_ATTEMPTS,
                partial=day == today,
            )
        )
    return days


def _recovered_within_window(row: sqlite3.Row) -> bool:
    if row["succeeded_at"] is None or row["first_attempt_at"] is None:
        return False
    elapsed = parse_iso(row["succeeded_at"]) - parse_iso(row["first_attempt_at"])
    return elapsed.total_seconds() <= health.RECOVERY_WINDOW_SECONDS


def _recovery(rows: list[sqlite3.Row]) -> Recovery:
    recovered = [r for r in rows if r["succeeded_attempt_id"] is not None]
    within = [r for r in recovered if _recovered_within_window(r)]
    unresolved = [r for r in rows if r["status"] == "failed"]
    retry_pending = [r for r in rows if r["succeeded_attempt_id"] is None and r["status"] == "pending"]
    return Recovery(
        affected_payments=len(rows),
        affected_cents=sum(r["amount_cents"] for r in rows),
        recovered_payments=len(recovered),
        recovered_cents=sum(r["amount_cents"] for r in recovered),
        recovered_within_window_payments=len(within),
        recovered_within_window_cents=sum(r["amount_cents"] for r in within),
        unresolved_payments=len(unresolved),
        unresolved_cents=sum(r["amount_cents"] for r in unresolved),
        retry_pending_payments=len(retry_pending),
        retry_pending_cents=sum(r["amount_cents"] for r in retry_pending),
        currency=CURRENCY,
    )


def _unresolved_item(row: sqlite3.Row) -> UnresolvedPayment:
    code = row["last_failure_code"]
    return UnresolvedPayment(
        id=row["id"],
        order_reference=row["order_reference"],
        created_at=row["created_at"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        channel=row["channel"],
        channel_label=CHANNEL_LABELS[row["channel"]],
        attempt_count=row["attempt_count"],
        last_failure_code=code,
        last_failure_label=FAILURE_CODE_LABELS.get(code, code) if code else None,
        customer=customer_ref(row),
    )


def _attention(channels: list[ChannelHealth], affected: list[sqlite3.Row]) -> Attention:
    unresolved_by_channel = Counter(r["channel"] for r in affected if r["status"] == "failed")
    degraded = [
        DegradedChannel(
            channel=c.channel,
            channel_label=c.channel_label,
            success_rate_bp=c.success_rate_bp or 0,
            baseline_success_rate_bp=c.baseline_success_rate_bp or 0,
            change_bp=c.change_bp or 0,
            failed_attempts=c.failed,
            unresolved_payments=unresolved_by_channel[c.channel],
        )
        for c in channels
        if c.assessment == "degraded"
    ]
    insufficient = [c.channel for c in channels if c.assessment == "insufficient_volume"]
    if sum(c.completed for c in channels) == 0:
        status = "no_completed_attempts"
    elif degraded:
        status = "degraded"
    elif all(c.assessment == "insufficient_volume" for c in channels):
        status = "insufficient_volume"
    else:
        status = "no_significant_degradation"
    return Attention(status=status, degraded=degraded, insufficient_volume_channels=insufficient)


@router.get("", response_model=PaymentHealthResponse)
def payment_health(
    principal: Principal = Depends(require("payments:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    channel: Channel | None = None,
) -> PaymentHealthResponse:
    mid = principal.merchant_id
    resolved = resolve_period(conn, period, from_date, to_date)
    base_from, base_to = health.baseline_days(resolved.from_day)
    base_start, base_end = chicago_range(base_from, base_to)
    baseline_period = periods.Period("custom", base_from, base_to, base_start, base_end)

    current = _outcome_counts(health_q.attempt_outcomes_by_channel(mid, conn, resolved.start, resolved.end))
    baseline = _outcome_counts(health_q.attempt_outcomes_by_channel(mid, conn, base_start, base_end))

    channels: list[ChannelHealth] = []
    for ch in CHANNEL_LABELS:
        if ch not in current and ch not in baseline:
            continue
        s = _summary(current.get(ch, Counter()), baseline.get(ch, Counter()))
        assessment = health.assess(s.succeeded, s.completed, s.baseline_succeeded, s.baseline_completed)
        channels.append(
            ChannelHealth(**s.model_dump(), channel=ch, channel_label=CHANNEL_LABELS[ch], assessment=assessment, assessment_label=ASSESSMENT_LABELS[assessment])
        )

    in_scope = [channel] if channel else list(CHANNEL_LABELS)
    scope_current: Counter[str] = sum((current.get(ch, Counter()) for ch in in_scope), Counter())
    scope_baseline: Counter[str] = sum((baseline.get(ch, Counter()) for ch in in_scope), Counter())

    affected = health_q.affected_payments(mid, conn, resolved.start, resolved.end, None)
    scope_affected = [r for r in affected if channel is None or r["channel"] == channel]

    return PaymentHealthResponse(
        as_of=now_iso(conn),
        period=period_info(resolved),
        baseline=BaselineInfo(from_date=base_from.isoformat(), to_date=base_to.isoformat(), range_label=baseline_period.range_label),
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else ALL_CHANNELS_LABEL,
        rules=HealthRules(
            baseline_days=health.BASELINE_DAYS,
            degraded_drop_bp=health.DEGRADED_DROP_BP,
            min_completed_attempts=health.MIN_COMPLETED_ATTEMPTS,
            low_volume_day_attempts=health.LOW_VOLUME_DAY_ATTEMPTS,
            recovery_window_seconds=health.RECOVERY_WINDOW_SECONDS,
        ),
        attention=_attention(channels, affected),
        attempts=_summary(scope_current, scope_baseline),
        trend=_trend(health_q.attempt_outcome_times(mid, conn, resolved.start, resolved.end, channel), resolved, chicago_day(clock.now(conn))),
        channels=channels,
        failure_signals=[
            FailureSignal(failure_code=r["failure_code"], label=FAILURE_CODE_LABELS.get(r["failure_code"], r["failure_code"]), failed_attempts=r["attempts"])
            for r in health_q.failure_signal_counts(mid, conn, resolved.start, resolved.end, channel)
        ],
        recovery=_recovery(scope_affected),
        unresolved=[_unresolved_item(r) for r in scope_affected if r["status"] == "failed"][: health.UNRESOLVED_LIST_LIMIT],
    )
