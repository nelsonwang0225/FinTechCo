"""Payouts: list with the funds summary, detail that reconciles exactly to its movements, and the movement CSV."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from app.api.listing import page_params
from app.api.schemas.payouts import FundsSummary, MovementItem, NextPayout, PayoutBuckets, PayoutDetail, PayoutListItem, PayoutListResponse
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import clock, schedule
from app.core.labels import MOVEMENT_TYPE_LABELS, PAYOUT_STATUS_LABELS
from app.core.tz import chicago_date_string, chicago_range, to_iso
from app.db.connection import get_conn
from app.db.queries import payouts as payouts_q
from app.db.queries.common import Page
from app.exports import csv as csv_export
from app.main import ApiError

router = APIRouter(prefix="/api/payouts", tags=["payouts"])

PayoutStatus = Literal["in_transit", "paid"]


def destination_string(row: sqlite3.Row, merchant_name: str) -> str:
    return f"{merchant_name}, {row['destination_label']} •••• {row['destination_last4']}, {row['destination_kind']}, demo record"


def list_item(row: sqlite3.Row, merchant_name: str) -> PayoutListItem:
    return PayoutListItem(
        id=row["id"],
        status=row["status"],
        status_label=PAYOUT_STATUS_LABELS[row["status"]],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        cutoff_at=row["cutoff_at"],
        payout_date=chicago_date_string(row["cutoff_at"]),
        sent_at=row["sent_at"],
        expected_arrival_date=row["expected_arrival_date"],
        paid_at=row["paid_at"],
        destination=destination_string(row, merchant_name),
    )


def movement_item(row: sqlite3.Row) -> MovementItem:
    return MovementItem(
        id=row["id"],
        type=row["type"],
        type_label=MOVEMENT_TYPE_LABELS[row["type"]],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        description=row["description"],
        posted_at=row["posted_at"],
        available_at=row["available_at"],
        payment_id=row["payment_id"],
        order_reference=row["order_reference"],
        customer_name=row["customer_name"],
        refund_id=row["refund_id"],
        dispute_id=row["dispute_id"],
    )


def funds_summary(principal: Principal, conn: sqlite3.Connection) -> FundsSummary:
    now = clock.now(conn)
    now_text = to_iso(now)
    available, pending = payouts_q.funds_summary(principal.merchant_id, conn, now_text)
    profile = payouts_q.merchant_payout_profile(principal.merchant_id, conn)
    cutoff = schedule.next_cutoff(profile["payout_schedule"], now)
    return FundsSummary(
        as_of=now_text,
        available_cents=available,
        pending_cents=pending,
        currency="USD",
        next_payout=NextPayout(
            cutoff_at=to_iso(cutoff),
            payout_date=chicago_date_string(cutoff),
            amount_cents=available,
            currency="USD",
            schedule=profile["payout_schedule"],
            schedule_label=schedule.SCHEDULE_LABELS[profile["payout_schedule"]],
            note="Estimate as of now: the funds currently available for payout. Not a bank balance.",
        ),
        destination=destination_string(profile, principal.merchant_name),
    )


@router.get("", response_model=PayoutListResponse)
def list_payouts(
    principal: Principal = Depends(require("payouts:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    page: Page = Depends(page_params),
    status_filter: PayoutStatus | None = Query(None, alias="status"),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
) -> PayoutListResponse:
    start = end = None
    if from_date or to_date:
        if not (from_date and to_date):
            raise ApiError(422, "validation_error", "from and to must be given together")
        if to_date < from_date:
            raise ApiError(422, "validation_error", "period end precedes period start")
        start, end = chicago_range(from_date, to_date)
    filters = payouts_q.PayoutFilters(status=status_filter, start=start, end=end)
    rows, total = payouts_q.list_payouts(principal.merchant_id, conn, filters, page)
    return PayoutListResponse(
        items=[list_item(r, principal.merchant_name) for r in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
        summary=funds_summary(principal, conn),
    )


def _load_reconciled(principal: Principal, conn: sqlite3.Connection, payout_id: str) -> tuple[sqlite3.Row, list[sqlite3.Row], int]:
    row = payouts_q.get_payout(principal.merchant_id, conn, payout_id)
    if row is None:
        raise ApiError(404, "not_found", "That payout is not in this business.")
    movements = payouts_q.list_movements_for_payout(principal.merchant_id, conn, payout_id)
    total, count = payouts_q.ledger_total(principal.merchant_id, conn, payout_id)
    if total != row["amount_cents"] or count != len(movements):
        raise ApiError(500, "reconciliation_mismatch", "This payout does not reconcile to its ledger movements.")
    return row, movements, total


@router.get("/{payout_id}", response_model=PayoutDetail)
def get_payout(payout_id: str, principal: Principal = Depends(require("payouts:read")), conn: sqlite3.Connection = Depends(get_conn)) -> PayoutDetail:
    row, movements, total = _load_reconciled(principal, conn, payout_id)
    buckets = payouts_q.bucket_totals(principal.merchant_id, conn, payout_id)
    base = list_item(row, principal.merchant_name)
    return PayoutDetail(
        **base.model_dump(),
        destination_label=row["destination_label"],
        destination_last4=row["destination_last4"],
        destination_kind=row["destination_kind"],
        buckets=PayoutBuckets(
            collections_cents=buckets["collections"],
            fees_cents=buckets["fees"],
            refunds_cents=buckets["refunds"],
            disputes_cents=buckets["disputes"],
            adjustments_cents=buckets["adjustments"],
        ),
        movement_total_cents=total,
        movement_count=len(movements),
        reconciled=total == row["amount_cents"],
        movements=[movement_item(m) for m in movements],
    )


EXPORT_HEADER = [
    "movement_id", "type", "type_label", "amount_cents", "amount_usd", "currency", "description",
    "posted_at", "posted_at_chicago", "available_at", "available_at_chicago",
    "payment_id", "order_reference", "customer_name", "refund_id", "dispute_id", "payout_id",
]


@router.get("/{payout_id}/export.csv", response_class=Response)
def export_payout_csv(
    payout_id: str,
    principal: Principal = Depends(require("reports:financial")),
    conn: sqlite3.Connection = Depends(get_conn),
) -> StreamingResponse:
    row, movements, _ = _load_reconciled(principal, conn, payout_id)
    payout_day = chicago_date_string(row["cutoff_at"])
    filename = csv_export.export_filename(principal.merchant_slug, "payout", payout_day, payout_id)
    csv_export.record_export(principal, conn, filename, f"Downloaded the movement CSV for payout {payout_id} ({payout_day}).", payout_id=payout_id)
    rows = (
        [
            m["id"], m["type"], MOVEMENT_TYPE_LABELS[m["type"]], m["amount_cents"], csv_export.usd(m["amount_cents"]), m["currency"], m["description"],
            m["posted_at"], csv_export.chicago(m["posted_at"]), m["available_at"], csv_export.chicago(m["available_at"]),
            m["payment_id"], m["order_reference"], m["customer_name"], m["refund_id"], m["dispute_id"], m["payout_id"],
        ]
        for m in movements
    )
    return csv_export.stream_csv(filename, EXPORT_HEADER, rows)
