"""Attempts list: one row per attempt with its payment's context. Filters on payment_attempt.created_at."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.queries.common import Page, escape_like, order_clause

SORT_COLUMNS: dict[str, str] = {
    "created_at": "a.created_at",
    "amount": "p.amount_cents",
    "outcome": "a.outcome",
    "order_reference": "p.order_reference",
}

SELECT = """
SELECT a.id, a.payment_id, a.attempt_number, a.method_type, a.card_brand, a.card_last4, a.wallet_type, a.outcome, a.failure_code,
       a.failure_message, a.created_at, a.completed_at,
       p.order_reference, p.amount_cents, p.currency, p.channel, p.customer_id, p.location_id,
       c.full_name AS customer_name, c.email AS customer_email, c.reference AS customer_reference, l.name AS location_name
FROM payment_attempt a
JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id
LEFT JOIN customer c ON c.id = p.customer_id AND c.merchant_id = p.merchant_id
LEFT JOIN location l ON l.id = p.location_id AND l.merchant_id = p.merchant_id
"""


@dataclass(frozen=True)
class AttemptFilters:
    start: str
    end: str
    search: str | None = None
    outcome: str | None = None
    channel: str | None = None
    location_id: str | None = None
    failure_code: str | None = None
    sort: str = "created_at"
    direction: str = "desc"


def _where(merchant_id: str, f: AttemptFilters) -> tuple[str, dict[str, object]]:
    clauses = ["a.merchant_id = :merchant_id", "a.created_at >= :start", "a.created_at < :end"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": f.start, "end": f.end}
    if f.search:
        term = f.search.strip()
        params["exact"] = term
        params["like"] = f"%{escape_like(term)}%"
        clauses.append(
            "(a.id = :exact OR p.id = :exact OR p.order_reference LIKE :like ESCAPE '\\' OR c.full_name LIKE :like ESCAPE '\\' "
            "OR c.email LIKE :like ESCAPE '\\')"
        )
    if f.outcome:
        clauses.append("a.outcome = :outcome")
        params["outcome"] = f.outcome
    if f.channel:
        clauses.append("p.channel = :channel")
        params["channel"] = f.channel
    if f.location_id:
        clauses.append("p.location_id = :location_id")
        params["location_id"] = f.location_id
    if f.failure_code:
        clauses.append("a.failure_code = :failure_code")
        params["failure_code"] = f.failure_code
    return " AND ".join(clauses), params


def list_attempts(merchant_id: str, conn: sqlite3.Connection, f: AttemptFilters, page: Page) -> tuple[list[sqlite3.Row], int]:
    where, params = _where(merchant_id, f)
    total = conn.execute(
        f"SELECT COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        f"LEFT JOIN customer c ON c.id = p.customer_id AND c.merchant_id = p.merchant_id WHERE {where}",
        params,
    ).fetchone()[0]
    order = order_clause(SORT_COLUMNS, f.sort, f.direction, "a.id")
    rows = conn.execute(f"{SELECT} WHERE {where} {order} LIMIT :limit OFFSET :offset", {**params, "limit": page.page_size, "offset": page.offset}).fetchall()
    return rows, total


def iter_attempts(merchant_id: str, conn: sqlite3.Connection, f: AttemptFilters) -> sqlite3.Cursor:
    where, params = _where(merchant_id, f)
    order = order_clause(SORT_COLUMNS, f.sort, f.direction, "a.id")
    return conn.execute(f"{SELECT} WHERE {where} {order}", params)
