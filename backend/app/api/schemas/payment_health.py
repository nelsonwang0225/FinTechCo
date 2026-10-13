from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PaymentListItem, PeriodInfo


class BaselineInfo(ApiModel):
    from_date: str
    to_date: str
    range_label: str
    days: int


class Thresholds(ApiModel):
    min_completed_attempts: int
    degradation_points: int
    low_volume_day_attempts: int
    baseline_days: int
    recovery_window_minutes: int


class AttemptStats(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bps: int | None


class HealthSummary(ApiModel):
    period: AttemptStats
    baseline: AttemptStats
    change_bps: int | None
    assessment: str
    assessment_label: str


class ChannelHealth(ApiModel):
    channel: str
    channel_label: str
    period: AttemptStats
    baseline: AttemptStats
    change_bps: int | None
    assessment: str
    assessment_label: str


class TrendPoint(ApiModel):
    date: str
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


class RecoverySummary(ApiModel):
    affected_payments: int
    recovered_payments: int
    recovered_within_window_payments: int
    unresolved_payments: int
    awaiting_outcome_payments: int
    affected_value_cents: int
    recovered_value_cents: int
    unresolved_value_cents: int
    awaiting_outcome_value_cents: int
    currency: str


class UnresolvedPayments(ApiModel):
    items: list[PaymentListItem]
    total: int


class PaymentHealthResponse(ApiModel):
    as_of: str
    period: PeriodInfo
    baseline: BaselineInfo
    channel: str | None
    thresholds: Thresholds
    summary: HealthSummary
    channels: list[ChannelHealth]
    trend: list[TrendPoint]
    failure_signals: list[FailureSignal]
    recovery: RecoverySummary
    unresolved: UnresolvedPayments
