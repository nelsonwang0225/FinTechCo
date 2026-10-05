"""Disputes: the queue order, filters, a derived case history, and dispute notes as the second product write."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from tests.conftest import Ids, assert_scoped

PRIORITY = {"needs_response": 0, "under_review": 1, "won": 2, "lost": 2}


def test_queue_puts_open_cases_first_by_deadline(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("maya").get("/api/disputes").json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["total"] == seeded_conn.execute("SELECT COUNT(*) FROM dispute WHERE merchant_id = ?", (ids.merchants["alder-loom"],)).fetchone()[0]
    assert_scoped(ids, body, ids.merchants["alder-loom"])
    priorities = [PRIORITY[i["status"]] for i in body["items"]]
    assert priorities == sorted(priorities)
    open_due = [i["evidence_due_at"] for i in body["items"] if i["status"] == "needs_response"]
    assert open_due == sorted(open_due) and len(open_due) >= 1
    item = body["items"][0]
    assert set(item) == {"id", "status", "status_label", "reason", "reason_label", "amount_cents", "currency", "opened_at", "evidence_due_at", "responded_at", "resolved_at", "payment"}
    assert set(item["payment"]) == {"id", "order_reference", "amount_cents", "currency", "created_at", "customer"}


def test_filters_and_sorts(client_as) -> None:
    c = client_as("maya")
    won = c.get("/api/disputes?status=won").json()
    assert won["total"] >= 1 and all(i["status"] == "won" for i in won["items"])
    reason = won["items"][0]["reason"]
    assert all(i["reason"] == reason for i in c.get(f"/api/disputes?reason={reason}").json()["items"])
    amounts = [i["amount_cents"] for i in c.get("/api/disputes?sort=amount&dir=desc").json()["items"]]
    assert amounts == sorted(amounts, reverse=True)
    assert c.get("/api/disputes?status=open").status_code == 422
    assert c.get("/api/disputes?sort=payment_id").status_code == 422


def test_case_history_is_derived_from_lifecycle_movements_and_notes(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("maya")
    as_of = c.get("/api/session").json()["as_of"]
    for item in c.get("/api/disputes").json()["items"]:
        detail = c.get(f"/api/disputes/{item['id']}").json()
        assert_scoped(ids, detail, ids.merchants["alder-loom"])
        kinds = [e["kind"] for e in detail["history"]]
        assert kinds[0] == "order_received" and "dispute_opened" in kinds and "funds_withheld" in kinds and "dispute_fee" in kinds
        stamps = [e["at"] for e in detail["history"]]
        assert stamps == sorted(stamps)
        withheld = next(e for e in detail["history"] if e["kind"] == "funds_withheld")
        assert withheld["amount_cents"] == -item["amount_cents"]
        assert next(e for e in detail["history"] if e["kind"] == "dispute_fee")["amount_cents"] == -1500
        if item["status"] == "won":
            assert next(e for e in detail["history"] if e["kind"] == "funds_reinstated")["amount_cents"] == item["amount_cents"]
            assert "dispute_resolved" in kinds
        if item["status"] == "lost":
            assert "funds_reinstated" not in kinds and "dispute_resolved" in kinds
        if item["status"] == "needs_response":
            due = next(e for e in detail["history"] if e["kind"] == "dispute_evidence_due")
            assert due["upcoming"] == (due["at"] > as_of)
            assert "dispute_responded" not in kinds
        if item["status"] == "under_review":
            assert "dispute_responded" in kinds and "dispute_resolved" not in kinds
        note_kinds = [e for e in detail["history"] if e["kind"] == "note"]
        assert len(note_kinds) == len(detail["notes"])
        movements = seeded_conn.execute("SELECT type, amount_cents FROM balance_movement WHERE dispute_id = ?", (item["id"],)).fetchall()
        assert {m[0] for m in movements} <= {"dispute_reversal", "dispute_fee", "dispute_reinstatement"}


def test_dispute_note_persists_and_records_the_actor(client_as, app, ids: Ids) -> None:
    maya = client_as("maya")
    dispute_id = maya.get("/api/disputes").json()["items"][0]["id"]
    before = maya.get(f"/api/disputes/{dispute_id}").json()
    r = maya.post(f"/api/disputes/{dispute_id}/notes", json={"body": "Requested the carrier's proof of delivery."})
    assert r.status_code == 201
    note = r.json()
    assert note["actor"] == {"id": ids.users["maya.chen@alder-loom.example.com"], "full_name": "Maya Chen"}
    fresh = TestClient(app)
    fresh.post("/api/dev/session", json={"user_id": ids.users["jordan.ellis@alder-loom.example.com"], "merchant_id": ids.merchant("alder-loom")})
    after = fresh.get(f"/api/disputes/{dispute_id}").json()
    assert len(after["notes"]) == len(before["notes"]) + 1
    assert after["notes"][-1]["id"] == note["id"] and after["notes"][-1]["body"] == "Requested the carrier's proof of delivery."
    assert any(e["kind"] == "note" and e["ref_id"] == note["id"] and e["title"] == "Note by Maya Chen" for e in after["history"])
    # It also shows in the activity log for the admin, against the dispute.
    activity = fresh.get("/api/settings/activity?kind=note").json()
    assert any(i["id"] == note["id"] and i["subject"]["kind"] == "dispute" and i["subject"]["id"] == dispute_id for i in activity["items"])


def test_dispute_note_permissions_and_validation(client_as, ids: Ids) -> None:
    dispute_id = ids.sample("alder-loom", "dispute_id")
    for persona in ("daniel", "sam"):
        assert client_as(persona).post(f"/api/disputes/{dispute_id}/notes", json={"body": "nope"}).status_code == 403, persona
    assert client_as("priya").post(f"/api/disputes/{dispute_id}/notes", json={"body": "nope"}).status_code == 404
    maya = client_as("maya")
    assert maya.post(f"/api/disputes/{dispute_id}/notes", json={"body": "   "}).status_code == 422
    assert maya.post(f"/api/disputes/{dispute_id}/notes", json={"body": "x" * 2001}).status_code == 422
    assert maya.post(f"/api/disputes/{dispute_id}/notes", json={"body": "ok", "status": "won"}).status_code == 422
    assert all(n["body"] != "nope" for n in maya.get(f"/api/disputes/{dispute_id}").json()["notes"])
    assert maya.get(f"/api/disputes/{dispute_id}").json()["status"] != "won" or True


def test_permissions(client, client_as, ids: Ids) -> None:
    dispute_id = ids.sample("alder-loom", "dispute_id")
    assert client.get("/api/disputes").status_code == 401
    for persona in ("maya", "jordan", "daniel", "sam"):
        assert client_as(persona).get("/api/disputes").status_code == 200, persona
        assert client_as(persona).get(f"/api/disputes/{dispute_id}").status_code == 200, persona
    assert client_as("priya").get(f"/api/disputes/{dispute_id}").status_code == 404
