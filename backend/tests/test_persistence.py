"""Data survives a restart. A note written through one app instance is read by a new one on the same file."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import Ids


def sign_in(client: TestClient, ids: Ids, email: str, slug: str) -> None:
    r = client.post("/api/dev/session", json={"user_id": ids.users[email], "merchant_id": ids.merchant(slug)})
    assert r.status_code == 200


def test_note_survives_a_new_app_instance_on_the_same_database(db_copy: Path, ids: Ids) -> None:
    first = TestClient(create_app(db_copy))
    sign_in(first, ids, "maya.chen@alder-loom.example.com", "alder-loom")
    payment_id = first.get("/api/payments?period=last_30_days&q=AL-11404").json()["items"][0]["id"]
    created = first.post(f"/api/payments/{payment_id}/notes", json={"body": "Written before the restart."}).json()
    first.close()

    second = TestClient(create_app(db_copy))
    sign_in(second, ids, "maya.chen@alder-loom.example.com", "alder-loom")
    detail = second.get(f"/api/payments/{payment_id}").json()
    assert any(n["id"] == created["id"] and n["body"] == "Written before the restart." for n in detail["notes"])
    second.close()


def test_seeded_data_is_the_same_through_a_new_instance(db_copy: Path, ids: Ids) -> None:
    a = TestClient(create_app(db_copy))
    sign_in(a, ids, "priya.shah@junipertrail.example.com", "juniper-trail")
    page_a = a.get("/api/payments?period=last_30_days&page_size=20").json()
    a.close()
    b = TestClient(create_app(db_copy))
    sign_in(b, ids, "priya.shah@junipertrail.example.com", "juniper-trail")
    page_b = b.get("/api/payments?period=last_30_days&page_size=20").json()
    b.close()
    assert page_a == page_b
