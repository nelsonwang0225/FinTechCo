import type { AttemptItem } from "../api/payments-types";
import { formatCount, formatElapsedMinutes, minutesBetween } from "./format";

/**
 * The customer-level picture of one payment, derived only from its recorded attempts: how many failed, whether a
 * later attempt succeeded and how long after the first attempt, and the recorded signals. It describes what was
 * recorded and never claims a cause.
 */
export function attemptChainSummary(attempts: AttemptItem[]): string {
  if (attempts.length === 0) return "No attempts recorded";
  const ordered = [...attempts].sort((a, b) => a.attempt_number - b.attempt_number);
  const failed = ordered.filter((a) => a.outcome === "failed");
  const success = ordered.find((a) => a.outcome === "succeeded");
  const latest = ordered[ordered.length - 1]!;
  const failedPart = `${formatCount(failed.length)} failed attempt${failed.length === 1 ? "" : "s"}`;

  if (success) {
    if (failed.length === 0) return success.attempt_number === 1 ? "Succeeded on the first attempt" : `Succeeded on attempt ${success.attempt_number}`;
    const first = ordered[0]!;
    const after = success.completed_at ? `, ${formatElapsedMinutes(minutesBetween(first.created_at, success.completed_at))} after the first` : "";
    return `${failedPart} · recovered on attempt ${success.attempt_number}${after}`;
  }

  const signals = Array.from(new Set(failed.map((a) => a.failure_message).filter((m): m is string => Boolean(m))));
  const signalPart = signals.length === 0 ? "" : ` · recorded signal${signals.length === 1 ? "" : "s"}: ${signals.join(", ")}`;
  if (latest.outcome === "pending") return `${failedPart} · attempt ${latest.attempt_number} pending${signalPart}`;
  return `${failedPart} · ${failed.length === 1 ? "no retry recorded" : "no successful retry"}${signalPart}`;
}
