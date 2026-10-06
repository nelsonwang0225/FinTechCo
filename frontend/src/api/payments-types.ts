// Wire types for payments, attempts and payment detail. Money is integer cents; timestamps are UTC ISO strings.
import type { ListResponse } from "./types";

export interface PeriodInfo {
  preset: string;
  label: string;
  from_date: string;
  to_date: string;
  range_label: string;
}

export interface MethodInfo {
  type: "card" | "wallet";
  card_brand: string;
  card_last4: string;
  wallet_type: string | null;
  label: string;
}

export interface CustomerRef {
  id: string;
  full_name: string;
  email: string;
  reference: string;
}

export interface LocationRef {
  id: string;
  name: string;
}

export type PaymentStatus = "succeeded" | "pending" | "failed" | "partially_refunded" | "refunded";
export type Channel = "website" | "mobile_app" | "in_store";
export type AttemptOutcome = "succeeded" | "failed" | "pending";

export interface PaymentListItem {
  id: string;
  order_reference: string;
  created_at: string;
  amount_cents: number;
  currency: string;
  status: PaymentStatus;
  status_label: string;
  channel: Channel;
  channel_label: string;
  location: LocationRef | null;
  customer: CustomerRef | null;
  method: MethodInfo | null;
  refunded_cents: number;
  net_cents: number;
  dispute_id: string | null;
  dispute_status: string | null;
}

export interface PaymentListResponse extends ListResponse<PaymentListItem> {
  /** Payment amount summed over every match, not just this page. */
  total_amount_cents: number;
  currency: string;
  period: PeriodInfo;
}

export interface AttemptItem {
  id: string;
  payment_id: string;
  attempt_number: number;
  created_at: string;
  completed_at: string | null;
  outcome: AttemptOutcome;
  outcome_label: string;
  failure_code: string | null;
  failure_message: string | null;
  method: MethodInfo;
}

export interface AttemptListItem extends AttemptItem {
  order_reference: string;
  amount_cents: number;
  currency: string;
  channel: Channel;
  channel_label: string;
  location: LocationRef | null;
  customer: CustomerRef | null;
}

export interface AttemptListResponse extends ListResponse<AttemptListItem> {
  period: PeriodInfo;
}

export interface RefundItem {
  id: string;
  amount_cents: number;
  currency: string;
  reason: string;
  reason_label: string;
  status: "pending" | "succeeded";
  status_label: string;
  created_at: string;
  completed_at: string | null;
}

export interface DisputeTag {
  id: string;
  status: "needs_response" | "under_review" | "won" | "lost";
  status_label: string;
  reason: string;
  reason_label: string;
  amount_cents: number;
  currency: string;
  opened_at: string;
  evidence_due_at: string;
  responded_at: string | null;
  resolved_at: string | null;
}

export interface PayoutRef {
  id: string;
  status: "in_transit" | "paid";
  status_label: string;
  cutoff_at: string;
  sent_at: string;
  paid_at: string | null;
}

export interface NoteItem {
  id: string;
  body: string;
  created_at: string;
  actor: { id: string; full_name: string };
}

export interface TimelineEvent {
  kind: string;
  at: string;
  title: string;
  detail: string | null;
  upcoming: boolean;
  amount_cents: number | null;
  ref_id: string | null;
}

export interface PaymentDetail {
  id: string;
  order_reference: string;
  description: string;
  created_at: string;
  amount_cents: number;
  currency: string;
  status: PaymentStatus;
  status_label: string;
  channel: Channel;
  channel_label: string;
  location: LocationRef | null;
  customer: CustomerRef | null;
  method: MethodInfo | null;
  refunded_cents: number;
  net_cents: number;
  succeeded_at: string | null;
  funds_available_at: string | null;
  payout: PayoutRef | null;
  dispute: DisputeTag | null;
  attempts: AttemptItem[];
  refunds: RefundItem[];
  notes: NoteItem[];
  timeline: TimelineEvent[];
}
