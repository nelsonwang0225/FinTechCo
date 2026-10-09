"""Reports: four CSV exports that reuse the list query builders with pagination removed and the active merchant's scope.

payments.csv and attempts.csv need reports:operational; payouts.csv and refunds.csv need reports:financial. Every download
is recorded as an export activity. Rows carry amount_cents plus amount_usd and Chicago renderings of every timestamp.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from app.api.attempts import FailureCode
from app.api.listing import resolve_period
from app.api.payouts import destination_string
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import periods
from app.core.labels import (
    ATTEMPT_OUTCOME_LABELS,
    CHANNEL_LABELS,
    DISPUTE_STATUS_LABELS,
    PAYMENT_STATUS_LABELS,
    PAYOUT_STATUS_LABELS,
    REFUND_REASON_LABELS,
    REFUND_STATUS_LABELS,
    method_label,
)
from app.core.tz import chicago_date_string, chicago_range
from app.db.connection import get_conn
from app.db.queries import attempts as attempts_q
from app.db.queries import payments as payments_q
from app.db.queries import payouts as payouts_q
from app.db.queries import refunds as refunds_q
from app.exports import csv as csv_export
from app.main import ApiError

router = APIRouter(prefix="/api/reports", tags=["reports"])

Channel = Literal["website", "mobile_app", "in_store"]
PaymentStatus = Literal["succeeded", "pending", "failed", "partially_refunded", "refunded"]
PaymentSort = Literal["created_at", "amount", "status", "order_reference", "customer"]
Outcome = Literal["succeeded", "failed", "pending"]
AttemptSort = Literal["created_at", "amount", "outcome", "order_reference"]
RefundStatus = Literal["pending", "succeeded"]
RefundReason = Literal["requested_by_customer", "damaged_in_transit", "wrong_item", "duplicate", "price_adjustment", "returned_in_store"]
PayoutStatus = Literal["in_transit", "paid"]
Direction = Literal["asc", "desc"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]

PAYMENTS_HEADER = [
    "payment_id", "order_reference", "created_at", "created_at_chicago", "status", "status_label", "channel", "channel_label",
    "location_id", "location_name", "customer_id", "customer_reference", "customer_name", "customer_email",
    "method_type", "card_brand", "card_last4", "wallet_type", "method_label",
    "amount_cents", "amount_usd", "refunded_cents", "refunded_usd", "net_cents", "net_usd", "currency",
    "succeeded_at", "succeeded_at_chicago", "dispute_id", "dispute_status", "description",
]
ATTEMPTS_HEADER = [
    "attempt_id", "payment_id", "order_reference", "attempt_number", "created_at", "created_at_chicago", "completed_at", "completed_at_chicago",
    "outcome", "outcome_label", "failure_code", "failure_message",
    "method_type", "card_brand", "card_last4", "wallet_type", "method_label",
    "amount_cents", "amount_usd", "currency", "channel", "channel_label", "location_id", "location_name",
    "customer_id", "customer_reference", "customer_name", "customer_email",
]
PAYOUTS_HEADER = [
    "payout_id", "status", "status_label", "cutoff_at", "cutoff_at_chicago", "payout_date", "sent_at", "sent_at_chicago",
    "expected_arrival_date", "paid_at", "paid_at_chicago", "destination",
    "collections_cents", "collections_usd", "fees_cents", "fees_usd", "refunds_cents", "refunds_usd",
    "disputes_cents", "disputes_usd", "adjustments_cents", "adjustments_usd", "amount_cents", "amount_usd", "currency",
]
REFUNDS_HEADER = [
    "refund_id", "payment_id", "order_reference", "created_at", "created_at_chicago", "completed_at", "completed_at_chicago",
    "status", "status_label", "reason", "reason_label", "amount_cents", "amount_usd", "currency",
    "channel", "channel_label", "customer_id", "customer_reference", "customer_name", "customer_email",
]


def _period_body(report: str, period: periods.Period) -> str:
    return f"Downloaded the {report} CSV for {period.label.lower()} ({period.range_label})."


@router.get("/payments.csv", response_class=Response)
def payments_csv(
    principal: Principal = Depends(require("reports:operational")),
    conn: sqlite3.Connection = Depends(get_conn),
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
) -> StreamingResponse:
    resolved = resolve_period(conn, period, from_date, to_date)
    filters = payments_q.PaymentFilters(
        start=resolved.start, end=resolved.end, search=q, status=status_filter, channel=channel, location_id=location_id,
        amount_min_cents=amount_min_cents, amount_max_cents=amount_max_cents, customer_id=customer_id, sort=sort, direction=direction,
    )
    filename = csv_export.export_filename(principal.merchant_slug, "payments", resolved.from_day, resolved.to_day)
    csv_export.record_export(principal, conn, filename, _period_body("payment register", resolved))
    rows = (
        [
            r["id"], r["order_reference"], r["created_at"], csv_export.chicago(r["created_at"]), r["status"], PAYMENT_STATUS_LABELS[r["status"]],
            r["channel"], CHANNEL_LABELS[r["channel"]], r["location_id"], r["location_name"],
            r["customer_id"], r["customer_reference"], r["customer_name"], r["customer_email"],
            r["method_type"], r["card_brand"], r["card_last4"], r["wallet_type"], method_label(r["method_type"], r["card_brand"], r["card_last4"], r["wallet_type"]),
            r["amount_cents"], csv_export.usd(r["amount_cents"]), r["refunded_cents"], csv_export.usd(r["refunded_cents"]), r["net_cents"], csv_export.usd(r["net_cents"]), r["currency"],
            r["succeeded_at"], csv_export.chicago(r["succeeded_at"]), r["dispute_id"], r["dispute_status"], r["description"],
        ]
        for r in payments_q.iter_payments(principal.merchant_id, conn, filters)
    )
    return csv_export.stream_csv(filename, PAYMENTS_HEADER, rows)


@router.get("/attempts.csv", response_class=Response)
def attempts_csv(
    principal: Principal = Depends(require("reports:operational")),
    conn: sqlite3.Connection = Depends(get_conn),
    q: str | None = Query(None, max_length=120),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    outcome: Outcome | None = None,
    channel: Channel | None = None,
    location_id: str | None = Query(None, max_length=40),
    failure_code: FailureCode | None = None,
    sort: AttemptSort = "created_at",
    direction: Direction = Query("desc", alias="dir"),
) -> StreamingResponse:
    resolved = resolve_period(conn, period, from_date, to_date)
    filters = attempts_q.AttemptFilters(
        start=resolved.start, end=resolved.end, search=q, outcome=outcome, channel=channel, location_id=location_id, failure_code=failure_code, sort=sort, direction=direction
    )
    filename = csv_export.export_filename(principal.merchant_slug, "attempts", resolved.from_day, resolved.to_day)
    csv_export.record_export(principal, conn, filename, _period_body("payment attempt", resolved))
    rows = (
        [
            r["id"], r["payment_id"], r["order_reference"], r["attempt_number"], r["created_at"], csv_export.chicago(r["created_at"]),
            r["completed_at"], csv_export.chicago(r["completed_at"]), r["outcome"], ATTEMPT_OUTCOME_LABELS[r["outcome"]], r["failure_code"], r["failure_message"],
            r["method_type"], r["card_brand"], r["card_last4"], r["wallet_type"], method_label(r["method_type"], r["card_brand"], r["card_last4"], r["wallet_type"]),
            r["amount_cents"], csv_export.usd(r["amount_cents"]), r["currency"], r["channel"], CHANNEL_LABELS[r["channel"]], r["location_id"], r["location_name"],
            r["customer_id"], r["customer_reference"], r["customer_name"], r["customer_email"],
        ]
        for r in attempts_q.iter_attempts(principal.merchant_id, conn, filters)
    )
    return csv_export.stream_csv(filename, ATTEMPTS_HEADER, rows)


@router.get("/payouts.csv", response_class=Response)
def payouts_csv(
    principal: Principal = Depends(require("reports:financial")),
    conn: sqlite3.Connection = Depends(get_conn),
    status_filter: PayoutStatus | None = Query(None, alias="status"),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
) -> StreamingResponse:
    start = end = None
    if from_date or to_date:
        if not (from_date and to_date):
            raise ApiError(422, "validation_error", "from and to must be given together")
        if to_date < from_date:
            raise ApiError(422, "validation_error", "period end precedes period start")
        start, end = chicago_range(from_date, to_date)
    filters = payouts_q.PayoutFilters(status=status_filter, start=start, end=end)
    payouts = payouts_q.iter_payouts(principal.merchant_id, conn, filters).fetchall()
    rows: list[list[object]] = []
    for po in payouts:
        buckets = payouts_q.bucket_totals(principal.merchant_id, conn, po["id"])
        total, _ = payouts_q.ledger_total(principal.merchant_id, conn, po["id"])
        if total != po["amount_cents"]:
            raise ApiError(500, "reconciliation_mismatch", f"Payout {po['id']} does not reconcile to its ledger movements.")
        rows.append(
            [
                po["id"], po["status"], PAYOUT_STATUS_LABELS[po["status"]], po["cutoff_at"], csv_export.chicago(po["cutoff_at"]), chicago_date_string(po["cutoff_at"]),
                po["sent_at"], csv_export.chicago(po["sent_at"]), po["expected_arrival_date"], po["paid_at"], csv_export.chicago(po["paid_at"]),
                destination_string(po, principal.merchant_name),
                buckets["collections"], csv_export.usd(buckets["collections"]), buckets["fees"], csv_export.usd(buckets["fees"]),
                buckets["refunds"], csv_export.usd(buckets["refunds"]), buckets["disputes"], csv_export.usd(buckets["disputes"]),
                buckets["adjustments"], csv_export.usd(buckets["adjustments"]), po["amount_cents"], csv_export.usd(po["amount_cents"]), po["currency"],
            ]
        )
    if from_date and to_date:
        from_label, to_label = from_date.isoformat(), to_date.isoformat()
    elif payouts:
        days = sorted(chicago_date_string(po["cutoff_at"]) for po in payouts)
        from_label, to_label = days[0], days[-1]
    else:
        from_label = to_label = "none"
    filename = csv_export.export_filename(principal.merchant_slug, "payouts", from_label, to_label)
    scope = f"{from_label} to {to_label}" if from_label != "none" else "no payouts"
    csv_export.record_export(principal, conn, filename, f"Downloaded the payout reconciliation CSV ({scope}).")
    return csv_export.stream_csv(filename, PAYOUTS_HEADER, rows)


@router.get("/refunds.csv", response_class=Response)
def refunds_csv(
    principal: Principal = Depends(require("reports:financial")),
    conn: sqlite3.Connection = Depends(get_conn),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    status_filter: RefundStatus | None = Query(None, alias="status"),
    reason: RefundReason | None = None,
) -> StreamingResponse:
    resolved = resolve_period(conn, period, from_date, to_date)
    filters = refunds_q.RefundFilters(start=resolved.start, end=resolved.end, status=status_filter, reason=reason)
    filename = csv_export.export_filename(principal.merchant_slug, "refunds", resolved.from_day, resolved.to_day)
    csv_export.record_export(principal, conn, filename, _period_body("refund register", resolved))
    rows = (
        [
            r["id"], r["payment_id"], r["order_reference"], r["created_at"], csv_export.chicago(r["created_at"]), r["completed_at"], csv_export.chicago(r["completed_at"]),
            r["status"], REFUND_STATUS_LABELS[r["status"]], r["reason"], REFUND_REASON_LABELS[r["reason"]], r["amount_cents"], csv_export.usd(r["amount_cents"]), r["currency"],
            r["channel"], CHANNEL_LABELS[r["channel"]], r["customer_id"], r["customer_reference"], r["customer_name"], r["customer_email"],
        ]
        for r in refunds_q.iter_refunds(principal.merchant_id, conn, filters)
    )
    return csv_export.stream_csv(filename, REFUNDS_HEADER, rows)
