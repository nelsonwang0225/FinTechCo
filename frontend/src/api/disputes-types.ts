// Wire types for the dispute queue and case detail.
import type { CustomerRef, NoteItem, TimelineEvent } from "./payments-types";
import type { ListResponse } from "./types";

export type DisputeStatus = "needs_response" | "under_review" | "won" | "lost";

export interface DisputePaymentRef {
  id: string;
  order_reference: string;
  amount_cents: number;
  currency: string;
  created_at: string;
  customer: CustomerRef | null;
}

export interface DisputeListItem {
  id: string;
  status: DisputeStatus;
  status_label: string;
  reason: string;
  reason_label: string;
  amount_cents: number;
  currency: string;
  opened_at: string;
  evidence_due_at: string;
  responded_at: string | null;
  resolved_at: string | null;
  payment: DisputePaymentRef;
}

export type DisputeListResponse = ListResponse<DisputeListItem>;

export interface DisputeDetail extends DisputeListItem {
  history: TimelineEvent[];
  notes: NoteItem[];
}
