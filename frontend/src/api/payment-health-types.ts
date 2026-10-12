// Mirrors backend/app/api/schemas/payment_health.py. Rates are integer basis points (9123 = 91.23%), null when nothing completed.
import type { PeriodInfo } from "./payments-types";

export type HealthAssessment = "degraded" | "no_significant_degradation" | "insufficient_volume" | "no_completed_attempts";
export type AttentionState = "degraded" | "no_significant_degradation" | "insufficient_data" | "no_completed_attempts";

export interface HealthRules {
  baseline_days: number;
  degraded_drop_bp: number;
  min_period_completed: number;
  min_baseline_completed: number;
  low_volume_day_completed: number;
  quick_recovery_seconds: number;
}

export interface BaselineInfo {
  from_date: string;
  to_date: string;
  range_label: string;
  days: number;
  days_with_completed: number;
}

export interface AttemptMetrics {
  completed: number;
  succeeded: number;
  failed: number;
  pending: number;
  success_rate_bp: number | null;
  baseline_completed: number;
  baseline_succeeded: number;
  baseline_rate_bp: number | null;
  change_bp: number | null;
}

export interface ChannelHealth extends AttemptMetrics {
  channel: string;
  channel_label: string;
  assessment: HealthAssessment;
  assessment_label: string;
}

export interface HealthAttention {
  state: AttentionState;
  label: string;
  degraded_channels: string[];
  not_assessed_channels: string[];
}

export interface TrendPoint {
  day: string;
  completed: number;
  succeeded: number;
  failed: number;
  pending: number;
  success_rate_bp: number | null;
  low_volume: boolean;
}

export interface FailureSignal {
  code: string;
  label: string;
  count: number;
}

export interface RecoveryGroup {
  payments: number;
  amount_cents: number;
}

export interface RecoverySummary {
  currency: string;
  affected: RecoveryGroup;
  recovered: RecoveryGroup;
  recovered_within_hour: RecoveryGroup;
  unresolved: RecoveryGroup;
  in_progress: RecoveryGroup;
}

export interface PaymentHealth {
  period: PeriodInfo;
  baseline: BaselineInfo;
  channel: string | null;
  channel_label: string | null;
  rules: HealthRules;
  attempts: AttemptMetrics;
  attention: HealthAttention;
  channels: ChannelHealth[];
  trend: TrendPoint[];
  failure_signals: FailureSignal[];
  recovery: RecoverySummary;
}
