import { Link, useParams } from "react-router-dom";
import type { MovementItem, PayoutDetail } from "../../api/payouts-types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { IconChevronLeft, IconDownload } from "../../layout/icons";
import { formatCount, formatDate, formatWeekdayDate } from "../../lib/format";
import { useQueryState } from "../../lib/query";
import { Pagination } from "../../components/Pagination";
import { useSession } from "../../session/SessionProvider";

export function PayoutDetailPage() {
  const { payoutId = "" } = useParams();
  const { can } = useSession();
  const query = useQueryState();
  const detail = useApi<PayoutDetail>(`/api/payouts/${encodeURIComponent(payoutId)}`);

  if (detail.error) {
    return (
      <>
        <PageHeader title="Payout" />
        <LoadError error={detail.error} onRetry={detail.reload} what="payout" backTo="/payouts" backLabel="Back to Payouts" />
      </>
    );
  }
  if (!detail.data) {
    return (
      <>
        <PageHeader title="Payout" />
        <LoadingState rows={6} />
      </>
    );
  }
  const p = detail.data;
  const pageSize = 25;
  const pages = Math.max(1, Math.ceil(p.movements.length / pageSize));
  const page = Math.min(Math.max(1, query.getInt("page", 1)), pages);
  const pagedMovements = p.movements.slice((page - 1) * pageSize, page * pageSize);
  const buckets: { label: string; cents: number }[] = [
    { label: "Collections", cents: p.buckets.collections_cents },
    { label: "Fees", cents: p.buckets.fees_cents },
    { label: "Refunds", cents: p.buckets.refunds_cents },
    { label: "Disputes", cents: p.buckets.disputes_cents },
    { label: "Adjustments", cents: p.buckets.adjustments_cents },
  ];
  const movementColumns: Column<MovementItem>[] = [
    { key: "posted", header: "Posted", render: (m) => <Timestamp iso={m.posted_at} /> },
    { key: "type", header: "Type", render: (m) => m.type_label },
    { key: "description", header: "Description", render: (m) => m.description },
    {
      key: "payment",
      header: "Payment",
      render: (m) =>
        m.payment_id ? (
          <Link to={`/payments/${m.payment_id}`} className="mono">
            {m.order_reference}
          </Link>
        ) : (
          <span className="muted">—</span>
        ),
    },
    { key: "customer", header: "Customer", render: (m) => m.customer_name ?? <span className="muted">—</span> },
    { key: "amount", header: "Amount", align: "right", render: (m) => <Money cents={m.amount_cents} sign /> },
  ];

  return (
    <>
      <PageHeader
        above={
          <Link to="/payouts">
            <IconChevronLeft />
            Payouts
          </Link>
        }
        title={
          <span className="detail-title">
            Payout · {formatWeekdayDate(p.payout_date)}
            <StatusBadge status={p.status} label={p.status_label} />
          </span>
        }
        subtitle={
          <>
            Payout <span className="mono">{p.id}</span> · {formatCount(p.movement_count)} movements
          </>
        }
        actions={
          <div className="detail-amount">
            <Money cents={p.amount_cents} className="detail-amount-value" />
            {can("reports:financial") ? (
              <a className="btn" href={`/api/payouts/${encodeURIComponent(p.id)}/export.csv`} download>
                <IconDownload />
                Download CSV
              </a>
            ) : null}
          </div>
        }
      />

      <div className="detail-grid-aside">
      <section className="card" aria-label="Payout summary">
        <h2 className="section-title">Payout details</h2>
        <DescriptionList
          columns={2}
          items={[
            { term: "Cutoff", value: <Timestamp iso={p.cutoff_at} mode="full" /> },
            { term: "Sent", value: <Timestamp iso={p.sent_at} mode="full" /> },
            { term: p.paid_at ? "Paid" : "Expected arrival", value: p.paid_at ? <Timestamp iso={p.paid_at} mode="full" /> : formatDate(p.expected_arrival_date) },
            { term: "Destination", value: p.destination },
            { term: "Movements", value: <span className="num">{formatCount(p.movement_count)}</span> },
            {
              term: "Reconciliation",
              value: p.reconciled ? (
                <span className="badge badge-success">
                  <span className="badge-dot" aria-hidden="true" />
                  Reconciled to the cent
                </span>
              ) : (
                <span className="badge badge-danger">
                  <span className="badge-dot" aria-hidden="true" />
                  Does not reconcile
                </span>
              ),
            },
          ]}
        />
      </section>

      <section className="card" aria-labelledby="recon-heading">
        <h2 id="recon-heading" className="section-title">
          What this payout is made of
        </h2>
        <table className="table recon-table">
          <caption className="visually-hidden">Reconciliation by movement type</caption>
          <tbody>
            {buckets.map((b) => (
              <tr key={b.label}>
                <th scope="row">{b.label}</th>
                <td className="money">
                  <Money cents={b.cents} sign />
                </td>
              </tr>
            ))}
            <tr className="recon-total">
              <th scope="row">Payout total</th>
              <td className="money">
                <Money cents={p.movement_total_cents} sign />
              </td>
            </tr>
          </tbody>
        </table>
      </section>
      </div>

      <section aria-labelledby="movements-heading">
        <h2 id="movements-heading" className="section-title">
          Movements
        </h2>
        <DataTable caption="Movements in this payout" columns={movementColumns} rows={pagedMovements} rowKey={(m) => m.id} />
        {p.movements.length > pageSize ? <Pagination page={page} pageSize={pageSize} total={p.movements.length} onPage={(n) => query.set({ page: n })} /> : null}
      </section>
    </>
  );
}
