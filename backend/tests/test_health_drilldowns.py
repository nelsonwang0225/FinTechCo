"""Payment Health drill-downs: every linked figure lands on a list whose count (and value) is the same number.

Each link on the page is a Payments or Attempts list query built from the Payment Health scope. These tests make the
same queries the frontend links make (see frontend/src/lib/healthScope.ts) and pin the seeded figures for Alder & Loom,
so a change to the rule, the lists or the seed that breaks parity shows up here. They also follow one unresolved payment
through detail, a note and the export, and check another merchant sees none of it.
"""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from tests.conftest import Ids, assert_scoped

LAST_7 = "period=last_7_days"
LAST_7_MOBILE = "period=last_7_days&channel=mobile_app"
OCT_1_2_MOBILE = "period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app"

# scope -> (failed attempts, issuer_unavailable attempts, unresolved payments, unresolved cents, mobile failed attempts)
PINNED: dict[str, tuple[int, int, int, int, int]] = {
    LAST_7: (90, 32, 28, 762273, 52),
    LAST_7_MOBILE: (52, 29, 16, 481133, 52),
    OCT_1_2_MOBILE: (42, 29, 12, 422811, 42),
}


def get_json(c: TestClient, path: str) -> dict:
    r = c.get(path)
    assert r.status_code == 200, r.text
    return r.json()


def all_pages(c: TestClient, path: str) -> list[dict]:
    """Every item of a list endpoint, across pages."""
    items: list[dict] = []
    page = 1
    while True:
        body = get_json(c, f"{path}&page_size=100&page={page}")
        items.extend(body["items"])
        if len(items) >= body["total"]:
            return items
        page += 1


def csv_rows(c: TestClient, path: str) -> list[dict[str, str]]:
    r = c.get(path)
    assert r.status_code == 200, r.text
    return list(csv.DictReader(io.StringIO(r.text)))


@pytest.mark.parametrize("scope", list(PINNED))
def test_failed_attempts_kpi_lands_on_the_same_count(client_as, scope: str) -> None:
    maya = client_as("maya")
    failed, *_ = PINNED[scope]
    health = get_json(maya, f"/api/payment-health?{scope}")
    assert health["scope"]["period"]["failed"] == failed
    assert get_json(maya, f"/api/attempts?{scope}&outcome=failed")["total"] == failed


@pytest.mark.parametrize("scope", list(PINNED))
def test_each_channel_row_lands_on_its_failed_attempts(client_as, scope: str) -> None:
    maya = client_as("maya")
    *_, mobile_failed = PINNED[scope]
    health = get_json(maya, f"/api/payment-health?{scope}")
    period = scope.replace("&channel=mobile_app", "")
    by_channel = {c["channel"]: c for c in health["channels"]}
    assert by_channel["mobile_app"]["status"] == "degraded"
    assert by_channel["mobile_app"]["period"]["failed"] == mobile_failed
    assert [c for c, row in by_channel.items() if row["status"] == "degraded"] == ["mobile_app"]
    assert health["attention"]["degraded_channels"] == ["mobile_app"]
    for channel, row in by_channel.items():
        assert get_json(maya, f"/api/attempts?{period}&channel={channel}&outcome=failed")["total"] == row["period"]["failed"], channel


@pytest.mark.parametrize("scope", list(PINNED))
def test_each_signal_lands_on_its_attempts(client_as, scope: str) -> None:
    maya = client_as("maya")
    _, issuer, *_ = PINNED[scope]
    signals = get_json(maya, f"/api/payment-health?{scope}")["failure_signals"]["items"]
    assert {s["failure_code"]: s["count"] for s in signals}["issuer_unavailable"] == issuer
    for s in signals:
        assert get_json(maya, f"/api/attempts?{scope}&outcome=failed&failure_code={s['failure_code']}")["total"] == s["count"], s["failure_code"]


@pytest.mark.parametrize("scope", list(PINNED))
def test_unresolved_count_and_value_land_on_the_same_payments(client_as, scope: str) -> None:
    maya = client_as("maya")
    _, _, unresolved, unresolved_cents, _ = PINNED[scope]
    health = get_json(maya, f"/api/payment-health?{scope}")
    assert health["recovery"]["unresolved"] == health["unresolved_payments"]["total"] == unresolved
    assert health["recovery"]["unresolved_cents"] == unresolved_cents

    listed = get_json(maya, f"/api/payments?{scope}&status=failed")
    assert listed["total"] == unresolved
    assert listed["total_amount_cents"] == unresolved_cents and listed["currency"] == "USD"
    items = all_pages(maya, f"/api/payments?{scope}&status=failed")
    assert sum(p["amount_cents"] for p in items) == unresolved_cents
    # The first five on Payment Health are members of the same set.
    assert {p["id"] for p in health["unresolved_payments"]["items"]} <= {p["id"] for p in items}


