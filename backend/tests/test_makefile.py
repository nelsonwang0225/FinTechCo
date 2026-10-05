"""The Makefile is the documented entry point.

The suite cannot invoke itself, so this checks the wiring: `make test` runs the backend suite, the frontend typecheck
and the frontend tests as separate recipe lines, so any failing line fails the target.
"""

from __future__ import annotations

import re

from tests.conftest import REPO_ROOT


def recipe(target: str) -> list[str]:
    makefile = (REPO_ROOT / "Makefile").read_text()
    match = re.search(rf"^{target}:[^\n]*\n((?:\t[^\n]*\n)+)", makefile, re.M)
    assert match, f"no recipe for {target}"
    return [line.strip() for line in match.group(1).splitlines()]


def test_make_test_runs_backend_typecheck_and_frontend_tests_as_separate_lines() -> None:
    assert recipe("test") == [
        "cd backend && .venv/bin/pytest -q",
        "cd frontend && npx tsc --noEmit -p tsconfig.json",
        "cd frontend && npx vitest run",
    ]


def test_pytest_runs_from_the_backend_directory_over_tests_only() -> None:
    pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text()
    assert 'testpaths = ["tests"]' in pyproject
    assert ".venv" in pyproject and "data" in pyproject
