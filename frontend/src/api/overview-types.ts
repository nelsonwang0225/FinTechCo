// Wire types for the Overview. Every number is derived on the server from the ledger and base records.
import type { PaymentListItem, PeriodInfo } from "./payments-types";
import type { NextPayout, PayoutBuckets } from "./payouts-types";
import type { Permission } from "./types";

export interface Greeting {
  salutation: string;
  first_name: string;
  merchant_name: string;
  as_of: string;
}

export interface OverviewTiles {
  collected_cents: number;
  refunds_cents: number;
  funds_available_cents: number;
  pending_cents: number;
  currency: string;
  next_payout: NextPayout;
}

export interface ChartPoint {
  day: string;
  amount_cents: number;
}

export interface CollectedChart {
  title: string;
  points: ChartPoint[];
  total_cents: number;
  currency: string;
}

export interface UpcomingPayout {
  cutoff_at: string;
  payout_date: string;
  amount_cents: number;
  currency: string;
  schedule: string;
  schedule_label: string;
  destination: string;
  note: string;
  buckets: PayoutBuckets;
}

export type AttentionKind = "dispute_deadline" | "payout_in_transit" | "refund_pending";

export interface AttentionLink {
  kind: "dispute" | "payout" | "payment";
  id: string;
  permission: Permission;
}

export interface AttentionItem {
  kind: AttentionKind;
  title: string;
  detail: string;
  at: string;
  at_label: string;
  amount_cents: number;
  currency: string;
  link: AttentionLink;
}

export interface Overview {
  greeting: Greeting;
  period: PeriodInfo;
  tiles: OverviewTiles;
  chart: CollectedChart;
  recent_payments: PaymentListItem[];
  upcoming_payout: UpcomingPayout;
  attention: AttentionItem[];
}
