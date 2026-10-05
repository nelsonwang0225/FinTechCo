from __future__ import annotations

from app.api.schemas.common import ApiModel
from app.api.schemas.payments import PaymentListItem, RefundItem


class CustomerListItem(ApiModel):
    id: str
    reference: str
    full_name: str
    email: str
    created_at: str
    first_payment_at: str | None
    last_activity_at: str | None


class CustomerListResponse(ApiModel):
    items: list[CustomerListItem]
    page: int
    page_size: int
    total: int


class CustomerRefundItem(RefundItem):
    payment_id: str
    order_reference: str


class CustomerDetail(CustomerListItem):
    payments: list[PaymentListItem]
    refunds: list[CustomerRefundItem]
