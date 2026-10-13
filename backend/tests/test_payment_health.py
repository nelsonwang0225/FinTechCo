"""Payment Health: attempt metrics, degradation verdicts, recovery and failure signals reconcile with base records.

Every figure is recomputed here with independent SQL on the seeded template, then compared with /api/payment-health.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date

import pytest

from app.api import payment_health as health_api
from app.core import health
from app.core.labels import FAILURE_CODE_LABELS
from app.core.tz import chicago_range, parse_iso
from app.seed import scenario as S
from tests.conftest import Ids, assert_scoped

LAST_7 = (date(2026, 9, 29), date(2026, 10, 5))
BASELINE_7 = (date(2026, 8, 30), date(2026, 9, 28))
CHANNELS = (None, "website", "mobile_app", "in_store")


def expected_counts(conn: sqlite3.Connection, merchant_id: str, days: tuple[date, date], channel: str | None) -> Counter[str]:
    start, end = chicago_range(*days)
    sql = (
        "SELECT a.outcome, COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = ? AND a.created_at >= ? AND a.created_at < ?"
    )
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    return Counter(dict(conn.execute(sql + " GROUP BY a.outcome", params).fetchall()))


def half_up_bps(num: int, den: int) -> int | None:
    if den == 0:
        return None
    whole, rest = divmod(num * 10000, den)
    return whole + (1 if rest * 2 >= den else 0)


def health_for(client, query: str = "") -> dict:
    response = client.get(f"/api/payment-health{query}")
    assert response.status_code == 200, response.text
    return response.json()


def chain_rows(conn: sqlite3.Connection, merchant_id: str, days: tuple[date, date], channel: str | None) -> dict[str, list[sqlite3.Row]]:
    """Every attempt of every payment created in the period, grouped by payment, in attempt order."""
    start, end = chicago_range(*days)
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    sql = (
        "SELECT a.*, p.amount_cents, p.channel, p.created_at AS payment_created_at FROM payment_attempt a "
        "JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id WHERE p.merchant_id = ? AND p.created_at >= ? AND p.created_at < ?"
    )
    params: list[object] = [merchant_id, start, end]
    if channel:
        sql += " AND p.channel = ?"
        params.append(channel)
    out: dict[str, list[sqlite3.Row]] = {}
    for row in cur.execute(sql + " ORDER BY a.payment_id, a.attempt_number", params):
        out.setdefault(row["payment_id"], []).append(row)
    return out


# --------------------------------------------------------------------- attempt metrics


@pytest.mark.parametrize("channel", CHANNELS)
def test_attempt_metrics_reconcile_with_attempts(client_as, ids: Ids, seeded_conn, channel: str | None) -> None:
    body = health_for(client_as("maya"), f"?channel={channel}" if channel else "")
    expected = expected_counts(seeded_conn, ids.merchant("alder-loom"), LAST_7, channel)
    baseline = expected_counts(seeded_conn, ids.merchant("alder-loom"), BASELINE_7, channel)
    scope = body["scope"]
    assert (scope["period"]["succeeded"], scope["period"]["failed"], scope["period"]["pending"]) == (expected["succeeded"], expected["failed"], expected["pending"])
    assert scope["period"]["completed"] == expected["succeeded"] + expected["failed"], "pending attempts stay out of the denominator"
    assert scope["period"]["success_rate_bps"] == half_up_bps(expected["succeeded"], expected["succeeded"] + expected["failed"])
    assert scope["baseline"]["succeeded"] == baseline["succeeded"] and scope["baseline"]["failed"] == baseline["failed"]
    assert scope["change_bps"] == scope["period"]["success_rate_bps"] - scope["baseline"]["success_rate_bps"]
    trend = body["trend"]
    assert [p["day"] for p in trend] == [f"2026-09-{d}" for d in (29, 30)] + [f"2026-10-0{d}" for d in range(1, 6)]
    assert sum(p["succeeded"] for p in trend) == expected["succeeded"]
    assert sum(p["failed"] for p in trend) == expected["failed"]
    assert sum(p["pending"] for p in trend) == expected["pending"]
    assert [p["partial"] for p in trend] == [False] * 6 + [True]


def test_channel_rows_add_up_to_all_channels(client_as) -> None:
    body = health_for(client_as("maya"))
    for key in ("succeeded", "failed", "pending"):
        assert sum(c["period"][key] for c in body["channels"]) == body["scope"]["period"][key]
        assert sum(c["baseline"][key] for c in body["channels"]) == body["scope"]["baseline"][key]
    assert [c["channel"] for c in body["channels"]] == ["website", "mobile_app", "in_store"]


def test_baseline_is_the_thirty_days_before_the_period(client_as) -> None:
    body = health_for(client_as("maya"))
    assert body["baseline_period"]["from_date"] == "2026-08-30" and body["baseline_period"]["to_date"] == "2026-09-28"
    body = health_for(client_as("maya"), "?from=2026-10-01&to=2026-10-02")
    assert body["baseline_period"]["from_date"] == "2026-09-01" and body["baseline_period"]["to_date"] == "2026-09-30"


# --------------------------------------------------------------------- degradation


def test_alder_mobile_app_is_degraded_with_evidence(client_as) -> None:
    body = health_for(client_as("maya"))
    assert body["attention"]["state"] == "degraded"
    degraded = {c["channel"]: c for c in body["attention"]["degraded_channels"]}
    assert set(degraded) == {"mobile_app"}
    app = degraded["mobile_app"]
    assert app["verdict_label"] == "Degraded"
    assert app["period"]["success_rate_bps"] == 7204 and app["baseline"]["success_rate_bps"] == 9079
    assert app["period"]["failed"] == 52
    assert app["change_bps"] <= -body["rules"]["degraded_drop_bps"]
    others = {c["channel"]: c["verdict"] for c in body["channels"] if c["channel"] != "mobile_app"}
    assert others == {"website": "ok", "in_store": "ok"}


def test_selected_channel_scopes_the_verdict(client_as) -> None:
    body = health_for(client_as("maya"), "?channel=website")
    assert body["channel"] == "website"
    assert [c["channel"] for c in body["channels"]] == ["website"]
    assert body["attention"]["state"] == "ok" and body["attention"]["degraded_channels"] == []


def test_low_volume_day_is_marked_and_not_judged(client_as) -> None:
    body = health_for(client_as("sam_copper"), "?from=2026-09-27&to=2026-09-27&channel=mobile_app")
    (point,) = body["trend"]
    assert (point["succeeded"], point["failed"]) == (3, 2)
    assert point["low_volume"] is True and point["success_rate_bps"] == 6000
    assert body["channels"][0]["verdict"] == "insufficient_data"
    assert body["attention"]["state"] == "insufficient_data" and body["attention"]["insufficient_channels"] == ["mobile_app"]


def test_pending_only_period_has_no_rate(client_as) -> None:
    body = health_for(client_as("sam_copper"), "?from=2026-10-05&to=2026-10-05&channel=website")
    assert body["scope"]["period"] == {"succeeded": 0, "failed": 0, "pending": 2, "completed": 0, "success_rate_bps": None, "failure_rate_bps": None}
    assert body["attention"]["state"] == "no_data"
    assert body["trend"][0]["success_rate_bps"] is None and body["trend"][0]["low_volume"] is False
    assert body["failure_signals"] == [] and body["recovery"]["affected_count"] == 0


def test_channel_the_merchant_does_not_use_is_empty(client_as) -> None:
    body = health_for(client_as("priya"), "?channel=mobile_app")
    assert body["channels"] == [] and body["attention"]["state"] == "no_data"
    assert all(p["success_rate_bps"] is None for p in body["trend"])


def test_period_without_failures(client_as) -> None:
    body = health_for(client_as("maya"), "?from=2026-09-29&to=2026-09-29&channel=mobile_app")
    assert body["scope"]["period"]["failed"] == 0 and body["scope"]["period"]["success_rate_bps"] == 10000
    assert body["scope"]["period"]["failure_rate_bps"] == 0
    assert body["failure_signals"] == [] and body["recovery"]["affected_count"] == 0 and body["unresolved_payments"] == []


def test_short_baseline_is_insufficient(client_as) -> None:
    """The last 30 days' baseline falls almost entirely before the seeded window starts."""
    body = health_for(client_as("maya"), "?period=last_30_days")
    assert body["attention"]["state"] == "insufficient_data"
    assert all(c["verdict"] == "insufficient_data" for c in body["channels"])


