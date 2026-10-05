# FinTechCo Business

A merchant payments portal. A business signs in and sees what it has collected, every payment and the attempts made to pay for it, refunds, disputes, payouts to its bank account, CSV reports and its team, always scoped to its own records.

Everything in this repository is fictional and synthetic: the businesses, the people, the cards, the bank accounts and every transaction. The portal says so on screen.

## Quick start

Requirements: Python 3.11 or newer, Node 22 and npm 10.

```
make setup   # venv, pinned Python dependencies, npm ci
make seed    # create and populate backend/data/fintechco.db
make run     # API on http://localhost:8000, app on http://localhost:5173 (Ctrl-C stops both)
```

Open http://localhost:5173 and pick a persona. The development persona bar lets you switch between the seeded businesses and roles:

| Business | Persona | Role |
|---|---|---|
| Alder & Loom | Maya Chen | Operations manager |
| Alder & Loom | Daniel Brooks | Finance manager |
| Alder & Loom | Jordan Ellis | Business admin |
| Alder & Loom | Sam Okafor | Read-only analyst |
| Juniper Trail Outfitters | Priya Shah | Operations manager |
| Copper Finch Coffee | Sam Okafor | Read-only analyst |

Other commands: `make test` runs the backend tests, the frontend typecheck and the frontend tests; `make reset` deletes the database and reseeds it (the seed is deterministic and prints its checksum).

## Where things are

- `backend/` — FastAPI service over SQLite with hand-written SQL. Routers in `app/api/`, SQL in `app/db/queries/`, the seed in `app/seed/`, tests in `tests/`.
- `frontend/` — React + Vite + TypeScript app with plain CSS. Pages in `src/pages/`, shared components in `src/components/`.
- `CLAUDE.md` — the engineering guide: layout, conventions, auth and scoping, the clock, the seed, and how to add a feature.
- `docs/DATA_MODEL.md` — tables, derivation rules and the ledger.
