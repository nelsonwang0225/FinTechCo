"""Merchant-scoped reference data for filter options. Never counts anything."""

from __future__ import annotations

import sqlite3


def list_locations(merchant_id: str, conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, name, address_line, city, state FROM location WHERE merchant_id = :merchant_id ORDER BY name",
        {"merchant_id": merchant_id},
    ).fetchall()