def test_verdict_thresholds() -> None:
    def counts(succeeded: int, failed: int) -> health.OutcomeCounts:
        return health.OutcomeCounts(succeeded=succeeded, failed=failed)

    baseline = counts(900, 100)  # 9000 bps
    assert health.verdict(counts(85, 15), baseline) == "degraded"  # exactly 500 bps below
    assert health.verdict(counts(851, 149), baseline) == "ok"  # 490 bps below
    assert health.verdict(counts(20, 9), baseline) == "insufficient_data"  # 29 completed
    assert health.verdict(counts(85, 15), counts(89, 10)) == "insufficient_data"  # 99 completed baseline
    assert health.verdict(health.OutcomeCounts(pending=3), baseline) == "no_data"
    assert health.rate_bps(2, 3) == 6667 and health.rate_bps(1, 8) == 1250 and health.rate_bps(1, 0) is None
    assert health.rate_bps(1, 20000) == 1  # 0.5 bps rounds half up


# --------------------------------------------------------------------- recovery


@pytest.mark.parametrize("channel", CHANNELS)
def test_recovery_is_counted_once_per_payment(client_as, ids: Ids, seeded_conn, channel: str | None) -> None:
    body = health_for(client_as("maya"), f"?channel={channel}" if channel else "")
    chains = chain_rows(seeded_conn, ids.merchant("alder-loom"), LAST_7, channel)
    affected = {pid: c for pid, c in chains.items() if any(a["outcome"] == "failed" for a in c)}
    recovered = {pid for pid, c in affected.items() if any(a["outcome"] == "succeeded" for a in c)}
    in_progress = {pid for pid, c in affected.items() if pid not in recovered and c[-1]["outcome"] == "pending"}
    unresolved = set(affected) - recovered - in_progress

    def quick(chain: list[sqlite3.Row]) -> bool:
        success = [a for a in chain if a["outcome"] == "succeeded"]
        return bool(success) and (parse_iso(success[0]["completed_at"]) - parse_iso(chain[0]["created_at"])).total_seconds() <= 3600

    def cents(pids: set[str]) -> int:
        return sum(affected[pid][0]["amount_cents"] for pid in pids)

    r = body["recovery"]
    assert (r["affected_count"], r["recovered_count"], r["unresolved_count"], r["in_progress_count"]) == (len(affected), len(recovered), len(unresolved), len(in_progress))
    assert (r["affected_cents"], r["recovered_cents"], r["unresolved_cents"]) == (cents(set(affected)), cents(recovered), cents(unresolved))
    assert r["recovered_within_hour_count"] == sum(quick(affected[pid]) for pid in recovered)
    assert r["affected_cents"] == r["recovered_cents"] + r["unresolved_cents"] + r["in_progress_cents"]
    assert r["currency"] == "USD"
    repeated = [pid for pid, c in affected.items() if sum(a["outcome"] == "failed" for a in c) > 1]
    if channel == "mobile_app":
        assert repeated, "the app window has payments declined more than once"
    attempt_value = sum(a["amount_cents"] for c in affected.values() for a in c if a["outcome"] == "failed")
    assert r["affected_cents"] <= attempt_value and (not repeated or r["affected_cents"] < attempt_value)


