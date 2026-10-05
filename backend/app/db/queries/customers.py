"""Customers: a merchant-scoped directory with first payment and recent activity derived from payments and refunds."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.queries.common import Page, escape_like, order_clause

SORT_COLUMNS: dict[str, str] = {
    "name": "c.full_name",
    "email": "c.email",
    "reference": "c.reference",
    "first_payment_at": "first_payment_at",
    "last_activity_at": "last_activity_at",
}

# Recent activity is the later of the last payment and the last refund request; both are ISO UTC strings so MAX compares correctly.
SELECT = """
WITH payment_activity AS (
    SELECT p.customer_id, MIN(p.created_at) AS first_payment_at, MAX(p.created_at) AS last_payment_at
    FROM payment p WHERE p.merchant_id = :merchant_id AND p.customer_id IS NOT NULL GROUP BY p.customer_id
),
refund_activity AS (
    SELECT p.customer_id, MAX(r.created_at) AS last_refund_at
    FROM refund r JOIN payment p ON p.id = r.payment_id AND p.merchant_id = r.merchant_id
    WHERE r.merchant_id = :merchant_id AND p.customer_id IS NOT NULL GROUP BY p.customer_id
)
SELECT c.id, c.reference, c.full_name, c.email, c.created_at,
       pa.first_payment_at,
       NULLIF(MAX(COALESCE(pa.last_payment_at, ''), COALESCE(ra.last_refund_at, '')), '') AS last_activity_at
FROM customer c
LEFT JOIN payment_activity pa ON pa.customer_id = c.id
LEFT JOIN refund_activity ra ON ra.customer_id = c.id
"""


@dataclass(frozen=True)
class CustomerFilters:
    search: str | None = None
    sort: str = "last_activity_at"
    direction: str = "desc"


def _where(merchant_id: str, f: CustomerFilters) -> tuple[str, dict[str, object]]:
    clauses = ["c.merchant_id = :merchant_id"]
    params: dict[str, object] = {"merchant_id": merchant_id}
    if f.search:
        term = f.search.strip()
        params["exact"] = term
        params["like"] = f"%{escape_like(term)}%"
        clauses.append("(c.id = :exact OR c.full_name LIKE :like ESCAPE '\\' OR c.email LIKE :like ESCAPE '\\' OR c.reference LIKE :like ESCAPE '\\')")
    return " AND ".join(clauses), params


def list_customers(merchant_id: str, conn: sqlite3.Connection, f: CustomerFilters, page: Page) -> tuple[list[sqlite3.Row], int]:
    where, params = _where(merchant_id, f)
    total = conn.execute(f"SELECT COUNT(*) FROM customer c WHERE {where}", params).fetchone()[0]
    order = order_clause(SORT_COLUMNS, f.sort, f.direction, "c.id")
    rows = conn.execute(f"{SELECT} WHERE {where} {order} LIMIT :limit OFFSET :offset", {**params, "limit": page.page_size, "offset": page.offset}).fetchall()
    return rows, total


def get_customer(merchant_id: str, conn: sqlite3.Connection, customer_id: str) -> sqlite3.Row | None:
    return conn.execute(f"{SELECT} WHERE c.id = :id AND c.merchant_id = :merchant_id", {"id": customer_id, "merchant_id": merchant_id}).fetchone()


def list_payments_for_customer(merchant_id: str, conn: sqlite3.Connection, customer_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ps.* FROM payment_summary ps WHERE ps.customer_id = :customer_id AND ps.merchant_id = :merchant_id ORDER BY ps.created_at DESC, ps.id",
        {"customer_id": customer_id, "merchant_id": merchant_id},
    ).fetchall()


def list_refunds_for_customer(merchant_id: str, conn: sqlite3.Connection, customer_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT r.id, r.payment_id, r.amount_cents, r.currency, r.reason, r.status, r.created_at, r.completed_at, p.order_reference "
        "FROM refund r JOIN payment p ON p.id = r.payment_id AND p.merchant_id = r.merchant_id "
        "WHERE p.customer_id = :customer_id AND r.merchant_id = :merchant_id ORDER BY r.created_at DESC, r.id",
        {"customer_id": customer_id, "merchant_id": merchant_id},
    ).fetchall()
