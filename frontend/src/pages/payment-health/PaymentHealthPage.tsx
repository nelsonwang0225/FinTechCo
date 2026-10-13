import { Link } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, PaymentHealth, TrendPoint } from "../../api/payment-health-types";
import type { PaymentListItem } from "../../api/payments-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { DescriptionList } from "../../components/DescriptionList";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { LineChart, type LineChartPoint } from "../../components/LineChart";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCents, formatCount, formatDateShort, formatPointChange, formatRate, formatTimestampFull } from "../../lib/format";
import { HEALTH_PATH, failedAttemptsHref, unresolvedPaymentsHref } from "../../lib/healthLinks";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";

type Scope = Record<string, string | undefined>;

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const scope: Scope = { ...periodParams(query), channel: query.get("channel") || undefined };
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString(scope)}`);
  // Every drill-down carries the exact Payment Health URL so "Back to Payment Health" restores this scope.
  const returnTo = `${HEALTH_PATH}${query.search ? `?${query.search}` : ""}`;

  return (
    <>
      <PageHeader
        title="Payment health"
        subtitle={
          health.data
            ? `Completed-attempt performance and recovery for ${health.data.period.range_label} · As of ${formatTimestampFull(health.data.as_of)}`
            : "Completed-attempt performance and recovery. Times are shown in America/Chicago."
        }
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={query.get("channel")} options={meta.data.channels} allLabel="All channels" onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !health.data ? <LoadingState rows={8} label="Loading payment health" /> : null}
      {health.data ? <HealthBody data={health.data} loading={health.loading} query={query} scope={scope} returnTo={returnTo} /> : null}
    </>
  );
}

function HealthBody({ data, loading, query, scope, returnTo }: { data: PaymentHealth; loading: boolean; query: QueryState; scope: Scope; returnTo: string }) {
  const { summary } = data;
  const scopeLabel = data.channel ? (data.channels.find((c) => c.channel === data.channel)?.channel_label ?? data.channel) : "All channels";
  const hasCompleted = summary.period.completed > 0;
  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <AttentionSummary data={data} scope={scope} returnTo={returnTo} />

      {hasCompleted ? (
        <>
          <div className="cards cards-4">
            <section className="card stat-card" aria-label="Success rate">
              <p className="stat-label">Success rate · {scopeLabel}</p>
              <p className="stat-value">{formatRate(summary.period.success_rate_bps)}</p>
              <p className="stat-foot">
                Baseline {formatRate(summary.baseline.success_rate_bps)} · {formatPointChange(summary.change_bps)}
              </p>
              <p className="stat-foot">
                <StatusBadge status={summary.assessment} label={summary.assessment_label} />
              </p>
            </section>
            <section className="card stat-card" aria-label="Completed attempts">
              <p className="stat-label">Completed attempts</p>
              <p className="stat-value">{formatCount(summary.period.completed)}</p>
              <p className="stat-foot">
                {formatCount(summary.period.succeeded)} succeeded · {formatCount(summary.period.failed)} failed
              </p>
              <p className="stat-foot">{pendingNote(summary.period.pending)}</p>
            </section>
            <section className="card stat-card" aria-label="Failed attempts">
              <p className="stat-label">Failed attempts</p>
              <p className="stat-value">{formatCount(summary.period.failed)}</p>
              <p className="stat-foot">
                <Link to={failedAttemptsHref(scope, returnTo)}>Review failed attempts</Link>
              </p>
            </section>
            <section className="card stat-card" aria-label="Unresolved payments">
              <p className="stat-label">Unresolved payments</p>
              <p className="stat-value">{formatCount(data.recovery.unresolved_payments)}</p>
              <p className="stat-foot">
                <Money cents={data.recovery.unresolved_value_cents} /> in payment amounts
              </p>
            </section>
          </div>
          <TrendSection data={data} scopeLabel={scopeLabel} />
        </>
      ) : (
        <section className="card health-empty">
          <EmptyState
            title="No completed attempts in this period"
            body={
              summary.period.pending > 0
                ? `${formatCount(summary.period.pending)} attempt${summary.period.pending === 1 ? " is" : "s are"} still pending. No success rate is shown until attempts complete.`
                : "There is nothing to measure for this scope. Try a wider period or another channel."
            }
          />
        </section>
      )}

      <ChannelTable data={data} query={query} />

      {hasCompleted || data.recovery.affected_payments > 0 ? (
        <div className="health-grid">
          <FailureSignals data={data} scope={scope} returnTo={returnTo} />
          <RecoverySection data={data} />
        </div>
      ) : null}

      {data.unresolved.total > 0 || hasCompleted ? <UnresolvedSection data={data} scope={scope} returnTo={returnTo} /> : null}

      <Definitions data={data} />
    </div>
  );
}

function pendingNote(pending: number): string {
  if (pending === 0) return "No pending attempts";
  return `${formatCount(pending)} pending attempt${pending === 1 ? "" : "s"} excluded from the rate`;
}

function AttentionSummary({ data, scope, returnTo }: { data: PaymentHealth; scope: Scope; returnTo: string }) {
  const degraded = data.channels.filter((c) => c.assessment === "degraded");
  const evaluated = data.channels.filter((c) => c.assessment === "not_degraded");
  const insufficient = data.channels.filter((c) => c.assessment === "insufficient_data");
  const empty = data.channels.filter((c) => c.assessment === "no_completed_attempts");
  const { min_completed_attempts: min, degradation_points: points } = data.thresholds;
  return (
    <section className="card health-attention" aria-labelledby="health-attention-heading">
      <div className="section-head">
        <h2 id="health-attention-heading" className="section-title">
          Attention summary
        </h2>
        <p className="muted section-aside">
          Each channel against its own last {data.baseline.days} days ({data.baseline.range_label})
        </p>
      </div>
      <ul className="attention-list">
        {degraded.map((c) => (
          <li key={c.channel} className="attention-item attention-degraded">
            <span className="attention-dot" aria-hidden="true" />
            <div className="attention-body">
              <p className="attention-title">
                {c.channel_label} is degraded: {formatRate(c.period.success_rate_bps)} success vs a {formatRate(c.baseline.success_rate_bps)} baseline (
                {formatPointChange(c.change_bps)})
              </p>
              <p className="attention-detail muted">
                {formatCount(c.period.failed)} failed of {formatCount(c.period.completed)} completed attempts in {data.period.range_label}
              </p>
              <p className="attention-when">
                <Link to={unresolvedPaymentsHref({ ...scope, channel: c.channel }, returnTo)}>Review unresolved {c.channel_label.toLowerCase()} payments</Link>
                {" · "}
                <Link to={failedAttemptsHref({ ...scope, channel: c.channel }, returnTo)}>Failed attempts</Link>
              </p>
            </div>
          </li>
        ))}
        {evaluated.length > 0 ? (
          <li className="attention-item attention-clear">
            <span className="attention-dot" aria-hidden="true" />
            <div className="attention-body">
              <p className="attention-title">{degraded.length === 0 ? "No significant degradation detected" : `No significant degradation in ${evaluated.map((c) => c.channel_label).join(", ")}`}</p>
              <p className="attention-detail muted">
                {evaluated.map((c) => c.channel_label).join(", ")} {evaluated.length === 1 ? "is" : "are"} within {points} percentage points of {evaluated.length === 1 ? "its" : "their"}{" "}
                baseline.
              </p>
            </div>
          </li>
        ) : null}
        {insufficient.map((c) => (
          <li key={c.channel} className="attention-item attention-insufficient">
            <span className="attention-dot" aria-hidden="true" />
            <div className="attention-body">
              <p className="attention-title">{c.channel_label}: not enough data to evaluate</p>
              <p className="attention-detail muted">
                {formatCount(c.period.completed)} completed attempts in the period and {formatCount(c.baseline.completed)} in the baseline; each needs at least {min}.
              </p>
            </div>
          </li>
        ))}
        {empty.map((c) => (
          <li key={c.channel} className="attention-item attention-insufficient">
            <span className="attention-dot" aria-hidden="true" />
            <div className="attention-body">
              <p className="attention-title">{c.channel_label}: no completed attempts in this period</p>
              {c.period.pending > 0 ? <p className="attention-detail muted">{pendingNote(c.period.pending)}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function trendDetail(p: TrendPoint): string {
  const day = formatDateShort(p.date);
  const pending = p.pending > 0 ? `, ${formatCount(p.pending)} pending` : "";
  if (p.completed === 0) return `${day}: no completed attempts${pending}`;
  const low = p.low_volume ? " (low volume)" : "";
  return `${day}: ${formatRate(p.success_rate_bps)} success${low} · ${formatCount(p.succeeded)} succeeded, ${formatCount(p.failed)} failed${pending}`;
}

function TrendSection({ data, scopeLabel }: { data: PaymentHealth; scopeLabel: string }) {
  const baseline = data.summary.baseline.success_rate_bps;
  const values = data.trend.map((p) => p.success_rate_bps).filter((v): v is number => v !== null);
  if (baseline !== null) values.push(baseline);
  const floor = Math.max(0, Math.floor((Math.min(10000, ...values) - 500) / 1000) * 1000);
  const series: LineChartPoint[] = data.trend.map((p) => ({ label: formatDateShort(p.date), value: p.success_rate_bps, lowVolume: p.low_volume, detail: trendDetail(p) }));
  return (
    <section className="card chart-card" aria-labelledby="health-trend-heading">
      <div className="section-head">
        <h2 id="health-trend-heading" className="section-title">
          Daily success rate · {scopeLabel}
        </h2>
        <p className="muted section-aside">Baseline {formatRate(baseline)} · {data.period.range_label}</p>
      </div>
      <LineChart
        title={`Daily completed-attempt success rate, ${scopeLabel}, ${data.period.range_label}`}
        series={series}
        reference={baseline}
        referenceLabel={`Baseline ${formatRate(baseline)} (${data.baseline.range_label})`}
        formatValue={(v) => formatRate(v)}
        minValue={floor}
        maxValue={10000}
      />
      <ul className="chart-legend" aria-label="Legend">
        <li>
          <span className="legend-line" aria-hidden="true" /> Success rate
        </li>
        <li>
          <span className="legend-line legend-dashed" aria-hidden="true" /> Baseline
        </li>
        <li>
          <span className="legend-hollow" aria-hidden="true" /> Low volume (fewer than {data.thresholds.low_volume_day_attempts} completed attempts)
        </li>
        <li>Gaps: days with no completed attempts</li>
      </ul>
      <details className="chart-data">
        <summary>Show daily counts</summary>
        <div className="table-wrap">
          <table className="table">
            <caption className="visually-hidden">Daily attempt counts</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col" className="money">
                  Success rate
                </th>
                <th scope="col" className="money">
                  Succeeded
                </th>
                <th scope="col" className="money">
                  Failed
                </th>
                <th scope="col" className="money">
                  Pending
                </th>
                <th scope="col">Note</th>
              </tr>
            </thead>
            <tbody>
              {data.trend.map((p) => (
                <tr key={p.date}>
                  <td>{formatDateShort(p.date)}</td>
                  <td className="money">{formatRate(p.success_rate_bps)}</td>
                  <td className="money">{formatCount(p.succeeded)}</td>
                  <td className="money">{formatCount(p.failed)}</td>
                  <td className="money">{formatCount(p.pending)}</td>
                  <td className="muted">{p.completed === 0 ? "No completed attempts" : p.low_volume ? "Low volume" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function ChannelTable({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => {
        const selected = data.channel === c.channel;
        return (
          <button type="button" className="link-button channel-select" aria-pressed={selected} onClick={() => query.set({ channel: selected ? null : c.channel })}>
            {c.channel_label}
            {selected ? <span className="tag">Showing</span> : null}
          </button>
        );
      },
    },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatRate(c.period.success_rate_bps) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatRate(c.baseline.success_rate_bps) },
    { key: "change", header: "Change", align: "right", render: (c) => formatPointChange(c.change_bps) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.period.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.period.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.period.pending) },
    { key: "assessment", header: "Assessment", render: (c) => <StatusBadge status={c.assessment} label={c.assessment_label} /> },
  ];
  return (
    <section aria-labelledby="health-channels-heading" className="health-section">
      <div className="section-head">
        <h2 id="health-channels-heading" className="section-title">
          Performance by channel
        </h2>
        {data.channel ? (
          <button type="button" className="link-button section-aside" onClick={() => query.set({ channel: null })}>
            Show all channels
          </button>
        ) : (
          <p className="muted section-aside">Select a channel to scope the page</p>
        )}
      </div>
      <DataTable caption="Completed-attempt performance by channel" columns={columns} rows={data.channels} rowKey={(c) => c.channel} />
    </section>
  );
}

function FailureSignals({ data, scope, returnTo }: { data: PaymentHealth; scope: Scope; returnTo: string }) {
  const failed = data.summary.period.failed;
  return (
    <section className="card" aria-labelledby="health-signals-heading">
      <div className="section-head">
        <h2 id="health-signals-heading" className="section-title">
          Recorded failure signals
        </h2>
        {failed > 0 ? (
          <Link to={failedAttemptsHref(scope, returnTo)} className="section-aside">
            All {formatCount(failed)} failed attempts
          </Link>
        ) : null}
      </div>
      <p className="muted health-note">Codes recorded on failed attempts. They describe what was reported, not a confirmed cause.</p>
      {data.failure_signals.length === 0 ? (
        <p className="muted">No failed attempts in this period.</p>
      ) : (
        <ul className="signal-list">
          {data.failure_signals.map((s) => (
            <li key={s.failure_code} className="signal-row">
              <Link to={failedAttemptsHref(scope, returnTo, s.failure_code)}>{s.label}</Link>
              <span className="num">
                {formatCount(s.failed_attempts)} <span className="muted">· {formatRate(shareBps(s.failed_attempts, failed))}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Share of a whole in basis points, integer half-up. */
function shareBps(part: number, whole: number): number | null {
  if (whole === 0) return null;
  return Math.floor((part * 20000 + whole) / (whole * 2));
}

function RecoverySection({ data }: { data: PaymentHealth }) {
  const r = data.recovery;
  const minutes = data.thresholds.recovery_window_minutes;
  return (
    <section className="card" aria-labelledby="health-recovery-heading">
      <div className="section-head">
        <h2 id="health-recovery-heading" className="section-title">
          Recovery by payment
        </h2>
        <p className="muted section-aside">Payment amounts, counted once per payment</p>
      </div>
      <dl className="bucket-list">
        <div className="bucket-row">
          <dt>Affected payments</dt>
          <dd>
            {formatCount(r.affected_payments)} · <Money cents={r.affected_value_cents} />
          </dd>
        </div>
        <div className="bucket-row">
          <dt>Recovered</dt>
          <dd>
            {formatCount(r.recovered_payments)} · <Money cents={r.recovered_value_cents} />
          </dd>
        </div>
        <div className="bucket-row bucket-sub">
          <dt>Recovered within {minutes} minutes of the first attempt</dt>
          <dd>{formatCount(r.recovered_within_window_payments)}</dd>
        </div>
        <div className="bucket-row">
          <dt>Unresolved</dt>
          <dd>
            {formatCount(r.unresolved_payments)} · <Money cents={r.unresolved_value_cents} />
          </dd>
        </div>
        <div className="bucket-row">
          <dt>Awaiting outcome</dt>
          <dd>
            {formatCount(r.awaiting_outcome_payments)} · <Money cents={r.awaiting_outcome_value_cents} />
          </dd>
        </div>
      </dl>
      <p className="muted health-note">Affected = recovered + unresolved + awaiting outcome. {formatCents(r.affected_value_cents)} is the total of those payments&apos; amounts.</p>
    </section>
  );
}

function UnresolvedSection({ data, scope, returnTo }: { data: PaymentHealth; scope: Scope; returnTo: string }) {
  const columns: Column<PaymentListItem>[] = [
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
    { key: "channel", header: "Channel", render: (p) => (p.location ? `${p.channel_label} · ${p.location.name}` : p.channel_label) },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  const total = data.unresolved.total;
  return (
    <section aria-labelledby="health-unresolved-heading" className="health-section">
      <div className="section-head">
        <h2 id="health-unresolved-heading" className="section-title">
          Payments that still need attention
        </h2>
        {total > 0 ? (
          <Link to={unresolvedPaymentsHref(scope, returnTo)} className="section-aside">
            Review all {formatCount(total)} unresolved payments in Payments
          </Link>
        ) : null}
      </div>
      {total === 0 ? (
        <p className="muted">No unresolved payments in this period.</p>
      ) : (
        <>
          <DataTable caption="First unresolved payments, newest first" columns={columns} rows={data.unresolved.items} rowKey={(p) => p.id} />
          {total > data.unresolved.items.length ? (
            <p className="muted health-note">
              Showing the newest {data.unresolved.items.length} of {formatCount(total)}.
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

function Definitions({ data }: { data: PaymentHealth }) {
  const t = data.thresholds;
  return (
    <details className="card definitions">
      <summary>How these figures are defined</summary>
      <DescriptionList
        columns={2}
        items={[
          { term: "Success rate", value: "Succeeded ÷ (succeeded + failed) attempts, by when each attempt was made. Pending attempts are counted separately and left out until they complete." },
          { term: "Baseline", value: `The same channel's success rate over the ${t.baseline_days} days before the selected period (${data.baseline.range_label}).` },
          {
            term: "Degraded",
            value: `A success rate at least ${t.degradation_points} percentage points below the channel's baseline. A channel is evaluated only when the period and the baseline each have at least ${t.min_completed_attempts} completed attempts.`,
          },
          { term: "Affected", value: "A payment created in the period with at least one failed attempt, counted once however many attempts it had." },
          { term: "Recovered", value: `An affected payment that later has a successful attempt. Recoveries within ${t.recovery_window_minutes} minutes of the first attempt are shown separately.` },
          { term: "Unresolved", value: "An affected payment with no successful attempt whose latest attempt failed. These are the payments listed as Failed in Payments." },
          { term: "Awaiting outcome", value: "An affected payment whose latest attempt is still pending." },
          { term: "Low-volume day", value: `A day with fewer than ${t.low_volume_day_attempts} completed attempts; its rate moves a lot with a few attempts.` },
        ]}
      />
    </details>
  );
}
