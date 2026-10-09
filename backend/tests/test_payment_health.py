"""GET /api/payment-health: every figure is recomputed independently from attempts and payments, drill-down figures equal
the totals of the lists they open, recovery is counted per payment, and nothing crosses a merchant boundary."""

from __future__ import annotations

import inspect
import json
import math
import re
import sqlite3
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from app.core.tz import chicago_day_bounds, chicago_range, parse_iso
from tests.conftest import PERSONAS, Ids, assert_scoped

TOP_KEYS = {"period", "baseline", "channel", "channel_label", "rules", "attention", "summary", "channels", "trend", "failure_signals", "recovery",
            "unresolved_payments"}
# The reporting clock is Monday 2026-10-05 09:12 CT; the presets are written out here rather than taken from app.core.periods.
PRESETS: dict[str, tuple[date, date]] = {
    "last_7_days": (date(2026, 9, 29), date(2026, 10, 5)),
    "month_to_date": (date(2026, 10, 1), date(2026, 10, 5)),
    "last_30_days": (date(2026, 9, 6), date(2026, 10, 5)),
}
CHANNELS = ["website", "mobile_app", "in_store"]
SLUG = {persona: slug for persona, (_, slug) in PERSONAS.items()}


def rate_bp(succeeded: int, failed: int) -> int | None:
    completed = succeeded + failed
    return None if completed == 0 else math.floor(Fraction(succeeded * 10000, completed) + Fraction(1, 2))


def outcomes(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None = None) -> Counter[str]:
    sql = ("SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id "
           "WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ?")
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    return Counter({row[0]: row[1] for row in conn.execute(sql + " GROUP BY a.outcome", params)})


def baseline_range(from_day: date) -> tuple[str, str]:
    return chicago_range(from_day - timedelta(days=30), from_day - timedelta(days=1))


def payment_chains(conn: sqlite3.Connection, merchant_id: str, start: str, end: str, channel: str | None) -> dict[str, tuple[int, list[sqlite3.Row]]]:
    """payment id -> (amount, attempts in order) for payments created in [start, end)."""
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    sql = "SELECT id, amount_cents FROM payment WHERE merchant_id = ? AND created_at >= ? AND created_at < ?"
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND channel = ?"
        params.append(channel)
    payments = {r["id"]: r["amount_cents"] for r in cur.execute(sql, params)}
    chains: dict[str, list[sqlite3.Row]] = {pid: [] for pid in payments}
    for row in cur.execute("SELECT * FROM payment_attempt WHERE merchant_id = ? ORDER BY payment_id, attempt_number", (merchant_id,)):
        if row["payment_id"] in chains:
            chains[row["payment_id"]].append(row)
    return {pid: (payments[pid], chain) for pid, chain in chains.items()}


def expected_recovery(chains: dict[str, tuple[int, list[sqlite3.Row]]]) -> dict[str, int]:
    out: Counter[str] = Counter()
    for amount, chain in chains.values():
        if not any(a["outcome"] == "failed" for a in chain):
            continue
        buckets = ["affected"]
        success = [a for a in chain if a["outcome"] == "succeeded"]
        if success:
            buckets.append("recovered")
            if (parse_iso(success[0]["completed_at"]) - parse_iso(chain[0]["created_at"])).total_seconds() <= 3600:
                buckets.append("recovered_within_hour")
        elif chain[-1]["outcome"] == "pending":
            buckets.append("in_progress")
        else:
            buckets.append("unresolved")
        for b in buckets:
            out[f"{b}_payments"] += 1
            out[f"{b}_value_cents"] += amount
    return dict(out)


def get(client: Any, query: str) -> dict[str, Any]:
    r = client.get(f"/api/payment-health?{query}")
    assert r.status_code == 200, r.text
    return r.json()


def list_total(client: Any, url: str) -> int:
    r = client.get(url)
    assert r.status_code == 200, r.text
    return int(r.json()["total"])


# --------------------------------------------------------------------------- shape and access


