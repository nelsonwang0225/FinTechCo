import type { PaymentHealth } from "../api/payment-health-types";
import type { AttemptListResponse, PaymentDetail, PaymentListResponse } from "../api/payments-types";
import type { Meta } from "../api/types";

export const META: Meta = {
  channels: [
    { value: "website", label: "Website" },
    { value: "mobile_app", label: "Mobile app" },
    { value: "in_store", label: "In store" },
  ],
  payment_statuses: [
    { value: "succeeded", label: "Succeeded" },
    { value: "pending", label: "Pending" },
    { value: "failed", label: "Failed" },
    { value: "partially_refunded", label: "Partially refunded" },
    { value: "refunded", label: "Refunded" },
  ],
  attempt_outcomes: [
    { value: "succeeded", label: "Succeeded" },
    { value: "failed", label: "Failed" },
    { value: "pending", label: "Pending" },
  ],
  refund_statuses: [
    { value: "pending", label: "Pending" },
    { value: "succeeded", label: "Succeeded" },
  ],
  refund_reasons: [{ value: "price_adjustment", label: "Price adjustment" }],
  dispute_statuses: [
    { value: "needs_response", label: "Needs response" },
    { value: "under_review", label: "Under review" },
    { value: "won", label: "Won" },
    { value: "lost", label: "Lost" },
  ],
  dispute_reasons: [
    { value: "fraudulent", label: "Fraudulent" },
    { value: "product_not_received", label: "Product not received" },
  ],
  payout_statuses: [
    { value: "in_transit", label: "In transit" },
    { value: "paid", label: "Paid" },
  ],
  period_presets: [
    { value: "last_7_days", label: "Last 7 days" },
    { value: "last_30_days", label: "Last 30 days" },
    { value: "month_to_date", label: "Month to date" },
    { value: "custom", label: "Custom range" },
  ],
  default_period: "last_7_days",
  locations: [
    { id: "loc_fultonmarket01", name: "Fulton Market", address_line: "815 W Fulton Market", city: "Chicago", state: "IL" },
    { id: "loc_lincolnpark001", name: "Lincoln Park", address_line: "2140 N Halsted St", city: "Chicago", state: "IL" },
  ],
  timezone: "America/Chicago",
};

export const PERIOD = { preset: "last_7_days", label: "Last 7 days", from_date: "2026-09-29", to_date: "2026-10-05", range_label: "Sep 29 – Oct 5, 2026" };

export const PAYMENTS: PaymentListResponse = {
  items: [
    {
      id: "pay_anchor00000001",
      order_reference: "AL-11404",
      created_at: "2026-09-22T19:11:37Z",
      amount_cents: 34398,
      currency: "USD",
      status: "partially_refunded",
      status_label: "Partially refunded",
      channel: "website",
      channel_label: "Website",
      location: null,
      customer: { id: "cus_taylor00000001", full_name: "Taylor Reed", email: "taylor.reed@example.com", reference: "AL-C-0003" },
      method: { type: "card", card_brand: "mastercard", card_last4: "8812", wallet_type: null, label: "Mastercard •••• 8812" },
      refunded_cents: 4800,
      net_cents: 29598,
      dispute_id: null,
      dispute_status: null,
    },
    {
      id: "pay_guest000000001",
      order_reference: "AL-12001",
      created_at: "2026-10-03T16:20:40Z",
      amount_cents: 5600,
      currency: "USD",
      status: "succeeded",
      status_label: "Succeeded",
      channel: "in_store",
      channel_label: "In store",
      location: { id: "loc_fultonmarket01", name: "Fulton Market" },
      customer: null,
      method: { type: "card", card_brand: "visa", card_last4: "1111", wallet_type: null, label: "Visa •••• 1111" },
      refunded_cents: 0,
      net_cents: 5600,
      dispute_id: null,
      dispute_status: null,
    },
  ],
  page: 1,
  page_size: 25,
  total: 2,
  period: PERIOD,
};

