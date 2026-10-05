"""Write a Dataset into an empty database in one transaction, in fixed table order."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields

from app.seed.generate import Dataset

TABLE_ORDER: tuple[tuple[str, str], ...] = (
    ("merchants", "merchant"),
    ("locations", "location"),
    ("users", "app_user"),
    ("memberships", "membership"),
    ("customers", "customer"),
    ("payments", "payment"),
    ("attempts", "payment_attempt"),
    ("refunds", "refund"),
    ("disputes", "dispute"),
    ("payouts", "payout"),
    ("movements", "balance_movement"),
    ("note_events", "note_event"),
)


def _insert(conn: sqlite3.Connection, table: str, rows: list) -> None:
    if not rows:
        return
    names = [f.name for f in fields(rows[0])]
    sql = f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})"
    conn.executemany(sql, [tuple(asdict(r)[n] for n in names) for r in rows])


def write_dataset(conn: sqlite3.Connection, data: Dataset) -> None:
    conn.execute("BEGIN")
    try:
        for attr, table in TABLE_ORDER:
            _insert(conn, table, getattr(data, attr))
        conn.executemany("INSERT INTO seed_meta (key, value) VALUES (?, ?)", sorted(data.meta.items()))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
