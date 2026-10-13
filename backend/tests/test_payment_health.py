"""Payment Health: completed-attempt success against each channel's own baseline, recorded failure signals and per-payment
recovery. Every figure is recomputed here from base rows with independent SQL, the drill-down filters on /api/attempts and
/api/payments return exactly the records a figure counts, and results never cross merchants."""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest

from app.api import payment_health as health_api
from app.api.attempts import FailureCode
from app.api.schemas.payment_health import OutcomeCounts
from app.core import clock, periods
from app.core.labels import FAILURE_SIGNAL_LABELS
from app.core.tz import chicago_day_bounds, chicago_range, parse_iso
from app.seed import scenario as S
from tests.conftest import PERSONAS, Ids, assert_scoped
from tests.test_seed_history import app_window_payments, declined

TOP_KEYS = {
    "period", "baseline_period", "channel", "channel_label", "thresholds", "summary", "attention", "channels", "daily", "failure_signals", "recovery",
    "unresolved",
}
CHANNELS = ("website", "mobile_app", "in_store")


def merchant_of(ids: Ids, persona: str) -> str:
    return ids.merchants[PERSONAS[persona][1]]


def outcomes(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> Counter[str]:
    sql = (
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ?"
    )
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    return Counter({row[0]: row[1] for row in conn.execute(sql + " GROUP BY a.outcome", params)})


def matches(counts: dict[str, Any], expected: Counter[str]) -> bool:
    return (counts["succeeded"], counts["failed"], counts["pending"], counts["completed"]) == (
        expected["succeeded"], expected["failed"], expected["pending"], expected["succeeded"] + expected["failed"]
    )


def chains_created_in(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None) -> dict[str, tuple[int, list[tuple[str, str, str | None]]]]:
    """payment id -> (amount, [(outcome, created_at, completed_at)] in attempt order) for payments created in [start, end)."""
    sql = (
        "SELECT p.id, p.amount_cents, a.outcome, a.created_at, a.completed_at FROM payment p "
        "JOIN payment_attempt a ON a.payment_id = p.id AND a.merchant_id = p.merchant_id "
        "WHERE p.merchant_id = ? AND p.created_at >= ? AND p.created_at < ?"
    )
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    out: dict[str, tuple[int, list[tuple[str, str, str | None]]]] = {}
    for pid, amount, outcome, created, completed in conn.execute(sql + " ORDER BY p.id, a.attempt_number", params):
        out.setdefault(pid, (amount, []))[1].append((outcome, created, completed))
    return out


# --------------------------------------------------------------------- shape, roles, scoping


@pytest.mark.parametrize("persona", ["maya", "daniel", "jordan", "sam", "priya", "sam_copper"])
def test_every_role_with_payments_read_gets_a_scoped_response(client_as, ids: Ids, persona: str) -> None:
    r = client_as(persona).get("/api/payment-health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == TOP_KEYS
    assert body["period"]["preset"] == "last_7_days"
    assert body["channel"] is None and body["channel_label"] == "All channels"
    assert body["thresholds"] == {
        "baseline_days": 30, "min_period_completed": 50, "min_baseline_completed": 100, "degraded_drop_bps": 1000,
        "low_volume_day_completed": 10, "recovery_window_minutes": 60,
    }
    assert_scoped(ids, body, merchant_of(ids, persona))


def test_the_route_needs_a_session(client) -> None:
    r = client.get("/api/payment-health")
    assert r.status_code == 401


@pytest.mark.parametrize("query", ["channel=bogus", "period=yesterday", "period=custom", "period=custom&from=2026-10-05&to=2026-10-01"])
def test_bad_input_is_a_422(client_as, query: str) -> None:
    r = client_as("maya").get(f"/api/payment-health?{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


# --------------------------------------------------------------------- reconciliation with base rows


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("preset", ["last_7_days", "last_30_days", "month_to_date"])
def test_attempt_figures_reconcile_with_payment_attempts(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str) -> None:
    merchant_id = merchant_of(ids, persona)
    period = periods.resolve(preset, clock.now(seeded_conn))
    baseline_from, baseline_to = period.from_day - timedelta(days=30), period.from_day - timedelta(days=1)
    b_start, b_end = chicago_range(baseline_from, baseline_to)
    body = client_as(persona).get(f"/api/payment-health?period={preset}").json()
    assert body["baseline_period"]["from_date"] == baseline_from.isoformat()
    assert body["baseline_period"]["to_date"] == baseline_to.isoformat()

    period_all = outcomes(seeded_conn, merchant_id, period.start, period.end)
    assert matches(body["summary"]["period"], period_all)
    assert matches(body["summary"]["baseline"], outcomes(seeded_conn, merchant_id, b_start, b_end))
    for row in body["channels"]:
        assert matches(row["period"], outcomes(seeded_conn, merchant_id, period.start, period.end, row["channel"])), row["channel"]
        assert matches(row["baseline"], outcomes(seeded_conn, merchant_id, b_start, b_end, row["channel"])), row["channel"]
    listed = {row["channel"] for row in body["channels"]}
    for channel in set(CHANNELS) - listed:
        assert not outcomes(seeded_conn, merchant_id, period.start, period.end, channel)
        assert not outcomes(seeded_conn, merchant_id, b_start, b_end, channel)

    # The daily series covers every Chicago day and sums to the summary.
    assert [p["day"] for p in body["daily"]] == [d.isoformat() for d in periods.day_buckets(period)]
    for key in ("succeeded", "failed", "pending"):
        assert sum(p[key] for p in body["daily"]) == period_all[key]
    for point in body["daily"][:3]:
        start, end = chicago_day_bounds(date.fromisoformat(point["day"]))
        day = outcomes(seeded_conn, merchant_id, start, end)
        assert (point["succeeded"], point["failed"], point["pending"]) == (day["succeeded"], day["failed"], day["pending"])

    # Recorded failure signals reconcile to the failed attempts.
    assert sum(s["failed_attempts"] for s in body["failure_signals"]) == period_all["failed"]
    codes = Counter(
        dict(seeded_conn.execute(
            "SELECT failure_code, COUNT(*) FROM payment_attempt WHERE merchant_id = ? AND outcome = 'failed' AND created_at >= ? AND created_at < ? GROUP BY failure_code",
            (merchant_id, period.start, period.end),
        ).fetchall())
    )
    assert {s["code"]: s["failed_attempts"] for s in body["failure_signals"]} == codes
    assert all(s["label"] == FAILURE_SIGNAL_LABELS[s["code"]] for s in body["failure_signals"])


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("query", ["period=last_7_days", "period=month_to_date&channel=mobile_app", "period=last_30_days&channel=website"])
def test_recovery_is_counted_once_per_payment(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, query: str) -> None:
    merchant_id = merchant_of(ids, persona)
    params = dict(part.split("=") for part in query.split("&"))
    period = periods.resolve(params["period"], clock.now(seeded_conn))
    body = client_as(persona).get(f"/api/payment-health?{query}").json()

    affected = {pid: v for pid, v in chains_created_in(seeded_conn, merchant_id, period.start, period.end, params.get("channel")).items() if declined_chain(v[1])}
    recovered = {pid: v for pid, v in affected.items() if any(o == "succeeded" for o, _, _ in v[1])}
    unresolved = {pid: v for pid, v in affected.items() if pid not in recovered}
    within = [
        pid for pid, (_, chain) in recovered.items()
        if parse_iso(next(c for o, _, c in chain if o == "succeeded") or "") - parse_iso(chain[0][1]) <= timedelta(hours=1)
    ]
    rec = body["recovery"]
    assert rec["affected_payments"] == len(affected)
    assert rec["recovered_payments"] == len(recovered)
    assert rec["unresolved_payments"] == len(unresolved)
    assert rec["recovered_within_window"] == len(within)
    assert rec["affected_cents"] == sum(a for a, _ in affected.values())
    assert rec["recovered_cents"] == sum(a for a, _ in recovered.values())
    assert rec["unresolved_cents"] == sum(a for a, _ in unresolved.values())
    assert rec["affected_cents"] == rec["recovered_cents"] + rec["unresolved_cents"]
    assert rec["unresolved_retry_pending"] == sum(1 for _, chain in unresolved.values() if chain[-1][0] == "pending")
    assert rec["currency"] == "USD"


def declined_chain(chain: list[tuple[str, str, str | None]]) -> bool:
    return any(o == "failed" for o, _, _ in chain)


# --------------------------------------------------------------------- drill-downs reconcile


def test_each_failure_signal_matches_its_attempts_drilldown(client_as) -> None:
    maya = client_as("maya")
    body = maya.get("/api/payment-health?period=last_7_days&channel=mobile_app").json()
    assert body["failure_signals"]
    for signal in body["failure_signals"]:
        drill = maya.get(f"/api/attempts?period=last_7_days&channel=mobile_app&outcome=failed&failure_code={signal['code']}&page_size=100").json()
        assert drill["total"] == signal["failed_attempts"], signal["code"]
        assert all(i["failure_code"] == signal["code"] and i["outcome"] == "failed" for i in drill["items"])


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
def test_recovery_groups_match_the_payments_drilldown(client_as, ids: Ids, persona: str) -> None:
    c = client_as(persona)
    body = c.get("/api/payment-health?period=month_to_date").json()
    rec = body["recovery"]
    for group, expected in (("affected", rec["affected_payments"]), ("recovered", rec["recovered_payments"]), ("unresolved", rec["unresolved_payments"])):
        drill = c.get(f"/api/payments?period=month_to_date&recovery={group}&page_size=100").json()
        assert drill["total"] == expected, group
        assert_scoped(ids, drill, merchant_of(ids, persona))
    first = c.get(f"/api/payments?period=month_to_date&recovery=unresolved&page_size={health_api.UNRESOLVED_LIMIT}").json()
    assert [p["id"] for p in body["unresolved"]] == [p["id"] for p in first["items"]]
    assert all(p["status"] in ("failed", "pending") for p in first["items"])


def test_unresolved_rows_describe_the_payment(client_as, seeded_conn: sqlite3.Connection) -> None:
    body = client_as("maya").get("/api/payment-health?period=last_7_days&channel=mobile_app").json()
    assert body["unresolved"]
    for row in body["unresolved"]:
        assert row["channel"] == "mobile_app"
        attempts = seeded_conn.execute("SELECT outcome, failure_code FROM payment_attempt WHERE payment_id = ? ORDER BY attempt_number", (row["id"],)).fetchall()
        assert "succeeded" not in [a[0] for a in attempts]
        assert row["failed_attempts"] == sum(1 for a in attempts if a[0] == "failed")
        assert row["last_failure_code"] == [a[1] for a in attempts if a[0] == "failed"][-1]
        assert row["amount_cents"] > 0 and row["currency"] == "USD"


# --------------------------------------------------------------------- the degradation rule on the seeded scenario


def test_the_scripted_app_checkout_window_is_flagged(client_as, seeded_conn: sqlite3.Connection) -> None:
    maya = client_as("maya")
    for preset in ("last_7_days", "month_to_date"):
        body = maya.get(f"/api/payment-health?period={preset}").json()
        assert body["attention"]["status"] == "degraded"
        assert [c["channel"] for c in body["attention"]["degraded"]] == ["mobile_app"]
        assert {c["channel"]: c["evaluation"] for c in body["channels"]} == {"website": "not_degraded", "mobile_app": "degraded", "in_store": "not_degraded"}
        mobile = body["attention"]["degraded"][0]
        assert mobile["drop_bps"] >= 1000 and mobile["drop_bps"] == mobile["baseline"]["success_rate_bps"] - mobile["period"]["success_rate_bps"]

    # Oct 1-2 on the app: the scripted window's attempts and payments are all inside what Payment Health counts.
    body = maya.get("/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app").json()
    assert (body["summary"]["period"]["failed"], body["summary"]["period"]["succeeded"]) == (42, 53)
    assert {s["code"]: s["failed_attempts"] for s in body["failure_signals"]}["issuer_unavailable"] == 29
    rec = body["recovery"]
    assert (rec["affected_payments"], rec["recovered_payments"], rec["unresolved_payments"]) == (38, 26, 12)
    chains, _ = app_window_payments(seeded_conn)
    window = {pid for pid, chain in chains.items() if declined(chain)}
    assert len(window) == 32
    affected = {p["id"] for p in maya.get("/api/payments?from=2026-10-01&to=2026-10-02&channel=mobile_app&recovery=affected&page_size=100").json()["items"]}
    unresolved = {p["id"] for p in maya.get("/api/payments?from=2026-10-01&to=2026-10-02&channel=mobile_app&recovery=unresolved&page_size=100").json()["items"]}
    assert window <= affected
    assert len(window & unresolved) == 9


def test_a_thin_baseline_is_not_evaluated(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?period=last_30_days").json()
    assert body["attention"]["status"] == "insufficient_volume"
    assert body["attention"]["degraded"] == []
    assert {c["evaluation"] for c in body["channels"]} == {"insufficient_volume"}
    assert all(c["baseline"]["completed"] < 100 for c in body["channels"])


def test_quiet_channels_are_named_but_not_judged(client_as) -> None:
    body = client_as("sam_copper").get("/api/payment-health?period=last_7_days").json()
    assert body["attention"]["status"] == "not_degraded"
    assert {c["channel"] for c in body["attention"]["not_evaluated"]} == {"website", "mobile_app"}
    assert {c["channel"]: c["evaluation"] for c in body["channels"]}["in_store"] == "not_degraded"


def test_a_low_volume_day_is_marked_and_not_judged(client_as) -> None:
    body = client_as("sam_copper").get("/api/payment-health?from=2026-09-27&to=2026-09-27&channel=mobile_app").json()
    assert body["summary"]["period"] == {"succeeded": 3, "failed": 2, "pending": 0, "completed": 5, "success_rate_bps": 6000}
    assert body["attention"]["status"] == "insufficient_volume"
    assert body["daily"] == [{"day": "2026-09-27", "succeeded": 3, "failed": 2, "pending": 0, "success_rate_bps": 6000, "low_volume": True}]


def test_pending_attempts_are_counted_but_never_rated(client_as) -> None:
    body = client_as("sam_copper").get("/api/payment-health?from=2026-10-05&to=2026-10-05&channel=website").json()
    period = body["summary"]["period"]
    assert period["completed"] == 0 and period["pending"] >= 2 and period["success_rate_bps"] is None
    assert body["attention"]["status"] == "no_completed"
    assert [c["channel"] for c in body["attention"]["not_evaluated"]] == ["website"]
    assert body["daily"][0]["success_rate_bps"] is None and body["daily"][0]["low_volume"] is False


def test_a_period_with_no_attempts_is_empty_not_zero(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?from=2026-08-01&to=2026-08-03").json()
    assert body["summary"]["period"]["completed"] == 0 and body["summary"]["period"]["success_rate_bps"] is None
    assert body["attention"]["status"] == "no_completed"
    assert body["channels"] == [] and body["failure_signals"] == [] and body["unresolved"] == []
    assert [p["success_rate_bps"] for p in body["daily"]] == [None, None, None]
    assert body["recovery"]["affected_payments"] == 0 and body["recovery"]["affected_cents"] == 0


def test_a_period_with_no_failures_rates_at_100_percent(client_as) -> None:
    body = client_as("sam_copper").get("/api/payment-health?from=2026-10-01&to=2026-10-05&channel=mobile_app").json()
    period = body["summary"]["period"]
    assert period["failed"] == 0 and period["completed"] > 0 and period["success_rate_bps"] == 10000
    assert body["failure_signals"] == [] and body["recovery"]["affected_payments"] == 0


# --------------------------------------------------------------------- rule units


def test_success_rate_is_integer_half_up() -> None:
    assert health_api.success_rate_bps(0, 0) is None
    assert health_api.success_rate_bps(2, 3) == 6667
    assert health_api.success_rate_bps(1, 3) == 3333
    assert health_api.success_rate_bps(1, 8) == 1250
    assert health_api.success_rate_bps(7, 7) == 10000


def counts(succeeded: int, failed: int) -> OutcomeCounts:
    return health_api.outcome_counts(succeeded, failed, 0)


def test_degradation_thresholds_are_inclusive() -> None:
    baseline = counts(900, 100)  # 9000 bps
    assert health_api.evaluate(counts(40, 10), baseline) == ("degraded", 1000)
    assert health_api.evaluate(counts(4001, 999), baseline)[0] == "not_degraded"  # 8002 bps: a 998 bps drop
    assert health_api.evaluate(counts(39, 10), baseline)[0] == "insufficient_volume"  # 49 completed
    assert health_api.evaluate(counts(40, 10), counts(89, 10))[0] == "insufficient_volume"  # 99 in the baseline
    assert health_api.evaluate(health_api.outcome_counts(0, 0, 3), baseline) == ("no_completed", None)


def test_recovery_window_boundary() -> None:
    rows: list[Any] = [
        {"succeeded_attempt_id": "att_a", "succeeded_at": "2026-10-01T01:00:00Z", "first_attempt_at": "2026-10-01T00:00:00Z", "latest_outcome": "succeeded", "amount_cents": 100},
        {"succeeded_attempt_id": "att_b", "succeeded_at": "2026-10-01T01:00:01Z", "first_attempt_at": "2026-10-01T00:00:00Z", "latest_outcome": "succeeded", "amount_cents": 200},
        {"succeeded_attempt_id": None, "succeeded_at": None, "first_attempt_at": "2026-10-01T00:00:00Z", "latest_outcome": "pending", "amount_cents": 400},
    ]
    rec = health_api.recovery_for(rows)
    assert (rec.affected_payments, rec.recovered_payments, rec.recovered_within_window, rec.unresolved_payments, rec.unresolved_retry_pending) == (3, 2, 1, 1, 1)
    assert (rec.affected_cents, rec.recovered_cents, rec.unresolved_cents) == (700, 300, 400)


def test_failure_signal_labels_match_the_seed_catalogue() -> None:
    assert FAILURE_SIGNAL_LABELS == S.DECLINE_CODES
    assert get_args(FailureCode) == tuple(FAILURE_SIGNAL_LABELS)


# --------------------------------------------------------------------- merchant isolation


def insert_failed_payment(db: Path, merchant_id: str, channel: str, suffix: str) -> None:
    """A payment with one failed attempt for another merchant, created on the clock's day."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO payment (id, merchant_id, customer_id, location_id, order_reference, description, amount_cents, currency, channel, created_at) "
        "VALUES (?, ?, NULL, NULL, ?, 'Isolation probe', 999999, 'USD', ?, '2026-10-05T13:00:00Z')",
        (f"pay_{suffix}", merchant_id, f"ISO-{suffix}", channel),
    )
    conn.execute(
        "INSERT INTO payment_attempt (id, merchant_id, payment_id, attempt_number, method_type, card_brand, card_last4, wallet_type, outcome, failure_code, "
        "failure_message, created_at, completed_at) VALUES (?, ?, ?, 1, 'card', 'visa', '0000', NULL, 'failed', 'lost_or_stolen', 'Card reported lost or stolen', "
        "'2026-10-05T13:00:00Z', '2026-10-05T13:00:02Z')",
        (f"att_{suffix}", merchant_id, f"pay_{suffix}"),
    )
    conn.commit()
    conn.close()


def test_another_merchants_records_never_reach_payment_health(client_as, db_copy: Path, ids: Ids) -> None:
    maya, priya = client_as("maya"), client_as("priya")
    queries = [
        "/api/payment-health?period=last_7_days",
        "/api/payment-health?period=last_7_days&channel=website",
        "/api/attempts?period=last_7_days&outcome=failed&failure_code=lost_or_stolen",
        "/api/payments?period=last_7_days&recovery=unresolved",
        "/api/payments?period=last_7_days&recovery=affected",
    ]
    alder_before = [maya.get(q).json() for q in queries]
    juniper_before = priya.get("/api/payment-health?period=last_7_days&channel=website").json()

    insert_failed_payment(db_copy, ids.merchant("juniper-trail"), "website", "zzzzzzzzzzzzzz")

    assert [maya.get(q).json() for q in queries] == alder_before
    for body in alder_before:
        assert_scoped(ids, body, ids.merchant("alder-loom"))
    juniper_after = priya.get("/api/payment-health?period=last_7_days&channel=website").json()
    assert juniper_after["recovery"]["unresolved_payments"] == juniper_before["recovery"]["unresolved_payments"] + 1
    assert juniper_after["summary"]["period"]["failed"] == juniper_before["summary"]["period"]["failed"] + 1
    assert juniper_after["unresolved"][0]["id"] == "pay_zzzzzzzzzzzzzz"


def test_merchants_see_disjoint_unresolved_payments(client_as, ids: Ids) -> None:
    seen: dict[str, set[str]] = {}
    for persona in ("maya", "priya", "sam_copper"):
        body = client_as(persona).get("/api/payment-health?period=month_to_date").json()
        seen[persona] = assert_scoped(ids, body, merchant_of(ids, persona))
    assert not (seen["maya"] & seen["priya"]) and not (seen["maya"] & seen["sam_copper"]) and not (seen["priya"] & seen["sam_copper"])
