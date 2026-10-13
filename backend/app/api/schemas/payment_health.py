from __future__ import annotations

from app.api.schemas.common import ApiModel, Option
from app.api.schemas.payments import PaymentListItem, PeriodInfo


class HealthRules(ApiModel):
    baseline_days: int
    degraded_drop_bp: int
    min_period_completed: int
    min_baseline_completed: int
    low_volume_day_completed: int
    recovery_window_minutes: int


class AttemptStats(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None


class ScopeSummary(ApiModel):
    channel: str | None
    channel_label: str
    period: AttemptStats
    baseline: AttemptStats
    change_bp: int | None


class ChannelHealth(ApiModel):
    channel: str
    channel_label: str
    period: AttemptStats
    baseline: AttemptStats
    change_bp: int | None
    verdict: str
    verdict_label: str


class Attention(ApiModel):
    verdict: str  # degraded | no_degradation | not_enough_data | no_data
    degraded_channels: list[str]


class TrendPoint(ApiModel):
    day: str
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None
    low_volume: bool


class FailureSignal(ApiModel):
    code: str
    label: str
    attempts: int
    payments: int


class Recovery(ApiModel):
    currency: str
    affected_payments: int
    affected_cents: int
    failed_attempts: int
    recovered_payments: int
    recovered_cents: int
    recovered_within_window_payments: int
    recovered_within_window_cents: int
    unresolved_payments: int
    unresolved_cents: int
    retry_pending_payments: int
    retry_pending_cents: int


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    baseline_period: PeriodInfo
    rules: HealthRules
    summary: ScopeSummary
    attention: Attention
    channels: list[ChannelHealth]
    trend: list[TrendPoint]
    failure_signals: list[FailureSignal]
    recovery: Recovery
    unresolved_payments: list[PaymentListItem]
    unresolved_total: int


class FailureSignalOptions(ApiModel):
    items: list[Option]
