"""Settings: the business profile, the team roster and the activity log, read-only and admin-only."""

from __future__ import annotations

import sqlite3

from tests.conftest import Ids, assert_scoped


def test_profile_reflects_the_merchant_row(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("jordan").get("/api/settings/profile").json()
    m = seeded_conn.execute("SELECT * FROM merchant WHERE id = ?", (ids.merchants["alder-loom"],)).fetchone()
    assert body["name"] == m["name"] == "Alder & Loom"
    assert body["legal_name"] == m["legal_name"] and body["support_email"] == m["support_email"] and body["industry"] == m["industry"]
    assert body["support_email"].endswith("example.com")
    assert body["timezone"] == "America/Chicago"
    assert body["payout_schedule"] == "daily" and body["payout_schedule_label"] == "Every business day"
    assert body["destination"] == "Alder & Loom, Operating account •••• 4821, external bank account, demo record"
    assert body["destination_last4"] == "4821" and len(body["destination_last4"]) == 4
    assert [loc["name"] for loc in body["locations"]] == ["Fulton Market", "Lincoln Park"]
    assert_scoped(ids, body, ids.merchants["alder-loom"])


def test_team_lists_every_membership_of_the_business(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("jordan").get("/api/settings/team").json()
    members = body["members"]
    expected = seeded_conn.execute(
        "SELECT u.full_name, mem.role, mem.id FROM membership mem JOIN app_user u ON u.id = mem.user_id WHERE mem.merchant_id = ? ORDER BY u.full_name, mem.id",
        (ids.merchants["alder-loom"],),
    ).fetchall()
    assert [(m["user"]["full_name"], m["role"], m["membership_id"]) for m in members] == [tuple(r) for r in expected]
    sam = next(m for m in members if m["user"]["full_name"] == "Sam Okafor")
    assert sam["role_label"] == "Read-only analyst" and sam["is_active"] is True and sam["email"] == "sam.okafor@example.com"
    assert sam["membership_id"] == ids.memberships[("sam.okafor@example.com", "alder-loom")]
    assert set(members[0]) == {"membership_id", "user", "email", "title", "role", "role_label", "is_active", "member_since"}
    assert_scoped(ids, body, ids.merchants["alder-loom"])


def test_activity_lists_notes_and_exports_newest_first(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    jordan = client_as("jordan")
    body = jordan.get("/api/settings/activity?page_size=100").json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["total"] == seeded_conn.execute("SELECT COUNT(*) FROM note_event WHERE merchant_id = ?", (ids.merchants["alder-loom"],)).fetchone()[0]
    stamps = [i["created_at"] for i in body["items"]]
    assert stamps == sorted(stamps, reverse=True)
    assert_scoped(ids, body, ids.merchants["alder-loom"])
    for item in body["items"]:
        assert set(item) == {"id", "kind", "kind_label", "actor", "subject", "body", "created_at"}
        assert item["kind"] in ("note", "export")
        if item["kind"] == "note":
            assert item["subject"]["kind"] in ("payment", "dispute") and item["subject"]["id"]
    assert all(i["kind"] == "note" for i in jordan.get("/api/settings/activity?kind=note").json()["items"])
    assert jordan.get("/api/settings/activity?kind=login").status_code == 422

    # A note added by Maya appears for the admin with Maya as the actor and the payment as the subject.
    maya = client_as("maya")
    payment = maya.get("/api/payments?period=last_30_days&q=AL-11404").json()["items"][0]
    maya.post(f"/api/payments/{payment['id']}/notes", json={"body": "Checked with the carrier."})
    latest = jordan.get("/api/settings/activity?kind=note").json()["items"][0]
    assert latest["actor"]["full_name"] == "Maya Chen"
    assert latest["subject"] == {"kind": "payment", "id": payment["id"], "label": "AL-11404"}
    assert latest["body"] == "Checked with the carrier."


def test_settings_are_admin_only_and_scoped(client, client_as, ids: Ids) -> None:
    for path in ("/api/settings/profile", "/api/settings/team", "/api/settings/activity"):
        assert client.get(path).status_code == 401, path
        for persona in ("maya", "daniel", "sam", "priya"):
            assert client_as(persona).get(path).status_code == 403, (persona, path)
        assert client_as("jordan").get(path).status_code == 200, path
