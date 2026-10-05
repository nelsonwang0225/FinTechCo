"""Refunds across a merchant, for the refund register export. Filters on refund.created_at."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

SELECT = """
SELECT r.id, r.payment_id, r.amount_cents, r.currency, r.reason, r.status, r.created_at, r.completed_at,
       p.order_reference, p.channel, p.customer_id,
       c.full_name AS customer_name, c.email AS customer_email, c.reference AS customer_reference
FROM refund r
JOIN payment p ON p.id = r.payment_id AND p.merchant_id = r.merchant_id
LEFT JOIN customer c ON c.id = p.customer_id AND c.merchant_id = p.merchant_id
"""


@dataclass(frozen=True)
class RefundFilters:
    start: str
    end: str
    status: str | None = None
    reason: str | None = None


def _where(merchant_id: str, f: RefundFilters) -> tuple[str, dict[str, object]]:
    clauses = ["r.merchant_id = :merchant_id", "r.created_at >= :start", "r.created_at < :end"]
    params: dict[str, object] = {"merchant_id": merchant_id, "start": f.start, "end": f.end}
    if f.status:
        clauses.append("r.status = :status")
        params["status"] = f.status
    if f.reason:
        clauses.append("r.reason = :reason")
        params["reason"] = f.reason
    return " AND ".join(clauses), params


def iter_refunds(merchant_id: str, conn: sqlite3.Connection, f: RefundFilters) -> sqlite3.Cursor:
    where, params = _where(merchant_id, f)
    return conn.execute(f"{SELECT} WHERE {where} ORDER BY r.created_at DESC, r.id", params)
