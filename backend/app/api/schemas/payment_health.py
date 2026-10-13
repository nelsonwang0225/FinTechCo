from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import CustomerRef, PeriodInfo


class HealthRules(ApiModel):
    baseline_days: int
    min_period_completed: int
    min_baseline_completed: int
    degraded_drop_bps: int
    low_volume_day_completed: int
    quick_recovery_minutes: int


class AttemptMetrics(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bps: int | None
    failure_rate_bps: int | None


class ChannelHealth(ApiModel):
    channel: str
    channel_label: str
    period: AttemptMetrics
    baseline: AttemptMetrics
    change_bps: int | None
    verdict: str
    verdict_label: str


class ScopeHealth(ApiModel):
    period: AttemptMetrics
    baseline: AttemptMetrics
    change_bps: int | None


class Attention(ApiModel):
    state: str
    degraded_channels: list[ChannelHealth]
    insufficient_channels: list[str]


class TrendPoint(ApiModel):
    day: str
    succeeded: int
    failed: int
    pending: int
    success_rate_bps: int | None
    low_volume: bool
    partial: bool


class FailureSignal(ApiModel):
    code: str
    label: str
    count: int


class Recovery(ApiModel):
    affected_count: int
    affected_cents: int
    recovered_count: int
    recovered_cents: int
    recovered_within_hour_count: int
    recovered_within_hour_cents: int
    unresolved_count: int
    unresolved_cents: int
    in_progress_count: int
    in_progress_cents: int
    currency: str


class UnresolvedPayment(ApiModel):
    id: str
    order_reference: str
    created_at: str
    amount_cents: int
    currency: str
    channel: str
    channel_label: str
    customer: CustomerRef | None
    failed_attempts: int
    last_failure_code: str
    last_failure_label: str
    last_attempt_at: str


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    baseline_period: PeriodInfo
    channel: str | None
    as_of: str
    rules: HealthRules
    scope: ScopeHealth
    attention: Attention
    channels: list[ChannelHealth]
    trend: list[TrendPoint]
    failure_signals: list[FailureSignal]
    recovery: Recovery
    unresolved_payments: list[UnresolvedPayment]


class FailureSignalsResponse(ApiModel):
    period: PeriodInfo
    channel: str | None
    signals: list[FailureSignal]
