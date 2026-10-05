# CLAUDE.md — FinTechCo Business

FinTechCo Business is a merchant payments portal built as the baseline for a sales demo. `docs/SPEC.md` is the brief and the source of truth; `docs/PLAN.md` is the approved phased plan. If anything here conflicts with the brief, the brief wins: stop and ask. Everything in this repository is fictional and synthetic.

A later feature (PH-142, "Payment Health") will be added live on top of this baseline, so this codebase must deliberately not contain any part of it. See GUARDRAILS.

## Stack and layout

- Backend: Python 3.11+, FastAPI, stdlib `sqlite3` with hand-written SQL (no ORM), pytest. Single service in `backend/`. The Makefile picks the interpreter explicitly (`python3.13`, else `python3.12`, else `python3.11`) and `make setup` fails with a clear message below 3.11; `.python-version` is committed.
- Frontend: Node 20+, React + Vite + TypeScript (strict), `react-router-dom`, plain CSS with design tokens, hand-written SVG chart, Vitest. Single app in `frontend/`.
- Database: SQLite file at `backend/data/fintechco.db` (gitignored; created by the seed).
- Dev wiring: Vite (`:5173`) proxies `/api` to uvicorn (`:8000`), so the app is same-origin and the session cookie just works.

```
Makefile                      setup | seed | reset | run | test | check-boundary | acceptance
.python-version               interpreter hint for pyenv/uv
CLAUDE.md                     this file
docs/SPEC.md                  the brief (do not edit)
docs/PLAN.md                  approved phased plan
docs/DATA_MODEL.md            tables, derivation rules, ledger identity (written in Phase 1)
docs/ACCEPTANCE.md            Definition of Done run results (written in Phase 8)
backend/
  requirements.txt            pinned: fastapi, uvicorn, httpx, pytest, tzdata
  pyproject.toml              pytest configuration only
  data/                       fintechco.db lives here (gitignored, .gitkeep committed)
  app/
    main.py                   create_app(), app = create_app(), GET /api/ping
    core/config.py            env: FINTECHCO_DB_PATH, FINTECHCO_ENV, FINTECHCO_SESSION_SECRET
    core/clock.py             now() = as_of read from seed_meta, wall_now() = real UTC; the only wall-clock reads
    core/tz.py                the only America/Chicago conversion code on the backend
    core/periods.py           the one resolver for last_7_days / last_30_days / month_to_date / custom
    core/money.py             integer-cent helpers, fee formula, cents -> "1,234.56" string
    core/ids.py               prefixed id generation
    db/schema.sql             DDL: tables, CHECKs, composite FKs, indexes, payment_summary view
    db/connection.py          per-request connection, WAL, foreign_keys=ON, sqlite3.Row
    db/queries/               one module per resource; every function takes merchant_id first
    auth/session.py           signed cookie, current_principal()
    auth/permissions.py       role matrix, require(permission)
    api/                      routers: dev, session, meta, overview, payments, attempts, payouts,
                              customers, disputes, reports, settings
    exports/csv.py            shared CSV writer
    seed/                     scenario.py, generate.py, write.py, verify.py, checksum.py, __main__.py
    tools/boundary_scan.py    Payment Health vocabulary and aggregation scan
  tests/                      pytest; acceptance checks live here (test_dod_01 ... test_dod_10)
frontend/
  package.json, package-lock.json (committed), vite.config.ts (/api proxy), tsconfig.json
  src/
    api/client.ts             fetch wrapper: credentials included, 401 -> persona chooser, 403/404 -> states
    session/                  SessionProvider, can(permission)
    dev/                      PersonaBar, PersonaChooser (development-only, outside product chrome)
    layout/                   AppShell, SideNav, TopBar, DemoIndicator
    components/               DataTable, Pagination, FilterBar, StatusBadge, Money, Timestamp, BarChart,
                              Timeline, NoteComposer, Loading/Empty/Error/Forbidden/NotFound states
    pages/                    overview, payments, payment-detail, payouts, payout-detail, customers,
                              customer-detail, disputes, dispute-detail, reports, settings
    lib/format.ts             the only place money and timestamps are formatted
    lib/query.ts              URL query-string state for filters, sort, page, tab
    styles/tokens.css, base.css
```

