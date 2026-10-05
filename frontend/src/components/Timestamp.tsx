import { chicagoDate, formatRelative, formatTime, formatTimeFull, formatTimestamp, formatTimestampFull } from "../lib/format";
import { useCurrentSession } from "../session/SessionProvider";

export type TimestampMode = "absolute" | "relative" | "full";

export interface TimestampProps {
  iso: string | null | undefined;
  mode?: TimestampMode;
  /** When given and on the same Chicago day as `iso`, only the time is shown (the full timestamp stays in the tooltip). */
  sameDayAs?: string | null;
}

/** A UTC instant shown in America/Chicago. Relative times are measured against the session clock, never the browser's. */
export function Timestamp({ iso, mode = "absolute", sameDayAs }: TimestampProps) {
  const session = useCurrentSession();
  if (!iso) return <span className="muted">—</span>;
  const full = formatTimestampFull(iso);
  const sameDay = Boolean(sameDayAs) && chicagoDate(iso) === chicagoDate(sameDayAs as string);
  const text = sameDay ? (mode === "full" ? formatTimeFull(iso) : formatTime(iso)) : mode === "relative" ? formatRelative(iso, session.as_of) : mode === "full" ? full : formatTimestamp(iso, session.as_of);
  return (
    <time dateTime={iso} title={full} className="num">
      {text}
    </time>
  );
}
