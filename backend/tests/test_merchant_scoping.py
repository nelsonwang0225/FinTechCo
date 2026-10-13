"""Another merchant's record requested by ID is denied by the backend (404, never data).

Each case uses a persona that holds the permission, so the check reaches the merchant scope. A new resource
route appends its cases to CASES.
"""

from __future__ import annotations

import sqlite3

import pytest

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


# Collection and summary endpoints have no id to request, so their scope is checked by content: each merchant's figures
# are its own, ids in the payload belong to it, and another merchant's rows changing leaves them untouched.

APP_WINDOW = "/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02"


@pytest.mark.parametrize("persona,slug", [("maya", "alder-loom"), ("priya", "juniper-trail"), ("sam_copper", "copper-finch")])
def test_payment_health_is_computed_from_the_merchants_own_attempts(client_as, ids: Ids, seeded_conn, persona: str, slug: str) -> None:
    body = client_as(persona).get(APP_WINDOW).json()
    merchant_id = ids.merchant(slug)
    expected = seeded_conn.execute(
        "SELECT COUNT(*) FROM payment_attempt WHERE merchant_id = ? AND created_at >= '2026-10-01T05:00:00Z' AND created_at < '2026-10-03T05:00:00Z'",
        (merchant_id,),
    ).fetchone()[0]
    summary = body["summary"]["period"]
    assert summary["completed"] + summary["pending"] == expected
    assert_scoped(ids, body, merchant_id)
    if slug != "alder-loom":
        assert all(s["failure_code"] != "issuer_unavailable" or s["failed_attempts"] < 5 for s in body["failure_signals"]), "no Alder spike"


def test_payment_health_unresolved_payments_never_cross_merchants(client_as, ids: Ids) -> None:
    seen: dict[str, set[str]] = {}
    for persona, slug in (("maya", "alder-loom"), ("priya", "juniper-trail"), ("sam_copper", "copper-finch")):
        body = client_as(persona).get("/api/payment-health?period=last_30_days").json()
        seen[slug] = {i["id"] for i in body["unresolved"]["items"]}
        assert all(ids.owner_of[i] == ids.merchant(slug) for i in seen[slug])
    assert not (seen["alder-loom"] & seen["juniper-trail"]) and not (seen["alder-loom"] & seen["copper-finch"])


def test_another_merchants_failures_do_not_move_payment_health(client_as, ids: Ids, db_copy) -> None:
    maya = client_as("maya")
    before = maya.get(APP_WINDOW).json()
    conn = sqlite3.connect(db_copy)
    changed = conn.execute(
        "UPDATE payment_attempt SET outcome = 'failed', failure_code = 'issuer_unavailable', failure_message = 'Issuer unavailable' "
        "WHERE merchant_id = ? AND outcome = 'succeeded' AND created_at >= '2026-10-01T05:00:00Z' AND created_at < '2026-10-03T05:00:00Z'",
        (ids.merchant("juniper-trail"),),
    ).rowcount
    conn.commit()
    conn.close()
    assert changed > 0
    assert maya.get(APP_WINDOW).json() == before
    priya = client_as("priya").get(APP_WINDOW).json()
    assert priya["summary"]["period"]["succeeded"] == 0, "the change is visible to its own merchant"


def test_failure_code_filtered_attempts_stay_in_the_merchant(client_as, ids: Ids) -> None:
    for persona, slug in (("maya", "alder-loom"), ("priya", "juniper-trail")):
        body = client_as(persona).get("/api/attempts?period=last_30_days&failure_code=insufficient_funds&page_size=100").json()
        assert body["total"] > 0
        assert_scoped(ids, body, ids.merchant(slug))
