import { daysUntil, formatDate } from "../../lib/format";

/** "Due in N days" against the reporting clock, never the browser clock. */
export function deadlineText(due: string, asOf: string): string {
  const days = daysUntil(due, asOf);
  if (days < 0) return `Overdue by ${-days} day${days === -1 ? "" : "s"}`;
  if (days === 0) return "Due today";
  return `Due in ${days} day${days === 1 ? "" : "s"}`;
}

export function Deadline({ due, asOf }: { due: string; asOf: string }) {
  const days = daysUntil(due, asOf);
  const tone = days < 0 ? "danger" : days <= 3 ? "warning" : "neutral";
  return (
    <span className={`deadline deadline-${tone}`}>
      <strong>{deadlineText(due, asOf)}</strong> <span className="muted">· {formatDate(due)}</span>
    </span>
  );
}
