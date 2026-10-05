// Wire types for the FinTechCo Business API. Money is integer cents; timestamps are UTC ISO strings.

export type Permission =
  | "overview:read"
  | "payments:read"
  | "customers:read"
  | "disputes:read"
  | "payouts:read"
  | "notes:write"
  | "reports:operational"
  | "reports:financial"
  | "settings:read";

export type Role = "business_admin" | "operations_manager" | "finance_manager" | "read_only_analyst";

export interface SessionUser {
  id: string;
  full_name: string;
  email: string;
  title: string;
}

export interface SessionMerchant {
  id: string;
  name: string;
  slug: string;
}

export interface Session {
  membership_id: string;
  user: SessionUser;
  merchant: SessionMerchant;
  role: Role;
  role_label: string;
  permissions: Permission[];
  as_of: string;
  timezone: string;
}

export interface PersonaOption {
  membership_id: string;
  user_id: string;
  full_name: string;
  title: string;
  role: Role;
  role_label: string;
}

export interface PersonaMerchant {
  merchant: SessionMerchant;
  personas: PersonaOption[];
}

export interface PersonasResponse {
  merchants: PersonaMerchant[];
}

export interface Option {
  value: string;
  label: string;
}

export interface LocationOption {
  id: string;
  name: string;
  address_line: string;
  city: string;
  state: string;
}

export interface Meta {
  channels: Option[];
  payment_statuses: Option[];
  attempt_outcomes: Option[];
  refund_statuses: Option[];
  refund_reasons: Option[];
  dispute_statuses: Option[];
  dispute_reasons: Option[];
  payout_statuses: Option[];
  period_presets: Option[];
  default_period: string;
  locations: LocationOption[];
  timezone: string;
}

export interface ListResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}
