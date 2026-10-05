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

from fastapi.responses import StreamingResponse

from app.core.money import format_usd
from app.core.tz import format_chicago


def usd(cents: int) -> str:
    return format_usd(cents)


def chicago(iso: str | None) -> str:
    return format_chicago(iso) if iso else ""


def export_filename(merchant_slug: str, report: str, from_day: date | str, to_day: date | str) -> str:
    return f"{merchant_slug}_{report}_{from_day}_{to_day}.csv"


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
