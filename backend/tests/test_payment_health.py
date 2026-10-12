"""Payment Health: every figure is an independent recomputation from raw attempt and payment rows, recovery counts
payments once, the degradation rule is exact, low-volume and empty periods draw no conclusion, and every figure stays
inside the session's merchant."""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import Any

import pytest

from app.core import clock, health, periods
from app.core.labels import FAILURE_CODE_LABELS
from app.core.tz import chicago_day, chicago_range, parse_iso
from app.seed.scenario import DECLINE_CODES
from tests.conftest import PERSONAS, Ids, assert_scoped, collect_ids

TOP_KEYS = {
    "as_of", "period", "baseline", "channel", "channel_label", "rules", "attention", "attempts", "trend", "channels", "failure_signals", "recovery",
    "unresolved",
}
SUMMARY_KEYS = {
    "succeeded", "failed", "pending", "completed", "success_rate_bp", "baseline_succeeded", "baseline_failed", "baseline_completed",
    "baseline_success_rate_bp", "change_bp",
}
CHANNELS = ("website", "mobile_app", "in_store")


def floats_in(payload: Any) -> list[float]:
    if isinstance(payload, float):
        return [payload]
    if isinstance(payload, dict):
        return [f for v in payload.values() for f in floats_in(v)]
    if isinstance(payload, list):
        return [f for v in payload for f in floats_in(v)]
    return []


# --- independent recomputation: plain rows, Python arithmetic, no shared code with the endpoint -----------------------


def attempt_rows(conn: sqlite3.Connection, merchant_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.id, a.payment_id, a.attempt_number, a.outcome, a.failure_code, a.created_at, a.completed_at, p.channel, p.amount_cents, "
        "p.created_at AS payment_created_at FROM payment_attempt a JOIN payment p ON p.id = a.payment_id WHERE a.merchant_id = ? AND p.merchant_id = ?",
        (merchant_id, merchant_id),
    ).fetchall()


def outcome_counts(rows: list[sqlite3.Row], start: str, end: str, channel: str | None) -> Counter[str]:
    return Counter(r["outcome"] for r in rows if start <= r["created_at"] < end and (channel is None or r["channel"] == channel))


def expected_rate(succeeded: int, failed: int) -> int | None:
    completed = succeeded + failed
    if completed == 0:
        return None
    # round(x) on an exact half would be banker's rounding; compare with half-up by hand.
    whole, rest = divmod(succeeded * 10000, completed)
    return whole + (1 if rest * 2 >= completed else 0)


def expected_recovery(rows: list[sqlite3.Row], start: str, end: str, channel: str | None) -> dict[str, Any]:
    by_payment: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        if start <= r["payment_created_at"] < end and (channel is None or r["channel"] == channel):
            by_payment.setdefault(r["payment_id"], []).append(r)
    out = Counter()
    for chain in by_payment.values():
        chain.sort(key=lambda r: r["attempt_number"])
        if not any(r["outcome"] == "failed" for r in chain):
            continue
        amount = chain[0]["amount_cents"]
        out["affected_payments"] += 1
        out["affected_cents"] += amount
        success = [r for r in chain if r["outcome"] == "succeeded"]
        if success:
            out["recovered_payments"] += 1
            out["recovered_cents"] += amount
            elapsed = parse_iso(success[0]["completed_at"]) - parse_iso(chain[0]["created_at"])
            if elapsed <= timedelta(hours=1):
                out["recovered_within_window_payments"] += 1
                out["recovered_within_window_cents"] += amount
        elif chain[-1]["outcome"] == "pending":
            out["retry_pending_payments"] += 1
            out["retry_pending_cents"] += amount
        else:
            out["unresolved_payments"] += 1
            out["unresolved_cents"] += amount
    return dict(out)


def get(client, query: str = "") -> dict[str, Any]:
    r = client.get(f"/api/payment-health{query}")
    assert r.status_code == 200, r.text
    return r.json()


