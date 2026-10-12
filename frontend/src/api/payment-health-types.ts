// Wire types for GET /api/payment-health. Rates are integer basis points (10000 = 100%); money is integer cents.
import type { Channel, PeriodInfo } from "./payments-types";

export type HealthAssessment = "degraded" | "within_baseline" | "insufficient_period_volume" | "insufficient_baseline" | "no_completed_attempts";

export interface HealthThresholds {
  degraded_drop_bp: number;
  min_period_completed: number;
  min_baseline_completed: number;
  low_volume_day_completed: number;
  baseline_days: number;
  quick_recovery_seconds: number;
}

export interface ScopeHealth {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
  baseline_succeeded: number;
  baseline_failed: number;
  baseline_completed: number;
  baseline_rate_bp: number | null;
  change_bp: number | null;
}

export interface ChannelHealth extends ScopeHealth {
  channel: Channel;
  channel_label: string;
  assessment: HealthAssessment;
  assessment_label: string;
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
  failed_attempts: number;
  share_bp: number;
}

export interface RecoveryBucket {
  payments: number;
  amount_cents: number;
}

export interface Recovery {
  affected: RecoveryBucket;
  recovered: RecoveryBucket;
  recovered_within_hour: RecoveryBucket;
  unresolved: RecoveryBucket;
  awaiting_retry: RecoveryBucket;
  currency: string;
}

export interface PaymentHealth {
  as_of: string;
  period: PeriodInfo;
  baseline: { from_date: string; to_date: string; range_label: string };
  channel: Channel | null;
  channel_label: string | null;
  thresholds: HealthThresholds;
  summary: ScopeHealth;
  channels: ChannelHealth[];
  trend: TrendPoint[];
  failure_signals: FailureSignal[];
  recovery: Recovery;
}
