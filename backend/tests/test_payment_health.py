"""GET /api/payment-health: every figure recomputed with independent SQL, matched to the list a drill-down opens, the
seeded scenario's conclusions, edge cases, and merchant isolation for this collection-level endpoint."""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction

import pytest

from app.core import clock, periods
from app.core.tz import chicago_range, parse_iso
from tests.conftest import PERSONAS, Ids, assert_scoped

PERSONA_PRESETS = [(p, q) for p in ("maya", "priya", "sam_copper") for q in ("last_7_days", "month_to_date", "last_30_days", "custom")]
CUSTOM = "from=2026-09-14&to=2026-09-20"


def query_for(preset: str) -> str:
    return CUSTOM if preset == "custom" else f"period={preset}"


def resolve(conn: sqlite3.Connection, preset: str) -> periods.Period:
    if preset == "custom":
        return periods.resolve("custom", clock.now(conn), date(2026, 9, 14), date(2026, 9, 20))
    return periods.resolve(preset, clock.now(conn))


def attempt_outcomes(conn: sqlite3.Connection, merchant_id: str | None, start: str, end: str, channel: str | None = None) -> Counter[str]:
    sql = "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id WHERE a.created_at >= ? AND a.created_at < ?"
    params: list[object] = [start, end]
    if merchant_id:
        sql += " AND a.merchant_id = ?"
        params.append(merchant_id)
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    return Counter(dict(conn.execute(sql + " GROUP BY a.outcome", params).fetchall()))


def rate(c: Counter[str]) -> int | None:
    """Basis points rounded half-up, with exact fractions."""
    completed = c["succeeded"] + c["failed"]
    return None if completed == 0 else math.floor(Fraction(c["succeeded"] * 10000, completed) + Fraction(1, 2))


