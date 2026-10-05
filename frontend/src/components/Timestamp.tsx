import { formatRelative, formatTimestamp, formatTimestampFull } from "../lib/format";
import { useCurrentSession } from "../session/SessionProvider";

export type TimestampMode = "absolute" | "relative" | "full";

/** A UTC instant shown in America/Chicago. Relative times are measured against the session clock, never the browser's. */
export function Timestamp({ iso, mode = "absolute" }: { iso: string | null | undefined; mode?: TimestampMode }) {
  const session = useCurrentSession();
  if (!iso) return <span className="muted">—</span>;
  const full = formatTimestampFull(iso);
  const text = mode === "relative" ? formatRelative(iso, session.as_of) : mode === "full" ? full : formatTimestamp(iso, session.as_of);
  return (
    <time dateTime={iso} title={full} className="num">
      {text}
    </time>
  );
}
