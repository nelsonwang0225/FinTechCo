"""One clock.

``now(conn)`` is the reporting clock: the ``as_of`` instant the seed wrote
into ``seed_meta``. Everything a merchant sees as "now" (as-of labels, funds
available, next payout, deadlines, period presets, the greeting) derives from
it, so the data reads the same on any calendar day.

``wall_now()`` is the real clock, used only for writes (notes, exports) and
session expiry. These two functions are the only wall-clock reads in the
backend; a test enforces that.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.core.tz import parse_iso


class ClockUnavailable(RuntimeError):
    """The database has no as_of value, i.e. it has not been seeded."""


def now(conn: sqlite3.Connection) -> datetime:
    row = conn.execute("SELECT value FROM seed_meta WHERE key = 'as_of'").fetchone()
    if row is None:
        raise ClockUnavailable("seed_meta has no as_of; run make seed")
    return parse_iso(row[0])


def wall_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
