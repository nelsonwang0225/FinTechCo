"""SQLite connections: one per request, foreign keys on, rows addressable by name."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(schema_sql())


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def database_exists(path: Path | str) -> bool:
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: a connection to the app's database for the duration of one request."""
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()
