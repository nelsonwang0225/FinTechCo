"""Payment Health: attempt figures reconcile with the attempt rows and the Attempts drill-down, each channel is assessed
against its own baseline by the documented integer rule, recovery is counted once per payment, and the edge cases
(no completed attempts, low volume, no failures, pending attempts) never produce a fabricated rate."""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
from math import floor
from typing import get_args

import pytest

from app.api.attempts import FailureCode
from app.api.payment_health import recovery
from app.core import clock, health, periods
from app.core.labels import FAILURE_CODE_LABELS
from app.core.tz import chicago_day_bounds, chicago_range
from app.seed import scenario as S
from tests.conftest import PERSONAS, Ids, assert_scoped
from tests.test_seed_history import chains, declined, recovered

CHANNELS = ["website", "mobile_app", "in_store"]


def oracle_rate(succeeded: int, completed: int) -> int | None:
    return None if completed == 0 else floor(Fraction(succeeded * 10000, completed) + Fraction(1, 2))


def attempt_counts(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> Counter[str]:
    sql = (
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ?"
    )
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    return Counter({outcome: n for outcome, n in seeded_rows(conn, sql + " GROUP BY a.outcome", params)})


def seeded_rows(conn: sqlite3.Connection, sql: str, params: list[object]) -> list[tuple]:
    return [tuple(r) for r in conn.execute(sql, params).fetchall()]


def assert_stats(stats: dict, counts: Counter[str]) -> None:
    assert stats["succeeded"] == counts["succeeded"]
    assert stats["failed"] == counts["failed"]
    assert stats["pending"] == counts["pending"]
    assert stats["completed"] == counts["succeeded"] + counts["failed"]
    assert stats["success_rate_bps"] == oracle_rate(counts["succeeded"], counts["succeeded"] + counts["failed"])


def merchant_of(ids: Ids, persona: str) -> str:
    return ids.merchants[PERSONAS[persona][1]]


# ------------------------------------------------------------------ attempt-level figures


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("preset", ["last_7_days", "last_30_days", "month_to_date"])
def test_attempt_figures_match_an_independent_recomputation(client_as, seeded_conn, ids: Ids, persona: str, preset: str) -> None:
    merchant_id = merchant_of(ids, persona)
    period = periods.resolve(preset, clock.now(seeded_conn))
    base_start, base_end = chicago_range(period.from_day - timedelta(days=30), period.from_day - timedelta(days=1))
    r = client_as(persona).get(f"/api/payment-health?period={preset}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert_scoped(ids, body, merchant_id)

    assert body["period"]["from_date"] == period.from_day.isoformat()
    assert body["baseline"]["from_date"] == (period.from_day - timedelta(days=30)).isoformat()
    assert body["baseline"]["to_date"] == (period.from_day - timedelta(days=1)).isoformat()
    assert body["channel"] is None
    assert [c["channel"] for c in body["channels"]] == CHANNELS

    assert_stats(body["summary"]["period"], attempt_counts(seeded_conn, merchant_id, period.start, period.end))
    assert_stats(body["summary"]["baseline"], attempt_counts(seeded_conn, merchant_id, base_start, base_end))
    for ch in body["channels"]:
        assert_stats(ch["period"], attempt_counts(seeded_conn, merchant_id, period.start, period.end, ch["channel"]))
        assert_stats(ch["baseline"], attempt_counts(seeded_conn, merchant_id, base_start, base_end, ch["channel"]))

    # The trend partitions the period's attempts by Chicago day.
    days = periods.day_buckets(period)
    assert [p["day"] for p in body["trend"]] == [d.isoformat() for d in days]
    for key in ("succeeded", "failed", "pending"):
        assert sum(p[key] for p in body["trend"]) == body["summary"]["period"][key]
    for point in body["trend"]:
        start, end = chicago_day_bounds(date.fromisoformat(point["day"]))
        assert_stats(point, attempt_counts(seeded_conn, merchant_id, start, end))
        assert point["low_volume"] == (point["completed"] < health.LOW_VOLUME_DAY_COMPLETED)

    # Recorded failure signals reconcile to the failed attempts.
    signals = dict(
        seeded_rows(
            seeded_conn,
            "SELECT failure_code, COUNT(*) FROM payment_attempt WHERE merchant_id = ? AND outcome = 'failed' AND created_at >= ? AND created_at < ? "
            "GROUP BY failure_code",
            [merchant_id, period.start, period.end],
        )
    )
    assert {s["failure_code"]: s["failed_attempts"] for s in body["failure_signals"]} == signals
    assert sum(s["failed_attempts"] for s in body["failure_signals"]) == body["summary"]["period"]["failed"]
    counts = [s["failed_attempts"] for s in body["failure_signals"]]
    assert counts == sorted(counts, reverse=True)
    assert all(s["label"] == FAILURE_CODE_LABELS[s["failure_code"]] for s in body["failure_signals"])


def test_figures_match_the_attempts_drill_down(client_as) -> None:
    maya = client_as("maya")
    scope = "period=last_7_days&channel=mobile_app"
    body = maya.get(f"/api/payment-health?{scope}").json()
    assert body["channel"] == "mobile_app" and body["channel_label"] == "Mobile app"
    for outcome in ("succeeded", "failed", "pending"):
        listed = maya.get(f"/api/attempts?{scope}&outcome={outcome}&page_size=1").json()["total"]
        assert listed == body["summary"]["period"][outcome], outcome
    assert body["failure_signals"], "the staged incident records failure signals"
    for signal in body["failure_signals"]:
        listed = maya.get(f"/api/attempts?{scope}&outcome=failed&failure_code={signal['failure_code']}&page_size=1").json()["total"]
        assert listed == signal["failed_attempts"], signal["failure_code"]


def test_channel_filter_scopes_every_figure_but_the_channel_table(client_as) -> None:
    maya = client_as("maya")
    everything = maya.get("/api/payment-health?period=month_to_date").json()
    mobile = maya.get("/api/payment-health?period=month_to_date&channel=mobile_app").json()
    assert mobile["channels"] == everything["channels"]
    by_channel = {c["channel"]: c for c in everything["channels"]}
    assert mobile["summary"]["period"] == by_channel["mobile_app"]["period"]
    assert mobile["summary"]["baseline"] == by_channel["mobile_app"]["baseline"]
    assert sum(p["completed"] for p in mobile["trend"]) == by_channel["mobile_app"]["period"]["completed"]
    assert sum(s["failed_attempts"] for s in mobile["failure_signals"]) == by_channel["mobile_app"]["period"]["failed"]
    assert mobile["recovery"]["affected_payments"] < everything["recovery"]["affected_payments"]
    assert all(p["channel"] == "mobile_app" for p in mobile["unresolved_payments"]["items"])


# ------------------------------------------------------------------ degradation against the baseline


@pytest.mark.parametrize("preset", ["last_7_days", "month_to_date"])
def test_the_staged_app_incident_is_the_only_degraded_channel(client_as, preset: str) -> None:
    body = client_as("maya").get(f"/api/payment-health?period={preset}").json()
    assessments = {c["channel"]: c["assessment"] for c in body["channels"]}
    assert assessments == {"website": "normal", "mobile_app": "degraded", "in_store": "normal"}
    mobile = next(c for c in body["channels"] if c["channel"] == "mobile_app")
    assert mobile["assessment_label"] == "Degraded"
    assert mobile["delta_bps"] == mobile["period"]["success_rate_bps"] - mobile["baseline"]["success_rate_bps"]
    assert mobile["delta_bps"] <= -health.DEGRADED_DROP_BPS


def test_low_volume_channels_are_not_evaluated(client_as) -> None:
    body = client_as("sam_copper").get("/api/payment-health?period=last_7_days").json()
    by_channel = {c["channel"]: c for c in body["channels"]}
    for channel in ("website", "mobile_app"):
        assert by_channel[channel]["period"]["completed"] < health.MIN_PERIOD_COMPLETED
        assert by_channel[channel]["assessment"] == "insufficient_data"
        assert by_channel[channel]["assessment_label"] == "Not enough data"
    assert by_channel["in_store"]["assessment"] == "normal"


def test_a_channel_without_traffic_has_no_rate(client_as) -> None:
    body = client_as("priya").get("/api/payment-health?period=last_7_days").json()
    mobile = next(c for c in body["channels"] if c["channel"] == "mobile_app")
    assert mobile["assessment"] == "no_attempts"
    assert mobile["period"]["success_rate_bps"] is None and mobile["baseline"]["success_rate_bps"] is None
    assert mobile["delta_bps"] is None
    assert not any(c["assessment"] == "degraded" for c in body["channels"])


def test_a_thin_baseline_draws_no_conclusion(client_as) -> None:
    """The 30 days before last_30_days are almost entirely before the seeded history."""
    body = client_as("maya").get("/api/payment-health?period=last_30_days").json()
    for channel in body["channels"]:
        assert channel["baseline"]["completed"] < health.MIN_BASELINE_COMPLETED
        assert channel["assessment"] == "insufficient_data"


# ------------------------------------------------------------------ edge cases


def test_a_period_with_only_pending_attempts_has_no_rate(client_as) -> None:
    body = client_as("sam_copper").get("/api/payment-health?period=custom&from=2026-10-05&to=2026-10-05&channel=website").json()
    period = body["summary"]["period"]
    assert period["completed"] == 0 and period["pending"] == 2
    assert period["success_rate_bps"] is None
    assert body["summary"]["delta_bps"] is None
    assert body["trend"] == [
        {"day": "2026-10-05", "succeeded": 0, "failed": 0, "pending": 2, "completed": 0, "success_rate_bps": None, "low_volume": True}
    ]
    assert body["failure_signals"] == []


def test_a_period_without_failures_has_no_signals_and_nothing_affected(client_as) -> None:
    body = client_as("sam_copper").get("/api/payment-health?period=month_to_date&channel=mobile_app").json()
    assert body["summary"]["period"]["failed"] == 0
    assert body["summary"]["period"]["success_rate_bps"] == 10000
    assert body["failure_signals"] == []
    assert body["recovery"]["affected_payments"] == 0 and body["recovery"]["affected_cents"] == 0
    assert body["unresolved_payments"] == {"items": [], "total": 0}


@pytest.mark.parametrize(
    "query",
    ["period=yesterday", "period=custom", "from=2026-10-05&to=2026-10-01", "channel=kiosk", "channel=Website"],
)
def test_invalid_scope_is_422(client_as, query: str) -> None:
    r = client_as("maya").get(f"/api/payment-health?{query}")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"


# ------------------------------------------------------------------ recovery per payment


@pytest.mark.parametrize("query", ["period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app", "period=last_7_days", "period=month_to_date"])
def test_recovery_is_counted_once_per_payment(client_as, seeded_conn, ids: Ids, query: str) -> None:
    maya = client_as("maya")
    body = maya.get(f"/api/payment-health?{query}").json()
    merchant_id = ids.merchant("alder-loom")
    start, end = chicago_range(date.fromisoformat(body["period"]["from_date"]), date.fromisoformat(body["period"]["to_date"]))
    sql = "SELECT id, amount_cents, status FROM payment_summary WHERE merchant_id = ? AND created_at >= ? AND created_at < ?"
    params: list[object] = [merchant_id, start, end]
    if body["channel"]:
        sql += " AND channel = ?"
        params.append(body["channel"])
    payments = {pid: (amount, status) for pid, amount, status in seeded_rows(seeded_conn, sql, params)}
    attempt_chains = chains(seeded_conn, set(payments))
    affected = {pid for pid, chain in attempt_chains.items() if declined(chain)}
    succeeded = {pid for pid in affected if any(a["outcome"] == "succeeded" for a in attempt_chains[pid])}
    within = {pid for pid in affected if recovered(attempt_chains[pid])}
    unresolved = {pid for pid in affected - succeeded if attempt_chains[pid][-1]["outcome"] == "failed"}
    retry_pending = {pid for pid in affected - succeeded if attempt_chains[pid][-1]["outcome"] == "pending"}

    def cents(group: set[str]) -> int:
        return sum(payments[pid][0] for pid in group)

    rec = body["recovery"]
    assert rec["affected_payments"] == len(affected) and rec["affected_cents"] == cents(affected)
    assert rec["recovered_payments"] == len(succeeded) and rec["recovered_cents"] == cents(succeeded)
    assert rec["recovered_within_window_payments"] == len(within) and rec["recovered_within_window_cents"] == cents(within)
    assert rec["unresolved_payments"] == len(unresolved) and rec["unresolved_cents"] == cents(unresolved)
    assert rec["retry_pending_payments"] == len(retry_pending) and rec["retry_pending_cents"] == cents(retry_pending)
    assert rec["affected_payments"] == rec["recovered_payments"] + rec["unresolved_payments"] + rec["retry_pending_payments"]
    assert rec["affected_cents"] == rec["recovered_cents"] + rec["unresolved_cents"] + rec["retry_pending_cents"]
    assert rec["currency"] == "USD"
    # Unresolved is exactly the derived "failed" payment status.
    assert unresolved == {pid for pid in affected if payments[pid][1] == "failed"}

    # The unresolved preview is the first page of the Payments list filtered to status=failed.
    listed = maya.get(f"/api/payments?{query}&status=failed&page_size=10").json()
    assert body["unresolved_payments"]["total"] == listed["total"] == rec["unresolved_payments"]
    assert [p["id"] for p in body["unresolved_payments"]["items"]] == [p["id"] for p in listed["items"]]


def test_the_staged_incident_has_recoveries_and_unresolved_payments(client_as) -> None:
    rec = client_as("maya").get("/api/payment-health?period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app").json()["recovery"]
    assert rec["recovered_within_window_payments"] >= 23
    assert rec["unresolved_payments"] >= 9


def test_recovery_groups_follow_the_payment_status() -> None:
    """Paths the seed does not exercise: a slow recovery and a retry still pending after a failure."""
    rows = [
        {"created_at": "2026-10-01T15:00:00Z", "amount_cents": 1000, "status": "succeeded", "succeeded_attempt_id": "att_a", "succeeded_at": "2026-10-01T15:59:59Z"},
        {"created_at": "2026-10-01T15:00:00Z", "amount_cents": 2000, "status": "refunded", "succeeded_attempt_id": "att_b", "succeeded_at": "2026-10-01T16:00:01Z"},
        {"created_at": "2026-10-01T15:00:00Z", "amount_cents": 4000, "status": "pending", "succeeded_attempt_id": None, "succeeded_at": None},
        {"created_at": "2026-10-01T15:00:00Z", "amount_cents": 8000, "status": "failed", "succeeded_attempt_id": None, "succeeded_at": None},
    ]
    rec = recovery(rows)  # type: ignore[arg-type]
    assert (rec.affected_payments, rec.affected_cents) == (4, 15000)
    assert (rec.recovered_payments, rec.recovered_cents) == (2, 3000)
    assert (rec.recovered_within_window_payments, rec.recovered_within_window_cents) == (1, 1000)
    assert (rec.retry_pending_payments, rec.retry_pending_cents) == (1, 4000)
    assert (rec.unresolved_payments, rec.unresolved_cents) == (1, 8000)


# ------------------------------------------------------------------ the rule itself


@pytest.mark.parametrize(
    "succeeded,completed,expected",
    [(0, 0, None), (0, 5, 0), (5, 5, 10000), (1, 3, 3333), (2, 3, 6667), (1, 32, 313), (1, 64, 156), (134, 186, 7204)],
)
def test_rate_is_basis_points_rounded_half_up(succeeded: int, completed: int, expected: int | None) -> None:
    assert health.rate_bps(succeeded, completed) == expected == oracle_rate(succeeded, completed)


def test_degraded_is_exact_at_the_threshold() -> None:
    baseline = health.Counts(succeeded=10000, failed=0)
    assert health.is_degraded(health.Counts(succeeded=9000, failed=1000), baseline)  # exactly 10.00 points
    assert not health.is_degraded(health.Counts(succeeded=9001, failed=999), baseline)  # 9.99 points
    # Rounded rates would both show 90.0% vs 100.0%; the rule uses the raw counts.
    assert not health.is_degraded(health.Counts(succeeded=90004, failed=9996), health.Counts(succeeded=100, failed=0))


def test_assessment_needs_enough_completed_attempts_on_both_sides() -> None:
    enough_baseline = health.Counts(succeeded=health.MIN_BASELINE_COMPLETED, failed=0)
    bad = health.Counts(succeeded=0, failed=health.MIN_PERIOD_COMPLETED)
    assert health.assess(health.Counts(pending=3), enough_baseline) == "no_attempts"
    assert health.assess(health.Counts(succeeded=0, failed=health.MIN_PERIOD_COMPLETED - 1), enough_baseline) == "insufficient_data"
    assert health.assess(bad, health.Counts(succeeded=health.MIN_BASELINE_COMPLETED - 1)) == "insufficient_data"
    assert health.assess(bad, enough_baseline) == "degraded"
    assert health.assess(health.Counts(succeeded=health.MIN_PERIOD_COMPLETED), enough_baseline) == "normal"


def test_recovery_window_is_inclusive() -> None:
    assert health.recovered_within("2026-10-01T15:00:00Z", "2026-10-01T16:00:00Z")
    assert not health.recovered_within("2026-10-01T15:00:00Z", "2026-10-01T16:00:01Z")


def test_baseline_is_the_thirty_days_before_the_period() -> None:
    assert health.baseline_days(date(2026, 9, 29)) == (date(2026, 8, 30), date(2026, 9, 28))


def test_failure_signal_labels_match_the_recorded_codes() -> None:
    assert FAILURE_CODE_LABELS == S.DECLINE_CODES
    assert get_args(FailureCode) == tuple(FAILURE_CODE_LABELS)
