from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.core import tz


def test_iso_round_trip_is_utc_with_z() -> None:
    dt = datetime(2026, 9, 14, 14, 32, 11, tzinfo=timezone.utc)
    assert tz.to_iso(dt) == "2026-09-14T14:32:11Z"
    assert tz.parse_iso("2026-09-14T14:32:11Z") == dt
    assert tz.parse_iso("2026-09-14T09:32:11-05:00") == dt


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError):
        tz.to_iso(datetime(2026, 1, 1))


def test_chicago_day_bounds_in_daylight_time() -> None:
    assert tz.chicago_day_bounds(date(2026, 9, 14)) == ("2026-09-14T05:00:00Z", "2026-09-15T05:00:00Z")


def test_chicago_day_bounds_across_dst_transitions() -> None:
    # 2026-03-08 is 23 hours long, 2026-11-01 is 25 hours long.
    assert tz.chicago_day_bounds(date(2026, 3, 8)) == ("2026-03-08T06:00:00Z", "2026-03-09T05:00:00Z")
    assert tz.chicago_day_bounds(date(2026, 11, 1)) == ("2026-11-01T05:00:00Z", "2026-11-02T06:00:00Z")


def test_late_evening_chicago_instant_is_previous_day_in_utc_terms() -> None:
    # 04:30Z on Sep 30 is 23:30 CT on Sep 29.
    assert tz.chicago_day("2026-09-30T04:30:00Z") == date(2026, 9, 29)


def test_chicago_range_is_inclusive() -> None:
    start, end = tz.chicago_range(date(2026, 9, 1), date(2026, 9, 30))
    assert start == "2026-09-01T05:00:00Z"
    assert end == "2026-10-01T05:00:00Z"
    with pytest.raises(ValueError):
        tz.chicago_range(date(2026, 9, 2), date(2026, 9, 1))


def test_chicago_local_builds_utc_instants() -> None:
    assert tz.to_iso(tz.chicago_local(2026, 10, 5, 9, 12)) == "2026-10-05T14:12:00Z"
    assert tz.to_iso(tz.chicago_local(2026, 12, 5, 9, 12)) == "2026-12-05T15:12:00Z"


def test_format_chicago_carries_the_offset() -> None:
    assert tz.format_chicago("2026-09-14T14:32:11Z") == "2026-09-14T09:32:11-05:00"
    assert tz.format_chicago("2026-12-14T14:32:11Z") == "2026-12-14T08:32:11-06:00"
