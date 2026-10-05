from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import CustomerRef, NoteItem, TimelineEventItem


class DisputePaymentRef(ApiModel):
    id: str
    order_reference: str
    amount_cents: int
    currency: str
    created_at: str
    customer: CustomerRef | None


class DisputeListItem(ApiModel):
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
    payment: DisputePaymentRef


class DisputeListResponse(ApiModel):
    items: list[DisputeListItem]
    page: int
    page_size: int
    total: int


class DisputeDetail(DisputeListItem):
    history: list[TimelineEventItem]
    notes: list[NoteItem]
