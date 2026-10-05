import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { CustomerListItem, CustomerListResponse } from "../../api/customers-types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSearch } from "../../components/FilterBar";
import { Pagination } from "../../components/Pagination";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { useQueryState } from "../../lib/query";

const PAGE_SIZE = 25;

export function CustomersPage() {
  const query = useQueryState();
  const navigate = useNavigate();
  const sort = query.get("sort", "last_activity_at");
  const dir: "asc" | "desc" = query.get("dir", sort === "last_activity_at" ? "desc" : "asc") === "asc" ? "asc" : "desc";
  const params = { q: query.get("q") || undefined, sort, dir, page: query.getInt("page", 1), page_size: PAGE_SIZE };
  const list = useApi<CustomerListResponse>(`/api/customers${queryString(params)}`);

  const columns: Column<CustomerListItem>[] = [
    {
      key: "name",
      header: "Name",
      sortKey: "name",
      className: "primary",
      render: (c) => (
        <Link to={`/customers/${c.id}`} className="row-link" onClick={(e) => e.stopPropagation()}>
          {c.full_name}
        </Link>
      ),
    },
    { key: "email", header: "Email", sortKey: "email", render: (c) => c.email },
    { key: "reference", header: "Reference", sortKey: "reference", className: "secondary", render: (c) => <span className="mono">{c.reference}</span> },
    { key: "first", header: "First payment", sortKey: "first_payment_at", render: (c) => <Timestamp iso={c.first_payment_at} /> },
    { key: "recent", header: "Recent activity", sortKey: "last_activity_at", render: (c) => <Timestamp iso={c.last_activity_at} /> },
  ];

  function onSort(key: string) {
    const nextDir = sort === key && dir === "asc" ? "desc" : "asc";
    query.set({ sort: key, dir: nextDir });
  }

  return (
    <>
      <PageHeader title="Customers" subtitle="Shoppers who have paid this business. Guest checkouts are not included." />
      <FilterBar>
        <FilterSearch id="customers-search" label="Search" value={query.get("q")} placeholder="Name, email or reference" onChange={(v) => query.set({ q: v })} />
      </FilterBar>
      {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : null}
      {!list.error && !list.data && list.loading ? <LoadingState rows={8} /> : null}
      {list.data && list.data.items.length === 0 ? <EmptyState title="No customers match" body="Try another name, email or reference." /> : null}
      {list.data && list.data.items.length > 0 ? (
        <>
          <DataTable
            caption="Customers"
            columns={columns}
            rows={list.data.items}
            rowKey={(c) => c.id}
            sort={{ sort, dir }}
            onSort={onSort}
            onRowClick={(c) => navigate(`/customers/${c.id}`)}
            loading={list.loading}
          />
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(p) => query.set({ page: p })} />
        </>
      ) : null}
    </>
  );
}
