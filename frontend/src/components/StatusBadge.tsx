export type Tone = "success" | "warning" | "danger" | "neutral" | "info";

const TONES: Record<string, Tone> = {
  succeeded: "success",
  paid: "success",
  won: "success",
  pending: "warning",
  in_transit: "info",
  partially_refunded: "neutral",
  refunded: "neutral",
  failed: "danger",
  lost: "danger",
  needs_response: "danger",
  under_review: "warning",
  degraded: "danger",
  within_range: "success",
  insufficient_volume: "neutral",
};

export function toneFor(status: string): Tone {
  return TONES[status] ?? "neutral";
}

/** Status is a dot plus text, never colour alone. */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = toneFor(status);
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-dot" aria-hidden="true" />
      {label ?? status.replace(/_/g, " ")}
    </span>
  );
}
