import type { CustomerRef, PeriodInfo } from "./payments-types";

/** Mirrors backend/app/api/schemas/payment_health.py. Rates and shares are integer basis points; money is integer cents. */

export type ChannelStatus = "degraded" | "normal" | "insufficient_volume" | "no_baseline";

export interface RuleInfo {
  baseline_days: number;
  min_period_completed: number;
  min_baseline_completed: number;
  degraded_drop_bp: number;
  low_volume_day_completed: number;
  recovery_window_minutes: number;
}

export interface BaselineInfo {
  from_date: string;
  to_date: string;
  range_label: string;
  history_starts: string | null;
  partial: boolean;
}

export interface OutcomeCounts {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
  failed_share_bp: number | null;
}

export interface TrendPoint {
  day: string;
  succeeded: number;
  failed: number;
  completed: number;
  success_rate_bp: number | null;
  low_volume: boolean;
}

export interface ChannelHealth {
  channel: string | null;
  channel_label: string;
  status: ChannelStatus;
  status_label: string;
  period: OutcomeCounts;
  baseline: OutcomeCounts;
  drop_bp: number | null;
  worst_day: TrendPoint | null;
}

export interface Attention {
  status: ChannelStatus;
  headline: string;
  detail: string;
  degraded_channels: string[];
}

export interface Trend {
  points: TrendPoint[];
  baseline_rate_bp: number | null;
}

export interface FailureSignal {
  failure_code: string;
  label: string;
  count: number;
  share_bp: number;
}

export interface FailureSignals {
  total_failed: number;
  items: FailureSignal[];
  primary: FailureSignal | null;
}

export interface Recovery {
  affected: number;
  recovered: number;
  recovered_within_window: number;
  recovered_later: number;
  attempt_pending: number;
  unresolved: number;
  recovered_within_window_share_bp: number | null;
  affected_cents: number;
  recovered_cents: number;
  unresolved_cents: number;
  attempt_pending_cents: number;
  currency: string;
}

export interface UnresolvedPayment {
  id: string;
  order_reference: string;
  customer: CustomerRef | null;
  amount_cents: number;
  currency: string;
  last_attempt_at: string;
  last_failure_code: string | null;
  last_failure_label: string | null;
  attempt_count: number;
}

export interface UnresolvedPayments {
  total: number;
  items: UnresolvedPayment[];
}

export interface PaymentHealth {
  period: PeriodInfo;
  channel: string | null;
  channel_label: string;
  as_of: string;
  rule: RuleInfo;
  baseline: BaselineInfo;
  attention: Attention;
  scope: ChannelHealth;
  channels: ChannelHealth[];
  trend: Trend;
  failure_signals: FailureSignals;
  recovery: Recovery;
  unresolved_payments: UnresolvedPayments;
}
