"""The only America/Chicago conversion code on the backend.

Storage and the API wire format are UTC ISO 8601 with second precision and a
trailing ``Z``. Humans see and choose times in America/Chicago, so filters,
chart buckets and CSV cells are converted here and nowhere else.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

REPORTING_TIMEZONE = "America/Chicago"
CHICAGO = ZoneInfo(REPORTING_TIMEZONE)
UTC = timezone.utc

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def to_iso(dt: datetime) -> str:
    """Render an aware datetime as the canonical UTC string."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime; storage requires aware UTC datetimes")
    return dt.astimezone(UTC).replace(microsecond=0).strftime(ISO_FORMAT)


def parse_iso(value: str) -> datetime:
    """Parse the canonical UTC string (or any ISO 8601 with an offset) into an aware datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp without offset: {value!r}")
    return dt.astimezone(UTC)


def chicago_local(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    """Build a UTC instant from America/Chicago wall-clock components (DST aware)."""
    local = datetime(year, month, day, hour, minute, second, tzinfo=CHICAGO)
    return local.astimezone(UTC)


def to_chicago(value: str | datetime) -> datetime:
    dt = parse_iso(value) if isinstance(value, str) else value
    return dt.astimezone(CHICAGO)


def chicago_day(value: str | datetime) -> date:
    """The America/Chicago calendar date an instant falls on."""
    return to_chicago(value).date()


def chicago_day_bounds(day: date) -> tuple[str, str]:
    """[start, end) UTC strings covering one Chicago calendar day."""
    start = datetime(day.year, day.month, day.day, tzinfo=CHICAGO)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=CHICAGO)
    return to_iso(start.astimezone(UTC)), to_iso(end.astimezone(UTC))


def chicago_range(from_day: date, to_day: date) -> tuple[str, str]:
    """[start, end) UTC strings covering the inclusive Chicago date range."""
    if to_day < from_day:
        raise ValueError("to_day precedes from_day")
    start, _ = chicago_day_bounds(from_day)
    _, end = chicago_day_bounds(to_day)
    return start, end


def format_chicago(value: str | datetime) -> str:
    """ISO 8601 in America/Chicago with its UTC offset, for CSV cells."""
    return to_chicago(value).replace(microsecond=0).isoformat()


def chicago_date_string(value: str | datetime) -> str:
    return chicago_day(value).isoformat()
