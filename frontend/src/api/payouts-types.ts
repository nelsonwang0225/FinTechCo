import type { ListResponse } from "./types";

export interface PayoutListItem {
  id: string;
  status: "in_transit" | "paid";
  status_label: string;
  amount_cents: number;
  currency: string;
  cutoff_at: string;
  payout_date: string;
  sent_at: string;
  expected_arrival_date: string;
  paid_at: string | null;
  destination: string;
}

export interface NextPayout {
  cutoff_at: string;
  payout_date: string;
  amount_cents: number;
  currency: string;
  schedule: string;
  schedule_label: string;
  note: string;
}

export interface FundsSummary {
  as_of: string;
  available_cents: number;
  pending_cents: number;
  currency: string;
  next_payout: NextPayout;
  destination: string;
}

export interface PayoutListResponse extends ListResponse<PayoutListItem> {
  summary: FundsSummary;
}

export interface MovementItem {
  id: string;
  type: string;
  type_label: string;
  amount_cents: number;
  currency: string;
  description: string;
  posted_at: string;
  available_at: string;
  payment_id: string | null;
  order_reference: string | null;
  customer_name: string | null;
  refund_id: string | null;
  dispute_id: string | null;
}

export interface PayoutBuckets {
  collections_cents: number;
  fees_cents: number;
  refunds_cents: number;
  disputes_cents: number;
  adjustments_cents: number;
}

export interface PayoutDetail extends PayoutListItem {
  destination_label: string;
  destination_last4: string;
  destination_kind: string;
  buckets: PayoutBuckets;
  movement_total_cents: number;
  movement_count: number;
  reconciled: boolean;
  movements: MovementItem[];
}
