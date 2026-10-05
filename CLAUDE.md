# CLAUDE.md — FinTechCo Business

FinTechCo Business is a merchant payments portal. A business signs in and sees what it has collected, every payment and the attempts made to pay for it, refunds, disputes, payouts to its bank account, CSV reports and its team, always scoped to its own records. Everything in this repository is fictional and synthetic: invented businesses and people, `example.com` emails, masked card and bank details.

This file is the engineering guide: how the code is laid out, the conventions it follows, and how to add to it. `docs/DATA_MODEL.md` explains the tables and derivation rules; `backend/app/db/schema.sql` is the authoritative DDL.

## Stack and layout

- Backend: Python 3.11+, FastAPI, stdlib `sqlite3` with hand-written SQL (no ORM), pytest. Single service in `backend/`.
- Frontend: Node 22 / npm 10, React + Vite + TypeScript (strict), `react-router-dom`, plain CSS with design tokens, hand-written SVG chart, Vitest. Single app in `frontend/`.
- Database: SQLite file at `backend/data/fintechco.db` (gitignored; created by the seed).
- Dev wiring: Vite (`:5173`) proxies `/api` to uvicorn (`:8000`), so the app is same-origin and the session cookie just works.

```
Makefile                      setup | seed | reset | run | test
README.md                     quick start
CLAUDE.md                     this file
docs/DATA_MODEL.md            tables, derivation rules, ledger identity
backend/
  requirements.txt            pinned: fastapi, uvicorn, httpx, pytest, tzdata
  pyproject.toml              pytest configuration only
  data/                       fintechco.db lives here (gitignored, .gitkeep committed)
  app/
    main.py                   create_app(db_path=None), app = create_app(), GET /api/ping, error handlers
    core/config.py            env: FINTECHCO_DB_PATH, FINTECHCO_ENV, FINTECHCO_SESSION_SECRET
    core/clock.py             now(conn) = the reporting clock from seed_meta, wall_now() = real UTC
    core/tz.py                the only America/Chicago conversion code on the backend
    core/periods.py           period presets (last_7_days, last_30_days, month_to_date, custom) and day buckets
    core/money.py             integer-cent helpers, fee formula, cents -> "1,234.56" string
    core/ids.py               prefixed id generation
    core/labels.py            human labels for every enum value
    core/schedule.py          payout schedules and the next cutoff
    core/timeline.py          payment timeline and dispute history, derived from base records
    db/schema.sql             DDL: tables, CHECKs, composite FKs, indexes, payment_summary view
    db/connection.py          per-request connection, WAL, foreign_keys=ON, sqlite3.Row
    db/queries/               one module per resource; every function takes merchant_id first
    auth/session.py           signed cookie, current_principal()
    auth/permissions.py       role matrix, require(permission)
    api/__init__.py           register_routers(): the list of router modules
    api/listing.py            shared period, pagination and "now" helpers for list endpoints
    api/schemas/              Pydantic response models (ApiModel forbids undeclared fields)
    api/                      routers: dev, session, meta, overview, payments, attempts, payouts,
                              customers, disputes, reports, settings
    exports/csv.py            shared CSV writer and export activity record
    seed/                     scenario.py, generate.py, write.py, verify.py, checksum.py, __main__.py
  tests/                      pytest: one module per resource plus cross-cutting suites
                              (test_route_permissions, test_merchant_scoping, test_clock_scan,
                              test_seed_invariants, test_seed_reproducible, test_persistence, test_makefile)
frontend/
  package.json, package-lock.json (committed), vite.config.ts (/api proxy), tsconfig.json
  src/
    api/client.ts             fetch wrapper: credentials included, 401 -> persona chooser, 403/404 -> states
    api/useApi.ts             useApi<T>(path | null): data, error, loading, reload
    api/*-types.ts            TypeScript mirrors of the backend response models
    session/                  SessionProvider, useSession(), can(permission), RequirePermission
    dev/                      PersonaBar, PersonaChooser (development only, outside product chrome)
    layout/                   AppShell, SideNav, TopBar, PageHeader, DemoIndicator
    components/               DataTable, Pagination, FilterBar, ActiveFilters, Tabs, StatusBadge, Money,
                              Timestamp, DescriptionList, BarChart, Timeline, NoteComposer, states
    pages/                    overview, payments, payment-detail, payouts, payout-detail, customers,
                              customer-detail, disputes, dispute-detail, reports, settings
    lib/format.ts             the only place money and timestamps are formatted
    lib/query.ts              URL query-string state for filters, sort, page, tab
    lib/scopedQuery.ts        prefixed query-string state for several filter sets on one page
    styles/tokens.css, base.css, pages.css
    test/                     mockApi, fixtures, render helpers for page tests
```