## Commands

Use the Makefile. Raw commands are listed so nothing is hidden. First run: `make setup && make seed && make run`.

| Target | What it does | Raw commands |
|---|---|---|
| `make setup` | Pick `python3.13`/`3.12`/`3.11` (fail clearly below 3.11), create the venv, install pinned Python deps, `npm ci` | `$(PYTHON) -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt && cd frontend && npm ci` |
| `make seed` | Create and populate the DB if it does not exist; no-op with a message if it does; prints the checksum | `cd backend && .venv/bin/python -m app.seed` |
| `make reset` | Delete `fintechco.db` (and `-wal`/`-shm`), reseed, print the checksum. Stop `make run` first. | `rm -f backend/data/fintechco.db*; cd backend && .venv/bin/python -m app.seed` |
| `make run` | Seed if the DB is missing, then start API (`:8000`) and Vite (`:5173`) as two jobs of one shell with a trap that kills both on Ctrl-C; a second `make run` after Ctrl-C starts cleanly | `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000` and `cd frontend && npm run dev -- --port 5173` |
| `make test` | Backend tests, frontend typecheck and smoke test (separate recipe lines, each from the repo root, so any failure fails the target) | `cd backend && .venv/bin/pytest -q` then `cd frontend && npx tsc --noEmit && npx vitest run` |
| `make check-boundary` | Build-time only, not part of `make test`: vocabulary and aggregation scan, must report zero hits | `cd backend && .venv/bin/pytest -q tests/boundary` |
| `make acceptance` | Definition of Done tests, verbose, one line per item | `cd backend && .venv/bin/pytest -v tests/test_dod_*.py` |

Single test: `cd backend && .venv/bin/pytest tests/test_dod_05_payout_reconciliation.py -q`.
Open `http://localhost:5173`; with no session the development persona chooser appears; pick a persona to reach the portal.

Environment variables (all optional in development):
- `FINTECHCO_DB_PATH` — default `backend/data/fintechco.db`, resolved from the package location, not the cwd.
- `FINTECHCO_ENV` — `development` (default) or `production`; production removes the `/api/dev/*` router entirely.
- `FINTECHCO_SESSION_SECRET` — HMAC key for the session cookie; a fixed development default is built in.

There is no clock override: the demo date is one constant in `app/seed/scenario.py` plus a reseed (see Clock).

## Conventions

