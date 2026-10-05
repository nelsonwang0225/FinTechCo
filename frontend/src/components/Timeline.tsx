import type { TimelineEvent } from "../api/payments-types";
import { Money } from "./Money";
import { Timestamp } from "./Timestamp";

const TONE_BY_KIND: Record<string, string> = {
  attempt_failed: "danger",
  attempt_pending: "warning",
  attempt_succeeded: "success",
  funds_available: "neutral",
  payout_included: "neutral",
  payout_sent: "info",
  payout_paid: "success",
  refund_pending: "warning",
  refund_succeeded: "neutral",
  dispute_opened: "danger",
  dispute_responded: "warning",
  dispute_resolved: "neutral",
  dispute_evidence_due: "danger",
  note: "info",
};

/** The record's history, derived by the API at read time. Future-dated events are marked upcoming. */
export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="timeline">
      {events.map((event, index) => (
        <li key={`${event.kind}-${event.at}-${index}`} className={`timeline-item tone-${TONE_BY_KIND[event.kind] ?? "neutral"}${event.upcoming ? " upcoming" : ""}`}>
          <span className="timeline-dot" aria-hidden="true" />
          <div className="timeline-body">
            <div className="timeline-head">
              <span className="timeline-title">{event.title}</span>
              {event.upcoming ? <span className="timeline-upcoming">Upcoming</span> : null}
              {event.amount_cents !== null ? <Money cents={event.amount_cents} sign className="timeline-amount" /> : null}
            </div>
            {event.detail ? <p className="timeline-detail">{event.detail}</p> : null}
            <p className="timeline-when">
              <Timestamp iso={event.at} mode="full" />
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
