"""GET /api/attempts: one row per attempt with recorded outcome and reason, filtered on the attempt's own timestamp."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import page_params, period_info, resolve_period
from app.api.payments import customer_ref, location_ref, method_info
from app.api.schemas.payments import AttemptListItem, AttemptListResponse
from app.auth.permissions import require
from app.auth.session import Principal
from app.core.labels import ATTEMPT_OUTCOME_LABELS, CHANNEL_LABELS
from app.db.connection import get_conn
from app.db.queries import attempts as attempts_q
from app.db.queries.common import Page

router = APIRouter(prefix="/api/attempts", tags=["attempts"])

Channel = Literal["website", "mobile_app", "in_store"]
Outcome = Literal["succeeded", "failed", "pending"]
# The recorded failure signals, exactly the keys of FAILURE_CODE_LABELS; an unknown code is a 422.
FailureCode = Literal[
    "insufficient_funds",
    "do_not_honor",
    "incorrect_cvc",
    "expired_card",
    "authentication_failed",
    "card_velocity_exceeded",
    "fraud_suspected",
    "issuer_unavailable",
    "processing_error",
    "lost_or_stolen",
    "incorrect_number",
]
AttemptSort = Literal["created_at", "amount", "outcome", "order_reference"]
Direction = Literal["asc", "desc"]
Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]


def attempt_list_item(row: sqlite3.Row) -> AttemptListItem:
    method = method_info(row)
    assert method is not None
    return AttemptListItem(
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
        order_reference=row["order_reference"],
        amount_cents=row["amount_cents"],
        currency=row["currency"],
        channel=row["channel"],
        channel_label=CHANNEL_LABELS[row["channel"]],
        location=location_ref(row),
        customer=customer_ref(row),
    )


@router.get("", response_model=AttemptListResponse)
def list_attempts(
    principal: Principal = Depends(require("payments:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    page: Page = Depends(page_params),
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
) -> AttemptListResponse:
    resolved = resolve_period(conn, period, from_date, to_date)
    filters = attempts_q.AttemptFilters(
        start=resolved.start,
        end=resolved.end,
        search=q,
        outcome=outcome,
        channel=channel,
        location_id=location_id,
        failure_code=failure_code,
        sort=sort,
        direction=direction,
    )
    rows, total = attempts_q.list_attempts(principal.merchant_id, conn, filters, page)
    return AttemptListResponse(items=[attempt_list_item(r) for r in rows], page=page.page, page_size=page.page_size, total=total, period=period_info(resolved))
