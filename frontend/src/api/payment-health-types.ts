// Wire types for Payment Health. Rates are integer basis points (7204 = 72.04%) or null when nothing completed;
// money is integer cents. Every figure is derived on the server from payment and attempt rows.
import type { PaymentListItem, PeriodInfo } from "./payments-types";

export type HealthVerdict = "degraded" | "not_degraded" | "insufficient_data" | "no_data";
export type AttentionVerdict = "degraded" | "no_degradation" | "not_enough_data" | "no_data";

export interface HealthRules {
  baseline_days: number;
  degraded_drop_bp: number;
  min_period_completed: number;
  min_baseline_completed: number;
  low_volume_day_completed: number;
  recovery_window_minutes: number;
}

export interface AttemptStats {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
}

export interface ScopeSummary {
  channel: string | null;
  channel_label: string;
  period: AttemptStats;
  baseline: AttemptStats;
  change_bp: number | null;
}

export interface ChannelHealth {
  channel: string;
  channel_label: string;
  period: AttemptStats;
  baseline: AttemptStats;
  change_bp: number | null;
  verdict: HealthVerdict;
  verdict_label: string;
}

export interface HealthAttention {
  verdict: AttentionVerdict;
  degraded_channels: string[];
}

export interface TrendPoint {
  day: string;
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
  low_volume: boolean;
}

export interface FailureSignal {
  code: string;
  label: string;
  attempts: number;
  payments: number;
}

export interface Recovery {
  currency: string;
  affected_payments: number;
  affected_cents: number;
  failed_attempts: number;
  recovered_payments: number;
  recovered_cents: number;
  recovered_within_window_payments: number;
  recovered_within_window_cents: number;
  unresolved_payments: number;
  unresolved_cents: number;
  retry_pending_payments: number;
  retry_pending_cents: number;
}

export interface PaymentHealth {
  period: PeriodInfo;
  baseline_period: PeriodInfo;
  rules: HealthRules;
  summary: ScopeSummary;
  attention: HealthAttention;
  channels: ChannelHealth[];
  trend: TrendPoint[];
  failure_signals: FailureSignal[];
  recovery: Recovery;
  unresolved_payments: PaymentListItem[];
  unresolved_total: number;
}
