import { Link, useNavigate } from "react-router-dom";
import { queryString } from "../../api/client";
import type { ChannelHealth, FailureSignal, HealthRules, PaymentHealth } from "../../api/payment-health-types";
import type { PaymentListItem } from "../../api/payments-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { DataTable, type Column } from "../../components/DataTable";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { LineChart } from "../../components/LineChart";
import { Money } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { Timestamp } from "../../components/Timestamp";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCents, formatCount, formatDateShort, formatPointsBp, formatRateBp } from "../../lib/format";
import { useQueryState, type QueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";
import { drillHref } from "./scope";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const channel = query.get("channel");
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString({ ...periodParams(query), channel })}`);
  const data = health.data;

  return (
    <>
      <PageHeader
        title="Payment Health"
        subtitle="Completed-attempt success by channel, compared with each channel's own recent baseline. Times are shown in America/Chicago."
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={channel} options={meta.data.channels} onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !data ? <LoadingState rows={8} /> : null}
      {data ? <HealthBody data={data} query={query} loading={health.loading} /> : null}
    </>
  );
}

function HealthBody({ data, query, loading }: { data: PaymentHealth; query: QueryState; loading: boolean }) {
  const { summary, recovery, rules } = data;
  const scopeFoot = `${summary.channel_label} · ${data.period.range_label}`;
  const hasCompleted = summary.period.completed > 0;
  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <section className="card" aria-labelledby="health-attention-heading">
        <h2 id="health-attention-heading" className="section-title">
          Attention
        </h2>
        <AttentionSummary data={data} query={query} />
      </section>

      {hasCompleted ? (
        <div className="cards cards-4">
          <section className="card stat-card" aria-label="Success rate">
            <p className="stat-label">Success rate</p>
            <p className="stat-value num">{formatRateBp(summary.period.success_rate_bp)}</p>
            <p className="stat-foot">
              Baseline {formatRateBp(summary.baseline.success_rate_bp)} · {formatPointsBp(summary.change_bp)}
            </p>
            <p className="stat-foot">{scopeFoot}</p>
          </section>
          <section className="card stat-card" aria-label="Completed attempts">
            <p className="stat-label">Completed attempts</p>
            <p className="stat-value num">{formatCount(summary.period.completed)}</p>
            <p className="stat-foot">
              {formatCount(summary.period.succeeded)} succeeded · {formatCount(summary.period.failed)} failed
            </p>
          </section>
          <section className="card stat-card" aria-label="Failed attempts">
            <p className="stat-label">Failed attempts</p>
            <p className="stat-value num">{formatCount(summary.period.failed)}</p>
            <p className="stat-foot">
              {summary.period.failed > 0 ? (
                <Link to={drillHref(query, { tab: "attempts", outcome: "failed" })}>Review failed attempts</Link>
              ) : (
                "No failed attempts in this period"
              )}
            </p>
          </section>
          <section className="card stat-card" aria-label="Pending attempts">
            <p className="stat-label">Pending attempts</p>
            <p className="stat-value num">{formatCount(summary.period.pending)}</p>
            <p className="stat-foot">Not completed yet, so not counted in the success rate</p>
          </section>
        </div>
      ) : (
        <EmptyState
          title="No completed attempts in this period"
          body={
            summary.period.pending > 0
              ? `${formatCount(summary.period.pending)} attempt${summary.period.pending === 1 ? " is" : "s are"} still pending, so there is no success rate to show yet.`
              : "There is no success rate to show. Try a wider period or another channel."
          }
        />
      )}

      {hasCompleted ? (
        <section className="card chart-card" aria-labelledby="health-trend-heading">
          <div className="section-head">
            <h2 id="health-trend-heading" className="section-title">
              Daily success rate
            </h2>
            <p className="muted section-aside">{scopeFoot}</p>
          </div>
          <TrendChart data={data} />
        </section>
      ) : null}

      <section aria-labelledby="health-channels-heading" className="health-section">
        <div className="section-head">
          <h2 id="health-channels-heading" className="section-title">
            Performance by channel
          </h2>
          <p className="muted section-aside">Select a channel to scope the page to it</p>
        </div>
        <ChannelTable channels={data.channels} query={query} />
      </section>

      <div className="health-grid">
        <section aria-labelledby="health-signals-heading" className="health-section">
          <div className="section-head">
            <h2 id="health-signals-heading" className="section-title">
              Recorded failure signals
            </h2>
          </div>
          <p className="muted health-note">What the failed attempts recorded as their reason. These are recorded signals, not confirmed root causes.</p>
          <SignalTable signals={data.failure_signals} query={query} />
        </section>

        <section aria-labelledby="health-recovery-heading" className="health-section">
          <div className="section-head">
            <h2 id="health-recovery-heading" className="section-title">
              Affected payments and recovery
            </h2>
          </div>
          <p className="muted health-note">
            Counted once per payment created in the period. Values are payment amounts, not revenue.
          </p>
          <dl className="bucket-list health-recovery">
            <RecoveryRow label="Affected payments" count={recovery.affected_payments} cents={recovery.affected_cents} note={`${formatCount(recovery.failed_attempts)} failed attempts`} />
            <RecoveryRow
              label="Recovered"
              count={recovery.recovered_payments}
              cents={recovery.recovered_cents}
              note={`${formatCount(recovery.recovered_within_window_payments)} within ${rules.recovery_window_minutes} min of the first attempt (${formatCents(recovery.recovered_within_window_cents)})`}
            />
            <RecoveryRow label="Unresolved" count={recovery.unresolved_payments} cents={recovery.unresolved_cents} note="No successful attempt yet" />
            {recovery.retry_pending_payments > 0 ? (
              <RecoveryRow label="Retry pending" count={recovery.retry_pending_payments} cents={recovery.retry_pending_cents} note="Latest attempt still pending" />
            ) : null}
          </dl>
        </section>
      </div>

      <section aria-labelledby="health-unresolved-heading" className="health-section">
        <div className="section-head">
          <h2 id="health-unresolved-heading" className="section-title">
            Unresolved payments
          </h2>
          {data.unresolved_total > 0 ? (
            <Link to={drillHref(query, { status: "failed" })} className="section-aside">
              Review all {formatCount(data.unresolved_total)} in Payments
            </Link>
          ) : null}
        </div>
        <UnresolvedTable items={data.unresolved_payments} total={data.unresolved_total} />
      </section>

      <Definitions rules={rules} baselineRange={data.baseline_period.range_label} />
    </div>
  );
}

function AttentionSummary({ data, query }: { data: PaymentHealth; query: QueryState }) {
  const { attention, rules } = data;
  const degraded = data.channels.filter((c) => c.verdict === "degraded");
  const notJudged = data.channels.filter((c) => c.verdict === "insufficient_data");
  return (
    <>
      {degraded.length > 0 ? (
        <ul className="attention-list">
          {degraded.map((c) => (
            <li key={c.channel} className="attention-item attention-degraded">
              <span className="attention-dot" aria-hidden="true" />
              <div className="attention-body">
                <p className="attention-title">{c.channel_label} is degraded</p>
                <p className="attention-detail">
                  {formatRateBp(c.period.success_rate_bp)} success against a {formatRateBp(c.baseline.success_rate_bp)} baseline ({formatPointsBp(c.change_bp)}) ·{" "}
                  {formatCount(c.period.failed)} failed attempts
                </p>
                <p className="attention-when">
                  <Link to={drillHref(query, { status: "failed" }, c.channel)}>Review unresolved {c.channel_label.toLowerCase()} payments</Link>
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="attention-empty health-verdict" data-verdict={attention.verdict}>
          <StatusBadge status={attention.verdict === "no_degradation" ? "not_degraded" : "no_data"} label={ATTENTION_TEXT[attention.verdict]} />
        </p>
      )}
      {notJudged.length > 0 ? (
        <p className="muted health-note">
          Not judged, too few completed attempts:{" "}
          {notJudged
            .map((c) => `${c.channel_label} (${formatCount(c.period.completed)} in the period, ${formatCount(c.baseline.completed)} in the baseline)`)
            .join("; ")}
          . A channel needs {rules.min_period_completed} and {rules.min_baseline_completed}.
        </p>
      ) : null}
    </>
  );
}

const ATTENTION_TEXT: Record<string, string> = {
  degraded: "Degraded",
  no_degradation: "No significant degradation detected",
  not_enough_data: "Not enough completed attempts to judge any channel",
  no_data: "No completed attempts in this period",
};

function TrendChart({ data }: { data: PaymentHealth }) {
  const points = data.trend.map((p) => {
    const day = formatDateShort(p.day);
    const counts = `${formatCount(p.succeeded)} succeeded, ${formatCount(p.failed)} failed${p.pending ? `, ${formatCount(p.pending)} pending` : ""}`;
    const detail =
      p.success_rate_bp === null
        ? `${day}: no completed attempts${p.pending ? ` (${formatCount(p.pending)} pending)` : ""}`
        : `${day}: ${formatRateBp(p.success_rate_bp)} · ${counts}${p.low_volume ? " · low volume" : ""}`;
    return { label: day, value: p.success_rate_bp, lowVolume: p.low_volume, detail };
  });
  const baseline = data.summary.baseline.success_rate_bp;
  return (
    <>
      <LineChart
        title={`Daily success rate, ${data.summary.channel_label}, ${data.period.range_label}`}
        points={points}
        reference={baseline}
        referenceLabel={`Baseline ${data.baseline_period.range_label}`}
        formatValue={(v) => formatRateBp(v)}
        domainMax={10_000}
      />
      <ul className="chart-legend" aria-label="Chart key">
        <li>
          <span className="legend-line" aria-hidden="true" />
          Daily success rate
        </li>
        <li>
          <span className="legend-reference" aria-hidden="true" />
          Baseline {formatRateBp(baseline)} ({data.baseline_period.range_label})
        </li>
        <li>
          <span className="legend-low" aria-hidden="true" />
          Low volume (fewer than {data.rules.low_volume_day_completed} completed)
        </li>
        <li>
          <span className="legend-gap" aria-hidden="true">
            ·
          </span>
          Gap: no completed attempts
        </li>
      </ul>
      <details className="health-data">
        <summary>Show daily figures</summary>
        <div className="table-wrap">
          <table className="table">
            <caption className="visually-hidden">Daily success rate</caption>
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
                <tr key={p.day}>
                  <td>{formatDateShort(p.day)}</td>
                  <td className="money">{formatRateBp(p.success_rate_bp)}</td>
                  <td className="money">{formatCount(p.succeeded)}</td>
                  <td className="money">{formatCount(p.failed)}</td>
                  <td className="money">{formatCount(p.pending)}</td>
                  <td className="muted">{p.success_rate_bp === null ? "No completed attempts" : p.low_volume ? "Low volume" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

function ChannelTable({ channels, query }: { channels: ChannelHealth[]; query: QueryState }) {
  const selected = query.get("channel");
  const select = (c: ChannelHealth) => query.set({ channel: selected === c.channel ? null : c.channel });
  const columns: Column<ChannelHealth>[] = [
    {
      key: "channel",
      header: "Channel",
      className: "primary",
      render: (c) => (
        <button
          type="button"
          className="link-button row-link"
          aria-pressed={selected === c.channel}
          onClick={(e) => {
            e.stopPropagation();
            select(c);
          }}
        >
          {c.channel_label}
        </button>
      ),
    },
    { key: "status", header: "Status", render: (c) => <StatusBadge status={c.verdict} label={c.verdict_label} /> },
    { key: "rate", header: "Success rate", align: "right", render: (c) => formatRateBp(c.period.success_rate_bp) },
    { key: "baseline", header: "Baseline", align: "right", render: (c) => formatRateBp(c.baseline.success_rate_bp) },
    { key: "change", header: "Change", align: "right", render: (c) => formatPointsBp(c.change_bp) },
    { key: "completed", header: "Completed", align: "right", render: (c) => formatCount(c.period.completed) },
    { key: "failed", header: "Failed", align: "right", render: (c) => formatCount(c.period.failed) },
    { key: "pending", header: "Pending", align: "right", render: (c) => formatCount(c.period.pending) },
  ];
  return <DataTable caption="Performance by channel" columns={columns} rows={channels} rowKey={(c) => c.channel} onRowClick={select} isSelected={(c) => c.channel === selected} />;
}

function SignalTable({ signals, query }: { signals: FailureSignal[]; query: QueryState }) {
  const navigate = useNavigate();
  if (signals.length === 0) return <EmptyState title="No failed attempts in this period" body="Nothing recorded a failure signal." />;
  const href = (s: FailureSignal) => drillHref(query, { tab: "attempts", outcome: "failed", failure_code: s.code });
  const columns: Column<FailureSignal>[] = [
    {
      key: "signal",
      header: "Recorded signal",
      className: "primary",
      render: (s) => (
        <Link to={href(s)} className="row-link" onClick={(e) => e.stopPropagation()}>
          {s.label}
        </Link>
      ),
    },
    { key: "attempts", header: "Failed attempts", align: "right", render: (s) => formatCount(s.attempts) },
    { key: "payments", header: "Payments", align: "right", render: (s) => formatCount(s.payments) },
  ];
  return <DataTable caption="Recorded failure signals" columns={columns} rows={signals} rowKey={(s) => s.code} onRowClick={(s) => navigate(href(s))} />;
}

function RecoveryRow({ label, count, cents, note }: { label: string; count: number; cents: number; note: string }) {
  return (
    <div className="bucket-row">
      <dt>
        {label}
        <span className="health-row-note muted">{note}</span>
      </dt>
      <dd className="money">
        <span className="num">{formatCount(count)}</span> · <Money cents={cents} />
      </dd>
    </div>
  );
}

function UnresolvedTable({ items, total }: { items: PaymentListItem[]; total: number }) {
  const navigate = useNavigate();
  if (items.length === 0) return <EmptyState title="No unresolved payments" body="Every affected payment in this scope has recovered or is still pending." />;
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
    { key: "channel", header: "Channel", render: (p) => (p.location ? `${p.channel_label} · ${p.location.name}` : p.channel_label) },
    { key: "status", header: "Status", render: (p) => <StatusBadge status={p.status} label={p.status_label} /> },
    { key: "amount", header: "Amount", align: "right", render: (p) => <Money cents={p.amount_cents} /> },
  ];
  return (
    <>
      <DataTable caption="Unresolved payments" columns={columns} rows={items} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/payments/${p.id}`)} />
      {total > items.length ? (
        <p className="muted health-note">
          Showing the {items.length} most recent of {formatCount(total)}.
        </p>
      ) : null}
    </>
  );
}

