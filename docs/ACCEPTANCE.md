# Acceptance run — Definition of Done

Recorded run of the ten Definition of Done items from `docs/SPEC.md`, performed on 2026-10-05 against commit `0d3e8ff` plus the Phase 8 changes (this document, `tests/test_dod_09_make_test.py`, `tests/boundary/`, the payment-detail layout and timestamp polish).

Two environments were used:

- **Fresh clone.** The branch was cloned into an empty directory and driven only through the documented Makefile targets (`make setup`, `make reset`, `make run`, `make test`, `make acceptance`, `make check-boundary`). HTTP calls went through the Vite dev server on `:5173` so the `/api` proxy and the session cookie were exercised exactly as the browser uses them.
- **Working tree.** `make test` and `make check-boundary` were run again on the final Phase 8 tree before the commit.

The clock in every run is the seeded scenario clock, Monday 2026-10-05 09:12 CT (`2026-10-05T14:12:00Z`), read from `seed_meta`.

| # | Item | Result |
|---|---|---|
| 1 | Documented commands start the services and a seeded user reaches the portal | Pass |
| 2 | Search, filter, paginate, open a payment; list and detail agree | Pass |
| 3 | Another merchant's record by ID is denied by the backend | Pass |
| 4 | An allowed note persists after refresh and records the acting user | Pass |
| 5 | A payout's detail reconciles exactly to its movements; its CSV downloads | Pass |
| 6 | Each report export matches the merchant and the selected filters | Pass |
| 7 | Data survives an application restart | Pass |
| 8 | `make reset` reproduces the identical baseline | Pass |
| 9 | `make test` passes | Pass |
| 10 | A search of the codebase for the out-of-scope feature finds nothing | Pass |

## 1. Documented commands start the services and a seeded user reaches the portal

Commands (fresh clone):

```
git clone --branch claude/fintechco-app-8kzucz <repo> repo && cd repo
make setup        # venv, pinned Python deps, npm ci            -> "Setup complete." in 14 s
make reset        # delete db, reseed, print counts + checksum  -> checksum c8e3e8f2…bab1c9
make run          # API :8000 and Vite :5173 under one shell    -> both answering after 1 s
```

Evidence:

```
GET http://localhost:8000/api/ping            -> {"ok":true,"db":"ok"}
GET http://localhost:5173/                    -> 200
GET http://localhost:5173/api/ping (proxy)    -> 200
POST /api/dev/session {Maya Chen, Alder & Loom} -> 200, ftc_session cookie set
GET /api/session  -> Maya Chen | Alder & Loom | operations_manager | as_of 2026-10-05T14:12:00Z
GET /api/overview -> 200, greeting "Good morning", collected (last 7 days) 20,666,537 cents
```

`tests/test_dod_01_startup.py` (3 tests) repeats this in-process: Makefile targets and raw commands are present, a fresh seed plus persona sign-in reaches `/api/session`, `/api/meta` and `/api/overview`, and `/api/ping` reports a missing database honestly.

## 2. Search, filter, paginate and open a payment; list and detail agree

Commands: the Payments page as Maya Chen (Alder & Loom), reproduced over HTTP through the Vite proxy.

```
GET /api/payments?period=last_7_days                                 -> total 537, page_size 25
GET /api/payments?period=last_7_days&page=2                          -> 25 items, first id differs from page 1
GET /api/payments?period=last_30_days&status=failed&channel=website  -> total 35, every row status=failed and channel=website
GET /api/payments?period=last_30_days&q=AL-11404                     -> pay_gn3iaui67br66s, partially_refunded, 34,398 cents
GET /api/payments/pay_gn3iaui67br66s                                 -> 200, partially_refunded, 34,398 cents, 2 attempts
list and detail agree on status, amount and order reference          -> True
```

In the browser the same page shows the filter bar (search, period, status, channel, location, min and max amount), the active-period line "Showing last 7 days: Sep 29 – Oct 5, 2026", sortable headers with `aria-sort`, and the Attempts tab; opening AL-11404 shows the two attempts (Visa •••• 4242 declined for insufficient funds, Mastercard •••• 8812 succeeded), the $48.00 price-adjustment refund, the payout it was swept into and the seeded note.

`tests/test_dod_02_payments_list_and_detail.py` (26 tests) covers every filter and sort column against independent SQL, pagination bounds, the Attempts tab, the derived status for every payment, and the list/detail agreement for sampled payments of every merchant.

