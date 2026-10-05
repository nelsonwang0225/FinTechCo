"""Overview: every tile is an independent recomputation from the ledger, the chart buckets by Chicago day and sums to
the tile, the response key set is exact, and the attention list is the closed set of three kinds."""

from __future__ import annotations

import inspect
import re
import sqlite3
from datetime import date
from typing import Any

import pytest

from app.api import overview as overview_api
from app.core import clock, periods
from app.core.tz import chicago_day_bounds, chicago_local
from app.db.queries import overview as overview_q
from tests.conftest import PERSONAS, Ids, assert_scoped

TOP_KEYS = {"greeting", "period", "tiles", "chart", "recent_payments", "upcoming_payout", "attention"}
TILE_KEYS = {"collected_cents", "refunds_cents", "funds_available_cents", "pending_cents", "currency", "next_payout"}
ATTENTION_KINDS = {"dispute_deadline", "payout_in_transit", "refund_pending"}
FORBIDDEN_KEY = re.compile(r"count|rate|ratio|percent|share|outcome|attempt", re.IGNORECASE)


def walk_keys(payload: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            out.append(f"{path}.{key}")
            out.extend(walk_keys(value, f"{path}.{key}"))
    elif isinstance(payload, list):
        for value in payload:
            out.extend(walk_keys(value, path + "[]"))
    return out


def ledger(conn: sqlite3.Connection, merchant_id: str, movement_type: str, start: str, end: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM balance_movement WHERE merchant_id = ? AND type = ? AND posted_at >= ? AND posted_at < ?",
        (merchant_id, movement_type, start, end),
    ).fetchone()
    return int(row[0])


@pytest.mark.parametrize("persona", ["maya", "daniel", "jordan", "sam", "priya", "sam_copper"])
def test_every_role_gets_the_overview_with_an_exact_key_set(client_as, ids: Ids, persona: str) -> None:
    r = client_as(persona).get("/api/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == TOP_KEYS
    assert set(body["tiles"]) == TILE_KEYS
    assert set(body["chart"]) == {"title", "points", "total_cents", "currency"}
    assert all(set(p) == {"day", "amount_cents"} for p in body["chart"]["points"])
    assert set(body["upcoming_payout"]) == {"cutoff_at", "payout_date", "amount_cents", "currency", "schedule", "schedule_label", "destination", "note", "buckets"}
    assert {item["kind"] for item in body["attention"]} <= ATTENTION_KINDS
    offending = [k for k in walk_keys(body) if FORBIDDEN_KEY.search(k.rsplit(".", 1)[-1])]
    assert not offending, offending
    assert_scoped(ids, body, ids.merchants[PERSONAS[persona][1]])


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("preset", ["last_7_days", "last_30_days", "month_to_date"])
def test_tiles_and_chart_match_an_independent_recomputation(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str) -> None:
    merchant_id = ids.merchants[PERSONAS[persona][1]]
    period = periods.resolve(preset, clock.now(seeded_conn))
    body = client_as(persona).get(f"/api/overview?period={preset}").json()
    assert body["period"]["preset"] == preset
    assert body["period"]["from_date"] == period.from_day.isoformat()
    assert body["period"]["to_date"] == period.to_day.isoformat()

    tiles = body["tiles"]
    assert tiles["collected_cents"] == ledger(seeded_conn, merchant_id, "charge", period.start, period.end)
    assert tiles["refunds_cents"] == -ledger(seeded_conn, merchant_id, "refund", period.start, period.end)
    assert tiles["refunds_cents"] >= 0

    now_text = body["greeting"]["as_of"]
    available = seeded_conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM balance_movement WHERE merchant_id = ? AND payout_id IS NULL AND available_at <= ?",
        (merchant_id, now_text),
    ).fetchone()[0]
    pending = seeded_conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM balance_movement WHERE merchant_id = ? AND payout_id IS NULL AND available_at > ?",
        (merchant_id, now_text),
    ).fetchone()[0]
    assert tiles["funds_available_cents"] == available
    assert tiles["pending_cents"] == pending
    assert tiles["next_payout"]["amount_cents"] == available
    assert "Not a bank balance" in tiles["next_payout"]["note"]

    chart = body["chart"]
    days = periods.day_buckets(period)
    assert [p["day"] for p in chart["points"]] == [d.isoformat() for d in days]
    assert sum(p["amount_cents"] for p in chart["points"]) == tiles["collected_cents"] == chart["total_cents"]
    for point in chart["points"]:
        start, end = chicago_day_bounds(date.fromisoformat(point["day"]))
        assert point["amount_cents"] == ledger(seeded_conn, merchant_id, "charge", start, end), point["day"]


