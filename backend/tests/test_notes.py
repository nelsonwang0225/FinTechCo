"""A note persists after refresh and records the acting user."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import Ids


def anchor_id(client: TestClient) -> str:
    return client.get("/api/payments?period=last_30_days&q=AL-11404").json()["items"][0]["id"]


def test_note_persists_and_records_the_actor(client_as, app, ids: Ids) -> None:
    maya = client_as("maya")
    payment_id = anchor_id(maya)
    before = maya.get(f"/api/payments/{payment_id}").json()
    r = maya.post(f"/api/payments/{payment_id}/notes", json={"body": "Shopper confirmed the duvet arrived."})
    assert r.status_code == 201
    note = r.json()
    assert note["body"] == "Shopper confirmed the duvet arrived."
    assert note["actor"] == {"id": ids.users["maya.chen@alder-loom.example.com"], "full_name": "Maya Chen"}
    assert note["id"].startswith("evt_")
    assert note["created_at"].endswith("Z")

    # A fresh client (new cookie jar, same database) sees it, in order, in the notes and the timeline.
    fresh = TestClient(app)
    fresh.post("/api/dev/session", json={"user_id": ids.users["jordan.ellis@alder-loom.example.com"], "merchant_id": ids.merchant("alder-loom")})
    after = fresh.get(f"/api/payments/{payment_id}").json()
    assert len(after["notes"]) == len(before["notes"]) + 1
    assert after["notes"][-1]["id"] == note["id"]
    assert after["notes"][-1]["actor"]["full_name"] == "Maya Chen"
    assert after["timeline"][-1]["kind"] == "note" and after["timeline"][-1]["title"] == "Note by Maya Chen"


def test_actor_comes_from_the_session_not_the_body(client_as, ids: Ids) -> None:
    jordan = client_as("jordan")
    payment_id = anchor_id(jordan)
    r = jordan.post(f"/api/payments/{payment_id}/notes", json={"body": "Reviewed.", "actor_user_id": ids.users["maya.chen@alder-loom.example.com"]})
    assert r.status_code == 422  # undeclared fields are refused
    r = jordan.post(f"/api/payments/{payment_id}/notes", json={"body": "Reviewed."})
    assert r.status_code == 201 and r.json()["actor"]["full_name"] == "Jordan Ellis"


def test_roles_without_notes_write_are_403(client_as) -> None:
    for persona in ("daniel", "sam"):
        c = client_as(persona)
        payment_id = anchor_id(c)
        r = c.post(f"/api/payments/{payment_id}/notes", json={"body": "nope"})
        assert r.status_code == 403, persona
        assert all(n["body"] != "nope" for n in c.get(f"/api/payments/{payment_id}").json()["notes"])


def test_cross_merchant_note_is_404(client_as, ids: Ids) -> None:
    priya = client_as("priya")
    alder_payment = ids.sample("alder-loom", "payment_id")
    assert priya.post(f"/api/payments/{alder_payment}/notes", json={"body": "nope"}).status_code == 404


def test_validation(client_as) -> None:
    maya = client_as("maya")
    payment_id = anchor_id(maya)
    assert maya.post(f"/api/payments/{payment_id}/notes", json={"body": ""}).status_code == 422
    assert maya.post(f"/api/payments/{payment_id}/notes", json={"body": "   "}).status_code == 422
    assert maya.post(f"/api/payments/{payment_id}/notes", json={"body": "x" * 2001}).status_code == 422
    assert maya.post(f"/api/payments/{payment_id}/notes", json={}).status_code == 422
    ok = maya.post(f"/api/payments/{payment_id}/notes", json={"body": "x" * 2000})
    assert ok.status_code == 201
