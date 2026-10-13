// Wire types for GET /api/payment-health. Rates are integer basis points; money is integer cents.
import type { CustomerRef, PeriodInfo } from "./payments-types";

export type Evaluation = "degraded" | "not_degraded" | "insufficient_volume" | "no_completed";

export interface HealthThresholds {
  baseline_days: number;
  min_period_completed: number;
  min_baseline_completed: number;
  degraded_drop_bps: number;
  low_volume_day_completed: number;
  recovery_window_minutes: number;
}

export interface OutcomeCounts {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bps: number | null;
}

export interface ChannelHealth {
  channel: string;
  channel_label: string;
  period: OutcomeCounts;
  baseline: OutcomeCounts;
  drop_bps: number | null;
  evaluation: Evaluation;
  evaluation_label: string;
}

export interface HealthDailyPoint {
  day: string;
  succeeded: number;
  failed: number;
  pending: number;
  success_rate_bps: number | null;
  low_volume: boolean;
}

export interface FailureSignal {
  code: string;
  label: string;
  failed_attempts: number;
}

export interface HealthRecovery {
  affected_payments: number;
  recovered_payments: number;
  recovered_within_window: number;
  unresolved_payments: number;
  unresolved_retry_pending: number;
  affected_cents: number;
  recovered_cents: number;
  unresolved_cents: number;
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
  status: string;
  status_label: string;
  failed_attempts: number;
  last_failure_code: string;
  last_failure_label: string;
  customer: CustomerRef | null;
}

export interface PaymentHealth {
  period: PeriodInfo;
  baseline_period: { from_date: string; to_date: string; range_label: string };
  channel: string | null;
  channel_label: string;
  thresholds: HealthThresholds;
  summary: { period: OutcomeCounts; baseline: OutcomeCounts };
  attention: { status: Evaluation; status_label: string; degraded: ChannelHealth[]; not_evaluated: ChannelHealth[] };
  channels: ChannelHealth[];
  daily: HealthDailyPoint[];
  failure_signals: FailureSignal[];
  recovery: HealthRecovery;
  unresolved: UnresolvedPayment[];
}
