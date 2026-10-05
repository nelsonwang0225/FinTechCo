"""Customers: a merchant-scoped directory and a detail page with the customer's payments and refunds."""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import page_params
from app.api.payments import list_item
from app.api.schemas.customers import CustomerDetail, CustomerListItem, CustomerListResponse, CustomerRefundItem
from app.auth.permissions import require
from app.auth.session import Principal
from app.core.labels import REFUND_REASON_LABELS, REFUND_STATUS_LABELS
from app.db.connection import get_conn
from app.db.queries import customers as customers_q
from app.db.queries.common import Page
from app.main import ApiError

router = APIRouter(prefix="/api/customers", tags=["customers"])

CustomerSort = Literal["name", "email", "reference", "first_payment_at", "last_activity_at"]
Direction = Literal["asc", "desc"]


def customer_item(row: sqlite3.Row) -> CustomerListItem:
    return CustomerListItem(
        id=row["id"],
        reference=row["reference"],
        full_name=row["full_name"],
        email=row["email"],
        created_at=row["created_at"],
        first_payment_at=row["first_payment_at"],
        last_activity_at=row["last_activity_at"],
    )


def customer_refund_item(row: sqlite3.Row) -> CustomerRefundItem:
    return CustomerRefundItem(
        id=row["id"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        reason=row["reason"],
        reason_label=REFUND_REASON_LABELS[row["reason"]],
        status=row["status"],
        status_label=REFUND_STATUS_LABELS[row["status"]],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        payment_id=row["payment_id"],
        order_reference=row["order_reference"],
    )


@router.get("", response_model=CustomerListResponse)
def list_customers(
    principal: Principal = Depends(require("customers:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    page: Page = Depends(page_params),
    q: str | None = Query(None, max_length=120),
    sort: CustomerSort = "last_activity_at",
    direction: Direction = Query("desc", alias="dir"),
) -> CustomerListResponse:
    filters = customers_q.CustomerFilters(search=q, sort=sort, direction=direction)
    rows, total = customers_q.list_customers(principal.merchant_id, conn, filters, page)
    return CustomerListResponse(items=[customer_item(r) for r in rows], page=page.page, page_size=page.page_size, total=total)


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(customer_id: str, principal: Principal = Depends(require("customers:read")), conn: sqlite3.Connection = Depends(get_conn)) -> CustomerDetail:
    row = customers_q.get_customer(principal.merchant_id, conn, customer_id)
    if row is None:
        raise ApiError(404, "not_found", "That customer is not in this business.")
    payments = customers_q.list_payments_for_customer(principal.merchant_id, conn, customer_id)
    refunds = customers_q.list_refunds_for_customer(principal.merchant_id, conn, customer_id)
    return CustomerDetail(**customer_item(row).model_dump(), payments=[list_item(p) for p in payments], refunds=[customer_refund_item(r) for r in refunds])
