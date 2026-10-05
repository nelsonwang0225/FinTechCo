"""GET /api/payouts: ordering, filters, and the funds summary with the derived next payout."""

from __future__ import annotations

import sqlite3

from tests.conftest import Ids, assert_scoped

AS_OF = "2026-10-05T14:12:00Z"


def test_list_orders_in_transit_first_then_newest(client_as, ids: Ids) -> None:
    body = client_as("daniel").get("/api/payouts?page_size=100").json()
    statuses = [i["status"] for i in body["items"]]
    assert statuses[0] == "in_transit" and statuses.count("in_transit") == 1
    paid = [i["cutoff_at"] for i in body["items"] if i["status"] == "paid"]
    assert paid == sorted(paid, reverse=True)
    assert body["total"] == 20
    assert set(body["items"][0]) == {"id", "status", "status_label", "amount_cents", "currency", "cutoff_at", "payout_date", "sent_at",
                                     "expected_arrival_date", "paid_at", "destination"}
    assert_scoped(ids, body, ids.merchant("alder-loom"))


def test_status_and_date_filters(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("daniel")
    paid = c.get("/api/payouts?status=paid&page_size=100").json()
    assert paid["total"] == seeded_conn.execute("SELECT COUNT(*) FROM payout WHERE merchant_id = ? AND status = 'paid'", (ids.merchant("alder-loom"),)).fetchone()[0]
    assert all(i["status"] == "paid" and i["paid_at"] for i in paid["items"])
    in_transit = c.get("/api/payouts?status=in_transit").json()
    assert in_transit["total"] == 1 and in_transit["items"][0]["paid_at"] is None and in_transit["items"][0]["payout_date"] == "2026-10-05"
    ranged = c.get("/api/payouts?from=2026-09-21&to=2026-09-25").json()
    assert [i["payout_date"] for i in ranged["items"]] == ["2026-09-25", "2026-09-24", "2026-09-23", "2026-09-22", "2026-09-21"]
    assert c.get("/api/payouts?from=2026-09-21").status_code == 422
    assert c.get("/api/payouts?from=2026-09-25&to=2026-09-21").status_code == 422
    assert c.get("/api/payouts?status=sent").status_code == 422


def test_labor_day_has_no_cutoff(client_as) -> None:
    body = client_as("daniel").get("/api/payouts?from=2026-09-05&to=2026-09-08").json()
    assert [i["payout_date"] for i in body["items"]] == ["2026-09-08"]


def test_funds_summary_matches_unswept_movements(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    summary = client_as("daniel").get("/api/payouts").json()["summary"]
    available, pending = seeded_conn.execute(
        "SELECT SUM(CASE WHEN available_at <= ? THEN amount_cents ELSE 0 END), SUM(CASE WHEN available_at > ? THEN amount_cents ELSE 0 END) "
        "FROM balance_movement WHERE merchant_id = ? AND payout_id IS NULL",
        (AS_OF, AS_OF, ids.merchant("alder-loom")),
    ).fetchone()
    assert summary["available_cents"] == available > 0
    assert summary["pending_cents"] == pending > 0
    assert summary["as_of"] == AS_OF
    assert summary["currency"] == "USD"
    assert "balance" not in summary["next_payout"]["note"].lower().replace("not a bank balance", "")
    assert summary["destination"] == "Alder & Loom, Operating account •••• 4821, external bank account, demo record"


def test_next_payout_is_derived_from_the_schedule(client_as) -> None:
    alder = client_as("daniel").get("/api/payouts").json()["summary"]
    assert alder["next_payout"]["cutoff_at"] == "2026-10-06T05:00:00Z"  # Tuesday 00:00 CT
    assert alder["next_payout"]["payout_date"] == "2026-10-06"
    assert alder["next_payout"]["amount_cents"] == alder["available_cents"]
    assert alder["next_payout"]["schedule_label"] == "Every business day"
    copper = client_as("sam_copper").get("/api/payouts").json()["summary"]
    assert copper["next_payout"]["payout_date"] == "2026-10-12"  # next Monday
    assert copper["next_payout"]["schedule"] == "weekly_monday"
    assert copper["destination"].startswith("Copper Finch Coffee, Business checking •••• 7730")
