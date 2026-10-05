# FinTechCo Business — Phased Implementation Plan

Source of truth: `docs/SPEC.md`. Conventions, layout, role matrix and guardrails: `CLAUDE.md`. One commit per phase; `make test` is green before each commit. If a requirement conflicts with something found along the way, stop and ask.

## Decisions the phases build on

- **Stack.** FastAPI + stdlib `sqlite3` with hand-written SQL and a `schema.sql` full of CHECK constraints and composite foreign keys; React + Vite + TypeScript with plain CSS and a hand-written SVG chart. Dependencies: Python `fastapi`, `uvicorn`, `httpx`, `pytest`, `tzdata`; Node `react`, `react-dom`, `react-router-dom` plus dev tooling (`vite`, `@vitejs/plugin-react`, `typescript`, types, `vitest`, `jsdom`). Nothing else without asking.
- **Demo clock.** Fixed at Monday 2026-10-05 09:12 America/Chicago; the seed covers the 30 days ending there (Sat Sep 5 to Mon Oct 5, Labor Day Sep 7 inside it). Every "as of", "next payout", "due in N days" and period preset hangs off that constant, so `make reset` is identical on any day and the Overview still feels live. Only the greeting uses the wall clock. One constant to move if the demo date changes.
- **Payment status is derived**, never stored: a `payment_summary` SQL view feeds list, detail, Overview, customer pages and the register export, so list and detail agree by construction.
- **Ledger.** `BalanceMovement` is a signed ledger; a payout sweeps unswept movements available before its cutoff and `payout.amount_cents == SUM(movements)` exactly, itemised as collections + fees + refunds + disputes/adjustments. Failed and pending attempts post nothing. Funds available and the next payout are derived from unswept movements.
- **Sessions.** Development-only persona selector → `POST /api/dev/session {user_id, merchant_id}` → 403 unless that exact membership exists → HMAC-signed HttpOnly cookie carrying only `membership_id`. Merchant and role are re-read from the membership on every request. Cross-merchant ids are 404. Every route declares `require(permission)`; a router-introspection test fails any route that does not.
- **Scoping.** `merchant_id` on every table including children, composite FKs `(parent_id, merchant_id)` with `foreign_keys=ON`, and every query function takes `merchant_id` first.
- **Boundary.** Attempts list paginates with `has_more` and no total; no facet counts; no `GROUP BY` over outcome or failure code; single-series money chart used only by Overview; closed attention-item enum; flat exports; `/api/ping` not `/api/health`; `make check-boundary` in `make test`.
- **Timezone.** UTC ISO 8601 in storage and on the wire; America/Chicago at filter, display and export boundaries through one helper per side.

## Phase 0 — Plan and guardrails on record (this step)
Deliverables: `CLAUDE.md`, `docs/PLAN.md`. Wait for approval of the plan and the defaults listed under Open questions.
Commit: `Add CLAUDE.md and phased implementation plan`

## Phase 1 — Scaffold and data model
Goal: both services start from the documented commands; the full schema exists; the app shell and design tokens are in place.
- `Makefile` (setup, seed, reset, run with a trap that stops both servers, test, check-boundary, acceptance), `.gitignore`, `backend/data/.gitkeep`, pinned `requirements.txt`, committed `package-lock.json`.
- `app/main.py` (`create_app()`, `/api/ping` reporting whether the DB exists, error handler `{"error": {code, message}}`), `core/config.py`, `core/clock.py`, `core/tz.py`, `core/money.py`, `core/ids.py`.
- `db/schema.sql`: all twelve entities plus `seed_meta`, CHECKs (currency, channel/location pairing, outcome/failure pairing, movement type/FK pairing), partial unique index for one succeeded attempt per payment, composite FKs, indexes on `(merchant_id, created_at)` and lookups, the `payment_summary` view. `db/connection.py` (per-request connection, WAL, `foreign_keys=ON`).
- `docs/DATA_MODEL.md`.
- Frontend scaffold: Vite + React + TS strict, `/api` proxy, `tokens.css` (warm white surfaces, dark ink, one teal accent, semantic status colours, `tabular-nums`), `AppShell` with left nav (Overview, Payments, Payouts, Customers, Disputes, Reports, Settings), top bar with merchant identity, the "Demo environment · Synthetic data" pill, route placeholders that render real page chrome, `lib/format.ts` (`formatCents`, `formatTimestamp`), Vitest smoke test, `tsc --noEmit`.
- Tests: schema (table set, money columns INTEGER with currency CHECK, `merchant_id` on every scoped table), `tz` (Chicago day bounds, DST days), `money` (fee rounding, negative formatting), boundary scan runs clean on the skeleton.
Verified: from a clean clone `make setup`, `make test` green, `make run` serves the shell and `/api/ping`.
Commit: `Scaffold backend, frontend and Makefile with the data model`

