# FinTechCo Business — Baseline Application Brief

You are building the baseline application for a sales demo: FinTechCo Business, a merchant payments portal. It must feel like an established product a business uses daily. A later feature (PH-142, "Payment Health") will be added live on top of it, so this baseline must deliberately NOT contain that feature. Everything here is fictional and synthetic.

## FIRST ACTIONS, BEFORE ANY CODE

1. Save this entire brief as docs/SPEC.md.
2. Create CLAUDE.md at the repo root: stack and layout, the exact commands to run, seed, reset, and test, conventions, and a GUARDRAILS section (synthetic data only; no new dependencies without asking; money stays integer cents; merchant scoping enforced in the backend; all acceptance checks in docs/SPEC.md must pass).
3. Propose a phased implementation plan and wait for my approval. Suggested phases: scaffold and data model; seed; API with auth and scoping; Payments and payment detail; Payouts and reconciliation; Overview; Customers, Disputes, Reports, Settings; polish and acceptance run. Commit at the end of each phase with a clear message.

## PRODUCT

FinTechCo Business: a workspace for merchants to manage customer payments, investigate transactions, track payouts, and handle account operations. Positioning: "Manage payments, resolve transaction issues, and track money reaching your business." The merchant is FinTechCo's business customer; the shopper is the merchant's customer. This is a merchant operations workspace, not a consumer banking app.

## STACK

* Frontend: React + Vite + TypeScript, single app.
* Backend: Python FastAPI, single service.
* Database: SQLite, local file.
* Tests: pytest for the API (this is where acceptance checks live), plus a minimal frontend smoke test.
* Makefile or package scripts: make setup, make seed, make reset, make run (starts both), make test.

## HARD DATA RULES

* Money is integer cents with explicit currency, USD only.
* Channel (website, mobile app, in-store) is separate from payment method (card, wallet; store masked details only).
* A Payment is the customer's purchase intent; a PaymentAttempt is one execution with its own outcome and recorded failure reason. One payment can have a failed attempt then a successful retry. Never collapse attempts into duplicate purchases.
* Refunds and disputes are separate records linked to payments; a refund never rewrites an attempt outcome.
* Every displayed total is derived from the same records shown on detail pages. A payout reconciles exactly to its balance movements.
* One documented reporting timezone (America/Chicago) used consistently across overview, filters, exports.
* Seed is deterministic (fixed RNG seed); make reset returns the identical baseline every time.

## ENTITIES

Merchant, Location, User, Membership (user to merchant with role), Customer, Payment, PaymentAttempt, Refund, Payout, BalanceMovement, Dispute, NoteEvent (who did what, when).

## SEED DATA

* Three merchants: Alder & Loom (homeware retailer; website, mobile app, two stores; the primary demo account), Juniper Trail Outfitters (outdoor gear; online plus one store; used for isolation checks), Copper Finch Coffee (coffee shops; small payments, some low-volume channel and period combinations).
* Users: Maya Chen (Alder & Loom, Operations Manager), Daniel Brooks (Alder & Loom, Finance Manager), Jordan Ellis (Alder & Loom, Business Administrator), Priya Shah (Juniper, Operations Manager), plus one read-only analyst. Shoppers use invented names (Avery Stone, Morgan Lee, Taylor Reed) and example.com emails; guest shoppers allowed.
* Volume: a few thousand payment attempts across a fixed 30-day window, with realistic variety: successes, recorded failures with plausible decline reasons, retries, pending attempts, refunds (full and partial, with reasons), payouts with reconciling movements, a handful of disputes with deadlines, and quieter periods.
* Engineer one deliberate concentration of failures in one channel and time window for Alder & Loom. It is a synthetic test scenario, not a claim about normal failure rates. Do not surface or annotate it anywhere in the UI; it simply exists in the data.

## SECTIONS

(left navigation: Overview, Payments, Payouts, Customers, Disputes, Reports, Settings)

Depth is uneven on purpose: Payments, payment detail, access enforcement, and Overview get the most care. Every visible page works; no "coming soon" screens.

