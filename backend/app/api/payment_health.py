"""GET /api/payment-health: completed-attempt success by channel against each channel's own baseline, recorded failure
signals, and per-payment recovery, for one period and optionally one channel.

Everything is derived from attempt and payment rows on each request. The attention summary and the channel table
always cover every channel with activity; the channel parameter scopes the KPIs and the failure signals.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import period_info, resolve_period
from app.api.schemas.payment_health import (
    AttentionSummary,
    BaselineInfo,
    ChannelHealth,
    FailureSignal,
    HealthKpis,
    HealthRules,
    PaymentHealthResponse,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import health_rules as rules
from app.core.health_rules import OutcomeCounts
from app.core.labels import CHANNEL_LABELS, FAILURE_CODE_LABELS, HEALTH_EVALUATION_LABELS
from app.core.periods import Period
from app.core.tz import chicago_range
from app.db.connection import get_conn
from app.db.queries import payment_health as health_q

router = APIRouter(prefix="/api/payment-health", tags=["payment-health"])

Channel = Literal["website", "mobile_app", "in_store"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]
ALL_CHANNELS_LABEL = "All channels"


def _counts_by_channel(rows: list[sqlite3.Row]) -> dict[str, OutcomeCounts]:
    out: dict[str, OutcomeCounts] = {}
    for row in rows:
        current = out.get(row["channel"], OutcomeCounts())
        out[row["channel"]] = current + OutcomeCounts(**{row["outcome"]: int(row["n"])})
    return out


def _total(counts: dict[str, OutcomeCounts], channel: str | None) -> OutcomeCounts:
    if channel:
        return counts.get(channel, OutcomeCounts())
    total = OutcomeCounts()
    for c in counts.values():
        total = total + c
    return total


def channel_health(channel: str, period: OutcomeCounts, baseline: OutcomeCounts) -> ChannelHealth:
    evaluation = rules.evaluate(period, baseline)
    return ChannelHealth(
        channel=channel,
        channel_label=CHANNEL_LABELS[channel],
        succeeded=period.succeeded,
        failed=period.failed,
        pending=period.pending,
        completed=period.completed,
        rate_bp=rules.rate_bp(period),
        baseline_succeeded=baseline.succeeded,
        baseline_failed=baseline.failed,
        baseline_completed=baseline.completed,
        baseline_rate_bp=rules.rate_bp(baseline),
        delta_bp=rules.delta_bp(period, baseline),
        evaluation=evaluation,
        evaluation_label=HEALTH_EVALUATION_LABELS[evaluation],
    )


def _names(items: list[ChannelHealth]) -> str:
    labels = [c.channel_label for c in items]
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def attention_summary(channels: list[ChannelHealth]) -> AttentionSummary:
    degraded = [c for c in channels if c.evaluation == "degraded"]
    evaluated = [c for c in channels if c.evaluation != "insufficient_volume"]
    unevaluated = [c for c in channels if c.evaluation == "insufficient_volume"]
    tail = f" {_names(unevaluated)}: insufficient volume to evaluate." if unevaluated else ""
    if degraded:
        sentences = []
        for c in degraded:
            assert c.rate_bp is not None and c.baseline_rate_bp is not None
            sentences.append(
                f"{c.channel_label} is degraded: {rules.format_rate(c.rate_bp)} success vs {rules.format_rate(c.baseline_rate_bp)} baseline, "
                f"{c.failed} failed attempt{'' if c.failed == 1 else 's'}."
            )
        return AttentionSummary(state="degraded", message=" ".join(sentences) + tail, degraded=degraded)
    if evaluated:
        return AttentionSummary(state="no_degradation", message=f"No significant degradation detected in {_names(evaluated)}.{tail}", degraded=[])
    return AttentionSummary(
        state="insufficient_volume",
        message="Insufficient volume to draw a conclusion: no channel has enough completed attempts in this period and its baseline.",
        degraded=[],
    )


def baseline_info(period: Period) -> tuple[BaselineInfo, str, str]:
    from_day, to_day = rules.baseline_days(period.from_day)
    start, end = chicago_range(from_day, to_day)
    same_year = from_day.year == to_day.year
    left = f"{from_day.strftime('%b')} {from_day.day}" + ("" if same_year else f", {from_day.year}")
    label = f"{left} – {to_day.strftime('%b')} {to_day.day}, {to_day.year}"
    return BaselineInfo(from_date=from_day.isoformat(), to_date=to_day.isoformat(), range_label=label), start, end


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
    baseline, baseline_start, baseline_end = baseline_info(resolved)

    period_counts = _counts_by_channel(health_q.outcome_counts_by_channel(merchant_id, conn, resolved.start, resolved.end))
    baseline_counts = _counts_by_channel(health_q.outcome_counts_by_channel(merchant_id, conn, baseline_start, baseline_end))
    active = [c for c in CHANNEL_LABELS if c in period_counts or c in baseline_counts]
    channels = [channel_health(c, period_counts.get(c, OutcomeCounts()), baseline_counts.get(c, OutcomeCounts())) for c in active]

    scoped = _total(period_counts, channel)
    scoped_baseline = _total(baseline_counts, channel)
    buckets = {row["bucket"]: row for row in health_q.recovery_buckets(merchant_id, conn, resolved.start, resolved.end, channel)}

    def bucket(name: str, column: str) -> int:
        row = buckets.get(name)
        return int(row[column]) if row is not None else 0

    return PaymentHealthResponse(
        period=period_info(resolved),
        baseline=baseline,
        channel=channel,
        channel_label=CHANNEL_LABELS[channel] if channel else ALL_CHANNELS_LABEL,
        rules=HealthRules(
            baseline_days=rules.BASELINE_DAYS,
            min_period_completed=rules.MIN_PERIOD_COMPLETED,
            min_baseline_completed=rules.MIN_BASELINE_COMPLETED,
            degraded_drop_bp=rules.DEGRADED_DROP_BP,
        ),
        summary=attention_summary(channels),
        kpis=HealthKpis(
            succeeded=scoped.succeeded,
            failed=scoped.failed,
            pending=scoped.pending,
            completed=scoped.completed,
            rate_bp=rules.rate_bp(scoped),
            baseline_completed=scoped_baseline.completed,
            baseline_rate_bp=rules.rate_bp(scoped_baseline),
            delta_bp=rules.delta_bp(scoped, scoped_baseline),
            affected_payments=sum(bucket(b, "n") for b in ("recovered", "unresolved", "awaiting_retry")),
            recovered_payments=bucket("recovered", "n"),
            unresolved_payments=bucket("unresolved", "n"),
            awaiting_retry_payments=bucket("awaiting_retry", "n"),
            affected_cents=sum(bucket(b, "amount_cents") for b in ("recovered", "unresolved", "awaiting_retry")),
            currency="USD",
        ),
        channels=channels,
        failure_signals=[
            FailureSignal(code=row["failure_code"], label=FAILURE_CODE_LABELS.get(row["failure_code"], row["failure_code"]), count=int(row["n"]))
            for row in health_q.failure_signal_counts(merchant_id, conn, resolved.start, resolved.end, channel)
        ],
    )
