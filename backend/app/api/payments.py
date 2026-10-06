"""Payments: list, detail with a derived timeline, and investigation notes (the product's write path)."""

from __future__ import annotations

import secrets
import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.listing import now_iso, page_params, period_info, resolve_period
from app.api.schemas.payments import (
    AttemptItem,
    CustomerRef,
    DisputeTag,
    LocationRef,
    MethodInfo,
    NoteCreate,
    NoteItem,
    NoteActor,
    PaymentDetail,
    PaymentListItem,
    PaymentListResponse,
    PayoutRef,
    RefundItem,
    TimelineEventItem,
)
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import clock, ids
from app.core.labels import (
    ATTEMPT_OUTCOME_LABELS,
    CHANNEL_LABELS,
    DISPUTE_REASON_LABELS,
    DISPUTE_STATUS_LABELS,
    PAYMENT_STATUS_LABELS,
    PAYOUT_STATUS_LABELS,
    REFUND_REASON_LABELS,
    REFUND_STATUS_LABELS,
    method_label,
)
from app.core.timeline import build_timeline
from app.core.tz import to_iso
from app.db.connection import get_conn
from app.db.queries import notes as notes_q
from app.db.queries import payments as payments_q
from app.db.queries.common import Page
from app.main import ApiError

router = APIRouter(prefix="/api/payments", tags=["payments"])

Channel = Literal["website", "mobile_app", "in_store"]
PaymentStatus = Literal["succeeded", "pending", "failed", "partially_refunded", "refunded"]
PaymentSort = Literal["created_at", "amount", "status", "order_reference", "customer"]
Direction = Literal["asc", "desc"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]


def method_info(row: sqlite3.Row) -> MethodInfo | None:
    label = method_label(row["method_type"], row["card_brand"], row["card_last4"], row["wallet_type"])
    if label is None:
        return None
    return MethodInfo(type=row["method_type"], card_brand=row["card_brand"], card_last4=row["card_last4"], wallet_type=row["wallet_type"], label=label)


def customer_ref(row: sqlite3.Row) -> CustomerRef | None:
    if row["customer_id"] is None:
        return None
    return CustomerRef(id=row["customer_id"], full_name=row["customer_name"], email=row["customer_email"], reference=row["customer_reference"])


def location_ref(row: sqlite3.Row) -> LocationRef | None:
    if row["location_id"] is None:
        return None
    return LocationRef(id=row["location_id"], name=row["location_name"])


