"""Disputes: the queue, one dispute with its payment, its ledger movements and its notes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.queries.common import Page, order_clause

SORT_COLUMNS: dict[str, str] = {
    "due": "d.evidence_due_at",
    "opened_at": "d.opened_at",
    "amount": "d.amount_cents",
    "status": "d.status",
}

# The queue order: open cases needing a response first by deadline, then cases under review, then decided cases newest first.
QUEUE_ORDER = (
    "ORDER BY CASE d.status WHEN 'needs_response' THEN 0 WHEN 'under_review' THEN 1 ELSE 2 END, "
    "CASE WHEN d.status IN ('won', 'lost') THEN d.resolved_at END DESC, d.evidence_due_at ASC, d.id"
)

SELECT = """
SELECT d.id, d.payment_id, d.amount_cents, d.currency, d.reason, d.status, d.opened_at, d.evidence_due_at, d.responded_at, d.resolved_at,
       p.order_reference, p.amount_cents AS payment_amount_cents, p.created_at AS payment_created_at, p.customer_id,
       c.full_name AS customer_name, c.email AS customer_email, c.reference AS customer_reference
FROM dispute d
JOIN payment p ON p.id = d.payment_id AND p.merchant_id = d.merchant_id
LEFT JOIN customer c ON c.id = p.customer_id AND c.merchant_id = p.merchant_id
"""


@dataclass(frozen=True)
class DisputeFilters:
    status: str | None = None
    reason: str | None = None
    sort: str = "queue"
    direction: str = "asc"


def _where(merchant_id: str, f: DisputeFilters) -> tuple[str, dict[str, object]]:
    clauses = ["d.merchant_id = :merchant_id"]
    params: dict[str, object] = {"merchant_id": merchant_id}
    if f.status:
        clauses.append("d.status = :status")
        params["status"] = f.status
    if f.reason:
        clauses.append("d.reason = :reason")
        params["reason"] = f.reason
    return " AND ".join(clauses), params


def _order(f: DisputeFilters) -> str:
    if f.sort == "queue":
        return QUEUE_ORDER
    return order_clause(SORT_COLUMNS, f.sort, f.direction, "d.id")


def list_disputes(merchant_id: str, conn: sqlite3.Connection, f: DisputeFilters, page: Page) -> tuple[list[sqlite3.Row], int]:
    where, params = _where(merchant_id, f)
    total = conn.execute(f"SELECT COUNT(*) FROM dispute d WHERE {where}", params).fetchone()[0]
    rows = conn.execute(f"{SELECT} WHERE {where} {_order(f)} LIMIT :limit OFFSET :offset", {**params, "limit": page.page_size, "offset": page.offset}).fetchall()
    return rows, total


def get_dispute(merchant_id: str, conn: sqlite3.Connection, dispute_id: str) -> sqlite3.Row | None:
    return conn.execute(f"{SELECT} WHERE d.id = :id AND d.merchant_id = :merchant_id", {"id": dispute_id, "merchant_id": merchant_id}).fetchone()


def dispute_exists(merchant_id: str, conn: sqlite3.Connection, dispute_id: str) -> bool:
    return conn.execute("SELECT 1 FROM dispute WHERE id = :id AND merchant_id = :merchant_id", {"id": dispute_id, "merchant_id": merchant_id}).fetchone() is not None


def list_movements_for_dispute(merchant_id: str, conn: sqlite3.Connection, dispute_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT bm.id, bm.type, bm.amount_cents, bm.currency, bm.posted_at, bm.available_at, bm.payout_id "
        "FROM balance_movement bm WHERE bm.dispute_id = :dispute_id AND bm.merchant_id = :merchant_id ORDER BY bm.posted_at, bm.id",
        {"dispute_id": dispute_id, "merchant_id": merchant_id},
    ).fetchall()


def list_notes_for_dispute(merchant_id: str, conn: sqlite3.Connection, dispute_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT n.id, n.body, n.created_at, u.id AS actor_id, u.full_name AS actor_name "
        "FROM note_event n JOIN app_user u ON u.id = n.actor_user_id "
        "WHERE n.dispute_id = :dispute_id AND n.merchant_id = :merchant_id AND n.kind = 'note' ORDER BY n.created_at, n.id",
        {"dispute_id": dispute_id, "merchant_id": merchant_id},
    ).fetchall()
