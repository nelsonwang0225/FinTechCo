"""The shared CSV writer: stdlib csv, UTF-8, a header row, no footer or totals row.

Money appears as `amount_cents` (integer) plus `amount_usd` (a string rendered with integer arithmetic).
UTC instants are passed through unchanged and rendered again in America/Chicago with offset in
`*_chicago` columns.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from datetime import date

import secrets
import sqlite3

from fastapi.responses import StreamingResponse

from app.auth.session import Principal
from app.core import clock, ids
from app.core.money import format_usd
from app.core.tz import format_chicago, to_iso
from app.db.queries import notes as notes_q


def usd(cents: int) -> str:
    return format_usd(cents)


def chicago(iso: str | None) -> str:
    return format_chicago(iso) if iso else ""


def export_filename(merchant_slug: str, report: str, from_day: date | str, to_day: date | str) -> str:
    return f"{merchant_slug}_{report}_{from_day}_{to_day}.csv"


def record_export(principal: Principal, conn: sqlite3.Connection, filename: str, body: str, *, payout_id: str | None = None) -> None:
    """Every CSV download is an activity record by the acting user, stamped with the wall clock."""
    notes_q.insert_export(
        principal.merchant_id,
        conn,
        event_id=ids.new_id("note_event", secrets.SystemRandom()),
        actor_user_id=principal.user_id,
        export_name=filename,
        body=body,
        created_at=to_iso(clock.wall_now()),
        payout_id=payout_id,
    )


def _encode(header: list[str], rows: Iterable[list[object]]) -> Iterator[bytes]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    yield buffer.getvalue().encode("utf-8")
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow(["" if v is None else v for v in row])
        yield buffer.getvalue().encode("utf-8")


def stream_csv(filename: str, header: list[str], rows: Iterable[list[object]]) -> StreamingResponse:
    return StreamingResponse(
        _encode(header, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
