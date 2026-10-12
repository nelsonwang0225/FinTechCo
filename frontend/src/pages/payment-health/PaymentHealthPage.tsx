import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, PaymentHealth, RecoveryBucket } from "../../api/payment-health-types";
import type { PaymentListItem, PaymentListResponse } from "../../api/payments-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { LineChart } from "../../components/LineChart";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCents, formatCount, formatDateShort, formatPointChange, formatPoints, formatRate, formatTimestampFull } from "../../lib/format";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter } from "../payments/PeriodFilter";
import { failedAttemptsHref, healthScope, unresolvedPaymentsHref, type HealthScope } from "./links";

const UNRESOLVED_PREVIEW = 5;

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const scope = healthScope(query);
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString(scope)}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment health"
        subtitle="Completed-attempt success by period and channel, compared with each channel's own baseline. Times are shown in America/Chicago."
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
      {data ? <HealthBody data={data} scope={scope} query={query} loading={health.loading} /> : null}
    </>
  );
}

function HealthBody({ data, scope, query, loading }: { data: PaymentHealth; scope: HealthScope; query: QueryState; loading: boolean }) {
  const s = data.summary;
  const scopeLabel = data.channel_label ?? "All channels";
  return (
    <div className={loading ? "overview overview-loading" : "overview"} aria-busy={loading || undefined}>
      <p className="toolbar-note">
        <span>
          {scopeLabel} · {data.period.label}: {data.period.range_label} · As of {formatTimestampFull(data.as_of)}
        </span>
      </p>
      <AttentionSummary data={data} scope={scope} />

      <div className="cards cards-4">
        <section className="card stat-card" aria-label="Success rate">
          <p className="stat-label">Success rate · {scopeLabel}</p>
          <p className="stat-value">{s.success_rate_bp !== null ? formatRate(s.success_rate_bp) : "—"}</p>
          <p className="stat-foot">
            {s.completed === 0
              ? "No completed attempts in this period"
              : s.baseline_rate_bp !== null && s.change_bp !== null
                ? `Baseline ${formatRate(s.baseline_rate_bp)} · ${formatPointChange(s.change_bp)}`
                : "No baseline attempts to compare with"}
          </p>
        </section>
        <section className="card stat-card" aria-label="Failed attempts">
          <p className="stat-label">Failed attempts</p>
          <p className="stat-value">{formatCount(s.failed)}</p>
          <p className="stat-foot">of {formatCount(s.completed)} completed attempts</p>
        </section>
        <section className="card stat-card" aria-label="Pending attempts">
          <p className="stat-label">Pending attempts</p>
          <p className="stat-value">{formatCount(s.pending)}</p>
          <p className="stat-foot">Not yet completed, so excluded from the success rate</p>
        </section>
        <section className="card stat-card" aria-label="Affected payments">
          <p className="stat-label">Affected payments</p>
          <p className="stat-value">{formatCount(data.recovery.affected.payments)}</p>
          <p className="stat-foot">
            {formatCents(data.recovery.affected.amount_cents)} in payment amounts · {formatCount(data.recovery.recovered.payments)} recovered
          </p>
        </section>
      </div>

      <TrendSection data={data} />
      <ChannelSection data={data} query={query} />

      <div className="overview-grid">
        <div className="detail-stack">
          <FailureSignals data={data} scope={scope} />
          <UnresolvedPayments data={data} scope={scope} />
        </div>
        <div className="detail-stack">
          <RecoverySection data={data} scope={scope} />
        </div>
      </div>

      <Definitions data={data} />
    </div>
  );
}