def test_recovery_groups_include_retries_still_pending() -> None:
    rows = [
        {"amount_cents": 1000, "created_at": "2026-10-01T15:00:00Z", "succeeded_at": "2026-10-01T15:20:00Z", "status": "succeeded"},
        {"amount_cents": 2000, "created_at": "2026-10-01T15:00:00Z", "succeeded_at": "2026-10-01T16:00:01Z", "status": "refunded"},
        {"amount_cents": 3000, "created_at": "2026-10-01T15:00:00Z", "succeeded_at": None, "status": "pending"},
        {"amount_cents": 4000, "created_at": "2026-10-01T15:00:00Z", "succeeded_at": None, "status": "failed"},
    ]
    r = health_api.recovery(rows)  # type: ignore[arg-type]
    assert (r.affected_count, r.recovered_count, r.recovered_within_hour_count, r.in_progress_count, r.unresolved_count) == (4, 2, 1, 1, 1)
    assert (r.affected_cents, r.recovered_cents, r.recovered_within_hour_cents, r.in_progress_cents, r.unresolved_cents) == (10000, 3000, 1000, 3000, 4000)
    assert health.recovered_quickly("2026-10-01T15:00:00Z", "2026-10-01T16:00:00Z") is True
    assert health.recovered_quickly("2026-10-01T15:00:00Z", "2026-10-01T16:00:01Z") is False


