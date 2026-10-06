"""GET /api/payment-health: every figure recomputed with independent SQL over payment_attempt and payment, then pinned.

The oracle here never imports the query module under test: rates come from Fraction arithmetic over raw attempt counts,
recovery from each payment's attempt chain, and the pinned seed values make a silent change in the data or the rule show up.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from fastapi.testclient import TestClient

from app.core import health
from app.core.tz import chicago_local, chicago_range, parse_iso, to_iso
from tests.conftest import Ids, assert_scoped, collect_ids

CHANNELS = ("website", "mobile_app", "in_store")
OCT_1_2_MOBILE = "period=custom&from=2026-10-01&to=2026-10-02&channel=mobile_app"
LAST_7 = "period=last_7_days"
ONE_HOUR = timedelta(hours=1)


# --------------------------------------------------------------------------- the independent oracle


def rate(numerator: int, denominator: int) -> int | None:
    """Half-up basis points through Fraction, independent of core/health.py."""
    return int(Fraction(numerator * 10000, denominator) + Fraction(1, 2)) if denominator else None


def outcomes(conn: sqlite3.Connection, merchant_id: str, channel: str | None, start: str, end: str) -> dict[str, Any]:
    extra = " AND p.channel = :channel" if channel else ""
    rows = conn.execute(
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id "
        f"WHERE a.merchant_id = :m AND a.created_at >= :s AND a.created_at < :e{extra} GROUP BY a.outcome",
        {"m": merchant_id, "s": start, "e": end, "channel": channel},
    ).fetchall()
    c = Counter(dict(rows))
    completed = c["succeeded"] + c["failed"]
    return {
        "succeeded": c["succeeded"], "failed": c["failed"], "pending": c["pending"], "completed": completed,
        "success_rate_bp": rate(c["succeeded"], completed), "failed_share_bp": rate(c["failed"], completed),
    }


def day_series(conn: sqlite3.Connection, merchant_id: str, channel: str | None, from_day: date, to_day: date) -> list[dict[str, Any]]:
    out = []
    day = from_day
    while day <= to_day:
        start, end = chicago_range(day, day)
        o = outcomes(conn, merchant_id, channel, start, end)
        out.append({"day": day.isoformat(), **{k: o[k] for k in ("succeeded", "failed", "completed", "success_rate_bp")}, "low_volume": o["completed"] < 10})
        day += timedelta(days=1)
    return out


def signals(conn: sqlite3.Connection, merchant_id: str, channel: str | None, start: str, end: str) -> list[tuple[str, int]]:
    extra = " AND p.channel = :channel" if channel else ""
    rows = conn.execute(
        "SELECT a.failure_code, COUNT(*) AS n FROM payment_attempt a JOIN payment p ON p.id = a.payment_id "
        f"WHERE a.merchant_id = :m AND a.outcome = 'failed' AND a.created_at >= :s AND a.created_at < :e{extra} GROUP BY a.failure_code ORDER BY n DESC, a.failure_code",
        {"m": merchant_id, "s": start, "e": end, "channel": channel},
    ).fetchall()
    return [(code, n) for code, n in rows]


def chains_for(conn: sqlite3.Connection, payment_ids: list[str]) -> dict[str, list[sqlite3.Row]]:
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    out: dict[str, list[sqlite3.Row]] = {pid: [] for pid in payment_ids}
    for row in cur.execute("SELECT * FROM payment_attempt ORDER BY payment_id, attempt_number"):
        if row["payment_id"] in out:
            out[row["payment_id"]].append(row)
    return out


def cohort(conn: sqlite3.Connection, merchant_id: str, channel: str | None, start: str, end: str) -> dict[str, Any]:
    """Recovery per payment created in [start, end): affected = any failed attempt; recovered = a success within an hour of the first attempt."""
    extra = " AND channel = :channel" if channel else ""
    payments = {
        pid: amount
        for pid, amount in conn.execute(f"SELECT id, amount_cents FROM payment WHERE merchant_id = :m AND created_at >= :s AND created_at < :e{extra}", {"m": merchant_id, "s": start, "e": end, "channel": channel})
    }
    chains = chains_for(conn, list(payments))
    states: dict[str, str] = {}
    for pid, chain in chains.items():
        if not any(a["outcome"] == "failed" for a in chain):
            continue
        success = [a for a in chain if a["outcome"] == "succeeded"]
        if success:
            within = parse_iso(success[0]["completed_at"]) - parse_iso(chain[0]["created_at"]) <= ONE_HOUR
            states[pid] = "recovered_within_window" if within else "recovered_later"
        elif chain[-1]["outcome"] == "pending":
            states[pid] = "attempt_pending"
        else:
            states[pid] = "unresolved"
    counts = Counter(states.values())
    cents: Counter[str] = Counter()
    for pid, state in states.items():
        cents[state] += payments[pid]
    return {
        "affected": len(states),
        "recovered": counts["recovered_within_window"] + counts["recovered_later"],
        "recovered_within_window": counts["recovered_within_window"],
        "recovered_later": counts["recovered_later"],
        "attempt_pending": counts["attempt_pending"],
        "unresolved": counts["unresolved"],
        "recovered_within_window_share_bp": rate(counts["recovered_within_window"], len(states)),
        "affected_cents": sum(cents.values()),
        "recovered_cents": cents["recovered_within_window"] + cents["recovered_later"],
        "unresolved_cents": cents["unresolved"],
        "attempt_pending_cents": cents["attempt_pending"],
        "currency": "USD",
        "unresolved_ids": {pid for pid, state in states.items() if state == "unresolved"},
    }


def get(client: TestClient, query: str) -> dict[str, Any]:
    r = client.get(f"/api/payment-health?{query}")
    assert r.status_code == 200, r.text
    return r.json()


def strip(counts: dict[str, Any]) -> dict[str, Any]:
    return {k: counts[k] for k in ("succeeded", "failed", "pending", "completed", "success_rate_bp", "failed_share_bp")}


# --------------------------------------------------------------------------- (a) the Oct 1–2 mobile scope


def test_oct_1_2_mobile_matches_sql_and_the_pinned_seed(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    body = get(client_as("maya"), OCT_1_2_MOBILE)
    assert set(body) == {"period", "channel", "channel_label", "as_of", "rule", "baseline", "attention", "scope", "channels", "trend", "failure_signals", "recovery", "unresolved_payments"}
    assert body["channel"] == "mobile_app" and body["channel_label"] == "Mobile app" and body["as_of"] == "2026-10-05T14:12:00Z"
    assert body["period"] == {"preset": "custom", "label": "Custom range", "from_date": "2026-10-01", "to_date": "2026-10-02", "range_label": "Oct 1 – Oct 2, 2026"}
    assert body["rule"] == {"baseline_days": 30, "min_period_completed": 30, "min_baseline_completed": 100, "degraded_drop_bp": 1000, "low_volume_day_completed": 10, "recovery_window_minutes": 60}
    assert body["baseline"] == {"from_date": "2026-09-01", "to_date": "2026-09-30", "range_label": "Sep 1 – Sep 30, 2026", "history_starts": "2026-09-05", "partial": True}
    assert_scoped(ids, body, alder)

    start, end = chicago_range(date(2026, 10, 1), date(2026, 10, 2))
    base_start, base_end = chicago_range(date(2026, 9, 1), date(2026, 9, 30))
    scope = body["scope"]
    assert strip(scope["period"]) == outcomes(seeded_conn, alder, "mobile_app", start, end)
    assert strip(scope["baseline"]) == outcomes(seeded_conn, alder, "mobile_app", base_start, base_end)
    assert scope["period"] == {"succeeded": 53, "failed": 42, "pending": 0, "completed": 95, "success_rate_bp": 5579, "failed_share_bp": 4421}
    assert scope["baseline"]["completed"] == 679 and scope["baseline"]["success_rate_bp"] == 9087
    assert scope["status"] == "degraded" and scope["status_label"] == "Degraded" and scope["drop_bp"] == 9087 - 5579 == 3508
    assert scope == next(c for c in body["channels"] if c["channel"] == "mobile_app")

    days = day_series(seeded_conn, alder, "mobile_app", date(2026, 10, 1), date(2026, 10, 2))
    assert body["trend"] == {"points": days, "baseline_rate_bp": 9087}
    assert [(p["succeeded"], p["failed"]) for p in days] == [(25, 31), (28, 11)]
    assert scope["worst_day"] == days[0] and scope["worst_day"]["day"] == "2026-10-01" and scope["worst_day"]["success_rate_bp"] == 4464

    assert body["attention"] == {
        "status": "degraded",
        "headline": "Attention needed: Mobile app payment performance degraded",
        "detail": "Mobile app: 55.8% of completed attempts succeeded vs 90.9% in the baseline (35.1 pts lower). Worst day Oct 1: 44.6% of 56 completed attempts.",
        "degraded_channels": ["mobile_app"],
    }

    expected = signals(seeded_conn, alder, "mobile_app", start, end)
    assert [(s["failure_code"], s["count"]) for s in body["failure_signals"]["items"]] == expected
    assert expected == [("issuer_unavailable", 29), ("do_not_honor", 3), ("insufficient_funds", 3), ("processing_error", 3), ("authentication_failed", 1), ("card_velocity_exceeded", 1), ("expired_card", 1), ("incorrect_cvc", 1)]
    assert body["failure_signals"]["total_failed"] == 42 == scope["period"]["failed"]
    assert body["failure_signals"]["primary"] == body["failure_signals"]["items"][0]
    assert body["failure_signals"]["items"][0] == {"failure_code": "issuer_unavailable", "label": "Issuer unavailable", "count": 29, "share_bp": rate(29, 42)}
    assert all(s["share_bp"] == rate(s["count"], 42) for s in body["failure_signals"]["items"])

    expected_cohort = cohort(seeded_conn, alder, "mobile_app", start, end)
    unresolved_ids = expected_cohort.pop("unresolved_ids")
    assert body["recovery"] == expected_cohort
    assert body["recovery"] == {
        "affected": 38, "recovered": 26, "recovered_within_window": 26, "recovered_later": 0, "attempt_pending": 0, "unresolved": 12,
        "recovered_within_window_share_bp": 6842, "affected_cents": 896010, "recovered_cents": 473199, "unresolved_cents": 422811, "attempt_pending_cents": 0, "currency": "USD",
    }

    unresolved = body["unresolved_payments"]
    assert unresolved["total"] == 12 == len(unresolved_ids)
    assert len(unresolved["items"]) == 5
    assert {i["id"] for i in unresolved["items"]} <= unresolved_ids
    latest = [i["last_attempt_at"] for i in unresolved["items"]]
    assert latest == sorted(latest, reverse=True)
    for item in unresolved["items"]:
        row = seeded_conn.execute(
            "SELECT p.order_reference, p.amount_cents, p.channel, a.failure_code, a.created_at, (SELECT COUNT(*) FROM payment_attempt x WHERE x.payment_id = p.id) "
            "FROM payment p JOIN payment_attempt a ON a.payment_id = p.id WHERE p.id = ? ORDER BY a.attempt_number DESC LIMIT 1",
            (item["id"],),
        ).fetchone()
        assert row[2] == "mobile_app"
        assert (item["order_reference"], item["amount_cents"], item["last_failure_code"], item["last_attempt_at"], item["attempt_count"]) == (row[0], row[1], row[3], row[4], row[5])
        assert item["last_failure_label"] and item["currency"] == "USD"
        assert item["customer"] is None or set(item["customer"]) == {"id", "full_name", "email", "reference"}


# --------------------------------------------------------------------------- (b) last 7 days, all channels


def test_last_7_days_all_channels(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    body = get(client_as("maya"), LAST_7)
    assert body["channel"] is None and body["channel_label"] == "All channels"
    assert body["period"]["from_date"] == "2026-09-29" and body["period"]["to_date"] == "2026-10-05"
    assert body["baseline"] == {"from_date": "2026-08-30", "to_date": "2026-09-28", "range_label": "Aug 30 – Sep 28, 2026", "history_starts": "2026-09-05", "partial": True}
    start, end = chicago_range(date(2026, 9, 29), date(2026, 10, 5))
    base_start, base_end = chicago_range(date(2026, 8, 30), date(2026, 9, 28))

    assert [c["channel"] for c in body["channels"]] == list(CHANNELS)
    for ch in body["channels"]:
        assert strip(ch["period"]) == outcomes(seeded_conn, alder, ch["channel"], start, end), ch["channel"]
        assert strip(ch["baseline"]) == outcomes(seeded_conn, alder, ch["channel"], base_start, base_end), ch["channel"]
        assert ch["drop_bp"] == ch["baseline"]["success_rate_bp"] - ch["period"]["success_rate_bp"]
    pinned = {c["channel"]: (c["status"], c["period"]["succeeded"], c["period"]["failed"], c["period"]["pending"], c["period"]["success_rate_bp"], c["baseline"]["completed"], c["baseline"]["success_rate_bp"]) for c in body["channels"]}
    assert pinned == {
        "website": ("normal", 246, 20, 1, 9248, 1060, 9142),
        "mobile_app": ("degraded", 134, 52, 1, 7204, 630, 9079),
        "in_store": ("normal", 119, 18, 0, 8686, 395, 9165),
    }

    scope = body["scope"]
    assert scope["channel"] is None and scope["channel_label"] == "All channels" and scope["status"] == "degraded"
    assert strip(scope["period"]) == outcomes(seeded_conn, alder, None, start, end)
    assert strip(scope["baseline"]) == outcomes(seeded_conn, alder, None, base_start, base_end)
    assert (scope["period"]["succeeded"], scope["period"]["failed"], scope["period"]["pending"], scope["period"]["success_rate_bp"]) == (499, 90, 2, 8472)
    assert scope["baseline"]["completed"] == 2085 and scope["baseline"]["success_rate_bp"] == 9127
    assert scope["drop_bp"] == 9127 - 8472, "the pooled drop is informational only; the verdict is the worst channel's"

    assert body["attention"] == {
        "status": "degraded",
        "headline": "Attention needed: Mobile app payment performance degraded",
        "detail": "Mobile app: 72.0% of completed attempts succeeded vs 90.8% in the baseline (18.8 pts lower). Worst day Oct 1: 44.6% of 56 completed attempts.",
        "degraded_channels": ["mobile_app"],
    }

    days = day_series(seeded_conn, alder, None, date(2026, 9, 29), date(2026, 10, 5))
    assert body["trend"]["points"] == days and len(days) == 7
    assert body["trend"]["baseline_rate_bp"] == 9127, "the all-channels scope draws its own pooled baseline rate when it carries a verdict"
    assert scope["worst_day"] == min((d for d in days if not d["low_volume"]), key=lambda d: (d["success_rate_bp"], d["day"]))

    assert [(s["failure_code"], s["count"]) for s in body["failure_signals"]["items"]] == signals(seeded_conn, alder, None, start, end)
    assert body["failure_signals"]["total_failed"] == 90
    expected_cohort = cohort(seeded_conn, alder, None, start, end)
    unresolved_ids = expected_cohort.pop("unresolved_ids")
    assert body["recovery"] == expected_cohort
    assert (expected_cohort["affected"], expected_cohort["recovered"], expected_cohort["unresolved"]) == (83, 55, 28)
    assert (expected_cohort["affected_cents"], expected_cohort["recovered_cents"], expected_cohort["unresolved_cents"]) == (2334007, 1571734, 762273)
    assert body["unresolved_payments"]["total"] == 28 == len(unresolved_ids)
    assert {i["id"] for i in body["unresolved_payments"]["items"]} <= unresolved_ids


def test_last_7_days_mobile_trend_marks_the_partial_day_as_low_volume(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = get(client_as("maya"), f"{LAST_7}&channel=mobile_app")
    points = body["trend"]["points"]
    assert points == day_series(seeded_conn, ids.merchant("alder-loom"), "mobile_app", date(2026, 9, 29), date(2026, 10, 5))
    assert [(p["day"][5:], p["succeeded"], p["failed"], p["success_rate_bp"], p["low_volume"]) for p in points] == [
        ("09-29", 19, 0, 10000, False), ("09-30", 26, 4, 8667, False), ("10-01", 25, 31, 4464, False), ("10-02", 28, 11, 7179, False),
        ("10-03", 18, 2, 9000, False), ("10-04", 13, 4, 7647, False), ("10-05", 5, 0, 10000, True),
    ]
    assert body["trend"]["baseline_rate_bp"] == 9079 and body["scope"]["worst_day"]["day"] == "2026-10-01"
    assert body["attention"]["degraded_channels"] == ["mobile_app"] and body["scope"] == body["channels"][1]
    expected = cohort(seeded_conn, ids.merchant("alder-loom"), "mobile_app", *chicago_range(date(2026, 9, 29), date(2026, 10, 5)))
    assert (body["recovery"]["affected"], body["recovery"]["recovered_within_window"], body["recovery"]["unresolved"]) == (47, 31, 16) == (expected["affected"], expected["recovered_within_window"], expected["unresolved"])
    assert (body["recovery"]["affected_cents"], body["recovery"]["recovered_cents"], body["recovery"]["unresolved_cents"]) == (1258843, 777710, 481133)


# --------------------------------------------------------------------------- (c) and (d): no baseline, month to date


def test_last_30_days_has_no_baseline_because_history_starts_inside_it(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    body = get(client_as("maya"), "period=last_30_days")
    first = seeded_conn.execute("SELECT MIN(created_at) FROM payment_attempt WHERE merchant_id = ?", (alder,)).fetchone()[0]
    assert first.startswith("2026-09-05") and body["baseline"]["history_starts"] == "2026-09-05"
    assert body["baseline"] == {"from_date": "2026-08-07", "to_date": "2026-09-05", "range_label": "Aug 7 – Sep 5, 2026", "history_starts": "2026-09-05", "partial": True}
    assert [c["status"] for c in body["channels"]] == ["no_baseline"] * 3
    assert [c["status_label"] for c in body["channels"]] == ["No baseline yet"] * 3
    assert [c["baseline"]["completed"] for c in body["channels"]] == [37, 23, 24]
    assert all(c["period"]["completed"] >= 30 for c in body["channels"]), "volume is not the reason"
    assert body["scope"]["status"] == "no_baseline" and body["scope"]["baseline"]["completed"] == 84
    assert body["attention"] == {
        "status": "no_baseline",
        "headline": "No baseline yet: payment history starts Sep 5, 2026",
        "detail": "The baseline would be Aug 7 – Sep 5, 2026, but recorded history begins Sep 5, 2026, leaving 84 completed attempts to compare against (100 needed). "
        "Period figures are shown without a verdict.",
        "degraded_channels": [],
    }
    assert body["trend"]["baseline_rate_bp"] is None and len(body["trend"]["points"]) == 30
    assert body["scope"]["period"]["success_rate_bp"] is not None, "period figures are still shown"


def test_month_to_date(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    body = get(client_as("maya"), "period=month_to_date")
    by_channel = {c["channel"]: c for c in body["channels"]}
    start, end = chicago_range(date(2026, 10, 1), date(2026, 10, 5))
    assert strip(by_channel["in_store"]["period"]) == outcomes(seeded_conn, alder, "in_store", start, end)
    assert by_channel["mobile_app"]["status"] == "degraded" and by_channel["mobile_app"]["period"]["completed"] == 137 and by_channel["mobile_app"]["period"]["success_rate_bp"] == 6496
    assert by_channel["website"]["status"] == "normal"
    assert by_channel["in_store"]["status"] == "normal" and by_channel["in_store"]["period"]["completed"] == 99
    assert (by_channel["in_store"]["period"]["success_rate_bp"], by_channel["in_store"]["baseline"]["success_rate_bp"], by_channel["in_store"]["drop_bp"]) == (8384, 9192, 808)
    assert body["attention"]["degraded_channels"] == ["mobile_app"] and body["scope"]["status"] == "degraded"
    assert len(body["trend"]["points"]) == 5


# --------------------------------------------------------------------------- (e) drill-down parity with the lists


def test_unresolved_and_signals_drill_down_to_the_lists_with_the_same_scope(client_as) -> None:
    c = client_as("maya")
    body = get(c, OCT_1_2_MOBILE)
    payments = c.get(f"/api/payments?{OCT_1_2_MOBILE}&status=failed&page_size=100").json()
    assert payments["total"] == body["unresolved_payments"]["total"] == body["recovery"]["unresolved"] == 12
    assert sum(p["amount_cents"] for p in payments["items"]) == body["recovery"]["unresolved_cents"] == 422811
    assert {i["id"] for i in body["unresolved_payments"]["items"]} <= {p["id"] for p in payments["items"]}
    issuer = c.get(f"/api/attempts?{OCT_1_2_MOBILE}&outcome=failed&failure_code=issuer_unavailable&page_size=1").json()
    assert issuer["total"] == 29 == body["failure_signals"]["primary"]["count"]
    for signal in body["failure_signals"]["items"]:
        listed = c.get(f"/api/attempts?{OCT_1_2_MOBILE}&outcome=failed&failure_code={signal['failure_code']}&page_size=1").json()
        assert listed["total"] == signal["count"], signal["failure_code"]
    failed = c.get(f"/api/attempts?{OCT_1_2_MOBILE}&outcome=failed&page_size=1").json()
    assert failed["total"] == body["failure_signals"]["total_failed"] == body["scope"]["period"]["failed"]


# --------------------------------------------------------------------------- (f) and (g): per payment, and the signal sum


def test_a_payment_declined_twice_then_completed_counts_once(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    start, end = chicago_range(date(2026, 10, 1), date(2026, 10, 2))
    twice = seeded_conn.execute(
        "SELECT p.id, p.amount_cents FROM payment p WHERE p.merchant_id = ? AND p.channel = 'mobile_app' AND p.created_at >= ? AND p.created_at < ? "
        "AND (SELECT COUNT(*) FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'failed') = 2 "
        "AND EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'succeeded' AND a.attempt_number = 3)",
        (alder, start, end),
    ).fetchall()
    assert twice, "the scripted history holds a payment that recovered on its third attempt"
    body = get(client_as("maya"), OCT_1_2_MOBILE)
    distinct = seeded_conn.execute(
        "SELECT COUNT(*), SUM(amount_cents) FROM payment p WHERE p.merchant_id = ? AND p.channel = 'mobile_app' AND p.created_at >= ? AND p.created_at < ? "
        "AND EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id AND a.outcome = 'failed')",
        (alder, start, end),
    ).fetchone()
    per_attempt = seeded_conn.execute(
        "SELECT COUNT(*), SUM(p.amount_cents) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id WHERE p.merchant_id = ? AND p.channel = 'mobile_app' "
        "AND p.created_at >= ? AND p.created_at < ? AND a.outcome = 'failed'",
        (alder, start, end),
    ).fetchone()
    assert (body["recovery"]["affected"], body["recovery"]["affected_cents"]) == tuple(distinct)
    assert per_attempt[0] > distinct[0] and per_attempt[1] > distinct[1], "counting per attempt would overstate both"
    assert per_attempt[0] - distinct[0] >= len(twice)
    for pid, _amount in twice:
        assert pid not in {i["id"] for i in body["unresolved_payments"]["items"]}
        assert client_as("maya").get(f"/api/payments/{pid}").json()["status"] == "succeeded"


def test_signal_counts_sum_to_failed_attempts_in_every_scope(client_as) -> None:
    c = client_as("maya")
    for query in (LAST_7, "period=last_30_days", "period=month_to_date", OCT_1_2_MOBILE, f"{LAST_7}&channel=in_store"):
        body = get(c, query)
        items = body["failure_signals"]["items"]
        assert sum(s["count"] for s in items) == body["failure_signals"]["total_failed"] == body["scope"]["period"]["failed"], query
        assert items == sorted(items, key=lambda s: (-s["count"], s["failure_code"])), query
        assert len({s["failure_code"] for s in items}) == len(items), query


# --------------------------------------------------------------------------- (h) merchant isolation


def test_other_merchants_see_only_their_own_figures(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    alder = ids.merchant("alder-loom")
    maya = get(client_as("maya"), "period=last_30_days")
    for persona, slug in (("priya", "juniper-trail"), ("sam_copper", "copper-finch")):
        merchant_id = ids.merchant(slug)
        body = get(client_as(persona), "period=last_30_days")
        assert_scoped(ids, body, merchant_id)
        assert not {i for i in collect_ids(body) if ids.owner_of.get(i) == alder}
        start, end = chicago_range(date(2026, 9, 6), date(2026, 10, 5))
        assert strip(body["scope"]["period"]) == outcomes(seeded_conn, merchant_id, None, start, end)
        assert body["scope"]["period"] != maya["scope"]["period"] and body["recovery"] != maya["recovery"]
        expected = cohort(seeded_conn, merchant_id, None, start, end)
        expected.pop("unresolved_ids")
        assert body["recovery"] == expected
        with_foreign_id = get(client_as(persona), f"period=last_30_days&merchant_id={alder}")
        assert with_foreign_id == body


# --------------------------------------------------------------------------- (i) thin scopes


def test_copper_finch_mobile_on_a_quiet_sunday_has_insufficient_volume(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = get(client_as("sam_copper"), "period=custom&from=2026-09-27&to=2026-09-27&channel=mobile_app")
    start, end = chicago_range(date(2026, 9, 27), date(2026, 9, 27))
    assert strip(body["scope"]["period"]) == outcomes(seeded_conn, ids.merchant("copper-finch"), "mobile_app", start, end)
    assert (body["scope"]["period"]["succeeded"], body["scope"]["period"]["failed"], body["scope"]["period"]["success_rate_bp"]) == (3, 2, 6000)
    assert body["scope"]["status"] == "insufficient_volume" and body["scope"]["status_label"] == "Insufficient volume"
    assert body["attention"]["status"] == "insufficient_volume" and body["attention"]["headline"] == "Insufficient volume to evaluate payment health"
    assert body["attention"]["detail"].startswith("5 completed attempts in the period (30 needed) and ")
    assert body["attention"]["detail"].endswith(" in the baseline (100 needed). Counts are shown without a verdict.")
    assert body["attention"]["degraded_channels"] == [] and body["trend"]["baseline_rate_bp"] is None
    assert body["trend"]["points"] == [{"day": "2026-09-27", "succeeded": 3, "failed": 2, "completed": 5, "success_rate_bp": 6000, "low_volume": True}]


def test_copper_finch_website_on_the_clock_day_has_pending_attempts_and_no_rate(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    body = get(client_as("sam_copper"), "period=custom&from=2026-10-05&to=2026-10-05&channel=website")
    start, end = chicago_range(date(2026, 10, 5), date(2026, 10, 5))
    expected = outcomes(seeded_conn, ids.merchant("copper-finch"), "website", start, end)
    assert strip(body["scope"]["period"]) == expected
    assert expected["completed"] == 0 and expected["pending"] == 2
    assert body["scope"]["period"]["success_rate_bp"] is None and body["scope"]["period"]["failed_share_bp"] is None
    assert body["scope"]["status"] == "insufficient_volume" and body["scope"]["drop_bp"] is None and body["scope"]["worst_day"] is None
    assert body["attention"]["headline"] == "Insufficient volume to evaluate payment health"
    assert body["attention"]["detail"].startswith("0 completed attempts in the period (30 needed)")
    assert body["trend"]["points"] == [{"day": "2026-10-05", "succeeded": 0, "failed": 0, "completed": 0, "success_rate_bp": None, "low_volume": True}]
    assert body["failure_signals"] == {"total_failed": 0, "items": [], "primary": None}


def test_juniper_trail_has_no_mobile_channel(client_as, seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    juniper = ids.merchant("juniper-trail")
    assert seeded_conn.execute("SELECT COUNT(*) FROM payment WHERE merchant_id = ? AND channel = 'mobile_app'", (juniper,)).fetchone()[0] == 0
    body = get(client_as("priya"), "period=last_30_days&channel=mobile_app")
    assert body["scope"]["period"] == {"succeeded": 0, "failed": 0, "pending": 0, "completed": 0, "success_rate_bp": None, "failed_share_bp": None}
    assert body["scope"]["baseline"]["completed"] == 0 and body["scope"]["status"] == "insufficient_volume"
    assert body["failure_signals"] == {"total_failed": 0, "items": [], "primary": None}
    assert body["recovery"]["affected"] == 0 and body["recovery"]["recovered_within_window_share_bp"] is None and body["recovery"]["affected_cents"] == 0
    assert body["unresolved_payments"] == {"total": 0, "items": []}
    assert all(p["success_rate_bp"] is None and p["low_volume"] for p in body["trend"]["points"])
    assert_scoped(ids, body, juniper)


# --------------------------------------------------------------------------- (j) validation and guards


def test_invalid_parameters_are_422(client_as, client) -> None:
    c = client_as("maya")
    for query in ("channel=bogus", "period=forever", "period=custom&from=2026-10-02&to=2026-10-01", "period=custom&from=2026-10-01", "from=not-a-date&to=2026-10-01"):
        r = c.get(f"/api/payment-health?{query}")
        assert r.status_code == 422, query
        assert r.json()["error"]["code"] == "validation_error", query
    assert c.get("/api/attempts?failure_code=bogus").status_code == 422
    assert c.get("/api/attempts?failure_code=issuer_unavailable").status_code == 200
    assert client.get("/api/payment-health").status_code == 401
    assert client_as("sam").get("/api/payment-health").status_code == 200, "every role with payments:read reads payment health"
    assert get(c, "")["period"]["preset"] == "last_7_days", "the default period is the last 7 days"


# --------------------------------------------------------------------------- (k) the incident window, by the hour


def test_incident_window_ties_the_rule_to_the_scripted_history(seeded_conn: sqlite3.Connection, ids: Ids) -> None:
    """Oct 1 15:00 to Oct 2 11:00 CT on Alder's app: the API cannot select hours, so the pure functions run over SQL rows here."""
    alder = ids.merchant("alder-loom")
    start, end = to_iso(chicago_local(2026, 10, 1, 15)), to_iso(chicago_local(2026, 10, 2, 11))
    o = outcomes(seeded_conn, alder, "mobile_app", start, end)
    window = health.Outcomes(succeeded=o["succeeded"], failed=o["failed"], pending=o["pending"])
    assert (window.succeeded, window.failed) == (25, 36) and window.success_rate_bp == 4098 == o["success_rate_bp"]
    codes = dict(signals(seeded_conn, alder, "mobile_app", start, end))
    assert codes["issuer_unavailable"] == 29 and sum(codes.values()) == 36
    assert health.rate_bp(codes["issuer_unavailable"], 36) == 8056 == rate(29, 36)

    payment_ids = [r[0] for r in seeded_conn.execute(
        "SELECT DISTINCT a.payment_id FROM payment_attempt a JOIN payment p ON p.id = a.payment_id "
        "WHERE p.merchant_id = ? AND p.channel = 'mobile_app' AND a.created_at >= ? AND a.created_at < ?", (alder, start, end),
    )]
    amounts = dict(seeded_conn.execute("SELECT id, amount_cents FROM payment WHERE id IN (%s)" % ",".join("?" * len(payment_ids)), payment_ids).fetchall())
    states: Counter[str] = Counter()
    cents: Counter[str] = Counter()
    for pid, chain in chains_for(seeded_conn, payment_ids).items():
        if not any(a["outcome"] == "failed" for a in chain):
            continue
        success = next((a for a in chain if a["outcome"] == "succeeded"), None)
        state = health.recovery_state(succeeded_at=success["completed_at"] if success else None, latest_outcome=chain[-1]["outcome"], first_attempt_at=chain[0]["created_at"])
        states[state] += 1
        cents[state] += amounts[pid]
    assert states == {"recovered_within_window": 23, "unresolved": 9} and sum(states.values()) == 32
    assert (sum(cents.values()), cents["recovered_within_window"], cents["unresolved"]) == (631409, 414876, 216533)