## 3. Requesting another merchant's record by ID is denied by the backend

Command: `make acceptance` → `tests/test_dod_03_cross_merchant.py` (15 tests passed).

For every detail route (payment, attempt, payout, customer, dispute) and every export that takes an id, a persona who holds the permission at one merchant requests a real id belonging to another merchant and receives `404 {"error": {"code": "not_found", ...}}`; the same id requested by its own merchant's persona is `200`. The payout case uses Sam Okafor signed in at Copper Finch requesting an Alder & Loom payout (404, the permission is held, the record is foreign); Priya Shah requesting the same payout is the role case (403, operations managers lack `payouts:read`). A note posted against a foreign payment is a 404 and writes nothing. The check order 401 → 403 → 404 is asserted on every route, and a route-walk test fails if any `/api/*` route other than ping, dev and session lacks `require()`.

## 4. An allowed investigation note persists after refresh and records the acting user

Commands (fresh clone, through the Vite proxy):

```
as Maya Chen:  POST /api/payments/pay_gn3iaui67br66s/notes {"body": "Restart check note."} -> 201, actor Maya Chen
               GET  /api/payments/pay_gn3iaui67br66s -> notes 1 -> 2, last body "Restart check note.", actor Maya Chen
(both servers stopped, API restarted alone)
as Jordan Ellis: GET /api/payments/pay_gn3iaui67br66s -> notes 2, last body "Restart check note.", actor Maya Chen, at 2026-10-05T06:14:41Z
                 GET /api/settings/activity?kind=note -> newest item: Maya Chen, "Restart check note."
```

The note is read back by a different user after a process restart, so it came from the database, not from anything cached in the browser or the first process. `tests/test_dod_04_notes.py` (5 tests) adds: the actor comes from the session, never from the request body; roles without `notes:write` get 403; validation rejects empty and over-long bodies.

## 5. A payout's detail reconciles exactly to its movements; its CSV downloads

Command: `make acceptance` → `tests/test_dod_05_payout_reconciliation.py` (5 tests passed).

- Every payout of every merchant (29 rows) satisfies `payout.amount_cents == SUM(balance_movement.amount_cents WHERE payout_id = id)` directly in the database.
- Every payout reachable by a persona with `payouts:read` reconciles again in the API response (`reconciled: true`, buckets collections + fees + refunds + disputes + adjustments equal the total) and in `GET /api/payouts/{id}/export.csv` (the `amount_cents` column sums to the payout total, one row per movement).
- The CSV has the documented headers, `amount_cents` and `amount_usd`, `*_chicago` timestamps, no totals row, `Content-Disposition: attachment`, and every download is recorded as an `export` activity.
- A payout whose stored amount is tampered with returns `500 reconciliation_mismatch` rather than a corrected number.

In the browser (Daniel Brooks, Alder & Loom) the largest payout's detail page shows "Reconciled to the cent" above the five buckets and lists its 581 movements with links to their payments; the Download CSV link returns 582 lines (header plus 581 movements). Jordan Ellis, who lacks `reports:financial`, sees the same reconciliation and no download link; Maya Chen gets the 403 state on Payouts.

## 6. Each report export matches the merchant and the selected filters

Command: `make acceptance` → `tests/test_dod_06_exports.py` (17 tests passed).

- The payment register for the whole window equals the Payments list for the same persona, row for row.
- Payment register and attempt export with six and five filter combinations (period presets and custom ranges, status, channel, amount range, search) across Maya (Alder & Loom), Priya (Juniper Trail) and Sam at Copper Finch: every CSV row satisfies the filters and belongs to the signed-in merchant, and the row set equals the paginated list drained to the end.
- Payout reconciliation export and refund register: row sets match the corresponding list queries; the refund register for `status=pending` returns exactly the three pending refunds.
- Permissions follow the matrix: operational reports need `reports:operational`, financial reports `reports:financial`; everyone else is 403.
- Every download is recorded as an `export` activity with the acting user and the filename.

In the browser the Reports page shows one card per report with its own filters kept in the URL, and each Download button returns a CSV named `<merchant-slug>_<report>_<from>_<to>.csv`.

## 7. Data survives an application restart

See item 4: a note written through the running app was read back, by another user, after `make run` was stopped and the API started again on the same database file. `tests/test_dod_07_persistence.py` (2 tests) repeats this in-process with two application instances over one database and also checks that the seeded data is byte-for-byte the same through a new instance.

