"""GET /api/payments/{id}: derived status, attempts, refunds, dispute tag, payout link and the read-time timeline."""

from __future__ import annotations

import sqlite3

from tests.conftest import Ids, assert_scoped


def anchor_id(client) -> str:
    return client.get("/api/payments?period=last_30_days&q=AL-11404").json()["items"][0]["id"]


def test_anchor_payment_timeline_reads_in_order(client_as, ids: Ids) -> None:
    c = client_as("maya")
    detail = c.get(f"/api/payments/{anchor_id(c)}").json()
    assert detail["status"] == "partially_refunded"
    assert detail["customer"]["email"] == "taylor.reed@example.com"
    assert detail["amount_cents"] == 34398 and detail["refunded_cents"] == 4800 and detail["net_cents"] == 29598
    assert [a["outcome"] for a in detail["attempts"]] == ["failed", "succeeded"]
    assert detail["attempts"][0]["failure_code"] == "insufficient_funds"
    assert detail["refunds"][0]["reason_label"] == "Price adjustment" and detail["refunds"][0]["status"] == "succeeded"
    assert detail["payout"]["status"] == "paid"
    assert detail["funds_available_at"] == "2026-09-24T19:14:53Z"
    kinds = [e["kind"] for e in detail["timeline"]]
    assert kinds == ["order_received", "attempt_failed", "attempt_succeeded", "funds_available", "payout_included", "refund_succeeded", "note", "payout_paid"]
    ats = [e["at"] for e in detail["timeline"]]
    assert ats == sorted(ats)
    assert not any(e["upcoming"] for e in detail["timeline"])
    note = next(e for e in detail["timeline"] if e["kind"] == "note")
    assert note["title"] == "Note by Maya Chen"
    assert detail["notes"][0]["actor"]["full_name"] == "Maya Chen"
    assert_scoped(ids, detail, ids.merchant("alder-loom"))


def test_pending_payment_has_no_funds_or_payout(client_as) -> None:
    c = client_as("maya")
    pending = c.get("/api/payments?status=pending&page_size=1").json()["items"][0]
    detail = c.get(f"/api/payments/{pending['id']}").json()
    assert detail["status"] == "pending" and detail["succeeded_at"] is None
    assert detail["funds_available_at"] is None and detail["payout"] is None
    assert [e["kind"] for e in detail["timeline"]] == ["order_received", "attempt_pending"]


def test_recent_success_shows_funds_available_as_upcoming(client_as) -> None:
    c = client_as("maya")
    recent = c.get("/api/payments?status=succeeded&sort=created_at&dir=desc&page_size=1").json()["items"][0]
    detail = c.get(f"/api/payments/{recent['id']}").json()
    assert detail["funds_available_at"] > "2026-10-05T14:12:00Z"
    funds = next(e for e in detail["timeline"] if e["kind"] == "funds_available")
    assert funds["upcoming"] is True
    assert detail["payout"] is None


def test_disputed_payment_carries_the_tag_and_milestones(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("maya")
    row = seeded_conn.execute("SELECT payment_id FROM dispute WHERE merchant_id = ? AND status = 'needs_response' ORDER BY opened_at LIMIT 1", (ids.merchant("alder-loom"),)).fetchone()
    detail = c.get(f"/api/payments/{row[0]}").json()
    assert detail["dispute"]["status"] == "needs_response"
    kinds = [e["kind"] for e in detail["timeline"]]
    assert "dispute_opened" in kinds and "dispute_evidence_due" in kinds
    due = next(e for e in detail["timeline"] if e["kind"] == "dispute_evidence_due")
    assert due["upcoming"] is True
    won = seeded_conn.execute("SELECT payment_id FROM dispute WHERE status = 'won' LIMIT 1").fetchone()
    detail = c.get(f"/api/payments/{won[0]}").json()
    assert [e["kind"] for e in detail["timeline"] if e["kind"].startswith("dispute")] == ["dispute_opened", "dispute_responded", "dispute_resolved"]
    assert detail["dispute"]["status_label"] == "Won"


def test_status_matches_the_view_for_a_spread_of_payments(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("maya")
    for status in ("succeeded", "failed", "pending", "partially_refunded", "refunded"):
        row = seeded_conn.execute("SELECT id FROM payment_summary WHERE merchant_id = ? AND status = ? LIMIT 1", (ids.merchant("alder-loom"), status)).fetchone()
        detail = c.get(f"/api/payments/{row[0]}").json()
        assert detail["status"] == status
        refunded = sum(r["amount_cents"] for r in detail["refunds"] if r["status"] == "succeeded")
        assert detail["refunded_cents"] == refunded
        assert detail["net_cents"] == detail["amount_cents"] - refunded
        if status == "refunded":
            assert refunded == detail["amount_cents"]


def test_unknown_or_malformed_ids_are_404(client_as) -> None:
    c = client_as("maya")
    assert c.get("/api/payments/pay_doesnotexist00").status_code == 404
    assert c.get("/api/payments/not-an-id").status_code == 404
    assert c.get("/api/payments/not-an-id").json()["error"]["code"] == "not_found"
