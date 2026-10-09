"""Every CSV export honours the current filters and the merchant scope.

For each report and a handful of filter combinations: every row satisfies every filter, every id in the file belongs to
the merchant, the row count equals the filtered count the list endpoint reports, and permissions follow the matrix.
"""

from __future__ import annotations

import csv
import io
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.money import format_usd
from tests.conftest import Ids

CHICAGO_OFFSET = ("-05:00", "-06:00")


def rows_of(r) -> list[dict[str, str]]:
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith('attachment; filename="')
    text = r.text
    assert not text.endswith("\n\n")
    return list(csv.DictReader(io.StringIO(text)))


def list_total(c: TestClient, path: str) -> int:
    r = c.get(path)
    assert r.status_code == 200, r.text
    return r.json()["total"]


def assert_owned(ids: Ids, merchant_id: str, *values: str | None) -> None:
    for value in values:
        if value:
            assert ids.owner_of[value] == merchant_id, value


PAYMENT_CASES = [
    ("maya", "period=last_30_days&status=failed"),
    ("maya", "period=last_7_days&channel=in_store"),
    ("maya", "period=last_30_days&amount_min_cents=10000&amount_max_cents=20000"),
    ("maya", "period=month_to_date&q=AL-1"),
    ("priya", "period=last_30_days&status=partially_refunded"),
    ("sam_copper", "from=2026-09-10&to=2026-09-20&channel=in_store"),
]


@pytest.mark.parametrize("persona,query", PAYMENT_CASES)
def test_payment_register_honours_filters_and_scope(client_as, ids: Ids, persona: str, query: str) -> None:
    c = client_as(persona) if persona != "sam_copper" else client_as("jordan")
    merchant_slug = {"maya": "alder-loom", "priya": "juniper-trail", "sam_copper": "copper-finch"}[persona]
    if persona == "sam_copper":  # the analyst holds no export permission; use the Alder admin on an Alder-only query instead
        merchant_slug = "alder-loom"
    merchant_id = ids.merchants[merchant_slug]
    rows = rows_of(c.get(f"/api/reports/payments.csv?{query}"))
    assert len(rows) == list_total(c, f"/api/payments?{query}&page_size=1")
    params = dict(p.split("=") for p in query.split("&"))
    for row in rows:
        assert_owned(ids, merchant_id, row["payment_id"], row["customer_id"] or None, row["location_id"] or None, row["dispute_id"] or None)
        if "status" in params:
            assert row["status"] == params["status"]
        if "channel" in params:
            assert row["channel"] == params["channel"]
        if "failure_code" in params:
            assert row["failure_code"] == params["failure_code"]
        if "amount_min_cents" in params:
            assert int(params["amount_min_cents"]) <= int(row["amount_cents"]) <= int(params["amount_max_cents"])
        if "q" in params:
            assert params["q"].lower() in (row["order_reference"] + row["customer_name"] + row["customer_email"] + row["payment_id"]).lower()
        assert row["amount_usd"] == format_usd(int(row["amount_cents"]))
        assert row["net_usd"] == format_usd(int(row["net_cents"]))
        assert row["created_at"].endswith("Z") and row["created_at_chicago"][-6:] in CHICAGO_OFFSET
    assert rows == sorted(rows, key=lambda r: r["created_at"], reverse=True)


def test_payment_register_matches_the_list_for_the_whole_window(client_as, ids: Ids) -> None:
    c = client_as("maya")
    rows = rows_of(c.get("/api/reports/payments.csv?period=last_30_days"))
    total = list_total(c, "/api/payments?period=last_30_days&page_size=1")
    assert len(rows) == total
    assert len({r["payment_id"] for r in rows}) == total
    assert rows[-1]["payment_id"].startswith("pay_")  # the last line is a record, never a totals row


ATTEMPT_CASES = [
    ("maya", "period=last_30_days&outcome=failed"),
    ("maya", "period=last_7_days&outcome=succeeded&channel=website"),
    ("maya", "period=last_30_days&channel=mobile_app"),
    ("maya", "period=last_7_days&outcome=failed&failure_code=issuer_unavailable&channel=mobile_app"),
    ("priya", "period=last_30_days&outcome=pending"),
    ("jordan", "period=last_30_days&q=AL-11404"),
]


@pytest.mark.parametrize("persona,query", ATTEMPT_CASES)
def test_attempt_export_honours_filters_and_scope(client_as, ids: Ids, persona: str, query: str) -> None:
    c = client_as(persona)
    merchant_id = ids.merchants[{"maya": "alder-loom", "jordan": "alder-loom", "priya": "juniper-trail"}[persona]]
    rows = rows_of(c.get(f"/api/reports/attempts.csv?{query}"))
    assert len(rows) == list_total(c, f"/api/attempts?{query}&page_size=1")
    params = dict(p.split("=") for p in query.split("&"))
    for row in rows:
        assert_owned(ids, merchant_id, row["attempt_id"], row["payment_id"], row["customer_id"] or None)
        if "outcome" in params:
            assert row["outcome"] == params["outcome"]
        if "channel" in params:
            assert row["channel"] == params["channel"]
        if row["outcome"] == "failed":
            assert row["failure_code"] and row["failure_message"]
        else:
            assert row["failure_code"] == "" and row["failure_message"] == ""
        assert row["method_label"] and row["card_last4"].isdigit() and len(row["card_last4"]) == 4
        assert row["amount_usd"] == format_usd(int(row["amount_cents"]))