function AttentionSummary({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const degraded = data.channels.filter((c) => c.assessment === "degraded");
  const unassessed = data.channels.filter((c) => c.assessment === "insufficient_period_volume" || c.assessment === "insufficient_baseline");
  const anyCompleted = data.channels.some((c) => c.completed > 0);
  const t = data.thresholds;
  return (
    <section className="card health-attention" aria-labelledby="attention-heading">
      <h2 id="attention-heading" className="section-title">
        Attention · all channels
      </h2>
      {!anyCompleted ? (
        <p className="muted attention-empty">No completed attempts in this period, so there is nothing to assess.</p>
      ) : degraded.length === 0 ? (
        <p className="attention-empty health-ok">
          <strong>No significant degradation detected.</strong>{" "}
          <span className="muted">
            No channel with enough volume fell {formatPoints(t.degraded_drop_bp)} or more below its baseline.
          </span>
        </p>
      ) : null}
      {degraded.length > 0 || unassessed.length > 0 ? (
        <ul className="attention-list">
          {degraded.map((c) => (
            <li key={c.channel} className="attention-item attention-degraded">
              <span className="attention-dot" aria-hidden="true" />
              <div className="attention-body">
                <p className="attention-title">{c.channel_label} is degraded</p>
                <p className="attention-detail">
                  {formatRate(c.success_rate_bp ?? 0)} success vs a {formatRate(c.baseline_rate_bp ?? 0)} baseline ({formatPointChange(c.change_bp ?? 0)}) ·{" "}
                  {formatCount(c.failed)} failed of {formatCount(c.completed)} completed attempts
                </p>
                <p className="attention-when">
                  <Link to={failedAttemptsHref(scope, { channel: c.channel })}>Review failed attempts</Link>
                  {" · "}
                  <Link to={unresolvedPaymentsHref(scope, { channel: c.channel })}>Review unresolved payments</Link>
                </p>
              </div>
            </li>
          ))}
          {unassessed.map((c) => (
            <li key={c.channel} className="attention-item attention-unassessed">
              <span className="attention-dot" aria-hidden="true" />
              <div className="attention-body">
                <p className="attention-title">{c.channel_label} not assessed</p>
                <p className="attention-detail muted">{unassessedReason(c, data)}</p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function unassessedReason(c: ChannelHealth, data: PaymentHealth): string {
  const t = data.thresholds;
  if (c.assessment === "insufficient_period_volume") {
    return `Too few completed attempts to draw a conclusion: ${formatCount(c.completed)} in this period, ${formatCount(t.min_period_completed)} needed.`;
  }
  return `Not enough baseline history: ${formatCount(c.baseline_completed)} completed attempts in ${data.baseline.range_label}, ${formatCount(t.min_baseline_completed)} needed.`;
}

function TrendSection({ data }: { data: PaymentHealth }) {
  const rates = data.trend.map((p) => p.success_rate_bp).filter((v): v is number => v !== null);
  const baseline = data.summary.baseline_rate_bp;
  const lowest = Math.min(...rates, ...(baseline !== null ? [baseline] : []));
  const min = Math.max(0, Math.floor((lowest - 500) / 1000) * 1000);
  const points = data.trend.map((p) => ({
    label: formatDateShort(p.day),
    value: p.success_rate_bp,
    lowVolume: p.low_volume,
    detail:
      p.success_rate_bp !== null
        ? `${formatRate(p.success_rate_bp)} · ${formatCount(p.succeeded)} succeeded, ${formatCount(p.failed)} failed, ${formatCount(p.pending)} pending`
        : `No completed attempts${p.pending ? `, ${formatCount(p.pending)} pending` : ""}`,
  }));
  return (
    <section className="card chart-card" aria-labelledby="trend-heading">
      <div className="section-head">
        <h2 id="trend-heading" className="section-title">
          Daily success rate
        </h2>
        <p className="muted section-aside">{data.channel_label ?? "All channels"}</p>
      </div>
      {rates.length === 0 ? (
        <EmptyState title="No completed attempts in this period" body="There is no success rate to chart. Try a wider period or another channel." />
      ) : (
        <>
          <LineChart
            title={`Daily success rate, ${data.period.range_label}`}
            points={points}
            reference={baseline}
            referenceLabel={`Baseline (${data.baseline.range_label})`}
            min={min}
            max={10000}
            formatValue={formatRate}
          />
          <ul className="chart-legend">
            <li>
              <span className="legend-line" aria-hidden="true" /> Daily success rate
            </li>
            <li>
              <span className="legend-dash" aria-hidden="true" />{" "}
              {baseline !== null ? `Baseline ${formatRate(baseline)} (${data.baseline.range_label})` : "No baseline attempts"}
            </li>
            <li>
              <span className="legend-hollow" aria-hidden="true" /> Low volume: fewer than {formatCount(data.thresholds.low_volume_day_completed)} completed attempts
            </li>
            <li>Gaps: days with no completed attempts</li>
          </ul>
        </>
      )}
    </section>
  );
}

function ChannelSection({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const toggle = (c: ChannelHealth) => query.set({ channel: data.channel === c.channel ? null : c.channel });
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <button
          type="button"
          className="link-button"
          aria-pressed={data.channel === c.channel}
          onClick={(e) => {
            e.stopPropagation();
            toggle(c);
          }}
        >
          {c.channel_label}
        </button>
      ),
    },
    { key: "completed", header: "Completed attempts", align: "right", render: (c) => formatCount(c.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.pending) },
    { key: "rate", header: "Success rate", align: "right", render: (c) => (c.success_rate_bp !== null ? formatRate(c.success_rate_bp) : "—") },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => (c.baseline_rate_bp !== null ? formatRate(c.baseline_rate_bp) : "—") },
    { key: "change", header: "Change", align: "right", render: (c) => (c.change_bp !== null ? formatPointChange(c.change_bp) : "—") },
    { key: "assessment", header: "Assessment", render: (c) => <StatusBadge status={c.assessment} label={c.assessment_label} /> },
  ];
  return (
    <section className="chart-card" aria-labelledby="channels-heading">
      <div className="section-head">
        <h2 id="channels-heading" className="section-title">
          Performance by channel
        </h2>
        <p className="muted section-aside">Select a channel to scope the page to it; select it again to show all channels.</p>
      </div>
      <DataTable
        caption="Performance by channel"
        columns={columns}
        rows={data.channels}
        rowKey={(c) => c.channel}
        onRowClick={toggle}
        rowClassName={(c) => (data.channel === c.channel ? "row-selected" : undefined)}
      />
    </section>
  );
}

function FailureSignals({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const columns: Column<PaymentHealth["failure_signals"][number]>[] = [
    {
      key: "signal",
      header: "Recorded signal",
      className: "primary",
      render: (f) => (
        <Link to={failedAttemptsHref(scope, { failureCode: f.code })} className="row-link">
          {f.label}
        </Link>
      ),
    },
    { key: "count", header: "Failed attempts", align: "right", render: (f) => formatCount(f.failed_attempts) },
    { key: "share", header: "Share of failed", align: "right", render: (f) => formatRate(f.share_bp) },
  ];
  return (
    <section aria-labelledby="signals-heading">
      <div className="section-head">
        <h2 id="signals-heading" className="section-title">
          Recorded failure signals
        </h2>
        {data.summary.failed > 0 ? (
          <Link to={failedAttemptsHref(scope)} className="section-aside">
            All {formatCount(data.summary.failed)} failed attempts
          </Link>
        ) : null}
      </div>
      <p className="muted health-note">
        The reason recorded on each failed attempt. These are recorded signals, not confirmed root causes. They add up to the {formatCount(data.summary.failed)}{" "}
        failed attempts in scope.
      </p>
      {data.failure_signals.length === 0 ? (
        <EmptyState
          title="No failed attempts recorded"
          body={data.summary.completed > 0 ? "Every completed attempt in this period succeeded." : "There were no completed attempts in this period."}
        />
      ) : (
        <DataTable caption="Recorded failure signals" columns={columns} rows={data.failure_signals} rowKey={(f) => f.code} />
      )}
    </section>
  );
}

function RecoveryRow({ label, bucket, children }: { label: string; bucket: RecoveryBucket; children?: ReactNode }) {
  return (
    <div className="bucket-row">
      <dt>
        {label}
        {children}
      </dt>
      <dd className="money">
        {formatCount(bucket.payments)} · <Money cents={bucket.amount_cents} />
      </dd>
    </div>
  );
}

function RecoverySection({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const r = data.recovery;
  return (
    <section className="card" aria-labelledby="recovery-heading">
      <h2 id="recovery-heading" className="section-title">
        Recovery by payment
      </h2>
      <p className="muted health-note">
        Payments created in the period with at least one failed attempt, each counted once with its payment amount, however many attempts it took. Outcome as of{" "}
        {formatTimestampFull(data.as_of)}.
      </p>
      {r.affected.payments === 0 ? (
        <p className="muted attention-empty">No payments created in this period had a failed attempt.</p>
      ) : (
        <dl className="bucket-list">
          <RecoveryRow label="Affected payments" bucket={r.affected} />
          <RecoveryRow label="Recovered by a later attempt" bucket={r.recovered} />
          <RecoveryRow label="Recovered within 1 hour of the first attempt" bucket={r.recovered_within_hour} />
          <RecoveryRow label="Unresolved" bucket={r.unresolved}>
            {r.unresolved.payments > 0 ? (
              <>
                {" · "}
                <Link to={unresolvedPaymentsHref(scope)}>Review</Link>
              </>
            ) : null}
          </RecoveryRow>
          <RecoveryRow label="Awaiting a pending retry" bucket={r.awaiting_retry} />
        </dl>
      )}
    </section>
  );
}

function UnresolvedPayments({ data, scope }: { data: PaymentHealth; scope: HealthScope }) {
  const navigate = useNavigate();
  const params = { ...scope, status: "failed", sort: "created_at", dir: "desc", page: 1, page_size: UNRESOLVED_PREVIEW };
  const list = useApi<PaymentListResponse>(`/api/payments${queryString(params)}`);
  const columns: Column<PaymentListItem>[] = [
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
    { key: "customer", header: "Customer", className: "primary", render: (p) => (p.customer ? p.customer.full_name : <span className="muted">Guest</span>) },
    { key: "channel", header: "Channel", render: (p) => p.channel_label },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  return (
    <section aria-labelledby="unresolved-heading">
      <div className="section-head">
        <h2 id="unresolved-heading" className="section-title">
          Payments that still need attention
        </h2>
        {data.recovery.unresolved.payments > 0 ? (
          <Link to={unresolvedPaymentsHref(scope)} className="section-aside">
            Review all {formatCount(data.recovery.unresolved.payments)} in Payments
          </Link>
        ) : null}
      </div>
      {list.error ? <LoadError error={list.error} onRetry={list.reload} /> : null}
      {!list.error && !list.data ? <LoadingState rows={3} /> : null}
      {list.data && list.data.items.length === 0 ? <EmptyState title="No unresolved payments" body="Every affected payment in this period recovered or is awaiting a retry." /> : null}
      {list.data && list.data.items.length > 0 ? (
        <DataTable
          caption="Most recent unresolved payments"
          columns={columns}
          rows={list.data.items}
          rowKey={(p) => p.id}
          onRowClick={(p) => navigate(`/payments/${p.id}`)}
          loading={list.loading}
        />
      ) : null}
    </section>
  );
}

function Definitions({ data }: { data: PaymentHealth }) {
  const t = data.thresholds;
  const drop = formatPoints(t.degraded_drop_bp);
  return (
    <section className="card health-definitions" aria-labelledby="definitions-heading">
      <h2 id="definitions-heading" className="section-title">
        Definitions
      </h2>
      <DescriptionList
        columns={3}
        items={[
          { term: "Success rate", value: "Succeeded ÷ (succeeded + failed) attempts created in the period. Pending attempts are excluded and shown separately." },
          { term: "Baseline", value: `The same channel over the ${t.baseline_days} days before the period (${data.baseline.range_label}), calculated the same way.` },
          {
            term: "Degraded",
            value: `At least ${formatCount(t.min_period_completed)} completed attempts in the period and ${formatCount(t.min_baseline_completed)} in the baseline, and a success rate ${drop} or more below the baseline. With less volume a channel is not assessed. A fixed rule, not a statistical model.`,
          },
          { term: "Low-volume day", value: `Fewer than ${formatCount(t.low_volume_day_completed)} completed attempts that day. Days with none are left as gaps.` },
          { term: "Recorded failure signal", value: "The failure reason recorded on a failed attempt. A signal to investigate, not a confirmed root cause." },
          {
            term: "Affected payment",
            value: "A payment created in the period with at least one failed attempt, counted once. Attempt figures use when each attempt was made, so a retry of an earlier payment counts there but not here.",
          },
          { term: "Recovered", value: `An affected payment that later succeeded, as of ${formatTimestampFull(data.as_of)}. Within 1 hour: completed within ${t.quick_recovery_seconds / 60} minutes of the first attempt.` },
          { term: "Unresolved", value: "An affected payment with no successful attempt whose latest attempt failed." },
          { term: "Awaiting a pending retry", value: "An affected payment with no successful attempt whose latest attempt is still pending." },
        ]}
      />
      <p className="muted health-note">Values are the amounts of the payments concerned, each payment counted once.</p>
    </section>
  );
}
