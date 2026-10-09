"""Payment Health response. Counts and cents are integers; rates are integer basis points, null when nothing completed."""

from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PaymentListItem, PeriodInfo


class BaselineInfo(ApiModel):
    days: int
    from_date: str
    to_date: str
    range_label: str


class HealthRules(ApiModel):
    baseline_days: int
    degraded_drop_bp: int
    min_period_completed: int
    min_baseline_completed: int
    low_volume_day_completed: int
    quick_recovery_seconds: int


class DegradedChannel(ApiModel):
    channel: str
    channel_label: str
    success_rate_bp: int
    baseline_rate_bp: int
    change_bp: int
    failed: int


class Attention(ApiModel):
    state: str
    state_label: str
    degraded_channels: list[DegradedChannel]


class BaselineCounts(ApiModel):
    succeeded: int
    failed: int
    completed: int
    success_rate_bp: int | None


class HealthSummary(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None
    baseline: BaselineCounts
    change_bp: int | None


class ChannelHealth(ApiModel):
    channel: str
    channel_label: str
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None
    baseline_completed: int
    baseline_rate_bp: int | None
    change_bp: int | None
    assessment: str
    assessment_label: str


class TrendPoint(ApiModel):
    day: str
    succeeded: int
    failed: int
    pending: int
    success_rate_bp: int | None
    low_volume: bool


class FailureSignal(ApiModel):
    failure_code: str
    label: str
    failed_attempts: int


class Recovery(ApiModel):
    affected_payments: int
    recovered_payments: int
    recovered_within_hour_payments: int
    in_progress_payments: int
    unresolved_payments: int
    affected_value_cents: int
    recovered_value_cents: int
    recovered_within_hour_value_cents: int
    in_progress_value_cents: int
    unresolved_value_cents: int
    currency: str


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    baseline: BaselineInfo
    channel: str | None
    channel_label: str | None
    rules: HealthRules
    attention: Attention
    summary: HealthSummary
    channels: list[ChannelHealth]
    trend: list[TrendPoint]
    failure_signals: list[FailureSignal]
    recovery: Recovery
    unresolved_payments: list[PaymentListItem]
