import { Link } from "react-router-dom";
import { queryString } from "../../api/client";
import type { FailureSignal, PaymentHealth } from "../../api/payment-health-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { BarChart } from "../../components/BarChart";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCount, formatDateShort, formatRateBp, formatTimestampFull } from "../../lib/format";
import { useQueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";
import { unresolvedPaymentsHref } from "./links";

export function PaymentHealthPage() {
  const query = useQueryState();
  const channel = query.get("channel");
  const meta = useApi<Meta>("/api/meta");
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString({ ...periodParams(query), channel })}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment health"
        subtitle={data ? `${data.channel_label} · ${data.period.range_label} · As of ${formatTimestampFull(data.as_of)}` : undefined}
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect
                id="health-channel"
                label="Channel"
                value={channel}
                options={meta.data.channels}
                allLabel="All channels"
                onChange={(value) => query.set({ channel: value })}
              />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !data ? <LoadingState rows={8} /> : null}
      {data ? <HealthBody data={data} loading={health.loading} /> : null}
    </>
  );
}

function HealthBody({ data, loading }: { data: PaymentHealth; loading: boolean }) {
  const { attempts, recovery } = data;
  if (attempts.completed === 0 && recovery.affected_payments === 0) {
    return (
      <EmptyState
        title="No completed attempts in this period"
        body={
          attempts.pending_excluded > 0
            ? `${pendingText(attempts.pending_excluded)} still pending. A success rate needs at least one succeeded or failed attempt.`
            : "A success rate needs at least one succeeded or failed attempt. Try a longer period or another channel."
        }
      />
    );
  }
  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <div className="cards cards-4">
        <section className="card stat-card" aria-label="Attempt success rate">
          <p className="stat-label">Attempt success rate</p>
          <p className="stat-value">{attempts.success_rate_bp === null ? "No completed attempts" : formatRateBp(attempts.success_rate_bp)}</p>
          <p className="stat-foot">
            {formatCount(attempts.succeeded)} succeeded of {formatCount(attempts.completed)} completed · {formatCount(attempts.pending_excluded)} pending excluded
          </p>
          {attempts.low_volume && attempts.completed > 0 ? (
            <p className="stat-foot health-caveat" role="note">
              Low volume: fewer than {attempts.low_volume_threshold} completed attempts, not enough to judge.
            </p>
          ) : null}
        </section>
        <section className="card stat-card" aria-label="Failed attempts">
          <p className="stat-label">Failed attempts</p>
          <p className="stat-value">{formatCount(attempts.failed)}</p>
          <p className="stat-foot">Attempts created in this period</p>
        </section>
        <section className="card stat-card" aria-label="Affected payments">
          <p className="stat-label">Affected payments</p>
          <p className="stat-value">{formatCount(recovery.affected_payments)}</p>
          <p className="stat-foot">
            {formatCount(recovery.recovered)} recovered ({formatCount(recovery.recovered_within_hour)} within 1 hour) · {formatCount(recovery.unresolved)} unresolved
          </p>
          {recovery.attempt_pending > 0 ? <p className="stat-foot">{formatCount(recovery.attempt_pending)} with an attempt still pending</p> : null}
        </section>
        <section className="card stat-card" aria-label="Affected payment value">
          <p className="stat-label">Affected payment value</p>
          <p className="stat-value">
            <Money cents={recovery.affected_cents} />
          </p>
          <p className="stat-foot">
            <Money cents={recovery.recovered_cents} /> recovered · <Money cents={recovery.unresolved_cents} /> unresolved
          </p>
        </section>
      </div>

      <section className="card chart-card" aria-labelledby="health-trend-heading">
        <div className="section-head">
          <h2 id="health-trend-heading" className="section-title">
            Failed attempts by day
          </h2>
          <p className="muted section-aside">
            {attempts.success_rate_bp === null ? "No completed attempts" : `${formatRateBp(attempts.success_rate_bp)} success rate`} · {data.period.range_label}
          </p>
        </div>
        <BarChart
          title={`Failed attempts by day, ${data.channel_label}, ${data.period.range_label}`}
          series={data.trend.points.map((p) => ({ label: formatDateShort(p.day), value: p.failed }))}
          formatValue={(v) => `${formatCount(v)} failed`}
          formatTick={formatCount}
        />
      </section>

      <div className="health-grid">
        <section className="card" aria-labelledby="health-signals-heading">
          <div className="section-head">
            <h2 id="health-signals-heading" className="section-title">
              Recorded failure signals
            </h2>
            <p className="muted section-aside">{formatCount(data.failure_signals.total_failed)} failed attempts</p>
          </div>
          <p className="muted health-note">Codes recorded on declined attempts. They are signals, not confirmed root causes.</p>
          <FailureSignalTable items={data.failure_signals.items} total={data.failure_signals.total_failed} />
        </section>

        <section className="card" aria-labelledby="health-recovery-heading">
          <div className="section-head">
            <h2 id="health-recovery-heading" className="section-title">
              Recovery after a failed attempt
            </h2>
          </div>
          <p className="muted health-note">Counted once per payment created in this period, however many attempts it took.</p>
          <dl className="bucket-list">
            <RecoveryRow label="Affected payments" count={recovery.affected_payments} cents={recovery.affected_cents} />
            <RecoveryRow label="Recovered on a later attempt" count={recovery.recovered} cents={recovery.recovered_cents} />
            <RecoveryRow label="Recovered within 1 hour" count={recovery.recovered_within_hour} />
            <RecoveryRow label="Unresolved" count={recovery.unresolved} cents={recovery.unresolved_cents} />
            {recovery.attempt_pending > 0 ? <RecoveryRow label="Attempt still pending" count={recovery.attempt_pending} cents={recovery.attempt_pending_cents} /> : null}
          </dl>
          {recovery.unresolved > 0 ? (
            <p className="health-action">
              <Link to={unresolvedPaymentsHref(data.period, data.channel)}>Review unresolved payments</Link>
            </p>
          ) : null}
        </section>
      </div>
    </div>
  );
}

function pendingText(n: number): string {
  return `${formatCount(n)} attempt${n === 1 ? " is" : "s are"}`;
}

/** Share of failed attempts in basis points, half-up, integer arithmetic. */
function shareBp(count: number, total: number): number {
  return Math.floor((2 * 10000 * count + total) / (2 * total));
}

function FailureSignalTable({ items, total }: { items: FailureSignal[]; total: number }) {
  if (items.length === 0) return <p className="muted">No failed attempts in this period.</p>;
  const columns: Column<FailureSignal>[] = [
    {
      key: "label",
      header: "Recorded signal",
      className: "primary",
      render: (s) => (
        <>
          {s.label}
          <span className="mono health-code">{s.failure_code}</span>
        </>
      ),
    },
    { key: "count", header: "Failed attempts", align: "right", render: (s) => formatCount(s.count) },
    { key: "share", header: "Share", align: "right", render: (s) => formatRateBp(shareBp(s.count, total)) },
  ];
  return <DataTable caption="Recorded failure signals" columns={columns} rows={items} rowKey={(s) => s.failure_code} />;
}

function RecoveryRow({ label, count, cents }: { label: string; count: number; cents?: number }) {
  return (
    <div className="bucket-row">
      <dt>{label}</dt>
      <dd className="money">
        {formatCount(count)}
        {cents === undefined ? null : (
          <>
            {" · "}
            <Money cents={cents} />
          </>
        )}
      </dd>
    </div>
  );
}
