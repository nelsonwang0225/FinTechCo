from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PaymentListItem, PeriodInfo


class HealthRules(ApiModel):
    baseline_days: int
    degraded_drop_bps: int
    min_period_completed: int
    min_baseline_completed: int
    low_volume_day_completed: int
    recovery_window_seconds: int


class BaselineRange(ApiModel):
    from_date: str
    to_date: str
    range_label: str


class AttemptStats(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bps: int | None


class HealthSummary(ApiModel):
    period: AttemptStats
    baseline: AttemptStats
    delta_bps: int | None


class ChannelHealth(ApiModel):
    channel: str
    label: str
    period: AttemptStats
    baseline: AttemptStats
    delta_bps: int | None
    assessment: str
    assessment_label: str


class TrendPoint(ApiModel):
    day: str
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bps: int | None
    low_volume: bool


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


class UnresolvedPayments(ApiModel):
    items: list[PaymentListItem]
    total: int


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    baseline: BaselineRange
    channel: str | None
    channel_label: str | None
    rules: HealthRules
    summary: HealthSummary
    channels: list[ChannelHealth]
    trend: list[TrendPoint]
    failure_signals: list[FailureSignal]
    recovery: Recovery
    unresolved_payments: UnresolvedPayments
