// Wire types for the merchant-scoped customer directory.
import type { PaymentListItem, RefundItem } from "./payments-types";
import type { ListResponse } from "./types";

export interface CustomerListItem {
  id: string;
  reference: string;
  full_name: string;
  email: string;
  created_at: string;
  first_payment_at: string | null;
  last_activity_at: string | null;
}

export type CustomerListResponse = ListResponse<CustomerListItem>;

export interface CustomerRefundItem extends RefundItem {
  payment_id: string;
  order_reference: string;
}

export interface CustomerDetail extends CustomerListItem {
  payments: PaymentListItem[];
  refunds: CustomerRefundItem[];
}
