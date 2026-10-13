// Wire types for GET /api/payment-health. Rates are integer basis points (10000 = 100%) or null when nothing completed;
// money is integer cents.
import type { PaymentListItem, PeriodInfo } from "./payments-types";

export type Assessment = "degraded" | "not_degraded" | "insufficient_data" | "no_completed_attempts";

export interface AttemptStats {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bps: number | null;
}

export interface HealthSummary {
  period: AttemptStats;
  baseline: AttemptStats;
  change_bps: number | null;
  assessment: Assessment;
  assessment_label: string;
}

export interface ChannelHealth extends HealthSummary {
  channel: string;
  channel_label: string;
}

export interface TrendPoint {
  date: string;
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bps: number | null;
  low_volume: boolean;
}

export interface FailureSignal {
  failure_code: string;
  label: string;
  failed_attempts: number;
}

export interface RecoverySummary {
  affected_payments: number;
  recovered_payments: number;
  recovered_within_window_payments: number;
  unresolved_payments: number;
  awaiting_outcome_payments: number;
  affected_value_cents: number;
  recovered_value_cents: number;
  unresolved_value_cents: number;
  awaiting_outcome_value_cents: number;
  currency: string;
}

export interface Thresholds {
  min_completed_attempts: number;
  degradation_points: number;
  low_volume_day_attempts: number;
  baseline_days: number;
  recovery_window_minutes: number;
}

export interface PaymentHealth {
  as_of: string;
  period: PeriodInfo;
  baseline: { from_date: string; to_date: string; range_label: string; days: number };
  channel: string | null;
  thresholds: Thresholds;
  summary: HealthSummary;
  channels: ChannelHealth[];
  trend: TrendPoint[];
  failure_signals: FailureSignal[];
  recovery: RecoverySummary;
  unresolved: { items: PaymentListItem[]; total: number };
}
