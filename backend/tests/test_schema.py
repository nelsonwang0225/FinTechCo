"""The schema is the first line of defence: entities, money columns, merchant scoping, integrity rules."""

from __future__ import annotations

import sqlite3

import pytest

from app.db.connection import table_names

ENTITY_TABLES = {
    "merchant",
    "location",
    "app_user",
    "membership",
    "customer",
    "payment",
    "payment_attempt",
    "refund",
    "payout",
    "balance_movement",
    "dispute",
    "note_event",
}
UNSCOPED_TABLES = {"merchant", "app_user", "seed_meta"}


def columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    return {row["name"]: dict(row) for row in conn.execute(f"PRAGMA table_info({table})")}


def test_table_set_is_exactly_the_entities_plus_seed_meta(empty_db: sqlite3.Connection) -> None:
    assert set(table_names(empty_db)) == ENTITY_TABLES | {"seed_meta"}


def test_payment_summary_view_exists(empty_db: sqlite3.Connection) -> None:
    views = {r[0] for r in empty_db.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}
    assert views == {"payment_summary"}


def test_every_scoped_table_carries_merchant_id(empty_db: sqlite3.Connection) -> None:
    for table in ENTITY_TABLES - UNSCOPED_TABLES:
        cols = columns(empty_db, table)
        assert "merchant_id" in cols, table
        assert cols["merchant_id"]["notnull"] == 1, table


def test_money_columns_are_integers_with_usd_currency(empty_db: sqlite3.Connection) -> None:
    for table in table_names(empty_db):
        cols = columns(empty_db, table)
        money_cols = [c for c in cols if c.endswith("_cents")]
        if not money_cols:
            continue
        for c in money_cols:
            assert cols[c]["type"] == "INTEGER", (table, c)
        assert "currency" in cols, table
        with pytest.raises(sqlite3.IntegrityError):
            empty_db.execute(f"INSERT INTO {table} (currency) VALUES ('EUR')")


def test_timestamp_columns_are_text(empty_db: sqlite3.Connection) -> None:
    for table in table_names(empty_db):
        for name, col in columns(empty_db, table).items():
            if name.endswith("_at") or name.endswith("_date"):
                assert col["type"] == "TEXT", (table, name)


def test_child_tables_reference_parents_with_composite_merchant_keys(empty_db: sqlite3.Connection) -> None:
    for table in ("payment_attempt", "refund", "dispute", "balance_movement", "note_event", "payment"):
        fks = [dict(r) for r in empty_db.execute(f"PRAGMA foreign_key_list({table})")]
        composite = [fk for fk in fks if fk["from"] == "merchant_id" and fk["to"] == "merchant_id"]
        assert composite, f"{table} has no composite (parent_id, merchant_id) foreign key"


def test_foreign_keys_are_enforced(empty_db: sqlite3.Connection) -> None:
    assert empty_db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        empty_db.execute(
            "INSERT INTO location (id, merchant_id, name, address_line, city, state) VALUES ('loc_x', 'mer_missing', 'A', 'B', 'C', 'IL')"
        )


def _merchant(conn: sqlite3.Connection, mid: str = "mer_a") -> None:
    conn.execute(
        "INSERT INTO merchant (id, name, slug, legal_name, support_email, industry, payout_schedule, destination_label, destination_last4, destination_kind, created_at)"
        " VALUES (?, 'A', ?, 'A LLC', 'a@example.com', 'retail', 'daily', 'Operating account', '1111', 'external bank account', '2026-01-01T00:00:00Z')",
        (mid, mid),
    )


def _payment(conn: sqlite3.Connection, pid: str = "pay_a", mid: str = "mer_a", channel: str = "website", location: str | None = None) -> None:
    conn.execute(
        "INSERT INTO payment (id, merchant_id, customer_id, location_id, order_reference, description, amount_cents, currency, channel, created_at)"
        " VALUES (?, ?, NULL, ?, ?, 'Order', 1000, 'USD', ?, '2026-09-10T15:00:00Z')",
        (pid, mid, location, pid, channel),
    )


def test_in_store_payments_require_a_location_and_online_payments_forbid_one(empty_db: sqlite3.Connection) -> None:
    _merchant(empty_db)
    with pytest.raises(sqlite3.IntegrityError):
        _payment(empty_db, channel="in_store")
    empty_db.execute("INSERT INTO location (id, merchant_id, name, address_line, city, state) VALUES ('loc_a', 'mer_a', 'Store', '1 Main', 'Chicago', 'IL')")
    with pytest.raises(sqlite3.IntegrityError):
        _payment(empty_db, channel="website", location="loc_a")
    _payment(empty_db, channel="in_store", location="loc_a")


