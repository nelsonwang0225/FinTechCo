"""Definition of Done 1: the documented commands start the services and a seeded user reaches the portal.

The Makefile is checked for the documented targets and commands; the seed +
app + persona flow runs here in-process against a fresh database path.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.seed import seed_database
from tests.conftest import REPO_ROOT


def test_makefile_documents_the_commands() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    for target in ("setup", "seed", "reset", "run", "test"):
        assert re.search(rf"^{target}:", makefile, re.M), target
    assert "-m venv" in makefile and "npm ci" in makefile
    assert "python -m app.seed" in makefile
    assert "uvicorn app.main:app" in makefile and "--port 8000" in makefile
    assert "npm run dev" in makefile and "5173" in makefile
    assert "trap" in makefile and "wait" in makefile
    assert (REPO_ROOT / ".python-version").read_text().strip() == "3.11"


def test_fresh_seed_then_a_seeded_user_reaches_the_portal(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    assert not db.exists()
    seed_database(db)
    app = create_app(db)
    with TestClient(app) as c:
        assert c.get("/api/ping").json() == {"ok": True, "db": "ok"}
        personas = c.get("/api/dev/personas").json()
        alder = next(g for g in personas["merchants"] if g["merchant"]["slug"] == "alder-loom")
        maya = next(p for p in alder["personas"] if p["full_name"] == "Maya Chen")
        r = c.post("/api/dev/session", json={"user_id": maya["user_id"], "merchant_id": alder["merchant"]["id"]})
        assert r.status_code == 200
        session = c.get("/api/session").json()
        assert session["merchant"]["name"] == "Alder & Loom"
        assert session["role"] == "operations_manager"
        assert "payments:read" in session["permissions"]
        assert c.get("/api/meta").status_code == 200
        overview = c.get("/api/overview").json()
        assert overview["greeting"] == {"salutation": "Good morning", "first_name": "Maya", "merchant_name": "Alder & Loom", "as_of": session["as_of"]}


def test_ping_reports_a_missing_database(tmp_path: Path) -> None:
    app = create_app(tmp_path / "missing.db")
    with TestClient(app) as c:
        assert c.get("/api/ping").json() == {"ok": True, "db": "missing"}
