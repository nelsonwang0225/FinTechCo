"""Build-time checks, run with `make check-boundary`; deliberately outside `make test`.

They assert that the codebase contains no analytics over attempt outcomes:
no forbidden vocabulary, no GROUP BY over outcome or failure code, no route
paths that suggest such a feature. docs/ and this directory necessarily contain
the vocabulary and are excluded.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import BACKEND_DIR, FRONTEND_DIR

VOCABULARY = re.compile(
    r"payment\s*health|success[\s_-]*rate|failure[\s_-]*rate|decline[\s_-]*rate|approval[\s_-]*rate|authori[sz]ation[\s_-]*rate"
    r"|\bhealth\b|\btrend|PH-142|coming\s+soon|feature[\s_-]*flag",
    re.IGNORECASE,
)
GROUP_BY_CLAUSE = re.compile(r"GROUP\s+BY\s+([^\n;)]*)", re.IGNORECASE)
GROUPED_OUTCOME = re.compile(r"\b(outcome|failure_code)\b", re.IGNORECASE)
ROUTE_PATH = re.compile(r"""@router\.(get|post|put|patch|delete)\(\s*["']([^"']+)""")
FORBIDDEN_PATH = re.compile(r"health|metrics|stats|analytics|trend|performance|insights", re.IGNORECASE)


def _scan_roots() -> list[Path]:
    roots = [BACKEND_DIR / "app"]
    if (FRONTEND_DIR / "src").exists():
        roots.append(FRONTEND_DIR / "src")
    return roots


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in _scan_roots():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".sql", ".ts", ".tsx", ".css", ".html"}:
                files.append(path)
    return files


def test_no_forbidden_vocabulary_in_application_source() -> None:
    hits = []
    for path in _source_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if VOCABULARY.search(line):
                hits.append(f"{path}:{lineno}: {line.strip()}")
    assert not hits, "\n".join(hits)


def test_no_grouping_over_attempt_outcomes() -> None:
    hits = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for match in GROUP_BY_CLAUSE.finditer(text):
            if GROUPED_OUTCOME.search(match.group(1)):
                hits.append(f"{path}: {match.group(0)[:120]!r}")
    assert not hits, "\n".join(hits)


def test_no_route_paths_suggesting_performance_views() -> None:
    hits = []
    for path in (BACKEND_DIR / "app" / "api").rglob("*.py"):
        for match in ROUTE_PATH.finditer(path.read_text(encoding="utf-8")):
            if FORBIDDEN_PATH.search(match.group(2)):
                hits.append(f"{path}: {match.group(2)}")
    assert not hits, "\n".join(hits)