**Overview:** "Good morning, Maya" with merchant name. Compact financial summary for a selected period: gross collected, refunds processed, funds available for payout, next scheduled payout, each with a period or as-of label. A simple collected-volume chart, recent payments, upcoming payout, and a short attention list (e.g., a dispute nearing its deadline). All values derived from the database. Explicitly exclude: success-rate trends, failure-reason analytics, channel health indicators of any kind.

**Payments:** searchable, sortable, paginated table: payment ID, order reference, customer, amount, channel, masked method, status, timestamps, link to detail. Filters: date range, status or outcome, channel, location, amount. Search by ID, order reference, or customer. Two tabs: Payments and Attempts. The Attempts tab lists attempt-level records and already supports filtering by outcome, period, and channel.

**Payment detail:** full record with amount, order reference, shopper, channel and location, masked method, and a chronological event timeline that reflects the actual seeded events (e.g., order received, first attempt declined with reason, retry succeeded, pending settlement, included in payout). Shows recorded failure reason, associated attempts, refund history, payout link where applicable. One real write action: authorized users add an internal investigation note that persists and records the acting user. Refund execution is out of scope: show refund history, no "Issue refund" button.

**Payouts:** list with amount, status, expected date, masked destination ("Alder & Loom, Operating account •••• 4821, external bank account, demo record"). Detail view itemizes collections, fees, refunds and adjustments, and the resulting amount, reconciling exactly. CSV download of a payout's constituent records. Do not label the available balance as a bank balance.

**Customers:** directory of shoppers with name, synthetic email, reference, first payment, recent activity; detail page links to their payments and refunds. Customer records are merchant-scoped; the same email under two merchants must never cross-link.

**Disputes:** small seeded queue: disputed amount, linked payment, reason, status, response deadline. Detail shows case history; authorized users can add internal notes. Otherwise read-only; no evidence submission, no simulated resolutions.

**Reports:** four working CSV exports honoring current filters and merchant scope: payment register, payment-attempt export (with outcomes and recorded reasons), payout reconciliation, refund register. No report builder, no analytics dashboard.

**Settings:** tabs for Business profile, Team, Activity. Roles: Business administrator (settings, team, operational views), Operations manager (payments, customers, disputes, notes), Finance manager (payments, payouts, reconciliation, financial exports), Read-only analyst (approved views, no writes). Seeded accounts only; no invitations or password recovery. A development-only persona selector establishes the session, visibly separate from product UI; it can never switch a user into a merchant they do not belong to. Permissions are enforced in the backend on every endpoint, not by hiding buttons.

## DESIGN

Premium financial-operations workspace: calm, clear, information-dense without crowding. Persistent left nav, compact top bar with merchant identity, clear page titles. Warm white or light neutral surfaces, dark text, one restrained accent, semantic colors only for genuine statuses. Readable sans-serif; right-aligned, tabular numerals in money columns. Strong tables: filters, sensible widths, readable timestamps. Real loading, empty, error, and saved states. Keyboard focus visible; status conveyed by text, not color alone. FinTechCo branding only. A discreet persistent indicator: "Demo environment · Synthetic data". The payment list and detail pages must feel as finished as the overview.

## HARD BOUNDARY, DO NOT BUILD

No part of Payment Health may exist in this codebase: no completed-attempt success or failure summary, no aggregated failure-reason breakdown, no success or failure trend over time, no payment-performance view or health indicator, no drill-down from aggregates into attempts, no dormant endpoint, hidden page, feature flag, or "coming soon" panel containing any of it. Reusable primitives are welcome and expected: tables, a chart component, data-access helpers, auth, test utilities. The feature itself must remain genuinely unbuilt.

## DEFINITION OF DONE

Finish by running this checklist yourself and reporting each result:

1. Documented commands start the services and a seeded user reaches the portal.
2. Search, filter, paginate, and open a payment; list and detail agree.
3. Requesting another merchant's record by ID is denied by the backend.
4. An allowed investigation note persists after refresh and records the acting user.
5. A payout's detail reconciles exactly to its movements; its CSV downloads.
6. Each report export matches the merchant and the selected filters.
7. Data survives an application restart.
8. make reset reproduces the identical baseline.
9. make test passes.
10. A search of the codebase for Payment Health functionality finds nothing.

Work phase by phase against the approved plan. Run the tests as you go. If a requirement conflicts with something you find, stop and ask rather than assuming.
