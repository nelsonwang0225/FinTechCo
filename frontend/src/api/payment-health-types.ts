// Wire types for GET /api/payment-health. Rates are integer basis points (10000 = 100%); money is integer cents.
import type { Channel, CustomerRef, PeriodInfo } from "./payments-types";
import type { Option } from "./types";

export type Assessment = "degraded" | "not_degraded" | "insufficient_volume";
export type AttentionStatus = "degraded" | "no_significant_degradation" | "insufficient_volume" | "no_completed_attempts";

export interface AttemptSummary {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
  baseline_succeeded: number;
  baseline_failed: number;
  baseline_completed: number;
  baseline_success_rate_bp: number | null;
  change_bp: number | null;
}

export interface ChannelHealth extends AttemptSummary {
  channel: Channel;
  channel_label: string;
  assessment: Assessment;
  assessment_label: string;
}

export interface DegradedChannel {
  channel: Channel;
  channel_label: string;
  success_rate_bp: number;
  baseline_success_rate_bp: number;
  change_bp: number;
  failed_attempts: number;
  unresolved_payments: number;
}

export interface HealthTrendDay {
  date: string;
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  success_rate_bp: number | null;
  low_volume: boolean;
  partial: boolean;
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

export interface UnresolvedPayment {
  id: string;
  order_reference: string;
  created_at: string;
  amount_cents: number;
  currency: string;
  channel: Channel;
  channel_label: string;
  attempt_count: number;
  last_failure_code: string | null;
  last_failure_label: string | null;
  customer: CustomerRef | null;
}

export interface PaymentHealth {
  as_of: string;
  period: PeriodInfo;
  baseline: { from_date: string; to_date: string; range_label: string };
  channel: Channel | null;
  channel_label: string;
  rules: {
    baseline_days: number;
    degraded_drop_bp: number;
    min_completed_attempts: number;
    low_volume_day_attempts: number;
    recovery_window_seconds: number;
  };
  attention: { status: AttentionStatus; degraded: DegradedChannel[]; insufficient_volume_channels: Channel[] };
  attempts: AttemptSummary;
  trend: HealthTrendDay[];
  channels: ChannelHealth[];
  failure_signals: FailureSignal[];
  recovery: Recovery;
  unresolved: UnresolvedPayment[];
}

export interface FailureSignalOptions {
  options: Option[];
}
