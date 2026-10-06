from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PeriodInfo


class AttemptPerformance(ApiModel):
    succeeded: int
    failed: int
    completed: int
    pending_excluded: int
    success_rate_bp: int | None  # basis points, half-up; None when no attempt completed
    low_volume: bool
    low_volume_threshold: int


class TrendPoint(ApiModel):
    day: str
    succeeded: int
    failed: int


class Trend(ApiModel):
    granularity: str
    points: list[TrendPoint]


class FailureSignal(ApiModel):
    failure_code: str
    label: str
    count: int


class FailureSignals(ApiModel):
    total_failed: int
    items: list[FailureSignal]


class Recovery(ApiModel):
    affected_payments: int
    recovered: int
    recovered_within_hour: int
    unresolved: int
    attempt_pending: int
    affected_cents: int
    recovered_cents: int
    unresolved_cents: int
    attempt_pending_cents: int
    currency: str


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    channel: str | None
    channel_label: str
    as_of: str
    attempts: AttemptPerformance
    trend: Trend
    failure_signals: FailureSignals
    recovery: Recovery
