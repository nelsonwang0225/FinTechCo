"""Customers: a merchant-scoped directory whose first-payment and recent-activity columns are derived, with search, sort and detail."""

from __future__ import annotations

import sqlite3

from tests.conftest import Ids, assert_scoped


def recompute(conn: sqlite3.Connection, customer_id: str) -> tuple[str | None, str | None]:
    first, last_payment = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM payment WHERE customer_id = ?", (customer_id,)).fetchone()
    last_refund = conn.execute(
        "SELECT MAX(r.created_at) FROM refund r JOIN payment p ON p.id = r.payment_id WHERE p.customer_id = ?", (customer_id,)
    ).fetchone()[0]
    candidates = [t for t in (last_payment, last_refund) if t]
    return first, (max(candidates) if candidates else None)


def test_directory_lists_every_customer_with_derived_activity(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchants["alder-loom"]
    body = client_as("maya").get("/api/customers?page_size=50").json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["total"] == seeded_conn.execute("SELECT COUNT(*) FROM customer WHERE merchant_id = ?", (merchant_id,)).fetchone()[0]
    assert len(body["items"]) == 50
    assert_scoped(ids, body, merchant_id)
    stamps = [c["last_activity_at"] for c in body["items"]]
    assert stamps == sorted(stamps, reverse=True)
    for c in body["items"][:10]:
        assert set(c) == {"id", "reference", "full_name", "email", "created_at", "first_payment_at", "last_activity_at"}
        assert c["email"].endswith("@example.com")
        assert (c["first_payment_at"], c["last_activity_at"]) == recompute(seeded_conn, c["id"])


def test_search_matches_name_email_reference_or_id(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("maya")
    by_name = c.get("/api/customers?q=ingrid").json()
    assert by_name["total"] >= 1 and all("ingrid" in (i["full_name"] + i["email"]).lower() for i in by_name["items"])
    sample = by_name["items"][0]
    assert [i["id"] for i in c.get(f"/api/customers?q={sample['reference']}").json()["items"]] == [sample["id"]]
    assert [i["id"] for i in c.get(f"/api/customers?q={sample['email']}").json()["items"]] == [sample["id"]]
    assert [i["id"] for i in c.get(f"/api/customers?q={sample['id']}").json()["items"]] == [sample["id"]]
    assert c.get("/api/customers?q=%25").json()["total"] == 0  # a literal percent sign matches nothing, not everything


def test_sort_is_whitelisted(client_as) -> None:
    c = client_as("maya")
    names = [i["full_name"] for i in c.get("/api/customers?sort=name&dir=asc&page_size=100").json()["items"]]
    assert names == sorted(names)
    assert c.get("/api/customers?sort=created_at").status_code == 422
    assert c.get("/api/customers?sort=full_name;DROP").status_code == 422
    assert c.get("/api/customers?page_size=101").status_code == 422


def test_detail_lists_the_customers_own_payments_and_refunds(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    c = client_as("maya")
    customer_id = seeded_conn.execute(
        "SELECT p.customer_id FROM refund r JOIN payment p ON p.id = r.payment_id WHERE r.merchant_id = ? AND p.customer_id IS NOT NULL LIMIT 1",
        (ids.merchants["alder-loom"],),
    ).fetchone()[0]
    body = c.get(f"/api/customers/{customer_id}").json()
    assert set(body) == {"id", "reference", "full_name", "email", "created_at", "first_payment_at", "last_activity_at", "payments", "refunds"}
    assert_scoped(ids, body, ids.merchants["alder-loom"])
    expected = [r[0] for r in seeded_conn.execute("SELECT id FROM payment WHERE customer_id = ? ORDER BY created_at DESC, id", (customer_id,))]
    assert [p["id"] for p in body["payments"]] == expected
    assert all(p["customer"]["id"] == customer_id for p in body["payments"])
    assert body["refunds"] and all(r["payment_id"] in expected for r in body["refunds"])
    assert all(set(r) >= {"id", "amount_cents", "reason_label", "status_label", "payment_id", "order_reference"} for r in body["refunds"])
    assert body["last_activity_at"] == max([p["created_at"] for p in body["payments"]] + [r["created_at"] for r in body["refunds"]])


def test_the_same_email_at_two_merchants_is_two_unrelated_customers(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    email, slugs = next(
        (r[0], r[1].split(","))
        for r in seeded_conn.execute(
            "SELECT c.email, GROUP_CONCAT(m.slug) FROM customer c JOIN merchant m ON m.id = c.merchant_id GROUP BY c.email HAVING COUNT(*) > 1 ORDER BY c.email LIMIT 1"
        )
    )
    assert "alder-loom" in slugs
    other_slug = next(s for s in slugs if s != "alder-loom")
    persona = {"juniper-trail": "priya", "copper-finch": "sam_copper"}[other_slug]
    alder = client_as("maya").get(f"/api/customers?q={email}").json()
    other = client_as(persona).get(f"/api/customers?q={email}").json()
    assert alder["total"] == 1 and other["total"] == 1
    assert alder["items"][0]["id"] != other["items"][0]["id"]
    alder_detail = client_as("maya").get(f"/api/customers/{alder['items'][0]['id']}").json()
    other_detail = client_as(persona).get(f"/api/customers/{other['items'][0]['id']}").json()
    assert_scoped(ids, alder_detail, ids.merchants["alder-loom"])
    assert_scoped(ids, other_detail, ids.merchants[other_slug])
    assert {p["id"] for p in alder_detail["payments"]}.isdisjoint({p["id"] for p in other_detail["payments"]})
    # Neither merchant can open the other's customer, even knowing the id.
    assert client_as("maya").get(f"/api/customers/{other['items'][0]['id']}").status_code == 404
    assert client_as(persona).get(f"/api/customers/{alder['items'][0]['id']}").status_code == 404


def test_permissions(client, client_as, ids: Ids) -> None:
    customer_id = ids.sample("alder-loom", "customer_id")
    assert client.get("/api/customers").status_code == 401
    assert client_as("daniel").get("/api/customers").status_code == 403
    assert client_as("daniel").get(f"/api/customers/{customer_id}").status_code == 403
    for persona in ("maya", "jordan", "sam"):
        assert client_as(persona).get(f"/api/customers/{customer_id}").status_code == 200, persona