def list_item(row: sqlite3.Row) -> PaymentListItem:
    return PaymentListItem(
        id=row["id"],
        order_reference=row["order_reference"],
        created_at=row["created_at"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        status=row["status"],
        status_label=PAYMENT_STATUS_LABELS[row["status"]],
        channel=row["channel"],
        channel_label=CHANNEL_LABELS[row["channel"]],
        location=location_ref(row),
        customer=customer_ref(row),
        method=method_info(row),
        refunded_cents=row["refunded_cents"],
        net_cents=row["net_cents"],
        dispute_id=row["dispute_id"],
        dispute_status=row["dispute_status"],
    )


def attempt_item(row: sqlite3.Row) -> AttemptItem:
    method = method_info(row)
    assert method is not None  # attempts always carry a method
    return AttemptItem(
        id=row["id"],
        payment_id=row["payment_id"],
        attempt_number=row["attempt_number"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        outcome=row["outcome"],
        outcome_label=ATTEMPT_OUTCOME_LABELS[row["outcome"]],
        failure_code=row["failure_code"],
        failure_message=row["failure_message"],
        method=method,
    )


def refund_item(row: sqlite3.Row) -> RefundItem:
    return RefundItem(
        id=row["id"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        reason=row["reason"],
        reason_label=REFUND_REASON_LABELS[row["reason"]],
        status=row["status"],
        status_label=REFUND_STATUS_LABELS[row["status"]],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


def dispute_tag(row: sqlite3.Row) -> DisputeTag:
    return DisputeTag(
        id=row["id"],
        status=row["status"],
        status_label=DISPUTE_STATUS_LABELS[row["status"]],
        reason=row["reason"],
        reason_label=DISPUTE_REASON_LABELS[row["reason"]],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        opened_at=row["opened_at"],
        evidence_due_at=row["evidence_due_at"],
        responded_at=row["responded_at"],
        resolved_at=row["resolved_at"],
    )


def note_item(row: sqlite3.Row) -> NoteItem:
    return NoteItem(id=row["id"], body=row["body"], created_at=row["created_at"], actor=NoteActor(id=row["actor_id"], full_name=row["actor_name"]))


@router.get("", response_model=PaymentListResponse)
def list_payments(
    principal: Principal = Depends(require("payments:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    page: Page = Depends(page_params),
    q: str | None = Query(None, max_length=120),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    status_filter: PaymentStatus | None = Query(None, alias="status"),
    channel: Channel | None = None,
    location_id: str | None = Query(None, max_length=40),
    amount_min_cents: int | None = Query(None, ge=0),
    amount_max_cents: int | None = Query(None, ge=0),
    customer_id: str | None = Query(None, max_length=40),
    sort: PaymentSort = "created_at",
    direction: Direction = Query("desc", alias="dir"),
) -> PaymentListResponse:
    resolved = resolve_period(conn, period, from_date, to_date)
    filters = payments_q.PaymentFilters(
        start=resolved.start,
        end=resolved.end,
        search=q,
        status=status_filter,
        channel=channel,
        location_id=location_id,
        amount_min_cents=amount_min_cents,
        amount_max_cents=amount_max_cents,
        customer_id=customer_id,
        sort=sort,
        direction=direction,
    )
    rows, total, total_amount_cents = payments_q.list_payments(principal.merchant_id, conn, filters, page)
    return PaymentListResponse(
        items=[list_item(r) for r in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
        total_amount_cents=total_amount_cents,
        currency="USD",
        period=period_info(resolved),
    )


@router.get("/{payment_id}", response_model=PaymentDetail)
def get_payment(payment_id: str, principal: Principal = Depends(require("payments:read")), conn: sqlite3.Connection = Depends(get_conn)) -> PaymentDetail:
    row = payments_q.get_payment(principal.merchant_id, conn, payment_id)
    if row is None:
        raise ApiError(404, "not_found", "That payment is not in this business.")
    attempts = payments_q.list_attempts_for_payment(principal.merchant_id, conn, payment_id)
    refunds = payments_q.list_refunds_for_payment(principal.merchant_id, conn, payment_id)
    dispute = payments_q.get_dispute_for_payment(principal.merchant_id, conn, payment_id)
    charge = payments_q.get_charge_movement(principal.merchant_id, conn, payment_id)
    notes = payments_q.list_notes_for_payment(principal.merchant_id, conn, payment_id)
    timeline = build_timeline(
        now_iso=now_iso(conn),
        payment=row,
        attempts=attempts,
        refunds=refunds,
        dispute=dispute,
        charge=charge,
        notes=notes,
        channel_label=CHANNEL_LABELS[row["channel"]],
    )
    payout = None
    if charge is not None and charge["payout_id"]:
        payout = PayoutRef(
            id=charge["payout_id"],
            status=charge["payout_status"],
            status_label=PAYOUT_STATUS_LABELS[charge["payout_status"]],
            cutoff_at=charge["cutoff_at"],
            sent_at=charge["sent_at"],
            paid_at=charge["paid_at"],
        )
    return PaymentDetail(
        id=row["id"],
        order_reference=row["order_reference"],
        description=row["description"],
        created_at=row["created_at"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        status=row["status"],
        status_label=PAYMENT_STATUS_LABELS[row["status"]],
        channel=row["channel"],
        channel_label=CHANNEL_LABELS[row["channel"]],
        location=location_ref(row),
        customer=customer_ref(row),
        method=method_info(row),
        refunded_cents=row["refunded_cents"],
        net_cents=row["net_cents"],
        succeeded_at=row["succeeded_at"],
        funds_available_at=charge["available_at"] if charge is not None else None,
        payout=payout,
        dispute=dispute_tag(dispute) if dispute is not None else None,
        attempts=[attempt_item(a) for a in attempts],
        refunds=[refund_item(r) for r in refunds],
        notes=[note_item(n) for n in notes],
        timeline=[TimelineEventItem(**e.__dict__) for e in timeline],
    )


@router.post("/{payment_id}/notes", response_model=NoteItem, status_code=status.HTTP_201_CREATED)
def add_payment_note(
    payment_id: str,
    body: NoteCreate,
    principal: Principal = Depends(require("notes:write")),
    conn: sqlite3.Connection = Depends(get_conn),
) -> NoteItem:
    text = body.body.strip()
    if not text:
        raise ApiError(422, "validation_error", "body: a note needs some text")
    if not payments_q.payment_exists(principal.merchant_id, conn, payment_id):
        raise ApiError(404, "not_found", "That payment is not in this business.")
    note_id = ids.new_id("note_event", secrets.SystemRandom())
    created_at = to_iso(clock.wall_now())
    notes_q.insert_note(principal.merchant_id, conn, note_id=note_id, actor_user_id=principal.user_id, body=text, created_at=created_at, payment_id=payment_id)
    row = notes_q.get_note(principal.merchant_id, conn, note_id)
    assert row is not None
    return note_item(row)
