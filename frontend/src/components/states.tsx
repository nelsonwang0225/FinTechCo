import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";

/** Skeleton rows while a view loads. */
export function LoadingState({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" aria-hidden="true">
          <span className="skeleton skeleton-wide" />
          <span className="skeleton skeleton-mid" />
          <span className="skeleton skeleton-narrow" />
        </div>
      ))}
      <span className="visually-hidden">{label}…</span>
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state state-empty" role="status">
      <p className="state-title">{title}</p>
      {body ? <p className="state-body">{body}</p> : null}
      {action ? <div className="state-action">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error | null; onRetry?: () => void }) {
  const message = error instanceof ApiError ? error.message : (error?.message ?? "Something went wrong.");
  return (
    <div className="state state-error" role="alert">
      <p className="state-title">Could not load this view</p>
      <p className="state-body">{message}</p>
      {onRetry ? (
        <div className="state-action">
          <button type="button" className="btn" onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function ForbiddenState() {
  return (
    <div className="state state-forbidden" role="alert">
      <p className="state-title">Your role does not include this section</p>
      <p className="state-body">Ask a business admin if you need access. Nothing from this section is loaded for your role.</p>
      <div className="state-action">
        <Link className="btn" to="/overview">
          Back to Overview
        </Link>
      </div>
    </div>
  );
}

export function NotFoundState({ what = "record", backTo, backLabel }: { what?: string; backTo?: string; backLabel?: string }) {
  return (
    <div className="state state-notfound" role="alert">
      <p className="state-title">That {what} is not in this business</p>
      <p className="state-body">Check the link, or search for it from the list.</p>
      {backTo ? (
        <div className="state-action">
          <Link className="btn" to={backTo}>
            {backLabel ?? "Back"}
          </Link>
        </div>
      ) : null}
    </div>
  );
}

/** Routes a load error to the right state component. */
export function LoadError({ error, onRetry, what, backTo, backLabel }: { error: ApiError; onRetry?: () => void; what?: string; backTo?: string; backLabel?: string }) {
  if (error.status === 403) return <ForbiddenState />;
  if (error.status === 404) return <NotFoundState what={what} backTo={backTo} backLabel={backLabel} />;
  return <ErrorState error={error} onRetry={onRetry} />;
}
