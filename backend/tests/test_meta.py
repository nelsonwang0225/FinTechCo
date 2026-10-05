"""GET /api/meta: labelled options and the merchant's locations, with no counts."""

from __future__ import annotations

from typing import Any

from tests.conftest import Ids, assert_scoped


def integers_in(payload: Any) -> list[int]:
    if isinstance(payload, bool):
        return []
    if isinstance(payload, int):
        return [payload]
    if isinstance(payload, dict):
        return [n for v in payload.values() for n in integers_in(v)]
    if isinstance(payload, list):
        return [n for v in payload for n in integers_in(v)]
    return []


def test_meta_has_options_and_scoped_locations(client_as, ids: Ids) -> None:
    body = client_as("maya").get("/api/meta").json()
    assert [o["value"] for o in body["channels"]] == ["website", "mobile_app", "in_store"]
    assert [o["value"] for o in body["payment_statuses"]] == ["succeeded", "pending", "failed", "partially_refunded", "refunded"]
    assert [o["value"] for o in body["attempt_outcomes"]] == ["succeeded", "failed", "pending"]
    assert [o["value"] for o in body["period_presets"]] == ["last_7_days", "last_30_days", "month_to_date", "custom"]
    assert body["default_period"] == "last_7_days"
    assert body["timezone"] == "America/Chicago"
    assert [loc["name"] for loc in body["locations"]] == ["Fulton Market", "Lincoln Park"]
    assert_scoped(ids, body, ids.merchant("alder-loom"))
    assert integers_in(body) == [], "meta must carry no counts"
    assert "failure_codes" not in body


def test_meta_locations_follow_the_session_merchant(client_as, ids: Ids) -> None:
    juniper = client_as("priya").get("/api/meta").json()
    assert [loc["name"] for loc in juniper["locations"]] == ["Flagship"]
    assert_scoped(ids, juniper, ids.merchant("juniper-trail"))
    copper = client_as("sam_copper").get("/api/meta").json()
    assert len(copper["locations"]) == 2
    assert_scoped(ids, copper, ids.merchant("copper-finch"))