export const ATTEMPTS: AttemptListResponse = {
  items: [
    {
      id: "att_anchor00000001",
      payment_id: "pay_anchor00000001",
      attempt_number: 1,
      created_at: "2026-09-22T19:11:37Z",
      completed_at: "2026-09-22T19:11:39Z",
      outcome: "failed",
      outcome_label: "Failed",
      failure_code: "insufficient_funds",
      failure_message: "Insufficient funds",
      method: { type: "card", card_brand: "visa", card_last4: "4242", wallet_type: null, label: "Visa •••• 4242" },
      order_reference: "AL-11404",
      amount_cents: 34398,
      currency: "USD",
      channel: "website",
      channel_label: "Website",
      location: null,
      customer: { id: "cus_taylor00000001", full_name: "Taylor Reed", email: "taylor.reed@example.com", reference: "AL-C-0003" },
    },
  ],
  page: 1,
  page_size: 25,
  total: 1,
  period: PERIOD,
};

export const ANCHOR_DETAIL: PaymentDetail = {
  id: "pay_anchor00000001",
  order_reference: "AL-11404",
  description: "Linen duvet cover, oat; Stoneware mug set of four",
  created_at: "2026-09-22T19:11:37Z",
  amount_cents: 34398,
  currency: "USD",
  status: "partially_refunded",
  status_label: "Partially refunded",
  channel: "website",
  channel_label: "Website",
  location: null,
  customer: { id: "cus_taylor00000001", full_name: "Taylor Reed", email: "taylor.reed@example.com", reference: "AL-C-0003" },
  method: { type: "card", card_brand: "mastercard", card_last4: "8812", wallet_type: null, label: "Mastercard •••• 8812" },
  refunded_cents: 4800,
  net_cents: 29598,
  succeeded_at: "2026-09-22T19:14:53Z",
  funds_available_at: "2026-09-24T19:14:53Z",
  payout: { id: "po_anchor000000001", status: "paid", status_label: "Paid", cutoff_at: "2026-09-25T05:00:00Z", sent_at: "2026-09-25T11:00:00Z", paid_at: "2026-09-28T14:00:00Z" },
  dispute: null,
  attempts: [
    {
      id: "att_anchor00000001",
      payment_id: "pay_anchor00000001",
      attempt_number: 1,
      created_at: "2026-09-22T19:11:37Z",
      completed_at: "2026-09-22T19:11:39Z",
      outcome: "failed",
      outcome_label: "Failed",
      failure_code: "insufficient_funds",
      failure_message: "Insufficient funds",
      method: { type: "card", card_brand: "visa", card_last4: "4242", wallet_type: null, label: "Visa •••• 4242" },
    },
    {
      id: "att_anchor00000002",
      payment_id: "pay_anchor00000001",
      attempt_number: 2,
      created_at: "2026-09-22T19:14:51Z",
      completed_at: "2026-09-22T19:14:53Z",
      outcome: "succeeded",
      outcome_label: "Succeeded",
      failure_code: null,
      failure_message: null,
      method: { type: "card", card_brand: "mastercard", card_last4: "8812", wallet_type: null, label: "Mastercard •••• 8812" },
    },
  ],
  refunds: [
    {
      id: "ref_anchor00000001",
      amount_cents: 4800,
      currency: "USD",
      reason: "price_adjustment",
      reason_label: "Price adjustment",
      status: "succeeded",
      status_label: "Succeeded",
      created_at: "2026-09-26T15:05:21Z",
      completed_at: "2026-09-26T15:12:00Z",
    },
  ],
  notes: [
    { id: "evt_anchor00000001", body: "Customer called about a second charge.", created_at: "2026-09-26T15:40:12Z", actor: { id: "usr_maya0000000001", full_name: "Maya Chen" } },
  ],
  timeline: [
    { kind: "order_received", at: "2026-09-22T19:11:37Z", title: "Order received", detail: "AL-11404 · Website", upcoming: false, amount_cents: 34398, ref_id: null },
    { kind: "attempt_failed", at: "2026-09-22T19:11:39Z", title: "Attempt 1 declined", detail: "Insufficient funds · Visa •••• 4242", upcoming: false, amount_cents: null, ref_id: "att_anchor00000001" },
    { kind: "attempt_succeeded", at: "2026-09-22T19:14:53Z", title: "Attempt 2 succeeded", detail: "Mastercard •••• 8812", upcoming: false, amount_cents: 34398, ref_id: "att_anchor00000002" },
    { kind: "funds_available", at: "2026-09-24T19:14:53Z", title: "Funds available for payout", detail: "$343.98 collected, less fees", upcoming: false, amount_cents: null, ref_id: null },
    { kind: "payout_included", at: "2026-09-25T05:00:00Z", title: "Included in payout", detail: "Payout po_anchor000000001", upcoming: false, amount_cents: null, ref_id: "po_anchor000000001" },
    { kind: "refund_succeeded", at: "2026-09-26T15:12:00Z", title: "Refund of $48.00 completed", detail: "Price adjustment", upcoming: false, amount_cents: -4800, ref_id: "ref_anchor00000001" },
    { kind: "note", at: "2026-09-26T15:40:12Z", title: "Note by Maya Chen", detail: "Customer called about a second charge.", upcoming: false, amount_cents: null, ref_id: "evt_anchor00000001" },
    { kind: "payout_paid", at: "2026-09-28T14:00:00Z", title: "Payout paid", detail: "Arrived at the bank account", upcoming: false, amount_cents: null, ref_id: "po_anchor000000001" },
  ],
};

