"""Membership lookups that run before a merchant is known.

These are the only queries without a ``merchant_id`` first parameter: they
exist to establish which merchant a session is for. Everything after that
goes through the merchant-scoped modules.
"""

from __future__ import annotations

import sqlite3

PRINCIPAL_SELECT = """
SELECT m.id AS membership_id, m.role, u.id AS user_id, u.full_name AS user_name, u.email AS user_email, u.title AS user_title,
       u.is_active, mer.id AS merchant_id, mer.name AS merchant_name, mer.slug AS merchant_slug
FROM membership m
JOIN app_user u ON u.id = m.user_id
JOIN merchant mer ON mer.id = m.merchant_id
"""


def principal_row(conn: sqlite3.Connection, membership_id: str) -> sqlite3.Row | None:
    return conn.execute(PRINCIPAL_SELECT + " WHERE m.id = :id", {"id": membership_id}).fetchone()


def membership_for(conn: sqlite3.Connection, user_id: str, merchant_id: str) -> sqlite3.Row | None:
    """The active membership for exactly this user and merchant, or None."""
    return conn.execute(
        PRINCIPAL_SELECT + " WHERE m.user_id = :user_id AND m.merchant_id = :merchant_id AND u.is_active = 1",
        {"user_id": user_id, "merchant_id": merchant_id},
    ).fetchone()


def list_personas(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every active membership, for the development persona chooser."""
    return conn.execute(PRINCIPAL_SELECT + " WHERE u.is_active = 1 ORDER BY mer.name, u.full_name").fetchall()
