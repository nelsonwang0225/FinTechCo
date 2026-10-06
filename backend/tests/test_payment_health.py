"""Payment Health (PH-142): attempt performance, failure signals and recovery recomputed with independent SQL, retries
counted once per payment, and every figure scoped to the session's merchant."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

import pytest

from app.core.tz import chicago_range, parse_iso
from tests.conftest import PERSONAS, Ids, assert_scoped

INCIDENT_QUERY = "period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app"
INCIDENT_FROM, INCIDENT_TO = date(2026, 10, 1), date(2026, 10, 2)


def health(client: Any, query: str) -> dict[str, Any]:
    r = client.get(f"/api/payment-health?{query}")
    assert r.status_code == 200, r.text
    return r.json()


def expected(conn: sqlite3.Connection, merchant_id: str, from_day: date, to_day: date, channel: str | None) -> dict[str, Any]:
    """The same figures computed straight from payment_attempt and payment, without the module's queries or the view."""
    start, end = chicago_range(from_day, to_day)
    chan_sql, chan_params = ("AND p.channel = ?", [channel]) if channel else ("", [])
    outcomes = dict(conn.execute(
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        f"WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ? {chan_sql} GROUP BY a.outcome",
        [merchant_id, start, end, *chan_params],
    ).fetchall())
    signals = conn.execute(
        "SELECT a.failure_code, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        f"WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ? AND a.outcome = 'failed' {chan_sql} "
        "GROUP BY 1 ORDER BY 2 DESC, 1",
        [merchant_id, start, end, *chan_params],
    ).fetchall()
    payments = conn.execute(
        f"SELECT p.id, p.amount_cents FROM payment p WHERE p.merchant_id = ? AND p.created_at >= ? AND p.created_at < ? {chan_sql}",
        [merchant_id, start, end, *chan_params],
    ).fetchall()
    recovery = {"affected": 0, "recovered": 0, "within_hour": 0, "unresolved": 0, "pending": 0,
                "affected_cents": 0, "recovered_cents": 0, "unresolved_cents": 0}
    for payment_id, amount in payments:
        chain = conn.execute(
            "SELECT outcome, created_at, completed_at FROM payment_attempt WHERE payment_id = ? AND merchant_id = ? ORDER BY attempt_number",
            (payment_id, merchant_id),
        ).fetchall()
        if not any(outcome == "failed" for outcome, _, _ in chain):
            continue
        recovery["affected"] += 1
        recovery["affected_cents"] += amount
        success = [completed for outcome, _, completed in chain if outcome == "succeeded"]
        if success:
            recovery["recovered"] += 1
            recovery["recovered_cents"] += amount
            if parse_iso(success[0]) - parse_iso(chain[0][1]) <= timedelta(hours=1):
                recovery["within_hour"] += 1
        elif chain[-1][0] == "pending":
            recovery["pending"] += 1
        else:
            recovery["unresolved"] += 1
            recovery["unresolved_cents"] += amount
    return {"outcomes": outcomes, "signals": signals, "recovery": recovery}


def assert_matches(body: dict[str, Any], exp: dict[str, Any]) -> None:
    succeeded, failed = exp["outcomes"].get("succeeded", 0), exp["outcomes"].get("failed", 0)
    completed = succeeded + failed
    attempts = body["attempts"]
    assert (attempts["succeeded"], attempts["failed"], attempts["completed"]) == (succeeded, failed, completed)
    assert attempts["pending_excluded"] == exp["outcomes"].get("pending", 0)
    if completed:
        assert attempts["success_rate_bp"] == (2 * 10000 * succeeded + completed) // (2 * completed)
    else:
        assert attempts["success_rate_bp"] is None
    assert attempts["low_volume"] == (completed < attempts["low_volume_threshold"])
    assert sum(p["succeeded"] for p in body["trend"]["points"]) == succeeded
    assert sum(p["failed"] for p in body["trend"]["points"]) == failed
    assert [(s["failure_code"], s["count"]) for s in body["failure_signals"]["items"]] == [tuple(r) for r in exp["signals"]]
    assert body["failure_signals"]["total_failed"] == failed
    rec, r = body["recovery"], exp["recovery"]
    assert (rec["affected_payments"], rec["recovered"], rec["recovered_within_hour"], rec["unresolved"], rec["attempt_pending"]) == (
        r["affected"], r["recovered"], r["within_hour"], r["unresolved"], r["pending"])
    assert (rec["affected_cents"], rec["recovered_cents"], rec["unresolved_cents"]) == (r["affected_cents"], r["recovered_cents"], r["unresolved_cents"])
    assert rec["recovered"] + rec["unresolved"] + rec["attempt_pending"] == rec["affected_payments"]


