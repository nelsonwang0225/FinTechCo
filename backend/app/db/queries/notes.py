"""Note events: the product's only writes (notes) plus export activity records."""

from __future__ import annotations

import sqlite3

from app.db.queries.common import Page


def insert_note(
    merchant_id: str,
    conn: sqlite3.Connection,
    *,
    note_id: str,
    actor_user_id: str,
    body: str,
    created_at: str,
    payment_id: str | None = None,
    dispute_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO note_event (id, merchant_id, kind, actor_user_id, payment_id, dispute_id, payout_id, export_name, body, created_at) "
        "VALUES (:id, :merchant_id, 'note', :actor_user_id, :payment_id, :dispute_id, NULL, NULL, :body, :created_at)",
        {"id": note_id, "merchant_id": merchant_id, "actor_user_id": actor_user_id, "payment_id": payment_id, "dispute_id": dispute_id,
         "body": body, "created_at": created_at},
    )


def insert_export(
    merchant_id: str,
    conn: sqlite3.Connection,
    *,
    event_id: str,
    actor_user_id: str,
    export_name: str,
    body: str,
    created_at: str,
    payout_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO note_event (id, merchant_id, kind, actor_user_id, payment_id, dispute_id, payout_id, export_name, body, created_at) "
        "VALUES (:id, :merchant_id, 'export', :actor_user_id, NULL, NULL, :payout_id, :export_name, :body, :created_at)",
        {"id": event_id, "merchant_id": merchant_id, "actor_user_id": actor_user_id, "payout_id": payout_id, "export_name": export_name, "body": body,
         "created_at": created_at},
    )


ACTIVITY_SELECT = """
SELECT n.id, n.kind, n.body, n.created_at, n.export_name, n.payment_id, n.dispute_id, n.payout_id,
       u.id AS actor_id, u.full_name AS actor_name,
       p.order_reference AS payment_reference, dp.order_reference AS dispute_reference
FROM note_event n
JOIN app_user u ON u.id = n.actor_user_id
LEFT JOIN payment p ON p.id = n.payment_id AND p.merchant_id = n.merchant_id
LEFT JOIN dispute d ON d.id = n.dispute_id AND d.merchant_id = n.merchant_id
LEFT JOIN payment dp ON dp.id = d.payment_id AND dp.merchant_id = d.merchant_id
"""


def list_activity(merchant_id: str, conn: sqlite3.Connection, kind: str | None, page: Page) -> tuple[list[sqlite3.Row], int]:
    """Who did what, when: notes and exports for the merchant, newest first."""
    clauses = ["n.merchant_id = :merchant_id"]
    params: dict[str, object] = {"merchant_id": merchant_id}
    if kind:
        clauses.append("n.kind = :kind")
        params["kind"] = kind
    where = " AND ".join(clauses)
    total = conn.execute(f"SELECT COUNT(*) FROM note_event n WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"{ACTIVITY_SELECT} WHERE {where} ORDER BY n.created_at DESC, n.id DESC LIMIT :limit OFFSET :offset",
        {**params, "limit": page.page_size, "offset": page.offset},
    ).fetchall()
    return rows, total


def get_note(merchant_id: str, conn: sqlite3.Connection, note_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT n.id, n.body, n.created_at, n.payment_id, n.dispute_id, u.id AS actor_id, u.full_name AS actor_name "
        "FROM note_event n JOIN app_user u ON u.id = n.actor_user_id WHERE n.id = :id AND n.merchant_id = :merchant_id",
        {"id": note_id, "merchant_id": merchant_id},
    ).fetchone()
