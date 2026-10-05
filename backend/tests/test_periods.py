from __future__ import annotations

from datetime import date

import pytest

from app.core import periods
from app.core.tz import chicago_local

NOW = chicago_local(2026, 10, 5, 9, 12)


def test_default_preset_is_last_7_days() -> None:
    p = periods.resolve(None, NOW)
    assert p.preset == "last_7_days"
    assert (p.from_day, p.to_day) == (date(2026, 9, 29), date(2026, 10, 5))
    assert p.start == "2026-09-29T05:00:00Z"
    assert p.end == "2026-10-06T05:00:00Z"


def test_last_30_days_ends_today() -> None:
    p = periods.resolve("last_30_days", NOW)
    assert (p.from_day, p.to_day) == (date(2026, 9, 6), date(2026, 10, 5))
    assert len(periods.day_buckets(p)) == 30


def test_month_to_date_starts_on_the_first() -> None:
    p = periods.resolve("month_to_date", NOW)
    assert (p.from_day, p.to_day) == (date(2026, 10, 1), date(2026, 10, 5))
    assert p.range_label == "Oct 1 – Oct 5, 2026"


def test_custom_requires_both_dates_in_order() -> None:
    p = periods.resolve("custom", NOW, date(2026, 9, 1), date(2026, 9, 30))
    assert (p.start, p.end) == ("2026-09-01T05:00:00Z", "2026-10-01T05:00:00Z")
    with pytest.raises(periods.InvalidPeriod):
        periods.resolve("custom", NOW)
    with pytest.raises(periods.InvalidPeriod):
        periods.resolve("custom", NOW, date(2026, 9, 2), date(2026, 9, 1))


def test_unknown_preset_is_rejected() -> None:
    with pytest.raises(periods.InvalidPeriod):
        periods.resolve("yesterday", NOW)


def test_labels_are_shared_vocabulary() -> None:
    assert periods.PRESET_LABELS["last_7_days"] == "Last 7 days"
    assert set(periods.PRESET_LABELS) == set(periods.PRESETS)
