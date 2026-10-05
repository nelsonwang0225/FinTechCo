# FinTechCo Business — Phased Implementation Plan

Source of truth: `docs/SPEC.md`. Conventions, layout, role matrix and guardrails: `CLAUDE.md`. Approved on 2026-10-05 with the amendments folded in below. One commit per phase; `make test` is green before each commit. Where the brief leaves a choice open, pick the option closest to the brief, keep going, and list the choice in the final report; stop only for a genuine blocker.

## Decisions the phases build on

- **Stack.** FastAPI + stdlib `sqlite3` with hand-written SQL and a `schema.sql` full of CHECK constraints and composite foreign keys; React + Vite + TypeScript with plain CSS and a hand-written SVG chart. Dependencies: Python `fastapi`, `uvicorn`, `httpx`, `pytest`, `tzdata`; Node `react`, `react-dom`, `react-router-dom` plus dev tooling (`vite`, `@vitejs/plugin-react`, `typescript`, types, `vitest`, `jsdom`). Nothing else without asking. Python 3.11+ (Makefile picks `python3.13`/`3.12`/`3.11`, `.python-version` committed) and Node 20+.
- **One clock.** The seed writes `as_of` (Monday 2026-10-05 09:12 America/Chicago) into `seed_meta` and `clock.now()` reads it from the database; there is no environment override. The seed covers the 30 complete CT days before that date plus the live partial day (Labor Day Sep 7 inside the window). Every "as of", "next payout", "due in N days", period preset, relative time and the Overview greeting hang off `clock.now()`, so `make reset` is identical on any day and the Overview reads "Good morning" beside the 9:12 as-of labels. The demo date is one constant in `scenario.py` plus a reseed.
- **Periods in one place.** `app/core/periods.py` resolves `last_7_days` / `last_30_days` / `month_to_date` / `custom` from `clock.now()`; the Overview, the Payments and Attempts tabs and the exports use it with identical preset names and labels, default `last_7_days`. The frontend sends preset names and never computes dates from the browser clock. A test fails on `datetime.now()`, `utcnow()` or `time.time()` outside `clock.py` and on `Date.now()` or bare `new Date()` outside `format.ts`.
- **Payment status is derived**, never stored: a `payment_summary` SQL view feeds list, detail, Overview, customer pages and the register export, so list and detail agree by construction.
- **Ledger.** `BalanceMovement` is a signed ledger; a payout sweeps unswept movements available before its cutoff and `payout.amount_cents == SUM(movements)` exactly, itemised as collections + fees + refunds + disputes/adjustments. Failed and pending attempts post nothing. Funds available and the next payout are derived from unswept movements. For every merchant a cutoff on a non-business day moves to the next business day, and an empty sweep creates no payout row.
- **Sessions.** Development-only persona selector → `POST /api/dev/session {user_id, merchant_id}` → 403 unless that exact membership exists → HMAC-signed HttpOnly cookie carrying only `membership_id`. Merchant and role are re-read from the membership on every request. Cross-merchant ids are 404. Every route declares `require(permission)`; a router-introspection test fails any route that does not. Cross-merchant tests use a persona that holds the permission so the 404 is actually reached; the 401 → 403 → 404 order is never reordered to make a test pass.
- **Role matrix.** As in `CLAUDE.md`: business_admin has `payouts:read` (no financial exports) and finance_manager has `disputes:read` (no notes); everything else as proposed.
- **Scoping.** `merchant_id` on every table including children, composite FKs `(parent_id, merchant_id)` with `foreign_keys=ON`, and every query function takes `merchant_id` first.
- **Boundary.** The boundary is rates, groupings over outcome or failure code, trends and health indicators, not a row count: the Attempts tab returns a `total` like every other list and keeps its filters in the URL. No facet counts; no `GROUP BY` over outcome or failure code; closed attention-item enum; flat exports; `/api/ping` not `/api/health`. The chart primitive is generic from day one (one or more series of `{label, value}`, `formatValue`, optional horizontal orientation); Overview is simply its only caller. Boundary checks are build-time only: `make check-boundary` and the DoD 10 checks stay out of `make test` and are run once for the acceptance record.
- **Seed realism.** Baseline first-attempt failure share of 6 to 9% in every channel (roughly 2,600 attempts for Alder & Loom's ~2,400 payments), plausible decline codes, retries on the same payment. Per-window parameter overrides exist as plain data; nothing in the repository names or describes them.
- **Timezone.** UTC ISO 8601 in storage and on the wire; America/Chicago at filter, display and export boundaries through one helper per side.

## Phase 0 — Plan and guardrails on record (done)
Deliverables: `CLAUDE.md`, `docs/PLAN.md`, approved with amendments and folded in.
Commits: `Add CLAUDE.md and phased implementation plan`, `Fold the approved amendments into the plan and CLAUDE.md`

## Phase 1 — Scaffold and data model
Goal: both services start from the documented commands; the full schema exists; the app shell and design tokens are in place.
- `Makefile` (interpreter detection with a clear failure below 3.11; setup, seed, reset, run as two jobs of one shell with a trap that kills both on Ctrl-C and verified to restart cleanly, test, check-boundary, acceptance), `.python-version`, `.gitignore`, `backend/data/.gitkeep`, pinned `requirements.txt`, committed `package-lock.json`.
- `app/main.py` (`create_app()`, `/api/ping` reporting whether the DB exists, error handler `{"error": {code, message}}`), `core/config.py`, `core/clock.py` (reads `as_of` from `seed_meta`), `core/tz.py`, `core/periods.py`, `core/money.py`, `core/ids.py`.
- `db/schema.sql`: all twelve entities plus `seed_meta`, CHECKs (currency, channel/location pairing, outcome/failure pairing, movement type/FK pairing), partial unique index for one succeeded attempt per payment, composite FKs, indexes on `(merchant_id, created_at)` and lookups, the `payment_summary` view. `db/connection.py` (per-request connection, WAL, `foreign_keys=ON`).
- `docs/DATA_MODEL.md`.
- Frontend scaffold: Vite + React + TS strict, `/api` proxy, `tokens.css` (warm white surfaces, dark ink, one teal accent, semantic status colours, `tabular-nums`), `AppShell` with left nav (Overview, Payments, Payouts, Customers, Disputes, Reports, Settings), top bar with merchant identity, the "Demo environment · Synthetic data" pill, route placeholders that render real page chrome, `lib/format.ts` (`formatCents`, `formatTimestamp`), Vitest smoke test, `tsc --noEmit`.
- Tests: schema (table set, money columns INTEGER with currency CHECK, `merchant_id` on every scoped table), `tz` (Chicago day bounds, DST days), `periods` (presets from a fixed now), `money` (fee rounding, negative formatting), the wall-clock scan (no `datetime.now()`/`utcnow()`/`time.time()` outside `clock.py`, no `Date.now()`/bare `new Date()` outside `format.ts`); the boundary scan (`tests/boundary/`, outside `make test`) runs clean on the skeleton.
Verified: from a clean clone `make setup`, `make test` green, `make run` serves the shell and `/api/ping`.
Commit: `Scaffold backend, frontend and Makefile with the data model`

## Phase 2 — Deterministic seed
Goal: `make reset` produces the identical, fully reconciled baseline every time, with the variety the brief describes.
- `app/seed/`: `scenario.py` (the as-of constant, merchants, locations, users, memberships, shopper name lists, priced catalogs, channel mixes, hour/weekday weights, outcome weights and decline codes, per-window parameter overrides, refund and dispute reasons, payout schedules), `generate.py` (pure `build_dataset()` over one `random.Random`), `write.py` (writes `as_of` into `seed_meta`), `verify.py` (invariants and reconciliation), `checksum.py`, `__main__.py`.
- Content: Alder & Loom (homeware catalog, website + mobile app + two stores, daily business-day payouts, ~2,400 payments / ~2,600 attempts), Juniper Trail Outfitters (website + one store, weekly Friday payouts, ~600 payments), Copper Finch Coffee (small menu prices, two shops, sparse order-ahead channel, days with zero volume in a channel, weekly Monday payouts, ~900 payments). Baseline first-attempt failure share of 6 to 9% in every channel with plausible decline codes, retries on the same payment (same or different card), a few pending attempts in the minutes before the clock on online channels, full and partial refunds with reasons (a couple pending), eight disputes with staggered deadlines (one due within days), payouts `paid` and `in_transit`, adjustments, ~15% guest payments, named repeat shoppers (Avery Stone, Morgan Lee, Taylor Reed) including an anchor payment with decline → retry → payout → partial refund → note, `avery.stone@example.com` as a distinct customer at Juniper, a handful of seeded notes by Maya, Jordan and Priya. Users per the brief plus the read-only analyst Sam Okafor at Alder & Loom and Copper Finch Coffee.
- `make seed` refuses to double-seed; `make reset` deletes and reseeds; both print row counts and the checksum.
- Tests: seed twice → identical checksum and golden value; invariants (one success per payment, nothing after a success, refunds ≤ amount and only after success, one charge+fee pair per success and none otherwise, every payout reconciles, children match parents, timestamp format, window bounds, shared email is two customers).
Verified: two `make reset` runs print the same checksum; a manual `sqlite3` look at the anchor payment reads correctly.
Commit: `Add deterministic seed with reconciling ledger and invariant checks`

## Phase 3 — Sessions, role matrix, merchant scoping, acceptance harness
Goal: the access model is built and proven before any business endpoint exists; personas are demoable in the browser.
- `auth/session.py` (signed cookie, `current_principal`), `auth/permissions.py` (matrix, `require`), routers `dev` (personas, session; env-gated), `session` (get, delete), `meta` (channels, statuses, outcomes, merchant-scoped locations; no counts, no failure reasons).
- Test harness: session-scoped seeded template DB copied per test, `client_as(persona)` fixtures for Maya, Daniel, Jordan, Priya, the analyst and anonymous; `SAMPLE_IDS` covering every path parameter (asserted against `app.routes`); `collect_ids()` to check every id in any response belongs to the active merchant.
- Tests: no/garbage/expired cookie → 401 on every protected route; forged `{maya, juniper}` → 403; analyst can start sessions at both of their merchants and not at Juniper; router introspection (every route has `require`); role × route matrix; `FINTECHCO_ENV=production` removes dev routes; DoD 1 (startup, a seeded user reaches the portal) and the DoD 3 framework.
- Frontend: `api/client.ts`, `SessionProvider` with `can()`, `PersonaChooser` (full-screen when no session, visibly not product UI), `PersonaBar` (collapsible dark band above the product chrome listing only seeded memberships), permission-filtered nav, remount on persona switch, shared states and table primitives (`DataTable`, `Pagination`, filters, `StatusBadge`, `Money`, `Timestamp`).
Verified: pick Maya → Alder & Loom; pick Priya → Juniper; nav changes per role; forged pair refused.
Commit: `Add persona sessions, role enforcement and merchant scoping with acceptance harness`

## Phase 4 — Payments, Attempts, payment detail, investigation notes
Goal: the pages the demo lives on, finished to the standard of the Overview.
- `GET /api/payments` (search by id, order reference, customer name/email; filters period preset or custom Chicago dates, status, channel, location, amount range; sort whitelist; `page`/`page_size` with `total`), `GET /api/attempts` (outcome, period preset or custom dates, channel, location, search; same pagination shape with `total`), `GET /api/payments/{id}` (payment, shopper, channel and location, masked method, attempts with recorded reasons, refund history, dispute tag, payout link, notes, and a timeline derived at read time: order received, each attempt with outcome and reason, settlement pending or funds available, included in payout, payout paid, refunds, dispute milestones, notes; future-dated events flagged upcoming), `POST /api/payments/{id}/notes` (`notes:write`, 1–2000 chars, actor from the session).
- Frontend: Payments page with Payments/Attempts tabs, URL-synced filter bar (date presets and custom range, status/outcome, channel, location, amount min/max parsed to cents without floats), debounced search, active-filter chips, sortable headers, pagination, skeleton/empty/error states, Export CSV button (wired in Phase 7). Payment detail with header, timeline, attempts table, refund history (no "Issue refund"), payout link gated by `can('payouts:read')`, customer link gated by `can('customers:read')`, note composer with saving/saved/error states for permitted roles and a read-only notice otherwise.
- Tests: DoD 2 (search, every filter cross-checked against SQL, stable disjoint pagination, list fields equal detail fields for a sample), DoD 4 (note persists, records the actor, visible through a fresh client, 403 for finance/analyst, 404 cross-merchant, 422 empty), DoD 7 (note survives a fresh app instance on the same file), anchor payment timeline order.
Commit: `Add payments list, attempts tab, payment detail timeline and investigation notes`

## Phase 5 — Payouts and reconciliation
Goal: payout list and detail reconcile exactly to the ledger; the constituent CSV downloads.
- `GET /api/payouts` (status and date-range filters, pagination, status rank then date desc) plus `summary {available_cents, pending_cents, next_payout {date, amount_cents}, as_of}`; `GET /api/payouts/{id}` (masked destination string, buckets, total, `reconciled`, every movement with payment/order links); `GET /api/payouts/{id}/export.csv` (`reports:financial`; one row per movement; records an `export` event). Reconciliation and the derived next payout live in `db/queries/payouts.py`; the timeline derivation written in Phase 4 lives in `db/queries/payments.py`.
- Frontend: Payouts list, "Funds available for payout" card (as-of label, never "balance"), upcoming payout card, detail with reconciliation table and Download CSV.
- Tests: DoD 5 (every payout of every merchant reconciles in DB, response and CSV; CSV row count equals movement count; Daniel 200; Priya 403 as the role without the permission; Sam Okafor at Copper Finch requesting an Alder & Loom payout 404, so the scoping check is actually reached).
Commit: `Add payouts with exact ledger reconciliation and movement CSV export`

## Phase 6 — Overview
Goal: a derived-only financial summary that agrees with the lists and stays inside the boundary.
- `GET /api/overview?period=last_7_days|last_30_days|month_to_date|custom&from&to`: greeting data, tiles with period/as-of labels (gross collected, refunds processed, funds available for payout, next payout), daily collected-volume series bucketed by Chicago day with zeros, recent payments, upcoming payout itemisation, attention items from the closed enum.
- Frontend: greeting ("Good morning, Maya" from `clock.now()`) with merchant name, period selector in the URL (default last 7 days), stat tiles, the generic SVG `BarChart` with `formatCents` (gridlines, text tooltips, accessible title, no navigation), recent payments, upcoming payout, attention list with permission-gated links.
- Tests: each tile equals an independent recomputation from charge/refund movements for the same Chicago period; chart buckets sum to the tile; CT midnight boundaries; response key set is exact and contains no attempt counts or rates.
Commit: `Add overview with derived financial summary and collected-volume chart`

## Phase 7 — Customers, Disputes, Reports, Settings
Goal: every remaining section works end to end; no "coming soon" anywhere.
- Customers: directory (name, email, reference, first payment, recent activity derived; search; pagination) and detail with payments and refunds tables. Guests are not customers.
- Disputes: queue (disputed amount, linked payment, reason, status, response deadline with "due in N days" from the clock), detail with case history derived from lifecycle timestamps plus notes, `POST /api/disputes/{id}/notes`. No evidence submission, no resolution actions.
- Reports: `payments.csv` (Payments list filters), `attempts.csv` (outcome, channel, location, date range, search; outcomes and recorded reasons per row), `payouts.csv` (payout date range and status; one row per payout with buckets and total), `refunds.csv` (date range, status, reason); each reuses its list query builder with the same filters and the active merchant; Reports page cards expose each report's filters; the Payments/Attempts Export buttons point at the first two with current filters.
- Settings (admin): Business profile (name, legal name, support email, reporting timezone, payout schedule, masked destination, locations), Team (memberships with role labels), Activity (notes and exports with actor, subject link and time). Read-only.
- Tests: DoD 6 (every export row satisfies every filter and belongs to the merchant; row count equals the filtered count; permissions per matrix), shared-email isolation, DoD 3 and 4 extended to customers and disputes, settings scope.
Commit: `Add customers, disputes, CSV reports and settings`

## Phase 8 — Polish and acceptance run
Goal: finished feel and a recorded Definition of Done run.
- State audit on every page (skeleton, empty, error, 403, 404, saved), focus order and visible rings, `aria-sort`/`aria-busy`, status text, column widths and timestamp readability on Payments and payment detail, consistent wording, `prefers-reduced-motion`.
- Fresh-clone rehearsal: clone to a temp dir, `make setup`, `make reset`, `make run`, sign in as Maya, `make test`. Restart check: add a note, stop and start the API, note still present.
- `tests/test_dod_09` (Makefile targets) and the build-time `tests/boundary/` checks (vocabulary scan, route-path scan, forbidden-key walk over every GET response as every role, no `GROUP BY` over outcome/failure code), run once via `make check-boundary` for the record and kept out of `make test`.
- `docs/ACCEPTANCE.md` recording each of the ten checks with command, result and evidence, including the checksum comparison and the scan output with its documented scope (and the note that `docs/SPEC.md`, `docs/PLAN.md`, `CLAUDE.md` and the scan's own tests contain the vocabulary by necessity).
Commit: `Polish states and accessibility; record acceptance checklist run`

## Phase 9 — Handoff
Goal: the repository reads as an established product's codebase.
- Rewrite `CLAUDE.md` as the product's engineering guide: no mention of a sales demo, a baseline, a brief, a plan, PH-142, Payment Health, a boundary, Definition of Done or phase-based git. Keep stack, layout, commands, conventions, data model, auth and scoping, clock and seed rules, and the synthetic-data, dependency, money, scoping and tests-green guardrails. Add a short "Adding a feature" section: where routers, queries, pages and tests go, the `require()` and `response_model` rules, the `client_as` fixtures, and the git workflow (branch `feature/<ticket>-<slug>` from `main`, `make test` green, PR into `main` listing the tests added).
- Rename `tests/test_dod_*` to descriptive names; drop `make acceptance` and `make check-boundary`; delete the boundary scan.
- Move `docs/SPEC.md`, `docs/PLAN.md` and `docs/ACCEPTANCE.md` to a `baseline-build` branch and remove them from the product branch. Add a short `README.md`.
- Create `main` from the final commit and make it the GitHub default branch (or report that it must be changed in GitHub settings).
Commit: `Hand off: engineering guide, descriptive test names, README`

## Final report
One message with: the exact commands to start the app and the URL, and which persona to pick first; the seed's deliberate parameter override described in chat only; the Definition of Done results, one line each; every default picked along the way; anything not finished. Then start the app with `make run` in the background and report that it is up.

## Approved defaults

1. **Demo clock date.** Mon 2026-10-05 09:12 CT, written by the seed into `seed_meta`; one constant plus a reseed to move it.
2. **Role matrix where the brief is silent.** Business administrator can add notes, read Payouts and run the operational exports; Operations manager can run the operational exports but has no Payouts pages (Overview tiles still show funds available and next payout); Finance manager can run all four exports and read Disputes but has no Customers page and no notes; Read-only analyst reads every view including Payouts but has no exports, settings or writes. Table in `CLAUDE.md`.
3. **The read-only analyst.** Sam Okafor, with memberships at Alder & Loom and Copper Finch Coffee so the third merchant is reachable in the persona selector.
4. **Cross-merchant requests return 404**, not 403, so another merchant's record ids are never confirmed to exist.
