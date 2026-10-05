"""Logical checksum of a database: SHA-256 over every table's rows ordered by primary key.

The seed_meta checksum row itself is excluded so the value is well defined.
SQLite file bytes are not stable (page allocation, WAL), so this is what
"identical baseline" means.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from app.db.connection import table_names


def _primary_key(conn: sqlite3.Connection, table: str) -> list[str]:
    cols = [dict(r) for r in conn.execute(f"PRAGMA table_info({table})")]
    pk = sorted((c for c in cols if c["pk"] > 0), key=lambda c: c["pk"])
    return [c["name"] for c in pk] or [c["name"] for c in cols]


def compute(conn: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for table in table_names(conn):
        order = ", ".join(_primary_key(conn, table))
        where = " WHERE key != 'checksum'" if table == "seed_meta" else ""
        digest.update(f"\n#{table}\n".encode())
        for row in conn.execute(f"SELECT * FROM {table}{where} ORDER BY {order}"):
            digest.update(json.dumps(list(row), separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in table_names(conn)}