def test_unresolved_list_is_the_first_page_of_failed_payments(client_as) -> None:
    c = client_as("maya")
    body = health_for(c, "?channel=mobile_app")
    listed = c.get("/api/payments?period=last_7_days&channel=mobile_app&status=failed&page_size=10").json()
    assert [p["id"] for p in body["unresolved_payments"]] == [p["id"] for p in listed["items"]]
    assert all(p["failed_attempts"] >= 1 and p["last_failure_label"] == FAILURE_CODE_LABELS[p["last_failure_code"]] for p in body["unresolved_payments"])


# --------------------------------------------------------------------- failure signals and drill-down


def test_failure_signals_reconcile_and_drill_down(client_as) -> None:
    c = client_as("maya")
    body = health_for(c, "?channel=mobile_app")
    signals = body["failure_signals"]
    assert sum(s["count"] for s in signals) == body["scope"]["period"]["failed"]
    assert signals[0]["code"] == "issuer_unavailable" and signals[0]["label"] == "Issuer unavailable"
    for s in signals:
        drill = c.get(f"/api/attempts?period=last_7_days&channel=mobile_app&outcome=failed&failure_code={s['code']}&page_size=100").json()
        assert drill["total"] == s["count"]
        assert {i["failure_code"] for i in drill["items"]} == {s["code"]}


def test_unresolved_drill_down_matches_the_payments_list(client_as) -> None:
    c = client_as("maya")
    for channel in CHANNELS:
        q = f"&channel={channel}" if channel else ""
        body = health_for(c, f"?period=last_7_days{q}")
        listed = c.get(f"/api/payments?period=last_7_days&status=failed{q}").json()
        assert listed["total"] == body["recovery"]["unresolved_count"]


def test_attempt_failure_code_filter_validates_and_exports(client_as) -> None:
    c = client_as("maya")
    assert c.get("/api/attempts?failure_code=card_declined").status_code == 422
    assert c.get("/api/attempts?sort=failure_code").status_code == 422
    total = c.get("/api/attempts?period=last_7_days&failure_code=issuer_unavailable").json()["total"]
    csv_text = c.get("/api/reports/attempts.csv?period=last_7_days&failure_code=issuer_unavailable").text
    lines = csv_text.strip().splitlines()
    assert len(lines) - 1 == total and all(",issuer_unavailable," in line for line in lines[1:])


def test_failure_code_labels_match_the_recorded_messages() -> None:
    assert FAILURE_CODE_LABELS == S.DECLINE_CODES


