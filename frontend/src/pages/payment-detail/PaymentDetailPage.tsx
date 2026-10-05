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
import { useSession } from "../../session/SessionProvider";

export function PaymentDetailPage() {
  const { paymentId = "" } = useParams();
  const { can } = useSession();
  const detail = useApi<PaymentDetail>(`/api/payments/${encodeURIComponent(paymentId)}`);

  if (detail.error) {
    return (
      <>
        <PageHeader title="Payment" />
        <LoadError error={detail.error} onRetry={detail.reload} what="payment" backTo="/payments" backLabel="Back to Payments" />
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
    { key: "completed", header: "Completed", render: (a) => <Timestamp iso={a.completed_at} mode="full" /> },
  ];
  const refundColumns: Column<RefundItem>[] = [
    { key: "at", header: "Requested", render: (r) => <Timestamp iso={r.created_at} mode="full" /> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} label={r.status_label} /> },
    { key: "reason", header: "Reason", render: (r) => r.reason_label },
    { key: "completed", header: "Completed", render: (r) => <Timestamp iso={r.completed_at} mode="full" /> },
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
    <span className="inline-badge">
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
        title={
          <span className="detail-title">
            <span className="mono">{p.order_reference}</span>
            <StatusBadge status={p.status} label={p.status_label} />
          </span>
        }
        subtitle={
          <>
            <Link to="/payments">Payments</Link> · Payment <span className="mono">{p.id}</span>
          </>
        }
        actions={
          <div className="detail-amount">
            <Money cents={p.amount_cents} className="detail-amount-value" />
            {p.refunded_cents > 0 ? (
              <span className="muted">
                Net <Money cents={p.net_cents} /> after refunds
              </span>
            ) : null}
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
            { term: "Payment id", value: <span className="mono">{p.id}</span> },
          ]}
        />
      </section>

      <div className="detail-grid">
        <section className="card" aria-labelledby="timeline-heading">
          <h2 id="timeline-heading" className="section-title">
            Timeline
          </h2>
          <Timeline events={p.timeline} />
        </section>

        <div className="detail-stack">
          <section aria-labelledby="attempts-heading">
            <h2 id="attempts-heading" className="section-title">
              Attempts
            </h2>
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