@pytest.mark.parametrize("persona", list(PERSONAS))
def test_every_role_gets_the_default_view(client_as, ids: Ids, persona: str) -> None:
    body = get(client_as(persona), "")
    assert set(body) == TOP_KEYS
    assert body["period"]["preset"] == "last_7_days"
    assert body["baseline"] == {"days": 30, "from_date": "2026-08-30", "to_date": "2026-09-28", "range_label": "Aug 30 – Sep 28, 2026"}
    assert body["rules"] == {"baseline_days": 30, "degraded_drop_bp": 1000, "min_period_completed": 50, "min_baseline_completed": 200,
                             "low_volume_day_completed": 20, "quick_recovery_seconds": 3600}
    assert body["channel"] is None and body["channel_label"] is None
    assert_scoped(ids, body, ids.merchant(SLUG[persona]))


def test_anonymous_is_401(client_as) -> None:
    assert client_as("anon").get("/api/payment-health").status_code == 401


@pytest.mark.parametrize("query", ["period=yesterday", "period=custom", "period=custom&from=2026-10-05", "from=2026-10-05&to=2026-10-01",
                                   "from=2025-01-01&to=2026-10-05", "channel=phone", "from=not-a-date&to=2026-10-05"])
def test_invalid_scope_is_422(client_as, query: str) -> None:
    r = client_as("maya").get(f"/api/payment-health?{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_the_view_is_read_only(client_as, db_copy: Path) -> None:
    def notes() -> int:
        with sqlite3.connect(db_copy) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM note_event").fetchone()[0])

    before = notes()
    get(client_as("maya"), "period=last_30_days")
    assert notes() == before


# --------------------------------------------------------------------------- attempt-level figures reconcile


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
@pytest.mark.parametrize("preset", list(PRESETS))
def test_summary_and_channels_reconcile_with_attempts(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, preset: str) -> None:
    c = client_as(persona)
    merchant_id = ids.merchant(SLUG[persona])
    from_day, to_day = PRESETS[preset]
    start, end = chicago_range(from_day, to_day)
    b_start, b_end = baseline_range(from_day)
    for channel in [None, *CHANNELS]:
        body = get(c, f"period={preset}" + (f"&channel={channel}" if channel else ""))
        cur, base = outcomes(seeded_conn, merchant_id, start, end, channel), outcomes(seeded_conn, merchant_id, b_start, b_end, channel)
        s = body["summary"]
        assert (s["succeeded"], s["failed"], s["pending"], s["completed"]) == (cur["succeeded"], cur["failed"], cur["pending"], cur["succeeded"] + cur["failed"])
        assert s["success_rate_bp"] == rate_bp(cur["succeeded"], cur["failed"])
        assert s["baseline"] == {"succeeded": base["succeeded"], "failed": base["failed"], "completed": base["succeeded"] + base["failed"],
                                 "success_rate_bp": rate_bp(base["succeeded"], base["failed"])}
        # The attempt figures equal the Attempts list it drills into.
        scope = f"period={preset}" + (f"&channel={channel}" if channel else "")
        assert s["failed"] == list_total(c, f"/api/attempts?{scope}&outcome=failed&page_size=1")
        assert s["pending"] == list_total(c, f"/api/attempts?{scope}&outcome=pending&page_size=1")
        assert s["succeeded"] + s["failed"] + s["pending"] == list_total(c, f"/api/attempts?{scope}&page_size=1")

    # The channel table is never filtered and lists every channel with attempts in the period or baseline.
    rows = {ch["channel"]: ch for ch in body["channels"]}
    for channel in CHANNELS:
        cur, base = outcomes(seeded_conn, merchant_id, start, end, channel), outcomes(seeded_conn, merchant_id, b_start, b_end, channel)
        if not cur and not base:
            assert channel not in rows
            continue
        row = rows[channel]
        assert (row["succeeded"], row["failed"], row["pending"]) == (cur["succeeded"], cur["failed"], cur["pending"])
        assert row["success_rate_bp"] == rate_bp(cur["succeeded"], cur["failed"])
        assert row["baseline_completed"] == base["succeeded"] + base["failed"]
        assert row["baseline_rate_bp"] == rate_bp(base["succeeded"], base["failed"])


@pytest.mark.parametrize("persona,query", [("maya", "period=last_7_days"), ("maya", "period=last_30_days&channel=mobile_app"),
                                           ("priya", "period=last_30_days"), ("sam_copper", "period=month_to_date&channel=in_store")])
def test_failure_signals_reconcile_to_failed_attempts(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, query: str) -> None:
    c = client_as(persona)
    body = get(c, query)
    signals = body["failure_signals"]
    assert sum(s["failed_attempts"] for s in signals) == body["summary"]["failed"]
    assert [s["failed_attempts"] for s in signals] == sorted((s["failed_attempts"] for s in signals), reverse=True)
    for s in signals:
        assert s["label"] and s["failure_code"] != s["label"]
        # Each signal opens the Attempts list filtered to exactly those failed attempts.
        assert s["failed_attempts"] == list_total(c, f"/api/attempts?{query}&outcome=failed&failure_code={s['failure_code']}&page_size=1")


@pytest.mark.parametrize("persona,channel", [("maya", None), ("maya", "mobile_app"), ("sam_copper", "website"), ("priya", "in_store")])
def test_trend_buckets_by_chicago_day_and_sums_to_the_summary(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, channel: str | None) -> None:
    merchant_id = ids.merchant(SLUG[persona])
    body = get(client_as(persona), "period=last_30_days" + (f"&channel={channel}" if channel else ""))
    from_day, to_day = PRESETS["last_30_days"]
    assert [p["day"] for p in body["trend"]] == [(from_day + timedelta(days=i)).isoformat() for i in range((to_day - from_day).days + 1)]
    for point in body["trend"]:
        counts = outcomes(seeded_conn, merchant_id, *chicago_day_bounds(date.fromisoformat(point["day"])), channel)
        assert (point["succeeded"], point["failed"], point["pending"]) == (counts["succeeded"], counts["failed"], counts["pending"])
        completed = counts["succeeded"] + counts["failed"]
        assert point["success_rate_bp"] == rate_bp(counts["succeeded"], counts["failed"])
        assert (point["success_rate_bp"] is None) == (completed == 0), "a day with no completed attempts is a gap, never 0% or 100%"
        assert point["low_volume"] == (0 < completed < 20)
    for key in ("succeeded", "failed", "pending"):
        assert sum(p[key] for p in body["trend"]) == body["summary"][key]


# --------------------------------------------------------------------------- degradation


def test_the_app_checkout_spike_is_the_only_degraded_channel(client_as) -> None:
    body = get(client_as("maya"), "period=last_7_days")
    assessments = {c["channel"]: c["assessment"] for c in body["channels"]}
    assert assessments == {"website": "healthy", "mobile_app": "degraded", "in_store": "healthy"}
    mobile = next(c for c in body["channels"] if c["channel"] == "mobile_app")
    assert mobile["change_bp"] == mobile["success_rate_bp"] - mobile["baseline_rate_bp"] <= -1000
    assert body["attention"]["state"] == "degraded"
    assert body["attention"]["degraded_channels"] == [{
        "channel": "mobile_app", "channel_label": "Mobile app", "success_rate_bp": mobile["success_rate_bp"],
        "baseline_rate_bp": mobile["baseline_rate_bp"], "change_bp": mobile["change_bp"], "failed": mobile["failed"],
    }]
    # Attention always looks across every channel, whatever channel the page is scoped to.
    assert get(client_as("maya"), "period=last_7_days&channel=website")["attention"] == body["attention"]


def test_low_volume_channels_are_not_evaluated(client_as) -> None:
    body = get(client_as("sam_copper"), "period=last_7_days")
    rows = {c["channel"]: c for c in body["channels"]}
    assert rows["mobile_app"]["assessment"] == rows["website"]["assessment"] == "insufficient_volume"
    assert rows["mobile_app"]["assessment_label"] == "Not enough volume"
    # Copper Finch in-store dips about six points against its baseline: below the threshold, so no alarm.
    assert rows["in_store"]["assessment"] == "healthy" and -1000 < rows["in_store"]["change_bp"] < 0
    assert body["attention"]["state"] == "healthy" and body["attention"]["degraded_channels"] == []


@pytest.mark.parametrize("persona", ["maya", "priya", "sam_copper"])
def test_a_thin_baseline_draws_no_conclusion(client_as, persona: str) -> None:
    # The seeded history starts on Sep 5, so the 30 days before a 30-day period hold a single day of attempts.
    body = get(client_as(persona), "period=last_30_days")
    assert {c["assessment"] for c in body["channels"]} == {"insufficient_volume"}
    assert all(c["baseline_completed"] < 200 for c in body["channels"])
    assert body["attention"]["state"] == "insufficient_volume" and body["attention"]["degraded_channels"] == []


# --------------------------------------------------------------------------- recovery per payment


@pytest.mark.parametrize("persona,query", [("maya", "from=2026-10-01&to=2026-10-02&channel=mobile_app"), ("maya", "period=last_7_days"),
                                           ("priya", "period=last_30_days"), ("sam_copper", "period=last_30_days&channel=website")])
def test_recovery_is_counted_once_per_payment(client_as, seeded_conn: sqlite3.Connection, ids: Ids, persona: str, query: str) -> None:
    c = client_as(persona)
    body = get(c, query)
    from_day, to_day = date.fromisoformat(body["period"]["from_date"]), date.fromisoformat(body["period"]["to_date"])
    chains = payment_chains(seeded_conn, ids.merchant(SLUG[persona]), *chicago_range(from_day, to_day), body["channel"])
    rec = body["recovery"]
    expected = expected_recovery(chains)
    assert {k: v for k, v in rec.items() if k != "currency" and v} == expected
    assert rec["currency"] == "USD"
    for unit in ("payments", "value_cents"):
        assert rec[f"affected_{unit}"] == rec[f"recovered_{unit}"] + rec[f"in_progress_{unit}"] + rec[f"unresolved_{unit}"]
        assert rec[f"recovered_within_hour_{unit}"] <= rec[f"recovered_{unit}"]
    # Several attempts never inflate the count or the value: each payment's amount appears once.
    assert rec["affected_payments"] <= sum(1 for _, chain in chains.values() for a in chain if a["outcome"] == "failed")
    # Unresolved payments are exactly the Payments list's failed payments for the same scope, newest first.
    payments = c.get(f"/api/payments?{query}&status=failed&page_size=10").json()
    assert rec["unresolved_payments"] == payments["total"]
    assert [p["id"] for p in body["unresolved_payments"]] == [p["id"] for p in payments["items"]]
    assert all(p["status"] == "failed" for p in body["unresolved_payments"])


def test_the_scripted_spike_recovers_on_retry(client_as) -> None:
    rec = get(client_as("maya"), "from=2026-10-01&to=2026-10-02&channel=mobile_app")["recovery"]
    assert rec["affected_payments"] >= 32 and rec["recovered_payments"] >= 23 and rec["unresolved_payments"] >= 9
    assert rec["recovered_within_hour_payments"] == rec["recovered_payments"]


def test_a_retry_still_pending_is_in_progress_not_unresolved_or_recovered(client_as, db_copy: Path, ids: Ids) -> None:
    c = client_as("maya")
    query = "from=2026-10-01&to=2026-10-02&channel=mobile_app"
    before = get(c, query)
    target = before["unresolved_payments"][0]
    with sqlite3.connect(db_copy) as conn:
        last = conn.execute("SELECT * FROM payment_attempt WHERE payment_id = ? ORDER BY attempt_number DESC LIMIT 1", (target["id"],)).fetchone()
        cols = [d[0] for d in conn.execute("SELECT * FROM payment_attempt LIMIT 0").description]
        row = dict(zip(cols, last))
        row.update(id="att_zzzzzzzzzzzzzz", attempt_number=row["attempt_number"] + 1, outcome="pending", failure_code=None, failure_message=None,
                   created_at=row["completed_at"], completed_at=None)
        conn.execute(f"INSERT INTO payment_attempt ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", [row[k] for k in cols])
    after = get(c, query)
    b, a = before["recovery"], after["recovery"]
    assert a["affected_payments"] == b["affected_payments"]
    assert a["unresolved_payments"] == b["unresolved_payments"] - 1 and a["in_progress_payments"] == b["in_progress_payments"] + 1
    assert a["in_progress_value_cents"] == target["amount_cents"] and a["recovered_payments"] == b["recovered_payments"]
    assert after["summary"]["pending"] == before["summary"]["pending"] + 1
    assert after["summary"]["success_rate_bp"] == before["summary"]["success_rate_bp"], "pending attempts stay out of the rate"
    assert target["id"] not in {p["id"] for p in after["unresolved_payments"]}


def test_a_slow_recovery_is_recovered_but_not_within_the_hour(client_as, db_copy: Path) -> None:
    c = client_as("maya")
    query = "from=2026-10-01&to=2026-10-02&channel=mobile_app"
    before = get(c, query)["recovery"]
    with sqlite3.connect(db_copy) as conn:
        payment_id, attempt_id, completed_at = conn.execute(
            "SELECT s.payment_id, s.id, s.completed_at FROM payment_attempt s JOIN payment p ON p.id = s.payment_id "
            "WHERE s.merchant_id = (SELECT id FROM merchant WHERE slug = 'alder-loom') AND s.outcome = 'succeeded' AND s.attempt_number > 1 "
            "AND p.channel = 'mobile_app' "
            "AND s.created_at >= '2026-10-01T20:00:00Z' AND s.created_at < '2026-10-02T12:00:00Z' ORDER BY s.created_at LIMIT 1"
        ).fetchone()
        later = parse_iso(completed_at) + timedelta(hours=2)
        conn.execute("UPDATE payment_attempt SET completed_at = ? WHERE id = ?", (later.strftime("%Y-%m-%dT%H:%M:%SZ"), attempt_id))
        amount = conn.execute("SELECT amount_cents FROM payment WHERE id = ?", (payment_id,)).fetchone()[0]
    after = get(c, query)["recovery"]
    assert after["recovered_payments"] == before["recovered_payments"]
    assert after["recovered_within_hour_payments"] == before["recovered_within_hour_payments"] - 1
    assert after["recovered_within_hour_value_cents"] == before["recovered_within_hour_value_cents"] - amount


# --------------------------------------------------------------------------- edge cases


def test_pending_only_scope_has_no_rate(client_as) -> None:
    # Copper Finch website on Oct 5: two pending attempts and nothing completed yet.
    body = get(client_as("sam_copper"), "from=2026-10-05&to=2026-10-05&channel=website")
    s = body["summary"]
    assert (s["completed"], s["pending"], s["success_rate_bp"], s["change_bp"]) == (0, 2, None, None)
    assert body["trend"] == [{"day": "2026-10-05", "succeeded": 0, "failed": 0, "pending": 2, "success_rate_bp": None, "low_volume": False}]
    assert body["failure_signals"] == [] and body["recovery"]["affected_payments"] == 0


def test_a_period_with_no_attempts_is_empty_not_fabricated(client_as) -> None:
    body = get(client_as("maya"), "from=2026-08-01&to=2026-08-07")
    assert body["summary"] == {"succeeded": 0, "failed": 0, "pending": 0, "completed": 0, "success_rate_bp": None,
                               "baseline": {"succeeded": 0, "failed": 0, "completed": 0, "success_rate_bp": None}, "change_bp": None}
    assert body["channels"] == [] and body["failure_signals"] == [] and body["unresolved_payments"] == []
    assert all(p["success_rate_bp"] is None and not p["low_volume"] for p in body["trend"])
    assert body["attention"] == {"state": "no_completed_attempts", "state_label": "No completed attempts", "degraded_channels": []}
    assert body["recovery"]["affected_payments"] == 0 and body["recovery"]["affected_value_cents"] == 0


def test_a_day_without_failures_has_no_signals_and_nothing_to_recover(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    merchant_id = ids.merchant("juniper-trail")
    day = next(
        d for d in (date(2026, 9, 6) + timedelta(days=i) for i in range(29))
        if (counts := outcomes(seeded_conn, merchant_id, *chicago_day_bounds(d), "in_store"))["succeeded"] and not counts["failed"]
    )
    body = get(client_as("priya"), f"from={day}&to={day}&channel=in_store")
    assert body["summary"]["failed"] == 0 and body["summary"]["success_rate_bp"] == 10000
    assert body["failure_signals"] == []
    assert body["recovery"]["affected_payments"] == 0 and body["unresolved_payments"] == []


# --------------------------------------------------------------------------- merchant boundaries


def test_results_follow_the_session_merchant_only(client_as, ids: Ids) -> None:
    maya = get(client_as("maya"), "period=last_30_days")
    juniper = ids.merchant("juniper-trail")
    assert get(client_as("maya"), f"period=last_30_days&merchant_id={juniper}") == maya, "a merchant_id parameter is ignored"
    sam, sam_copper = get(client_as("sam"), "period=last_30_days"), get(client_as("sam_copper"), "period=last_30_days")
    assert_scoped(ids, sam_copper, ids.merchant("copper-finch"))
    assert {p["id"] for p in sam["unresolved_payments"]}.isdisjoint({p["id"] for p in sam_copper["unresolved_payments"]})
    assert sam["summary"] != sam_copper["summary"]


def test_every_attempt_subquery_filters_on_the_merchant() -> None:
    from app.db.queries import payment_health as health_q

    source = inspect.getsource(health_q)
    subqueries = re.findall(r"FROM payment_attempt (\w+) WHERE ([^)]*)\)", source)
    assert len(subqueries) == 2
    for alias, clause in subqueries:
        assert f"{alias}.merchant_id = :merchant_id" in clause, clause
    # The shared attempt WHERE and the affected-payment WHERE each open with the merchant clause.
    assert '["a.merchant_id = :merchant_id",' in source and '"ps.merchant_id = :merchant_id",' in source


def test_other_merchants_rows_never_move_the_figures(client_as, db_copy: Path, ids: Ids) -> None:
    maya, priya = client_as("maya"), client_as("priya")
    queries = ["period=last_7_days", "period=last_30_days&channel=website", "from=2026-10-01&to=2026-10-02&channel=mobile_app"]
    maya_before = [json.dumps(get(maya, q), sort_keys=True) for q in queries]
    priya_before = get(priya, "period=last_30_days")
    others = (ids.merchant("juniper-trail"), ids.merchant("copper-finch"))
    with sqlite3.connect(db_copy) as conn:
        # Turn every other-merchant success in the window into an issuer_unavailable failure.
        conn.execute(
            "UPDATE payment_attempt SET outcome = 'failed', failure_code = 'issuer_unavailable', failure_message = 'Issuer unavailable' "
            f"WHERE outcome = 'succeeded' AND merchant_id IN ({', '.join('?' for _ in others)}) AND created_at >= '2026-09-01T00:00:00Z'",
            others,
        )
    assert [json.dumps(get(maya, q), sort_keys=True) for q in queries] == maya_before
    priya_after = get(priya, "period=last_30_days")
    assert priya_after["summary"]["failed"] > priya_before["summary"]["failed"]
    assert priya_after["recovery"]["unresolved_payments"] > priya_before["recovery"]["unresolved_payments"]
    assert_scoped(ids, priya_after, ids.merchant("juniper-trail"))
