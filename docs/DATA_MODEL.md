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
- The one stored derived number, `payout.amount_cents`, is verified against its movements at seed time, in tests, and on every detail read.

### Payment Health

`GET /api/payment-health` is computed per request from `payment_attempt`, `payment` and `payment_summary`; the rule and its constants live in `app/core/health.py` and nothing about it is stored.

- **Rate**: completed-attempt success, `succeeded / (succeeded + failed)`, in integer basis points rounded half-up. Pending attempts never enter a rate. Attempts are bucketed on `payment_attempt.created_at` by America/Chicago day and by the payment's channel, the same timestamp the Attempts tab filters on.
- **Baseline**: the same channel over the `BASELINE_DAYS` (30) Chicago days ending the day before the period starts. Its range is reported with the merchant's `history_starts` (the Chicago date of its first recorded attempt); the baseline is *partial* when history starts after the baseline's first day.
- **Rule**, per channel, never over pooled counts: fewer than `MIN_PERIOD_COMPLETED` (30) completed attempts in the period → `insufficient_volume`; fewer than `MIN_BASELINE_COMPLETED` (100) in the baseline → `no_baseline` when recorded history starts after the baseline's first day (there is nothing to compare against yet), otherwise `insufficient_volume`; with enough volume, `degraded` when the baseline rate minus the period rate is at least `DEGRADED_DROP_BP` (1000), else `normal`. Normal means no significant degradation was detected, never that every payment succeeded. The all-channels scope takes the worst per-channel verdict (degraded, then normal, then no_baseline, then insufficient_volume).
- **Trend**: one point per Chicago day of the period; a day with no completed attempt has no rate (a gap, never 0%), and a day with fewer than `LOW_VOLUME_DAY_COMPLETED` (10) is marked low volume. The worst day quoted as evidence is the lowest-rate day with at least that many completed attempts, falling back to any day with one.
- **Failure signals**: failed attempts in scope grouped by the recorded `failure_code`, most frequent first. The labels in `core/labels.py` (`FAILURE_CODE_LABELS`) mirror the seed's `DECLINE_CODES` table exactly, and `/api/meta` serves them as filter options.
- **Recovery** is counted per payment, never per attempt, over payments created in the period with at least one failed attempt: `recovered_within_window` when a succeeded attempt completed no later than `RECOVERY_WINDOW` (1 hour) after the payment's first attempt was created, `recovered_later` otherwise, `attempt_pending` when there is no success and the latest attempt is pending, else `unresolved`. Each payment's amount is counted once, in its state.
- **Unresolved** is exactly the Payments list's derived status `failed` for the same period and channel, so the drill-down totals agree.

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
