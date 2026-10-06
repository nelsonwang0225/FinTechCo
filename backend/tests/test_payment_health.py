"""Payment Health: the Oct 1-2 app-checkout incident, reconciliation with the Attempts and Payments lists, low-volume
and empty periods, and merchant isolation. Every number is checked against the API lists or independent SQL."""

from __future__ import annotations

import sqlite3

import pytest

from app.core.tz import chicago_range
from tests.conftest import PERSONAS, Ids, assert_scoped

INCIDENT = "period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app"


def health(client, query: str = "") -> dict:
    r = client.get(f"/api/payment-health{'?' + query if query else ''}")
    assert r.status_code == 200, r.text
    return r.json()


def by_channel(body: dict) -> dict[str, dict]:
    return {c["channel"]: c for c in body["channels"]}


def sql_outcomes(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> dict[str, int]:
    clause = " AND p.channel = ?" if channel else ""
    params: tuple = (merchant_id, start, end, channel) if channel else (merchant_id, start, end)
    rows = conn.execute(
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id "
        f"WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ?{clause} GROUP BY a.outcome",
        params,
    ).fetchall()
    counts = {"succeeded": 0, "failed": 0, "pending": 0}
    counts.update({r[0]: r[1] for r in rows})
    return counts


def test_the_app_checkout_incident_is_degraded_with_its_recorded_numbers(client_as) -> None:
    body = health(client_as("maya"), INCIDENT)
    k = body["kpis"]
    assert (k["succeeded"], k["failed"], k["pending"], k["completed"]) == (53, 42, 0, 95)
    assert k["rate_bp"] == 5579
    assert (k["baseline_completed"], k["baseline_rate_bp"]) == (679, 9087)
    assert body["baseline"] == {"from_date": "2026-09-01", "to_date": "2026-09-30", "range_label": "Sep 1 – Sep 30, 2026"}
    mobile = by_channel(body)["mobile_app"]
    assert (mobile["evaluation"], mobile["baseline_succeeded"], mobile["baseline_failed"]) == ("degraded", 617, 62)
    assert body["summary"]["state"] == "degraded"
    assert [c["channel"] for c in body["summary"]["degraded"]] == ["mobile_app"]
    assert "Mobile app is degraded: 55.8% success vs 90.9% baseline, 42 failed attempts." in body["summary"]["message"]

    signals = body["failure_signals"]
    assert signals[0] == {"code": "issuer_unavailable", "label": "Issuer unavailable", "count": 29}
    assert sum(s["count"] for s in signals) == k["failed"]

    assert (k["affected_payments"], k["recovered_payments"], k["unresolved_payments"], k["awaiting_retry_payments"]) == (38, 26, 12, 0)
    assert k["affected_cents"] == 896010
    assert k["currency"] == "USD"


def test_unresolved_count_is_the_payments_list_total_for_status_failed(client_as) -> None:
    maya = client_as("maya")
    for query in (INCIDENT, "period=last_7_days", "period=last_7_days&channel=website", "period=month_to_date&channel=in_store"):
        body = health(maya, query)
        listing = maya.get(f"/api/payments?{query}&status=failed&page_size=1").json()
        assert body["kpis"]["unresolved_payments"] == listing["total"], query


def test_attempt_counts_reconcile_with_the_attempts_list(client_as) -> None:
    maya = client_as("maya")
    for query in (INCIDENT, "period=last_7_days", "period=last_7_days&channel=in_store"):
        k = health(maya, query)["kpis"]
        for outcome in ("succeeded", "failed", "pending"):
            total = maya.get(f"/api/attempts?{query}&outcome={outcome}&page_size=1").json()["total"]
            assert k[outcome] == total, (query, outcome)


def test_recovery_counts_each_payment_once_with_its_amount_once(client_as, ids: Ids, seeded_conn: sqlite3.Connection) -> None:
    body = health(client_as("maya"), INCIDENT)
    start, end = "2026-10-01T05:00:00Z", "2026-10-03T05:00:00Z"
    rows = seeded_conn.execute(
        "SELECT p.id, p.amount_cents, SUM(a.outcome = 'failed') AS failed, SUM(a.outcome = 'succeeded') AS succeeded "
        "FROM payment p JOIN payment_attempt a ON a.payment_id = p.id "
        "WHERE p.merchant_id = ? AND p.channel = 'mobile_app' AND p.created_at >= ? AND p.created_at < ? GROUP BY p.id HAVING failed > 0",
        (ids.merchant("alder-loom"), start, end),
    ).fetchall()
    assert len(rows) == body["kpis"]["affected_payments"]
    assert sum(r["amount_cents"] for r in rows) == body["kpis"]["affected_cents"]
    assert sum(1 for r in rows if r["succeeded"]) == body["kpis"]["recovered_payments"]
    # Payments declined more than once and then recovered are still one recovered payment each.
    assert any(r["failed"] >= 2 and r["succeeded"] for r in rows)


def test_last_seven_days_flags_only_the_app_channel(client_as) -> None:
    body = health(client_as("maya"))
    assert body["period"]["preset"] == "last_7_days"
    channels = by_channel(body)
    assert channels["mobile_app"]["rate_bp"] == 7204 and channels["mobile_app"]["baseline_rate_bp"] == 9079
    assert channels["mobile_app"]["evaluation"] == "degraded"
    assert channels["website"]["evaluation"] == "within_range"
    assert channels["in_store"]["evaluation"] == "within_range"  # a 4.8-point drop stays below the rule
    assert [c["channel"] for c in body["summary"]["degraded"]] == ["mobile_app"]


def test_low_volume_channels_are_not_evaluated(client_as) -> None:
    body = health(client_as("sam_copper"))
    channels = by_channel(body)
    assert channels["mobile_app"]["evaluation"] == "insufficient_volume"
    assert channels["website"]["evaluation"] == "insufficient_volume"
    assert channels["in_store"]["evaluation"] == "within_range"  # a 5.9-point drop is ordinary variation
    assert body["summary"]["state"] == "no_degradation"
    assert body["summary"]["message"] == "No significant degradation detected in In store. Website and Mobile app: insufficient volume to evaluate."


def test_an_empty_baseline_draws_no_conclusion(client_as) -> None:
    body = health(client_as("maya"), "period=last_30_days")
    assert body["baseline"]["to_date"] == "2026-09-05"
    assert all(c["evaluation"] == "insufficient_volume" for c in body["channels"])
    assert body["summary"]["state"] == "insufficient_volume"
    assert body["summary"]["degraded"] == []
    assert "degraded" not in body["summary"]["message"]


def test_a_period_without_attempts_has_no_rate(client_as) -> None:
    body = health(client_as("maya"), "period=custom&from=2026-08-01&to=2026-08-07")
    k = body["kpis"]
    assert (k["completed"], k["pending"], k["rate_bp"], k["delta_bp"]) == (0, 0, None, None)
    assert (k["affected_payments"], k["affected_cents"]) == (0, 0)
    assert body["channels"] == [] and body["failure_signals"] == []
    assert body["summary"]["state"] == "insufficient_volume"


def test_a_pending_only_period_reports_pending_and_no_rate(client_as) -> None:
    body = health(client_as("sam_copper"), "period=custom&from=2026-10-05&to=2026-10-05&channel=website")
    k = body["kpis"]
    assert (k["completed"], k["pending"], k["rate_bp"]) == (0, 2, None)
    assert by_channel(body)["website"]["evaluation"] == "insufficient_volume"


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper", "daniel", "jordan", "sam"])
def test_every_role_with_payments_read_gets_only_its_own_merchant(client_as, ids: Ids, persona: str) -> None:
    body = health(client_as(persona), "period=last_7_days")
    assert_scoped(ids, body, ids.merchant(PERSONAS[persona][1]))


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
def test_counts_are_computed_from_the_merchants_own_attempts(client_as, ids: Ids, seeded_conn: sqlite3.Connection, persona: str) -> None:
    from datetime import date

    merchant_id = ids.merchant(PERSONAS[persona][1])
    body = health(client_as(persona), "period=last_7_days")
    start, end = chicago_range(date.fromisoformat(body["period"]["from_date"]), date.fromisoformat(body["period"]["to_date"]))
    expected = sql_outcomes(seeded_conn, merchant_id, start, end)
    assert {o: body["kpis"][o] for o in expected} == expected
    for c in body["channels"]:
        own = sql_outcomes(seeded_conn, merchant_id, start, end, c["channel"])
        assert (c["succeeded"], c["failed"], c["pending"]) == (own["succeeded"], own["failed"], own["pending"])


def test_another_merchants_incident_is_invisible(client_as, ids: Ids) -> None:
    priya = client_as("priya")
    body = health(priya, INCIDENT)
    assert body["kpis"]["completed"] == 0 and body["kpis"]["affected_payments"] == 0
    assert "mobile_app" not in by_channel(body)
    # A merchant id in the query string is ignored: the session decides the merchant.
    spoofed = health(priya, f"{INCIDENT}&merchant_id={ids.merchant('alder-loom')}")
    assert spoofed == body


def test_requires_a_session(client) -> None:
    r = client.get("/api/payment-health")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_rejects_unknown_channels_and_bad_periods(client_as) -> None:
    maya = client_as("maya")
    assert maya.get("/api/payment-health?channel=fax").status_code == 422
    assert maya.get("/api/payment-health?period=custom&from=2026-10-05&to=2026-10-01").status_code == 422
