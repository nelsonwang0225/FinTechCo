"""GET /api/attempts: per-record outcomes with recorded reasons, filtered on the attempt's own timestamp."""

from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import Ids, assert_scoped

LAST_30 = "period=last_30_days"
START, END = "2026-09-06T05:00:00Z", "2026-10-06T05:00:00Z"


def count(conn: sqlite3.Connection, merchant_id: str, extra: str = "", params: dict[str, object] | None = None) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id WHERE a.merchant_id = :m AND a.created_at >= :s AND a.created_at < :e " + extra,
        {"m": merchant_id, "s": START, "e": END, **(params or {})},
    ).fetchone()[0]


def test_list_shape_has_total_and_period(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("maya").get(f"/api/attempts?{LAST_30}").json()
    assert set(body) == {"items", "page", "page_size", "total", "period"}
    assert body["total"] == count(seeded_conn, ids.merchant("alder-loom"))
    assert body["period"]["preset"] == "last_30_days"
    assert_scoped(ids, body, ids.merchant("alder-loom"))
    item = body["items"][0]
    assert set(item) == {"id", "payment_id", "attempt_number", "created_at", "completed_at", "outcome", "outcome_label", "failure_code", "failure_message",
                         "method", "order_reference", "amount_cents", "currency", "channel", "channel_label", "location", "customer"}


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "pending"])
def test_outcome_filter(client_as, seeded_conn: sqlite3.Connection, ids: Ids, outcome: str) -> None:
    body = client_as("maya").get(f"/api/attempts?{LAST_30}&outcome={outcome}&page_size=100").json()
    assert body["total"] == count(seeded_conn, ids.merchant("alder-loom"), "AND a.outcome = :o", {"o": outcome})
    assert body["items"]
    for item in body["items"]:
        assert item["outcome"] == outcome
        if outcome == "failed":
            assert item["failure_code"] and item["failure_message"]
        else:
            assert item["failure_code"] is None and item["failure_message"] is None
        if outcome == "pending":
            assert item["completed_at"] is None


@pytest.mark.parametrize("channel", ["website", "mobile_app", "in_store"])
def test_channel_and_location_filters(client_as, seeded_conn: sqlite3.Connection, ids: Ids, channel: str) -> None:
    body = client_as("maya").get(f"/api/attempts?{LAST_30}&channel={channel}&page_size=5").json()
    assert body["total"] == count(seeded_conn, ids.merchant("alder-loom"), "AND p.channel = :c", {"c": channel})
    assert all(i["channel"] == channel for i in body["items"])
    location_id = ids.sample("alder-loom", "location_id")
    body = client_as("maya").get(f"/api/attempts?{LAST_30}&location_id={location_id}&page_size=5").json()
    assert body["total"] == count(seeded_conn, ids.merchant("alder-loom"), "AND p.location_id = :l", {"l": location_id})


def test_period_filters_on_the_attempt_timestamp(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("maya").get("/api/attempts?from=2026-09-22&to=2026-09-22&page_size=100&sort=created_at&dir=asc").json()
    expected = seeded_conn.execute(
        "SELECT COUNT(*) FROM payment_attempt WHERE merchant_id = ? AND created_at >= '2026-09-22T05:00:00Z' AND created_at < '2026-09-23T05:00:00Z'",
        (ids.merchant("alder-loom"),),
    ).fetchone()[0]
    assert body["total"] == expected
    anchor_attempts = [i for i in body["items"] if i["order_reference"] == "AL-11404"]
    assert [a["attempt_number"] for a in anchor_attempts] == [1, 2]
    assert anchor_attempts[0]["failure_message"] == "Insufficient funds"


def test_search_and_sort(client_as) -> None:
    c = client_as("maya")
    body = c.get(f"/api/attempts?{LAST_30}&q=AL-11404").json()
    assert body["total"] == 2
    body = c.get(f"/api/attempts?{LAST_30}&sort=amount&dir=desc&page_size=30").json()
    amounts = [i["amount_cents"] for i in body["items"]]
    assert amounts == sorted(amounts, reverse=True)
    assert c.get("/api/attempts?sort=failure_code").status_code == 422
    assert c.get("/api/attempts?outcome=declined").status_code == 422


def test_other_merchants_see_their_own_attempts(client_as, ids: Ids) -> None:
    body = client_as("priya").get(f"/api/attempts?{LAST_30}&page_size=50").json()
    assert body["total"] > 0
    assert_scoped(ids, body, ids.merchant("juniper-trail"))
