"""Disputes: the queue, a case with its derived history, and internal notes (the second of the two product writes)."""

from __future__ import annotations

import secrets
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.listing import now_iso, page_params
from app.api.payments import note_item
from app.api.schemas.disputes import DisputeDetail, DisputeListItem, DisputeListResponse, DisputePaymentRef
from app.api.schemas.payments import CustomerRef, NoteCreate, NoteItem, TimelineEventItem
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import clock, ids
from app.core.labels import DISPUTE_REASON_LABELS, DISPUTE_STATUS_LABELS
from app.core.timeline import build_dispute_history
from app.core.tz import to_iso
from app.db.connection import get_conn
from app.db.queries import disputes as disputes_q
from app.db.queries import notes as notes_q
from app.db.queries.common import Page
from app.main import ApiError

router = APIRouter(prefix="/api/disputes", tags=["disputes"])

DisputeStatus = Literal["needs_response", "under_review", "won", "lost"]
DisputeReason = Literal["fraudulent", "product_not_received", "product_unacceptable", "duplicate", "credit_not_processed"]
DisputeSort = Literal["queue", "due", "opened_at", "amount", "status"]
Direction = Literal["asc", "desc"]


def dispute_item(row: sqlite3.Row) -> DisputeListItem:
    customer = None
    if row["customer_id"] is not None:
        customer = CustomerRef(id=row["customer_id"], full_name=row["customer_name"], email=row["customer_email"], reference=row["customer_reference"])
    return DisputeListItem(
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
        payment=DisputePaymentRef(
            id=row["payment_id"],
            order_reference=row["order_reference"],
            amount_cents=row["payment_amount_cents"],
            currency=row["currency"],
            created_at=row["payment_created_at"],
            customer=customer,
        ),
    )


@router.get("", response_model=DisputeListResponse)
def list_disputes(
    principal: Principal = Depends(require("disputes:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    page: Page = Depends(page_params),
    status_filter: DisputeStatus | None = Query(None, alias="status"),
    reason: DisputeReason | None = None,
    sort: DisputeSort = "queue",
    direction: Direction = Query("asc", alias="dir"),
) -> DisputeListResponse:
    filters = disputes_q.DisputeFilters(status=status_filter, reason=reason, sort=sort, direction=direction)
    rows, total = disputes_q.list_disputes(principal.merchant_id, conn, filters, page)
    return DisputeListResponse(items=[dispute_item(r) for r in rows], page=page.page, page_size=page.page_size, total=total)


@router.get("/{dispute_id}", response_model=DisputeDetail)
def get_dispute(dispute_id: str, principal: Principal = Depends(require("disputes:read")), conn: sqlite3.Connection = Depends(get_conn)) -> DisputeDetail:
    row = disputes_q.get_dispute(principal.merchant_id, conn, dispute_id)
    if row is None:
        raise ApiError(404, "not_found", "That dispute is not in this business.")
    movements = disputes_q.list_movements_for_dispute(principal.merchant_id, conn, dispute_id)
    notes = disputes_q.list_notes_for_dispute(principal.merchant_id, conn, dispute_id)
    history = build_dispute_history(now_iso=now_iso(conn), dispute=row, movements=movements, notes=notes)
    return DisputeDetail(
        **dispute_item(row).model_dump(),
        history=[TimelineEventItem(**e.__dict__) for e in history],
        notes=[note_item(n) for n in notes],
    )


@router.post("/{dispute_id}/notes", response_model=NoteItem, status_code=status.HTTP_201_CREATED)
def add_dispute_note(
    dispute_id: str,
    body: NoteCreate,
    principal: Principal = Depends(require("notes:write")),
    conn: sqlite3.Connection = Depends(get_conn),
) -> NoteItem:
    text = body.body.strip()
    if not text:
        raise ApiError(422, "validation_error", "body: a note needs some text")
    if not disputes_q.dispute_exists(principal.merchant_id, conn, dispute_id):
        raise ApiError(404, "not_found", "That dispute is not in this business.")
    note_id = ids.new_id("note_event", secrets.SystemRandom())
    created_at = to_iso(clock.wall_now())
    notes_q.insert_note(principal.merchant_id, conn, note_id=note_id, actor_user_id=principal.user_id, body=text, created_at=created_at, dispute_id=dispute_id)
    row = notes_q.get_note(principal.merchant_id, conn, note_id)
    assert row is not None
    return note_item(row)