## Phase 2 — Deterministic seed
Goal: `make reset` produces the identical, fully reconciled baseline every time, with the variety the brief describes.
- `app/seed/`: `scenario.py` (merchants, locations, users, memberships, shopper name lists, priced catalogs, channel mixes, hour/weekday weights, decline codes with weights, refund and dispute reasons, payout schedules, the neutrally named concentration block), `generate.py` (pure `build_dataset()` over one `random.Random`), `write.py`, `verify.py` (invariants and reconciliation), `checksum.py`, `__main__.py`.
- Content: Alder & Loom (homeware catalog, website + mobile app + two stores, daily business-day payouts, ~2,400 payments / ~2,900 attempts), Juniper Trail Outfitters (website + one store, weekly Friday payouts, ~600 payments), Copper Finch Coffee (small menu prices, two shops, sparse order-ahead channel, days with zero volume in a channel, weekly Monday payouts, ~900 payments). Realistic outcomes with plausible decline reasons, retries on the same payment (same or different card), a few pending attempts in the minutes before the clock on online channels, full and partial refunds with reasons (a couple pending), eight disputes with staggered deadlines (one due within days), payouts `paid` and one `in_transit`, adjustments, ~15% guest payments, named repeat shoppers (Avery Stone, Morgan Lee, Taylor Reed) including an anchor payment with decline → retry → payout → partial refund → note, `avery.stone@example.com` as a distinct customer at Juniper, a handful of seeded notes by Maya, Jordan and Priya. Users per the brief plus the read-only analyst (see Open questions).
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
- `GET /api/payments` (search by id, order reference, customer name/email; filters date range in Chicago days, status, channel, location, amount range; sort whitelist; `page`/`page_size` with `total`), `GET /api/attempts` (outcome, period, channel, location, search; `has_more`, no total), `GET /api/payments/{id}` (payment, shopper, channel and location, masked method, attempts with recorded reasons, refund history, dispute tag, payout link, notes, and a timeline derived at read time: order received, each attempt with outcome and reason, settlement pending or funds available, included in payout, payout paid, refunds, dispute milestones, notes; future-dated events flagged upcoming), `POST /api/payments/{id}/notes` (`notes:write`, 1–2000 chars, actor from the session).
- Frontend: Payments page with Payments/Attempts tabs, URL-synced filter bar (date presets and custom range, status/outcome, channel, location, amount min/max parsed to cents without floats), debounced search, active-filter chips, sortable headers, pagination, skeleton/empty/error states, Export CSV button (wired in Phase 7). Payment detail with header, timeline, attempts table, refund history (no "Issue refund"), payout link gated by `can('payouts:read')`, customer link gated by `can('customers:read')`, note composer with saving/saved/error states for permitted roles and a read-only notice otherwise.
- Tests: DoD 2 (search, every filter cross-checked against SQL, stable disjoint pagination, list fields equal detail fields for a sample), DoD 4 (note persists, records the actor, visible through a fresh client, 403 for finance/analyst, 404 cross-merchant, 422 empty), DoD 7 (note survives a fresh app instance on the same file), anchor payment timeline order.
Commit: `Add payments list, attempts tab, payment detail timeline and investigation notes`

## Phase 5 — Payouts and reconciliation
Goal: payout list and detail reconcile exactly to the ledger; the constituent CSV downloads.
- `GET /api/payouts` (status and date-range filters, pagination, status rank then date desc) plus `summary {available_cents, pending_cents, next_payout {date, amount_cents}, as_of}`; `GET /api/payouts/{id}` (masked destination string, buckets, total, `reconciled`, every movement with payment/order links); `GET /api/payouts/{id}/export.csv` (`reports:financial`; one row per movement; records an `export` event). Reconciliation and the derived next payout live in `db/queries/payouts.py`; the timeline derivation written in Phase 4 lives in `db/queries/payments.py`.
- Frontend: Payouts list, "Funds available for payout" card (as-of label, never "balance"), upcoming payout card, detail with reconciliation table and Download CSV.
- Tests: DoD 5 (every payout of every merchant reconciles in DB, response and CSV; CSV row count equals movement count; Daniel 200, Maya 403, Priya 404).
Commit: `Add payouts with exact ledger reconciliation and movement CSV export`

## Phase 6 — Overview
Goal: a derived-only financial summary that agrees with the lists and stays inside the boundary.
- `GET /api/overview?period=last_7_days|last_30_days|month_to_date|custom&from&to`: greeting data, tiles with period/as-of labels (gross collected, refunds processed, funds available for payout, next payout), daily collected-volume series bucketed by Chicago day with zeros, recent payments, upcoming payout itemisation, attention items from the closed enum.
- Frontend: greeting ("Good morning, Maya" by wall-clock hour in CT) with merchant name, period selector in the URL, stat tiles, SVG `BarChart` (single money series, gridlines, text tooltips, accessible title, no navigation), recent payments, upcoming payout, attention list with permission-gated links.
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
- `tests/test_dod_09` (Makefile targets) and `test_dod_10` (boundary scan, route-path scan, forbidden-key walk over every GET response as every role, no `GROUP BY` over outcome/failure code, `BarChart` import allowlist).
- `docs/ACCEPTANCE.md` recording each of the ten checks with command, result and evidence, including the checksum comparison and the scan output with its documented scope (and the note that `docs/SPEC.md`, `docs/PLAN.md`, `CLAUDE.md` and the scan's own tests contain the vocabulary by necessity).
Commit: `Polish states and accessibility; record acceptance checklist run`

## Open questions (defaults in effect unless changed)

1. **Demo clock date.** Fixed at Mon 2026-10-05 09:12 CT. Say if the live demo should show a different date; it is one constant plus a reseed.
2. **Role matrix where the brief is silent.** Business administrator can add notes and run the operational exports; Operations manager can run the operational exports (payment register, attempt export) but has no Payouts pages (Overview tiles still show funds available and next payout); Finance manager can run all four exports but has no Customers or Disputes pages; Read-only analyst reads every view including Payouts but has no exports, settings or writes. Table in `CLAUDE.md`.
3. **The read-only analyst.** Named Sam Okafor, with memberships at Alder & Loom and Copper Finch Coffee so the third merchant is reachable in the persona selector.
4. **Cross-merchant requests return 404**, not 403, so another merchant's record ids are never confirmed to exist. Switch to 403 if the demo should visibly say "forbidden".
