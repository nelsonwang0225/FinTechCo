import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { IconChevronLeft } from "../layout/icons";

/**
 * Shown on a list reached from Payment Health: where the list came from, the filters it carries, and how many records
 * they match, so the number on the list can be read against the number that was clicked. `parts` are built by the
 * caller from the current filters, so the bar changes as the list is narrowed.
 */
export function HealthContextBar({ parts, result, backHref }: { parts: string[]; result: ReactNode; backHref: string }) {
  return (
    <section className="health-context" aria-label="Opened from Payment Health">
      <p className="health-context-scope">
        <span className="health-context-origin">From Payment Health</span>
        {parts.map((part) => (
          <span key={part}>
            <span aria-hidden="true"> · </span>
            {part}
          </span>
        ))}
      </p>
      <p className="health-context-result num" role="status">
        {result}
      </p>
      <Link className="health-context-back" to={backHref}>
        <IconChevronLeft />
        Back to Payment Health
      </Link>
    </section>
  );
}
