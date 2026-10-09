# Data model

Authoritative DDL: `backend/app/db/schema.sql`. This page explains the rules the DDL encodes.

## Conventions

- Ids: TEXT, `<prefix>_` + 14 lowercase base-32 characters (`mer_`, `loc_`, `usr_`, `mem_`, `cus_`, `pay_`, `att_`, `ref_`, `po_`, `bm_`, `dp_`, `evt_`).
- `*_at`: UTC ISO 8601 `YYYY-MM-DDTHH:MM:SSZ` (lexicographically sortable). `*_date`: America/Chicago calendar date.
- Money: `amount_cents INTEGER` plus `currency TEXT CHECK (currency = 'USD')` on every money-bearing table.
- Scoping: every merchant-owned table carries `merchant_id`; children reference parents through composite `(parent_id, merchant_id)` foreign keys, enforced with `PRAGMA foreign_keys = ON`, so a child row can never belong to a different merchant than its parent.

## Tables

| Table | Scoped | Purpose and rules |
|---|:-:|---|
| `merchant` | – | The business using the portal. Payout schedule (`daily`, `weekly_friday`, `weekly_monday`) and a masked payout destination (label, last4, kind). |
| `location` | Y | Physical stores. Online payments have no location. |
| `app_user` | – | People who sign in. Seeded accounts only. |
| `membership` | Y | User × merchant × role. `UNIQUE (user_id, merchant_id)`. Roles: `business_admin`, `operations_manager`, `finance_manager`, `read_only_analyst`. |
| `customer` | Y | The merchant's shopper. `UNIQUE (merchant_id, email)`: the same email at two merchants is two unrelated rows. First payment and recent activity are derived, never stored. |
| `payment` | Y | The purchase intent: order reference, description, amount, channel (`website`, `mobile_app`, `in_store`), location (required exactly when `in_store`), customer or guest (`customer_id NULL`). No status column. |
| `payment_attempt` | Y | One execution of a payment: attempt number, masked method (`card`/`wallet`, brand, last4, wallet type), outcome (`succeeded`, `failed`, `pending`), `failure_code` + `failure_message` exactly when failed, `completed_at` exactly when not pending. At most one succeeded attempt per payment (partial unique index). |
| `refund` | Y | Links to the payment, never to an attempt. Amount, reason, status (`pending`, `succeeded`), `completed_at` exactly when succeeded. |
| `dispute` | Y | One per payment. Amount, reason, status (`needs_response`, `under_review`, `won`, `lost`), `opened_at`, `evidence_due_at`, `responded_at` (set from `under_review` on), `resolved_at` (set exactly for `won`/`lost`). |
| `payout` | Y | A sweep of available balance movements to the merchant's bank. Stored `amount_cents` must equal the sum of its movements. Status `in_transit` or `paid` (`paid_at` set exactly when paid). `UNIQUE (merchant_id, cutoff_at)`. |
| `balance_movement` | Y | The signed ledger (see below). `payout_id NULL` means not yet swept. |
| `note_event` | Y | Who did what, when. `kind = note`: an internal note on exactly one payment or dispute, with the acting user. `kind = export`: a CSV download (`export_name`, optional `payout_id`). |
| `seed_meta` | – | Key/value written by the seed: `as_of`, `rng_seed`, `window_start`, `window_end`, `checksum`. Never a wall-clock value. |

## Derived, never stored

- **Payment status** comes from the `payment_summary` view: a succeeded attempt exists → `refunded` if succeeded refunds equal the amount, `partially_refunded` if they are positive, otherwise `succeeded`; no succeeded attempt and the latest attempt is pending → `pending`; otherwise `failed`. Pending refunds do not change status. The view also exposes the method to display (succeeded attempt's, else latest), the payout containing the charge, the dispute, and the customer and location names. Every reader selects from it.
- **Timelines** (payment detail, dispute case history), **customer activity**, **payout itemisation**, **funds available**, the **next payout** and every **Overview total** are computed from the rows they summarise at read time.
- **Payment Health** (`app/core/health.py`, `GET /api/payment-health`) is computed at read time from attempts and payments:
  - *Success rate* is `succeeded / (succeeded + failed)` over attempts whose `created_at` is in the period, as integer basis points rounded half-up; pending attempts are counted but never in the denominator, and no completed attempts means no rate.
  - *Baseline* is the same scope over the 30 Chicago days before the period. A channel is *degraded* when its rate is at least 10 points below its baseline, and is evaluated only with at least 50 completed attempts in the period and 200 in the baseline.
  - *Recovery* is per payment, over payments whose `created_at` is in the period: a payment with a failed attempt is *affected*; it is *recovered* once any attempt succeeds (within one hour when the success completes within 3600 s of the first attempt), *in progress* while its latest attempt is pending, and *unresolved* when its latest attempt failed, which is exactly `payment_summary.status = 'failed'`. Each payment's amount is counted once.
- The one stored derived number, `payout.amount_cents`, is verified against its movements at seed time, in tests, and on every detail read.

## Ledger

`balance_movement.amount_cents` carries the sign and the type fixes it:

| Type | Sign | Source references | Posted at | Available at |
|---|:-:|---|---|---|
| `charge` | + | payment, attempt | attempt `completed_at` | posted + 2 days |
| `fee` | − | payment, attempt | attempt `completed_at` | posted + 2 days |
| `refund` | − | payment, refund | refund `completed_at` | immediately |
| `dispute_reversal` | − | payment, dispute | dispute `opened_at` | immediately |
| `dispute_fee` | − (1500) | payment, dispute | dispute `opened_at` | immediately |
| `dispute_reinstatement` | + | payment, dispute | dispute `resolved_at` (won) | immediately |
| `adjustment` | ± | none | as seeded | immediately |

Fees: online channels 2.9% + 30¢, in-store 2.7% + 5¢, basis-point share rounded half-up in integer arithmetic. Failed and pending attempts post nothing; pending refunds post nothing.

## Payouts

A cutoff is 00:00 America/Chicago on each of the merchant's payout days (daily on business days, weekly Friday, weekly Monday). A cutoff that falls on a weekend or holiday (Labor Day 2026-09-07) moves to the next business day. Each cutoff sweeps every unswept movement with `available_at < cutoff_at`; an empty sweep creates no payout. The payout is sent at 06:00 CT the same day (`in_transit`) and arrives at 09:00 CT the next business day (`paid`).

Reconciliation identity, checked everywhere: `payout.amount_cents == SUM(amount_cents) OVER movements WHERE payout_id = payout.id`, itemised as collections (`charge`) + fees + refunds + disputes and adjustments.

Funds available for payout = unswept movements with `available_at <= now`; pending = unswept with `available_at > now`. The next payout is derived: the next cutoff after `now`, carrying the funds currently available, labelled as an estimate as of now. It is never described as a bank balance.

## Clock

`seed_meta.as_of` is the reporting clock. `app/core/clock.py: now()` reads it; everything a merchant sees as "now" derives from it. Writes (notes, exports) and session expiry use the wall clock through `clock.wall_now()`.
