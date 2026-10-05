import { Link, useNavigate, useParams } from "react-router-dom";
import type { CustomerDetail, CustomerRefundItem } from "../../api/customers-types";
import type { PaymentListItem } from "../../api/payments-types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { IconChevronLeft } from "../../layout/icons";

export function CustomerDetailPage() {
  const { customerId = "" } = useParams();
  const navigate = useNavigate();
  const detail = useApi<CustomerDetail>(`/api/customers/${encodeURIComponent(customerId)}`);

  if (detail.error) {
    return (
      <>
        <PageHeader title="Customer" />
        <LoadError error={detail.error} onRetry={detail.reload} what="customer" backTo="/customers" backLabel="Back to Customers" />
      </>
    );
  }
  if (!detail.data) {
    return (
      <>
        <PageHeader title="Customer" />
        <LoadingState rows={6} />
      </>
    );
  }
  const c = detail.data;
  const paymentColumns: Column<PaymentListItem>[] = [
    {
      key: "created_at",
      header: "Created",
      render: (p) => (
        <Link to={`/payments/${p.id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          <Timestamp iso={p.created_at} />
        </Link>
      ),
    },
    { key: "order", header: "Order", className: "secondary", render: (p) => <span className="mono">{p.order_reference}</span> },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "channel", header: "Channel", render: (p) => (p.location ? `${p.channel_label} · ${p.location.name}` : p.channel_label) },
    { key: "method", header: "Method", render: (p) => p.method?.label ?? <span className="muted">—</span> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  const refundColumns: Column<CustomerRefundItem>[] = [
    { key: "at", header: "Requested", render: (r) => <Timestamp iso={r.created_at} /> },
    {
      key: "order",
      header: "Order",
      render: (r) => (
        <Link to={`/payments/${r.payment_id}`} className="mono">
          {r.order_reference}
        </Link>
      ),
    },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} label={r.status_label} /> },
    { key: "reason", header: "Reason", render: (r) => r.reason_label },
    { key: "completed", header: "Completed", render: (r) => <Timestamp iso={r.completed_at} /> },
    { key: "amount", header: "Amount", align: "right", render: (r) => <Money cents={-r.amount_cents} sign /> },
  ];

  return (
    <>
      <PageHeader
        above={
          <Link to="/customers">
            <IconChevronLeft />
            Customers
          </Link>
        }
        title={c.full_name}
        subtitle={
          <>
            Customer <span className="mono">{c.reference}</span> · {c.email}
          </>
        }
      />
      <section className="card detail-summary" aria-label="Customer summary">
        <DescriptionList
          columns={3}
          items={[
            { term: "Email", value: c.email },
            { term: "Reference", value: <span className="mono">{c.reference}</span> },
            { term: "Customer since", value: <Timestamp iso={c.created_at} mode="full" /> },
            { term: "First payment", value: <Timestamp iso={c.first_payment_at} mode="full" /> },
            { term: "Recent activity", value: <Timestamp iso={c.last_activity_at} mode="full" /> },
            { term: "Customer ID", value: <span className="mono">{c.id}</span> },
          ]}
        />
      </section>
      <section aria-labelledby="customer-payments-heading" className="detail-summary">
        <h2 id="customer-payments-heading" className="section-title">
          Payments
        </h2>
        {c.payments.length === 0 ? (
          <EmptyState title="No payments yet" body="Payments by this customer appear here." />
        ) : (
          <DataTable caption="Payments by this customer" columns={paymentColumns} rows={c.payments} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />
        )}
      </section>
      <section aria-labelledby="customer-refunds-heading">
        <h2 id="customer-refunds-heading" className="section-title">
          Refunds
        </h2>
        {c.refunds.length === 0 ? (
          <EmptyState title="No refunds" body="Refunds issued to this customer appear here with their reason." />
        ) : (
          <DataTable caption="Refunds to this customer" columns={refundColumns} rows={c.refunds} rowKey={(r) => r.id} />
        )}
      </section>
    </>
  );
}