def test_incident_numbers_match_independent_sql(client_as: Any, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = health(client_as("maya"), INCIDENT_QUERY)
    assert_matches(body, expected(seeded_conn, ids.merchant("alder-loom"), INCIDENT_FROM, INCIDENT_TO, "mobile_app"))

    # Pinned against today's seed (checksum cc88bde3), so a silent change to the scenario or the maths shows up here.
    assert body["attempts"] == {"succeeded": 53, "failed": 42, "completed": 95, "pending_excluded": 0, "success_rate_bp": 5579,
                                "low_volume": False, "low_volume_threshold": 30}
    assert body["recovery"] == {"affected_payments": 38, "recovered": 26, "recovered_within_hour": 26, "unresolved": 12,
                                "attempt_pending": 0, "affected_cents": 896010, "recovered_cents": 473199,
                                "unresolved_cents": 422811, "attempt_pending_cents": 0, "currency": "USD"}
    top = body["failure_signals"]["items"][0]
    assert (top["failure_code"], top["label"], top["count"]) == ("issuer_unavailable", "Issuer unavailable", 29)
    assert [p["day"] for p in body["trend"]["points"]] == ["2026-10-01", "2026-10-02"]
    assert body["channel_label"] == "Mobile app"
    assert body["period"]["from_date"] == "2026-10-01" and body["period"]["to_date"] == "2026-10-02"


def test_unresolved_drill_down_lands_on_the_same_payments(client_as: Any) -> None:
    maya = client_as("maya")
    body = health(maya, INCIDENT_QUERY)
    listed = maya.get(f"/api/payments?status=failed&page_size=100&{INCIDENT_QUERY}").json()
    assert listed["total"] == body["recovery"]["unresolved"]
    assert sum(item["amount_cents"] for item in listed["items"]) == body["recovery"]["unresolved_cents"]


def test_a_retried_payment_counts_once_as_recovered(client_as: Any, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    start, end = chicago_range(INCIDENT_FROM, INCIDENT_TO)
    retried = seeded_conn.execute(
        "SELECT p.id, p.amount_cents, p.created_at FROM payment p WHERE p.merchant_id = ? AND p.channel = 'mobile_app' "
        "AND p.created_at >= ? AND p.created_at < ? "
        "AND (SELECT COUNT(*) FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'failed') = 2 "
        "AND EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'succeeded') ORDER BY p.created_at LIMIT 1",
        (alder, start, end),
    ).fetchone()
    assert retried is not None, "the incident includes a payment declined twice and then completed"
    payment_id, amount, created_at = retried
    attempts = health(client_as("maya"), INCIDENT_QUERY)

    # Every other recovered payment in the cohort, from SQL; the retried payment adds exactly one payment and one amount.
    others = seeded_conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(p.amount_cents), 0) FROM payment p WHERE p.merchant_id = ? AND p.channel = 'mobile_app' "
        "AND p.created_at >= ? AND p.created_at < ? AND p.id <> ? "
        "AND EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'failed') "
        "AND EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'succeeded')",
        (alder, start, end, payment_id),
    ).fetchone()
    assert attempts["recovery"]["recovered"] == others[0] + 1
    assert attempts["recovery"]["recovered_cents"] == others[1] + amount

    # Counting per failed attempt instead would have added its amount twice.
    per_attempt = seeded_conn.execute(
        "SELECT COALESCE(SUM(p.amount_cents), 0) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = ? AND a.outcome = 'failed' AND p.channel = 'mobile_app' AND p.created_at >= ? AND p.created_at < ? "
        "AND EXISTS (SELECT 1 FROM payment_attempt s WHERE s.payment_id = p.id AND s.outcome = 'succeeded')",
        (alder, start, end),
    ).fetchone()[0]
    assert per_attempt > attempts["recovery"]["recovered_cents"]


@pytest.mark.parametrize("persona", ["priya", "sam_copper"])
def test_other_merchants_see_only_their_own_figures(persona: str, client_as: Any, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchant(PERSONAS[persona][1])
    alder = health(client_as("maya"), INCIDENT_QUERY)
    for query, from_day, to_day, channel in [
        (INCIDENT_QUERY, INCIDENT_FROM, INCIDENT_TO, "mobile_app"),
        ("period=custom&from=2026-10-01&to=2026-10-02", INCIDENT_FROM, INCIDENT_TO, None),
    ]:
        body = health(client_as(persona), query)
        assert_matches(body, expected(seeded_conn, merchant_id, from_day, to_day, channel))
        assert_scoped(ids, body, merchant_id)
        assert body["recovery"] != alder["recovery"]
        assert body["attempts"]["failed"] < alder["attempts"]["failed"]
        # A merchant id in the query string is not a filter: the session's merchant is the only scope.
        assert health(client_as(persona), f"{query}&merchant_id={ids.merchant('alder-loom')}") == body


def test_merchant_without_completed_attempts_gets_no_rate(client_as: Any) -> None:
    # Juniper Trail has no mobile app channel: nothing completed, so no success rate is fabricated.
    body = health(client_as("priya"), INCIDENT_QUERY)
    assert body["attempts"]["completed"] == 0 and body["attempts"]["success_rate_bp"] is None
    assert body["failure_signals"]["items"] == [] and body["recovery"]["affected_payments"] == 0


@pytest.mark.parametrize("query", ["channel=bogus", "period=forever", "period=custom&from=2026-10-02&to=2026-10-01", "channel=web"])
def test_invalid_filters_are_422(query: str, client_as: Any) -> None:
    r = client_as("maya").get(f"/api/payment-health?{query}")
    assert r.status_code == 422
    assert set(r.json()["error"]) == {"code", "message"}
