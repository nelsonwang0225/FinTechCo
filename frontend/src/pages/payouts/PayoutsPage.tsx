import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { FundsSummary, PayoutListItem, PayoutListResponse } from "../../api/payouts-types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterDate, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatDate, formatTimestampFull, formatWeekdayDate } from "../../lib/format";
import { useQueryState } from "../../lib/query";

const PAGE_SIZE = 25;
const STATUS_OPTIONS = [
  { value: "in_transit", label: "In transit" },
  { value: "paid", label: "Paid" },
];

export function PayoutsPage() {
  const query = useQueryState();
  const navigate = useNavigate();
  const from = query.get("from");
  const to = query.get("to");
  const params = {
    status: query.get("status") || undefined,
    from: from && to ? from : undefined,
    to: from && to ? to : undefined,
    page: query.getInt("page", 1),
    page_size: PAGE_SIZE,
  };
  const list = useApi<PayoutListResponse>(`/api/payouts${queryString(params)}`);

  const columns: Column<PayoutListItem>[] = [
    {
      key: "date",
      header: "Payout date",
      className: "primary",
      render: (p) => (
        <Link to={`/payouts/${p.id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          {formatWeekdayDate(p.payout_date)}
        </Link>
      ),
    },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "sent", header: "Sent", render: (p) => <Timestamp iso={p.sent_at} /> },
    {
      key: "arrival",
      header: "Arrival",
      render: (p) => (p.paid_at ? <Timestamp iso={p.paid_at} /> : <span className="muted">Expected {formatDate(p.expected_arrival_date)}</span>),
    },
    {
      key: "destination",
      header: "Destination",
      render: (p) => (
        <span className="muted cell-truncate" title={p.destination}>
          {p.destination}
        </span>
      ),
    },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];

  return (
    <>
      <PageHeader title="Payouts" subtitle="Track funds moving from payment activity to your bank account. Each payout is itemised to the cent." />
      {list.data ? <FundsCards summary={list.data.summary} /> : null}
      <FilterBar>
        <FilterSelect id="payouts-status" label="Status" value={query.get("status")} options={STATUS_OPTIONS} onChange={(v) => query.set({ status: v })} />
        <FilterDate id="payouts-from" label="From" value={from} max={to || undefined} onChange={(v) => query.set({ from: v })} />
        <FilterDate id="payouts-to" label="To" value={to} min={from || undefined} onChange={(v) => query.set({ to: v })} />
      </FilterBar>
      {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : null}
      {!list.error && !list.data && list.loading ? <LoadingState rows={6} /> : null}
      {list.data && list.data.items.length === 0 ? <EmptyState title="No payouts match" body="Try a wider date range or clear the status filter." /> : null}
      {list.data && list.data.items.length > 0 ? (
        <>
          <DataTable caption="Payouts" columns={columns} rows={list.data.items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payouts/${p.id}`)} loading={list.loading} />
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(p) => query.set({ page: p })} />
        </>
      ) : null}
    </>
  );
}

/** Funds available for payout and the upcoming payout. Labelled as an estimate as of the reporting clock, never a balance. */
export function FundsCards({ summary }: { summary: FundsSummary }) {
  return (
    <div className="cards">
      <section className="card stat-card" aria-label="Funds available for payout">
        <p className="stat-label">Funds available for payout</p>
        <p className="stat-value">
          <Money cents={summary.available_cents} />
        </p>
        <p className="stat-foot">As of {formatTimestampFull(summary.as_of)}</p>
      </section>
      <section className="card stat-card" aria-label="Pending funds">
        <p className="stat-label">Pending, not yet available</p>
        <p className="stat-value">
          <Money cents={summary.pending_cents} />
        </p>
        <p className="stat-foot">Collected funds that become available two days after settlement</p>
      </section>
      <section className="card stat-card" aria-label="Next payout">
        <p className="stat-label">Next payout · {formatWeekdayDate(summary.next_payout.payout_date)}</p>
        <p className="stat-value">
          <Money cents={summary.next_payout.amount_cents} />
        </p>
        <p className="stat-foot">
          {summary.next_payout.schedule_label} · {summary.next_payout.note}
        </p>
        <p className="stat-foot muted">{summary.destination}</p>
      </section>
    </div>
  );
}
