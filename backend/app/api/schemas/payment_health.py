"""GET /api/payment-health response. Rates and shares are integer basis points (half-up); money is integer cents."""

from __future__ import annotations

from typing import Literal

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import CustomerRef, PeriodInfo

ChannelStatus = Literal["degraded", "normal", "insufficient_volume", "no_baseline"]


class RuleInfo(ApiModel):
    """The constants of core/health.py, so the page can quote them instead of keeping its own copy."""

    baseline_days: int
    min_period_completed: int
    min_baseline_completed: int
    degraded_drop_bp: int
    low_volume_day_completed: int
    recovery_window_minutes: int


class BaselineInfo(ApiModel):
    from_date: str
    to_date: str
    range_label: str
    history_starts: str | None  # Chicago date of the merchant's first recorded attempt
    partial: bool  # history starts after from_date, so the baseline covers fewer days than the rule names


class OutcomeCounts(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None  # None when nothing completed
    failed_share_bp: int | None


class TrendPoint(ApiModel):
    day: str
    succeeded: int
    failed: int
    completed: int
    success_rate_bp: int | None  # None = a gap in the chart, never 0%
    low_volume: bool


class ChannelHealth(ApiModel):
    channel: str | None  # None = all channels
    channel_label: str
    status: ChannelStatus
    status_label: str
    period: OutcomeCounts
    baseline: OutcomeCounts
    drop_bp: int | None  # baseline rate minus period rate; positive means worse than baseline
    worst_day: TrendPoint | None


class Attention(ApiModel):
    status: ChannelStatus
    headline: str
    detail: str
    degraded_channels: list[str]


class Trend(ApiModel):
    points: list[TrendPoint]
    baseline_rate_bp: int | None  # the dashed reference line; None without a usable baseline


class FailureSignal(ApiModel):
    failure_code: str
    label: str
    count: int
    share_bp: int  # of failed attempts in scope


class FailureSignals(ApiModel):
    total_failed: int
    items: list[FailureSignal]
    primary: FailureSignal | None


class Recovery(ApiModel):
    affected: int
    recovered: int
    recovered_within_window: int
    recovered_later: int
    attempt_pending: int
    unresolved: int
    recovered_within_window_share_bp: int | None  # of affected payments
    affected_cents: int
    recovered_cents: int
    unresolved_cents: int
    attempt_pending_cents: int
    currency: str


class UnresolvedPayment(ApiModel):
    id: str
    order_reference: str
    customer: CustomerRef | None
    amount_cents: int
    currency: str
    last_attempt_at: str
    last_failure_code: str | None
    last_failure_label: str | None
    attempt_count: int


class UnresolvedPayments(ApiModel):
    total: int
    items: list[UnresolvedPayment]


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    channel: str | None
    channel_label: str
    as_of: str
    rule: RuleInfo
    baseline: BaselineInfo
    attention: Attention
    scope: ChannelHealth  # the selected scope: the KPI row reads from here
    channels: list[ChannelHealth]  # every channel, evaluated on its own
    trend: Trend
    failure_signals: FailureSignals
    recovery: Recovery
    unresolved_payments: UnresolvedPayments
