"""Definition of Done 9: `make test` is the one command that runs everything, and each step fails the target on its own.

The suite cannot invoke itself, so this checks the Makefile wiring: the test target runs the backend suite, the
frontend typecheck and the frontend tests as separate recipe lines (so any failing line fails the target), and the
boundary checks are kept out of it on purpose. The actual run is recorded in docs/ACCEPTANCE.md.
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
    lines = recipe("test")
    assert lines == [
        "cd backend && .venv/bin/pytest -q",
        "cd frontend && npx tsc --noEmit -p tsconfig.json",
        "cd frontend && npx vitest run",
    ]
    assert not any("tests/boundary" in line for line in lines)


def test_pytest_collects_the_definition_of_done_suite_but_not_the_boundary_checks() -> None:
    pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text()
    assert "tests/boundary" in pyproject  # excluded from the default run
    dod = sorted(p.name for p in (REPO_ROOT / "backend" / "tests").glob("test_dod_*.py"))
    assert len(dod) >= 9 and dod[0].startswith("test_dod_01")


def test_check_boundary_and_acceptance_targets_exist() -> None:
    assert recipe("check-boundary") == ["cd backend && .venv/bin/pytest -q tests/boundary"]
    assert recipe("acceptance") == ["cd backend && .venv/bin/pytest -v tests/test_dod_*.py"]
