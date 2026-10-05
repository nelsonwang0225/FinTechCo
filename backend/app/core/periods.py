"""The one place period presets are resolved.

Presets are inclusive America/Chicago date ranges ending on the clock's date.
The Overview, the Payments and Attempts tabs and the exports all accept the
same preset names and show the same labels. The frontend sends preset names
(or ``custom`` with two dates the user typed) and never computes dates itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.tz import chicago_day, chicago_range

PRESETS: tuple[str, ...] = ("last_7_days", "last_30_days", "month_to_date", "custom")
DEFAULT_PRESET = "last_7_days"

PRESET_LABELS: dict[str, str] = {
    "last_7_days": "Last 7 days",
    "last_30_days": "Last 30 days",
    "month_to_date": "Month to date",
    "custom": "Custom range",
}


class InvalidPeriod(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    preset: str
    from_day: date
    to_day: date
    start: str  # inclusive UTC ISO
    end: str  # exclusive UTC ISO

    @property
    def label(self) -> str:
        return PRESET_LABELS[self.preset]

    @property
    def range_label(self) -> str:
        """Human label such as 'Sep 29 – Oct 5, 2026'."""
        if self.from_day == self.to_day:
            return _fmt(self.from_day, with_year=True)
        same_year = self.from_day.year == self.to_day.year
        left = _fmt(self.from_day, with_year=not same_year)
        right = _fmt(self.to_day, with_year=True)
        return f"{left} – {right}"


def _fmt(d: date, *, with_year: bool) -> str:
    month = d.strftime("%b")
    return f"{month} {d.day}, {d.year}" if with_year else f"{month} {d.day}"


def resolve(
    preset: str | None,
    now: datetime,
    from_day: date | None = None,
    to_day: date | None = None,
) -> Period:
    """Resolve a preset (or custom dates) against the reporting clock."""
    name = preset or DEFAULT_PRESET
    if name not in PRESETS:
        raise InvalidPeriod(f"unknown period preset {name!r}")
    today = chicago_day(now)
    if name == "last_7_days":
        from_day, to_day = today - timedelta(days=6), today
    elif name == "last_30_days":
        from_day, to_day = today - timedelta(days=29), today
    elif name == "month_to_date":
        from_day, to_day = today.replace(day=1), today
    else:
        if from_day is None or to_day is None:
            raise InvalidPeriod("custom period requires from and to dates")
        if to_day < from_day:
            raise InvalidPeriod("period end precedes period start")
        if (to_day - from_day).days > 366:
            raise InvalidPeriod("period longer than a year")
    start, end = chicago_range(from_day, to_day)
    return Period(preset=name, from_day=from_day, to_day=to_day, start=start, end=end)


def day_buckets(period: Period) -> list[date]:
    """Every Chicago calendar day in the period, in order."""
    days = []
    cursor = period.from_day
    while cursor <= period.to_day:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days
