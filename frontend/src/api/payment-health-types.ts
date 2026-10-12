// Mirrors backend/app/api/schemas/payment_health.py. Rates are integer basis points; null means nothing completed.
import type { Channel, PaymentListItem, PeriodInfo } from "./payments-types";

export type HealthAssessment = "degraded" | "normal" | "insufficient_data" | "no_attempts";

export interface HealthRules {
  baseline_days: number;
  degraded_drop_bps: number;
  min_period_completed: number;
  min_baseline_completed: number;
  low_volume_day_completed: number;
  recovery_window_seconds: number;
}

export interface AttemptStats {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bps: number | null;
}

export interface ChannelHealth {
  channel: Channel;
  label: string;
  period: AttemptStats;
  baseline: AttemptStats;
  delta_bps: number | null;
  assessment: HealthAssessment;
  assessment_label: string;
}

export interface TrendPoint extends AttemptStats {
  day: string;
  low_volume: boolean;
}

export interface FailureSignal {
  failure_code: string;
  label: string;
  failed_attempts: number;
}

export interface Recovery {
  affected_payments: number;
  affected_cents: number;
  recovered_payments: number;
  recovered_cents: number;
  recovered_within_window_payments: number;
  recovered_within_window_cents: number;
  unresolved_payments: number;
  unresolved_cents: number;
  retry_pending_payments: number;
  retry_pending_cents: number;
  currency: string;
}

export interface PaymentHealth {
  period: PeriodInfo;
  baseline: { from_date: string; to_date: string; range_label: string };
  channel: Channel | null;
  channel_label: string | null;
  rules: HealthRules;
  summary: { period: AttemptStats; baseline: AttemptStats; delta_bps: number | null };
  channels: ChannelHealth[];
  trend: TrendPoint[];
  failure_signals: FailureSignal[];
  recovery: Recovery;
  unresolved_payments: { items: PaymentListItem[]; total: number };
}
