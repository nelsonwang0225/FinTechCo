from __future__ import annotations

from app.api.schemas.common import ApiModel, Option


class LocationOption(ApiModel):
    id: str
    name: str
    address_line: str
    city: str
    state: str


class MetaResponse(ApiModel):
    channels: list[Option]
    payment_statuses: list[Option]
    attempt_outcomes: list[Option]
    failure_signals: list[Option]
    refund_statuses: list[Option]
    refund_reasons: list[Option]
    dispute_statuses: list[Option]
    dispute_reasons: list[Option]
    payout_statuses: list[Option]
    period_presets: list[Option]
    default_period: str
    locations: list[LocationOption]
    timezone: str
