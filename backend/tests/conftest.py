"""Shared fixtures.

The seeded database is built once per test session into a temporary directory
(`template_db`); tests that only read open it directly, tests that write copy
it first (`db_copy`). `client_as("maya")` gives a signed-in TestClient over a
private copy; `ids` knows which merchant owns every seeded id.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.db.connection import connect, init_schema
from app.main import create_app
from app.seed import SeedResult, seed_database

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

ID_PATTERN = re.compile(r"^(mer|loc|usr|mem|cus|pay|att|ref|po|bm|dp|evt)_[a-z2-7]{14}$")

# Persona name -> (user email, merchant slug). Sam Okafor holds two memberships.
PERSONAS: dict[str, tuple[str, str]] = {
    "maya": ("maya.chen@alder-loom.example.com", "alder-loom"),
    "daniel": ("daniel.brooks@alder-loom.example.com", "alder-loom"),
    "jordan": ("jordan.ellis@alder-loom.example.com", "alder-loom"),
    "priya": ("priya.shah@junipertrail.example.com", "juniper-trail"),
    "sam": ("sam.okafor@example.com", "alder-loom"),
    "sam_copper": ("sam.okafor@example.com", "copper-finch"),
}

PERSONA_ROLES: dict[str, str] = {
    "maya": "operations_manager",
    "daniel": "finance_manager",
    "jordan": "business_admin",
    "priya": "operations_manager",
    "sam": "read_only_analyst",
    "sam_copper": "read_only_analyst",
}


@dataclass
class Ids:
    merchants: dict[str, str]  # slug -> id
    users: dict[str, str]  # email -> id
    memberships: dict[tuple[str, str], str]  # (email, slug) -> id
    owner_of: dict[str, str] = field(default_factory=dict)  # any merchant-owned id -> merchant id
    samples: dict[str, dict[str, str]] = field(default_factory=dict)  # slug -> {path param -> id}

    def merchant(self, slug: str) -> str:
        return self.merchants[slug]

    def sample(self, slug: str, param: str) -> str:
        return self.samples[slug][param]


def build_ids(conn: sqlite3.Connection) -> Ids:
    merchants = {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM merchant")}
    users = {r["email"]: r["id"] for r in conn.execute("SELECT id, email FROM app_user")}
    memberships = {
        (r["email"], r["slug"]): r["id"]
        for r in conn.execute("SELECT m.id, u.email, mer.slug FROM membership m JOIN app_user u ON u.id = m.user_id JOIN merchant mer ON mer.id = m.merchant_id")
    }
    ids = Ids(merchants, users, memberships)
    for table in ("location", "membership", "customer", "payment", "payment_attempt", "refund", "dispute", "payout", "balance_movement", "note_event"):
        for row in conn.execute(f"SELECT id, merchant_id FROM {table}"):
            ids.owner_of[row["id"]] = row["merchant_id"]
    for slug, merchant_id in merchants.items():
        ids.owner_of[merchant_id] = merchant_id

        def first(sql: str) -> str:
            row = conn.execute(sql, {"m": merchant_id}).fetchone()
            return row[0] if row else ""

        ids.samples[slug] = {
            "payment_id": first("SELECT p.id FROM payment p JOIN payment_attempt a ON a.payment_id = p.id WHERE p.merchant_id = :m "
                                "GROUP BY p.id HAVING COUNT(*) > 1 ORDER BY p.created_at LIMIT 1"),
            "attempt_id": first("SELECT id FROM payment_attempt WHERE merchant_id = :m ORDER BY created_at LIMIT 1"),
            "payout_id": first("SELECT id FROM payout WHERE merchant_id = :m ORDER BY cutoff_at DESC LIMIT 1"),
            "customer_id": first("SELECT id FROM customer WHERE merchant_id = :m ORDER BY created_at LIMIT 1"),
            "dispute_id": first("SELECT id FROM dispute WHERE merchant_id = :m ORDER BY opened_at LIMIT 1"),
            "refund_id": first("SELECT id FROM refund WHERE merchant_id = :m ORDER BY created_at LIMIT 1"),
            "location_id": first("SELECT id FROM location WHERE merchant_id = :m ORDER BY name LIMIT 1"),
        }
    return ids


def collect_ids(payload: Any) -> set[str]:
    """Every prefixed id anywhere in a JSON payload."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            found |= collect_ids(value)
    elif isinstance(payload, list):
        for value in payload:
            found |= collect_ids(value)
    elif isinstance(payload, str) and ID_PATTERN.match(payload):
        found.add(payload)
    return found


def assert_scoped(ids: Ids, payload: Any, merchant_id: str) -> set[str]:
    """Assert every merchant-owned id in the payload belongs to merchant_id; return the ids seen."""
    seen = collect_ids(payload)
    for value in seen:
        if value.startswith("usr_"):
            continue
        owner = ids.owner_of.get(value)
        assert owner is not None, f"unknown id in response: {value}"
        assert owner == merchant_id, f"{value} belongs to {owner}, not {merchant_id}"
    return seen


def api_routes(app: FastAPI) -> list[APIRoute]:
    """Every APIRoute, including those inside included routers."""
    out: list[APIRoute] = []
    for item in app.routes:
        inner = getattr(item, "original_router", None)
        for route in inner.routes if inner is not None else [item]:
            if isinstance(route, APIRoute):
                out.append(route)
    return out


def route_permission(route: APIRoute) -> str | None:
    for dep in route.dependant.dependencies:
        permission = getattr(dep.call, "permission", None)
        if permission:
            return permission
    return None


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


@pytest.fixture(scope="session")
def ids(template_db: Path) -> Ids:
    conn = connect(template_db)
    try:
        return build_ids(conn)
    finally:
        conn.close()


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


@pytest.fixture
def app(db_copy: Path) -> FastAPI:
    return create_app(db_copy)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """An anonymous client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_as(app: FastAPI, ids: Ids) -> Iterator[Callable[[str], TestClient]]:
    """client_as("maya") -> a TestClient signed in as that persona (see PERSONAS)."""
    clients: list[TestClient] = []

    def factory(persona: str) -> TestClient:
        c = TestClient(app)
        clients.append(c)
        if persona != "anon":
            email, slug = PERSONAS[persona]
            r = c.post("/api/dev/session", json={"user_id": ids.users[email], "merchant_id": ids.merchants[slug]})
            assert r.status_code == 200, r.text
        return c

    yield factory
    for c in clients:
        c.close()
