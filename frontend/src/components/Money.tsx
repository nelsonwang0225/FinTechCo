import { formatCents } from "../lib/format";

/** Integer cents rendered as a right-aligned tabular dollar amount. */
export function Money({ cents, sign = false, className = "" }: { cents: number; sign?: boolean; className?: string }) {
  return <span className={`money ${className}`.trim()}>{formatCents(cents, { sign, symbol: true })}</span>;
}
