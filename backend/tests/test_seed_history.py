"""The scripted stretches of synthetic merchant transaction history.

``scenario.SCRIPTED_WINDOWS`` tells a few periods of attempt history exactly: Alder & Loom's app
checkout from Thursday 1 October 15:00 to Friday 2 October 11:00 (Chicago), a quiet Sunday for
Copper Finch's app, and Copper Finch's website on the morning of the clock. These tests pin what
those fixtures contain, that the surrounding history stays ordinary, that every retry is its own
attempt record, and that downstream records (ledger, payouts) follow only completed attempts.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date, timedelta

from app.core.tz import chicago_day_bounds, chicago_local, parse_iso, to_iso
from app.seed import scenario as S
from app.seed.generate import build_dataset

APP_WINDOW_START = to_iso(chicago_local(2026, 10, 1, 15, 0))
APP_WINDOW_END = to_iso(chicago_local(2026, 10, 2, 11, 0))
ONE_HOUR = timedelta(hours=1)


def one(conn: sqlite3.Connection, sql: str, *params: object) -> object:
    return conn.execute(sql, params).fetchone()[0]


def merchant_id(conn: sqlite3.Connection, slug: str) -> str:
    return str(one(conn, "SELECT id FROM merchant WHERE slug = ?", slug))


def window_attempts(conn: sqlite3.Connection, slug: str, channel: str, start: str, end: str) -> list[sqlite3.Row]:
    """Attempts of one merchant channel created inside [start, end)."""
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    return cur.execute(
        "SELECT a.*, p.amount_cents, p.customer_id, p.created_at AS payment_created_at FROM payment_attempt a "
        "JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE p.merchant_id = ? AND p.channel = ? AND a.created_at >= ? AND a.created_at < ? ORDER BY a.created_at, a.attempt_number",
        (merchant_id(conn, slug), channel, start, end),
    ).fetchall()


def chains(conn: sqlite3.Connection, payment_ids: set[str]) -> dict[str, list[sqlite3.Row]]:
    """Every attempt of the given payments, in attempt order."""
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    out: dict[str, list[sqlite3.Row]] = {pid: [] for pid in payment_ids}
    for row in cur.execute("SELECT * FROM payment_attempt ORDER BY payment_id, attempt_number"):
        if row["payment_id"] in out:
            out[row["payment_id"]].append(row)
    return out


def app_window_payments(conn: sqlite3.Connection) -> tuple[dict[str, list[sqlite3.Row]], dict[str, int]]:
    rows = window_attempts(conn, "alder-loom", "mobile_app", APP_WINDOW_START, APP_WINDOW_END)
    amounts = {r["payment_id"]: r["amount_cents"] for r in rows}
    return chains(conn, set(amounts)), amounts


def recovered(chain: list[sqlite3.Row]) -> bool:
    """A declined payment whose later attempt succeeded within an hour of the first attempt."""
    first = parse_iso(chain[0]["created_at"])
    success = [a for a in chain if a["outcome"] == "succeeded"]
    return bool(success) and parse_iso(success[0]["completed_at"]) - first <= ONE_HOUR


def declined(chain: list[sqlite3.Row]) -> bool:
    return any(a["outcome"] == "failed" for a in chain)


def day_outcomes(conn: sqlite3.Connection, slug: str, channel: str) -> dict[date, Counter[str]]:
    """Attempt outcomes per Chicago calendar day for one merchant channel."""
    out: dict[date, Counter[str]] = {}
    day = S.WINDOW_START_DAY
    while day <= S.AS_OF_DAY:
        start, end = chicago_day_bounds(day)
        out[day] = Counter(r["outcome"] for r in window_attempts(conn, slug, channel, start, end))
        day += timedelta(days=1)
    return out


def failure_rate(counts: Counter[str]) -> float:
    completed = counts["failed"] + counts["succeeded"]
    return counts["failed"] / completed if completed else 0.0


# --------------------------------------------------------------------- the app-checkout window


def test_app_window_attempt_counts(seeded_conn: sqlite3.Connection) -> None:
    rows = window_attempts(seeded_conn, "alder-loom", "mobile_app", APP_WINDOW_START, APP_WINDOW_END)
    outcomes = Counter(r["outcome"] for r in rows)
    assert len(rows) == 61
    assert outcomes == {"failed": 36, "succeeded": 25}
    codes = Counter(r["failure_code"] for r in rows if r["outcome"] == "failed")
    assert codes["issuer_unavailable"] == 29
    assert set(codes) <= set(S.DECLINE_CODES)
    assert all(r["failure_message"] == S.DECLINE_CODES[r["failure_code"]] for r in rows if r["outcome"] == "failed")
    assert all(r["failure_code"] is None and r["failure_message"] is None for r in rows if r["outcome"] == "succeeded")


def test_app_window_payments_and_recovery(seeded_conn: sqlite3.Connection) -> None:
    by_payment, _ = app_window_payments(seeded_conn)
    affected = {pid: chain for pid, chain in by_payment.items() if declined(chain)}
    assert len(affected) == 32
    recovered_ids = {pid for pid, chain in affected.items() if recovered(chain)}
    unresolved_ids = {pid for pid, chain in affected.items() if not any(a["outcome"] == "succeeded" for a in chain)}
    assert len(recovered_ids) == 23
    assert len(unresolved_ids) == 9
    assert recovered_ids | unresolved_ids == set(affected) and not recovered_ids & unresolved_ids
    shapes = Counter((sum(a["outcome"] == "failed" for a in chain), any(a["outcome"] == "succeeded" for a in chain)) for chain in affected.values())
    assert shapes[(1, True)] >= 15 and shapes[(2, True)] >= 1, "retries that succeed after one and after two declines"
    assert shapes[(1, False)] >= 1 and shapes[(2, False)] >= 1, "declines with no further attempt, once and twice"
    assert sum(a["outcome"] == "pending" for chain in by_payment.values() for a in chain) == 0


def test_app_window_retries_are_distinct_attempt_records(seeded_conn: sqlite3.Connection) -> None:
    by_payment, _ = app_window_payments(seeded_conn)
    for pid, chain in by_payment.items():
        assert [a["attempt_number"] for a in chain] == list(range(1, len(chain) + 1)), pid
        assert len({a["id"] for a in chain}) == len(chain), pid
        for earlier, later in zip(chain, chain[1:]):
            assert earlier["outcome"] == "failed", f"{pid}: only a declined attempt is followed by another"
            assert earlier["completed_at"] <= later["created_at"], pid
        assert sum(a["outcome"] == "succeeded" for a in chain) <= 1, pid
        if chain[-1]["outcome"] == "succeeded":
            assert all(a["outcome"] == "failed" and a["failure_code"] for a in chain[:-1]), f"{pid}: declined attempts keep their outcome and code"


def test_app_window_amount_is_the_payment_amount_on_every_attempt(seeded_conn: sqlite3.Connection) -> None:
    by_payment, amounts = app_window_payments(seeded_conn)
    for pid, chain in by_payment.items():
        # The amount lives on the payment, so every attempt in the chain carries it; the ledger charge, when there is one, matches it.
        charged = seeded_conn.execute("SELECT amount_cents, attempt_id FROM balance_movement WHERE payment_id = ? AND type = 'charge'", (pid,)).fetchall()
        succeeded = [a for a in chain if a["outcome"] == "succeeded"]
        assert len(charged) == len(succeeded), pid
        for amount, attempt_id in charged:
            assert amount == amounts[pid] and attempt_id == succeeded[0]["id"], pid


def test_app_window_payment_values(seeded_conn: sqlite3.Connection) -> None:
    by_payment, amounts = app_window_payments(seeded_conn)
    affected = {pid for pid, chain in by_payment.items() if declined(chain)}
    recovered_ids = {pid for pid in affected if recovered(by_payment[pid])}
    affected_value = sum(amounts[pid] for pid in affected)
    recovered_value = sum(amounts[pid] for pid in recovered_ids)
    unresolved_value = sum(amounts[pid] for pid in affected - recovered_ids)
    assert 500_000 <= affected_value <= 700_000
    assert 350_000 <= recovered_value <= 500_000
    assert affected_value == recovered_value + unresolved_value
    values = sorted(amounts.values())
    assert values[0] >= 2_500 and values[-1] <= 60_000
    assert sum(v <= 25_000 for v in values) > len(values) / 2, "most purchases are under $250"
    assert any(v > 25_000 for v in values), "some purchases are between $250 and $600"
    assert len({v % 100 for v in values}) > 5, "realistic cents, not round dollars"


def test_app_window_shoppers_vary(seeded_conn: sqlite3.Connection) -> None:
    rows = window_attempts(seeded_conn, "alder-loom", "mobile_app", APP_WINDOW_START, APP_WINDOW_END)
    customers = {r["payment_id"]: r["customer_id"] for r in rows}
    named = [c for c in customers.values() if c]
    assert len(named) == len(set(named)), "each named shopper appears once in the window"
    assert len(customers) - len(named) >= 1, "some payments are guest checkouts"
    returning = one(seeded_conn, "SELECT COUNT(*) FROM customer c WHERE c.id IN (%s) AND (SELECT COUNT(*) FROM payment p WHERE p.customer_id = c.id) > 1"
                    % ",".join("?" * len(named)), *named)
    assert returning >= 1, "some shoppers have history outside the window"
    methods = Counter((r["method_type"], r["wallet_type"]) for r in rows)
    assert methods[("card", None)] and methods[("wallet", "apple_pay")] and methods[("wallet", "google_pay")]


# --------------------------------------------------------------------- channels and the rest of the history


def test_app_window_sits_in_the_mobile_channel_only(seeded_conn: sqlite3.Connection) -> None:
    rates = {ch: Counter(r["outcome"] for r in window_attempts(seeded_conn, "alder-loom", ch, APP_WINDOW_START, APP_WINDOW_END))
             for ch in ("mobile_app", "website", "in_store")}
    assert failure_rate(rates["mobile_app"]) > 0.5
    for channel in ("website", "in_store"):
        assert rates[channel]["failed"] <= 6, channel
        assert failure_rate(rates[channel]) <= 0.2, channel


def test_mobile_history_outside_the_window_is_ordinary(seeded_conn: sqlite3.Connection) -> None:
    per_day = day_outcomes(seeded_conn, "alder-loom", "mobile_app")
    window_days = {date(2026, 10, 1), date(2026, 10, 2)}
    outside = Counter()
    for day, counts in per_day.items():
        if day in window_days:
            continue
        outside.update(counts)
        assert 0 <= counts["failed"] <= 6, day
    assert 0.05 <= failure_rate(outside) <= 0.13
    assert 27 <= per_day[date(2026, 10, 1)]["failed"] <= 33
    assert 8 <= per_day[date(2026, 10, 2)]["failed"] <= 13
    for day in (date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 3), date(2026, 10, 4)):
        assert per_day[day]["failed"] + per_day[day]["succeeded"] >= 10, f"{day}: ordinary days surround the window"


def test_other_channels_have_no_comparable_day(seeded_conn: sqlite3.Connection) -> None:
    for channel in ("website", "in_store"):
        for day, counts in day_outcomes(seeded_conn, "alder-loom", channel).items():
            completed = counts["failed"] + counts["succeeded"]
            if completed >= 10:
                assert failure_rate(counts) <= 0.25, (channel, day)
            assert counts["failed"] <= 8, (channel, day)


def test_low_volume_channel_period(seeded_conn: sqlite3.Connection) -> None:
    start, end = chicago_day_bounds(date(2026, 9, 27))
    counts = Counter(r["outcome"] for r in window_attempts(seeded_conn, "copper-finch", "mobile_app", start, end))
    assert counts == {"failed": 2, "succeeded": 3}


def test_channel_period_with_pending_attempts_and_nothing_completed(seeded_conn: sqlite3.Connection) -> None:
    start, end = chicago_day_bounds(date(2026, 10, 5))
    rows = window_attempts(seeded_conn, "copper-finch", "website", start, end)
    counts = Counter(r["outcome"] for r in rows)
    assert counts["pending"] >= 2 and counts["failed"] == 0 and counts["succeeded"] == 0
    assert all(r["completed_at"] is None for r in rows)


# --------------------------------------------------------------------- isolation and downstream records


def test_window_belongs_to_one_merchant(seeded_conn: sqlite3.Connection, client_as) -> None:
    alder = merchant_id(seeded_conn, "alder-loom")
    others = seeded_conn.execute(
        "SELECT a.failure_code, COUNT(*) FROM payment_attempt a WHERE a.merchant_id <> ? AND a.outcome = 'failed' AND a.created_at >= ? AND a.created_at < ? GROUP BY 1",
        (alder, APP_WINDOW_START, APP_WINDOW_END),
    ).fetchall()
    assert sum(n for _, n in others) <= 3
    assert all(code != "issuer_unavailable" for code, _ in others)
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt WHERE failure_code = 'issuer_unavailable' AND merchant_id <> ?", alder) <= 2
    by_payment, _ = app_window_payments(seeded_conn)
    assert all(chain[0]["merchant_id"] == alder for chain in by_payment.values())
    sample = sorted(by_payment)[0]
    assert client_as("maya").get(f"/api/payments/{sample}").status_code == 200
    assert client_as("priya").get(f"/api/payments/{sample}").status_code == 404
    assert client_as("sam_copper").get(f"/api/payments/{sample}").status_code == 404


def test_ledger_and_payouts_follow_only_completed_attempts(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM balance_movement m WHERE m.type IN ('charge', 'fee') AND NOT EXISTS "
                            "(SELECT 1 FROM payment_attempt a WHERE a.id = m.attempt_id AND a.outcome = 'succeeded')") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM balance_movement m JOIN payment_attempt a ON a.id = m.attempt_id WHERE m.type = 'charge' AND m.posted_at <> a.completed_at") == 0
    by_payment, _ = app_window_payments(seeded_conn)
    for pid, chain in by_payment.items():
        movements = seeded_conn.execute("SELECT type, posted_at, payout_id FROM balance_movement WHERE payment_id = ?", (pid,)).fetchall()
        success = [a for a in chain if a["outcome"] == "succeeded"]
        if not success:
            assert movements == [], f"{pid}: a payment with no completed attempt posts nothing"
            continue
        assert {m[0] for m in movements} >= {"charge", "fee"}
        for _type, posted_at, payout_id in movements:
            assert posted_at >= success[0]["completed_at"], pid
            if payout_id:
                cutoff = one(seeded_conn, "SELECT cutoff_at FROM payout WHERE id = ?", payout_id)
                assert posted_at < cutoff, pid
    assert one(seeded_conn, "SELECT COUNT(*) FROM payout p WHERE p.amount_cents <> (SELECT COALESCE(SUM(amount_cents), 0) FROM balance_movement WHERE payout_id = p.id)") == 0


def test_window_payments_carry_notes(seeded_conn: sqlite3.Connection) -> None:
    by_payment, _ = app_window_payments(seeded_conn)
    notes = seeded_conn.execute(
        "SELECT n.payment_id, n.created_at, u.email FROM note_event n JOIN app_user u ON u.id = n.actor_user_id WHERE n.kind = 'note' AND n.payment_id IN (%s)"
        % ",".join("?" * len(by_payment)), tuple(by_payment)).fetchall()
    assert len(notes) == 3
    noted = Counter()
    for pid, created_at, email in notes:
        chain = by_payment[pid]
        assert created_at >= max(a["completed_at"] or a["created_at"] for a in chain), "notes come after the attempts they describe"
        assert email == "maya.chen@alder-loom.example.com"
        noted[(sum(a["outcome"] == "failed" for a in chain), any(a["outcome"] == "succeeded" for a in chain))] += 1
    assert noted == {(2, True): 1, (1, True): 1, (2, False): 1}


def test_scripted_history_is_deterministic() -> None:
    first, second = build_dataset(), build_dataset()
    inside = lambda a: APP_WINDOW_START <= a.created_at < APP_WINDOW_END  # noqa: E731
    assert [a for a in first.attempts if inside(a)] == [a for a in second.attempts if inside(a)]
    assert first.payments == second.payments and first.note_events == second.note_events
