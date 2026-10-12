"""Payment Health response. Rates are integer basis points (9123 = 91.23%), None when nothing completed; money is int cents."""

from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PeriodInfo


class HealthRules(ApiModel):
    baseline_days: int
    degraded_drop_bp: int
    min_period_completed: int
    min_baseline_completed: int
    low_volume_day_completed: int
    quick_recovery_seconds: int


class BaselineInfo(ApiModel):
    from_date: str
    to_date: str
    range_label: str
    days: int
    days_with_completed: int


class AttemptMetrics(ApiModel):
    completed: int
    succeeded: int
    failed: int
    pending: int
    success_rate_bp: int | None
    baseline_completed: int
    baseline_succeeded: int
    baseline_rate_bp: int | None
    change_bp: int | None


class ChannelHealth(AttemptMetrics):
    channel: str
    channel_label: str
    assessment: str
    assessment_label: str


class Attention(ApiModel):
    state: str
    label: str
    degraded_channels: list[str]
    not_assessed_channels: list[str]


class TrendPoint(ApiModel):
    day: str
    completed: int
    succeeded: int
    failed: int
    pending: int
    success_rate_bp: int | None
    low_volume: bool


class FailureSignal(ApiModel):
    code: str
    label: str
    count: int


class RecoveryGroup(ApiModel):
    payments: int
    amount_cents: int


class RecoverySummary(ApiModel):
    currency: str
    affected: RecoveryGroup
    recovered: RecoveryGroup
    recovered_within_hour: RecoveryGroup
    unresolved: RecoveryGroup
    in_progress: RecoveryGroup


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    baseline: BaselineInfo
    channel: str | None
    channel_label: str | None
    rules: HealthRules
    attempts: AttemptMetrics
    attention: Attention
    channels: list[ChannelHealth]
    trend: list[TrendPoint]
    failure_signals: list[FailureSignal]
    recovery: RecoverySummary
