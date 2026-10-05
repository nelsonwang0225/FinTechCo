"""Shared fixtures. Phase 3 adds the seeded template database and persona clients."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.connection import connect, init_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"


@pytest.fixture
def empty_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A fresh database with the schema and nothing else."""
    conn = connect(tmp_path / "empty.db")
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()