# --- shape, roles, scoping ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("persona", ["maya", "daniel", "jordan", "sam", "priya", "sam_copper"])
def test_every_role_gets_health_with_an_exact_key_set_and_no_floats(client_as, ids: Ids, persona: str) -> None:
    body = get(client_as(persona))
    assert set(body) == TOP_KEYS
    assert set(body["attempts"]) == SUMMARY_KEYS
    assert all(set(c) == SUMMARY_KEYS | {"channel", "channel_label", "assessment", "assessment_label"} for c in body["channels"])
    assert body["rules"] == {
        "baseline_days": 30, "degraded_drop_bp": 1000, "min_completed_attempts": 20, "low_volume_day_attempts": 10, "recovery_window_seconds": 3600,
    }
    assert body["period"]["preset"] == "last_7_days"
    assert body["channel"] is None and body["channel_label"] == "All channels"
    assert floats_in(body) == [], "rates are integer basis points"
    assert_scoped(ids, body, ids.merchants[PERSONAS[persona][1]])


def test_anonymous_is_401(client) -> None:
    assert client.get("/api/payment-health").status_code == 401


@pytest.mark.parametrize("persona", ["maya", "priya", "sam", "sam_copper"])
@pytest.mark.parametrize("preset", ["last_7_days", "last_30_days", "month_to_date"])
@pytest.mark.parametrize("channel", [None, *CHANNELS])
def test_figures_match_an_independent_recomputation(
    client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str, channel: str | None
) -> None:
    merchant_id = ids.merchants[PERSONAS[persona][1]]
    rows = attempt_rows(seeded_conn, merchant_id)
    period = periods.resolve(preset, clock.now(seeded_conn))
    base_start, base_end = chicago_range(period.from_day - timedelta(days=30), period.from_day - timedelta(days=1))
    body = get(client_as(persona), f"?period={preset}" + (f"&channel={channel}" if channel else ""))

    assert body["period"]["from_date"] == period.from_day.isoformat() and body["period"]["to_date"] == period.to_day.isoformat()
    assert body["baseline"]["from_date"] == (period.from_day - timedelta(days=30)).isoformat()
    assert body["baseline"]["to_date"] == (period.from_day - timedelta(days=1)).isoformat()

    # Attempt level: counts by outcome, pending outside the denominator, rate in half-up basis points.
    cur = outcome_counts(rows, period.start, period.end, channel)
    base = outcome_counts(rows, base_start, base_end, channel)
    a = body["attempts"]
    assert (a["succeeded"], a["failed"], a["pending"]) == (cur["succeeded"], cur["failed"], cur["pending"])
    assert a["completed"] == cur["succeeded"] + cur["failed"]
    assert a["success_rate_bp"] == expected_rate(cur["succeeded"], cur["failed"])
    assert (a["baseline_succeeded"], a["baseline_failed"]) == (base["succeeded"], base["failed"])
    assert a["baseline_success_rate_bp"] == expected_rate(base["succeeded"], base["failed"])

    # Channels are always all of the merchant's channels; the scope's figures are the selected row's.
    for c in body["channels"]:
        cc = outcome_counts(rows, period.start, period.end, c["channel"])
        cb = outcome_counts(rows, base_start, base_end, c["channel"])
        assert (c["succeeded"], c["failed"], c["pending"]) == (cc["succeeded"], cc["failed"], cc["pending"]), c["channel"]
        assert (c["baseline_succeeded"], c["baseline_failed"]) == (cb["succeeded"], cb["failed"]), c["channel"]
    if channel is None:
        assert sum(c["completed"] for c in body["channels"]) == a["completed"]
    elif any(c["channel"] == channel for c in body["channels"]):
        row = next(c for c in body["channels"] if c["channel"] == channel)
        assert {k: row[k] for k in SUMMARY_KEYS} == a

    # Trend: one entry per Chicago day, summing to the totals, a gap (None) wherever nothing completed.
    assert [d["date"] for d in body["trend"]] == [d.isoformat() for d in periods.day_buckets(period)]
    for key in ("succeeded", "failed", "pending"):
        assert sum(d[key] for d in body["trend"]) == a[key]
    for d in body["trend"]:
        day_rows = [r for r in rows if chicago_day(r["created_at"]).isoformat() == d["date"] and (channel is None or r["channel"] == channel)]
        day = Counter(r["outcome"] for r in day_rows)
        assert (d["succeeded"], d["failed"], d["pending"]) == (day["succeeded"], day["failed"], day["pending"]), d["date"]
        assert d["success_rate_bp"] == expected_rate(day["succeeded"], day["failed"])
        assert d["low_volume"] == (d["completed"] < 10)
        assert d["partial"] == (d["date"] == chicago_day(clock.now(seeded_conn)).isoformat())

    # Recorded failure signals reconcile exactly to the failed attempts.
    signals = Counter(r["failure_code"] for r in rows if r["outcome"] == "failed" and period.start <= r["created_at"] < period.end
                      and (channel is None or r["channel"] == channel))
    assert {s["failure_code"]: s["failed_attempts"] for s in body["failure_signals"]} == dict(signals)
    assert sum(s["failed_attempts"] for s in body["failure_signals"]) == a["failed"]
    assert all(s["label"] == FAILURE_CODE_LABELS[s["failure_code"]] for s in body["failure_signals"])

    # Recovery is per payment, value once per payment, and the three outcomes partition the affected payments.
    rec = body["recovery"]
    expected = expected_recovery(rows, period.start, period.end, channel)
    for key, value in rec.items():
        if key != "currency":
            assert value == expected.get(key, 0), key
    assert rec["affected_payments"] == rec["recovered_payments"] + rec["unresolved_payments"] + rec["retry_pending_payments"]
    assert rec["affected_cents"] == rec["recovered_cents"] + rec["unresolved_cents"] + rec["retry_pending_cents"]
    assert len(body["unresolved"]) == min(rec["unresolved_payments"], 10)
    assert_scoped(ids, body, merchant_id)


