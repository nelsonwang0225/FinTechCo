"""Payout schedule rules shared by the API (next payout) and checked against the seed.

A cutoff is 00:00 America/Chicago on a merchant's payout day: every business day for a daily schedule,
Friday for weekly_friday, Monday for weekly_monday. A cutoff that falls on a non-business day moves to
the next business day. Labor Day 2026-09-07 is not a business day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.core.tz import chicago_day, chicago_local

HOLIDAYS: frozenset[date] = frozenset({date(2026, 9, 7)})

SCHEDULE_LABELS: dict[str, str] = {
    "daily": "Every business day",
    "weekly_friday": "Weekly on Fridays",
    "weekly_monday": "Weekly on Mondays",
}


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in HOLIDAYS


def roll_forward(day: date) -> date:
    while not is_business_day(day):
        day += timedelta(days=1)
    return day


def next_business_day(day: date) -> date:
    return roll_forward(day + timedelta(days=1))


def is_cutoff_day(schedule: str, day: date) -> bool:
    """Whether a cutoff lands on `day` once holiday rolling is applied."""
    if schedule == "daily":
        return is_business_day(day)
    anchor_weekday = 4 if schedule == "weekly_friday" else 0
    # The cutoff lands on `day` if `day` is the rolled-forward anchor of some week.
    cursor = day
    while True:
        if cursor.weekday() == anchor_weekday:
            return roll_forward(cursor) == day
        if is_business_day(cursor) and cursor != day:
            return False
        cursor -= timedelta(days=1)
        if (day - cursor).days > 7:
            return False


def cutoff_days(schedule: str, start: date, end: date) -> list[date]:
    """Every cutoff day in [start, end]."""
    return [d for d in (start + timedelta(days=n) for n in range((end - start).days + 1)) if is_cutoff_day(schedule, d)]


def next_cutoff(schedule: str, now: datetime) -> datetime:
    """The first cutoff instant strictly after `now`, as a UTC datetime."""
    day = chicago_day(now)
    while True:
        if is_cutoff_day(schedule, day):
            instant = chicago_local(day.year, day.month, day.day)
            if instant > now:
                return instant
        day += timedelta(days=1)
