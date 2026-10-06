"""GET /api/payment-health: completed-attempt success per channel against a baseline, with failure signals and recovery.

Everything is computed per request from payment_attempt, payment and payment_summary rows (app/db/queries/payment_health.py)
through the rule in app/core/health.py. Nothing is stored. The period and channel parameters are exactly those of
/api/attempts, so every figure drills down to the Attempts and Payments lists with the same query string.
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
    BaselineInfo,
    ChannelHealth,
    FailureSignal,
    FailureSignals,
    OutcomeCounts,
    PaymentHealthResponse,
    Recovery,
    RuleInfo,
    Trend,
    TrendPoint,
    UnresolvedPayment,
    UnresolvedPayments,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS, HEALTH_STATUS_LABELS
from app.core.tz import chicago_day, chicago_range
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

UNRESOLVED_LIMIT = 5

RULE = RuleInfo(
    baseline_days=health.BASELINE_DAYS,
    min_period_completed=health.MIN_PERIOD_COMPLETED,
    min_baseline_completed=health.MIN_BASELINE_COMPLETED,
    degraded_drop_bp=health.DEGRADED_DROP_BP,
    low_volume_day_completed=health.LOW_VOLUME_DAY_COMPLETED,
    recovery_window_minutes=int(health.RECOVERY_WINDOW.total_seconds()) // 60,
)


def outcome_counts(o: health.Outcomes) -> OutcomeCounts:
    return OutcomeCounts(
        succeeded=o.succeeded, failed=o.failed, pending=o.pending, completed=o.completed, success_rate_bp=o.success_rate_bp, failed_share_bp=o.failed_share_bp
    )


def trend_point(d: health.DayOutcomes) -> TrendPoint:
    return TrendPoint(day=d.day.isoformat(), succeeded=d.succeeded, failed=d.failed, completed=d.completed, success_rate_bp=d.success_rate_bp, low_volume=d.low_volume)


def _outcomes(counter: Counter[str]) -> health.Outcomes:
    return health.Outcomes(succeeded=counter["succeeded"], failed=counter["failed"], pending=counter["pending"])


class Buckets:
    """Attempt outcomes per channel (None = all channels) for the baseline window and for every day of the period."""

    def __init__(self, rows: list[sqlite3.Row], period: periods.Period, baseline_to: date) -> None:
        self.days = periods.day_buckets(period)
        scopes: list[str | None] = [None, *health.CHANNELS]
        self._baseline: dict[str | None, Counter[str]] = {s: Counter() for s in scopes}
        self._daily: dict[str | None, dict[date, Counter[str]]] = {s: {d: Counter() for d in self.days} for s in scopes}
        for row in rows:
            day = chicago_day(row["created_at"])
            for scope in (None, row["channel"]):
                if day <= baseline_to:
                    self._baseline[scope][row["outcome"]] += 1
                elif day in self._daily[scope]:
                    self._daily[scope][day][row["outcome"]] += 1

    def baseline(self, scope: str | None) -> health.Outcomes:
        return _outcomes(self._baseline[scope])

    def daily(self, scope: str | None) -> list[health.DayOutcomes]:
        return [health.DayOutcomes(day=d, **_outcomes(c).__dict__) for d, c in self._daily[scope].items()]

    def period(self, scope: str | None) -> health.Outcomes:
        total: Counter[str] = Counter()
        for c in self._daily[scope].values():
            total.update(c)
        return _outcomes(total)


def channel_health(scope: str | None, label: str, status: health.ChannelStatus, period: health.Outcomes, baseline: health.Outcomes, worst: health.DayOutcomes | None) -> ChannelHealth:
    return ChannelHealth(
        channel=scope,
        channel_label=label,
        status=status,
        status_label=HEALTH_STATUS_LABELS[status],
        period=outcome_counts(period),
        baseline=outcome_counts(baseline),
        drop_bp=health.drop_bp(period, baseline),
        worst_day=trend_point(worst) if worst is not None else None,
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
    baseline_from, baseline_to = health.baseline_window(resolved.from_day)
    baseline_start, _ = chicago_range(baseline_from, baseline_to)

    first_attempt = health_q.history_starts(merchant_id, conn)
    history_starts = chicago_day(first_attempt) if first_attempt else None
    buckets = Buckets(health_q.attempt_outcomes(merchant_id, conn, baseline_start, resolved.end), resolved, baseline_to)

    # Every channel on its own: the rule never runs over pooled counts.
    verdicts: list[health.ChannelVerdict] = []
    channels: list[ChannelHealth] = []
    for name in health.CHANNELS:
        period_out, baseline_out = buckets.period(name), buckets.baseline(name)
        status = health.evaluate(period_out, baseline_out, baseline_from=baseline_from, history_starts=history_starts)
        worst = health.worst_day(buckets.daily(name))
        verdicts.append(health.ChannelVerdict(channel=name, label=CHANNEL_LABELS[name], status=status, period=period_out, baseline=baseline_out, worst_day=worst))
        channels.append(channel_health(name, CHANNEL_LABELS[name], status, period_out, baseline_out, worst))

    if channel is not None:
        evaluated = [v for v in verdicts if v.channel == channel]
        scope = next(c for c in channels if c.channel == channel)
        scope_period, scope_baseline = evaluated[0].period, evaluated[0].baseline
    else:
        evaluated = verdicts
        scope_period, scope_baseline = buckets.period(None), buckets.baseline(None)
        scope = channel_health(None, health.ALL_CHANNELS_LABEL, health.aggregate_status([v.status for v in verdicts]), scope_period, scope_baseline, health.worst_day(buckets.daily(None)))

    headline, detail = health.attention_text(scope.status, evaluated, baseline_from=baseline_from, baseline_to=baseline_to, history_starts=history_starts)
    attention = Attention(status=scope.status, headline=headline, detail=detail, degraded_channels=[v.channel for v in evaluated if v.status == "degraded"])

    trend = Trend(
        points=[trend_point(d) for d in buckets.daily(channel)],
        baseline_rate_bp=scope_baseline.success_rate_bp if scope.status in ("degraded", "normal") else None,
    )

    signal_rows = health_q.failure_signals(merchant_id, conn, resolved.start, resolved.end, channel)
    total_failed = sum(int(r["count"]) for r in signal_rows)
    signals = [
        FailureSignal(failure_code=r["failure_code"], label=FAILURE_CODE_LABELS[r["failure_code"]], count=r["count"], share_bp=health.rate_bp(r["count"], total_failed) or 0)
        for r in signal_rows
    ]
    failure_signals = FailureSignals(total_failed=total_failed, items=signals, primary=signals[0] if signals else None)

    counts: Counter[str] = Counter()
    cents: Counter[str] = Counter()
    for row in health_q.recovery_cohort(merchant_id, conn, resolved.start, resolved.end, channel):
        state = health.recovery_state(succeeded_at=row["succeeded_at"], latest_outcome=row["latest_outcome"], first_attempt_at=row["first_attempt_at"])
        counts[state] += 1
        cents[state] += int(row["amount_cents"])
    affected = sum(counts.values())
    recovery = Recovery(
        affected=affected,
        recovered=counts["recovered_within_window"] + counts["recovered_later"],
        recovered_within_window=counts["recovered_within_window"],
        recovered_later=counts["recovered_later"],
        attempt_pending=counts["attempt_pending"],
        unresolved=counts["unresolved"],
        recovered_within_window_share_bp=health.rate_bp(counts["recovered_within_window"], affected),
        affected_cents=sum(cents.values()),
        recovered_cents=cents["recovered_within_window"] + cents["recovered_later"],
        unresolved_cents=cents["unresolved"],
        attempt_pending_cents=cents["attempt_pending"],
        currency="USD",
    )

    unresolved = UnresolvedPayments(
        total=health_q.count_unresolved(merchant_id, conn, resolved.start, resolved.end, channel),
        items=[
            UnresolvedPayment(
                id=r["id"],
                order_reference=r["order_reference"],
                customer=customer_ref(r),
                amount_cents=r["amount_cents"],
                currency=r["currency"],
                last_attempt_at=r["latest_attempt_at"],
                last_failure_code=r["last_failure_code"],
                last_failure_label=FAILURE_CODE_LABELS[r["last_failure_code"]] if r["last_failure_code"] else None,
                attempt_count=r["attempt_count"],
            )
            for r in health_q.list_unresolved(merchant_id, conn, resolved.start, resolved.end, channel, UNRESOLVED_LIMIT)
        ],
    )

    return PaymentHealthResponse(
        period=period_info(resolved),
        channel=channel,
        channel_label=scope.channel_label,
        as_of=now_iso(conn),
        rule=RULE,
        baseline=BaselineInfo(
            from_date=baseline_from.isoformat(),
            to_date=baseline_to.isoformat(),
            range_label=health.date_range_label(baseline_from, baseline_to),
            history_starts=history_starts.isoformat() if history_starts else None,
            partial=history_starts is None or history_starts > baseline_from,
        ),
        attention=attention,
        scope=scope,
        channels=channels,
        trend=trend,
        failure_signals=failure_signals,
        recovery=recovery,
        unresolved_payments=unresolved,
    )
