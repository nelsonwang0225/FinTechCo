"""Deterministic seed: scenario constants, generator, writer, verifier and checksum.

`seed_database(path)` is the one entry point; the CLI (`python -m app.seed`)
and the tests both call it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.db.connection import connect, init_schema


@dataclass(frozen=True)
class SeedResult:
    checksum: str
    row_counts: dict[str, int]


def seed_database(path: Path) -> SeedResult:
    """Create the schema at `path`, write the generated dataset, verify it and store the checksum."""
    from app.seed import checksum
    from app.seed.generate import build_dataset
    from app.seed.verify import verify
    from app.seed.write import write_dataset

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        init_schema(conn)
        write_dataset(conn, build_dataset())
        verify(conn)
        digest = checksum.compute(conn)
        conn.execute("INSERT INTO seed_meta (key, value) VALUES ('checksum', ?)", (digest,))
        conn.commit()
        return SeedResult(digest, checksum.row_counts(conn))
    finally:
        conn.close()
