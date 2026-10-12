"""GET /api/payment-health: completed-attempt success against a per-channel baseline, recorded failure signals and
recovery by payment, for one period and optionally one channel.

Attempt figures use payment_attempt.created_at (the Attempts tab's timestamp); the recovery cohort uses
payment.created_at (the Payments list's timestamp), so every drill-down opens a list whose total matches the figure.
Nothing is stored: every number is recomputed from attempts and payments on each request.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import now_iso, period_info, resolve_period
from app.api.schemas.payment_health import (
    BaselineInfo,
    ChannelHealth,
    FailureSignal,
    HealthThresholds,
    PaymentHealthResponse,
    Recovery,
    RecoveryBucket,
    ScopeHealth,
    TrendPoint,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health, periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS, HEALTH_ASSESSMENT_LABELS
from app.core.tz import chicago_day, chicago_range
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

Tally = Counter[str]  # outcome -> attempts


def _scope(period: Tally, baseline: Tally) -> dict[str, int | None]:
    s, f = period["succeeded"], period["failed"]
    bs, bf = baseline["succeeded"], baseline["failed"]
    return {
        "succeeded": s,
        "failed": f,
        "pending": period["pending"],
        "completed": s + f,
        "success_rate_bp": health.rate_bp(s, s + f),
        "baseline_succeeded": bs,
        "baseline_failed": bf,
        "baseline_completed": bs + bf,
        "baseline_rate_bp": health.rate_bp(bs, bs + bf),
        "change_bp": health.change_bp(s, s + f, bs, bs + bf),
    }


def _bucket(rows: list[sqlite3.Row]) -> RecoveryBucket:
    return RecoveryBucket(payments=len(rows), amount_cents=sum(r["amount_cents"] for r in rows))


def recovery_of(rows: list[sqlite3.Row]) -> Recovery:
    """Split the affected cohort, one row per payment: recovered, unresolved (status failed) or awaiting a pending retry."""
    recovered = [r for r in rows if r["succeeded_attempt_id"] is not None]
    unresolved = [r for r in rows if r["succeeded_attempt_id"] is None and r["status"] == "failed"]
    awaiting = [r for r in rows if r["succeeded_attempt_id"] is None and r["status"] == "pending"]
    if len(recovered) + len(unresolved) + len(awaiting) != len(rows):
        raise RuntimeError("affected payment with an unexpected status")
    quick = [r for r in recovered if health.recovered_within(r["first_attempt_at"], r["succeeded_at"])]
    return Recovery(
        affected=_bucket(rows),
        recovered=_bucket(recovered),
        recovered_within_hour=_bucket(quick),
        unresolved=_bucket(unresolved),
        awaiting_retry=_bucket(awaiting),
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
    baseline_from, baseline_to = health.baseline_days(resolved.from_day)
    baseline_start, baseline_end = chicago_range(baseline_from, baseline_to)

    attempts = health_q.period_attempts(merchant_id, conn, resolved.start, resolved.end)
    by_channel: dict[str, Tally] = {c: Counter() for c in CHANNEL_LABELS}
    for row in attempts:
        by_channel[row["channel"]][row["outcome"]] += 1
    baseline_by_channel: dict[str, Tally] = {c: Counter() for c in CHANNEL_LABELS}
    for row in health_q.outcome_counts_by_channel(merchant_id, conn, baseline_start, baseline_end):
        baseline_by_channel[row["channel"]][row["outcome"]] += row["n"]

    channels = []
    for code, label in CHANNEL_LABELS.items():
        p, b = by_channel[code], baseline_by_channel[code]
        assessment = health.assess(p["succeeded"], p["succeeded"] + p["failed"], b["succeeded"], b["succeeded"] + b["failed"])
        channels.append(
            ChannelHealth(**_scope(p, b), channel=code, channel_label=label, assessment=assessment, assessment_label=HEALTH_ASSESSMENT_LABELS[assessment])
        )

    in_scope = [r for r in attempts if channel is None or r["channel"] == channel]
    scope_period: Tally = sum((by_channel[c] for c in CHANNEL_LABELS if channel in (None, c)), Counter())
    scope_baseline: Tally = sum((baseline_by_channel[c] for c in CHANNEL_LABELS if channel in (None, c)), Counter())

    days: dict[date, Tally] = {d: Counter() for d in periods.day_buckets(resolved)}
    for row in in_scope:
        days[chicago_day(row["created_at"])][row["outcome"]] += 1
    trend = []
    for day, tally in days.items():
        completed = tally["succeeded"] + tally["failed"]
        trend.append(TrendPoint(day=day.isoformat(), succeeded=tally["succeeded"], failed=tally["failed"], pending=tally["pending"], completed=completed,
                                success_rate_bp=health.rate_bp(tally["succeeded"], completed), low_volume=health.is_low_volume_day(completed)))

    signals = Counter(r["failure_code"] for r in in_scope if r["outcome"] == "failed")
    failed_total = sum(signals.values())
    failure_signals = [
        FailureSignal(code=code, label=FAILURE_CODE_LABELS.get(code, code), failed_attempts=n, share_bp=health.rate_bp(n, failed_total) or 0)
        for code, n in sorted(signals.items(), key=lambda item: (-item[1], item[0]))
    ]

    baseline_period = periods.Period(preset="custom", from_day=baseline_from, to_day=baseline_to, start=baseline_start, end=baseline_end)
    return PaymentHealthResponse(
        as_of=now_iso(conn),
        period=period_info(resolved),
        baseline=BaselineInfo(from_date=baseline_from.isoformat(), to_date=baseline_to.isoformat(), range_label=baseline_period.range_label),
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else None,
        thresholds=HealthThresholds(**asdict(health.THRESHOLDS)),
        summary=ScopeHealth(**_scope(scope_period, scope_baseline)),
        channels=channels,
        trend=trend,
        failure_signals=failure_signals,
        recovery=recovery_of(health_q.affected_payments(merchant_id, conn, resolved.start, resolved.end, channel)),
    )
