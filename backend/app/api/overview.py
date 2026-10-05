"""Overview: a derived financial summary for a period, the daily collected series, recent payments, the upcoming payout
and a short attention list.

Every number is a sum over ledger movements or a listing of base records, computed on each request. Attention items are
a closed set of three kinds read from disputes, payouts and refunds.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.listing import period_info, resolve_period
from app.api.payments import list_item
from app.api.payouts import funds_summary
from app.api.schemas.overview import (
    AttentionItem,
    AttentionLink,
    ChartPoint,
    CollectedChart,
    Greeting,
    OverviewResponse,
    OverviewTiles,
    UpcomingPayout,
)
from app.api.schemas.payouts import PayoutBuckets
from app.auth.permissions import require
from app.auth.session import Principal
from app.core import clock, periods
from app.core.money import format_usd
from app.core.tz import to_chicago, to_iso
from app.db.connection import get_conn
from app.db.queries import overview as overview_q

router = APIRouter(prefix="/api/overview", tags=["overview"])

Preset = Literal["last_7_days", "last_30_days", "month_to_date", "custom"]
RECENT_PAYMENTS = 6
CHART_TITLE = "Collected by day"


def salutation_for(now: datetime) -> str:
    """Time of day from the reporting clock in America/Chicago."""
    hour = to_chicago(now).hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def attention_items(merchant_id: str, conn: sqlite3.Connection) -> list[AttentionItem]:
    items: list[AttentionItem] = []
    for d in overview_q.disputes_awaiting_response(merchant_id, conn):
        items.append(
            AttentionItem(
                kind="dispute_deadline",
                title=f"Dispute on {d['order_reference']} needs a response",
                detail=f"{format_usd(d['amount_cents'], symbol=True)} is held until the case is decided.",
                at=d["evidence_due_at"],
                at_label="Evidence due",
                amount_cents=d["amount_cents"],
                currency=d["currency"],
                link=AttentionLink(kind="dispute", id=d["id"], permission="disputes:read"),
            )
        )
    for p in overview_q.payouts_in_transit(merchant_id, conn):
        items.append(
            AttentionItem(
                kind="payout_in_transit",
                title=f"Payout of {format_usd(p['amount_cents'], symbol=True)} is on its way",
                detail=f"Expected to arrive {_long_date(p['expected_arrival_date'])}.",
                at=p["sent_at"],
                at_label="Sent",
                amount_cents=p["amount_cents"],
                currency=p["currency"],
                link=AttentionLink(kind="payout", id=p["id"], permission="payouts:read"),
            )
        )
    for r in overview_q.refunds_pending(merchant_id, conn):
        items.append(
            AttentionItem(
                kind="refund_pending",
                title=f"Refund of {format_usd(r['amount_cents'], symbol=True)} on {r['order_reference']} is pending",
                detail="It will post to the ledger once the processor completes it.",
                at=r["created_at"],
                at_label="Requested",
                amount_cents=r["amount_cents"],
                currency=r["currency"],
                link=AttentionLink(kind="payment", id=r["payment_id"], permission="payments:read"),
            )
        )
    return items


def _long_date(day_text: str) -> str:
    d = date.fromisoformat(day_text)
    return f"{d.strftime('%A')}, {d.strftime('%b')} {d.day}"


@router.get("", response_model=OverviewResponse)
def get_overview(
    principal: Principal = Depends(require("overview:read")),
    conn: sqlite3.Connection = Depends(get_conn),
    period: Preset | None = None,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
) -> OverviewResponse:
    merchant_id = principal.merchant_id
    now = clock.now(conn)
    now_text = to_iso(now)
    resolved = resolve_period(conn, period, from_date, to_date)

    collected = overview_q.ledger_sum(merchant_id, conn, "charge", resolved.start, resolved.end)
    refunds = -overview_q.ledger_sum(merchant_id, conn, "refund", resolved.start, resolved.end)
    days = periods.day_buckets(resolved)
    by_day = overview_q.bucket_by_chicago_day(overview_q.charges_posted(merchant_id, conn, resolved.start, resolved.end), days)
    points = [ChartPoint(day=d.isoformat(), amount_cents=by_day[d]) for d in days]

    summary = funds_summary(principal, conn)
    buckets = overview_q.available_buckets(merchant_id, conn, now_text)

    return OverviewResponse(
        greeting=Greeting(
            salutation=salutation_for(now),
            first_name=principal.user_name.split()[0],
            merchant_name=principal.merchant_name,
            as_of=now_text,
        ),
        period=period_info(resolved),
        tiles=OverviewTiles(
            collected_cents=collected,
            refunds_cents=refunds,
            funds_available_cents=summary.available_cents,
            pending_cents=summary.pending_cents,
            currency="USD",
            next_payout=summary.next_payout,
        ),
        chart=CollectedChart(title=CHART_TITLE, points=points, total_cents=sum(p.amount_cents for p in points), currency="USD"),
        recent_payments=[list_item(r) for r in overview_q.recent_payments(merchant_id, conn, RECENT_PAYMENTS)],
        upcoming_payout=UpcomingPayout(
            cutoff_at=summary.next_payout.cutoff_at,
            payout_date=summary.next_payout.payout_date,
            amount_cents=summary.available_cents,
            currency="USD",
            schedule=summary.next_payout.schedule,
            schedule_label=summary.next_payout.schedule_label,
            destination=summary.destination,
            note=summary.next_payout.note,
            buckets=PayoutBuckets(
                collections_cents=buckets["collections"],
                fees_cents=buckets["fees"],
                refunds_cents=buckets["refunds"],
                disputes_cents=buckets["disputes"],
                adjustments_cents=buckets["adjustments"],
            ),
        ),
        attention=attention_items(merchant_id, conn),
    )
