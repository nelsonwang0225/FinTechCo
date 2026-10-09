import type { PaymentListItem, PeriodInfo } from "./payments-types";

// Mirrors backend/app/api/schemas/payment_health.py. Rates are integer basis points; null means nothing completed.

export type HealthAssessment = "degraded" | "healthy" | "insufficient_volume" | "no_attempts";
export type HealthState = "degraded" | "healthy" | "insufficient_volume" | "no_completed_attempts";

export interface HealthRules {
  baseline_days: number;
  degraded_drop_bp: number;
  min_period_completed: number;
  min_baseline_completed: number;
  low_volume_day_completed: number;
  quick_recovery_seconds: number;
}

export interface DegradedChannel {
  channel: string;
  channel_label: string;
  success_rate_bp: number;
  baseline_rate_bp: number;
  change_bp: number;
  failed: number;
}

export interface HealthSummary {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
  baseline: { succeeded: number; failed: number; completed: number; success_rate_bp: number | null };
  change_bp: number | null;
}

export interface ChannelHealth {
  channel: string;
  channel_label: string;
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
  baseline_completed: number;
  baseline_rate_bp: number | null;
  change_bp: number | null;
  assessment: HealthAssessment;
  assessment_label: string;
}

export interface TrendPoint {
  day: string;
  succeeded: number;
  failed: number;
  pending: number;
  success_rate_bp: number | null;
  low_volume: boolean;
}

export interface FailureSignal {
  failure_code: string;
  label: string;
  failed_attempts: number;
}

export interface Recovery {
  affected_payments: number;
  recovered_payments: number;
  recovered_within_hour_payments: number;
  in_progress_payments: number;
  unresolved_payments: number;
  affected_value_cents: number;
  recovered_value_cents: number;
  recovered_within_hour_value_cents: number;
  in_progress_value_cents: number;
  unresolved_value_cents: number;
  currency: string;
}

export interface PaymentHealth {
  period: PeriodInfo;
  baseline: { days: number; from_date: string; to_date: string; range_label: string };
  channel: string | null;
  channel_label: string | null;
  rules: HealthRules;
  attention: { state: HealthState; state_label: string; degraded_channels: DegradedChannel[] };
  summary: HealthSummary;
  channels: ChannelHealth[];
  trend: TrendPoint[];
  failure_signals: FailureSignal[];
  recovery: Recovery;
  unresolved_payments: PaymentListItem[];
}
