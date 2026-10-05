"""Build-time check: no GET response, as any role, carries a key that names an aggregate over attempt outcomes.

Every JSON GET route is called as every persona with the merchant's own sample ids; the keys of every response are
walked and matched against the vocabulary of success/failure summaries, rates, trends and health indicators.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import FastAPI

from tests.conftest import PERSONAS, Ids, api_routes, route_permission

FORBIDDEN_KEY = re.compile(
    r"rate|ratio|percent|share|health|trend|score|breakdown|by_outcome|by_failure|by_reason|outcome_count|failure_count|success_count"
    r"|succeeded_count|failed_count|declin|approval|authori[sz]ation",
    re.IGNORECASE,
)


def walk(payload: Any, path: str = "$") -> list[str]:
    keys: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.append(f"{path}.{key}")
            keys.extend(walk(value, f"{path}.{key}"))
    elif isinstance(payload, list):
        for value in payload:
            keys.extend(walk(value, f"{path}[]"))
    return keys


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_no_get_response_carries_an_outcome_aggregate_key(app: FastAPI, client_as, ids: Ids, persona: str) -> None:
    c = client_as(persona)
    slug = PERSONAS[persona][1]
    hits: list[str] = []
    checked = 0
    for route in api_routes(app):
        if "GET" not in route.methods or route.response_model is None or route.path.startswith("/api/dev"):
            continue
        path = route.path
        for name, value in ids.samples[slug].items():
            path = path.replace("{" + name + "}", value)
        r = c.get(path)
        if r.status_code != 200:
            continue
        checked += 1
        for key in walk(r.json()):
            leaf = key.rsplit(".", 1)[-1]
            if FORBIDDEN_KEY.search(leaf):
                hits.append(f"{path}: {key}")
    assert checked > 0
    assert not hits, "\n".join(hits)


def test_every_guarded_get_route_was_reachable_by_some_persona(app: FastAPI, client_as, ids: Ids) -> None:
    unreached = []
    for route in api_routes(app):
        if "GET" not in route.methods or route_permission(route) is None:
            continue
        reached = False
        for persona in PERSONAS:
            slug = PERSONAS[persona][1]
            path = route.path
            for name, value in ids.samples[slug].items():
                path = path.replace("{" + name + "}", value)
            if client_as(persona).get(path).status_code == 200:
                reached = True
                break
        if not reached:
            unreached.append(route.path)
    assert not unreached, unreached
