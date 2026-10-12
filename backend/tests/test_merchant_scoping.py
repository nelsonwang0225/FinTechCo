"""Another merchant's record requested by ID is denied by the backend (404, never data).

Each case uses a persona that holds the permission, so the check reaches the merchant scope. A new resource
route appends its cases to CASES.
"""

from __future__ import annotations

import pytest

from app.core import clock, periods
from tests.conftest import Ids, assert_scoped

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


def test_payment_health_is_scoped_to_the_session_merchant(client_as, ids: Ids, seeded_conn) -> None:
    """A collection endpoint with no ids: each merchant's aggregates equal SQL over its own rows only."""
    p = periods.resolve("last_30_days", clock.now(seeded_conn))
    seen = {}
    for persona, slug in (("maya", "alder-loom"), ("priya", "juniper-trail"), ("sam_copper", "copper-finch")):
        body = client_as(persona).get("/api/payment-health?period=last_30_days").json()
        merchant_id = ids.merchant(slug)
        expected = dict(seeded_conn.execute(
            "SELECT outcome, COUNT(*) FROM payment_attempt WHERE merchant_id = ? AND created_at >= ? AND created_at < ? GROUP BY outcome",
            (merchant_id, p.start, p.end),
        ).fetchall())
        s = body["summary"]
        assert (s["succeeded"], s["failed"], s["pending"]) == (expected.get("succeeded", 0), expected.get("failed", 0), expected.get("pending", 0))
        affected = seeded_conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount_cents), 0) FROM payment p WHERE p.merchant_id = ? AND p.created_at >= ? AND p.created_at < ? "
            "AND EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'failed')",
            (merchant_id, p.start, p.end),
        ).fetchone()
        assert (body["recovery"]["affected"]["payments"], body["recovery"]["affected"]["amount_cents"]) == tuple(affected)
        assert_scoped(ids, body, merchant_id)
        seen[slug] = (s["succeeded"], s["failed"], body["recovery"]["affected"]["amount_cents"])
    assert len(set(seen.values())) == 3, seen
