from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PeriodInfo


class HealthThresholds(ApiModel):
    degraded_drop_bp: int
    min_period_completed: int
    min_baseline_completed: int
    low_volume_day_completed: int
    baseline_days: int
    quick_recovery_seconds: int


class BaselineInfo(ApiModel):
    from_date: str
    to_date: str
    range_label: str


class ScopeHealth(ApiModel):
    """Completed-attempt figures for the period and the baseline. Rates are basis points; None when nothing completed."""

    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bp: int | None
    baseline_succeeded: int
    baseline_failed: int
    baseline_completed: int
    baseline_rate_bp: int | None
    change_bp: int | None


class ChannelHealth(ScopeHealth):
    channel: str
    channel_label: str
    assessment: str
    assessment_label: str


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
    failed_attempts: int
    share_bp: int


class RecoveryBucket(ApiModel):
    payments: int
    amount_cents: int


class Recovery(ApiModel):
    affected: RecoveryBucket
    recovered: RecoveryBucket
    recovered_within_hour: RecoveryBucket
    unresolved: RecoveryBucket
    awaiting_retry: RecoveryBucket
    currency: str


class PaymentHealthResponse(ApiModel):
    as_of: str
    period: PeriodInfo
    baseline: BaselineInfo
    channel: str | None
    channel_label: str | None
    thresholds: HealthThresholds
    summary: ScopeHealth
    channels: list[ChannelHealth]
    trend: list[TrendPoint]
    failure_signals: list[FailureSignal]
    recovery: Recovery
