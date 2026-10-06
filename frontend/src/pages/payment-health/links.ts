import type { PeriodInfo } from "../../api/payments-types";
import { queryString } from "../../api/client";

/** URL period keys for the period the API actually resolved, in the form the Payments page reads them. */
export function periodQuery(period: PeriodInfo): Record<string, string> {
  if (period.preset === "custom") return { period: "custom", from: period.from_date, to: period.to_date };
  return { period: period.preset };
}

/**
 * The existing Payments list filtered to failed payments with the same dates and channel. A failed payment has no
 * succeeded attempt and its latest attempt failed, which is exactly an unresolved payment in Payment Health.
 */
export function unresolvedPaymentsHref(period: PeriodInfo, channel: string | null): string {
  return `/payments${queryString({ ...periodQuery(period), channel: channel ?? undefined, status: "failed" })}`;
}