def test_unresolved_list_matches_the_failed_status_drill_down(client_as) -> None:
    """'Review all in Payments' links to status=failed with the same period and channel; the counts must agree."""
    c = client_as("maya")
    for query in ("period=month_to_date&channel=mobile_app", "period=last_7_days"):
        body = get(c, f"?{query}")
        listed = c.get(f"/api/payments?{query}&status=failed&page_size=100").json()
        assert listed["total"] == body["recovery"]["unresolved_payments"]
        assert sum(p["amount_cents"] for p in listed["items"]) == body["recovery"]["unresolved_cents"]
        oldest_first = sorted(listed["items"], key=lambda p: (p["created_at"], p["id"]))
        assert [u["id"] for u in body["unresolved"]] == [p["id"] for p in oldest_first[:10]]


def test_same_user_at_two_merchants_sees_only_each_merchants_figures(client_as, ids: Ids) -> None:
    alder = get(client_as("sam"), "?period=last_30_days")
    copper = get(client_as("sam_copper"), "?period=last_30_days")
    alder_ids = assert_scoped(ids, alder, ids.merchant("alder-loom"))
    copper_ids = assert_scoped(ids, copper, ids.merchant("copper-finch"))
    assert alder_ids and not (alder_ids & copper_ids)
    assert alder["attempts"] != copper["attempts"]
    # A channel the merchant does not trade on cannot reach another merchant's attempts.
    juniper = get(client_as("priya"), "?period=last_30_days&channel=mobile_app")
    assert juniper["attempts"]["completed"] == 0 and juniper["recovery"]["affected_payments"] == 0
    assert "mobile_app" not in [c["channel"] for c in juniper["channels"]]
    assert collect_ids(juniper) == set()


# --- the seeded story and edge cases -------------------------------------------------------------------------------------


@pytest.mark.parametrize("preset", ["last_7_days", "month_to_date"])
def test_alder_mobile_app_incident_is_the_only_degraded_channel(client_as, preset: str) -> None:
    body = get(client_as("maya"), f"?period={preset}")
    attention = body["attention"]
    assert attention["status"] == "degraded"
    assert [d["channel"] for d in attention["degraded"]] == ["mobile_app"]
    flagged = attention["degraded"][0]
    row = next(c for c in body["channels"] if c["channel"] == "mobile_app")
    assert flagged["success_rate_bp"] == row["success_rate_bp"] and flagged["failed_attempts"] == row["failed"]
    assert row["baseline_success_rate_bp"] - row["success_rate_bp"] >= 1000
    assert {c["channel"]: c["assessment"] for c in body["channels"]} == {"website": "not_degraded", "mobile_app": "degraded", "in_store": "not_degraded"}