## Commands

Use the Makefile. Raw commands are listed so nothing is hidden. First run: `make setup && make seed && make run`.

| Target | What it does | Raw commands |
|---|---|---|
| `make setup` | Create the venv (python3.13, 3.12 or 3.11, whichever is found), install pinned Python deps, `npm ci` | `python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt && cd frontend && npm ci` |
| `make seed` | Create and populate the DB if it does not exist; no-op with a message if it does; prints the checksum | `cd backend && .venv/bin/python -m app.seed` |
| `make reset` | Delete `fintechco.db` (and `-wal`/`-shm`), reseed, print the checksum. Stop `make run` first. | `rm -f backend/data/fintechco.db*; cd backend && .venv/bin/python -m app.seed` |
| `make run` | Seed if the DB is missing, then start API (`:8000`) and Vite (`:5173`) as jobs of one shell; Ctrl-C stops both | `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000` and `cd frontend && npm run dev -- --port 5173` |
| `make test` | Backend tests, frontend typecheck, frontend tests (separate recipe lines, so any failure fails the target) | `cd backend && .venv/bin/pytest -q` then `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run` |

Single test: `cd backend && .venv/bin/pytest tests/test_payout_reconciliation.py -q`. One frontend test: `cd frontend && npx vitest run src/pages/payments`.
Open `http://localhost:5173`; with no session the development persona chooser appears; pick a persona to reach the portal.

Environment variables (all optional in development):
- `FINTECHCO_DB_PATH` — default `backend/data/fintechco.db`, resolved from the package location, not the cwd.
- `FINTECHCO_ENV` — `development` (default) or `production`; production removes the `/api/dev/*` router entirely.
- `FINTECHCO_SESSION_SECRET` — HMAC key for the session cookie; a fixed development default is built in.

There is no clock variable: the reporting clock is written into `seed_meta` by the seed and read from there (see "Clock and reporting timezone").

## Conventions

