"""Another merchant's record requested by ID is denied by the backend (404, never data).

Each case uses a persona that holds the permission, so the check reaches the merchant scope. A new resource
route appends its cases to CASES.
"""

from __future__ import annotations

import pytest

from tests.conftest import PERSONAS, Ids, assert_scoped

# (persona, route template, slug whose id is foreign to that persona, path parameter)
CASES: list[tuple[str, str, str, str]] = [
    ("maya", "/api/payments/{id}", "juniper-trail", "payment_id"),
    ("priya", "/api/payments/{id}", "alder-loom", "payment_id"),
    ("sam_copper", "/api/payments/{id}", "alder-loom", "payment_id"),
    ("sam_copper", "/api/payouts/{id}", "alder-loom", "payout_id"),
    ("daniel", "/api/payouts/{id}", "juniper-trail", "payout_id"),
    ("daniel", "/api/payouts/{id}/export.csv", "juniper-trail", "payout_id"),
    ("maya", "/api/customers/{id}", "juniper-trail", "customer_id"),
    ("priya", "/api/customers/{id}", "alder-loom", "customer_id"),
    ("sam_copper", "/api/customers/{id}", "alder-loom", "customer_id"),
    ("maya", "/api/disputes/{id}", "juniper-trail", "dispute_id"),
    ("priya", "/api/disputes/{id}", "alder-loom", "dispute_id"),
    ("sam_copper", "/api/disputes/{id}", "alder-loom", "dispute_id"),
]


@pytest.mark.parametrize("persona,template,foreign_slug,param", CASES)
def test_foreign_record_by_id_is_404(client_as, ids: Ids, persona: str, template: str, foreign_slug: str, param: str) -> None:
    foreign_id = ids.sample(foreign_slug, param)
    assert ids.owner_of[foreign_id] == ids.merchant(foreign_slug)
    r = client_as(persona).get(template.replace("{id}", foreign_id))
    assert r.status_code == 404, r.text
    assert r.json() == {"error": {"code": "not_found", "message": r.json()["error"]["message"]}}
    assert foreign_id not in r.text


def test_foreign_payment_note_is_404_not_written(client_as, ids: Ids, seeded_conn) -> None:
    foreign_id = ids.sample("juniper-trail", "payment_id")
    r = client_as("maya").post(f"/api/payments/{foreign_id}/notes", json={"body": "should not land"})
    assert r.status_code == 404
    assert client_as("priya").get(f"/api/payments/{foreign_id}").json()["notes"] == [] or all(
        n["body"] != "should not land" for n in client_as("priya").get(f"/api/payments/{foreign_id}").json()["notes"]
    )


def test_foreign_dispute_note_is_404_not_written(client_as, ids: Ids) -> None:
    foreign_id = ids.sample("juniper-trail", "dispute_id")
    assert client_as("maya").post(f"/api/disputes/{foreign_id}/notes", json={"body": "should not land"}).status_code == 404
    assert all(n["body"] != "should not land" for n in client_as("priya").get(f"/api/disputes/{foreign_id}").json()["notes"])


def test_the_same_id_is_found_by_its_own_merchant(client_as, ids: Ids) -> None:
    own = ids.sample("juniper-trail", "payment_id")
    assert client_as("priya").get(f"/api/payments/{own}").status_code == 200
    assert client_as("maya").get(f"/api/payments/{own}").status_code == 404


def _health_oracle(conn, merchant_id: str | None) -> tuple[int, int]:
    """(attempts, affected payments) for the last 7 days, for one merchant or, with None, for every merchant."""
    scope = "AND a.merchant_id = :m" if merchant_id else ""
    params = {"m": merchant_id, "s": "2026-09-29T05:00:00Z", "e": "2026-10-06T05:00:00Z"}
    attempts = conn.execute(f"SELECT COUNT(*) FROM payment_attempt a WHERE a.created_at >= :s AND a.created_at < :e {scope}", params).fetchone()[0]
    affected = conn.execute(
        "SELECT COUNT(*) FROM payment p WHERE p.created_at >= :s AND p.created_at < :e "
        + ("AND p.merchant_id = :m " if merchant_id else "")
        + "AND EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id AND a.merchant_id = p.merchant_id AND a.outcome = 'failed')",
        params,
    ).fetchone()[0]
    return attempts, affected


@pytest.mark.parametrize("first,second", [("sam", "sam_copper"), ("maya", "priya")])
def test_payment_health_is_scoped_to_the_session_merchant(client_as, ids: Ids, seeded_conn, first: str, second: str) -> None:
    """An aggregate leaks by blending, not by foreign ids, so the figures are checked against each merchant's own rows."""
    bodies = {}
    for persona in (first, second):
        merchant_id = ids.merchants[PERSONAS[persona][1]]
        body = client_as(persona).get("/api/payment-health?period=last_7_days").json()
        assert_scoped(ids, body, merchant_id)
        attempts, affected = _health_oracle(seeded_conn, merchant_id)
        period = body["summary"]["period"]
        assert period["completed"] + period["pending"] == attempts
        assert body["recovery"]["affected_payments"] == affected
        assert all(ids.owner_of[p["id"]] == merchant_id for p in body["unresolved_payments"]["items"])
        bodies[persona] = body
    everyone = _health_oracle(seeded_conn, None)
    for body in bodies.values():
        period = body["summary"]["period"]
        assert period["completed"] + period["pending"] < everyone[0]
        assert body["recovery"]["affected_payments"] < everyone[1]
    first_ids = {p["id"] for p in bodies[first]["unresolved_payments"]["items"]}
    second_ids = {p["id"] for p in bodies[second]["unresolved_payments"]["items"]}
    assert first_ids.isdisjoint(second_ids)
    # Only Alder & Loom's app checkout is degraded; nobody else inherits it.
    for persona, body in bodies.items():
        degraded = [c["channel"] for c in body["channels"] if c["assessment"] == "degraded"]
        assert degraded == (["mobile_app"] if PERSONAS[persona][1] == "alder-loom" else []), persona


def test_payment_health_ignores_a_merchant_in_the_query(client_as, ids: Ids) -> None:
    own = client_as("priya").get("/api/payment-health?period=last_7_days").json()
    spoofed = client_as("priya").get(f"/api/payment-health?period=last_7_days&merchant_id={ids.merchant('alder-loom')}").json()
    assert spoofed == own
