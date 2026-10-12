"""GET /api/payment-health: completed-attempt success against each channel's own baseline, recorded failure signals,
and recovery per payment, for one period and optionally one channel.

Every figure is derived on request from attempt and payment rows (rules in app.core.health). The attention summary
always assesses every channel, so scoping the page to one channel never hides another channel's degradation.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import period_info, resolve_period
from app.api.schemas.payment_health import (
    Attention,
    AttemptMetrics,
    BaselineInfo,
    ChannelHealth,
    FailureSignal,
    HealthRules,
    PaymentHealthResponse,
    RecoveryGroup,
    RecoverySummary,
    TrendPoint,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS, HEALTH_ASSESSMENT_LABELS, HEALTH_ATTENTION_LABELS
from app.core.tz import chicago_range
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

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


def metrics(period: health.Counts, baseline: health.Counts) -> dict[str, int | None]:
    return {
        "completed": period.completed,
        "succeeded": period.succeeded,
        "failed": period.failed,
        "pending": period.pending,
        "success_rate_bp": period.rate_bp,
        "baseline_completed": baseline.completed,
        "baseline_succeeded": baseline.succeeded,
        "baseline_rate_bp": baseline.rate_bp,
        "change_bp": health.change_bp(period, baseline),
    }


def group(g: health.Group) -> RecoveryGroup:
    return RecoveryGroup(payments=g.payments, amount_cents=g.amount_cents)


@router.get("", response_model=PaymentHealthResponse)
def get_payment_health(
    principal: Principal = Depends(require("payments:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    channel: Channel | None = None,
) -> PaymentHealthResponse:
    resolved = resolve_period(conn, period, from_date, to_date)
    base_from, base_to = health.baseline_days(resolved.from_day)
    base_start, base_end = chicago_range(base_from, base_to)
    baseline_period = periods.Period(preset="custom", from_day=base_from, to_day=base_to, start=base_start, end=base_end)

    rows = health_q.attempt_rows(principal.merchant_id, conn, resolved.start, resolved.end)
    base_rows = health_q.attempt_rows(principal.merchant_id, conn, base_start, base_end)
    affected = health_q.affected_payment_rows(principal.merchant_id, conn, resolved.start, resolved.end, channel)

    seen = {r["channel"] for r in rows} | {r["channel"] for r in base_rows} | ({channel} if channel else set())
    channels: list[ChannelHealth] = []
    for ch in (c for c in CHANNEL_LABELS if c in seen):
        p, b = health.count_attempts(rows, ch), health.count_attempts(base_rows, ch)
        assessment = health.assess(p, b)
        channels.append(
            ChannelHealth(
                channel=ch,
                channel_label=CHANNEL_LABELS[ch],
                assessment=assessment,
                assessment_label=HEALTH_ASSESSMENT_LABELS[assessment],
                **metrics(p, b),
            )
        )
    state = health.attention_state(c.assessment for c in channels)

    scope = health.count_attempts(rows, channel)
    scope_baseline = health.count_attempts(base_rows, channel)
    recovery = health.recovery(affected)
    return PaymentHealthResponse(
        period=period_info(resolved),
        baseline=BaselineInfo(
            from_date=base_from.isoformat(),
            to_date=base_to.isoformat(),
            range_label=baseline_period.range_label,
            days=health.BASELINE_DAYS,
            days_with_completed=health.days_with_completed(base_rows, channel),
        ),
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else None,
        rules=RULES,
        attempts=AttemptMetrics(**metrics(scope, scope_baseline)),
        attention=Attention(
            state=state,
            label=HEALTH_ATTENTION_LABELS[state],
            degraded_channels=[c.channel for c in channels if c.assessment == "degraded"],
            not_assessed_channels=[c.channel for c in channels if c.assessment == "insufficient_volume"],
        ),
        channels=channels,
        trend=[
            TrendPoint(
                day=p.day.isoformat(),
                completed=p.counts.completed,
                succeeded=p.counts.succeeded,
                failed=p.counts.failed,
                pending=p.counts.pending,
                success_rate_bp=p.counts.rate_bp,
                low_volume=p.low_volume,
            )
            for p in health.daily_trend(rows, periods.day_buckets(resolved), channel)
        ],
        failure_signals=[FailureSignal(code=code, label=FAILURE_CODE_LABELS[code], count=n) for code, n in health.signal_counts(rows, channel)],
        recovery=RecoverySummary(
            currency="USD",
            affected=group(recovery.affected),
            recovered=group(recovery.recovered),
            recovered_within_hour=group(recovery.recovered_within_hour),
            unresolved=group(recovery.unresolved),
            in_progress=group(recovery.in_progress),
        ),
    )
