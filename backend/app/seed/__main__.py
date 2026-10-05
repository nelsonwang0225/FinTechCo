"""`python -m app.seed`: create and populate the database if it does not exist.

Prints row counts per table and the checksum. Refuses to double-seed; use
`make reset` to rebuild.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.core import config
from app.db.connection import connect, database_exists, table_names
from app.seed import seed_database


def main(argv: list[str]) -> int:
    path: Path = config.db_path()
    if database_exists(path):
        conn = connect(path)
        try:
            if "seed_meta" in table_names(conn):
                row = conn.execute("SELECT value FROM seed_meta WHERE key = 'checksum'").fetchone()
                print(f"Database already seeded at {path} (checksum {row[0] if row else 'unknown'}). Use `make reset` to rebuild.")
                return 0
        finally:
            conn.close()
        print(f"{path} exists but is not a seeded database. Remove it or run `make reset`.", file=sys.stderr)
        return 1

    result = seed_database(path)
    width = max(len(name) for name in result.row_counts)
    print(f"Seeded {path}")
    for name, count in result.row_counts.items():
        print(f"  {name:<{width}}  {count:>7,}")
    print(f"checksum {result.checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
