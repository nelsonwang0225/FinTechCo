"""Settings: the business profile and the team roster. Read-only."""

from __future__ import annotations

import sqlite3


def merchant_profile(merchant_id: str, conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, name, slug, legal_name, support_email, industry, payout_schedule, destination_label, destination_last4, destination_kind, created_at "
        "FROM merchant WHERE id = :merchant_id",
        {"merchant_id": merchant_id},
    ).fetchone()
    assert row is not None
    return row


def list_team(merchant_id: str, conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT mem.id AS membership_id, mem.role, mem.created_at, u.id AS user_id, u.full_name, u.email, u.title, u.is_active "
        "FROM membership mem JOIN app_user u ON u.id = mem.user_id WHERE mem.merchant_id = :merchant_id ORDER BY u.full_name, mem.id",
        {"merchant_id": merchant_id},
    ).fetchall()
