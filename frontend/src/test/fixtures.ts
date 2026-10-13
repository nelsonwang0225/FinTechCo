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

export const FAILURE_SIGNALS = {
  items: [
    { value: "insufficient_funds", label: "Insufficient funds" },
    { value: "issuer_unavailable", label: "Issuer unavailable" },
  ],
};

const stats = (succeeded: number, failed: number, pending: number, success_rate_bp: number | null) => ({
  succeeded,
  failed,
  pending,
  completed: succeeded + failed,
  success_rate_bp,
});

/** Alder & Loom, last 7 days: the app checkout is degraded, the other two channels are not. */
export const HEALTH: PaymentHealth = {
  period: PERIOD,
  baseline_period: { preset: "custom", label: "Custom range", from_date: "2026-08-30", to_date: "2026-09-28", range_label: "Aug 30 – Sep 28, 2026" },
  rules: { baseline_days: 30, degraded_drop_bp: 1000, min_period_completed: 50, min_baseline_completed: 200, low_volume_day_completed: 10, recovery_window_minutes: 60 },
  summary: { channel: null, channel_label: "All channels", period: stats(504, 85, 2, 8557), baseline: stats(1910, 175, 1, 9161), change_bp: -604 },
  attention: { verdict: "degraded", degraded_channels: ["mobile_app"] },
  channels: [
    { channel: "website", channel_label: "Website", period: stats(246, 20, 1, 9248), baseline: stats(969, 91, 1, 9142), change_bp: 106, verdict: "not_degraded", verdict_label: "No significant degradation" },
    { channel: "mobile_app", channel_label: "Mobile app", period: stats(134, 52, 1, 7204), baseline: stats(572, 58, 0, 9079), change_bp: -1875, verdict: "degraded", verdict_label: "Degraded" },
    { channel: "in_store", channel_label: "In store", period: stats(119, 18, 0, 8686), baseline: stats(362, 33, 0, 9165), change_bp: -479, verdict: "not_degraded", verdict_label: "No significant degradation" },
  ],
  trend: [
    { day: "2026-10-01", succeeded: 80, failed: 21, pending: 0, completed: 101, success_rate_bp: 7921, low_volume: false },
    { day: "2026-10-02", succeeded: 5, failed: 3, pending: 0, completed: 8, success_rate_bp: 6250, low_volume: true },
    { day: "2026-10-03", succeeded: 0, failed: 0, pending: 1, completed: 0, success_rate_bp: null, low_volume: false },
    { day: "2026-10-04", succeeded: 88, failed: 6, pending: 0, completed: 94, success_rate_bp: 9362, low_volume: false },
  ],
  failure_signals: [
    { code: "issuer_unavailable", label: "Issuer unavailable", attempts: 31, payments: 28 },
    { code: "insufficient_funds", label: "Insufficient funds", attempts: 20, payments: 19 },
  ],
  recovery: {
    currency: "USD",
    affected_payments: 70,
    affected_cents: 1234567,
    failed_attempts: 85,
    recovered_payments: 58,
    recovered_cents: 1000000,
    recovered_within_window_payments: 57,
    recovered_within_window_cents: 990000,
    unresolved_payments: 12,
    unresolved_cents: 234567,
    retry_pending_payments: 0,
    retry_pending_cents: 0,
  },
  unresolved_payments: [
    {
      id: "pay_unresolved0001",
      order_reference: "AL-13020",
      created_at: "2026-10-01T22:05:10Z",
      amount_cents: 18999,
      currency: "USD",
      status: "failed",
      status_label: "Failed",
      channel: "mobile_app",
      channel_label: "Mobile app",
      location: null,
      customer: { id: "cus_unresolved0001", full_name: "Robin Vale", email: "robin.vale@example.com", reference: "AL-C-0101" },
      method: { type: "card", card_brand: "visa", card_last4: "4242", wallet_type: null, label: "Visa •••• 4242" },
      refunded_cents: 0,
      net_cents: 18999,
      dispute_id: null,
      dispute_status: null,
    },
  ],
  unresolved_total: 12,
};
