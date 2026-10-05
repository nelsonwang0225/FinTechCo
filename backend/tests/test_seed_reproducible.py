"""`make reset` reproduces the identical seeded dataset.

The logical checksum (every table ordered by primary key) is the definition
of "identical". GOLDEN_CHECKSUM changes only with an intentional scenario
change, which the commit message must say.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import config
from app.db.connection import connect
from app.seed import SeedResult, checksum, seed_database
from app.seed import scenario as S
from app.seed.__main__ import main as seed_cli

GOLDEN_CHECKSUM = "cc88bde3744deba225c58aa07fa955185e2afc868c5608fb7710e7a1ef84d464"


def test_seeding_twice_gives_the_same_checksum(template_seed: tuple[Path, SeedResult], tmp_path: Path) -> None:
    _, first = template_seed
    second = seed_database(tmp_path / "again.db")
    assert second.checksum == first.checksum
    assert second.row_counts == first.row_counts


def test_checksum_matches_the_golden_value(template_seed: tuple[Path, SeedResult]) -> None:
    _, result = template_seed
    assert result.checksum == GOLDEN_CHECKSUM


def test_stored_checksum_is_recomputable(template_db: Path) -> None:
    conn = connect(template_db)
    try:
        stored = conn.execute("SELECT value FROM seed_meta WHERE key = 'checksum'").fetchone()[0]
        assert checksum.compute(conn) == stored == GOLDEN_CHECKSUM
    finally:
        conn.close()


def test_seed_meta_carries_the_scenario_clock_and_no_wall_clock(template_db: Path) -> None:
    conn = connect(template_db)
    try:
        meta = dict(conn.execute("SELECT key, value FROM seed_meta"))
    finally:
        conn.close()
    assert meta["as_of"] == "2026-10-05T14:12:00Z"
    assert meta["window_start"] == "2026-09-05T05:00:00Z"
    assert meta["rng_seed"] == str(S.RNG_SEED)
    assert meta["reporting_timezone"] == "America/Chicago"
    assert set(meta) == {"as_of", "window_start", "window_end", "rng_seed", "reporting_timezone", "seed_version", "checksum"}


def test_seed_cli_refuses_to_seed_twice(template_db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("FINTECHCO_DB_PATH", str(template_db))
    assert config.db_path() == template_db
    assert seed_cli([]) == 0
    out = capsys.readouterr().out
    assert "already seeded" in out and GOLDEN_CHECKSUM in out
    conn = connect(template_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM seed_meta WHERE key = 'checksum'").fetchone()[0] == 1
    finally:
        conn.close()


def test_seed_cli_prints_counts_and_checksum_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("FINTECHCO_DB_PATH", str(tmp_path / "cli.db"))
    assert seed_cli([]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("Seeded ")
    assert lines[-1] == f"checksum {GOLDEN_CHECKSUM}"
    tables = {line.split()[0] for line in lines[1:-1]}
    assert tables == {"merchant", "location", "app_user", "membership", "customer", "payment", "payment_attempt", "refund", "dispute",
                      "payout", "balance_movement", "note_event", "seed_meta"}