def test_incident_window_signals_and_recovery(client_as) -> None:
    body = get(client_as("maya"), "?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app")
    assert body["failure_signals"][0] == {"failure_code": "issuer_unavailable", "label": "Issuer unavailable", "failed_attempts": 29}
    oct1 = body["trend"][0]
    assert oct1["date"] == "2026-10-01" and oct1["success_rate_bp"] is not None and oct1["success_rate_bp"] < 5000
    rec = body["recovery"]
    # The scripted window alone has 23 payments recovered within the hour and 9 left unresolved.
    assert rec["recovered_within_window_payments"] >= 23
    assert rec["unresolved_payments"] >= 9
    assert all(u["channel"] == "mobile_app" for u in body["unresolved"])
    assert any(u["attempt_count"] == 2 for u in body["unresolved"]), "declined twice still counts as one payment"


def test_low_volume_channel_draws_no_conclusion(client_as) -> None:
    body = get(client_as("sam_copper"), "?period=last_7_days")
    mobile = next(c for c in body["channels"] if c["channel"] == "mobile_app")
    assert mobile["completed"] < 20 and mobile["assessment"] == "insufficient_volume"
    assert "mobile_app" in body["attention"]["insufficient_volume_channels"]
    assert body["attention"]["degraded"] == []


def test_pending_only_day_is_a_gap_with_its_pending_count(client_as) -> None:
    body = get(client_as("sam_copper"), "?period=last_7_days&channel=website")
    today = body["trend"][-1]
    assert today == {
        "date": "2026-10-05", "succeeded": 0, "failed": 0, "pending": today["pending"], "completed": 0, "success_rate_bp": None,
        "low_volume": True, "partial": True,
    }
    assert today["pending"] > 0
    assert body["attempts"]["pending"] >= today["pending"]


def test_period_with_no_failures_has_no_signals_and_nothing_affected(client_as) -> None:
    body = get(client_as("sam_copper"), "?period=last_7_days&channel=website")
    assert body["attempts"]["failed"] == 0 and body["attempts"]["succeeded"] > 0
    assert body["attempts"]["success_rate_bp"] == 10000
    assert body["failure_signals"] == [] and body["unresolved"] == []
    assert body["recovery"]["affected_payments"] == 0


def test_period_with_no_attempts_fabricates_no_rate(client_as) -> None:
    body = get(client_as("maya"), "?period=custom&from=2026-01-01&to=2026-01-07")
    assert body["attention"] == {"status": "no_completed_attempts", "degraded": [], "insufficient_volume_channels": []}
    assert body["attempts"]["success_rate_bp"] is None and body["attempts"]["change_bp"] is None
    assert all(d["success_rate_bp"] is None for d in body["trend"])
    assert body["channels"] == [] and body["failure_signals"] == [] and body["unresolved"] == []


@pytest.mark.parametrize(
    "query",
    ["?channel=phone", "?period=yesterday", "?period=custom", "?period=custom&from=2026-10-05&to=2026-10-01", "?from=2024-01-01&to=2026-01-01"],
)
def test_bad_parameters_are_422(client_as, query: str) -> None:
    r = client_as("maya").get(f"/api/payment-health{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


# --- the rule itself ----------------------------------------------------------------------------------------------------


def test_rate_is_half_up_basis_points_and_none_without_completed_attempts() -> None:
    assert health.rate_bp(0, 0) is None
    assert health.rate_bp(1, 3) == 3333
    assert health.rate_bp(2, 3) == 6667
    assert health.rate_bp(1, 8) == 1250
    assert health.rate_bp(1, 16) == 625  # 625.0 exactly
    assert health.rate_bp(1, 32) == 313  # 312.5 rounds up


def test_degraded_is_exact_at_the_threshold_and_needs_volume_on_both_sides() -> None:
    # 90% baseline; 80% is exactly 10.0 points lower -> degraded; 80.1% is not.
    assert health.assess(80, 100, 90, 100) == "degraded"
    assert health.assess(801, 1000, 90, 100) == "not_degraded"
    assert health.assess(10, 19, 90, 100) == "insufficient_volume"
    assert health.assess(10, 100, 18, 19) == "insufficient_volume"
    assert health.assess(100, 100, 50, 100) == "not_degraded"  # improvement is never degraded


def test_baseline_is_the_thirty_days_before_the_period() -> None:
    assert health.baseline_days(date(2026, 10, 1)) == (date(2026, 9, 1), date(2026, 9, 30))


def test_failure_code_labels_match_the_seeded_decline_codes() -> None:
    assert FAILURE_CODE_LABELS == DECLINE_CODES