- IDs are TEXT with a type prefix and 14 lowercase base-32 characters: `mer_`, `loc_`, `usr_`, `mem_`, `cus_`, `pay_`, `att_`, `ref_`, `po_`, `bm_`, `dp_`, `evt_`. Seeded IDs come from the seeded RNG, so they are stable across resets and may be used in docs and tests. Runtime writes (notes) use `secrets`.
- Timestamps: `*_at` columns are TEXT ISO 8601 UTC, second precision, trailing `Z` (lexicographically sortable). `*_date` columns are America/Chicago calendar dates `YYYY-MM-DD`. Never SQLite datetime arithmetic for local days.
- Money: `amount_cents INTEGER NOT NULL` plus `currency TEXT NOT NULL CHECK (currency = 'USD')` on every money-bearing table. Signed cents on balance movements. Pydantic fields are `int`. Fee math is integer half-up. Dollar strings are parsed and rendered with `divmod(abs(cents), 100)` and an explicit sign; never `float`.
- Enums are lowercase snake_case: channel `website|mobile_app|in_store`; method `card|wallet` (brand + last4 only, wallet type for wallets); attempt outcome `succeeded|failed|pending`; payment status `pending|succeeded|failed|partially_refunded|refunded` (derived, see below); refund status `pending|succeeded` with reason `requested_by_customer|damaged_in_transit|wrong_item|duplicate|price_adjustment|returned_in_store`; payout status `in_transit|paid`; movement type `charge|fee|refund|dispute_reversal|dispute_fee|dispute_reinstatement|adjustment`; dispute status `needs_response|under_review|won|lost` with reason `fraudulent|product_not_received|product_unacceptable|duplicate|credit_not_processed`; roles `business_admin|operations_manager|finance_manager|read_only_analyst`. Attempt failure codes are a fixed table in the seed (`insufficient_funds`, `do_not_honor`, `incorrect_cvc`, `expired_card`, `authentication_failed`, `card_velocity_exceeded`, `fraud_suspected`, `issuer_unavailable`, `processing_error`, `lost_or_stolen`, `incorrect_number`) each with a human label.
- API: every list response, the Attempts list included, is `{items, page, page_size, total}`. Errors are `{"error": {"code", "message"}}`, including 422 via a `RequestValidationError` handler. Check order on every endpoint: 401 (no valid session) → 403 (role lacks permission) → 404 (id not in this merchant) → work. Every JSON endpoint declares a Pydantic `response_model`, so responses cannot carry undeclared fields; CSV endpoints stream text and are the documented exception.
- SQL lives only in `app/db/queries/`. Every function's first parameter is `merchant_id`, every statement contains `merchant_id = :merchant_id`, by-id lookups are `id = :id AND merchant_id = :merchant_id`. Sort columns come from a whitelist dict, never from user strings. `LIKE` wildcards in search input are escaped.
- Derived values are not stored. Payment status comes from the `payment_summary` view: a succeeded attempt exists → `refunded` if succeeded refunds equal the amount, `partially_refunded` if they are positive, else `succeeded`; no succeeded attempt and the latest attempt is `pending` → `pending`; otherwise `failed`. Pending refunds do not change status. Customer first/recent activity (max of last payment and last refund), payment timelines, dispute histories, payout itemisation and all Overview totals are computed from the rows they summarise. The one stored derived number is `payout.amount_cents`, verified against its movements at seed time, in tests and on every detail read (a mismatch is a 500, never papered over).
- Canonical timestamps: the Payments list filters and sorts on `payment.created_at`; the Attempts tab on `payment_attempt.created_at`; "collected" money (Overview tiles, chart, payout buckets) on the `charge` movement's `posted_at`, which equals the succeeding attempt's `completed_at`. The seed keeps attempts short and away from Chicago midnight so these never straddle a day.
- Exports reuse the matching list query builder with pagination removed. CSV: stdlib `csv`, UTF-8, header row, no footer or totals row, `amount_cents` integer plus `amount_usd` string, timestamps rendered in America/Chicago with offset in `*_chicago` columns, filename `<merchant-slug>_<report>_<from>_<to>.csv`, `Content-Disposition: attachment`.
- Frontend: function components, named exports, no UI library, no CSS-in-JS. Money through `formatCents()` (integer math), timestamps through `formatTimestamp()` (`Intl.DateTimeFormat`, `timeZone: "America/Chicago"`); relative times and "due in N days" are computed against the session's `as_of`, never the browser clock. `Date.now()` and bare `new Date()` appear only in `lib/format.ts` (a test enforces it). Period filters send preset names (`last_7_days`, `last_30_days`, `month_to_date`) or `custom` with the user's two dates; the frontend never computes dates. Status is a dot plus text, never colour alone. Money cells right-aligned with `font-variant-numeric: tabular-nums`, header included. Every data view has loading (skeleton), empty, error, 403 and 404 states; every write has pending and saved states. `:focus-visible` rings on everything interactive. Filters, sort, page and tab live in the URL query string, so a link can land on a filtered view.
- `BarChart` is a generic primitive: one or more series of `{label, value}` points, a `formatValue` prop (Overview passes `formatCents`), optional horizontal orientation. Overview is simply its only caller today.
- Python: type hints everywhere, no `print` in `app/` outside the seed CLI. `datetime.now()`, `utcnow()` and `time.time()` appear only in `app/core/clock.py` (a test enforces it).
- Git: one commit per phase of `docs/PLAN.md`, imperative subject, body lists what was verified. Never commit `backend/data/*.db`.

## Data model summary

Entities: Merchant, Location, User, Membership, Customer, Payment, PaymentAttempt, Refund, Payout, BalanceMovement, Dispute, NoteEvent, plus `seed_meta` (key/value: rng seed, window, as-of, checksum; never a wall-clock value). Full column list and constraints in `docs/DATA_MODEL.md` and `backend/app/db/schema.sql`.

