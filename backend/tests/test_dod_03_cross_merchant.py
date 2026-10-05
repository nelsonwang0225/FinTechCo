"""Definition of Done 3: another merchant's record requested by ID is denied by the backend (404, never data).

Each case uses a persona that holds the permission, so the check reaches the merchant scope. Later phases
append their resource routes to CASES.
"""

from __future__ import annotations

import pytest

from tests.conftest import Ids

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
