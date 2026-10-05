import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { DisputeListItem, DisputeListResponse } from "../../api/disputes-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { ActiveFilters, type Chip } from "../../components/ActiveFilters";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { Pagination } from "../../components/Pagination";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, ErrorState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatDate } from "../../lib/format";
import { useQueryState } from "../../lib/query";
import { useCurrentSession } from "../../session/SessionProvider";
import { Deadline } from "./Deadline";

const PAGE_SIZE = 25;

export function DisputesPage() {
  const query = useQueryState();
  const navigate = useNavigate();
  const meta = useApi<Meta>("/api/meta");
  const sort = query.get("sort", "queue");
  const dir: "asc" | "desc" = query.get("dir", "asc") === "desc" ? "desc" : "asc";
  const params = {
    status: query.get("status") || undefined,
    reason: query.get("reason") || undefined,
    sort,
    dir,
    page: query.getInt("page", 1),
    page_size: PAGE_SIZE,
  };
  const list = useApi<DisputeListResponse>(`/api/disputes${queryString(params)}`);

  const chips = useMemo<Chip[]>(() => {
    const out: Chip[] = [];
    const label = (options: { value: string; label: string }[] | undefined, value: string) => options?.find((o) => o.value === value)?.label ?? value;
    if (query.get("status")) out.push({ key: "status", label: `Status: ${label(meta.data?.dispute_statuses, query.get("status"))}`, onRemove: () => query.set({ status: null }) });
    if (query.get("reason")) out.push({ key: "reason", label: `Reason: ${label(meta.data?.dispute_reasons, query.get("reason"))}`, onRemove: () => query.set({ reason: null }) });
    return out;
  }, [query, meta.data]);

  const columns: Column<DisputeListItem>[] = [
    {
      key: "opened",
      header: "Opened",
      sortKey: "opened_at",
      render: (d) => (
        <Link to={`/disputes/${d.id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          <Timestamp iso={d.opened_at} />
        </Link>
      ),
    },
    {
      key: "payment",
      header: "Payment",
      render: (d) => (
        <Link to={`/payments/${d.payment.id}`} className="mono" onClick={(e) => e.stopPropagation()}>
          {d.payment.order_reference}
        </Link>
      ),
    },
    { key: "customer", header: "Customer", render: (d) => d.payment.customer?.full_name ?? <span className="muted">Guest</span> },
    { key: "reason", header: "Reason", render: (d) => d.reason_label },
    { key: "status", header: "Status", sortKey: "status", render: (d) => <StatusBadge status={d.status} label={d.status_label} /> },
    { key: "deadline", header: "Response deadline", sortKey: "due", render: (d) => <DeadlineCell dispute={d} /> },
    { key: "amount", header: "Amount", align: "right", sortKey: "amount", render: (d) => <Money cents={d.amount_cents} /> },
  ];

  function onSort(key: string) {
    const nextDir = sort === key && dir === "asc" ? "desc" : "asc";
    query.set({ sort: key, dir: nextDir });
  }

  return (
    <>
      <PageHeader title="Disputes" subtitle="Chargebacks raised against payments. Cases needing a response come first." />
      {meta.error ? <ErrorState error={meta.error} onRetry={meta.reload} /> : null}
      {meta.data ? (
        <FilterBar>
          <FilterSelect id="disputes-status" label="Status" value={query.get("status")} options={meta.data.dispute_statuses} onChange={(v) => query.set({ status: v })} />
          <FilterSelect id="disputes-reason" label="Reason" value={query.get("reason")} options={meta.data.dispute_reasons} onChange={(v) => query.set({ reason: v })} />
        </FilterBar>
      ) : null}
      <ActiveFilters chips={chips} onClear={() => query.set({ status: null, reason: null })} />
      {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : null}
      {!list.error && !list.data && list.loading ? <LoadingState rows={5} /> : null}
      {list.data && list.data.items.length === 0 ? <EmptyState title="No disputes match" body="Clear a filter to see every case." /> : null}
      {list.data && list.data.items.length > 0 ? (
        <>
          <DataTable
            caption="Disputes"
            columns={columns}
            rows={list.data.items}
            rowKey={(d) => d.id}
            sort={sort === "queue" ? undefined : { sort, dir }}
            onSort={onSort}
            onRowClick={(d) => navigate(`/disputes/${d.id}`)}
            loading={list.loading}
          />
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(p) => query.set({ page: p })} />
        </>
      ) : null}
    </>
  );
}

function DeadlineCell({ dispute }: { dispute: DisputeListItem }) {
  const session = useCurrentSession();
  if (dispute.status === "needs_response") return <Deadline due={dispute.evidence_due_at} asOf={session.as_of} />;
  if (dispute.status === "under_review") return <span className="muted">Responded {dispute.responded_at ? formatDate(dispute.responded_at) : ""}</span>;
  return <span className="muted">Resolved {dispute.resolved_at ? formatDate(dispute.resolved_at) : ""}</span>;
}
