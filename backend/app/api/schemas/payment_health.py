from __future__ import annotations

from typing import Literal

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import CustomerRef, PeriodInfo

Assessment = Literal["degraded", "not_degraded", "insufficient_volume"]
AttentionStatus = Literal["degraded", "no_significant_degradation", "insufficient_volume", "no_completed_attempts"]


class BaselineInfo(ApiModel):
    from_date: str
    to_date: str
    range_label: str


class HealthRules(ApiModel):
    """The thresholds the backend applied, so the page's definitions show the same numbers."""

    baseline_days: int
    degraded_drop_bp: int
    min_completed_attempts: int
    low_volume_day_attempts: int
    recovery_window_seconds: int


class AttemptSummary(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None
    baseline_succeeded: int
    baseline_failed: int
    baseline_completed: int
    baseline_success_rate_bp: int | None
    change_bp: int | None


class ChannelHealth(AttemptSummary):
    channel: str
    channel_label: str
    assessment: Assessment
    assessment_label: str


class DegradedChannel(ApiModel):
    channel: str
    channel_label: str
    success_rate_bp: int
    baseline_success_rate_bp: int
    change_bp: int
    failed_attempts: int
    unresolved_payments: int


class Attention(ApiModel):
    status: AttentionStatus
    degraded: list[DegradedChannel]
    insufficient_volume_channels: list[str]


class TrendDay(ApiModel):
    date: str
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None
    low_volume: bool
    partial: bool


class FailureSignal(ApiModel):
    failure_code: str
    label: str
    failed_attempts: int


class Recovery(ApiModel):
    affected_payments: int
    affected_cents: int
    recovered_payments: int
    recovered_cents: int
    recovered_within_window_payments: int
    recovered_within_window_cents: int
    unresolved_payments: int
    unresolved_cents: int
    retry_pending_payments: int
    retry_pending_cents: int
    currency: str


class UnresolvedPayment(ApiModel):
    id: str
    order_reference: str
    created_at: str
    amount_cents: int
    currency: str
    channel: str
    channel_label: str
    attempt_count: int
    last_failure_code: str | None
    last_failure_label: str | None
    customer: CustomerRef | None


class PaymentHealthResponse(ApiModel):
    as_of: str
    period: PeriodInfo
    baseline: BaselineInfo
    channel: str | None
    channel_label: str
    rules: HealthRules
    attention: Attention
    attempts: AttemptSummary
    trend: list[TrendDay]
    channels: list[ChannelHealth]
    failure_signals: list[FailureSignal]
    recovery: Recovery
    unresolved: list[UnresolvedPayment]
