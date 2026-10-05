"""Record integrity and money invariants of the seeded baseline.

Every check here is about records and ledger money. None of them sums
attempts by outcome.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.db.connection import connect
from app.seed import scenario as S
from app.seed.verify import SeedVerificationError, verify

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def one(conn: sqlite3.Connection, sql: str, *params: object) -> object:
    return conn.execute(sql, params).fetchone()[0]


def test_verify_suite_passes_on_the_baseline(seeded_conn: sqlite3.Connection) -> None:
    verify(seeded_conn)


def test_verify_suite_catches_a_payout_that_does_not_reconcile(template_db: Path, tmp_path: Path) -> None:
    broken = tmp_path / "broken.db"
    shutil.copyfile(template_db, broken)
    conn = connect(broken)
    try:
        conn.execute("UPDATE payout SET amount_cents = amount_cents + 1 WHERE id = (SELECT id FROM payout ORDER BY id LIMIT 1)")
        conn.commit()
        with pytest.raises(SeedVerificationError, match="reconcile"):
            verify(conn)
    finally:
        conn.close()


def test_every_payment_has_attempts_numbered_from_one(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment p WHERE NOT EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id)") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt a WHERE a.attempt_number > 1 AND NOT EXISTS "
                            "(SELECT 1 FROM payment_attempt b WHERE b.payment_id = a.payment_id AND b.attempt_number = a.attempt_number - 1)") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt WHERE attempt_number > 3") == 0


def test_at_most_one_success_and_nothing_after_it(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM (SELECT payment_id FROM payment_attempt WHERE outcome = 'succeeded' GROUP BY payment_id HAVING COUNT(*) > 1)") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt s JOIN payment_attempt later ON later.payment_id = s.payment_id "
                            "AND later.attempt_number > s.attempt_number WHERE s.outcome = 'succeeded'") == 0


def test_pending_attempts_are_last_recent_and_online(seeded_conn: sqlite3.Connection) -> None:
    rows = seeded_conn.execute(
        "SELECT a.payment_id, a.attempt_number, a.created_at, p.channel FROM payment_attempt a JOIN payment p ON p.id = a.payment_id WHERE a.outcome = 'pending'"
    ).fetchall()
    assert rows, "the baseline should contain payments still in flight"
    as_of = one(seeded_conn, "SELECT value FROM seed_meta WHERE key = 'as_of'")
    for payment_id, number, created_at, channel in rows:
        assert channel != "in_store"
        assert created_at <= as_of
        assert one(seeded_conn, "SELECT MAX(attempt_number) FROM payment_attempt WHERE payment_id = ?", payment_id) == number


def test_attempt_chain_is_chronological(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt a JOIN payment_attempt b ON a.payment_id = b.payment_id "
                            "AND a.attempt_number < b.attempt_number WHERE a.completed_at IS NULL OR a.completed_at > b.created_at") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt a JOIN payment p ON p.id = a.payment_id WHERE a.created_at < p.created_at") == 0


def test_refunds_follow_a_success_and_never_exceed_the_amount(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM refund r WHERE NOT EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = r.payment_id "
                            "AND a.outcome = 'succeeded' AND a.completed_at <= r.created_at)") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM (SELECT r.payment_id, SUM(r.amount_cents) s, p.amount_cents a FROM refund r "
                            "JOIN payment p ON p.id = r.payment_id GROUP BY r.payment_id) WHERE s > a") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM refund WHERE status = 'pending'") >= 1
    assert one(seeded_conn, "SELECT COUNT(*) FROM refund WHERE status = 'pending' AND completed_at IS NOT NULL") == 0


def test_each_success_posts_exactly_one_charge_and_one_fee(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt a WHERE a.outcome = 'succeeded' AND ("
                            "(SELECT COUNT(*) FROM balance_movement m WHERE m.attempt_id = a.id AND m.type = 'charge') != 1 OR "
                            "(SELECT COUNT(*) FROM balance_movement m WHERE m.attempt_id = a.id AND m.type = 'fee') != 1)") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM balance_movement m JOIN payment_attempt a ON a.id = m.attempt_id WHERE a.outcome != 'succeeded'") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM balance_movement m JOIN payment p ON p.id = m.payment_id "
                            "WHERE m.type = 'charge' AND (m.amount_cents != p.amount_cents OR m.posted_at != "
                            "(SELECT completed_at FROM payment_attempt a WHERE a.id = m.attempt_id))") == 0


def test_fee_amounts_follow_the_schedule(seeded_conn: sqlite3.Connection) -> None:
    from app.core.money import fee_cents

    rows = seeded_conn.execute(
        "SELECT p.amount_cents, p.channel, m.amount_cents FROM balance_movement m JOIN payment p ON p.id = m.payment_id WHERE m.type = 'fee'"
    ).fetchall()
    assert rows
    for amount, channel, fee in rows:
        assert fee == -fee_cents(amount, channel)


def test_refund_and_dispute_movements_pair_with_their_records(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM refund r WHERE (r.status = 'succeeded') != "
                            "((SELECT COUNT(*) FROM balance_movement m WHERE m.refund_id = r.id AND m.type = 'refund' AND m.amount_cents = -r.amount_cents) = 1)") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM dispute d WHERE "
                            "(SELECT COUNT(*) FROM balance_movement m WHERE m.dispute_id = d.id AND m.type = 'dispute_reversal' AND m.amount_cents = -d.amount_cents) != 1 OR "
                            "(SELECT COUNT(*) FROM balance_movement m WHERE m.dispute_id = d.id AND m.type = 'dispute_fee' AND m.amount_cents = ?) != 1 OR "
                            "((SELECT COUNT(*) FROM balance_movement m WHERE m.dispute_id = d.id AND m.type = 'dispute_reinstatement' AND m.amount_cents = d.amount_cents) != (d.status = 'won'))",
               -S.DISPUTE_FEE_CENTS) == 0


def test_every_payout_reconciles_exactly_to_its_movements(seeded_conn: sqlite3.Connection) -> None:
    rows = seeded_conn.execute(
        "SELECT p.id, p.amount_cents, (SELECT COALESCE(SUM(m.amount_cents), 0) FROM balance_movement m WHERE m.payout_id = p.id), "
        "(SELECT COUNT(*) FROM balance_movement m WHERE m.payout_id = p.id) FROM payout p"
    ).fetchall()
    assert len(rows) == 29
    for _, amount, ledger_sum, count in rows:
        assert amount == ledger_sum
        assert count > 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM balance_movement m JOIN payout p ON p.id = m.payout_id WHERE m.available_at >= p.cutoff_at") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM balance_movement m WHERE m.payout_id IS NULL AND m.available_at < "
                            "(SELECT MAX(cutoff_at) FROM payout p WHERE p.merchant_id = m.merchant_id)") == 0


def test_payout_statuses_follow_the_clock(seeded_conn: sqlite3.Connection) -> None:
    as_of = one(seeded_conn, "SELECT value FROM seed_meta WHERE key = 'as_of'")
    assert one(seeded_conn, "SELECT COUNT(*) FROM payout WHERE status = 'paid' AND (paid_at IS NULL OR paid_at > ?)", as_of) == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM payout WHERE status = 'in_transit' AND paid_at IS NOT NULL") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM payout WHERE status = 'in_transit'") >= 1
    assert one(seeded_conn, "SELECT COUNT(*) FROM payout WHERE status = 'paid'") >= 1
    # Labor Day 2026-09-07 is not a business day: no cutoff falls on it.
    assert one(seeded_conn, "SELECT COUNT(*) FROM payout WHERE cutoff_at = '2026-09-07T05:00:00Z'") == 0


def test_children_belong_to_their_parents_merchant(seeded_conn: sqlite3.Connection) -> None:
    pairs = (("payment_attempt", "payment", "payment_id"), ("refund", "payment", "payment_id"), ("dispute", "payment", "payment_id"),
             ("note_event", "payment", "payment_id"), ("note_event", "dispute", "dispute_id"), ("balance_movement", "payment", "payment_id"),
             ("balance_movement", "payout", "payout_id"), ("payment", "customer", "customer_id"), ("payment", "location", "location_id"))
    for child, parent, key in pairs:
        assert one(seeded_conn, f"SELECT COUNT(*) FROM {child} c JOIN {parent} p ON p.id = c.{key} WHERE c.merchant_id != p.merchant_id") == 0, (child, key)


def test_timestamps_are_canonical_utc_inside_the_window(seeded_conn: sqlite3.Connection) -> None:
    meta = dict(seeded_conn.execute("SELECT key, value FROM seed_meta"))
    for table, column in (("payment", "created_at"), ("payment_attempt", "created_at"), ("payment_attempt", "completed_at"), ("refund", "created_at"),
                          ("refund", "completed_at"), ("dispute", "opened_at"), ("dispute", "evidence_due_at"), ("balance_movement", "posted_at"),
                          ("balance_movement", "available_at"), ("payout", "cutoff_at"), ("payout", "sent_at"), ("payout", "paid_at"),
                          ("note_event", "created_at")):
        for (value,) in seeded_conn.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"):
            assert ISO_UTC.match(value), (table, column, value)
    for table in ("payment", "payment_attempt", "refund", "note_event"):
        assert one(seeded_conn, f"SELECT COUNT(*) FROM {table} WHERE created_at < ? OR created_at > ?", meta["window_start"], meta["as_of"]) == 0


def test_shared_email_is_two_unrelated_customers(seeded_conn: sqlite3.Connection) -> None:
    rows = seeded_conn.execute(
        "SELECT c.id, m.slug FROM customer c JOIN merchant m ON m.id = c.merchant_id WHERE c.email = 'avery.stone@example.com' ORDER BY m.slug"
    ).fetchall()
    assert [slug for _, slug in rows] == ["alder-loom", "juniper-trail"]
    assert len({cid for cid, _ in rows}) == 2
    assert one(seeded_conn, "SELECT COUNT(*) FROM (SELECT merchant_id, email FROM customer GROUP BY merchant_id, email HAVING COUNT(*) > 1)") == 0


def test_only_synthetic_identities(seeded_conn: sqlite3.Connection) -> None:
    assert one(seeded_conn, "SELECT COUNT(*) FROM customer WHERE email NOT LIKE '%@example.com'") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM app_user WHERE email NOT LIKE '%@%.example.com' AND email NOT LIKE '%@example.com'") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM payment_attempt WHERE card_last4 IS NOT NULL AND LENGTH(card_last4) != 4") == 0
    assert one(seeded_conn, "SELECT COUNT(*) FROM merchant WHERE LENGTH(destination_last4) != 4 OR destination_kind != 'external bank account'") == 0


def test_anchor_payment_reads_as_the_brief_describes(seeded_conn: sqlite3.Connection) -> None:
    payment = seeded_conn.execute(
        "SELECT p.id, p.amount_cents, p.channel, c.email FROM payment p JOIN customer c ON c.id = p.customer_id WHERE p.created_at = '2026-09-22T19:11:37Z'"
    ).fetchone()
    assert payment["email"] == "taylor.reed@example.com" and payment["channel"] == "website"
    attempts = seeded_conn.execute(
        "SELECT attempt_number, card_brand, card_last4, outcome, failure_code FROM payment_attempt WHERE payment_id = ? ORDER BY attempt_number", (payment["id"],)
    ).fetchall()
    assert [tuple(a) for a in attempts] == [(1, "visa", "4242", "failed", "insufficient_funds"), (2, "mastercard", "8812", "succeeded", None)]
    refund = seeded_conn.execute("SELECT amount_cents, reason, status FROM refund WHERE payment_id = ?", (payment["id"],)).fetchone()
    assert tuple(refund) == (4800, "price_adjustment", "succeeded")
    assert one(seeded_conn, "SELECT COUNT(*) FROM balance_movement WHERE payment_id = ? AND payout_id IS NOT NULL AND type = 'charge'", payment["id"]) == 1
    note = seeded_conn.execute(
        "SELECT u.full_name FROM note_event n JOIN app_user u ON u.id = n.actor_user_id WHERE n.payment_id = ? AND n.kind = 'note'", (payment["id"],)
    ).fetchone()
    assert note["full_name"] == "Maya Chen"
