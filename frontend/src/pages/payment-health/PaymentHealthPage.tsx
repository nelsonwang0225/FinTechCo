import { Link } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, FailureSignal, PaymentHealth, UnresolvedPayment } from "../../api/payment-health-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { Money } from "../../components/Money";
import { RateChart } from "../../components/RateChart";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCents, formatCount, formatDateShort, formatPointChange, formatRate, formatTimestampFull } from "../../lib/format";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";
import { failedAttemptsHref, healthScope, unresolvedPaymentsHref, type HealthScope } from "./healthLinks";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString({ ...periodParams(query), channel: query.get("channel") || undefined })}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment health"
        subtitle="Completed-attempt performance against each channel's own baseline, and what happened to the payments affected. Times are shown in America/Chicago."
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={query.get("channel")} options={meta.data.channels} onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !data ? <LoadingState rows={8} /> : null}
      {data ? <HealthBody data={data} loading={health.loading} query={query} scope={healthScope(query)} /> : null}
    </>
  );
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${formatCount(n)} ${n === 1 ? one : many}`;
}

function HealthBody({ data, loading, query, scope }: { data: PaymentHealth; loading: boolean; query: QueryState; scope: HealthScope }) {
  const a = data.attempts;
  const r = data.recovery;
  const channel = data.channel ?? undefined;
  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <p className="toolbar-note health-scope">
        <span>
          {data.channel_label} · {data.period.label}: {data.period.range_label} · Baseline {data.baseline.range_label} · As of {formatTimestampFull(data.as_of)}
        </span>
      </p>

      <AttentionSummary data={data} scope={scope} />

      <div className="cards cards-4">
        <section className="card stat-card" aria-label="Success rate">
          <p className="stat-label">Success rate · completed attempts</p>
          <p className="stat-value">{formatRate(a.success_rate_bp)}</p>
          <p className="stat-foot">
            Baseline {formatRate(a.baseline_success_rate_bp)} · {formatPointChange(a.change_bp)}
          </p>
          <p className="stat-foot">
            {plural(a.completed, "completed attempt")} · {formatCount(a.pending)} pending, not counted
          </p>
          {a.completed > 0 && (a.completed < data.rules.min_completed_attempts || a.baseline_completed < data.rules.min_completed_attempts) ? (
            <p className="stat-foot stat-caution">
              <strong>Low volume:</strong> fewer than {data.rules.min_completed_attempts} completed attempts here or in the baseline, so this is not compared.
            </p>
          ) : null}
        </section>
        <section className="card stat-card" aria-label="Failed attempts">
          <p className="stat-label">Failed attempts</p>
          <p className="stat-value num">{formatCount(a.failed)}</p>
          <p className="stat-foot">
            of {plural(a.completed, "completed attempt")} · {formatCount(a.succeeded)} succeeded
          </p>
          {a.failed > 0 ? (
            <p className="stat-foot">
              <Link to={failedAttemptsHref(scope, channel)}>View failed attempts</Link>
            </p>
          ) : null}
        </section>
        <section className="card stat-card" aria-label="Affected payments">
          <p className="stat-label">Affected payments</p>
          <p className="stat-value num">{formatCount(r.affected_payments)}</p>
          <p className="stat-foot">
            <Money cents={r.affected_cents} /> in payment amounts
          </p>
          <p className="stat-foot">
            {formatCount(r.recovered_payments)} recovered · {formatCount(r.recovered_within_window_payments)} within 1 hour
          </p>
        </section>
        <section className="card stat-card" aria-label="Unresolved payments">
          <p className="stat-label">Unresolved payments</p>
          <p className="stat-value num">{formatCount(r.unresolved_payments)}</p>
          <p className="stat-foot">
            <Money cents={r.unresolved_cents} /> in payment amounts
            {r.retry_pending_payments > 0 ? ` · ${formatCount(r.retry_pending_payments)} with a retry pending` : ""}
          </p>
          {r.unresolved_payments > 0 ? (
            <p className="stat-foot">
              <Link to={unresolvedPaymentsHref(scope, channel)}>Review in Payments</Link>
            </p>
          ) : null}
        </section>
      </div>

      <section className="card chart-card" aria-labelledby="health-trend-heading">
        <div className="section-head">
          <h2 id="health-trend-heading" className="section-title">
            Daily success rate
          </h2>
          <p className="muted section-aside">
            {data.channel_label} · baseline {formatRate(a.baseline_success_rate_bp)} ({data.baseline.range_label})
          </p>
        </div>
        {data.trend.every((d) => d.success_rate_bp === null) ? (
          <EmptyState title="No completed attempts" body="There is no success rate to chart for this period. Pending attempts are not counted." />
        ) : (
          <>
            <RateChart
              title={`Daily success rate, ${data.channel_label}, ${data.period.range_label}`}
              baselineBp={a.baseline_success_rate_bp}
              baselineLabel={`Baseline, ${data.baseline.range_label}`}
              points={data.trend.map((d) => ({
                label: `${formatDateShort(d.date)}${d.partial ? " (so far)" : ""}`,
                rateBp: d.success_rate_bp,
                lowVolume: d.low_volume,
                detail: `${formatCount(d.succeeded)} succeeded · ${formatCount(d.failed)} failed · ${formatCount(d.pending)} pending`,
              }))}
            />
            <ul className="chart-legend" aria-label="Chart legend">
              <li>
                <span className="legend-swatch legend-line" aria-hidden="true" />
                Success rate
              </li>
              <li>
                <span className="legend-swatch legend-baseline" aria-hidden="true" />
                Baseline ({data.rules.baseline_days} days before)
              </li>
              <li>
                <span className="legend-swatch legend-low" aria-hidden="true" />
                Low volume (fewer than {data.rules.low_volume_day_attempts} completed)
              </li>
              <li>
                <span className="legend-swatch legend-gap" aria-hidden="true" />
                Gap: no completed attempts
              </li>
            </ul>
          </>
        )}
      </section>

      <div className="health-grid">
        <section aria-labelledby="health-channels-heading">
          <div className="section-head">
            <h2 id="health-channels-heading" className="section-title">
              Performance by channel
            </h2>
            {data.channel ? (
              <button type="button" className="btn btn-sm" onClick={() => query.set({ channel: null })}>
                Show all channels
              </button>
            ) : null}
          </div>
          <ChannelTable rows={data.channels} selected={data.channel} onSelect={(ch) => query.set({ channel: ch })} />
        </section>
        <section aria-labelledby="health-signals-heading">
          <div className="section-head">
            <h2 id="health-signals-heading" className="section-title">
              Recorded failure signals
            </h2>
            <p className="muted section-aside">What failed attempts recorded, not confirmed causes</p>
          </div>
          <SignalTable rows={data.failure_signals} scope={scope} channel={channel} />
        </section>
      </div>

      <section className="card" aria-labelledby="health-recovery-heading">
        <h2 id="health-recovery-heading" className="section-title">
          Recovery by payment
        </h2>
        <p className="muted section-intro">Payments created in the period that had at least one failed attempt. Each payment and its amount count once.</p>
        <DescriptionList
          columns={4}
          items={[
            { term: "Affected", value: <RecoveryValue count={r.affected_payments} cents={r.affected_cents} /> },
            { term: "Recovered", value: <RecoveryValue count={r.recovered_payments} cents={r.recovered_cents} /> },
            { term: "Recovered within 1 hour", value: <RecoveryValue count={r.recovered_within_window_payments} cents={r.recovered_within_window_cents} /> },
            { term: "Unresolved", value: <RecoveryValue count={r.unresolved_payments} cents={r.unresolved_cents} /> },
            { term: "Retry pending", value: <RecoveryValue count={r.retry_pending_payments} cents={r.retry_pending_cents} /> },
          ]}
        />
      </section>

      <section aria-labelledby="health-unresolved-heading">
        <div className="section-head">
          <h2 id="health-unresolved-heading" className="section-title">
            Unresolved payments
          </h2>
          {r.unresolved_payments > 0 ? (
            <Link to={unresolvedPaymentsHref(scope, channel)} className="section-aside">
              Review all {formatCount(r.unresolved_payments)} in Payments
            </Link>
          ) : null}
        </div>
        <UnresolvedTable rows={data.unresolved} total={r.unresolved_payments} />
      </section>

      <Definitions data={data} />
    </div>
  );
}

function RecoveryValue({ count, cents }: { count: number; cents: number }) {
  return (
    <span className="num">
      {plural(count, "payment")} · {formatCents(cents)}
    </span>
  );
}

function AttentionSummary({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const { attention, rules } = data;
  const drop = formatPointChange(rules.degraded_drop_bp).replace("+", "");
  const labelOf = (ch: string) => data.channels.find((c) => c.channel === ch)?.channel_label ?? ch;
  const insufficient = attention.insufficient_volume_channels.map(labelOf);
  return (
    <section className={`card health-attention health-attention-${attention.status}`} aria-labelledby="health-attention-heading">
      <h2 id="health-attention-heading" className="section-title">
        {attention.status === "degraded"
          ? `${attention.degraded.length === 1 ? "1 channel is" : `${attention.degraded.length} channels are`} degraded`
          : attention.status === "no_significant_degradation"
            ? "No significant degradation detected"
            : attention.status === "insufficient_volume"
              ? "Not enough completed attempts to assess"
              : "No completed attempts in this period"}
      </h2>
      {attention.status === "degraded" ? (
        <ul className="attention-list">
          {attention.degraded.map((d) => (
            <li key={d.channel} className="attention-item attention-degraded">
              <span className="attention-dot" aria-hidden="true" />
              <div className="attention-body">
                <p className="attention-title">
                  <strong>{d.channel_label}</strong>: {formatRate(d.success_rate_bp)} success rate vs {formatRate(d.baseline_success_rate_bp)} baseline (
                  {formatPointChange(d.change_bp)})
                </p>
                <p className="attention-detail muted">
                  {plural(d.failed_attempts, "failed attempt")} · {plural(d.unresolved_payments, "unresolved payment")}
                </p>
                <p className="attention-when">
                  <Link to={failedAttemptsHref(scope, d.channel)}>Review failed attempts</Link>
                  {d.unresolved_payments > 0 ? (
                    <>
                      {" · "}
                      <Link to={unresolvedPaymentsHref(scope, d.channel)}>Review unresolved payments</Link>
                    </>
                  ) : null}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="muted health-attention-note">
        {attention.status === "no_significant_degradation"
          ? `Every channel with enough completed attempts is within ${drop} of its own baseline.`
          : attention.status === "insufficient_volume"
            ? `A channel needs at least ${rules.min_completed_attempts} completed attempts in the period and in its baseline before a conclusion is drawn.`
            : attention.status === "no_completed_attempts"
              ? "There is no success rate to assess. Pending attempts are not counted."
              : `A channel is degraded when its success rate is at least ${drop} below its own baseline.`}
        {insufficient.length > 0 && attention.status !== "insufficient_volume" ? ` Not enough attempts to assess: ${insufficient.join(", ")}.` : ""}
      </p>
    </section>
  );
}

function ChannelTable({ rows, selected, onSelect }: { rows: ChannelHealth[]; selected: string | null; onSelect: (channel: string) => void }) {
  if (rows.length === 0) return <EmptyState title="No attempts" body="No channel had attempts in this period or its baseline." />;
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <button
          type="button"
          className={c.channel === selected ? "link-button is-selected" : "link-button"}
          aria-pressed={c.channel === selected}
          onClick={() => onSelect(c.channel)}
        >
          {c.channel_label}
          {c.channel === selected ? <span className="selected-tag"> · showing</span> : null}
        </button>
      ),
    },
    { key: "assessment", header: "Assessment", render: (c) => <StatusBadge status={c.assessment} label={c.assessment_label} /> },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatRate(c.success_rate_bp) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatRate(c.baseline_success_rate_bp) },
    { key: "change", header: "Change", align: "right", render: (c) => formatPointChange(c.change_bp) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.failed) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.completed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.pending) },
  ];
  return <DataTable caption="Performance by channel" columns={columns} rows={rows} rowKey={(c) => c.channel} />;
}

function SignalTable({ rows, scope, channel }: { rows: FailureSignal[]; scope: HealthScope; channel: string | undefined }) {
  if (rows.length === 0) return <EmptyState title="No failed attempts" body="No failure signals were recorded in this period." />;
  const columns: Column<FailureSignal>[] = [
    {
      key: "signal",
      header: "Recorded signal",
      className: "primary",
      render: (s) => <Link to={failedAttemptsHref(scope, channel, s.failure_code)}>{s.label}</Link>,
    },
    { key: "code", header: "Code", className: "secondary", render: (s) => <span className="mono">{s.failure_code}</span> },
    { key: "count", header: "Failed attempts", align: "right", render: (s) => formatCount(s.failed_attempts) },
  ];
  return <DataTable caption="Recorded failure signals" columns={columns} rows={rows} rowKey={(s) => s.failure_code} />;
}

function UnresolvedTable({ rows, total }: { rows: UnresolvedPayment[]; total: number }) {
  if (rows.length === 0) return <EmptyState title="No unresolved payments" body="Every payment with a failed attempt in this period has recovered or is still retrying." />;
  const columns: Column<UnresolvedPayment>[] = [
    {
      key: "created_at",
      header: "Created",
      render: (p) => (
        <Link to={`/payments/${p.id}`} className="row-link">
          <Timestamp iso={p.created_at} />
        </Link>
      ),
    },
    { key: "order", header: "Order", className: "secondary", render: (p) => <span className="mono">{p.order_reference}</span> },
    { key: "customer", header: "Customer", className: "primary", render: (p) => (p.customer ? p.customer.full_name : <span className="muted">Guest</span>) },
    { key: "channel", header: "Channel", render: (p) => p.channel_label },
    { key: "attempts", header: "Attempts", align: "right", render: (p) => formatCount(p.attempt_count) },
    { key: "signal", header: "Last recorded signal", render: (p) => p.last_failure_label ?? <span className="muted">—</span> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  return (
    <>
      <DataTable caption={`First ${rows.length} of ${total} unresolved payments, oldest first`} columns={columns} rows={rows} rowKey={(p) => p.id} />
      {total > rows.length ? <p className="muted table-note">Showing the first {rows.length} of {formatCount(total)}, oldest first.</p> : null}
    </>
  );
}

function Definitions({ data }: { data: PaymentHealth }) {
  const { rules } = data;
  const drop = formatPointChange(rules.degraded_drop_bp).replace("+", "");
  const minutes = Math.floor(rules.recovery_window_seconds / 60);
  return (
    <section className="card health-definitions" aria-labelledby="health-definitions-heading">
      <h2 id="health-definitions-heading" className="section-title">
        Definitions
      </h2>
      <DescriptionList
        columns={2}
        items={[
          {
            term: "Success rate",
            value: "Succeeded attempts ÷ completed attempts (succeeded + failed), for attempts created in the period. Pending attempts are not completed and are left out; their count is shown.",
          },
          { term: "Baseline", value: `The same channel's success rate over the ${rules.baseline_days} days before the period (${data.baseline.range_label}).` },
          {
            term: "Degraded",
            value: `A success rate at least ${drop} below the channel's own baseline, with at least ${rules.min_completed_attempts} completed attempts in both the period and the baseline. A fixed rule, not a statistical model.`,
          },
          { term: "Not enough attempts", value: `Fewer than ${rules.min_completed_attempts} completed attempts in the period or the baseline. No conclusion is drawn.` },
          { term: "Low-volume day", value: `A day with fewer than ${rules.low_volume_day_attempts} completed attempts, drawn as a hollow point. Days with none are gaps.` },
          {
            term: "Affected payment",
            value: "A payment created in the period with at least one failed attempt. It counts once, and so does its amount, however many attempts it had.",
          },
          { term: "Recovered", value: `An affected payment that later had a succeeded attempt. "Within 1 hour" means it succeeded within ${minutes} minutes of its first attempt.` },
          { term: "Unresolved", value: "An affected payment with no succeeded attempt whose latest attempt failed (payment status Failed)." },
          { term: "Retry pending", value: "An affected payment with no succeeded attempt whose latest attempt is still pending." },
          { term: "Recorded failure signal", value: "The failure code a failed attempt recorded. It describes what was reported, not a confirmed root cause." },
          { term: "Payment amounts", value: "Affected, recovered and unresolved values are the amounts of those payments. They are not lost revenue." },
        ]}
      />
    </section>
  );
}
