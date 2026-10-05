"""Payments: list over the payment_summary view, detail, and the rows a detail page is built from.

Every function takes merchant_id first and every statement filters on it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.queries.common import Page, escape_like, order_clause

SORT_COLUMNS: dict[str, str] = {
    "created_at": "ps.created_at",
    "amount": "ps.amount_cents",
    "status": "ps.status",
    "order_reference": "ps.order_reference",
    "customer": "ps.customer_name",
}


@dataclass(frozen=True)
class PaymentFilters:
    start: str  # inclusive UTC ISO
    end: str  # exclusive UTC ISO
    search: str | None = None
    status: str | None = None
    channel: str | None = None
    location_id: str | None = None
    amount_min_cents: int | None = None
    amount_max_cents: int | None = None
    customer_id: str | None = None
    sort: str = "created_at"
    direction: str = "desc"


def _where(merchant_id: str, f: PaymentFilters) -> tuple[str, dict[str, object]]:
    clauses = ["ps.merchant_id = :merchant_id", "ps.created_at >= :start", "ps.created_at < :end"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": f.start, "end": f.end}
    if f.search:
        term = f.search.strip()
        params["exact"] = term
        params["like"] = f"%{escape_like(term)}%"
        clauses.append(
            "(ps.id = :exact OR ps.order_reference LIKE :like ESCAPE '\\' OR ps.customer_name LIKE :like ESCAPE '\\' "
            "OR ps.customer_email LIKE :like ESCAPE '\\')"
        )
    if f.status:
        clauses.append("ps.status = :status")
        params["status"] = f.status
    if f.channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = f.channel
    if f.location_id:
        clauses.append("ps.location_id = :location_id")
        params["location_id"] = f.location_id
    if f.amount_min_cents is not None:
        clauses.append("ps.amount_cents >= :amount_min")
        params["amount_min"] = f.amount_min_cents
    if f.amount_max_cents is not None:
        clauses.append("ps.amount_cents <= :amount_max")
        params["amount_max"] = f.amount_max_cents
    if f.customer_id:
        clauses.append("ps.customer_id = :customer_id")
        params["customer_id"] = f.customer_id
    return " AND ".join(clauses), params


def list_payments(merchant_id: str, conn: sqlite3.Connection, f: PaymentFilters, page: Page) -> tuple[list[sqlite3.Row], int]:
    where, params = _where(merchant_id, f)
    total = conn.execute(f"SELECT COUNT(*) FROM payment_summary ps WHERE {where}", params).fetchone()[0]
    order = order_clause(SORT_COLUMNS, f.sort, f.direction, "ps.id")
    rows = conn.execute(
        f"SELECT ps.* FROM payment_summary ps WHERE {where} {order} LIMIT :limit OFFSET :offset",
        {**params, "limit": page.page_size, "offset": page.offset},
    ).fetchall()
    return rows, total


def iter_payments(merchant_id: str, conn: sqlite3.Connection, f: PaymentFilters) -> sqlite3.Cursor:
    """The same query as the list, without pagination, for exports."""
    where, params = _where(merchant_id, f)
    order = order_clause(SORT_COLUMNS, f.sort, f.direction, "ps.id")
    return conn.execute(f"SELECT ps.* FROM payment_summary ps WHERE {where} {order}", params)


def get_payment(merchant_id: str, conn: sqlite3.Connection, payment_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT ps.* FROM payment_summary ps WHERE ps.id = :id AND ps.merchant_id = :merchant_id",
        {"id": payment_id, "merchant_id": merchant_id},
    ).fetchone()


def payment_exists(merchant_id: str, conn: sqlite3.Connection, payment_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM payment WHERE id = :id AND merchant_id = :merchant_id", {"id": payment_id, "merchant_id": merchant_id}).fetchone()
    return row is not None


def list_attempts_for_payment(merchant_id: str, conn: sqlite3.Connection, payment_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.* FROM payment_attempt a WHERE a.payment_id = :payment_id AND a.merchant_id = :merchant_id ORDER BY a.attempt_number",
        {"payment_id": payment_id, "merchant_id": merchant_id},
    ).fetchall()


def list_refunds_for_payment(merchant_id: str, conn: sqlite3.Connection, payment_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT r.* FROM refund r WHERE r.payment_id = :payment_id AND r.merchant_id = :merchant_id ORDER BY r.created_at, r.id",
        {"payment_id": payment_id, "merchant_id": merchant_id},
    ).fetchall()


def get_dispute_for_payment(merchant_id: str, conn: sqlite3.Connection, payment_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT d.* FROM dispute d WHERE d.payment_id = :payment_id AND d.merchant_id = :merchant_id",
        {"payment_id": payment_id, "merchant_id": merchant_id},
    ).fetchone()


def get_charge_movement(merchant_id: str, conn: sqlite3.Connection, payment_id: str) -> sqlite3.Row | None:
    """The charge movement of the succeeded attempt, with its payout if swept."""
    return conn.execute(
        "SELECT bm.id, bm.posted_at, bm.available_at, bm.payout_id, po.status AS payout_status, po.cutoff_at, po.sent_at, po.paid_at "
        "FROM balance_movement bm LEFT JOIN payout po ON po.id = bm.payout_id AND po.merchant_id = bm.merchant_id "
        "WHERE bm.payment_id = :payment_id AND bm.merchant_id = :merchant_id AND bm.type = 'charge'",
        {"payment_id": payment_id, "merchant_id": merchant_id},
    ).fetchone()


def list_notes_for_payment(merchant_id: str, conn: sqlite3.Connection, payment_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT n.id, n.body, n.created_at, u.id AS actor_id, u.full_name AS actor_name "
        "FROM note_event n JOIN app_user u ON u.id = n.actor_user_id "
        "WHERE n.payment_id = :payment_id AND n.merchant_id = :merchant_id AND n.kind = 'note' ORDER BY n.created_at, n.id",
        {"payment_id": payment_id, "merchant_id": merchant_id},
    ).fetchall()