def test_chart_has_a_zero_for_a_day_with_nothing_collected(client_as) -> None:
    body = client_as("sam_copper").get("/api/overview?period=custom&from=2026-09-07&to=2026-09-07").json()
    assert body["chart"]["points"] == [{"day": "2026-09-07", "amount_cents": body["chart"]["points"][0]["amount_cents"]}]
    body = client_as("maya").get("/api/overview?period=custom&from=2026-08-01&to=2026-08-03").json()
    assert body["chart"]["points"] == [{"day": "2026-08-01", "amount_cents": 0}, {"day": "2026-08-02", "amount_cents": 0}, {"day": "2026-08-03", "amount_cents": 0}]
    assert body["tiles"]["collected_cents"] == 0 and body["tiles"]["refunds_cents"] == 0


def test_buckets_follow_chicago_midnight_including_the_dst_change() -> None:
    days = [date(2026, 9, 30), date(2026, 10, 1), date(2026, 11, 1), date(2026, 11, 2)]
    rows = [
        {"posted_at": "2026-10-01T04:59:59Z", "amount_cents": 100},  # 23:59:59 CDT on Sep 30
        {"posted_at": "2026-10-01T05:00:00Z", "amount_cents": 1000},  # 00:00:00 CDT on Oct 1
        {"posted_at": "2026-11-02T05:59:59Z", "amount_cents": 10},  # 23:59:59 CST on Nov 1, after the DST change
        {"posted_at": "2026-11-02T06:00:00Z", "amount_cents": 1},  # 00:00:00 CST on Nov 2
        {"posted_at": "2026-12-25T12:00:00Z", "amount_cents": 99999},  # outside the days asked for: ignored
    ]
    assert overview_q.bucket_by_chicago_day(rows, days) == {date(2026, 9, 30): 100, date(2026, 10, 1): 1000, date(2026, 11, 1): 10, date(2026, 11, 2): 1}


