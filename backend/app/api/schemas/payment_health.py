from __future__ import annotations

from typing import Literal

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import CustomerRef, PeriodInfo

Evaluation = Literal["degraded", "not_degraded", "insufficient_volume", "no_completed"]


class Thresholds(ApiModel):
    baseline_days: int
    min_period_completed: int
    min_baseline_completed: int
    degraded_drop_bps: int
    low_volume_day_completed: int
    recovery_window_minutes: int


class BaselinePeriod(ApiModel):
    from_date: str
    to_date: str
    range_label: str


class OutcomeCounts(ApiModel):
    succeeded: int
    failed: int
    pending: int
    completed: int
    success_rate_bps: int | None  # succeeded / completed in basis points, half-up; None when nothing completed


class ChannelHealth(ApiModel):
    channel: str
    channel_label: str
    period: OutcomeCounts
    baseline: OutcomeCounts
    drop_bps: int | None  # baseline rate minus period rate; None unless both have a rate
    evaluation: Evaluation
    evaluation_label: str


class ScopeSummary(ApiModel):
    period: OutcomeCounts
    baseline: OutcomeCounts


class Attention(ApiModel):
    status: Evaluation
    status_label: str
    degraded: list[ChannelHealth]
    not_evaluated: list[ChannelHealth]


class DailyPoint(ApiModel):
    day: str
    succeeded: int
    failed: int
    pending: int
    success_rate_bps: int | None
    low_volume: bool


class FailureSignal(ApiModel):
    code: str
    label: str
    failed_attempts: int


class Recovery(ApiModel):
    affected_payments: int
    recovered_payments: int
    recovered_within_window: int
    unresolved_payments: int
    unresolved_retry_pending: int
    affected_cents: int
    recovered_cents: int
    unresolved_cents: int
    currency: str


class UnresolvedPayment(ApiModel):
    id: str
    order_reference: str
    created_at: str
    amount_cents: int
    currency: str
    channel: str
    channel_label: str
    status: str
    status_label: str
    failed_attempts: int
    last_failure_code: str
    last_failure_label: str
    customer: CustomerRef | None


class PaymentHealthResponse(ApiModel):
    period: PeriodInfo
    baseline_period: BaselinePeriod
    channel: str | None
    channel_label: str
    thresholds: Thresholds
    summary: ScopeSummary
    attention: Attention
    channels: list[ChannelHealth]
    daily: list[DailyPoint]
    failure_signals: list[FailureSignal]
    recovery: Recovery
    unresolved: list[UnresolvedPayment]
