"""Shared fixtures.

The seeded database is built once per test session into a temporary directory
(`template_db`); tests that only read open it directly, tests that write copy
it first (`db_copy`). Phase 3 adds the persona clients on top of these.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.connection import connect, init_schema
from app.seed import SeedResult, seed_database

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


@pytest.fixture(scope="session")
def template_seed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, SeedResult]:
    """The seeded database, built once per session."""
    path = tmp_path_factory.mktemp("seed") / "fintechco.db"
    return path, seed_database(path)


@pytest.fixture(scope="session")
def template_db(template_seed: tuple[Path, SeedResult]) -> Path:
    return template_seed[0]


@pytest.fixture
def seeded_conn(template_db: Path) -> Iterator[sqlite3.Connection]:
    """Read-only use of the shared template; never write through this connection."""
    conn = connect(template_db)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def db_copy(template_db: Path, tmp_path: Path) -> Path:
    """A private copy of the seeded database for tests that write."""
    target = tmp_path / "fintechco.db"
    shutil.copyfile(template_db, target)
    return target