def test_recent_payments_are_the_latest_six_for_the_merchant(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchants["alder-loom"]
    body = client_as("maya").get("/api/overview").json()
    expected = [r[0] for r in seeded_conn.execute("SELECT id FROM payment WHERE merchant_id = ? ORDER BY created_at DESC, id LIMIT 6", (merchant_id,))]
    assert [p["id"] for p in body["recent_payments"]] == expected
    assert all(set(p) >= {"id", "order_reference", "created_at", "amount_cents", "status", "status_label"} for p in body["recent_payments"])


def test_upcoming_payout_buckets_sum_to_funds_available(client_as) -> None:
    for persona in ("maya", "priya", "sam_copper"):
        body = client_as(persona).get("/api/overview").json()
        upcoming = body["upcoming_payout"]
        assert sum(upcoming["buckets"].values()) == upcoming["amount_cents"] == body["tiles"]["funds_available_cents"]
        assert upcoming["payout_date"] == body["tiles"]["next_payout"]["payout_date"]
        assert "demo record" in upcoming["destination"]


def test_attention_items_come_from_disputes_payouts_and_refunds_only(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchants["alder-loom"]
    body = client_as("maya").get("/api/overview").json()
    items = body["attention"]
    disputes = [i for i in items if i["kind"] == "dispute_deadline"]
    payouts = [i for i in items if i["kind"] == "payout_in_transit"]
    refunds = [i for i in items if i["kind"] == "refund_pending"]
    assert len(disputes) + len(payouts) + len(refunds) == len(items)

    expected_disputes = seeded_conn.execute("SELECT id, evidence_due_at FROM dispute WHERE merchant_id = ? AND status = 'needs_response' ORDER BY evidence_due_at, id", (merchant_id,)).fetchall()
    assert [(i["link"]["id"], i["at"]) for i in disputes] == [(r[0], r[1]) for r in expected_disputes]
    assert all(i["link"] == {"kind": "dispute", "id": i["link"]["id"], "permission": "disputes:read"} for i in disputes)
    assert all(i["at_label"] == "Evidence due" for i in disputes)

    expected_payouts = seeded_conn.execute("SELECT id, sent_at, amount_cents FROM payout WHERE merchant_id = ? AND status = 'in_transit' ORDER BY cutoff_at DESC, id", (merchant_id,)).fetchall()
    assert [(i["link"]["id"], i["at"], i["amount_cents"]) for i in payouts] == [tuple(r) for r in expected_payouts]
    assert all(i["link"]["permission"] == "payouts:read" for i in payouts)

    expected_refunds = seeded_conn.execute("SELECT payment_id, created_at, amount_cents FROM refund WHERE merchant_id = ? AND status = 'pending' ORDER BY created_at DESC, id", (merchant_id,)).fetchall()
    assert [(i["link"]["id"], i["at"], i["amount_cents"]) for i in refunds] == [tuple(r) for r in expected_refunds]
    assert all(i["link"] == {"kind": "payment", "id": i["link"]["id"], "permission": "payments:read"} for i in refunds)

    # The attention and overview code never reads the attempt table.
    assert "payment_attempt" not in inspect.getsource(overview_q)
    assert "payment_attempt" not in inspect.getsource(overview_api)


def test_period_validation(client_as) -> None:
    c = client_as("maya")
    assert c.get("/api/overview?period=custom").status_code == 422
    assert c.get("/api/overview?period=yesterday").status_code == 422
    assert c.get("/api/overview?period=custom&from=2026-10-05&to=2026-10-01").status_code == 422
    body = c.get("/api/overview?from=2026-10-01&to=2026-10-02").json()
    assert body["period"]["preset"] == "custom" and len(body["chart"]["points"]) == 2


def test_greeting_hangs_off_the_reporting_clock(client_as) -> None:
    c = client_as("maya")
    session = c.get("/api/session").json()
    greeting = c.get("/api/overview").json()["greeting"]
    assert greeting == {"salutation": "Good morning", "first_name": "Maya", "merchant_name": "Alder & Loom", "as_of": session["as_of"]}
    assert overview_api.salutation_for(chicago_local(2026, 10, 5, 11, 59)) == "Good morning"
    assert overview_api.salutation_for(chicago_local(2026, 10, 5, 12, 0)) == "Good afternoon"
    assert overview_api.salutation_for(chicago_local(2026, 10, 5, 17, 0)) == "Good evening"


def test_anonymous_and_cross_merchant_scoping(client, client_as, ids: Ids) -> None:
    assert client.get("/api/overview").status_code == 401
    alder = client_as("sam").get("/api/overview").json()
    copper = client_as("sam_copper").get("/api/overview").json()
    assert alder["greeting"]["merchant_name"] == "Alder & Loom" and copper["greeting"]["merchant_name"] == "Copper Finch Coffee"
    assert_scoped(ids, alder, ids.merchants["alder-loom"])
    assert_scoped(ids, copper, ids.merchants["copper-finch"])
    assert {p["id"] for p in alder["recent_payments"]}.isdisjoint({p["id"] for p in copper["recent_payments"]})
