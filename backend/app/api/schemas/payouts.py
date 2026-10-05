from __future__ import annotations

from app.api.schemas.common import ApiModel


class PayoutListItem(ApiModel):
    id: str
    status: str
    status_label: str
    amount_cents: int
    currency: str
    cutoff_at: str
    payout_date: str
    sent_at: str
    expected_arrival_date: str
    paid_at: str | None
    destination: str


class NextPayout(ApiModel):
    cutoff_at: str
    payout_date: str
    amount_cents: int
    currency: str
    schedule: str
    schedule_label: str
    note: str


class FundsSummary(ApiModel):
    as_of: str
    available_cents: int
    pending_cents: int
    currency: str
    next_payout: NextPayout
    destination: str


class PayoutListResponse(ApiModel):
    items: list[PayoutListItem]
    page: int
    page_size: int
    total: int
    summary: FundsSummary


class MovementItem(ApiModel):
    id: str
    type: str
    type_label: str
    amount_cents: int
    currency: str
    description: str
    posted_at: str
    available_at: str
    payment_id: str | None
    order_reference: str | None
    customer_name: str | None
    refund_id: str | None
    dispute_id: str | None


class PayoutBuckets(ApiModel):
    collections_cents: int
    fees_cents: int
    refunds_cents: int
    disputes_cents: int
    adjustments_cents: int


class PayoutDetail(PayoutListItem):
    destination_label: str
    destination_last4: str
    destination_kind: str
    buckets: PayoutBuckets
    movement_total_cents: int
    movement_count: int
    reconciled: bool
    movements: list[MovementItem]
