from __future__ import annotations

from typing import Literal

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PeriodInfo

Evaluation = Literal["degraded", "within_range", "insufficient_volume"]
SummaryState = Literal["degraded", "no_degradation", "insufficient_volume"]


class BaselineInfo(ApiModel):
    from_date: str
    to_date: str
    range_label: str


class HealthRules(ApiModel):
    baseline_days: int
    min_period_completed: int
    min_baseline_completed: int
    degraded_drop_bp: int


class ChannelHealth(ApiModel):
    channel: str
    channel_label: str
    succeeded: int
    failed: int
    pending: int
    completed: int
    rate_bp: int | None
    baseline_succeeded: int
    baseline_failed: int
    baseline_completed: int
    baseline_rate_bp: int | None
    delta_bp: int | None
    evaluation: Evaluation
    evaluation_label: str


class AttentionSummary(ApiModel):
    state: SummaryState
    message: str
    degraded: list[ChannelHealth]


class HealthKpis(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    rate_bp: int | None
    baseline_completed: int
    baseline_rate_bp: int | None
    delta_bp: int | None
    affected_payments: int
    recovered_payments: int
    unresolved_payments: int
    awaiting_retry_payments: int
    affected_cents: int
    currency: str


class FailureSignal(ApiModel):
    code: str
    label: str
    count: int


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    baseline: BaselineInfo
    channel: str | None
    channel_label: str
    rules: HealthRules
    summary: AttentionSummary
    kpis: HealthKpis
    channels: list[ChannelHealth]
    failure_signals: list[FailureSignal]
