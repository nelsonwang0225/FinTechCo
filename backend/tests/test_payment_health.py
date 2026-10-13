"""Payment Health: every figure is an independent recomputation from payment_attempt and payment rows.

Attempt figures (rates, channels, trend, failure signals) count attempts by payment_attempt.created_at. Recovery counts
payments with a failed attempt by payment.created_at, once per payment. Drill-down totals equal the existing lists.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import get_args
from urllib.parse import urlencode

import pytest

from app.api import attempts as attempts_api
from app.core import clock, health, periods
from app.core.labels import FAILURE_CODE_LABELS
from app.core.tz import chicago_day_bounds, chicago_range, parse_iso
from app.seed import scenario
from tests.conftest import PERSONAS, Ids, assert_scoped

CHANNELS = ("website", "mobile_app", "in_store")
APP_WINDOW = {"period": "custom", "from": "2026-10-01", "to": "2026-10-02", "channel": "mobile_app"}


def get(client, **params: str):
    r = client.get("/api/payment-health?" + urlencode(params))
    assert r.status_code == 200, r.text
    return r.json()


def outcomes(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> Counter[str]:
    sql = (
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ?"
    )
    args: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        args.append(channel)
    return Counter(dict(conn.execute(sql + " GROUP BY a.outcome", args).fetchall()))


def expected_stats(counts: Counter[str]) -> dict[str, object]:
    completed = counts["succeeded"] + counts["failed"]
    rate = None if completed == 0 else (counts["succeeded"] * 20000 + completed) // (completed * 2)
    return {"succeeded": counts["succeeded"], "failed": counts["failed"], "pending": counts["pending"], "completed": completed, "success_rate_bps": rate}


def chains(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None) -> dict[str, list[sqlite3.Row]]:
    """Every attempt of every payment created in [start, end), grouped by payment, in attempt order."""
    sql = (
        "SELECT a.*, p.amount_cents FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE p.merchant_id = ? AND p.created_at >= ? AND p.created_at < ?"
    )
    args: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        args.append(channel)
    out: dict[str, list[sqlite3.Row]] = {}
    for row in conn.execute(sql + " ORDER BY a.payment_id, a.attempt_number", args):
        out.setdefault(row["payment_id"], []).append(row)
    return out


def expected_recovery(chain_map: dict[str, list[sqlite3.Row]]) -> dict[str, int]:
    affected = {pid: c for pid, c in chain_map.items() if any(a["outcome"] == "failed" for a in c)}
    recovered = {pid: c for pid, c in affected.items() if any(a["outcome"] == "succeeded" for a in c)}
    awaiting = {pid: c for pid, c in affected.items() if pid not in recovered and c[-1]["outcome"] == "pending"}
    unresolved = {pid: c for pid, c in affected.items() if pid not in recovered and pid not in awaiting}

    def within(c: list[sqlite3.Row]) -> bool:
        success = next(a for a in c if a["outcome"] == "succeeded")
        return parse_iso(success["completed_at"]) - parse_iso(c[0]["created_at"]) <= timedelta(hours=1)

    def value(group: dict[str, list[sqlite3.Row]]) -> int:
        return sum(c[0]["amount_cents"] for c in group.values())

    return {
        "affected_payments": len(affected),
        "recovered_payments": len(recovered),
        "recovered_within_window_payments": sum(within(c) for c in recovered.values()),
        "unresolved_payments": len(unresolved),
        "awaiting_outcome_payments": len(awaiting),
        "affected_value_cents": value(affected),
        "recovered_value_cents": value(recovered),
        "unresolved_value_cents": value(unresolved),
        "awaiting_outcome_value_cents": value(awaiting),
    }


# --------------------------------------------------------------------- reconciliation


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("preset", ["last_7_days", "last_30_days", "month_to_date"])
def test_figures_match_an_independent_recomputation(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str) -> None:
    merchant_id = ids.merchants[PERSONAS[persona][1]]
    period = periods.resolve(preset, clock.now(seeded_conn))
    baseline_from, baseline_to = period.from_day - timedelta(days=30), period.from_day - timedelta(days=1)
    baseline_start, baseline_end = chicago_range(baseline_from, baseline_to)
    body = get(client_as(persona), period=preset)

    assert body["period"]["from_date"] == period.from_day.isoformat() and body["period"]["to_date"] == period.to_day.isoformat()
    assert (body["baseline"]["from_date"], body["baseline"]["to_date"]) == (baseline_from.isoformat(), baseline_to.isoformat())
    assert body["channel"] is None

    # Summary and channels: attempt counts by created_at; the channel rows add up to the summary.
    assert body["summary"]["period"] == expected_stats(outcomes(seeded_conn, merchant_id, period.start, period.end))
    assert body["summary"]["baseline"] == expected_stats(outcomes(seeded_conn, merchant_id, baseline_start, baseline_end))
    assert [c["channel"] for c in body["channels"]] == list(CHANNELS)
    for row in body["channels"]:
        assert row["period"] == expected_stats(outcomes(seeded_conn, merchant_id, period.start, period.end, row["channel"]))
        assert row["baseline"] == expected_stats(outcomes(seeded_conn, merchant_id, baseline_start, baseline_end, row["channel"]))
    for key in ("succeeded", "failed", "pending"):
        assert sum(c["period"][key] for c in body["channels"]) == body["summary"]["period"][key]

    # Trend: one point per Chicago day, each its own count, summing to the summary.
    assert [p["date"] for p in body["trend"]] == [d.isoformat() for d in periods.day_buckets(period)]
    for point in body["trend"]:
        day_start, day_end = chicago_day_bounds(date.fromisoformat(point["date"]))
        stats = expected_stats(outcomes(seeded_conn, merchant_id, day_start, day_end))
        assert {k: point[k] for k in stats} == stats
        assert point["low_volume"] == (0 < point["completed"] < health.LOW_VOLUME_DAY_ATTEMPTS)
    for key in ("succeeded", "failed", "pending"):
        assert sum(p[key] for p in body["trend"]) == body["summary"]["period"][key]

    # Failure signals reconcile to the failed attempts.
    expected_codes = dict(
        seeded_conn.execute(
            "SELECT failure_code, COUNT(*) FROM payment_attempt WHERE merchant_id = ? AND outcome = 'failed' AND created_at >= ? AND created_at < ? "
            "GROUP BY failure_code",
            (merchant_id, period.start, period.end),
        ).fetchall()
    )
    assert {s["failure_code"]: s["failed_attempts"] for s in body["failure_signals"]} == expected_codes
    assert sum(s["failed_attempts"] for s in body["failure_signals"]) == body["summary"]["period"]["failed"]
    assert all(s["label"] == FAILURE_CODE_LABELS[s["failure_code"]] for s in body["failure_signals"])
    counts = [s["failed_attempts"] for s in body["failure_signals"]]
    assert counts == sorted(counts, reverse=True)

    # Recovery: by payment, once per payment, partitioned.
    recovery = body["recovery"]
    assert {k: recovery[k] for k in recovery if k != "currency"} == expected_recovery(chains(seeded_conn, merchant_id, period.start, period.end, None))
    assert recovery["affected_payments"] == recovery["recovered_payments"] + recovery["unresolved_payments"] + recovery["awaiting_outcome_payments"]
    assert recovery["affected_value_cents"] == recovery["recovered_value_cents"] + recovery["unresolved_value_cents"] + recovery["awaiting_outcome_value_cents"]
    assert recovery["recovered_within_window_payments"] <= recovery["recovered_payments"]
    assert recovery["currency"] == "USD"
    assert body["unresolved"]["total"] == recovery["unresolved_payments"]
    assert_scoped(ids, body, merchant_id)


def test_channel_scope_narrows_every_attempt_and_payment_figure(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchant("alder-loom")
    start, end = chicago_range(date(2026, 10, 1), date(2026, 10, 2))
    body = get(client_as("maya"), **APP_WINDOW)
    assert body["channel"] == "mobile_app"
    assert body["summary"]["period"] == expected_stats(outcomes(seeded_conn, merchant_id, start, end, "mobile_app"))
    assert body["summary"]["period"] == next(c for c in body["channels"] if c["channel"] == "mobile_app")["period"]
    assert len(body["channels"]) == 3, "the channel table and attention summary always cover every channel"
    assert sum(p["completed"] for p in body["trend"]) == body["summary"]["period"]["completed"]
    assert {k: body["recovery"][k] for k in body["recovery"] if k != "currency"} == expected_recovery(chains(seeded_conn, merchant_id, start, end, "mobile_app"))
    assert all(item["channel"] == "mobile_app" and item["status"] == "failed" for item in body["unresolved"]["items"])


# --------------------------------------------------------------------- the seeded mobile-app incident


def test_the_scripted_app_checkout_incident_is_detected(client_as) -> None:
    body = get(client_as("maya"), period="last_7_days")
    verdicts = {c["channel"]: c["assessment"] for c in body["channels"]}
    assert verdicts["mobile_app"] == "degraded"
    assert verdicts["website"] == "not_degraded"
    mobile = next(c for c in body["channels"] if c["channel"] == "mobile_app")
    assert mobile["change_bps"] is not None and mobile["change_bps"] <= -health.DEGRADATION_POINTS * 100

    window = get(client_as("maya"), **APP_WINDOW)
    signals = {s["failure_code"]: s["failed_attempts"] for s in window["failure_signals"]}
    assert signals["issuer_unavailable"] >= 29
    assert window["failure_signals"][0]["failure_code"] == "issuer_unavailable"
    recovery = window["recovery"]
    assert recovery["affected_payments"] >= 32 and recovery["recovered_payments"] >= 23 and recovery["unresolved_payments"] >= 9


def test_value_is_counted_once_per_payment_not_per_attempt(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchant("alder-loom")
    start, end = chicago_range(date(2026, 10, 1), date(2026, 10, 2))
    body = get(client_as("maya"), **APP_WINDOW)
    chain_map = chains(seeded_conn, merchant_id, start, end, "mobile_app")
    multi = [c for c in chain_map.values() if sum(a["outcome"] == "failed" for a in c) >= 2]
    assert multi, "the window holds payments declined more than once"
    per_attempt = sum(a["amount_cents"] for c in chain_map.values() for a in c if any(x["outcome"] == "failed" for x in c))
    assert body["recovery"]["affected_value_cents"] < per_attempt


# --------------------------------------------------------------------- drill-down reconciliation


@pytest.mark.parametrize("params", [{"period": "last_7_days"}, {"period": "month_to_date", "channel": "mobile_app"}, APP_WINDOW])
def test_drill_down_totals_equal_the_existing_lists(client_as, params: dict[str, str]) -> None:
    c = client_as("maya")
    body = get(c, **params)
    payments = c.get("/api/payments?" + urlencode({**params, "status": "failed"})).json()
    assert payments["total"] == body["unresolved"]["total"] == body["recovery"]["unresolved_payments"]
    assert [i["id"] for i in body["unresolved"]["items"]] == [i["id"] for i in payments["items"][: len(body["unresolved"]["items"])]]
    assert len(body["unresolved"]["items"]) == min(10, payments["total"])
    for signal in body["failure_signals"]:
        attempts = c.get("/api/attempts?" + urlencode({**params, "outcome": "failed", "failure_code": signal["failure_code"]})).json()
        assert attempts["total"] == signal["failed_attempts"]
    failed = c.get("/api/attempts?" + urlencode({**params, "outcome": "failed"})).json()
    assert failed["total"] == body["summary"]["period"]["failed"]


# --------------------------------------------------------------------- edge cases


def test_only_pending_attempts_give_no_rate_and_no_verdict(client_as) -> None:
    body = get(client_as("sam_copper"), period="custom", **{"from": "2026-10-05", "to": "2026-10-05"}, channel="website")
    summary = body["summary"]
    assert summary["period"]["completed"] == 0 and summary["period"]["pending"] > 0
    assert summary["period"]["success_rate_bps"] is None
    assert summary["change_bps"] is None
    assert summary["assessment"] == "no_completed_attempts"
    assert all(p["success_rate_bps"] is None for p in body["trend"])


def test_low_volume_is_not_evaluated(client_as) -> None:
    body = get(client_as("sam_copper"), period="custom", **{"from": "2026-09-27", "to": "2026-09-27"}, channel="mobile_app")
    assert body["summary"]["period"]["completed"] == 5
    assert body["summary"]["assessment"] == "insufficient_data"
    assert body["trend"][0]["low_volume"] is True and body["trend"][0]["success_rate_bps"] == 6000


def test_a_channel_with_no_attempts_is_reported_as_such(client_as) -> None:
    body = get(client_as("priya"), period="last_7_days")
    mobile = next(c for c in body["channels"] if c["channel"] == "mobile_app")
    assert mobile["period"]["completed"] == 0 and mobile["assessment"] == "no_completed_attempts"


def test_a_short_baseline_is_not_evaluated(client_as) -> None:
    body = get(client_as("maya"), period="last_30_days")
    assert body["baseline"]["from_date"] == "2026-08-07"
    thin = [c for c in body["channels"] if c["baseline"]["completed"] < health.MIN_COMPLETED_ATTEMPTS]
    assert thin and all(c["assessment"] == "insufficient_data" for c in thin)


def test_a_period_with_no_attempts_is_empty_not_fabricated(client_as) -> None:
    body = get(client_as("maya"), period="custom", **{"from": "2026-11-01", "to": "2026-11-07"})
    assert body["summary"]["period"] == {"succeeded": 0, "failed": 0, "pending": 0, "completed": 0, "success_rate_bps": None}
    assert body["summary"]["assessment"] == "no_completed_attempts"
    assert body["failure_signals"] == [] and body["unresolved"] == {"items": [], "total": 0}
    assert body["recovery"]["affected_payments"] == 0
    assert all(p["success_rate_bps"] is None and not p["low_volume"] for p in body["trend"])


def test_a_day_with_no_failures_has_a_full_rate_and_no_signals(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchant("juniper-trail")
    day = None
    for offset in range(25):
        d = date(2026, 9, 6) + timedelta(days=offset)
        start, end = chicago_day_bounds(d)
        counts = outcomes(seeded_conn, merchant_id, start, end, "in_store")
        if counts["failed"] == 0 and counts["succeeded"] > 0:
            day = d
            break
    assert day is not None, "a Juniper in-store day without a failed attempt"
    body = get(client_as("priya"), period="custom", **{"from": day.isoformat(), "to": day.isoformat()}, channel="in_store")
    assert body["summary"]["period"]["failed"] == 0 and body["summary"]["period"]["success_rate_bps"] == 10000
    assert body["failure_signals"] == [] and body["recovery"]["affected_payments"] == 0


# --------------------------------------------------------------------- the rule itself


def test_the_degradation_rule_is_exact_at_the_threshold() -> None:
    baseline = health.AttemptCounts(succeeded=90, failed=10)  # 90%
    assert health.assess(health.AttemptCounts(succeeded=85, failed=15), baseline) == "degraded"  # exactly 5 points below
    assert health.assess(health.AttemptCounts(succeeded=851, failed=149), baseline) == "not_degraded"  # 4.9 points below
    assert health.assess(health.AttemptCounts(succeeded=20, failed=9), baseline) == "insufficient_data"  # 29 completed
    assert health.assess(health.AttemptCounts(succeeded=20, failed=10), baseline) == "degraded"  # 30 completed, 66.7%
    assert health.assess(health.AttemptCounts(succeeded=30), health.AttemptCounts(succeeded=29)) == "insufficient_data"
    assert health.assess(health.AttemptCounts(pending=4), baseline) == "no_completed_attempts"


def test_rates_are_integer_basis_points_rounded_half_up() -> None:
    assert health.rate_bps(0, 0) is None
    assert health.rate_bps(2, 3) == 6667
    assert health.rate_bps(1, 3) == 3333
    assert health.rate_bps(1, 8) == 1250
    assert health.rate_bps(1, 20000) == 1  # 0.5 bps rounds up
    assert health.rate_bps(5, 5) == 10000


def test_failure_code_labels_match_the_seed_catalogue() -> None:
    assert FAILURE_CODE_LABELS == scenario.DECLINE_CODES
    assert set(get_args(attempts_api.FailureCode)) == set(FAILURE_CODE_LABELS), "the attempts filter accepts exactly the recorded codes"


def test_thresholds_are_echoed_for_the_definitions(client_as) -> None:
    body = get(client_as("sam"))
    assert body["thresholds"] == {"min_completed_attempts": 30, "degradation_points": 5, "low_volume_day_attempts": 10, "baseline_days": 30, "recovery_window_minutes": 60}
    assert body["period"]["preset"] == "last_7_days"


# --------------------------------------------------------------------- validation


def test_anonymous_is_401_and_bad_input_is_422(client_as) -> None:
    assert client_as("anon").get("/api/payment-health").status_code == 401
    c = client_as("maya")
    for qs in ("channel=pos", "period=yesterday", "period=custom&from=2026-10-01", "from=2026-10-05&to=2026-10-01", "from=2025-01-01&to=2026-10-05"):
        r = c.get(f"/api/payment-health?{qs}")
        assert r.status_code == 422, qs
        assert r.json()["error"]["code"] == "validation_error"