- Every merchant-owned table carries `merchant_id`, including children (attempts, refunds, movements, notes), and every child → parent foreign key is composite `(parent_id, merchant_id)` with `PRAGMA foreign_keys=ON`, so a child can never belong to a different merchant than its parent. Polymorphic links (a movement's source, a note's subject) are nullable per-type composite FKs (`payment_id`, `attempt_id`, `refund_id`, `dispute_id`, `payout_id`) with a CHECK tying each type or kind to exactly the FKs it must carry.
- **Payment** is the shopper's purchase intent: order reference, amount, channel, location (required exactly when `in_store`), customer or guest (`customer_id NULL`). It has no status column.
- **PaymentAttempt** is one execution: attempt number, masked method, outcome, `failure_code` + `failure_message` when failed, created/completed. At most one succeeded attempt per payment (partial unique index); nothing after a success; pending only as the latest attempt. A declined-then-retried order is one payment with two attempts, never two payments. The list shows the method of the succeeded attempt, else the latest.
- **Refund** and **Dispute** link to the payment, never to an attempt, and never modify attempt rows. Refund: amount, reason, status. Dispute: amount, reason, status, `opened_at`, `evidence_due_at`, `responded_at`, `resolved_at`; one per payment; a dispute is a tag on a payment, not a status.
- **BalanceMovement** is the signed ledger; signs are part of the type: `charge`, `dispute_reinstatement` and positive `adjustment`s are credits, `fee`, `refund`, `dispute_reversal`, `dispute_fee` and negative `adjustment`s are debits, and `amount_cents` carries the sign so reconciliation is one `SUM`. Succeeded attempt → `charge +amount` and `fee −(2.9% + 30¢ online, 2.7% + 5¢ in-store, integer half-up)` posted at `completed_at`, `available_on = posted_at + 2 days`. Failed and pending attempts post nothing. Succeeded refund → `refund −amount` posted at `refund.completed_at`; pending refunds post nothing. Dispute → `dispute_reversal −amount` and `dispute_fee −1500` at `opened_at`; won → `dispute_reinstatement +amount` at `resolved_at`. A few `adjustment` rows with descriptions. `payout_id NULL` means not yet swept.
- **Payout** is created at each schedule cutoff (00:00 America/Chicago on the merchant's payout days; Alder & Loom daily on business days, Juniper weekly Friday, Copper Finch weekly Monday). For every merchant a cutoff that falls on a weekend or holiday (Labor Day 2026-09-07) moves to the next business day, and an empty sweep creates no payout row. A payout sweeps every unswept movement with `available_on < cutoff`. `payout.amount_cents == SUM(movement.amount_cents WHERE payout_id = id)`, itemised as collections + fees + refunds + disputes and adjustments. Sent 06:00 CT the same day (`in_transit`), arrives 09:00 CT the next business day (`paid` when `paid_at <= now`). Each merchant has its own masked destination, e.g. `"Alder & Loom, Operating account •••• 4821, external bank account, demo record"`.
- **Funds available for payout** = unswept movements with `available_on <= now`; **pending** = unswept with `available_on > now`. The **next payout** is derived, not stored: the next cutoff after `now` from the schedule, carrying the funds currently available, labelled as an estimate as of now. It is never labelled a bank balance.
- **Customer** is merchant-scoped: `UNIQUE(merchant_id, email)`; the same email at two merchants is two unrelated rows.
- **NoteEvent** is "who did what, when": kind `note` (internal investigation notes on payments and disputes, the only user write) and `export` (a CSV download), with `actor_user_id`, subject and time. Settings → Activity lists them.

## Auth, sessions and scoping

- Development-only persona selector. `GET /api/dev/personas` lists seeded memberships grouped by merchant. `POST /api/dev/session {user_id, merchant_id}` looks up an active membership for exactly that pair; none means 403 `no_membership` and no cookie. On success it sets `ftc_session` (HttpOnly, SameSite=Lax, Path=/, 12 h): base64url(JSON `{membership_id, iat, exp}`) + `.` + base64url(HMAC-SHA256), stdlib only. The dev router exists only when `FINTECHCO_ENV != production`.
- `current_principal()` (`app/auth/session.py`) verifies the cookie on every request and loads user, membership, merchant and role from the `membership` row each time; nothing the client sends and nothing cached can carry a different merchant or role. `GET /api/session` returns `{user, merchant, role, permissions, as_of, timezone}`; `DELETE /api/session` clears the cookie.
- Every `/api/*` route except `/api/ping`, `/api/dev/*`, `GET|DELETE /api/session` depends on `require("<permission>")`, which yields 401, then 403, then a `Principal`. A test enumerates `app.routes` and fails if any route lacks it, then runs role × route and asserts 403 exactly where the matrix says.
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
- Tests that assert a cross-merchant 404 use a persona that holds the permission, so the 404 is actually reached (for payouts: Sam Okafor at Copper Finch requesting an Alder & Loom payout); a persona without the permission is the 403 case. The 401 → 403 → 404 order is never changed to make a test pass.
- Scoping: all queries filter on the principal's `merchant_id`; cross-merchant ids return 404 (not 403) so the existence of other merchants' records is not confirmed. Exports and search are scoped the same way. Switching persona remounts the whole app (keyed by `membership_id`) so no data from the previous merchant stays on screen.

## Clock and reporting timezone

- One reporting timezone, **America/Chicago**, everywhere a human sees or chooses a time: Overview periods and labels, list filters, CSV exports, displayed timestamps. Storage and the API wire format stay UTC ISO 8601. Conversion happens once per side: `app/core/tz.py` (`chicago_day_bounds(date) -> (utc_start, utc_end_exclusive)`, `chicago_day(iso)`, `format_chicago(iso)`; the seed converts its CT schedules through the same module) and `frontend/src/lib/format.ts`. Date filters are Chicago calendar dates, inclusive, converted to UTC instants with DST handled by `zoneinfo`.
- Period presets are resolved in exactly one place, `app/core/periods.py`, from `clock.now()`: `last_7_days` and `last_30_days` are the 7 or 30 CT dates ending today (today being partial, up to `now`), `month_to_date` is the 1st through today, `custom` is `from`/`to`. The Overview, the Payments and Attempts tabs and the exports all accept the same preset names and show the same labels; the default preset everywhere is `last_7_days`. "The same period" therefore means the same resolved dates everywhere.
- One clock. The seed writes `as_of` into `seed_meta` and `clock.now()` reads it from the database, so there is nothing to configure: the demo date is one constant in `app/seed/scenario.py` plus a reseed. `now()` drives "as of", funds available, next payout, deadline countdowns, period presets, relative times and the Overview greeting (so it always reads "Good morning" beside the 9:12 as-of labels). The seed window is the 30 complete CT days before the as-of date plus the live partial day up to the clock. Writes (notes, exports) and session expiry use `clock.wall_now()`, the only wall-clock reads in the backend.

## Seed and determinism

- One `random.Random(FIXED_SEED)` owned by the seeder; no module-level `random`, no `uuid4`, no wall clock, sorted iteration only. Generation is a pure `build_dataset()` of dataclasses, written in fixed table order in one transaction, then `verify.py` runs the invariant suite (one success per payment, movement pairs, payout reconciliation, merchant consistency, formats) and fails the seed on any violation.
- `make seed` and `make reset` print a SHA-256 over every table's rows ordered by primary key (excluding the `seed_meta` checksum row). `tests/test_dod_08_reset_reproducible.py` holds the golden value; update it only for an intentional scenario change and say so in the commit message. The seed CLI prints row counts per table and the checksum, nothing else.
- Seed parameter names are neutral (`first_attempt_outcome_weights`, `window_overrides`, `decline_codes`): the boundary scan covers `app/seed/` like the rest of `app/`, so no constant or comment may use the forbidden vocabulary. Baseline outcome weights give every channel a 6 to 9% first-attempt failure share; per-window overrides are plain parameters with no narrative, and nothing in the repository describes what any override represents.

## GUARDRAILS

1. **Synthetic data only.** Fictional merchants, invented people, `example.com` emails, masked card details (brand + last4), masked bank references marked "demo record". Never import, paste or generate real customer, card or bank data. The "Demo environment · Synthetic data" indicator stays visible. FinTechCo branding only.
2. **No new dependencies without asking.** The approved set is exactly: Python `fastapi`, `uvicorn`, `httpx`, `pytest`, `tzdata`; Node `react`, `react-dom`, `react-router-dom` and dev `vite`, `@vitejs/plugin-react`, `typescript`, `@types/react`, `@types/react-dom`, `vitest`, `jsdom`. Charts are hand-written SVG, CSS is plain, dates use `Intl`/`zoneinfo`. Anything else, including linters, requires explicit approval first.
3. **Money stays integer cents** with an explicit `currency` column, USD only. No floats or decimals in models, SQL, schemas, CSVs or frontend formatting. Every displayed total is derived from the same records shown on detail pages, and a payout reconciles exactly to its movements.
4. **Merchant scoping is enforced in the backend** on every endpoint: `require()` on every route, `merchant_id` in every query, cross-merchant ids are 404, the session carries only a membership id, the dev session endpoint refuses non-members. Hiding UI is never the enforcement.
5. **All acceptance checks in `docs/SPEC.md` must pass.** `make test` (which includes `tests/test_dod_*.py`) is green before every phase commit, and the ten Definition of Done items are run and reported in `docs/ACCEPTANCE.md` at the end.
6. **Hard boundary: no Payment Health.** Nothing may compute or show a completed-attempt success or failure summary, an aggregated failure-reason breakdown, a success or failure trend over time, a payment-performance view or health indicator, or a drill-down from an aggregate into attempts; no dormant endpoint, hidden page, feature flag or "coming soon" panel for any of it. The boundary is rates, groupings over outcome or failure code, trends and health indicators, not a row count: every list, the Attempts tab included, returns a pagination `total`. Concretely: no filter option carries a count; no `GROUP BY` over `outcome` or `failure_code` anywhere in `app/`; Overview tiles and chart bars do not link anywhere except the next-payout tile to Payouts; attention items are a closed enum (`dispute_deadline`, `payout_in_transit`, `refund_pending`) and their query never reads the `payment_attempt` table at all; the Overview and `meta` responses carry no counts of records; exports have no totals rows; no test or seed check computes a success or failure rate (tests check money totals through movements, never by summing attempts by outcome); the liveness route is `/api/ping`. Allowed and expected: per-record outcomes and recorded reasons on attempts, the Attempts tab's outcome/period/channel filters with the result total, the generic table and chart primitives, data-access helpers, auth and test utilities. The checks are build-time only: `make check-boundary` (`backend/tests/boundary/`, excluded from `make test` so the suite still passes when a later feature adds aggregations over attempts) scans `backend/app` and `frontend/src` for the vocabulary (`payment health`, `success rate`/`success_rate`, `failure rate`/`failure_rate`, `decline rate`, `approval rate`, `authorization rate`, `health`, `trend`, `PH-142`, `coming soon`, `feature_flag`), for `GROUP BY` over `outcome` or `failure_code`, and for route paths containing `health|metrics|stats|analytics|trend|performance|insights`; it is run once for the acceptance record and must report nothing. `docs/SPEC.md`, `docs/PLAN.md`, this file and the scan's own tests necessarily contain the vocabulary and are listed as such in `docs/ACCEPTANCE.md`.
7. **Derive, don't duplicate.** Payment status, timelines, dispute histories, customer activity, reconciliation groups and Overview totals are computed from base records. The only stored derived number is `payout.amount_cents`, which is verified against the ledger.
8. **Determinism is sacred in the seed.** No wall clock, no unseeded randomness, no order-dependent iteration; the golden checksum guards it.
9. **Only two product write paths exist**: payment notes and dispute notes (plus the `export` activity record). No refund execution, evidence submission, dispute resolution, invitations, password recovery or settings edits, and no buttons for them.
10. **Stop and ask** when a requirement conflicts with something found in the brief or the codebase. Do not assume. Work phase by phase against `docs/PLAN.md` and run the tests as you go.
