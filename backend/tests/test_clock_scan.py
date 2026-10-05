"""There is one clock. Wall-clock reads live only in app/core/clock.py and frontend/src/lib/format.ts."""

from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import BACKEND_DIR, FRONTEND_DIR

PY_FORBIDDEN = re.compile(r"datetime\.now\(|\.utcnow\(|time\.time\(|date\.today\(|datetime\.today\(")
TS_FORBIDDEN = re.compile(r"Date\.now\(|new Date\(\s*\)")


def _py_files() -> list[Path]:
    return [p for p in (BACKEND_DIR / "app").rglob("*.py")] + [p for p in (BACKEND_DIR / "tests").rglob("*.py")]


def _ts_files() -> list[Path]:
    src = FRONTEND_DIR / "src"
    if not src.exists():
        return []
    return [p for p in src.rglob("*") if p.suffix in {".ts", ".tsx"}]


def test_backend_reads_the_wall_clock_only_in_clock_py() -> None:
    offenders = []
    for path in _py_files():
        if path.name == "clock.py" and path.parent.name == "core":
            continue
        if path.name == "test_clock_scan.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PY_FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(BACKEND_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, "wall-clock reads outside app/core/clock.py:\n" + "\n".join(offenders)


def test_frontend_reads_the_browser_clock_only_in_format_ts() -> None:
    offenders = []
    for path in _ts_files():
        if path.name == "format.ts" and path.parent.name == "lib":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if TS_FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(FRONTEND_DIR)}:{lineno}: {line.strip()}")
    assert not offenders, "browser-clock reads outside src/lib/format.ts:\n" + "\n".join(offenders)
