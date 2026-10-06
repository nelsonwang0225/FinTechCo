import type { PeriodInfo } from "./payments-types";

/** Mirrors backend/app/api/schemas/payment_health.py. Rates are integer basis points. */
export interface AttemptPerformance {
  succeeded: number;
  failed: number;
  completed: number;
  pending_excluded: number;
  success_rate_bp: number | null;
  low_volume: boolean;
  low_volume_threshold: number;
}

export interface TrendPoint {
  day: string;
  succeeded: number;
  failed: number;
}

export interface Trend {
  granularity: string;
  points: TrendPoint[];
}

export interface FailureSignal {
  failure_code: string;
  label: string;
  count: number;
}

export interface FailureSignals {
  total_failed: number;
  items: FailureSignal[];
}

export interface Recovery {
  affected_payments: number;
  recovered: number;
  recovered_within_hour: number;
  unresolved: number;
  attempt_pending: number;
  affected_cents: number;
  recovered_cents: number;
  unresolved_cents: number;
  attempt_pending_cents: number;
  currency: string;
}

export interface PaymentHealth {
  period: PeriodInfo;
  channel: string | null;
  channel_label: string;
  as_of: string;
  attempts: AttemptPerformance;
  trend: Trend;
  failure_signals: FailureSignals;
  recovery: Recovery;
}
