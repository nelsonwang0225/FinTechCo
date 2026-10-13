// Wire types for Payment Health. Rates are integer basis points (10000 = 100%), null when nothing completed;
// money is integer cents; days are America/Chicago calendar dates.
import type { CustomerRef, PeriodInfo } from "./payments-types";

export type HealthVerdict = "degraded" | "ok" | "insufficient_data" | "no_data";

export interface HealthRules {
  baseline_days: number;
  min_period_completed: number;
  min_baseline_completed: number;
  degraded_drop_bps: number;
  low_volume_day_completed: number;
  quick_recovery_minutes: number;
}

export interface AttemptMetrics {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bps: number | null;
  failure_rate_bps: number | null;
}

export interface ChannelHealth {
  channel: string;
  channel_label: string;
  period: AttemptMetrics;
  baseline: AttemptMetrics;
  change_bps: number | null;
  verdict: HealthVerdict;
  verdict_label: string;
}

export interface ScopeHealth {
  period: AttemptMetrics;
  baseline: AttemptMetrics;
  change_bps: number | null;
}

export interface Attention {
  state: HealthVerdict;
  degraded_channels: ChannelHealth[];
  insufficient_channels: string[];
}

export interface TrendPoint {
  day: string;
  succeeded: number;
  failed: number;
  pending: number;
  success_rate_bps: number | null;
  low_volume: boolean;
  partial: boolean;
}

export interface FailureSignal {
  code: string;
  label: string;
  count: number;
}

export interface Recovery {
  affected_count: number;
  affected_cents: number;
  recovered_count: number;
  recovered_cents: number;
  recovered_within_hour_count: number;
  recovered_within_hour_cents: number;
  unresolved_count: number;
  unresolved_cents: number;
  in_progress_count: number;
  in_progress_cents: number;
  currency: string;
}

export interface UnresolvedPayment {
  id: string;
  order_reference: string;
  created_at: string;
  amount_cents: number;
  currency: string;
  channel: string;
  channel_label: string;
  customer: CustomerRef | null;
  failed_attempts: number;
  last_failure_code: string;
  last_failure_label: string;
  last_attempt_at: string;
}

export interface PaymentHealth {
  period: PeriodInfo;
  baseline_period: PeriodInfo;
  channel: string | null;
  as_of: string;
  rules: HealthRules;
  scope: ScopeHealth;
  attention: Attention;
  channels: ChannelHealth[];
  trend: TrendPoint[];
  failure_signals: FailureSignal[];
  recovery: Recovery;
  unresolved_payments: UnresolvedPayment[];
}

export interface FailureSignalsResponse {
  period: PeriodInfo;
  channel: string | null;
  signals: FailureSignal[];
}