def test_payout_reconciliation_export(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("daniel")
    merchant_id = ids.merchants["alder-loom"]
    rows = rows_of(c.get("/api/reports/payouts.csv"))
    assert len(rows) == list_total(c, "/api/payouts?page_size=1")
    for row in rows:
        assert_owned(ids, merchant_id, row["payout_id"])
        buckets = sum(int(row[k]) for k in ("collections_cents", "fees_cents", "refunds_cents", "disputes_cents", "adjustments_cents"))
        assert buckets == int(row["amount_cents"])
        ledger = seeded_conn.execute("SELECT SUM(amount_cents) FROM balance_movement WHERE payout_id = ?", (row["payout_id"],)).fetchone()[0]
        assert ledger == int(row["amount_cents"])
        assert row["amount_usd"] == format_usd(int(row["amount_cents"]))
        assert "demo record" in row["destination"]
    paid = rows_of(c.get("/api/reports/payouts.csv?status=paid&from=2026-09-28&to=2026-10-02"))
    assert len(paid) == list_total(c, "/api/payouts?status=paid&from=2026-09-28&to=2026-10-02&page_size=1")
    assert all(r["status"] == "paid" and "2026-09-28" <= r["payout_date"] <= "2026-10-02" for r in paid)
    assert c.get("/api/reports/payouts.csv?from=2026-10-01").status_code == 422


def test_refund_register_export(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("daniel")
    merchant_id = ids.merchants["alder-loom"]
    for query, where in (
        ("period=last_30_days", ""),
        ("period=last_30_days&status=pending", " AND status = 'pending'"),
        ("period=last_7_days&reason=price_adjustment", " AND reason = 'price_adjustment'"),
    ):
        rows = rows_of(c.get(f"/api/reports/refunds.csv?{query}"))
        days = 30 if "last_30" in query else 7
        start = {30: "2026-09-06T05:00:00Z", 7: "2026-09-29T05:00:00Z"}[days]
        expected = seeded_conn.execute(
            f"SELECT COUNT(*) FROM refund WHERE merchant_id = ? AND created_at >= ? AND created_at < '2026-10-06T05:00:00Z'{where}", (merchant_id, start)
        ).fetchone()[0]
        assert len(rows) == expected, query
        params = dict(p.split("=") for p in query.split("&"))
        for row in rows:
            assert_owned(ids, merchant_id, row["refund_id"], row["payment_id"], row["customer_id"] or None)
            if "status" in params:
                assert row["status"] == params["status"]
            if "reason" in params:
                assert row["reason"] == params["reason"]
            assert row["amount_usd"] == format_usd(int(row["amount_cents"]))
            assert (row["completed_at"] == "") == (row["status"] == "pending")


def test_permissions_follow_the_matrix(client, client_as) -> None:
    for path in ("/api/reports/payments.csv", "/api/reports/attempts.csv", "/api/reports/payouts.csv", "/api/reports/refunds.csv"):
        assert client.get(path).status_code == 401, path
    operational = {"maya": 200, "jordan": 200, "daniel": 200, "sam": 403}
    financial = {"maya": 403, "jordan": 403, "daniel": 200, "sam": 403}
    for persona, expected in operational.items():
        assert client_as(persona).get("/api/reports/payments.csv?period=last_7_days").status_code == expected, persona
        assert client_as(persona).get("/api/reports/attempts.csv?period=last_7_days").status_code == expected, persona
    for persona, expected in financial.items():
        assert client_as(persona).get("/api/reports/payouts.csv").status_code == expected, persona
        assert client_as(persona).get("/api/reports/refunds.csv?period=last_7_days").status_code == expected, persona


def test_every_download_is_recorded_as_activity(client_as, app, ids: Ids) -> None:
    daniel = client_as("daniel")
    jordan = client_as("jordan")
    before = jordan.get("/api/settings/activity?kind=export").json()["total"]
    r = daniel.get("/api/reports/refunds.csv?period=last_7_days")
    filename = r.headers["content-disposition"].split('filename="')[1].rstrip('"')
    assert filename == "alder-loom_refunds_2026-09-29_2026-10-05.csv"
    daniel.get("/api/reports/payments.csv?period=month_to_date")
    activity = jordan.get("/api/settings/activity?kind=export").json()
    assert activity["total"] == before + 2
    names = [i["subject"]["label"] for i in activity["items"][:2]]
    assert filename in names and "alder-loom_payments_2026-10-01_2026-10-05.csv" in names
    assert all(i["actor"]["full_name"] == "Daniel Brooks" and i["kind"] == "export" for i in activity["items"][:2])


def test_a_payout_that_does_not_reconcile_fails_the_export_loudly(client_as, db_copy) -> None:
    daniel = client_as("daniel")
    payout_id = daniel.get("/api/payouts").json()["items"][0]["id"]
    conn = sqlite3.connect(db_copy)
    conn.execute("UPDATE payout SET amount_cents = amount_cents + 1 WHERE id = ?", (payout_id,))
    conn.commit()
    conn.close()
    r = daniel.get("/api/reports/payouts.csv")
    assert r.status_code == 500 and r.json()["error"]["code"] == "reconciliation_mismatch"
