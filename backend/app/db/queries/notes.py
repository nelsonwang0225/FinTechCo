"""Note events: the product's only writes (notes) plus export activity records."""

from __future__ import annotations

import sqlite3


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


def insert_export(merchant_id: str, conn: sqlite3.Connection, *, event_id: str, actor_user_id: str, export_name: str, body: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO note_event (id, merchant_id, kind, actor_user_id, payment_id, dispute_id, payout_id, export_name, body, created_at) "
        "VALUES (:id, :merchant_id, 'export', :actor_user_id, NULL, NULL, NULL, :export_name, :body, :created_at)",
        {"id": event_id, "merchant_id": merchant_id, "actor_user_id": actor_user_id, "export_name": export_name, "body": body, "created_at": created_at},
    )


def get_note(merchant_id: str, conn: sqlite3.Connection, note_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT n.id, n.body, n.created_at, n.payment_id, n.dispute_id, u.id AS actor_id, u.full_name AS actor_name "
        "FROM note_event n JOIN app_user u ON u.id = n.actor_user_id WHERE n.id = :id AND n.merchant_id = :merchant_id",
        {"id": note_id, "merchant_id": merchant_id},
    ).fetchone()