def test_failure_signal_options_match_the_health_breakdown(client, client_as, ids: Ids) -> None:
    assert client.get("/api/payment-health/failure-signals").status_code == 401
    c = client_as("maya")
    options = c.get("/api/payment-health/failure-signals?period=last_7_days&channel=mobile_app").json()
    assert options["signals"] == health_for(c, "?channel=mobile_app")["failure_signals"]
    assert c.get("/api/payment-health/failure-signals?channel=phone").status_code == 422
    copper = client_as("sam_copper").get("/api/payment-health/failure-signals").json()
    alder = c.get("/api/payment-health/failure-signals").json()
    assert sum(s["count"] for s in copper["signals"]) != sum(s["count"] for s in alder["signals"])
    assert_scoped(ids, copper, ids.merchant("copper-finch"))


# --------------------------------------------------------------------- validation and boundaries


def test_period_and_channel_validation(client, client_as) -> None:
    assert client.get("/api/payment-health").status_code == 401
    c = client_as("maya")
    assert c.get("/api/payment-health?period=custom").status_code == 422
    assert c.get("/api/payment-health?period=yesterday").status_code == 422
    assert c.get("/api/payment-health?from=2026-10-05&to=2026-10-01").status_code == 422
    response = c.get("/api/payment-health?channel=phone")
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("persona", ["maya", "daniel", "jordan", "sam"])
def test_every_role_can_read(client_as, persona: str) -> None:
    assert client_as(persona).get("/api/payment-health").status_code == 200


def test_results_are_scoped_to_the_signed_in_merchant(client_as, ids: Ids, seeded_conn) -> None:
    """The aggregate carries few ids, so isolation is asserted on values: each merchant sees exactly its own counts."""
    seen: dict[str, dict] = {}
    for persona, slug in (("maya", "alder-loom"), ("priya", "juniper-trail"), ("sam_copper", "copper-finch")):
        body = health_for(client_as(persona), "?period=month_to_date")
        merchant_id = ids.merchant(slug)
        assert_scoped(ids, body, merchant_id)
        mtd = (date(2026, 10, 1), date(2026, 10, 5))
        expected = expected_counts(seeded_conn, merchant_id, mtd, None)
        assert body["scope"]["period"]["succeeded"] == expected["succeeded"] and body["scope"]["period"]["failed"] == expected["failed"]
        chains = chain_rows(seeded_conn, merchant_id, mtd, None)
        affected = [c for c in chains.values() if any(a["outcome"] == "failed" for a in c)]
        assert body["recovery"]["affected_count"] == len(affected)
        assert body["recovery"]["affected_cents"] == sum(c[0]["amount_cents"] for c in affected)
        signal_total = seeded_conn.execute(
            "SELECT COUNT(*) FROM payment_attempt WHERE merchant_id = ? AND outcome = 'failed' AND created_at >= ? AND created_at < ?",
            (merchant_id, *chicago_range(*mtd)),
        ).fetchone()[0]
        assert sum(s["count"] for s in body["failure_signals"]) == signal_total
        seen[slug] = body
    unresolved = {slug: {p["id"] for p in b["unresolved_payments"]} for slug, b in seen.items()}
    assert unresolved["alder-loom"].isdisjoint(unresolved["copper-finch"]) and unresolved["alder-loom"].isdisjoint(unresolved["juniper-trail"])
    assert seen["alder-loom"]["scope"] != seen["copper-finch"]["scope"]


def test_same_persona_switching_merchant_sees_only_the_new_merchant(client_as, ids: Ids) -> None:
    """Sam Okafor belongs to two merchants; each session answers for its own membership only."""
    alder = health_for(client_as("sam"), "?channel=mobile_app")
    copper = health_for(client_as("sam_copper"), "?channel=mobile_app")
    assert_scoped(ids, alder, ids.merchant("alder-loom"))
    assert_scoped(ids, copper, ids.merchant("copper-finch"))
    assert alder["scope"]["period"]["completed"] > copper["scope"]["period"]["completed"]
