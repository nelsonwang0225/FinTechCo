"""Definition of Done 5: a payout detail reconciles exactly to its ledger movements, and the CSV downloads.

Every payout of every merchant is checked in the database; every payout a persona can reach is checked
through the API and the CSV. Daniel (finance) downloads; Jordan (admin) is refused the CSV; Priya has no
payouts:read at all; Sam Okafor at Copper Finch asking for an Alder & Loom payout reaches the scope check
and gets 404.
"""

from __future__ import annotations

import csv
import io
import shutil
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.connection import connect
from app.main import create_app
from tests.conftest import Ids, assert_scoped


def test_every_payout_of_every_merchant_reconciles_in_the_database(seeded_conn: sqlite3.Connection) -> None:
    rows = seeded_conn.execute(
        "SELECT p.id, p.merchant_id, p.amount_cents, (SELECT SUM(m.amount_cents) FROM balance_movement m WHERE m.payout_id = p.id AND m.merchant_id = p.merchant_id), "
        "(SELECT COUNT(*) FROM balance_movement m WHERE m.payout_id = p.id) FROM payout p"
    ).fetchall()
    assert len(rows) == 29
    for payout_id, _, amount, ledger_sum, count in rows:
        assert amount == ledger_sum, payout_id
        assert count > 0, payout_id
    assert seeded_conn.execute("SELECT COUNT(DISTINCT merchant_id) FROM payout").fetchone()[0] == 3


def test_every_reachable_payout_reconciles_in_the_response_and_the_csv(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    for persona, slug in (("daniel", "alder-loom"), ("sam_copper", "copper-finch")):
        reader = client_as(persona)
        downloader = client_as("daniel") if slug == "alder-loom" else None
        listing = reader.get("/api/payouts?page_size=100").json()
        expected = seeded_conn.execute("SELECT COUNT(*) FROM payout WHERE merchant_id = ?", (ids.merchant(slug),)).fetchone()[0]
        assert listing["total"] == expected == len(listing["items"])
        for item in listing["items"]:
            detail = reader.get(f"/api/payouts/{item['id']}").json()
            assert detail["reconciled"] is True
            assert detail["movement_total_cents"] == detail["amount_cents"] == item["amount_cents"]
            assert sum(m["amount_cents"] for m in detail["movements"]) == detail["amount_cents"]
            buckets = detail["buckets"]
            assert sum(buckets.values()) == detail["amount_cents"]
            assert detail["movement_count"] == len(detail["movements"]) == seeded_conn.execute(
                "SELECT COUNT(*) FROM balance_movement WHERE payout_id = ?", (item["id"],)
            ).fetchone()[0]
            assert "demo record" in detail["destination"]
            assert_scoped(ids, detail, ids.merchant(slug))
            if downloader is not None:
                r = downloader.get(f"/api/payouts/{item['id']}/export.csv")
                assert r.status_code == 200
                rows = list(csv.DictReader(io.StringIO(r.text)))
                assert len(rows) == detail["movement_count"]
                assert sum(int(row["amount_cents"]) for row in rows) == detail["amount_cents"]
                assert all(row["payout_id"] == item["id"] for row in rows)


def test_csv_shape_headers_and_activity_record(client_as, ids: Ids, app) -> None:
    daniel = client_as("daniel")
    payout_id = daniel.get("/api/payouts?page_size=1").json()["items"][0]["id"]
    detail = daniel.get(f"/api/payouts/{payout_id}").json()
    r = daniel.get(f"/api/payouts/{payout_id}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == f'attachment; filename="alder-loom_payout_{detail["payout_date"]}_{payout_id}.csv"'
    lines = r.text.splitlines()
    assert lines[0].split(",") == [
        "movement_id", "type", "type_label", "amount_cents", "amount_usd", "currency", "description", "posted_at", "posted_at_chicago",
        "available_at", "available_at_chicago", "payment_id", "order_reference", "customer_name", "refund_id", "dispute_id", "payout_id",
    ]
    assert len(lines) == 1 + detail["movement_count"]  # header plus one row per movement; no totals row
    rows = list(csv.DictReader(io.StringIO(r.text)))
    for row in rows:
        cents = int(row["amount_cents"])
        dollars, rem = divmod(abs(cents), 100)
        assert row["amount_usd"] == f"{'-' if cents < 0 else ''}{dollars:,}.{rem:02d}"
        assert row["posted_at"].endswith("Z") and row["posted_at_chicago"].endswith("-05:00")
        assert row["currency"] == "USD"
    assert not any(row["type"].lower().startswith("total") for row in rows)
    # The download is recorded as an export activity by the acting user.
    conn = connect(app.state.db_path)
    try:
        event = conn.execute("SELECT kind, actor_user_id, export_name, merchant_id FROM note_event WHERE kind = 'export' ORDER BY created_at DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert event["actor_user_id"] == ids.users["daniel.brooks@alder-loom.example.com"]
    assert event["export_name"].endswith(f"{payout_id}.csv")
    assert event["merchant_id"] == ids.merchant("alder-loom")


def test_roles_and_scope(client_as, ids: Ids) -> None:
    payout_id = ids.sample("alder-loom", "payout_id")
    assert client_as("daniel").get(f"/api/payouts/{payout_id}").status_code == 200
    assert client_as("daniel").get(f"/api/payouts/{payout_id}/export.csv").status_code == 200
    assert client_as("jordan").get(f"/api/payouts/{payout_id}").status_code == 200
    assert client_as("jordan").get(f"/api/payouts/{payout_id}/export.csv").status_code == 403
    assert client_as("sam").get(f"/api/payouts/{payout_id}").status_code == 200
    assert client_as("sam").get(f"/api/payouts/{payout_id}/export.csv").status_code == 403
    assert client_as("maya").get("/api/payouts").status_code == 403
    assert client_as("priya").get(f"/api/payouts/{payout_id}").status_code == 403
    assert client_as("priya").get("/api/payouts").status_code == 403
    r = client_as("sam_copper").get(f"/api/payouts/{payout_id}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client_as("daniel").get(f"/api/payouts/{ids.sample('juniper-trail', 'payout_id')}").status_code == 404
    assert client_as("daniel").get("/api/payouts/po_nothere0000000").status_code == 404


def test_a_mismatch_is_a_500_never_papered_over(template_db: Path, tmp_path: Path, ids: Ids) -> None:
    broken = tmp_path / "broken.db"
    shutil.copyfile(template_db, broken)
    payout_id = ids.sample("alder-loom", "payout_id")
    conn = connect(broken)
    try:
        conn.execute("UPDATE payout SET amount_cents = amount_cents + 1 WHERE id = ?", (payout_id,))
        conn.commit()
    finally:
        conn.close()
    with TestClient(create_app(broken), raise_server_exceptions=False) as c:
        c.post("/api/dev/session", json={"user_id": ids.users["daniel.brooks@alder-loom.example.com"], "merchant_id": ids.merchant("alder-loom")})
        r = c.get(f"/api/payouts/{payout_id}")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "reconciliation_mismatch"
        assert c.get(f"/api/payouts/{payout_id}/export.csv").status_code == 500
