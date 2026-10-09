import { Link, useParams } from "react-router-dom";
import type { AttemptItem, PaymentDetail, RefundItem } from "../../api/payments-types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { Money } from "../../components/Money";
import { NoteComposer } from "../../components/NoteComposer";
import { StatusBadge } from "../../components/StatusBadge";
import { Timeline } from "../../components/Timeline";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { IconChevronLeft } from "../../layout/icons";
import { attemptChainSummary } from "../../lib/attemptChain";
import { backToHealthHref, backToListLink } from "../../lib/healthScope";
import { useQueryState } from "../../lib/query";
import { useSession } from "../../session/SessionProvider";

export function PaymentDetailPage() {
  const { paymentId = "" } = useParams();
  const { can } = useSession();
  const query = useQueryState();
  // Opened from a list that was reached from Payment Health, the URL carries that list's query: link back to both.
  const backToList = backToListLink(query);
  const backToHealth = backToHealthHref(query);
  const detail = useApi<PaymentDetail>(`/api/payments/${encodeURIComponent(paymentId)}`);

  if (detail.error) {
    return (
      <>
        <PageHeader title="Payment" />
        <LoadError
          error={detail.error}
          onRetry={detail.reload}
          what="payment"
          backTo={backToList?.href ?? "/payments"}
          backLabel={backToList?.label ?? "Back to Payments"}
        />
      </>
    );
  }
  if (!detail.data) {
    return (
      <>
        <PageHeader title="Payment" />
        <LoadingState rows={6} />
      </>
    );
  }
  const p = detail.data;

  const attemptColumns: Column<AttemptItem>[] = [
    { key: "n", header: "#", render: (a) => <span className="num">{a.attempt_number}</span> },
    { key: "at", header: "Attempted", render: (a) => <Timestamp iso={a.created_at} mode="full" /> },
    { key: "outcome", header: "Outcome", render: (a) => <StatusBadge status={a.outcome} label={a.outcome_label} /> },
    { key: "reason", header: "Recorded reason", render: (a) => a.failure_message ?? <span className="muted">—</span> },
    { key: "method", header: "Method", render: (a) => a.method.label },
    { key: "completed", header: "Completed", render: (a) => <Timestamp iso={a.completed_at} mode="full" sameDayAs={a.created_at} /> },
  ];
  const refundColumns: Column<RefundItem>[] = [
    { key: "at", header: "Requested", render: (r) => <Timestamp iso={r.created_at} mode="full" /> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} label={r.status_label} /> },
    { key: "reason", header: "Reason", render: (r) => r.reason_label },
    { key: "completed", header: "Completed", render: (r) => <Timestamp iso={r.completed_at} mode="full" sameDayAs={r.created_at} /> },
    { key: "amount", header: "Amount", align: "right", render: (r) => <Money cents={-r.amount_cents} sign /> },
  ];

  const customerValue = p.customer ? (
    can("customers:read") ? (
      <Link to={`/customers/${p.customer.id}`}>{p.customer.full_name}</Link>
    ) : (
      p.customer.full_name
    )
  ) : (
    <span className="muted">Guest checkout</span>
  );
  const payoutValue = p.payout ? (
    <span>
      {can("payouts:read") ? <Link to={`/payouts/${p.payout.id}`}>Payout {p.payout.status_label.toLowerCase()}</Link> : <>Payout {p.payout.status_label.toLowerCase()}</>}
      {p.payout.paid_at ? (
        <>
          {" · "}
          <Timestamp iso={p.payout.paid_at} />
        </>
      ) : null}
    </span>
  ) : p.funds_available_at ? (
    <span>
      Awaiting payout · funds available <Timestamp iso={p.funds_available_at} mode="relative" />
    </span>
  ) : (
    <span className="muted">Not collected</span>
  );
  const disputeValue = p.dispute ? (
    <span className="inline-badge">
      <StatusBadge status={p.dispute.status} label={p.dispute.status_label} />
      {can("disputes:read") ? <Link to={`/disputes/${p.dispute.id}`}>View dispute</Link> : null}
    </span>
  ) : (
    <span className="muted">None</span>
  );

  return (
    <>
      <PageHeader
        above={
          backToList ? (
            <span className="breadcrumb-links">
              <Link to={backToList.href}>
                <IconChevronLeft />
                {backToList.label}
              </Link>
              {backToHealth ? (
                <>
                  <span aria-hidden="true">·</span>
                  <Link to={backToHealth}>Back to Payment Health</Link>
                </>
              ) : null}
            </span>
          ) : (
            <Link to="/payments">
              <IconChevronLeft />
              Payments
            </Link>
          )
        }
        title={
          <span className="detail-title">
            <span className="mono">{p.order_reference}</span>
            <StatusBadge status={p.status} label={p.status_label} />
          </span>
        }
        subtitle={
          <>
            Payment <span className="mono">{p.id}</span> · {p.location ? `${p.channel_label} · ${p.location.name}` : p.channel_label}
          </>
        }
        actions={
          <div className="detail-actions">
            {backToList && can("notes:write") ? (
              // In an investigation the note is the next step; this takes the person to the existing composer.
              <button type="button" className="btn btn-sm" onClick={focusNoteComposer}>
                Add investigation note
              </button>
            ) : null}
            <div className="detail-amount">
              <Money cents={p.amount_cents} className="detail-amount-value" />
              {p.refunded_cents > 0 ? (
                <span className="muted">
                  Net <Money cents={p.net_cents} /> after refunds
                </span>
              ) : null}
            </div>
          </div>
        }
      />

      <section className="card detail-summary" aria-label="Payment summary">
        <DescriptionList
          columns={3}
          items={[
            { term: "Created", value: <Timestamp iso={p.created_at} mode="full" /> },
            { term: "Customer", value: customerValue },
            { term: "Channel", value: p.location ? `${p.channel_label} · ${p.location.name}` : p.channel_label },
            { term: "Method", value: p.method?.label ?? <span className="muted">—</span> },
            { term: "Description", value: p.description },
            { term: "Payout", value: payoutValue },
            { term: "Dispute", value: disputeValue },
            { term: "Refunded", value: p.refunded_cents > 0 ? <Money cents={p.refunded_cents} /> : <span className="muted">None</span> },
            { term: "Payment ID", value: <span className="mono">{p.id}</span> },
          ]}
        />
      </section>

      <div className="detail-stack detail-tables">
        <section aria-labelledby="attempts-heading">
          <h2 id="attempts-heading" className="section-title">
            Attempts
          </h2>
          <AttemptChain attempts={p.attempts} />
          <DataTable caption="Payment attempts" columns={attemptColumns} rows={p.attempts} rowKey={(a) => a.id} />
        </section>

        <section aria-labelledby="refunds-heading">
          <h2 id="refunds-heading" className="section-title">
            Refunds
          </h2>
          {p.refunds.length === 0 ? (
            <EmptyState title="No refunds" body="Refunds issued against this payment appear here with their reason." />
          ) : (
            <DataTable caption="Refunds" columns={refundColumns} rows={p.refunds} rowKey={(r) => r.id} />
          )}
        </section>
      </div>

      <div className="detail-grid">
        <section className="card" aria-labelledby="timeline-heading">
          <h2 id="timeline-heading" className="section-title">
            Timeline
          </h2>
          <Timeline events={p.timeline} />
        </section>

        <div className="detail-stack">
          <section className="card" aria-labelledby="notes-heading">
            <h2 id="notes-heading" className="section-title">
              Investigation notes
            </h2>
            {p.notes.length === 0 ? <p className="muted">No notes yet.</p> : null}
            <ul className="notes">
              {p.notes.map((n) => (
                <li key={n.id} className="note">
                  <p className="note-body">{n.body}</p>
                  <p className="note-meta">
                    {n.actor.full_name} · <Timestamp iso={n.created_at} mode="full" />
                  </p>
                </li>
              ))}
            </ul>
            {can("notes:write") ? (
              <NoteComposer postPath={`/api/payments/${encodeURIComponent(p.id)}/notes`} label="Add a note" onSaved={() => detail.reload()} />
            ) : (
              <p className="muted note-readonly">Notes are read-only for your role.</p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

function focusNoteComposer() {
  const field = document.getElementById("note-body");
  field?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  field?.focus({ preventScroll: true });
}

/**
 * The attempts read as one customer's story: a summary line from the recorded attempts, then each attempt with its
 * outcome and recorded signal in order. The table below keeps the full detail (times, method, completion).
 */
function AttemptChain({ attempts }: { attempts: AttemptItem[] }) {
  const ordered = [...attempts].sort((a, b) => a.attempt_number - b.attempt_number);
  return (
    <div className="attempt-chain" aria-label="Attempt chain">
      <p className="attempt-chain-summary">{attemptChainSummary(ordered)}</p>
      {ordered.length > 0 ? (
        <ol className="attempt-chain-steps" role="list">
          {ordered.map((a, i) => (
            <li key={a.id} className="attempt-chain-step">
              {i > 0 ? (
                <span className="attempt-chain-arrow" aria-hidden="true">
                  →
                </span>
              ) : null}
              <span className="attempt-chain-chip">
                <span className="attempt-chain-number">Attempt {a.attempt_number}</span>
                <StatusBadge status={a.outcome} label={a.outcome_label} />
                {a.failure_message ? <span className="attempt-chain-signal">{a.failure_message}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
