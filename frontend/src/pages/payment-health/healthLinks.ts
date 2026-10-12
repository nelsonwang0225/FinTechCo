import { queryString } from "../../api/client";
import type { QueryState } from "../../lib/query";
import { periodParams } from "../payments/PeriodFilter";

/** The Payment Health scope a drill-down came from: the period exactly as the page sent it, plus the channel. */
export interface HealthScope {
  period?: string;
  from?: string;
  to?: string;
  channel?: string;
}

/** Keys that carry the originating scope through Payments, so "Back to Payment Health" restores it unchanged. */
const RETURN_KEYS = { period: "ph_period", from: "ph_from", to: "ph_to", channel: "ph_channel" } as const;

export function healthScope(query: QueryState): HealthScope {
  return { ...periodParams(query), channel: query.get("channel") || undefined };
}

function returnParams(scope: HealthScope): Record<string, string | undefined> {
  return { [RETURN_KEYS.period]: scope.period, [RETURN_KEYS.from]: scope.from, [RETURN_KEYS.to]: scope.to, [RETURN_KEYS.channel]: scope.channel };
}

function periodOf(scope: HealthScope): Record<string, string | undefined> {
  return { period: scope.period, from: scope.from, to: scope.to };
}

/** Failed attempts in the same period, optionally for one channel and one recorded failure signal (the Attempts tab). */
export function failedAttemptsHref(scope: HealthScope, channel: string | undefined, failureCode?: string): string {
  return `/payments${queryString({ tab: "attempts", ...periodOf(scope), outcome: "failed", channel, failure_code: failureCode, ...returnParams(scope) })}`;
}

/** Unresolved payments (derived status failed) created in the same period, optionally for one channel. */
export function unresolvedPaymentsHref(scope: HealthScope, channel: string | undefined): string {
  return `/payments${queryString({ ...periodOf(scope), status: "failed", channel, ...returnParams(scope) })}`;
}

/** The Payment Health page for the scope carried in the URL, or null when the visit did not start there. */
export function healthReturnHref(query: QueryState): string | null {
  const period = query.get(RETURN_KEYS.period);
  if (!period) return null;
  return `/payment-health${queryString({ period, from: query.get(RETURN_KEYS.from), to: query.get(RETURN_KEYS.to), channel: query.get(RETURN_KEYS.channel) })}`;
}
