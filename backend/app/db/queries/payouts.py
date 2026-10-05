"""Payouts: list, detail, itemised movements, reconciliation and the funds summary.

A payout's stored amount is the one stored derived number in the system; `ledger_total` is what it
must equal, and the API refuses to paper over a mismatch.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.queries.common import Page

BUCKET_TYPES: dict[str, tuple[str, ...]] = {
    "collections": ("charge",),
    "fees": ("fee",),
    "refunds": ("refund",),
    "disputes": ("dispute_reversal", "dispute_fee", "dispute_reinstatement"),
    "adjustments": ("adjustment",),
}


@dataclass(frozen=True)
class PayoutFilters:
    status: str | None = None
    start: str | None = None  # inclusive UTC ISO on cutoff_at
    end: str | None = None  # exclusive UTC ISO on cutoff_at


def _where(merchant_id: str, f: PayoutFilters) -> tuple[str, dict[str, object]]:
    clauses = ["po.merchant_id = :merchant_id"]
    params: dict[str, object] = {"merchant_id": merchant_id}
    if f.status:
        clauses.append("po.status = :status")
        params["status"] = f.status
    if f.start:
        clauses.append("po.cutoff_at >= :start")
        params["start"] = f.start
    if f.end:
        clauses.append("po.cutoff_at < :end")
        params["end"] = f.end
    return " AND ".join(clauses), params


ORDER = "ORDER BY CASE po.status WHEN 'in_transit' THEN 0 ELSE 1 END, po.cutoff_at DESC, po.id"


def list_payouts(merchant_id: str, conn: sqlite3.Connection, f: PayoutFilters, page: Page) -> tuple[list[sqlite3.Row], int]:
    where, params = _where(merchant_id, f)
    total = conn.execute(f"SELECT COUNT(*) FROM payout po WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT po.* FROM payout po WHERE {where} {ORDER} LIMIT :limit OFFSET :offset",
        {**params, "limit": page.page_size, "offset": page.offset},
    ).fetchall()
    return rows, total


def iter_payouts(merchant_id: str, conn: sqlite3.Connection, f: PayoutFilters) -> sqlite3.Cursor:
    where, params = _where(merchant_id, f)
    return conn.execute(f"SELECT po.* FROM payout po WHERE {where} {ORDER}", params)


def get_payout(merchant_id: str, conn: sqlite3.Connection, payout_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT po.* FROM payout po WHERE po.id = :id AND po.merchant_id = :merchant_id", {"id": payout_id, "merchant_id": merchant_id}).fetchone()


def list_movements_for_payout(merchant_id: str, conn: sqlite3.Connection, payout_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT bm.id, bm.type, bm.amount_cents, bm.currency, bm.description, bm.posted_at, bm.available_at, bm.payout_id, "
        "bm.payment_id, bm.attempt_id, bm.refund_id, bm.dispute_id, p.order_reference, c.full_name AS customer_name "
        "FROM balance_movement bm "
        "LEFT JOIN payment p ON p.id = bm.payment_id AND p.merchant_id = bm.merchant_id "
        "LEFT JOIN customer c ON c.id = p.customer_id AND c.merchant_id = p.merchant_id "
        "WHERE bm.payout_id = :payout_id AND bm.merchant_id = :merchant_id ORDER BY bm.posted_at, bm.id",
        {"payout_id": payout_id, "merchant_id": merchant_id},
    ).fetchall()


def ledger_total(merchant_id: str, conn: sqlite3.Connection, payout_id: str) -> tuple[int, int]:
    """(sum of movement amounts, movement count) for a payout."""
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0), COUNT(*) FROM balance_movement WHERE payout_id = :payout_id AND merchant_id = :merchant_id",
        {"payout_id": payout_id, "merchant_id": merchant_id},
    ).fetchone()
    return int(row[0]), int(row[1])


def bucket_totals(merchant_id: str, conn: sqlite3.Connection, payout_id: str) -> dict[str, int]:
    """Signed cents per bucket, computed from the same movement rows the detail lists."""
    by_type = {
        row[0]: int(row[1])
        for row in conn.execute(
            "SELECT type, SUM(amount_cents) FROM balance_movement WHERE payout_id = :payout_id AND merchant_id = :merchant_id GROUP BY type",
            {"payout_id": payout_id, "merchant_id": merchant_id},
        )
    }
    return {bucket: sum(by_type.get(t, 0) for t in types) for bucket, types in BUCKET_TYPES.items()}


def funds_summary(merchant_id: str, conn: sqlite3.Connection, now_iso: str) -> tuple[int, int]:
    """(available, pending): unswept movements split on whether they are available at `now`."""
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN available_at <= :now THEN amount_cents ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN available_at > :now THEN amount_cents ELSE 0 END), 0) "
        "FROM balance_movement WHERE merchant_id = :merchant_id AND payout_id IS NULL",
        {"merchant_id": merchant_id, "now": now_iso},
    ).fetchone()
    return int(row[0]), int(row[1])


def merchant_payout_profile(merchant_id: str, conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT slug, payout_schedule, destination_label, destination_last4, destination_kind FROM merchant WHERE id = :merchant_id",
        {"merchant_id": merchant_id},
    ).fetchone()
    assert row is not None
    return row
