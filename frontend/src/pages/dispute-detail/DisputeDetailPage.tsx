import { Link, useParams } from "react-router-dom";
import type { DisputeDetail } from "../../api/disputes-types";
import { useApi } from "../../api/useApi";
import { DescriptionList } from "../../components/DescriptionList";
import { Money } from "../../components/Money";
import { NoteComposer } from "../../components/NoteComposer";
import { StatusBadge } from "../../components/StatusBadge";
import { Timeline } from "../../components/Timeline";
import { Timestamp } from "../../components/Timestamp";
import { LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { IconChevronLeft } from "../../layout/icons";
import { useCurrentSession, useSession } from "../../session/SessionProvider";
import { Deadline } from "../disputes/Deadline";

export function DisputeDetailPage() {
  const { disputeId = "" } = useParams();
  const { can } = useSession();
  const detail = useApi<DisputeDetail>(`/api/disputes/${encodeURIComponent(disputeId)}`);

  if (detail.error) {
    return (
      <>
        <PageHeader title="Dispute" />
        <LoadError error={detail.error} onRetry={detail.reload} what="dispute" backTo="/disputes" backLabel="Back to Disputes" />
      </>
    );
  }
  if (!detail.data) {
    return (
      <>
        <PageHeader title="Dispute" />
        <LoadingState rows={6} />
      </>
    );
  }
  const d = detail.data;
  return (
    <>
      <PageHeader
        title={
          <span className="detail-title">
            Dispute on <span className="mono">{d.payment.order_reference}</span>
            <StatusBadge status={d.status} label={d.status_label} />
          </span>
        }
        above={
          <Link to="/disputes">
            <IconChevronLeft />
            Disputes
          </Link>
        }
        subtitle={
          <>
            Dispute <span className="mono">{d.id}</span> · {d.reason_label}
          </>
        }
        actions={
          <div className="detail-amount">
            <Money cents={d.amount_cents} className="detail-amount-value" />
            <span className="muted">
              disputed of <Money cents={d.payment.amount_cents} />
            </span>
          </div>
        }
      />

      <section className="card detail-summary" aria-label="Dispute summary">
        <DescriptionList
          columns={3}
          items={[
            { term: "Reason", value: d.reason_label },
            { term: "Opened", value: <Timestamp iso={d.opened_at} mode="full" /> },
            { term: "Evidence due", value: <EvidenceDue dispute={d} /> },
            { term: "Responded", value: <Timestamp iso={d.responded_at} mode="full" /> },
            { term: "Resolved", value: <Timestamp iso={d.resolved_at} mode="full" /> },
            {
              term: "Payment",
              value: (
                <Link to={`/payments/${d.payment.id}`} className="mono">
                  {d.payment.order_reference}
                </Link>
              ),
            },
            {
              term: "Customer",
              value: d.payment.customer ? (
                can("customers:read") ? (
                  <Link to={`/customers/${d.payment.customer.id}`}>{d.payment.customer.full_name}</Link>
                ) : (
                  d.payment.customer.full_name
                )
              ) : (
                <span className="muted">Guest checkout</span>
              ),
            },
            { term: "Paid on", value: <Timestamp iso={d.payment.created_at} mode="full" /> },
            { term: "Dispute id", value: <span className="mono">{d.id}</span> },
          ]}
        />
      </section>

      <div className="detail-grid">
        <section className="card" aria-labelledby="history-heading">
          <h2 id="history-heading" className="section-title">
            Case history
          </h2>
          <Timeline events={d.history} />
        </section>
        <section className="card" aria-labelledby="dispute-notes-heading">
          <h2 id="dispute-notes-heading" className="section-title">
            Internal notes
          </h2>
          {d.notes.length === 0 ? <p className="muted">No notes yet.</p> : null}
          <ul className="notes">
            {d.notes.map((n) => (
              <li key={n.id} className="note">
                <p className="note-body">{n.body}</p>
                <p className="note-meta">
                  {n.actor.full_name} · <Timestamp iso={n.created_at} mode="full" />
                </p>
              </li>
            ))}
          </ul>
          {can("notes:write") ? (
            <NoteComposer postPath={`/api/disputes/${encodeURIComponent(d.id)}/notes`} label="Add a note" onSaved={() => detail.reload()} />
          ) : (
            <p className="muted note-readonly">Notes are read-only for your role.</p>
          )}
        </section>
      </div>
    </>
  );
}

function EvidenceDue({ dispute }: { dispute: DisputeDetail }) {
  const session = useCurrentSession();
  if (dispute.status === "needs_response") return <Deadline due={dispute.evidence_due_at} asOf={session.as_of} />;
  return <Timestamp iso={dispute.evidence_due_at} mode="full" />;
}
