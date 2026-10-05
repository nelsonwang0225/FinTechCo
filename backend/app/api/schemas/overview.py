from __future__ import annotations

from typing import Literal

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PaymentListItem, PeriodInfo
from app.api.schemas.payouts import NextPayout, PayoutBuckets

AttentionKind = Literal["dispute_deadline", "payout_in_transit", "refund_pending"]
AttentionLinkKind = Literal["dispute", "payout", "payment"]


class Greeting(ApiModel):
    salutation: str
    first_name: str
    merchant_name: str
    as_of: str


class OverviewTiles(ApiModel):
    collected_cents: int
    refunds_cents: int
    funds_available_cents: int
    pending_cents: int
    currency: str
    next_payout: NextPayout


class ChartPoint(ApiModel):
    day: str
    amount_cents: int


class CollectedChart(ApiModel):
    title: str
    points: list[ChartPoint]
    total_cents: int
    currency: str


class UpcomingPayout(ApiModel):
    cutoff_at: str
    payout_date: str
    amount_cents: int
    currency: str
    schedule: str
    schedule_label: str
    destination: str
    note: str
    buckets: PayoutBuckets


class AttentionLink(ApiModel):
    kind: AttentionLinkKind
    id: str
    permission: str


class AttentionItem(ApiModel):
    kind: AttentionKind
    title: str
    detail: str
    at: str
    at_label: str
    amount_cents: int
    currency: str
    link: AttentionLink


class OverviewResponse(ApiModel):
    greeting: Greeting
    period: PeriodInfo
    tiles: OverviewTiles
    chart: CollectedChart
    recent_payments: list[PaymentListItem]
    upcoming_payout: UpcomingPayout
    attention: list[AttentionItem]