def test_at_most_one_succeeded_attempt_per_payment(empty_db: sqlite3.Connection) -> None:
    _merchant(empty_db)
    _payment(empty_db)
    insert = (
        "INSERT INTO payment_attempt (id, merchant_id, payment_id, attempt_number, method_type, card_brand, card_last4, wallet_type, outcome, failure_code, failure_message, created_at, completed_at)"
        " VALUES (?, 'mer_a', 'pay_a', ?, 'card', 'visa', '4242', NULL, 'succeeded', NULL, NULL, '2026-09-10T15:00:00Z', '2026-09-10T15:00:02Z')"
    )
    empty_db.execute(insert, ("att_1", 1))
    with pytest.raises(sqlite3.IntegrityError):
        empty_db.execute(insert, ("att_2", 2))


def test_failed_attempts_carry_a_reason_and_pending_attempts_have_no_completion(empty_db: sqlite3.Connection) -> None:
    _merchant(empty_db)
    _payment(empty_db)
    base = (
        "INSERT INTO payment_attempt (id, merchant_id, payment_id, attempt_number, method_type, card_brand, card_last4, wallet_type, outcome, failure_code, failure_message, created_at, completed_at) VALUES "
    )
    with pytest.raises(sqlite3.IntegrityError):
        empty_db.execute(base + "('att_1', 'mer_a', 'pay_a', 1, 'card', 'visa', '4242', NULL, 'failed', NULL, NULL, '2026-09-10T15:00:00Z', '2026-09-10T15:00:02Z')")
    with pytest.raises(sqlite3.IntegrityError):
        empty_db.execute(base + "('att_1', 'mer_a', 'pay_a', 1, 'card', 'visa', '4242', NULL, 'pending', NULL, NULL, '2026-09-10T15:00:00Z', '2026-09-10T15:00:02Z')")
    empty_db.execute(base + "('att_1', 'mer_a', 'pay_a', 1, 'card', 'visa', '4242', NULL, 'failed', 'do_not_honor', 'Do not honor', '2026-09-10T15:00:00Z', '2026-09-10T15:00:02Z')")


def test_a_child_cannot_point_at_another_merchants_payment(empty_db: sqlite3.Connection) -> None:
    _merchant(empty_db, "mer_a")
    _merchant(empty_db, "mer_b")
    _payment(empty_db, "pay_a", "mer_a")
    with pytest.raises(sqlite3.IntegrityError):
        empty_db.execute(
            "INSERT INTO refund (id, merchant_id, payment_id, amount_cents, currency, reason, status, created_at, completed_at)"
            " VALUES ('ref_x', 'mer_b', 'pay_a', 100, 'USD', 'duplicate', 'succeeded', '2026-09-11T00:00:00Z', '2026-09-11T00:00:00Z')"
        )


def test_movement_types_carry_exactly_their_source_references_and_signs(empty_db: sqlite3.Connection) -> None:
    _merchant(empty_db)
    _payment(empty_db)
    empty_db.execute(
        "INSERT INTO payment_attempt (id, merchant_id, payment_id, attempt_number, method_type, card_brand, card_last4, wallet_type, outcome, failure_code, failure_message, created_at, completed_at)"
        " VALUES ('att_1', 'mer_a', 'pay_a', 1, 'card', 'visa', '4242', NULL, 'succeeded', NULL, NULL, '2026-09-10T15:00:00Z', '2026-09-10T15:00:02Z')"
    )
    insert = (
        "INSERT INTO balance_movement (id, merchant_id, type, amount_cents, currency, description, posted_at, available_at, payout_id, payment_id, attempt_id, refund_id, dispute_id)"
        " VALUES (?, 'mer_a', ?, ?, 'USD', 'd', '2026-09-10T15:00:02Z', '2026-09-12T15:00:02Z', NULL, ?, ?, NULL, NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):  # charge must be positive
        empty_db.execute(insert, ("bm_1", "charge", -1000, "pay_a", "att_1"))
    with pytest.raises(sqlite3.IntegrityError):  # fee must be negative
        empty_db.execute(insert, ("bm_1", "fee", 59, "pay_a", "att_1"))
    with pytest.raises(sqlite3.IntegrityError):  # charge needs an attempt
        empty_db.execute(insert, ("bm_1", "charge", 1000, "pay_a", None))
    with pytest.raises(sqlite3.IntegrityError):  # adjustment carries no references
        empty_db.execute(insert, ("bm_1", "adjustment", 500, "pay_a", "att_1"))
    empty_db.execute(insert, ("bm_1", "charge", 1000, "pay_a", "att_1"))
    empty_db.execute(insert, ("bm_2", "fee", -59, "pay_a", "att_1"))
