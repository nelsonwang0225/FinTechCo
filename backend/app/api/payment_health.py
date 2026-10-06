"""GET /api/payment-health: completed-attempt performance, a daily trend, recorded failure signals and payment recovery.

Success rate is succeeded / (succeeded + failed) over attempts created in the period; pending attempts are excluded and
reported. Recovery is counted once per payment created in the period that has at least one failed attempt:
recovered (a succeeded attempt exists), attempt pending (no success, latest attempt pending) or unresolved. Every
figure is computed from base rows on each request, scoped to the session's merchant.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import now_iso, period_info, resolve_period
from app.api.schemas.payment_health import (
    AttemptPerformance,
    FailureSignal,
    FailureSignals,
    PaymentHealthResponse,
    Recovery,
    Trend,
    TrendPoint,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import periods
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS
from app.core.tz import chicago_day, parse_iso
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

LOW_VOLUME_MIN = 30  # fewer completed attempts than this: show the rate, but say it is not enough to judge
RECOVERY_WINDOW = timedelta(hours=1)
ALL_CHANNELS_LABEL = "All channels"


def rate_bp(numerator: int, denominator: int) -> int | None:
    """numerator / denominator in basis points, rounded half-up in integer arithmetic; None without a denominator."""
    if denominator <= 0:
        return None
    return (2 * 10000 * numerator + denominator) // (2 * denominator)


def attempt_performance(rows: list[sqlite3.Row], days: list[date]) -> tuple[AttemptPerformance, Trend]:
    totals: Counter[str] = Counter()
    by_day: dict[date, Counter[str]] = {d: Counter() for d in days}
    for row in rows:
        totals[row["outcome"]] += 1
        by_day[chicago_day(row["created_at"])][row["outcome"]] += 1
    completed = totals["succeeded"] + totals["failed"]
    performance = AttemptPerformance(
        succeeded=totals["succeeded"],
        failed=totals["failed"],
        completed=completed,
        pending_excluded=totals["pending"],
        success_rate_bp=rate_bp(totals["succeeded"], completed),
        low_volume=completed < LOW_VOLUME_MIN,
        low_volume_threshold=LOW_VOLUME_MIN,
    )
    points = [TrendPoint(day=d.isoformat(), succeeded=by_day[d]["succeeded"], failed=by_day[d]["failed"]) for d in days]
    return performance, Trend(granularity="day", points=points)


def recovery_summary(rows: list[sqlite3.Row]) -> Recovery:
    counts: Counter[str] = Counter()
    cents: Counter[str] = Counter()
    within_hour = 0
    for row in rows:
        if row["succeeded_attempt_id"] is not None:
            state = "recovered"
            if parse_iso(row["succeeded_at"]) - parse_iso(row["first_attempt_at"]) <= RECOVERY_WINDOW:
                within_hour += 1
        elif row["latest_outcome"] == "pending":
            state = "attempt_pending"
        else:
            state = "unresolved"
        counts[state] += 1
        cents[state] += row["amount_cents"]
    return Recovery(
        affected_payments=len(rows),
        recovered=counts["recovered"],
        recovered_within_hour=within_hour,
        unresolved=counts["unresolved"],
        attempt_pending=counts["attempt_pending"],
        affected_cents=sum(row["amount_cents"] for row in rows),
        recovered_cents=cents["recovered"],
        unresolved_cents=cents["unresolved"],
        attempt_pending_cents=cents["attempt_pending"],
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
    filters = health_q.HealthFilters(start=resolved.start, end=resolved.end, channel=channel)

    attempts, trend = attempt_performance(health_q.attempt_rows(merchant_id, conn, filters), periods.day_buckets(resolved))
    signals = [
        FailureSignal(failure_code=r["failure_code"], label=FAILURE_CODE_LABELS.get(r["failure_code"], r["failure_code"]), count=r["count"])
        for r in health_q.failure_signals(merchant_id, conn, filters)
    ]

    return PaymentHealthResponse(
        period=period_info(resolved),
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else ALL_CHANNELS_LABEL,
        as_of=now_iso(conn),
        attempts=attempts,
        trend=trend,
        failure_signals=FailureSignals(total_failed=sum(s.count for s in signals), items=signals),
        recovery=recovery_summary(health_q.recovery_cohort(merchant_id, conn, filters)),
    )
