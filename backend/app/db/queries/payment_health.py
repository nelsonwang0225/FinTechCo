"""Payment Health: the attempt and payment rows its figures are derived from.

Attempts are selected on payment_attempt.created_at (as the Attempts tab is), affected payments on payment.created_at (as
the Payments list is), so every figure can be reopened in the matching list with the same period. Every function takes
merchant_id first and every statement filters on it; derivation happens in app.core.health.
"""

from __future__ import annotations

import sqlite3


def attempt_rows(merchant_id: str, conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    """Every attempt created in [start, end), with its payment's channel."""
    return conn.execute(
        "SELECT a.created_at, a.outcome, a.failure_code, p.channel FROM payment_attempt a "
        "JOIN payment p ON p.id = a.payment_id AND p.merchant_id = a.merchant_id "
        "WHERE a.merchant_id = :merchant_id AND a.created_at >= :start AND a.created_at < :end "
        "ORDER BY a.created_at, a.id",
        {"merchant_id": merchant_id, "start": start, "end": end},
    ).fetchall()


def affected_payment_rows(merchant_id: str, conn: sqlite3.Connection, start: str, end: str, channel: str | None) -> list[sqlite3.Row]:
    """Payments created in [start, end) with at least one failed attempt: one row per payment, whatever its attempt count."""
    clauses = [
        "ps.merchant_id = :merchant_id",
        "ps.created_at >= :start",
        "ps.created_at < :end",
        "EXISTS (SELECT 1 FROM payment_attempt f WHERE f.payment_id = ps.id AND f.merchant_id = :merchant_id AND f.outcome = 'failed')",
    ]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": start, "end": end}
    if channel:
        clauses.append("ps.channel = :channel")
        params["channel"] = channel
    return conn.execute(
        "SELECT ps.id, ps.amount_cents, ps.channel, ps.status, ps.succeeded_at, "
        "(SELECT a1.created_at FROM payment_attempt a1 WHERE a1.payment_id = ps.id AND a1.merchant_id = :merchant_id AND a1.attempt_number = 1) "
        "AS first_attempt_at "
        f"FROM payment_summary ps WHERE {' AND '.join(clauses)} ORDER BY ps.created_at, ps.id",
        params,
    ).fetchall()