- IDs are TEXT with a type prefix and 14 lowercase base-32 characters: `mer_`, `loc_`, `usr_`, `mem_`, `cus_`, `pay_`, `att_`, `ref_`, `po_`, `bm_`, `dp_`, `evt_`. Seeded IDs come from the seeded RNG, so they are stable across resets and may be used in docs and tests. Runtime writes (notes, export records) use `secrets`.
- Timestamps: `*_at` columns are TEXT ISO 8601 UTC, second precision, trailing `Z` (lexicographically sortable). `*_date` columns are America/Chicago calendar dates `YYYY-MM-DD`. Never SQLite datetime arithmetic for local days.
- Money: `amount_cents INTEGER NOT NULL` plus `currency TEXT NOT NULL CHECK (currency = 'USD')` on every money-bearing table. Signed cents on balance movements. Pydantic fields are `int`. Fee math is integer half-up. Dollar strings are parsed and rendered with `divmod(abs(cents), 100)` and an explicit sign; never `float`.
- Enums are lowercase snake_case: channel `website|mobile_app|in_store`; method `card|wallet` (brand + last4 only, wallet type for wallets); attempt outcome `succeeded|failed|pending`; payment status `pending|succeeded|failed|partially_refunded|refunded` (derived, see below); refund status `pending|succeeded` with reason `requested_by_customer|damaged_in_transit|wrong_item|duplicate|price_adjustment|returned_in_store`; payout status `in_transit|paid`; movement type `charge|fee|refund|dispute_reversal|dispute_fee|dispute_reinstatement|adjustment`; dispute status `needs_response|under_review|won|lost` with reason `fraudulent|product_not_received|product_unacceptable|duplicate|credit_not_processed`; roles `business_admin|operations_manager|finance_manager|read_only_analyst`. Attempt failure codes are a fixed table in the seed (`insufficient_funds`, `do_not_honor`, `incorrect_cvc`, `expired_card`, `authentication_failed`, `card_velocity_exceeded`, `fraud_suspected`, `issuer_unavailable`, `processing_error`, `lost_or_stolen`, `incorrect_number`), each with a human label in `core/labels.py`.
- API: list responses are `{items, page, page_size, total}` (`page` from 1, `page_size` 1–100, default 25). Errors are `{"error": {"code", "message"}}`, including 422 via a `RequestValidationError` handler. Check order on every endpoint: 401 (no valid session) → 403 (role lacks permission) → 404 (id not in this merchant) → work. Every JSON endpoint declares a Pydantic `response_model` built on `ApiModel` (`extra="forbid"`), so responses cannot carry undeclared fields; CSV endpoints stream text and are the documented exception.
- SQL lives only in `app/db/queries/`. Every function's first parameter is `merchant_id`, every statement contains `merchant_id = :merchant_id`, by-id lookups are `id = :id AND merchant_id = :merchant_id`. The one exception is `queries/access.py`, which resolves personas and memberships before a session exists. Sort columns come from a whitelist dict, never from user strings. `LIKE` wildcards in search input are escaped.
- Derived values are not stored. Payment status comes from the `payment_summary` view: a succeeded attempt exists → `refunded` if succeeded refunds equal the amount, `partially_refunded` if they are positive, else `succeeded`; no succeeded attempt and the latest attempt is `pending` → `pending`; otherwise `failed`. Pending refunds do not change status. Customer first/recent activity (max of last payment and last refund), payment timelines, dispute histories, payout itemisation and all Overview totals are computed from the rows they summarise. The one stored derived number is `payout.amount_cents`, verified against its movements at seed time, in tests and on every detail read (a mismatch is a 500, never papered over).
- Canonical timestamps: the Payments list filters and sorts on `payment.created_at`; the Attempts tab on `payment_attempt.created_at`; "collected" money (Overview tiles, chart, payout buckets) on the `charge` movement's `posted_at`, which equals the succeeding attempt's `completed_at`.
- Exports reuse the matching list query builder with pagination removed. CSV: stdlib `csv`, UTF-8, header row, no footer or totals row, `amount_cents` integer plus `amount_usd` string, timestamps rendered in America/Chicago with offset in `*_chicago` columns, filename `<merchant-slug>_<report>_<from>_<to>.csv`, `Content-Disposition: attachment`. Every download is recorded as an `export` activity.
- Frontend: function components, named exports, no UI library, no CSS-in-JS. Money through `formatCents()` (integer math), timestamps through `formatTimestamp()` and friends (`Intl.DateTimeFormat`, `timeZone: "America/Chicago"`); relative times and "due in N days" are computed against the session's `as_of`, not the browser clock. Status is a dot plus text, never colour alone. Money cells right-aligned with `font-variant-numeric: tabular-nums`, header included. Every data view has loading (skeleton), empty, error, 403 and 404 states; every write has pending and saved states. `:focus-visible` rings on everything interactive. Filters, sort, page and tab live in the URL query string.
- Python: type hints everywhere, no `print` in `app/` outside the seed CLI, no `datetime.now()` outside `app/core/clock.py` (a test scans for it, and for `Date.now()` / `new Date()` outside `lib/format.ts` on the frontend).
- Git: feature branches off `main`, imperative commit subjects, bodies that say what was verified. Never commit `backend/data/*.db`. See "Adding a feature".

## Data model summary

Entities: Merchant, Location, User, Membership, Customer, Payment, PaymentAttempt, Refund, Payout, BalanceMovement, Dispute, NoteEvent, plus `seed_meta` (key/value: rng seed, window, reporting clock, checksum; never a wall-clock value). Full column list and constraints in `docs/DATA_MODEL.md` and `backend/app/db/schema.sql`.

