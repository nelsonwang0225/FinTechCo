# FinTechCo Business — developer entry points.
# Every recipe line runs from the repository root in its own shell, so a failure on any line fails the target.
# Raw commands are documented in CLAUDE.md.

SHELL := /bin/bash

PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3)
VENV := backend/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
DB := backend/data/fintechco.db

.PHONY: setup seed reset run test lint test-backend test-frontend test-isolation

setup:
	@if [ -z "$(PYTHON)" ]; then echo "No python3 interpreter found. Install Python 3.11 or newer."; exit 1; fi
	@if ! "$(PYTHON)" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then \
	  echo "Python 3.11 or newer is required; $(PYTHON) is $$("$(PYTHON)" --version 2>&1)."; \
	  echo "Install python3.11+ (for example: brew install python@3.12) and re-run make setup."; exit 1; fi
	@echo "Using $(PYTHON) ($$("$(PYTHON)" --version 2>&1))"
	"$(PYTHON)" -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r backend/requirements.txt
	cd frontend && npm ci --no-audit --no-fund
	@echo "Setup complete. Next: make seed && make run"

seed:
	cd backend && .venv/bin/python -m app.seed

reset:
	rm -f $(DB) $(DB)-wal $(DB)-shm
	cd backend && .venv/bin/python -m app.seed

# Both servers are jobs of one shell; the trap kills both on Ctrl-C so a second `make run` starts cleanly.
run:
	@if [ ! -f "$(DB)" ]; then $(MAKE) --no-print-directory seed; fi
	@trap 'echo; echo "Stopping servers..."; kill $$(jobs -p) 2>/dev/null; wait 2>/dev/null; echo "Stopped."' INT TERM; \
	  (cd backend && exec .venv/bin/uvicorn app.main:app --reload --port 8000) & \
	  (cd frontend && exec npm run dev -- --port 5173 --strictPort) & \
	  echo "API on http://localhost:8000, app on http://localhost:5173 (Ctrl-C stops both)"; \
	  wait

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npx tsc --noEmit -p tsconfig.json
	cd frontend && npx vitest run

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npx eslint src

# Targeted runs for the edit-test loop. K is a pytest -k expression, F a vitest file filter; both default to everything.
test-backend:
	cd backend && .venv/bin/pytest -v $(if $(K),-k "$(K)")

test-frontend:
	cd frontend && npx vitest run $(F)

# Merchant isolation, route guards and session handling.
test-isolation:
	cd backend && .venv/bin/pytest -v tests/test_merchant_scoping.py tests/test_route_permissions.py tests/test_auth_sessions.py