const SUMMARY_ZERO = {
  succeeded: 0, failed: 0, pending: 0, completed: 0, success_rate_bp: null, baseline_succeeded: 0, baseline_failed: 0, baseline_completed: 0,
  baseline_success_rate_bp: null, change_bp: null,
};

/** Payment Health for Alder & Loom, last 7 days, all channels: the seeded mobile-app incident (figures from the seed). */
export const HEALTH: PaymentHealth = {
  as_of: "2026-10-05T14:12:00Z",
  period: PERIOD,
  baseline: { from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026" },
  channel: null,
  channel_label: "All channels",
  rules: { baseline_days: 30, degraded_drop_bp: 1000, min_completed_attempts: 20, low_volume_day_attempts: 10, recovery_window_seconds: 3600 },
  attention: {
    status: "degraded",
    degraded: [
      { channel: "mobile_app", channel_label: "Mobile app", success_rate_bp: 7204, baseline_success_rate_bp: 9079, change_bp: -1875, failed_attempts: 52, unresolved_payments: 16 },
    ],
    insufficient_volume_channels: [],
  },
  attempts: {
    succeeded: 499, failed: 90, pending: 2, completed: 589, success_rate_bp: 8472, baseline_succeeded: 1903, baseline_failed: 182, baseline_completed: 2085,
    baseline_success_rate_bp: 9127, change_bp: -655,
  },
  trend: [
    { date: "2026-09-29", succeeded: 75, failed: 4, pending: 0, completed: 79, success_rate_bp: 9494, low_volume: false, partial: false },
    { date: "2026-09-30", succeeded: 89, failed: 7, pending: 0, completed: 96, success_rate_bp: 9271, low_volume: false, partial: false },
    { date: "2026-10-01", succeeded: 84, failed: 38, pending: 0, completed: 122, success_rate_bp: 6885, low_volume: false, partial: false },
    { date: "2026-10-02", succeeded: 81, failed: 18, pending: 0, completed: 99, success_rate_bp: 8182, low_volume: false, partial: false },
    { date: "2026-10-03", succeeded: 96, failed: 9, pending: 0, completed: 105, success_rate_bp: 9143, low_volume: false, partial: false },
    { date: "2026-10-04", succeeded: 62, failed: 13, pending: 0, completed: 75, success_rate_bp: 8267, low_volume: false, partial: false },
    { date: "2026-10-05", succeeded: 12, failed: 1, pending: 2, completed: 13, success_rate_bp: 9231, low_volume: false, partial: true },
  ],
  channels: [
    { ...SUMMARY_ZERO, channel: "website", channel_label: "Website", succeeded: 246, failed: 20, pending: 1, completed: 266, success_rate_bp: 9248,
      baseline_succeeded: 969, baseline_failed: 91, baseline_completed: 1060, baseline_success_rate_bp: 9142, change_bp: 106, assessment: "not_degraded",
      assessment_label: "No significant change" },
    { ...SUMMARY_ZERO, channel: "mobile_app", channel_label: "Mobile app", succeeded: 134, failed: 52, pending: 1, completed: 186, success_rate_bp: 7204,
      baseline_succeeded: 572, baseline_failed: 58, baseline_completed: 630, baseline_success_rate_bp: 9079, change_bp: -1875, assessment: "degraded",
      assessment_label: "Degraded" },
    { ...SUMMARY_ZERO, channel: "in_store", channel_label: "In store", succeeded: 119, failed: 18, pending: 0, completed: 137, success_rate_bp: 8686,
      baseline_succeeded: 362, baseline_failed: 33, baseline_completed: 395, baseline_success_rate_bp: 9165, change_bp: -479, assessment: "not_degraded",
      assessment_label: "No significant change" },
  ],
  failure_signals: [
    { failure_code: "issuer_unavailable", label: "Issuer unavailable", failed_attempts: 32 },
    { failure_code: "do_not_honor", label: "Do not honor", failed_attempts: 17 },
    { failure_code: "insufficient_funds", label: "Insufficient funds", failed_attempts: 13 },
  ],
  recovery: {
    affected_payments: 83, affected_cents: 2334007, recovered_payments: 55, recovered_cents: 1571734, recovered_within_window_payments: 55,
    recovered_within_window_cents: 1571734, unresolved_payments: 28, unresolved_cents: 762273, retry_pending_payments: 0, retry_pending_cents: 0, currency: "USD",
  },
  unresolved: [
    { id: "pay_unresolved00001", order_reference: "AL-12009", created_at: "2026-09-29T15:02:00Z", amount_cents: 12900, currency: "USD", channel: "website",
      channel_label: "Website", attempt_count: 1, last_failure_code: "insufficient_funds", last_failure_label: "Insufficient funds",
      customer: { id: "cus_taylorreed00001", full_name: "Taylor Reed", email: "taylor.reed@example.com", reference: "AL-C-0001" } },
    { id: "pay_unresolved00002", order_reference: "AL-12183", created_at: "2026-10-01T22:40:00Z", amount_cents: 21800, currency: "USD", channel: "mobile_app",
      channel_label: "Mobile app", attempt_count: 2, last_failure_code: "issuer_unavailable", last_failure_label: "Issuer unavailable", customer: null },
  ],
};

/** A period with no completed attempts at all. */
export const HEALTH_EMPTY: PaymentHealth = {
  ...HEALTH,
  attention: { status: "no_completed_attempts", degraded: [], insufficient_volume_channels: [] },
  attempts: SUMMARY_ZERO,
  trend: HEALTH.trend.map((d) => ({ ...d, succeeded: 0, failed: 0, pending: 0, completed: 0, success_rate_bp: null, low_volume: true })),
  channels: [],
  failure_signals: [],
  recovery: { ...HEALTH.recovery, affected_payments: 0, affected_cents: 0, recovered_payments: 0, recovered_cents: 0, recovered_within_window_payments: 0,
    recovered_within_window_cents: 0, unresolved_payments: 0, unresolved_cents: 0 },
  unresolved: [],
};