def test_list_total_amount_sums_every_match_not_one_page(client_as) -> None:
    maya = client_as("maya")
    body = get_json(maya, "/api/payments?period=last_30_days&page_size=5")
    assert len(body["items"]) == 5 and body["total"] > 5
    expected = sum(p["amount_cents"] for p in all_pages(maya, "/api/payments?period=last_30_days"))
    assert body["total_amount_cents"] == expected
    empty = get_json(maya, "/api/payments?period=last_7_days&q=no-such-order-zzz")
    assert empty["total"] == 0 and empty["total_amount_cents"] == 0


@pytest.mark.parametrize("scope", list(PINNED))
def test_export_of_the_unresolved_list_is_exactly_the_unresolved_set(client_as, scope: str) -> None:
    maya = client_as("maya")
    _, _, unresolved, unresolved_cents, _ = PINNED[scope]
    listed = {p["id"] for p in all_pages(maya, f"/api/payments?{scope}&status=failed")}
    rows = csv_rows(maya, f"/api/reports/payments.csv?{scope}&status=failed")
    assert len(rows) == unresolved
    assert {r["payment_id"] for r in rows} == listed
    assert sum(int(r["amount_cents"]) for r in rows) == unresolved_cents
    assert {r["status"] for r in rows} == {"failed"}


def test_the_export_is_recorded_as_activity(client_as) -> None:
    jordan = client_as("jordan")  # settings:read, to see the activity list; the export itself needs reports:operational
    jordan.get(f"/api/reports/payments.csv?{OCT_1_2_MOBILE}&status=failed")
    activity = get_json(jordan, "/api/settings/activity")
    assert activity["items"][0]["kind"] == "export"


def test_unresolved_payment_detail_and_note_from_the_flow(client_as, ids: Ids) -> None:
    maya = client_as("maya")
    alder = ids.merchant("alder-loom")
    first = get_json(maya, f"/api/payment-health?{OCT_1_2_MOBILE}")["unresolved_payments"]["items"][0]
    detail = get_json(maya, f"/api/payments/{first['id']}")
    assert detail["status"] == "failed"
    assert len(detail["attempts"]) == first["attempt_count"]
    assert all(a["outcome"] == "failed" and a["failure_code"] for a in detail["attempts"])
    assert detail["attempts"][-1]["failure_code"] == first["last_failure_code"]

    body = "Reviewed after mobile payment incident. Customer has not successfully retried."
    r = maya.post(f"/api/payments/{first['id']}/notes", json={"body": body})
    assert r.status_code == 201, r.text
    note_id = r.json()["id"]
    after = get_json(maya, f"/api/payments/{first['id']}")
    assert after["notes"][-1]["id"] == note_id and after["notes"][-1]["body"] == body
    assert [e["upcoming"] for e in after["timeline"] if e["ref_id"] == note_id] == [False]
    assert_scoped(ids, {k: v for k, v in after.items() if k not in ("notes", "timeline")}, alder)

    # Another merchant: no record, no note, no write.
    priya = client_as("priya")
    assert priya.get(f"/api/payments/{first['id']}").status_code == 404
    assert priya.post(f"/api/payments/{first['id']}/notes", json={"body": "nope"}).status_code == 404
    assert note_id not in str(get_json(priya, "/api/payments?period=last_30_days"))


@pytest.mark.parametrize("scope", list(PINNED))
def test_another_merchant_never_sees_alder_records_through_the_links(client_as, ids: Ids, scope: str) -> None:
    priya = client_as("priya")
    juniper = ids.merchant("juniper-trail")
    for path in (
        f"/api/payments?{scope}&status=failed",
        f"/api/attempts?{scope}&outcome=failed",
        f"/api/attempts?{scope}&outcome=failed&failure_code=issuer_unavailable",
        f"/api/payment-health?{scope}",
    ):
        assert_scoped(ids, get_json(priya, path), juniper)
    for row in csv_rows(priya, f"/api/reports/payments.csv?{scope}&status=failed"):
        assert ids.owner_of[row["payment_id"]] == juniper