- Every merchant-owned table carries `merchant_id`, including children (attempts, refunds, movements, notes), and every child → parent foreign key is composite `(parent_id, merchant_id)` with `PRAGMA foreign_keys=ON`, so a child can never belong to a different merchant than its parent. Polymorphic links (a movement's source, a note's subject) are nullable per-type composite FKs (`payment_id`, `attempt_id`, `refund_id`, `dispute_id`, `payout_id`) with a CHECK tying each type or kind to exactly the FKs it must carry.
- **Payment** is the shopper's purchase intent: order reference, amount, channel, location (required exactly when `in_store`), customer or guest (`customer_id NULL`). It has no status column.
- **PaymentAttempt** is one execution: attempt number, masked method, outcome, `failure_code` + `failure_message` when failed, created/completed. At most one succeeded attempt per payment (partial unique index); nothing after a success; pending only as the latest attempt. A declined-then-retried order is one payment with two attempts, never two payments. The list shows the method of the succeeded attempt, else the latest.
- **Refund** and **Dispute** link to the payment, never to an attempt, and never modify attempt rows. Refund: amount, reason, status. Dispute: amount, reason, status, `opened_at`, `evidence_due_at`, `responded_at`, `resolved_at`; one per payment; a dispute is a tag on a payment, not a status.
- **BalanceMovement** is the signed ledger; signs are part of the type: `charge`, `dispute_reinstatement` and positive `adjustment`s are credits, `fee`, `refund`, `dispute_reversal`, `dispute_fee` and negative `adjustment`s are debits, and `amount_cents` carries the sign so reconciliation is one `SUM`. Succeeded attempt → `charge +amount` and `fee −(2.9% + 30¢ online, 2.7% + 5¢ in-store, integer half-up)` posted at `completed_at`, `available_on = posted_at + 2 days`. Failed and pending attempts post nothing. Succeeded refund → `refund −amount` posted at `refund.completed_at`; pending refunds post nothing. Dispute → `dispute_reversal −amount` and `dispute_fee −1500` at `opened_at`; won → `dispute_reinstatement +amount` at `resolved_at`. A few `adjustment` rows with descriptions. `payout_id NULL` means not yet swept.
- **Payout** is created at each schedule cutoff (00:00 America/Chicago on the merchant's payout days; Alder & Loom daily on business days, Juniper weekly Friday, Copper Finch weekly Monday; a cutoff that falls on a non-business day such as Labor Day 2026-09-07 rolls to the next business day) and sweeps every unswept movement with `available_on < cutoff`; an empty sweep creates no payout row. `payout.amount_cents == SUM(movement.amount_cents WHERE payout_id = id)`, itemised as collections + fees + refunds + disputes and adjustments. Sent 06:00 CT the same day (`in_transit`), arrives 09:00 CT the next business day (`paid` when `paid_at <= now`). Each merchant has its own masked destination, e.g. `"Alder & Loom, Operating account •••• 4821, external bank account, demo record"`.
- **Funds available for payout** = unswept movements with `available_on <= now`; **pending** = unswept with `available_on > now`. The **next payout** is derived, not stored: the next cutoff after `now` from the schedule, carrying the funds currently available, labelled as an estimate as of now. It is never labelled a bank balance.
- **Customer** is merchant-scoped: `UNIQUE(merchant_id, email)`; the same email at two merchants is two unrelated rows.
- **NoteEvent** is "who did what, when": kind `note` (internal investigation notes on payments and disputes, the only user write) and `export` (a CSV download), with `actor_user_id`, subject and time. Settings → Activity lists them.

## Auth, sessions and scoping

- Development-only persona selector. `GET /api/dev/personas` lists seeded memberships grouped by merchant. `POST /api/dev/session {user_id, merchant_id}` looks up an active membership for exactly that pair; none means 403 `no_membership` and no cookie. On success it sets `ftc_session` (HttpOnly, SameSite=Lax, Path=/, 12 h): base64url(JSON `{membership_id, iat, exp}`) + `.` + base64url(HMAC-SHA256), stdlib only. The dev router exists only when `FINTECHCO_ENV != production`.
- `current_principal()` (`app/auth/session.py`) verifies the cookie on every request and loads user, membership, merchant and role from the `membership` row each time; nothing the client sends and nothing cached can carry a different merchant or role. `GET /api/session` returns `{membership_id, user, merchant, role, role_label, permissions, as_of, timezone}`; `DELETE /api/session` clears the cookie.
- Every `/api/*` route except `/api/ping`, `/api/dev/*`, `GET|DELETE /api/session` depends on `require("<permission>")`, which yields 401, then 403, then a `Principal`. `tests/test_route_permissions.py` enumerates `app.routes` and fails if any route lacks it, then runs role × route and asserts 403 exactly where the matrix says.
- Role matrix (`app/auth/permissions.py`, one dict; change only after asking):

| Permission | business_admin | operations_manager | finance_manager | read_only_analyst |
|---|:-:|:-:|:-:|:-:|
| `overview:read`, `payments:read` (list, Attempts tab, detail) | Y | Y | Y | Y |
| `customers:read` | Y | Y | – | Y |
| `disputes:read` | Y | Y | Y | Y |
| `payouts:read` (list, detail) | Y | – | Y | Y |
| `notes:write` (payment and dispute notes) | Y | Y | – | – |
| `reports:operational` (payment register, attempt export) | Y | Y | Y | – |
| `reports:financial` (payout reconciliation, refund register, payout CSV) | – | – | Y | – |
| `settings:read` (profile, team, activity) | Y | – | – | – |

- Overview is summary content for every role: the funds-available and next-payout tiles render for everyone with `overview:read`; links from tiles and attention items into Payouts or Disputes render only when the role has that permission. Hiding nav items and buttons is a courtesy; the backend is the enforcement.
- Scoping: all queries filter on the principal's `merchant_id`; cross-merchant ids return 404 (not 403) so the existence of other merchants' records is not confirmed. Exports and search are scoped the same way. Switching persona remounts the whole app (keyed by `membership_id`) so no data from the previous merchant stays on screen.

## Clock and reporting timezone

- One reporting timezone, **America/Chicago**, everywhere a human sees or chooses a time: Overview periods and labels, list filters, CSV exports, displayed timestamps. Storage and the API wire format stay UTC ISO 8601. Conversion happens once per side: `app/core/tz.py` (`chicago_day_bounds(date) -> (utc_start, utc_end_exclusive)`, `chicago_day(iso)`, `format_chicago(iso)`; the seed converts its CT schedules through the same module) and `frontend/src/lib/format.ts`. Date filters are Chicago calendar dates, inclusive, converted to UTC instants with DST handled by `zoneinfo`.
- Period presets (`app/core/periods.py`) are inclusive CT date ranges ending on the clock's date: `last_7_days` and `last_30_days` are the 7 or 30 CT dates ending today (today being partial, up to `now`), `month_to_date` is the 1st through today, `custom` is `from`/`to`. The frontend sends preset names; the same `from`/`to` dates are what the Payments list and the exports take, so "the same period" means the same two dates everywhere. The default everywhere is the last 7 days.
- There is one clock. The seed writes the reporting instant into `seed_meta` (`as_of`, Monday 2026-10-05 09:12 CT) and `clock.now(conn)` reads it; it drives "as of", funds available, next payout, deadline countdowns, period presets, relative times and the greeting. The seeded window is the 30 complete CT days before that date plus the partial day up to the clock. Writes (notes, exports) and session expiry use `clock.wall_now()`, and those are the only wall-clock reads (`tests/test_clock_scan.py`).

## Seed and determinism

- One `random.Random(FIXED_SEED)` owned by the seeder; no module-level `random`, no `uuid4`, no wall clock, sorted iteration only. Generation is a pure `build_dataset()` of dataclasses, written in fixed table order in one transaction, then `verify.py` runs the invariant suite (one success per payment, movement pairs, payout reconciliation, merchant consistency, formats) and fails the seed on any violation.
- `make seed` and `make reset` print a SHA-256 over every table's rows ordered by primary key (excluding the `seed_meta` checksum row). `tests/test_seed_reproducible.py` holds the golden value; update it only for an intentional scenario change and say so in the commit message. The seed CLI prints row counts per table and the checksum, nothing else.
- Scenario parameters live in `app/seed/scenario.py` as plain data (`first_attempt_outcome_weights`, `window_overrides`, `decline_codes`, schedules, catalogues of names and products). Change the scenario there, reseed, and update the golden checksum in the same commit.

## Guardrails

1. **Synthetic data only.** Fictional merchants, invented people, `example.com` emails, masked card details (brand + last4), masked bank references marked "demo record". Never import, paste or generate real customer, card or bank data. The "Demo environment · Synthetic data" indicator stays visible. FinTechCo branding only.
2. **No new dependencies without asking.** The approved set is exactly: Python `fastapi`, `uvicorn`, `httpx`, `pytest`, `tzdata`; Node `react`, `react-dom`, `react-router-dom` and dev `vite`, `@vitejs/plugin-react`, `typescript`, `@types/react`, `@types/react-dom`, `vitest`, `jsdom`. Charts are hand-written SVG, CSS is plain, dates use `Intl`/`zoneinfo`. Anything else, including linters, requires explicit approval first.
3. **Money stays integer cents** with an explicit `currency` column, USD only. No floats or decimals in models, SQL, schemas, CSVs or frontend formatting. Every displayed total is derived from the same records shown on detail pages, and a payout reconciles exactly to its movements.
4. **Merchant scoping is enforced in the backend** on every endpoint: `require()` on every route, `merchant_id` in every query, cross-merchant ids are 404, the session carries only a membership id, the dev session endpoint refuses non-members. Hiding UI is never the enforcement.
5. **`make test` is green before every commit.** The backend suite, the frontend typecheck and the frontend tests all pass; a change that needs a golden value or a fixture updated says so in its commit message.
6. **Derive, don't duplicate.** Payment status, timelines, dispute histories, customer activity, reconciliation groups and Overview totals are computed from base records. The only stored derived number is `payout.amount_cents`, which is verified against the ledger.
7. **Determinism is sacred in the seed.** No wall clock, no unseeded randomness, no order-dependent iteration; the golden checksum guards it.
8. **Only two product write paths exist**: payment notes and dispute notes (plus the `export` activity record). No refund execution, evidence submission, dispute resolution, invitations, password recovery or settings edits, and no buttons for them, unless a ticket adds one deliberately.
9. **Stop and ask** when a requirement conflicts with something found in this guide or the codebase. Do not assume.

## Adding a feature

A feature touches the same five places every time; keep each in its usual spot so the cross-cutting tests keep covering it.

1. **Query** — `backend/app/db/queries/<resource>.py`. Every function takes `merchant_id` first and every statement filters on it; sort columns come from a `SORT_COLUMNS` whitelist; filters are a small dataclass. Nothing outside `db/queries/` contains SQL.
2. **Schema** — `backend/app/api/schemas/<resource>.py`. Response models extend `ApiModel`; list responses reuse `{items, page, page_size, total}`; labels come from `core/labels.py`, money is `int` cents with `currency`.
3. **Router** — `backend/app/api/<resource>.py` exposes `router`. Every route depends on `require("<permission>")` and declares `response_model=`; the handler checks existence in this merchant (404) before doing work and raises `ApiError(status, code, message)` for errors. Add the module name to the list in `register_routers()` in `app/api/__init__.py`. A new permission is a change to the role matrix in `auth/permissions.py` and needs sign-off first; the frontend reads it through `can("<permission>")`.
4. **Frontend** — types in `src/api/<resource>-types.ts` mirroring the schema; a page in `src/pages/<resource>/<Name>Page.tsx` built from `useApi`, `useQueryState`, `DataTable`, `FilterBar` and the state components; a route in `App.tsx` wrapped in `RequirePermission`; a nav item in `layout/SideNav.tsx` gated by `can()`. Money and timestamps only through `lib/format.ts`. Filters, sort, page and tab live in the URL.
5. **Tests** — `backend/tests/test_<resource>.py` using the fixtures in `tests/conftest.py`: `client_as("maya")` (also `daniel`, `jordan`, `sam` at Alder & Loom, `priya` at Juniper Trail, `sam_copper` at Copper Finch) returns a signed-in `TestClient` over a private copy of the seeded database; `ids.samples[<merchant-slug>][<param>]` gives a real id of each kind; `seeded_conn` is a read-only connection for independent SQL. Add a cross-merchant case for every new by-id route to `CASES` in `tests/test_merchant_scoping.py`; `tests/test_route_permissions.py` picks up the new routes automatically and fails if one is unguarded or lacks a `response_model`. Frontend pages get a `<Name>Page.test.tsx` beside them using `renderPage` and `mockFetch` from `src/test/`.

Git workflow: branch `feature/<ticket>-<slug>` from `main`; keep `make test` green; open a pull request into `main` whose description lists the tests added. Imperative commit subjects; bodies say what was verified.
