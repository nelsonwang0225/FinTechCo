"""The runtime payout schedule agrees with the seeded payouts and rolls over holidays."""

from __future__ import annotations

import sqlite3
from datetime import date

from app.core import schedule
from app.core.tz import chicago_local, chicago_day


def test_business_days_and_rolling() -> None:
    assert schedule.is_business_day(date(2026, 9, 4))  # Friday
    assert not schedule.is_business_day(date(2026, 9, 5))  # Saturday
    assert not schedule.is_business_day(date(2026, 9, 7))  # Labor Day
    assert schedule.next_business_day(date(2026, 9, 4)) == date(2026, 9, 8)
    assert schedule.roll_forward(date(2026, 9, 7)) == date(2026, 9, 8)


def test_cutoff_days_per_schedule() -> None:
    assert schedule.cutoff_days("daily", date(2026, 9, 4), date(2026, 9, 9)) == [date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9)]
    assert schedule.cutoff_days("weekly_friday", date(2026, 9, 1), date(2026, 9, 30)) == [date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18), date(2026, 9, 25)]
    # Monday 2026-09-07 is Labor Day, so that week's Monday cutoff lands on Tuesday the 8th.
    assert schedule.cutoff_days("weekly_monday", date(2026, 9, 1), date(2026, 9, 30)) == [date(2026, 9, 8), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28)]


def test_next_cutoff_after_the_clock() -> None:
    now = chicago_local(2026, 10, 5, 9, 12)  # Monday morning
    assert schedule.next_cutoff("daily", now) == chicago_local(2026, 10, 6)
    assert schedule.next_cutoff("weekly_friday", now) == chicago_local(2026, 10, 9)
    assert schedule.next_cutoff("weekly_monday", now) == chicago_local(2026, 10, 12)
    # Exactly at a cutoff instant the next one is strictly later.
    assert schedule.next_cutoff("daily", chicago_local(2026, 10, 5)) == chicago_local(2026, 10, 6)
    # Before Labor Day weekend the next daily cutoff skips Saturday, Sunday and the holiday.
    assert schedule.next_cutoff("daily", chicago_local(2026, 9, 4, 12)) == chicago_local(2026, 9, 8)
    assert schedule.next_cutoff("weekly_monday", chicago_local(2026, 9, 4, 12)) == chicago_local(2026, 9, 8)


def test_runtime_schedule_reproduces_the_seeded_cutoffs(seeded_conn: sqlite3.Connection) -> None:
    for merchant_id, payout_schedule in seeded_conn.execute("SELECT id, payout_schedule FROM merchant"):
        seeded = [chicago_day(row[0]) for row in seeded_conn.execute("SELECT cutoff_at FROM payout WHERE merchant_id = ? ORDER BY cutoff_at", (merchant_id,))]
        expected = schedule.cutoff_days(payout_schedule, date(2026, 9, 5), date(2026, 10, 5))
        # The first cutoff of the window has nothing to sweep for a weekly merchant, so it may be absent; the rest agree.
        assert seeded == [d for d in expected if d >= seeded[0]], payout_schedule
