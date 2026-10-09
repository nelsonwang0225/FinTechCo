"""GET /api/payment-health: completed-attempt success against a per-channel baseline, and recovery per payment.

Read-only. Attempt figures (rates, trend, failure signals) count attempts created in the period, the Attempts tab's
basis; recovery and the unresolved list count payments created in the period, the Payments list's basis, so every
drill-down opens a list whose total matches the figure it came from. The rules live in ``app.core.health``.
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
    BaselineCounts,
    BaselineInfo,
    ChannelHealth,
    DegradedChannel,
    FailureSignal,
    HealthRules,
    HealthSummary,
    PaymentHealthResponse,
    Recovery,
    TrendPoint,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health, periods
from app.core.health import OutcomeCounts
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS, HEALTH_ASSESSMENT_LABELS, HEALTH_STATE_LABELS
from app.core.money import CURRENCY
from app.core.tz import chicago_day, parse_iso
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q
from app.db.queries import payments as payments_q
from app.db.queries.common import Page

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

RULES = HealthRules(
    baseline_days=health.BASELINE_DAYS,
    degraded_drop_bp=health.DEGRADED_DROP_BP,
    min_period_completed=health.MIN_PERIOD_COMPLETED,
    min_baseline_completed=health.MIN_BASELINE_COMPLETED,
    low_volume_day_completed=health.LOW_VOLUME_DAY_COMPLETED,
    quick_recovery_seconds=health.QUICK_RECOVERY_SECONDS,
)


def counts_by_channel(rows: list[sqlite3.Row]) -> dict[str, OutcomeCounts]:
    out: dict[str, OutcomeCounts] = defaultdict(OutcomeCounts)
    for row in rows:
        out[row["channel"]] = out[row["channel"]] + OutcomeCounts(**{row["outcome"]: row["n"]})
    return out


def scoped(by_channel: dict[str, OutcomeCounts], channel: str | None) -> OutcomeCounts:
    if channel:
        return by_channel.get(channel, OutcomeCounts())
    return sum(by_channel.values(), OutcomeCounts())


def channel_health(channel: str, current: OutcomeCounts, baseline: OutcomeCounts) -> ChannelHealth:
    assessment = health.assess(current, baseline)
    return ChannelHealth(
        channel=channel,
        channel_label=CHANNEL_LABELS[channel],
        succeeded=current.succeeded,
        failed=current.failed,
        pending=current.pending,
        completed=current.completed,
        success_rate_bp=current.rate_bp,
        baseline_completed=baseline.completed,
        baseline_rate_bp=baseline.rate_bp,
        change_bp=health.change_bp(current, baseline),
        assessment=assessment,
        assessment_label=HEALTH_ASSESSMENT_LABELS[assessment],
    )


def trend(rows: list[sqlite3.Row], days: list[date]) -> list[TrendPoint]:
    by_day: dict[date, OutcomeCounts] = {d: OutcomeCounts() for d in days}
    for row in rows:
        day = chicago_day(row["created_at"])
        if day in by_day:
            by_day[day] = by_day[day] + OutcomeCounts(**{row["outcome"]: 1})
    return [
        TrendPoint(day=d.isoformat(), succeeded=c.succeeded, failed=c.failed, pending=c.pending, success_rate_bp=c.rate_bp, low_volume=health.low_volume_day(c))
        for d, c in by_day.items()
    ]


def recovery(rows: list[sqlite3.Row]) -> Recovery:
    """Each affected payment counted once, with its amount counted once."""
    count: dict[str, int] = defaultdict(int)
    value: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["succeeded_attempt_id"] is not None:
            buckets = ["recovered"]
            elapsed = parse_iso(row["succeeded_at"]) - parse_iso(row["first_attempt_at"])
            if elapsed.total_seconds() <= health.QUICK_RECOVERY_SECONDS:
                buckets.append("recovered_within_hour")
        elif row["status"] == "pending":
            buckets = ["in_progress"]
        else:
            assert row["status"] == "failed", row["id"]
            buckets = ["unresolved"]
        for bucket in ["affected", *buckets]:
            count[bucket] += 1
            value[bucket] += row["amount_cents"]
    return Recovery(
        affected_payments=count["affected"],
        recovered_payments=count["recovered"],
        recovered_within_hour_payments=count["recovered_within_hour"],
        in_progress_payments=count["in_progress"],
        unresolved_payments=count["unresolved"],
        affected_value_cents=value["affected"],
        recovered_value_cents=value["recovered"],
        recovered_within_hour_value_cents=value["recovered_within_hour"],
        in_progress_value_cents=value["in_progress"],
        unresolved_value_cents=value["unresolved"],
        currency=CURRENCY,
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
    base = periods.preceding(resolved, health.BASELINE_DAYS)

    current_by_channel = counts_by_channel(health_q.outcome_counts(merchant_id, conn, resolved.start, resolved.end))
    baseline_by_channel = counts_by_channel(health_q.outcome_counts(merchant_id, conn, base.start, base.end))
    channels = [
        channel_health(c, current_by_channel.get(c, OutcomeCounts()), baseline_by_channel.get(c, OutcomeCounts()))
        for c in CHANNEL_LABELS
        if c in current_by_channel or c in baseline_by_channel
    ]
    state = health.attention_state([c.assessment for c in channels], scoped(current_by_channel, None).completed)
    degraded = [
        DegradedChannel(
            channel=c.channel, channel_label=c.channel_label, success_rate_bp=c.success_rate_bp, baseline_rate_bp=c.baseline_rate_bp,
            change_bp=c.change_bp, failed=c.failed,
        )
        for c in channels
        if c.assessment == "degraded" and c.success_rate_bp is not None and c.baseline_rate_bp is not None and c.change_bp is not None
    ]

    current = scoped(current_by_channel, channel)
    baseline = scoped(baseline_by_channel, channel)
    signals = [
        FailureSignal(failure_code=r["failure_code"], label=FAILURE_CODE_LABELS.get(r["failure_code"], r["failure_code"]), failed_attempts=r["n"])
        for r in health_q.failure_code_counts(merchant_id, conn, resolved.start, resolved.end, channel)
    ]
    unresolved_rows, _ = payments_q.list_payments(
        merchant_id, conn, payments_q.PaymentFilters(start=resolved.start, end=resolved.end, status="failed", channel=channel), Page(1, health.UNRESOLVED_LIST_SIZE)
    )

    return PaymentHealthResponse(
        period=period_info(resolved),
        baseline=BaselineInfo(days=health.BASELINE_DAYS, from_date=base.from_day.isoformat(), to_date=base.to_day.isoformat(), range_label=base.range_label),
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else None,
        rules=RULES,
        attention=Attention(state=state, state_label=HEALTH_STATE_LABELS[state], degraded_channels=degraded),
        summary=HealthSummary(
            succeeded=current.succeeded,
            failed=current.failed,
            pending=current.pending,
            completed=current.completed,
            success_rate_bp=current.rate_bp,
            baseline=BaselineCounts(succeeded=baseline.succeeded, failed=baseline.failed, completed=baseline.completed, success_rate_bp=baseline.rate_bp),
            change_bp=health.change_bp(current, baseline),
        ),
        channels=channels,
        trend=trend(health_q.attempt_rows(merchant_id, conn, resolved.start, resolved.end, channel), periods.day_buckets(resolved)),
        failure_signals=signals,
        recovery=recovery(health_q.affected_payments(merchant_id, conn, resolved.start, resolved.end, channel)),
        unresolved_payments=[list_item(r) for r in unresolved_rows],
    )