function Definitions({ rules, baselineRange }: { rules: HealthRules; baselineRange: string }) {
  const points = `${formatRateBp(rules.degraded_drop_bp).replace("%", "")} percentage points`;
  return (
    <details className="card health-definitions">
      <summary className="section-title">How these figures are defined</summary>
      <dl>
        <dt>Success rate</dt>
        <dd>Succeeded attempts divided by completed attempts (succeeded plus failed). Pending attempts are not completed and are counted separately.</dd>
        <dt>Baseline</dt>
        <dd>
          The same channel's success rate over the {rules.baseline_days} days before the selected period ({baselineRange}).
        </dd>
        <dt>Degraded</dt>
        <dd>
          A channel whose success rate is {points} or more below its baseline. A channel is judged only when the period has at least{" "}
          {rules.min_period_completed} completed attempts and the baseline at least {rules.min_baseline_completed}; otherwise the page says there is not enough
          data. The rule is fixed and the same for every channel.
        </dd>
        <dt>Low-volume day</dt>
        <dd>A day with fewer than {rules.low_volume_day_completed} completed attempts. Its rate is shown but can swing on a handful of attempts.</dd>
        <dt>Affected payment</dt>
        <dd>A payment created in the period with at least one failed attempt. Each payment counts once, at its amount, however many attempts it took.</dd>
        <dt>Recovered</dt>
        <dd>
          An affected payment that later had a successful attempt. Recovered within {rules.recovery_window_minutes} minutes means the success completed no more than{" "}
          {rules.recovery_window_minutes} minutes after the payment's first attempt.
        </dd>
        <dt>Unresolved</dt>
        <dd>An affected payment with no successful attempt whose latest attempt failed. These are the payments listed with status Failed.</dd>
        <dt>Recorded failure signal</dt>
        <dd>The reason a failed attempt recorded. It describes the attempt; it is not a confirmed root cause.</dd>
      </dl>
    </details>
  );
}