def affected_payments(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> dict[str, list[tuple[str, int]]]:
    """Payments created in [start, end) with a failed attempt, grouped by how they ended: (payment id, amount) pairs."""
    sql = (
        "SELECT p.id, p.amount_cents, MIN(a.created_at) AS first_at, MAX(CASE WHEN a.outcome = 'succeeded' THEN a.completed_at END) AS ok_at, "
        "(SELECT l.outcome FROM payment_attempt l WHERE l.payment_id = p.id ORDER BY l.attempt_number DESC LIMIT 1) AS latest "
        "FROM payment p JOIN payment_attempt a ON a.payment_id = p.id WHERE p.merchant_id = ? AND p.created_at >= ? AND p.created_at < ?"
    )
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    groups: dict[str, list[tuple[str, int]]] = {k: [] for k in ("affected", "recovered", "recovered_within_hour", "unresolved", "in_progress")}
    for r in conn.execute(sql + " GROUP BY p.id HAVING SUM(a.outcome = 'failed') > 0", params):
        pair = (r["id"], r["amount_cents"])
        groups["affected"].append(pair)
        if r["ok_at"]:
            groups["recovered"].append(pair)
            if (parse_iso(r["ok_at"]) - parse_iso(r["first_at"])).total_seconds() <= 3600:
                groups["recovered_within_hour"].append(pair)
        elif r["latest"] == "failed":
            groups["unresolved"].append(pair)
        else:
            assert r["latest"] == "pending"
            groups["in_progress"].append(pair)
    return groups


@pytest.mark.parametrize("persona,preset", PERSONA_PRESETS)
def test_figures_match_an_independent_recomputation(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str) -> None:
    merchant_id = ids.merchants[PERSONAS[persona][1]]
    period = resolve(seeded_conn, preset)
    body = client_as(persona).get(f"/api/payment-health?{query_for(preset)}").json()
    assert body["period"]["from_date"] == period.from_day.isoformat() and body["period"]["to_date"] == period.to_day.isoformat()

    base_from, base_to = period.from_day - timedelta(days=30), period.from_day - timedelta(days=1)
    assert (body["baseline"]["from_date"], body["baseline"]["to_date"], body["baseline"]["days"]) == (base_from.isoformat(), base_to.isoformat(), 30)
    base_start, base_end = chicago_range(base_from, base_to)

    # Completed-attempt totals, pending kept out of the rate.
    c = attempt_outcomes(seeded_conn, merchant_id, period.start, period.end)
    b = attempt_outcomes(seeded_conn, merchant_id, base_start, base_end)
    a = body["attempts"]
    assert (a["succeeded"], a["failed"], a["pending"], a["completed"]) == (c["succeeded"], c["failed"], c["pending"], c["succeeded"] + c["failed"])
    assert a["success_rate_bp"] == rate(c)
    assert (a["baseline_succeeded"], a["baseline_completed"], a["baseline_rate_bp"]) == (b["succeeded"], b["succeeded"] + b["failed"], rate(b))

    # Channel rows reconcile to the totals and to per-channel SQL.
    for key in ("completed", "succeeded", "failed", "pending"):
        assert sum(ch[key] for ch in body["channels"]) == a[key]
    for ch in body["channels"]:
        cc = attempt_outcomes(seeded_conn, merchant_id, period.start, period.end, ch["channel"])
        assert (ch["succeeded"], ch["failed"], ch["pending"], ch["success_rate_bp"]) == (cc["succeeded"], cc["failed"], cc["pending"], rate(cc))

    # The trend has every Chicago day and sums to the totals; signals sum to the failed attempts.
    assert [p["day"] for p in body["trend"]] == [d.isoformat() for d in periods.day_buckets(period)]
    for key in ("completed", "succeeded", "failed", "pending"):
        assert sum(p[key] for p in body["trend"]) == a[key]
    assert sum(s["count"] for s in body["failure_signals"]) == a["failed"]

    # Recovery is per payment, value counted once per payment.
    expected = affected_payments(seeded_conn, merchant_id, period.start, period.end)
    for name, pairs in expected.items():
        assert body["recovery"][name] == {"payments": len(pairs), "amount_cents": sum(amount for _, amount in pairs)}, name
    r = body["recovery"]
    for unit in ("payments", "amount_cents"):
        assert r["recovered"][unit] + r["unresolved"][unit] + r["in_progress"][unit] == r["affected"][unit]
    assert r["currency"] == "USD"


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("channel", [None, "website", "mobile_app", "in_store"])
def test_figures_match_the_lists_a_drill_down_opens(client_as, persona: str, channel: str | None) -> None:
    c = client_as(persona)
    scope = "period=last_7_days" + (f"&channel={channel}" if channel else "")
    body = c.get(f"/api/payment-health?{scope}").json()
    assert c.get(f"/api/attempts?{scope}&outcome=failed").json()["total"] == body["attempts"]["failed"]
    assert c.get(f"/api/attempts?{scope}&outcome=pending").json()["total"] == body["attempts"]["pending"]
    for signal in body["failure_signals"]:
        listed = c.get(f"/api/attempts?{scope}&outcome=failed&failure_code={signal['code']}").json()["total"]
        assert listed == signal["count"], signal["code"]
    assert c.get(f"/api/payments?{scope}&status=failed").json()["total"] == body["recovery"]["unresolved"]["payments"]


def test_alder_and_loom_mobile_app_is_degraded_over_the_last_seven_days(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?period=last_7_days").json()
    by_channel = {ch["channel"]: ch for ch in body["channels"]}
    assert body["attention"]["state"] == "degraded"
    assert body["attention"]["degraded_channels"] == ["mobile_app"]
    mobile = by_channel["mobile_app"]
    assert mobile["assessment"] == "degraded" and mobile["assessment_label"] == "Degraded"
    assert mobile["change_bp"] <= -body["rules"]["degraded_drop_bp"]
    assert by_channel["website"]["assessment"] == "no_significant_degradation"
    assert by_channel["in_store"]["assessment"] == "no_significant_degradation"

    scoped = client_as("maya").get("/api/payment-health?period=last_7_days&channel=mobile_app").json()
    assert scoped["channel"] == "mobile_app" and scoped["channel_label"] == "Mobile app"
    assert scoped["failure_signals"][0]["code"] == "issuer_unavailable"
    assert scoped["failure_signals"][0]["label"] == "Issuer unavailable"
    # Scoping to one channel still assesses every channel.
    assert scoped["attention"]["degraded_channels"] == ["mobile_app"]
    assert [ch["channel"] for ch in scoped["channels"]] == ["website", "mobile_app", "in_store"]
    website = client_as("maya").get("/api/payment-health?period=last_7_days&channel=website").json()
    assert website["attention"]["state"] == "degraded"


def test_low_volume_channels_are_not_assessed(client_as) -> None:
    copper = client_as("sam_copper").get("/api/payment-health?period=last_7_days").json()
    by_channel = {ch["channel"]: ch["assessment"] for ch in copper["channels"]}
    assert by_channel == {"website": "insufficient_volume", "mobile_app": "insufficient_volume", "in_store": "no_significant_degradation"}
    assert copper["attention"]["state"] == "no_significant_degradation"
    assert copper["attention"]["not_assessed_channels"] == ["website", "mobile_app"]

    juniper = client_as("priya").get("/api/payment-health?period=last_7_days").json()
    assert [ch["channel"] for ch in juniper["channels"]] == ["website", "in_store"], "a channel with no attempts at all is not listed"
    assert {ch["channel"]: ch["assessment"] for ch in juniper["channels"]} == {"website": "no_significant_degradation", "in_store": "insufficient_volume"}


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
def test_a_short_baseline_draws_no_conclusion(client_as, persona: str) -> None:
    # The seeded history starts 2026-09-05, so the 30 days before the last 30 days hold one day of data.
    body = client_as(persona).get("/api/payment-health?period=last_30_days").json()
    assert body["attention"]["state"] == "insufficient_data"
    assert body["attention"]["degraded_channels"] == []
    assert body["baseline"]["days_with_completed"] == 1
    assert all(ch["assessment"] == "insufficient_volume" for ch in body["channels"])


def test_a_period_with_no_attempts_has_no_rate(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?from=2026-08-01&to=2026-08-07").json()
    assert body["attempts"]["completed"] == 0 and body["attempts"]["success_rate_bp"] is None and body["attempts"]["change_bp"] is None
    assert body["attention"]["state"] == "no_completed_attempts"
    assert body["channels"] == [] and body["failure_signals"] == []
    assert len(body["trend"]) == 7 and all(p["success_rate_bp"] is None and not p["low_volume"] for p in body["trend"])
    assert body["recovery"]["affected"] == {"payments": 0, "amount_cents": 0}


def test_pending_attempts_are_reported_but_not_in_the_rate(client_as, seeded_conn: sqlite3.Connection) -> None:
    body = client_as("sam_copper").get("/api/payment-health?from=2026-10-05&to=2026-10-05&channel=website").json()
    a = body["attempts"]
    assert a["pending"] >= 2 and a["completed"] == 0 and a["success_rate_bp"] is None
    assert body["trend"] == [{"day": "2026-10-05", "completed": 0, "succeeded": 0, "failed": 0, "pending": a["pending"], "success_rate_bp": None, "low_volume": False}]
    assert body["failure_signals"] == []
    website = next(ch for ch in body["channels"] if ch["channel"] == "website")
    assert website["assessment"] == "no_completed_attempts"


def test_a_day_with_no_failures_has_no_signals(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    days = [
        d for (d,) in seeded_conn.execute(
            "SELECT DISTINCT substr(a.created_at, 1, 10) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id "
            "WHERE a.merchant_id = ? AND p.channel = 'in_store'", (alder,))
    ]
    clean = None
    for text in sorted(days):
        day = date.fromisoformat(text)
        start, end = chicago_range(day, day)
        c = attempt_outcomes(seeded_conn, alder, start, end, "in_store")
        if c["succeeded"] and not c["failed"]:
            clean = day
            break
    assert clean is not None
    body = client_as("maya").get(f"/api/payment-health?from={clean}&to={clean}&channel=in_store").json()
    assert body["attempts"]["failed"] == 0 and body["attempts"]["success_rate_bp"] == 10000
    assert body["failure_signals"] == []
    assert [p["day"] for p in body["trend"]] == [clean.isoformat()]


def test_quick_recovery_is_part_of_recovery(client_as) -> None:
    # Every seeded retry succeeds within 3,018 s of the first attempt, so here the two groups coincide; the one-hour
    # boundary itself is covered in test_health_rules.py.
    r = client_as("maya").get("/api/payment-health?period=last_7_days&channel=mobile_app").json()["recovery"]
    assert r["recovered"]["payments"] > 0
    assert r["recovered_within_hour"] == r["recovered"]


def test_rules_are_published_with_the_figures(client_as) -> None:
    rules = client_as("maya").get("/api/payment-health").json()["rules"]
    assert rules == {
        "baseline_days": 30,
        "degraded_drop_bp": 1000,
        "min_period_completed": 50,
        "min_baseline_completed": 100,
        "low_volume_day_completed": 10,
        "quick_recovery_seconds": 3600,
    }


@pytest.mark.parametrize(
    "query",
    ["channel=phone", "period=last_year", "from=2026-10-05&to=2026-10-01", "period=custom&from=2026-10-01", "from=2026-13-01&to=2026-13-02"],
)
def test_invalid_parameters_are_422(client_as, query: str) -> None:
    r = client_as("maya").get(f"/api/payment-health?{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_every_role_can_read_payment_health_and_anonymous_cannot(client, client_as) -> None:
    assert client.get("/api/payment-health").status_code == 401
    for persona in ("maya", "daniel", "jordan", "sam", "priya", "sam_copper"):
        assert client_as(persona).get("/api/payment-health").status_code == 200, persona


# ---------------------------------------------------------------------------------------------- merchant isolation


@pytest.mark.parametrize("persona,other", [("sam", "sam_copper"), ("sam_copper", "sam"), ("maya", "priya"), ("priya", "maya")])
def test_results_are_scoped_to_the_session_merchant(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, other: str) -> None:
    merchant_id = ids.merchants[PERSONAS[persona][1]]
    other_id = ids.merchants[PERSONAS[other][1]]
    period = resolve(seeded_conn, "last_30_days")
    body = client_as(persona).get("/api/payment-health?period=last_30_days").json()
    assert_scoped(ids, body, merchant_id)

    mine = attempt_outcomes(seeded_conn, merchant_id, period.start, period.end)
    theirs = attempt_outcomes(seeded_conn, other_id, period.start, period.end)
    everyone = attempt_outcomes(seeded_conn, None, period.start, period.end)
    for outcome in ("succeeded", "failed"):
        assert body["attempts"][outcome] == mine[outcome]
        assert body["attempts"][outcome] < everyone[outcome], "figures must not include another merchant's attempts"
        assert body["attempts"][outcome] + theirs[outcome] <= everyone[outcome]

    own = affected_payments(seeded_conn, merchant_id, period.start, period.end)
    foreign = affected_payments(seeded_conn, other_id, period.start, period.end)
    assert body["recovery"]["affected"]["payments"] == len(own["affected"])
    assert body["recovery"]["affected"]["amount_cents"] == sum(a for _, a in own["affected"])
    assert {pid for pid, _ in own["affected"]}.isdisjoint({pid for pid, _ in foreign["affected"]})


def test_the_same_user_at_two_merchants_sees_two_different_results(client_as) -> None:
    alder = client_as("sam").get("/api/payment-health?period=last_7_days").json()
    copper = client_as("sam_copper").get("/api/payment-health?period=last_7_days").json()
    assert alder["attention"]["degraded_channels"] == ["mobile_app"]
    assert copper["attention"]["degraded_channels"] == []
    assert alder["attempts"] != copper["attempts"]
    assert alder["recovery"] != copper["recovery"]
