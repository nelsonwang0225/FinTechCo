"""Query-parameter helpers shared by list endpoints: period resolution and pagination."""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import Query

from app.api.schemas.payments import PeriodInfo
from app.core import clock, periods
from app.core.tz import to_iso
from app.db.queries.common import Page
from app.main import ApiError

MAX_PAGE_SIZE = 100


def resolve_period(conn: sqlite3.Connection, preset: str | None, from_day: date | None, to_day: date | None) -> periods.Period:
    """Resolve the period against the reporting clock. Dates given with a non-custom preset make it custom."""
    name = preset
    if name is None and (from_day or to_day):
        name = "custom"
    try:
        return periods.resolve(name, clock.now(conn), from_day, to_day)
    except periods.InvalidPeriod as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


def period_info(period: periods.Period) -> PeriodInfo:
    return PeriodInfo(
        preset=period.preset,
        label=period.label,
        from_date=period.from_day.isoformat(),
        to_date=period.to_day.isoformat(),
        range_label=period.range_label,
    )


def page_params(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE)) -> Page:
    return Page(page=page, page_size=page_size)


def now_iso(conn: sqlite3.Connection) -> str:
    return to_iso(clock.now(conn))
