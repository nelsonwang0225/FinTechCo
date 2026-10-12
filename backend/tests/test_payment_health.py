"""Payment Health: every figure is an independent recomputation from attempts and payments, the parts reconcile to the
whole, drill-down lists return the same totals, and low volume never produces a verdict."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import pytest

from app.api.payment_health import recovery_of
from app.core import clock, health, periods
from app.core.tz import chicago_day, chicago_range
from tests.conftest import PERSONAS, Ids, assert_scoped

PRESETS = ["last_7_days", "month_to_date", "last_30_days"]
CHANNELS = ["website", "mobile_app", "in_store"]


def resolve(conn: sqlite3.Connection, preset: str) -> periods.Period:
    return periods.resolve(preset, clock.now(conn))


def attempt_outcomes(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> Counter[str]:
    sql = (
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = :m AND a.created_at >= :s AND a.created_at < :e AND (:c IS NULL OR p.channel = :c) GROUP BY a.outcome"
    )
    return Counter({row[0]: row[1] for row in conn.execute(sql, {"m": merchant_id, "s": start, "e": end, "c": channel})})


def independent_recovery(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None) -> dict[str, tuple[int, int]]:
    """Walk raw attempts per payment, without the payment_summary view, and bucket each payment once."""
    rows = conn.execute(
        "SELECT p.id, p.amount_cents, a.attempt_number, a.outcome, a.created_at, a.completed_at FROM payment p "
        "JOIN payment_attempt a ON a.payment_id = p.id AND a.merchant_id = p.merchant_id "
        "WHERE p.merchant_id = :m AND p.created_at >= :s AND p.created_at < :e AND (:c IS NULL OR p.channel = :c) ORDER BY p.id, a.attempt_number",
        {"m": merchant_id, "s": start, "e": end, "c": channel},
    ).fetchall()
    by_payment: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_payment[r["id"]].append(r)
    buckets: dict[str, list[int]] = {k: [] for k in ("affected", "recovered", "recovered_within_hour", "unresolved", "awaiting_retry")}
    for attempts in by_payment.values():
        if not any(a["outcome"] == "failed" for a in attempts):
            continue
        amount = attempts[0]["amount_cents"]
        buckets["affected"].append(amount)
        success = [a for a in attempts if a["outcome"] == "succeeded"]
        if success:
            buckets["recovered"].append(amount)
            first = datetime.fromisoformat(attempts[0]["created_at"].replace("Z", "+00:00"))
            done = datetime.fromisoformat(success[0]["completed_at"].replace("Z", "+00:00"))
            if done - first <= timedelta(hours=1):
                buckets["recovered_within_hour"].append(amount)
        elif attempts[-1]["outcome"] == "pending":
            buckets["awaiting_retry"].append(amount)
        else:
            buckets["unresolved"].append(amount)
    return {k: (len(v), sum(v)) for k, v in buckets.items()}


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("channel", [None, *CHANNELS])
def test_attempt_figures_reconcile_with_the_attempts(client_as, seeded_conn: sqlite3.Connection, ids: Ids, preset: str, channel: str | None) -> None:
    merchant_id = ids.merchant("alder-loom")
    query = f"period={preset}" + (f"&channel={channel}" if channel else "")
    body = client_as("maya").get(f"/api/payment-health?{query}").json()
    p = resolve(seeded_conn, preset)
    expected = attempt_outcomes(seeded_conn, merchant_id, p.start, p.end, channel)
    s = body["summary"]
    assert (s["succeeded"], s["failed"], s["pending"]) == (expected["succeeded"], expected["failed"], expected["pending"])
    assert s["completed"] == s["succeeded"] + s["failed"]  # pending never enters the denominator
    assert s["success_rate_bp"] == health.rate_bp(s["succeeded"], s["completed"])

    # Baseline: the 30 Chicago days before the period, same channel.
    b_from, b_to = p.from_day - timedelta(days=30), p.from_day - timedelta(days=1)
    assert (body["baseline"]["from_date"], body["baseline"]["to_date"]) == (b_from.isoformat(), b_to.isoformat())
    base = attempt_outcomes(seeded_conn, merchant_id, *chicago_range(b_from, b_to), channel)
    assert (s["baseline_succeeded"], s["baseline_failed"]) == (base["succeeded"], base["failed"])

    # Channels always cover all three and add up to the merchant total.
    assert [c["channel"] for c in body["channels"]] == CHANNELS
    if channel is None:
        for key in ("succeeded", "failed", "pending", "baseline_succeeded", "baseline_failed"):
            assert sum(c[key] for c in body["channels"]) == s[key]
    else:
        (row,) = [c for c in body["channels"] if c["channel"] == channel]
        assert {k: row[k] for k in s} == s

    # The trend has one point per Chicago day and sums to the summary; empty days are gaps, not 0%.
    assert [t["day"] for t in body["trend"]] == [d.isoformat() for d in periods.day_buckets(p)]
    for key in ("succeeded", "failed", "pending"):
        assert sum(t[key] for t in body["trend"]) == s[key]
    for t in body["trend"]:
        assert t["completed"] == t["succeeded"] + t["failed"]
        assert (t["success_rate_bp"] is None) == (t["completed"] == 0)
        assert t["low_volume"] == (0 < t["completed"] < 10)

    # Recorded failure signals reconcile exactly to the failed attempts.
    assert sum(f["failed_attempts"] for f in body["failure_signals"]) == s["failed"]
    counts = [f["failed_attempts"] for f in body["failure_signals"]]
    assert counts == sorted(counts, reverse=True)
    assert_scoped(ids, body, merchant_id)


def test_trend_buckets_by_the_attempts_chicago_day(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("maya").get("/api/payment-health?period=last_7_days&channel=mobile_app").json()
    p = resolve(seeded_conn, "last_7_days")
    rows = seeded_conn.execute(
        "SELECT a.created_at, a.outcome FROM payment_attempt a JOIN payment p ON p.id = a.payment_id WHERE a.merchant_id = ? AND p.channel = 'mobile_app' "
        "AND a.created_at >= ? AND a.created_at < ?",
        (ids.merchant("alder-loom"), p.start, p.end),
    ).fetchall()
    per_day: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        per_day[chicago_day(r["created_at"]).isoformat()][r["outcome"]] += 1
    for t in body["trend"]:
        assert (t["succeeded"], t["failed"], t["pending"]) == (per_day[t["day"]]["succeeded"], per_day[t["day"]]["failed"], per_day[t["day"]]["pending"])


def test_each_failure_signal_drills_into_the_same_failed_attempts(client_as) -> None:
    c = client_as("maya")
    scope = "period=month_to_date&channel=mobile_app"
    body = c.get(f"/api/payment-health?{scope}").json()
    assert body["failure_signals"]
    for signal in body["failure_signals"]:
        listing = c.get(f"/api/attempts?{scope}&outcome=failed&failure_code={signal['code']}&page_size=1").json()
        assert listing["total"] == signal["failed_attempts"], signal["code"]
    failed = c.get(f"/api/attempts?{scope}&outcome=failed&page_size=1").json()
    assert failed["total"] == body["summary"]["failed"]


def test_the_scripted_mobile_app_incident_is_flagged_with_its_evidence(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?period=month_to_date").json()
    channels = {c["channel"]: c for c in body["channels"]}
    app = channels["mobile_app"]
    assert app["assessment"] == "degraded" and app["assessment_label"] == "Degraded"
    assert app["completed"] >= 50 and app["baseline_completed"] >= 200
    assert app["change_bp"] <= -500
    assert channels["website"]["assessment"] == "within_baseline"
    scoped = client_as("maya").get("/api/payment-health?period=month_to_date&channel=mobile_app").json()
    assert scoped["failure_signals"][0]["code"] == "issuer_unavailable"
    assert scoped["failure_signals"][0]["label"] == "Issuer unavailable"
    assert scoped["channel_label"] == "Mobile app"


def test_low_volume_never_produces_a_verdict(client_as) -> None:
    # last_30_days reaches back before the seeded history, so every baseline is too thin.
    body = client_as("maya").get("/api/payment-health?period=last_30_days").json()
    assert {c["assessment"] for c in body["channels"]} == {"insufficient_baseline"}
    copper = client_as("sam_copper").get("/api/payment-health?period=last_7_days").json()
    assert {c["channel"]: c["assessment"] for c in copper["channels"]}["mobile_app"] == "insufficient_period_volume"
    juniper = client_as("priya").get("/api/payment-health?period=last_7_days").json()
    app = {c["channel"]: c for c in juniper["channels"]}["mobile_app"]
    assert app["assessment"] == "no_completed_attempts"
    assert app["success_rate_bp"] is None and app["change_bp"] is None


def test_a_period_without_attempts_is_empty_not_fabricated(client_as) -> None:
    r = client_as("maya").get("/api/payment-health?from=2026-08-01&to=2026-08-07")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["completed"] == 0 and body["summary"]["success_rate_bp"] is None
    assert all(t["success_rate_bp"] is None and not t["low_volume"] for t in body["trend"])
    assert body["failure_signals"] == []
    assert body["recovery"]["affected"] == {"payments": 0, "amount_cents": 0}


def test_pending_attempts_are_counted_but_excluded(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = client_as("sam_copper").get("/api/payment-health?from=2026-10-05&to=2026-10-05&channel=website").json()
    start, end = chicago_range(date(2026, 10, 5), date(2026, 10, 5))
    expected = attempt_outcomes(seeded_conn, ids.merchant("copper-finch"), start, end, "website")
    assert body["summary"]["pending"] == expected["pending"] > 0
    assert body["summary"]["completed"] == expected["succeeded"] + expected["failed"]
    if body["summary"]["completed"] == 0:
        assert body["summary"]["success_rate_bp"] is None


@pytest.mark.parametrize("persona,preset,channel", [
    ("maya", "last_7_days", None), ("maya", "month_to_date", "mobile_app"), ("maya", "last_30_days", "website"),
    ("priya", "last_30_days", None), ("sam_copper", "last_7_days", None),
])
def test_recovery_is_counted_once_per_payment(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str, channel: str | None) -> None:
    query = f"period={preset}" + (f"&channel={channel}" if channel else "")
    body = client_as(persona).get(f"/api/payment-health?{query}").json()
    p = resolve(seeded_conn, preset)
    expected = independent_recovery(seeded_conn, ids.merchants[PERSONAS[persona][1]], p.start, p.end, channel)
    got = {k: (v["payments"], v["amount_cents"]) for k, v in body["recovery"].items() if k != "currency"}
    assert got == expected
    r = body["recovery"]
    for key in ("payments", "amount_cents"):
        assert r["affected"][key] == r["recovered"][key] + r["unresolved"][key] + r["awaiting_retry"][key]
        assert r["recovered_within_hour"][key] <= r["recovered"][key]
    assert r["currency"] == "USD"


def test_unresolved_payments_drill_into_the_failed_payments_list(client_as) -> None:
    c = client_as("maya")
    for scope in ("period=last_7_days", "period=month_to_date&channel=mobile_app", "from=2026-09-10&to=2026-09-20&channel=in_store"):
        body = c.get(f"/api/payment-health?{scope}").json()
        listing = c.get(f"/api/payments?{scope}&status=failed&page_size=1").json()
        assert listing["total"] == body["recovery"]["unresolved"]["payments"], scope


def test_awaiting_and_quick_recovery_buckets() -> None:
    rows = [
        {"amount_cents": 1000, "succeeded_attempt_id": "att_a", "succeeded_at": "2026-10-01T21:00:00Z", "status": "succeeded", "first_attempt_at": "2026-10-01T20:00:00Z"},
        {"amount_cents": 2000, "succeeded_attempt_id": "att_b", "succeeded_at": "2026-10-01T21:00:01Z", "status": "refunded", "first_attempt_at": "2026-10-01T20:00:00Z"},
        {"amount_cents": 3000, "succeeded_attempt_id": None, "succeeded_at": None, "status": "failed", "first_attempt_at": "2026-10-01T20:00:00Z"},
        {"amount_cents": 4000, "succeeded_attempt_id": None, "succeeded_at": None, "status": "pending", "first_attempt_at": "2026-10-01T20:00:00Z"},
    ]
    r = recovery_of(rows)  # type: ignore[arg-type]
    assert (r.affected.payments, r.affected.amount_cents) == (4, 10000)
    assert (r.recovered.payments, r.recovered.amount_cents) == (2, 3000)  # a later refund does not undo recovery
    assert (r.recovered_within_hour.payments, r.recovered_within_hour.amount_cents) == (1, 1000)
    assert (r.unresolved.payments, r.unresolved.amount_cents) == (1, 3000)
    assert (r.awaiting_retry.payments, r.awaiting_retry.amount_cents) == (1, 4000)


def test_thresholds_and_definitions_are_returned(client_as) -> None:
    body = client_as("sam").get("/api/payment-health").json()
    assert body["period"]["preset"] == "last_7_days"
    assert body["as_of"] == "2026-10-05T14:12:00Z"
    assert body["thresholds"] == {
        "degraded_drop_bp": 500, "min_period_completed": 50, "min_baseline_completed": 200,
        "low_volume_day_completed": 10, "baseline_days": 30, "quick_recovery_seconds": 3600,
    }


@pytest.mark.parametrize("query", [
    "channel=kiosk", "period=yesterday", "from=2026-10-05&to=2026-10-01", "from=2025-01-01&to=2026-10-01", "from=2026-10-01", "channel=mobile_app%25",
])
def test_invalid_parameters_are_422(client_as, query: str) -> None:
    r = client_as("maya").get(f"/api/payment-health?{query}")
    assert r.status_code == 422, query
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("persona", ["maya", "daniel", "jordan", "sam", "priya", "sam_copper"])
def test_every_role_with_payments_read_gets_the_page(client_as, persona: str) -> None:
    assert client_as(persona).get("/api/payment-health").status_code == 200