## 8. `make reset` reproduces the identical baseline

Commands (fresh clone):

```
make reset   # run 1   checksum c8e3e8f26f983e82fda3dc6275e350aa1d57c8be8d1114e755dd5b7f30bab1c9
make reset   # run 2   checksum c8e3e8f26f983e82fda3dc6275e350aa1d57c8be8d1114e755dd5b7f30bab1c9
make reset   # run 3   checksum c8e3e8f26f983e82fda3dc6275e350aa1d57c8be8d1114e755dd5b7f30bab1c9
```

The checksum is SHA-256 over every table's rows ordered by primary key and matches the golden value in `tests/test_dod_08_reset_reproducible.py` (6 tests: golden match, two seeds agree, stored checksum recomputable, `seed_meta` carries the scenario clock and no wall-clock value, the CLI refuses to seed twice, the CLI prints counts and checksum only). Row counts: 3 merchants, 5 locations, 5 users, 6 memberships, 1,144 customers, 3,731 payments, 3,971 attempts, 139 refunds, 29 payouts, 7,395 balance movements, 8 disputes, 12 notes.

## 9. `make test` passes

Fresh clone:

```
make test
  cd backend && .venv/bin/pytest -q                  -> 228 passed in 45.57s
  cd frontend && npx tsc --noEmit -p tsconfig.json   -> clean
  cd frontend && npx vitest run                      -> Test Files 11 passed, Tests 43 passed
exit 0 (63 s)
```

Working tree at the Phase 8 commit: backend 228 passed in 52.28 s, `tsc` clean, Vitest 11 files and 44 tests passed (the frontend gained one format test in this phase). `tests/test_dod_09_make_test.py` (3 tests) pins the recipe lines of `make test` and keeps `tests/boundary/` out of the default pytest collection. `make acceptance` runs the Definition of Done suite verbosely: 82 passed.

## 10. A search of the codebase for the out-of-scope feature finds nothing

Command: `make check-boundary` → `tests/boundary/` (10 tests passed in 6.07 s), plus a repository-wide `grep`.

Scope of the scan: every `.py`, `.sql`, `.ts`, `.tsx`, `.css` and `.html` file under `backend/app` and `frontend/src`.

- `test_no_forbidden_vocabulary_in_application_source`: no hit for `payment health`, `success rate`/`success_rate`, `failure rate`/`failure_rate`, `decline rate`, `approval rate`, `authorization rate`, `health`, `trend`, `PH-142`, `coming soon`, `feature_flag` (case-insensitive, separators tolerated).
- `test_no_grouping_over_attempt_outcomes`: no `GROUP BY` clause anywhere in `backend/app` names `outcome` or `failure_code`.
- `test_no_route_paths_suggesting_performance_views`: no route path contains `health`, `metrics`, `stats`, `analytics`, `trend`, `performance` or `insights`.
- `test_no_get_response_carries_an_outcome_aggregate_key` (one run per persona, six personas): every JSON `GET` route is called as every persona with sample ids, and no key at any depth matches `rate|ratio|percent|share|health|trend|score|breakdown|by_outcome|by_failure|by_reason|outcome_count|failure_count|success_count|succeeded_count|failed_count|declin|approval|authori[sz]ation`.
- `test_every_guarded_get_route_was_reachable_by_some_persona`: the walk above actually reached every guarded `GET` route, so the key check covered the whole API.

A manual `grep -rniE` for the same vocabulary over the whole repository (all source, styles, SQL, HTML, JSON, Markdown and the Makefile, excluding `node_modules` and `.venv`) returns hits only in `docs/SPEC.md`, `docs/PLAN.md`, `CLAUDE.md` and `backend/tests/boundary/`, which necessarily contain the vocabulary in order to state and test the boundary. Those four locations are the documented exceptions; nothing under `backend/app`, `frontend/src`, `backend/tests/test_*.py` or `docs/DATA_MODEL.md` matches.

By construction, additionally: the Attempts endpoints return per-attempt rows only; no filter option carries a count; the Overview and `meta` responses carry no record counts; attention items are the closed enum `dispute_deadline | payout_in_transit | refund_pending` and their query never reads attempt rows (asserted in `tests/test_overview.py`); exports have no totals rows; the chart is a generic money-series primitive.
