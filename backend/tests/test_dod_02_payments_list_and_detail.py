"""Definition of Done 2: search, filter and paginate payments, open one, and the list agrees with the detail.

Every filter is cross-checked against SQL on the same database.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.tz import chicago_range
from tests.conftest import Ids, assert_scoped

LAST_30 = "period=last_30_days"


def sql_count(conn: sqlite3.Connection, merchant_id: str, extra: str, params: dict[str, object] | None = None) -> int:
    start, end = chicago_range(*_days())
    base = {"m": merchant_id, "start": start, "end": end, **(params or {})}
    return conn.execute(f"SELECT COUNT(*) FROM payment_summary ps WHERE ps.merchant_id = :m AND ps.created_at >= :start AND ps.created_at < :end {extra}", base).fetchone()[0]


def _days():
    from datetime import date

    return date(2026, 9, 6), date(2026, 10, 5)


def test_default_period_is_the_last_seven_chicago_days(client_as, ids: Ids) -> None:
    body = client_as("maya").get("/api/payments").json()
    assert body["period"] == {"preset": "last_7_days", "label": "Last 7 days", "from_date": "2026-09-29", "to_date": "2026-10-05", "range_label": "Sep 29 – Oct 5, 2026"}
    start, end = chicago_range(*[__import__("datetime").date.fromisoformat(d) for d in ("2026-09-29", "2026-10-05")])
    assert start == "2026-09-29T05:00:00Z" and end == "2026-10-06T05:00:00Z"
    for item in body["items"]:
        assert start <= item["created_at"] < end
    assert body["page"] == 1 and body["page_size"] == 25 and len(body["items"]) == 25
    assert_scoped(ids, body, ids.merchant("alder-loom"))


def test_total_matches_sql(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("maya").get(f"/api/payments?{LAST_30}").json()
    assert body["total"] == sql_count(seeded_conn, ids.merchant("alder-loom"), "")
    assert body["total"] > 2000


@pytest.mark.parametrize("status", ["succeeded", "failed", "pending", "partially_refunded", "refunded"])
def test_status_filter(client_as, seeded_conn: sqlite3.Connection, ids: Ids, status: str) -> None:
    body = client_as("maya").get(f"/api/payments?{LAST_30}&status={status}&page_size=100").json()
    assert body["total"] == sql_count(seeded_conn, ids.merchant("alder-loom"), "AND ps.status = :s", {"s": status})
    assert body["items"] and all(i["status"] == status for i in body["items"])


@pytest.mark.parametrize("channel", ["website", "mobile_app", "in_store"])
def test_channel_filter(client_as, seeded_conn: sqlite3.Connection, ids: Ids, channel: str) -> None:
    body = client_as("maya").get(f"/api/payments?{LAST_30}&channel={channel}&page_size=5").json()
    assert body["total"] == sql_count(seeded_conn, ids.merchant("alder-loom"), "AND ps.channel = :c", {"c": channel})
    assert all(i["channel"] == channel for i in body["items"])
    if channel == "in_store":
        assert all(i["location"] is not None for i in body["items"])
    else:
        assert all(i["location"] is None for i in body["items"])


def test_location_filter(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    location_id = ids.sample("alder-loom", "location_id")
    body = client_as("maya").get(f"/api/payments?{LAST_30}&location_id={location_id}&page_size=5").json()
    assert body["total"] == sql_count(seeded_conn, ids.merchant("alder-loom"), "AND ps.location_id = :l", {"l": location_id})
    assert body["total"] > 0 and all(i["location"]["id"] == location_id for i in body["items"])


def test_amount_range_filter_is_integer_cents(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("maya").get(f"/api/payments?{LAST_30}&amount_min_cents=10000&amount_max_cents=25000&page_size=100").json()
    assert body["total"] == sql_count(seeded_conn, ids.merchant("alder-loom"), "AND ps.amount_cents BETWEEN 10000 AND 25000")
    assert all(10000 <= i["amount_cents"] <= 25000 for i in body["items"])
    assert client_as("maya").get("/api/payments?amount_min_cents=12.50").status_code == 422


def test_search_by_order_reference_email_name_and_id(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("maya")
    by_ref = c.get(f"/api/payments?{LAST_30}&q=AL-11404").json()
    assert by_ref["total"] == 1 and by_ref["items"][0]["order_reference"] == "AL-11404"
    anchor_id = by_ref["items"][0]["id"]
    by_id = c.get(f"/api/payments?{LAST_30}&q={anchor_id}").json()
    assert [i["id"] for i in by_id["items"]] == [anchor_id]
    by_email = c.get(f"/api/payments?{LAST_30}&q=taylor.reed@example.com&page_size=50").json()
    expected = sql_count(seeded_conn, ids.merchant("alder-loom"), "AND ps.customer_email = 'taylor.reed@example.com'")
    assert by_email["total"] == expected >= 4
    by_name = c.get(f"/api/payments?{LAST_30}&q=Taylor%20Reed&page_size=50").json()
    assert by_name["total"] == expected
    assert all(i["customer"]["full_name"] == "Taylor Reed" for i in by_name["items"])


def test_search_escapes_like_wildcards(client_as, ids: Ids) -> None:
    c = client_as("maya")
    assert c.get(f"/api/payments?{LAST_30}&q=%25").json()["total"] == 0
    assert c.get(f"/api/payments?{LAST_30}&q=AL-1140_").json()["total"] == 0


def test_custom_period_uses_inclusive_chicago_dates(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("maya").get("/api/payments?from=2026-09-22&to=2026-09-22&page_size=100&sort=created_at&dir=asc").json()
    assert body["period"]["preset"] == "custom" and body["period"]["range_label"] == "Sep 22, 2026"
    start, end = "2026-09-22T05:00:00Z", "2026-09-23T05:00:00Z"
    assert body["total"] == seeded_conn.execute(
        "SELECT COUNT(*) FROM payment WHERE merchant_id = ? AND created_at >= ? AND created_at < ?", (ids.merchant("alder-loom"), start, end)
    ).fetchone()[0]
    assert body["items"][0]["created_at"] >= start
    c = client_as("maya")
    assert c.get("/api/payments?period=custom").status_code == 422
    assert c.get("/api/payments?from=2026-09-22&to=2026-09-21").status_code == 422
    assert c.get("/api/payments?from=not-a-date&to=2026-09-21").status_code == 422
    assert c.get("/api/payments?period=yesterday").status_code == 422


@pytest.mark.parametrize("sort,key", [("created_at", "created_at"), ("amount", "amount_cents"), ("order_reference", "order_reference")])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_whitelist_orders_the_page(client_as, sort: str, key: str, direction: str) -> None:
    body = client_as("maya").get(f"/api/payments?{LAST_30}&sort={sort}&dir={direction}&page_size=60").json()
    values = [i[key] for i in body["items"]]
    assert values == sorted(values, reverse=direction == "desc")


def test_unknown_sort_or_direction_is_422(client_as) -> None:
    c = client_as("maya")
    assert c.get("/api/payments?sort=amount_cents;DROP").status_code == 422
    assert c.get("/api/payments?dir=sideways").status_code == 422
    assert c.get("/api/payments?page=0").status_code == 422
    assert c.get("/api/payments?page_size=101").status_code == 422


def test_pagination_is_disjoint_stable_and_complete(client_as) -> None:
    c = client_as("maya")
    first = c.get(f"/api/payments?{LAST_30}&page=1&page_size=40").json()
    second = c.get(f"/api/payments?{LAST_30}&page=2&page_size=40").json()
    again = c.get(f"/api/payments?{LAST_30}&page=1&page_size=40").json()
    ids_1 = [i["id"] for i in first["items"]]
    ids_2 = [i["id"] for i in second["items"]]
    assert ids_1 == [i["id"] for i in again["items"]]
    assert not set(ids_1) & set(ids_2)
    assert len(ids_1) == len(ids_2) == 40
    big = c.get(f"/api/payments?{LAST_30}&page=1&page_size=80").json()
    assert [i["id"] for i in big["items"]] == ids_1 + ids_2
    last_page = (first["total"] + 39) // 40
    tail = c.get(f"/api/payments?{LAST_30}&page={last_page}&page_size=40").json()
    assert 0 < len(tail["items"]) <= 40
    assert c.get(f"/api/payments?{LAST_30}&page={last_page + 1}&page_size=40").json()["items"] == []


def test_list_fields_equal_detail_fields(client_as, ids: Ids) -> None:
    c = client_as("maya")
    body = c.get(f"/api/payments?{LAST_30}&page_size=12").json()
    assert body["items"]
    for item in body["items"]:
        detail = c.get(f"/api/payments/{item['id']}").json()
        for key in ("id", "order_reference", "created_at", "amount_cents", "currency", "status", "status_label", "channel", "channel_label",
                    "location", "customer", "method", "refunded_cents", "net_cents"):
            assert item[key] == detail[key], (item["id"], key)
        assert item["dispute_id"] == (detail["dispute"]["id"] if detail["dispute"] else None)
        assert_scoped(ids, detail, ids.merchant("alder-loom"))


def test_list_method_is_the_succeeded_attempt_else_the_latest(client_as) -> None:
    c = client_as("maya")
    anchor = c.get(f"/api/payments?{LAST_30}&q=AL-11404").json()["items"][0]
    assert anchor["method"]["label"] == "Mastercard •••• 8812"
    detail = c.get(f"/api/payments/{anchor['id']}").json()
    assert [a["method"]["card_last4"] for a in detail["attempts"]] == ["4242", "8812"]
    failed = c.get(f"/api/payments?{LAST_30}&status=failed&page_size=1").json()["items"][0]
    detail = c.get(f"/api/payments/{failed['id']}").json()
    assert failed["method"] == detail["attempts"][-1]["method"]


def test_every_role_with_payments_read_sees_only_its_merchant(client_as, ids: Ids) -> None:
    for persona, slug in (("daniel", "alder-loom"), ("jordan", "alder-loom"), ("sam", "alder-loom"), ("priya", "juniper-trail"), ("sam_copper", "copper-finch")):
        body = client_as(persona).get(f"/api/payments?{LAST_30}&page_size=50").json()
        assert body["total"] > 0
        assert_scoped(ids, body, ids.merchant(slug))
        assert all(i["order_reference"].startswith({"alder-loom": "AL-", "juniper-trail": "JT-", "copper-finch": "CF-"}[slug]) for i in body["items"])
