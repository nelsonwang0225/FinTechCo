"""Invariant suite run after seeding. Any violation fails the seed.

These checks are about record integrity and money, never about outcome
statistics.
"""

from __future__ import annotations

import re
import sqlite3

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class SeedVerificationError(AssertionError):
    pass


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise SeedVerificationError(message)


def verify(conn: sqlite3.Connection) -> None:
    q = conn.execute

    meta = {k: v for k, v in q("SELECT key, value FROM seed_meta")}
    _check("as_of" in meta, "seed_meta.as_of missing")
    window_start, as_of = meta["window_start"], meta["as_of"]

    # Timestamps: canonical format and inside the window.
    for table, col in (("payment", "created_at"), ("payment_attempt", "created_at"), ("refund", "created_at"), ("dispute", "opened_at"),
                       ("balance_movement", "posted_at"), ("payout", "cutoff_at"), ("note_event", "created_at")):
        rows = q(f"SELECT {col} FROM {table}").fetchall()
        for (value,) in rows:
            _check(bool(ISO.match(value)), f"{table}.{col} not canonical: {value}")
        if table in ("payment", "payment_attempt", "refund", "note_event"):
            bad = q(f"SELECT COUNT(*) FROM {table} WHERE {col} < ? OR {col} > ?", (window_start, as_of)).fetchone()[0]
            _check(bad == 0, f"{bad} rows of {table} outside the window")

    # Attempts: contiguous numbering, at most one success, nothing after a success, pending only last.
    _check(q("SELECT COUNT(*) FROM payment p WHERE NOT EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = p.id)").fetchone()[0] == 0,
           "payment without attempts")
    for payment_id, numbers, outcomes in q(
        "SELECT payment_id, GROUP_CONCAT(attempt_number, ','), GROUP_CONCAT(outcome, ',') FROM "
        "(SELECT payment_id, attempt_number, outcome FROM payment_attempt ORDER BY payment_id, attempt_number) GROUP BY payment_id"
    ):
        nums = [int(n) for n in numbers.split(",")]
        _check(nums == list(range(1, len(nums) + 1)), f"{payment_id}: attempt numbers {nums}")
        outs = outcomes.split(",")
        _check(outs.count("succeeded") <= 1, f"{payment_id}: more than one success")
        if "succeeded" in outs:
            _check(outs[-1] == "succeeded", f"{payment_id}: attempt after success")
        if "pending" in outs:
            _check(outs[-1] == "pending" and outs.count("pending") == 1, f"{payment_id}: pending not last")

    # Attempt instants are ordered within a payment.
    _check(q(
        "SELECT COUNT(*) FROM payment_attempt a JOIN payment_attempt b ON a.payment_id = b.payment_id AND a.attempt_number < b.attempt_number "
        "WHERE a.completed_at IS NULL OR a.completed_at > b.created_at"
    ).fetchone()[0] == 0, "attempt chain out of order")

    # Refunds: only on succeeded payments, after the success, never exceeding the amount.
    _check(q(
        "SELECT COUNT(*) FROM refund r WHERE NOT EXISTS (SELECT 1 FROM payment_attempt a WHERE a.payment_id = r.payment_id AND a.outcome = 'succeeded' AND a.completed_at <= r.created_at)"
    ).fetchone()[0] == 0, "refund without a prior successful attempt")
    _check(q(
        "SELECT COUNT(*) FROM (SELECT r.payment_id, SUM(r.amount_cents) s, p.amount_cents a FROM refund r JOIN payment p ON p.id = r.payment_id GROUP BY r.payment_id) WHERE s > a"
    ).fetchone()[0] == 0, "refunds exceed payment amount")

    # Ledger pairing.
    _check(q(
        "SELECT COUNT(*) FROM payment_attempt a WHERE a.outcome = 'succeeded' AND ("
        "(SELECT COUNT(*) FROM balance_movement m WHERE m.attempt_id = a.id AND m.type = 'charge') != 1 OR "
        "(SELECT COUNT(*) FROM balance_movement m WHERE m.attempt_id = a.id AND m.type = 'fee') != 1)"
    ).fetchone()[0] == 0, "succeeded attempt without exactly one charge and one fee")
    _check(q(
        "SELECT COUNT(*) FROM balance_movement m JOIN payment_attempt a ON a.id = m.attempt_id WHERE a.outcome != 'succeeded'"
    ).fetchone()[0] == 0, "movement on a non-succeeded attempt")
    _check(q(
        "SELECT COUNT(*) FROM balance_movement m JOIN payment p ON p.id = m.payment_id WHERE m.type = 'charge' AND m.amount_cents != p.amount_cents"
    ).fetchone()[0] == 0, "charge amount differs from payment amount")
    _check(q(
        "SELECT COUNT(*) FROM refund r WHERE (r.status = 'succeeded') != ((SELECT COUNT(*) FROM balance_movement m WHERE m.refund_id = r.id) = 1)"
    ).fetchone()[0] == 0, "refund movement pairing broken")
    _check(q(
        "SELECT COUNT(*) FROM dispute d WHERE (SELECT COUNT(*) FROM balance_movement m WHERE m.dispute_id = d.id AND m.type = 'dispute_reversal') != 1 "
        "OR (SELECT COUNT(*) FROM balance_movement m WHERE m.dispute_id = d.id AND m.type = 'dispute_fee') != 1 "
        "OR ((SELECT COUNT(*) FROM balance_movement m WHERE m.dispute_id = d.id AND m.type = 'dispute_reinstatement') != (d.status = 'won'))"
    ).fetchone()[0] == 0, "dispute movement pairing broken")

    # Payouts reconcile exactly, and every movement available before a merchant's last cutoff is swept.
    _check(q(
        "SELECT COUNT(*) FROM payout p WHERE p.amount_cents != (SELECT COALESCE(SUM(m.amount_cents), 0) FROM balance_movement m WHERE m.payout_id = p.id)"
    ).fetchone()[0] == 0, "payout does not reconcile")
    _check(q("SELECT COUNT(*) FROM payout p WHERE NOT EXISTS (SELECT 1 FROM balance_movement m WHERE m.payout_id = p.id)").fetchone()[0] == 0,
           "empty payout")
    _check(q(
        "SELECT COUNT(*) FROM balance_movement m WHERE m.payout_id IS NULL AND m.available_at < (SELECT MAX(cutoff_at) FROM payout p WHERE p.merchant_id = m.merchant_id)"
    ).fetchone()[0] == 0, "available movement left unswept")
    _check(q(
        "SELECT COUNT(*) FROM balance_movement m JOIN payout p ON p.id = m.payout_id WHERE m.available_at >= p.cutoff_at OR m.merchant_id != p.merchant_id"
    ).fetchone()[0] == 0, "payout contains a movement not available at its cutoff")

    # Scoping: children agree with parents (also enforced by the composite foreign keys).
    for child, parent, key in (("payment_attempt", "payment", "payment_id"), ("refund", "payment", "payment_id"), ("dispute", "payment", "payment_id"),
                               ("note_event", "payment", "payment_id"), ("balance_movement", "payment", "payment_id"), ("balance_movement", "payout", "payout_id")):
        bad = q(f"SELECT COUNT(*) FROM {child} c JOIN {parent} p ON p.id = c.{key} WHERE c.merchant_id != p.merchant_id").fetchone()[0]
        _check(bad == 0, f"{child}.{key} crosses merchants")

    # Customers are unique per merchant and shared emails exist across merchants as distinct rows.
    _check(q("SELECT COUNT(*) FROM (SELECT merchant_id, email FROM customer GROUP BY merchant_id, email HAVING COUNT(*) > 1)").fetchone()[0] == 0,
           "duplicate customer email within a merchant")
    _check(q("SELECT COUNT(DISTINCT merchant_id) FROM customer WHERE email = 'avery.stone@example.com'").fetchone()[0] >= 2,
           "shared email should exist at two merchants")

    # Note actors are members of the merchant.
    _check(q(
        "SELECT COUNT(*) FROM note_event n WHERE NOT EXISTS (SELECT 1 FROM membership m WHERE m.user_id = n.actor_user_id AND m.merchant_id = n.merchant_id)"
    ).fetchone()[0] == 0, "note by a non-member")
