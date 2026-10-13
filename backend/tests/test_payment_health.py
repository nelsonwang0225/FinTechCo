"""Payment Health: every figure is an independent recomputation from payment and payment_attempt rows, the degraded rule
behaves as documented on the seeded stories, edge periods never fabricate a rate, and one merchant's rows never move
another merchant's results."""

from __future__ import annotations

import math
import sqlite3
import typing
from collections import Counter, defaultdict
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from app.api import attempts as attempts_api
from app.core import clock, health, periods
from app.core.labels import FAILURE_CODE_LABELS
from app.core.tz import chicago_day_bounds, chicago_range, parse_iso
from app.db.connection import connect
from app.seed import scenario
from tests.conftest import PERSONAS, Ids, assert_scoped

CHANNELS = ("website", "mobile_app", "in_store")
TOP_KEYS = {"period", "baseline_period", "rules", "summary", "attention", "channels", "trend", "failure_signals", "recovery", "unresolved_payments",
            "unresolved_total"}


# ------------------------------------------------------------------ independent recomputation helpers


def attempts_in(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> list[sqlite3.Row]:
    sql = ("SELECT a.payment_id, a.outcome, a.failure_code, a.created_at, p.channel FROM payment_attempt a JOIN payment p ON p.id = a.payment_id "
           "WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ?")
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    return conn.execute(sql, params).fetchall()


def stats(rows: list[sqlite3.Row]) -> dict[str, Any]:
    c = Counter(r["outcome"] for r in rows)
    completed = c["succeeded"] + c["failed"]
    rate = None if completed == 0 else math.floor(Fraction(c["succeeded"] * 10_000, completed) + Fraction(1, 2))
    return {"succeeded": c["succeeded"], "failed": c["failed"], "pending": c["pending"], "completed": completed, "success_rate_bp": rate}


def chains_created_in(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None) -> dict[str, tuple[int, list[sqlite3.Row]]]:
    """payment id -> (amount_cents, attempts in order) for payments created in [start, end)."""
    sql = "SELECT id, amount_cents FROM payment WHERE merchant_id = ? AND created_at >= ? AND created_at < ?"
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND channel = ?"
        params.append(channel)
    amounts = {r["id"]: r["amount_cents"] for r in conn.execute(sql, params)}
    chains: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute("SELECT * FROM payment_attempt WHERE merchant_id = ? ORDER BY payment_id, attempt_number", (merchant_id,)):
        if row["payment_id"] in amounts:
            chains[row["payment_id"]].append(row)
    return {pid: (amounts[pid], chains[pid]) for pid in amounts}


def expected_recovery(chains: dict[str, tuple[int, list[sqlite3.Row]]]) -> dict[str, Any]:
    out: dict[str, Any] = defaultdict(int)
    out["unresolved_ids"] = set()
    for pid, (amount, chain) in chains.items():
        if not any(a["outcome"] == "failed" for a in chain):
            continue
        out["affected_payments"] += 1
        out["affected_cents"] += amount
        out["failed_attempts"] += sum(a["outcome"] == "failed" for a in chain)
        success = [a for a in chain if a["outcome"] == "succeeded"]
        if success:
            out["recovered_payments"] += 1
            out["recovered_cents"] += amount
            if parse_iso(success[0]["completed_at"]) - parse_iso(chain[0]["created_at"]) <= timedelta(hours=1):
                out["recovered_within_window_payments"] += 1
                out["recovered_within_window_cents"] += amount
        elif chain[-1]["outcome"] == "pending":
            out["retry_pending_payments"] += 1
            out["retry_pending_cents"] += amount
        else:
            out["unresolved_payments"] += 1
            out["unresolved_cents"] += amount
            out["unresolved_ids"].add(pid)
    return out


def merchant_of(persona: str, ids: Ids) -> str:
    return ids.merchants[PERSONAS[persona][1]]


# ------------------------------------------------------------------ shape, defaults and validation


def test_default_scope_is_last_7_days_all_channels(client_as, ids: Ids) -> None:
    r = client_as("maya").get("/api/payment-health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == TOP_KEYS
    assert body["period"]["preset"] == "last_7_days"
    assert body["summary"]["channel"] is None and body["summary"]["channel_label"] == "All channels"
    assert [c["channel"] for c in body["channels"]] == list(CHANNELS)
    assert body["baseline_period"]["from_date"] == "2026-08-30" and body["baseline_period"]["to_date"] == "2026-09-28"
    assert body["rules"] == {"baseline_days": 30, "degraded_drop_bp": 1000, "min_period_completed": 50, "min_baseline_completed": 200,
                             "low_volume_day_completed": 10, "recovery_window_minutes": 60}
    assert_scoped(ids, body, ids.merchant("alder-loom"))


@pytest.mark.parametrize("query", ["channel=atm", "period=yesterday", "from=2026-10-05&to=2026-10-01", "from=2026-10-01", "from=2024-01-01&to=2026-10-05"])
def test_invalid_scope_is_422(client_as, query: str) -> None:
    r = client_as("maya").get(f"/api/payment-health?{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_requires_a_session(client) -> None:
    r = client.get("/api/payment-health")
    assert r.status_code == 401


# ------------------------------------------------------------------ reconciliation with the underlying attempts


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("preset", ["last_7_days", "last_30_days", "month_to_date"])
@pytest.mark.parametrize("channel", [None, "mobile_app", "website"])
def test_every_figure_matches_an_independent_recomputation(
    client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str, channel: str | None
) -> None:
    merchant_id = merchant_of(persona, ids)
    period = periods.resolve(preset, clock.now(seeded_conn))
    baseline_start, baseline_end = chicago_range(period.from_day - timedelta(days=30), period.from_day - timedelta(days=1))
    query = f"period={preset}" + (f"&channel={channel}" if channel else "")
    c = client_as(persona)
    body = c.get(f"/api/payment-health?{query}").json()
    assert_scoped(ids, body, merchant_id)

    # Per channel, always all three, regardless of the channel filter.
    for row in body["channels"]:
        assert row["period"] == stats(attempts_in(seeded_conn, merchant_id, period.start, period.end, row["channel"])), row["channel"]
        assert row["baseline"] == stats(attempts_in(seeded_conn, merchant_id, baseline_start, baseline_end, row["channel"])), row["channel"]
    assert sum(row["period"]["failed"] for row in body["channels"]) == stats(attempts_in(seeded_conn, merchant_id, period.start, period.end))["failed"]

    # The scope summary follows the channel filter.
    scope_rows = attempts_in(seeded_conn, merchant_id, period.start, period.end, channel)
    assert body["summary"]["period"] == stats(scope_rows)
    assert body["summary"]["baseline"] == stats(attempts_in(seeded_conn, merchant_id, baseline_start, baseline_end, channel))

    # Daily trend: one point per Chicago day, bucketed on the attempt's created_at, summing to the summary.
    days = periods.day_buckets(period)
    assert [p["day"] for p in body["trend"]] == [d.isoformat() for d in days]
    for point in body["trend"]:
        start, end = chicago_day_bounds(date.fromisoformat(point["day"]))
        expected = stats(attempts_in(seeded_conn, merchant_id, start, end, channel))
        assert {k: point[k] for k in expected} == expected, point["day"]
        assert point["low_volume"] == (0 < point["completed"] < 10)
    for key in ("succeeded", "failed", "pending"):
        assert sum(p[key] for p in body["trend"]) == body["summary"]["period"][key]

    # Recorded failure signals reconcile to the failed attempts.
    signals = Counter(r["failure_code"] for r in scope_rows if r["outcome"] == "failed")
    assert {s["code"]: s["attempts"] for s in body["failure_signals"]} == dict(signals)
    assert sum(s["attempts"] for s in body["failure_signals"]) == body["summary"]["period"]["failed"]
    for s in body["failure_signals"]:
        assert s["label"] == FAILURE_CODE_LABELS[s["code"]]
        assert s["payments"] == len({r["payment_id"] for r in scope_rows if r["failure_code"] == s["code"]})
        drill = c.get(f"/api/attempts?{query}&outcome=failed&failure_code={s['code']}&page_size=1").json()
        assert drill["total"] == s["attempts"], s["code"]

    # Recovery is per payment, by payment.created_at, each payment's amount counted once.
    expected = expected_recovery(chains_created_in(seeded_conn, merchant_id, period.start, period.end, channel))
    recovery = body["recovery"]
    for key in ("affected_payments", "affected_cents", "failed_attempts", "recovered_payments", "recovered_cents", "recovered_within_window_payments",
                "recovered_within_window_cents", "unresolved_payments", "unresolved_cents", "retry_pending_payments", "retry_pending_cents"):
        assert recovery[key] == expected[key], key
    assert recovery["affected_payments"] == recovery["recovered_payments"] + recovery["unresolved_payments"] + recovery["retry_pending_payments"]
    assert recovery["affected_cents"] == recovery["recovered_cents"] + recovery["unresolved_cents"] + recovery["retry_pending_cents"]
    assert recovery["recovered_within_window_payments"] <= recovery["recovered_payments"]

    # The unresolved list is the Payments list's status=failed rows for the same scope.
    payments = c.get(f"/api/payments?{query}&status=failed&page_size=10").json()
    assert body["unresolved_total"] == payments["total"] == recovery["unresolved_payments"]
    assert [p["id"] for p in body["unresolved_payments"]] == [p["id"] for p in payments["items"]]
    assert {p["id"] for p in body["unresolved_payments"]} <= expected["unresolved_ids"]


# ------------------------------------------------------------------ the degraded rule on the seeded stories


def verdicts(body: dict[str, Any]) -> dict[str, str]:
    return {row["channel"]: row["verdict"] for row in body["channels"]}


@pytest.mark.parametrize("preset", ["last_7_days", "month_to_date"])
def test_alder_loom_app_checkout_is_degraded(client_as, preset: str) -> None:
    body = client_as("maya").get(f"/api/payment-health?period={preset}").json()
    assert verdicts(body) == {"website": "not_degraded", "mobile_app": "degraded", "in_store": "not_degraded"}
    assert body["attention"] == {"verdict": "degraded", "degraded_channels": ["mobile_app"]}
    app = next(row for row in body["channels"] if row["channel"] == "mobile_app")
    assert app["verdict_label"] == "Degraded"
    assert app["change_bp"] <= -1000
    assert app["change_bp"] == app["period"]["success_rate_bp"] - app["baseline"]["success_rate_bp"]


def test_last_7_days_app_rates(client_as) -> None:
    app = next(row for row in client_as("maya").get("/api/payment-health").json()["channels"] if row["channel"] == "mobile_app")
    assert app["period"]["success_rate_bp"] == 7204  # 134 of 186 completed
    assert (app["period"]["succeeded"], app["period"]["completed"]) == (134, 186)
    assert app["baseline"]["success_rate_bp"] == 9079


def test_scripted_app_window_shows_in_recovery(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?from=2026-10-01&to=2026-10-02&channel=mobile_app").json()
    recovery = body["recovery"]
    assert recovery["affected_payments"] >= 32
    assert recovery["unresolved_payments"] >= 9
    assert recovery["recovered_within_window_payments"] == recovery["recovered_payments"] >= 23
    codes = {s["code"]: s["attempts"] for s in body["failure_signals"]}
    assert max(codes, key=lambda code: codes[code]) == "issuer_unavailable"


def test_last_30_days_never_concludes_without_baseline_data(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?period=last_30_days").json()
    assert set(verdicts(body).values()) == {"insufficient_data"}
    assert body["attention"] == {"verdict": "not_enough_data", "degraded_channels": []}
    assert all(row["baseline"]["completed"] < 200 for row in body["channels"])


def test_low_volume_channels_are_not_judged(client_as) -> None:
    copper = client_as("sam_copper").get("/api/payment-health").json()
    assert verdicts(copper) == {"website": "insufficient_data", "mobile_app": "insufficient_data", "in_store": "not_degraded"}
    juniper = client_as("priya").get("/api/payment-health").json()
    assert verdicts(juniper) == {"website": "not_degraded", "mobile_app": "no_data", "in_store": "insufficient_data"}
    assert juniper["attention"] == {"verdict": "no_degradation", "degraded_channels": []}


# ------------------------------------------------------------------ edge periods


def test_pending_only_day_has_no_rate(client_as) -> None:
    """Copper Finch's website on the clock's morning: two pending attempts and nothing completed."""
    body = client_as("sam_copper").get("/api/payment-health?from=2026-10-05&to=2026-10-05&channel=website").json()
    assert body["summary"]["period"] == {"succeeded": 0, "failed": 0, "pending": 2, "completed": 0, "success_rate_bp": None}
    assert body["summary"]["change_bp"] is None
    assert body["trend"] == [{"day": "2026-10-05", "succeeded": 0, "failed": 0, "pending": 2, "completed": 0, "success_rate_bp": None, "low_volume": False}]
    assert body["failure_signals"] == []


def test_a_period_before_the_history_is_empty_not_fabricated(client_as) -> None:
    body = client_as("maya").get("/api/payment-health?from=2026-08-01&to=2026-08-07").json()
    assert body["summary"]["period"]["completed"] == 0 and body["summary"]["period"]["success_rate_bp"] is None
    assert all(p["success_rate_bp"] is None and not p["low_volume"] for p in body["trend"])
    assert set(verdicts(body).values()) == {"no_data"}
    assert body["attention"] == {"verdict": "no_data", "degraded_channels": []}
    assert body["failure_signals"] == [] and body["unresolved_payments"] == [] and body["unresolved_total"] == 0
    assert body["recovery"]["affected_payments"] == 0 and body["recovery"]["affected_cents"] == 0


def test_a_day_without_failures_has_no_signals_or_affected_payments(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchant("juniper-trail")
    day = next(
        d for d in (date(2026, 9, 5) + timedelta(days=i) for i in range(30))
        if attempts_in(seeded_conn, merchant_id, *chicago_day_bounds(d), "in_store")
        and not any(r["outcome"] == "failed" for r in attempts_in(seeded_conn, merchant_id, *chicago_day_bounds(d), "in_store"))
        and not any(r["outcome"] == "failed" for chain in chains_created_in(seeded_conn, merchant_id, *chicago_day_bounds(d), "in_store").values()
                    for r in chain[1])
    )
    body = client_as("priya").get(f"/api/payment-health?from={day}&to={day}&channel=in_store").json()
    assert body["summary"]["period"]["failed"] == 0 and body["summary"]["period"]["success_rate_bp"] == 10_000
    assert body["failure_signals"] == []
    assert body["recovery"]["affected_payments"] == 0 and body["unresolved_total"] == 0


# ------------------------------------------------------------------ merchant isolation


def mutate_other_merchants(db: Path, ids: Ids, keep_slug: str) -> None:
    """Rewrite every other merchant's attempts and channels so any leak would change the kept merchant's figures."""
    conn = connect(db)
    try:
        for slug, merchant_id in ids.merchants.items():
            if slug == keep_slug:
                continue
            conn.execute("UPDATE payment SET channel = 'mobile_app' WHERE merchant_id = ? AND channel = 'website'", (merchant_id,))
            conn.execute(
                "UPDATE payment_attempt SET failure_code = 'issuer_unavailable', failure_message = 'Issuer unavailable' WHERE merchant_id = ? AND outcome = 'failed'",
                (merchant_id,),
            )
    finally:
        conn.close()


@pytest.mark.parametrize("keep_slug,persona", [("alder-loom", "maya"), ("juniper-trail", "priya"), ("copper-finch", "sam_copper")])
def test_other_merchants_rows_never_change_the_result(client_as, db_copy: Path, ids: Ids, keep_slug: str, persona: str) -> None:
    c = client_as(persona)
    urls = [
        "/api/payment-health",
        "/api/payment-health?period=month_to_date&channel=mobile_app",
        "/api/payment-health?from=2026-09-05&to=2026-10-05",
        "/api/attempts?period=last_30_days&outcome=failed&failure_code=issuer_unavailable",
    ]
    before = [c.get(u).json() for u in urls]
    mutate_other_merchants(db_copy, ids, keep_slug)
    assert [c.get(u).json() for u in urls] == before
    for body in before:
        assert_scoped(ids, body, ids.merchants[keep_slug])


def test_the_mutation_is_visible_to_the_owning_merchant(client_as, db_copy: Path, ids: Ids) -> None:
    """Guards the isolation test above: the rewrite does change the merchant whose rows it touches."""
    c = client_as("priya")
    before = c.get("/api/payment-health?from=2026-09-05&to=2026-10-05").json()
    mutate_other_merchants(db_copy, ids, "alder-loom")
    after = c.get("/api/payment-health?from=2026-09-05&to=2026-10-05").json()
    assert after["channels"] != before["channels"]
    assert {s["code"] for s in after["failure_signals"]} == {"issuer_unavailable"}


# ------------------------------------------------------------------ rules and labels


def test_rate_is_integer_basis_points_rounded_half_up() -> None:
    assert health.rate_bp(health.Counts()) is None
    assert health.rate_bp(health.Counts(pending=3)) is None
    assert health.rate_bp(health.Counts(succeeded=2, failed=1)) == 6667
    assert health.rate_bp(health.Counts(succeeded=1, failed=31)) == 313  # 312.5 rounds up
    assert health.rate_bp(health.Counts(succeeded=1, failed=15)) == 625
    assert health.rate_bp(health.Counts(succeeded=5, failed=0)) == 10_000
    assert health.rate_bp(health.Counts(succeeded=0, failed=5)) == 0


def counts(rate_bp: int, completed: int) -> health.Counts:
    succeeded = rate_bp * completed // 10_000
    return health.Counts(succeeded=succeeded, failed=completed - succeeded)


def test_degraded_rule_boundaries() -> None:
    base = counts(9000, 1000)  # 90.00%
    assert health.evaluate(counts(8000, 100), base) == "degraded"  # exactly 10 points below
    assert health.evaluate(health.Counts(succeeded=8001, failed=1999), base) == "not_degraded"  # 9.99 points below
    assert health.evaluate(counts(5000, 50), base) == "degraded"  # minimum period volume
    assert health.evaluate(counts(5000, 49), base) == "insufficient_data"
    assert health.evaluate(counts(5000, 100), counts(9000, 200)) == "degraded"  # minimum baseline volume
    assert health.evaluate(counts(5000, 100), counts(9000, 199)) == "insufficient_data"
    assert health.evaluate(health.Counts(pending=4), base) == "no_data"
    assert health.evaluate(counts(9500, 100), base) == "not_degraded"  # better than baseline


def test_baseline_is_the_30_days_before_the_period() -> None:
    period = periods.resolve("month_to_date", parse_iso("2026-10-05T14:12:00Z"))
    baseline = health.baseline_period(period)
    assert (baseline.from_day, baseline.to_day) == (date(2026, 9, 1), date(2026, 9, 30))
    assert (baseline.start, baseline.end) == chicago_range(date(2026, 9, 1), date(2026, 9, 30))
    assert baseline.end == period.start


def test_failure_labels_match_the_recorded_signals() -> None:
    assert FAILURE_CODE_LABELS == scenario.DECLINE_CODES
    assert set(typing.get_args(attempts_api.FailureCode)) == set(FAILURE_CODE_LABELS)


def test_failure_signal_options(client_as) -> None:
    body = client_as("sam").get("/api/attempts/failure-signals").json()
    assert body == {"items": [{"value": code, "label": label} for code, label in FAILURE_CODE_LABELS.items()]}
