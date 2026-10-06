// Wire types for Payment Health. Rates are integer basis points (7204 = 72.04%); money is integer cents.
import type { Channel, PeriodInfo } from "./payments-types";

export type HealthEvaluation = "degraded" | "within_range" | "insufficient_volume";
export type HealthSummaryState = "degraded" | "no_degradation" | "insufficient_volume";

export interface BaselineInfo {
  from_date: string;
  to_date: string;
  range_label: string;
}

export interface HealthRules {
  baseline_days: number;
  min_period_completed: number;
  min_baseline_completed: number;
  degraded_drop_bp: number;
}

export interface ChannelHealth {
  channel: Channel;
  channel_label: string;
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  rate_bp: number | null;
  baseline_succeeded: number;
  baseline_failed: number;
  baseline_completed: number;
  baseline_rate_bp: number | null;
  delta_bp: number | null;
  evaluation: HealthEvaluation;
  evaluation_label: string;
}

export interface AttentionSummary {
  state: HealthSummaryState;
  message: string;
  degraded: ChannelHealth[];
}

export interface HealthKpis {
  succeeded: number;
  failed: number;
  pending: number;
  completed: number;
  rate_bp: number | null;
  baseline_completed: number;
  baseline_rate_bp: number | null;
  delta_bp: number | null;
  affected_payments: number;
  recovered_payments: number;
  unresolved_payments: number;
  awaiting_retry_payments: number;
  affected_cents: number;
  currency: string;
}

export interface FailureSignal {
  code: string;
  label: string;
  count: number;
}

export interface PaymentHealth {
  period: PeriodInfo;
  baseline: BaselineInfo;
  channel: Channel | null;
  channel_label: string;
  rules: HealthRules;
  summary: AttentionSummary;
  kpis: HealthKpis;
  channels: ChannelHealth[];
  failure_signals: FailureSignal[];
}
