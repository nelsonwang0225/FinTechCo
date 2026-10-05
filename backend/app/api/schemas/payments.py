from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ApiModel


class PeriodInfo(ApiModel):
    preset: str
    label: str
    from_date: str
    to_date: str
    range_label: str


class MethodInfo(ApiModel):
    type: str
    card_brand: str
    card_last4: str
    wallet_type: str | None
    label: str


class CustomerRef(ApiModel):
    id: str
    full_name: str
    email: str
    reference: str


class LocationRef(ApiModel):
    id: str
    name: str


class PaymentListItem(ApiModel):
    id: str
    order_reference: str
    created_at: str
    amount_cents: int
    currency: str
    status: str
    status_label: str
    channel: str
    channel_label: str
    location: LocationRef | None
    customer: CustomerRef | None
    method: MethodInfo | None
    refunded_cents: int
    net_cents: int
    dispute_id: str | None
    dispute_status: str | None


class PaymentListResponse(ApiModel):
    items: list[PaymentListItem]
    page: int
    page_size: int
    total: int
    period: PeriodInfo


class AttemptItem(ApiModel):
    id: str
    payment_id: str
    attempt_number: int
    created_at: str
    completed_at: str | None
    outcome: str
    outcome_label: str
    failure_code: str | None
    failure_message: str | None
    method: MethodInfo


class AttemptListItem(AttemptItem):
    order_reference: str
    amount_cents: int
    currency: str
    channel: str
    channel_label: str
    location: LocationRef | None
    customer: CustomerRef | None


class AttemptListResponse(ApiModel):
    items: list[AttemptListItem]
    page: int
    page_size: int
    total: int
    period: PeriodInfo


class RefundItem(ApiModel):
    id: str
    amount_cents: int
    currency: str
    reason: str
    reason_label: str
    status: str
    status_label: str
    created_at: str
    completed_at: str | None


class DisputeTag(ApiModel):
    id: str
    status: str
    status_label: str
    reason: str
    reason_label: str
    amount_cents: int
    currency: str
    opened_at: str
    evidence_due_at: str
    responded_at: str | None
    resolved_at: str | None


class PayoutRef(ApiModel):
    id: str
    status: str
    status_label: str
    cutoff_at: str
    sent_at: str
    paid_at: str | None


class NoteActor(ApiModel):
    id: str
    full_name: str


class NoteItem(ApiModel):
    id: str
    body: str
    created_at: str
    actor: NoteActor


class NoteCreate(ApiModel):
    body: str = Field(min_length=1, max_length=2000)


class TimelineEventItem(ApiModel):
    kind: str
    at: str
    title: str
    detail: str | None
    upcoming: bool
    amount_cents: int | None
    ref_id: str | None


class PaymentDetail(ApiModel):
    id: str
    order_reference: str
    description: str
    created_at: str
    amount_cents: int
    currency: str
    status: str
    status_label: str
    channel: str
    channel_label: str
    location: LocationRef | None
    customer: CustomerRef | None
    method: MethodInfo | None
    refunded_cents: int
    net_cents: int
    succeeded_at: str | None
    funds_available_at: str | None
    payout: PayoutRef | None
    dispute: DisputeTag | None
    attempts: list[AttemptItem]
    refunds: list[RefundItem]
    notes: list[NoteItem]
    timeline: list[TimelineEventItem]
