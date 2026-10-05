import type { ReactNode } from "react";
import { queryString } from "../../api/client";
import type { Meta, Permission } from "../../api/types";
import { useApi } from "../../api/useApi";
import { FilterBar, FilterDate, FilterSelect } from "../../components/FilterBar";
import { ErrorState, ForbiddenState, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { IconDownload } from "../../layout/icons";
import { useQueryState, type QueryState } from "../../lib/query";
import { scopedQuery } from "../../lib/scopedQuery";
import { useSession } from "../../session/SessionProvider";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";

/**
 * Four CSV exports, each honouring its own filters (kept in the URL under a prefix) and the active business.
 * The browser downloads straight from the API, which checks the permission again and records the export.
 */
export function ReportsPage() {
  const { can, session } = useSession();
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const operational = can("reports:operational");
  const financial = can("reports:financial");

  if (!operational && !financial) {
    return (
      <>
        <PageHeader title="Reports" />
        <ForbiddenState />
      </>
    );
  }
  return (
    <>
      <PageHeader title="Reports" subtitle={`Export payment, payout, refund and operational records for ${session?.merchant.name ?? "this business"} as CSV. Each download honours its filters and is recorded under Settings → Activity.`} />
      {meta.loading && !meta.data ? <LoadingState rows={4} /> : null}
      {meta.error ? <ErrorState error={meta.error} onRetry={meta.reload} /> : null}
      {meta.data ? (
        <div className="report-grid">
          {operational ? <PaymentRegisterCard meta={meta.data} query={scopedQuery(query, "pr")} /> : null}
          {operational ? <AttemptExportCard meta={meta.data} query={scopedQuery(query, "ar")} /> : null}
          {financial ? <PayoutReconciliationCard meta={meta.data} query={scopedQuery(query, "po")} /> : null}
          {financial ? <RefundRegisterCard meta={meta.data} query={scopedQuery(query, "rr")} /> : null}
        </div>
      ) : null}
    </>
  );
}

function ReportCard({ id, title, description, permission, href, children }: { id: string; title: string; description: string; permission: Permission; href: string; children: ReactNode }) {
  return (
    <section className="card report-card" aria-labelledby={`${id}-title`} data-permission={permission}>
      <h2 id={`${id}-title`} className="section-title">
        {title}
      </h2>
      <p className="muted report-description">{description}</p>
      <FilterBar>{children}</FilterBar>
      <div className="report-actions">
        <a className="btn" href={href} download data-report={id}>
          <IconDownload />
          Download CSV
        </a>
      </div>
    </section>
  );
}

function PaymentRegisterCard({ meta, query }: { meta: Meta; query: QueryState }) {
  const params = { ...periodParams(query), status: query.get("status") || undefined, channel: query.get("channel") || undefined, location_id: query.get("location_id") || undefined };
  return (
    <ReportCard id="payments" title="Payment register" description="One row per payment with its status, channel, masked method, amounts and customer." permission="reports:operational" href={`/api/reports/payments.csv${queryString(params)}`}>
      <PeriodFilter query={query} presets={meta.period_presets} idPrefix="pr-period" />
      <FilterSelect id="pr-status" label="Status" value={query.get("status")} options={meta.payment_statuses} onChange={(v) => query.set({ status: v })} />
      <FilterSelect id="pr-channel" label="Channel" value={query.get("channel")} options={meta.channels} onChange={(v) => query.set({ channel: v })} />
      {meta.locations.length > 0 ? (
        <FilterSelect id="pr-location" label="Location" value={query.get("location_id")} options={meta.locations.map((l) => ({ value: l.id, label: l.name }))} onChange={(v) => query.set({ location_id: v })} />
      ) : null}
    </ReportCard>
  );
}

function AttemptExportCard({ meta, query }: { meta: Meta; query: QueryState }) {
  const params = { ...periodParams(query), outcome: query.get("outcome") || undefined, channel: query.get("channel") || undefined, location_id: query.get("location_id") || undefined };
  return (
    <ReportCard id="attempts" title="Payment attempt export" description="One row per attempt with its outcome and the recorded reason when it was declined." permission="reports:operational" href={`/api/reports/attempts.csv${queryString(params)}`}>
      <PeriodFilter query={query} presets={meta.period_presets} idPrefix="ar-period" />
      <FilterSelect id="ar-outcome" label="Outcome" value={query.get("outcome")} options={meta.attempt_outcomes} onChange={(v) => query.set({ outcome: v })} />
      <FilterSelect id="ar-channel" label="Channel" value={query.get("channel")} options={meta.channels} onChange={(v) => query.set({ channel: v })} />
    </ReportCard>
  );
}

function PayoutReconciliationCard({ meta, query }: { meta: Meta; query: QueryState }) {
  const from = query.get("from");
  const to = query.get("to");
  const params = { status: query.get("status") || undefined, from: from && to ? from : undefined, to: from && to ? to : undefined };
  return (
    <ReportCard id="payouts" title="Payout reconciliation" description="One row per payout: collections, fees, refunds, disputes and adjustments, and the amount they reconcile to." permission="reports:financial" href={`/api/reports/payouts.csv${queryString(params)}`}>
      <FilterSelect id="po-status" label="Status" value={query.get("status")} options={meta.payout_statuses} onChange={(v) => query.set({ status: v })} />
      <FilterDate id="po-from" label="Payout date from" value={from} max={to || undefined} onChange={(v) => query.set({ from: v })} />
      <FilterDate id="po-to" label="Payout date to" value={to} min={from || undefined} onChange={(v) => query.set({ to: v })} />
    </ReportCard>
  );
}

function RefundRegisterCard({ meta, query }: { meta: Meta; query: QueryState }) {
  const params = { ...periodParams(query), status: query.get("status") || undefined, reason: query.get("reason") || undefined };
  return (
    <ReportCard id="refunds" title="Refund register" description="One row per refund with its status, reason, amount and the payment it belongs to." permission="reports:financial" href={`/api/reports/refunds.csv${queryString(params)}`}>
      <PeriodFilter query={query} presets={meta.period_presets} idPrefix="rr-period" />
      <FilterSelect id="rr-status" label="Status" value={query.get("status")} options={meta.refund_statuses} onChange={(v) => query.set({ status: v })} />
      <FilterSelect id="rr-reason" label="Reason" value={query.get("reason")} options={meta.refund_reasons} onChange={(v) => query.set({ reason: v })} />
    </ReportCard>
  );
}
