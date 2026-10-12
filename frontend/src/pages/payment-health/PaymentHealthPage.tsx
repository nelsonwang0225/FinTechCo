import { Link } from "react-router-dom";
import { queryString } from "../../api/client";
import type { PaymentHealth } from "../../api/payment-health-types";
import type { Meta } from "../../api/types";
import { useApi } from "../../api/useApi";
import { FilterBar, FilterSelect } from "../../components/FilterBar";
import { RateChart } from "../../components/RateChart";
import { EmptyState, LoadError, LoadingState } from "../../components/states";
import { PageHeader } from "../../layout/PageHeader";
import { formatCount, formatDateShort, formatPointChange, formatRate } from "../../lib/format";
import { attemptsLink, healthPath, type Scope } from "../../lib/healthLinks";
import { useQueryState } from "../../lib/query";
import { PeriodFilter, periodParams } from "../payments/PeriodFilter";
import { AttentionSummary, ChannelTable, Definitions, FailureSignals, RecoveryPanel } from "./HealthSections";

export function PaymentHealthPage() {
  const query = useQueryState();
  const meta = useApi<Meta>("/api/meta");
  const channel = query.get("channel");
  const scope: Scope = { ...periodParams(query), channel: channel || undefined };
  const health = useApi<PaymentHealth>(`/api/payment-health${queryString(scope)}`);

  return (
    <>
      <PageHeader
        title="Payment Health"
        subtitle="Completed-attempt success by channel, compared with each channel's own recent baseline. Times are shown in America/Chicago."
        actions={
          meta.data ? (
            <FilterBar>
              <PeriodFilter query={query} presets={meta.data.period_presets} idPrefix="health-period" />
              <FilterSelect id="health-channel" label="Channel" value={channel} options={meta.data.channels} allLabel="All channels" onChange={(v) => query.set({ channel: v })} />
            </FilterBar>
          ) : undefined
        }
      />
      {health.error ? <LoadError error={health.error} onRetry={health.reload} /> : null}
      {!health.error && !health.data ? <LoadingState rows={8} label="Loading payment health" /> : null}
      {health.data ? <HealthBody data={health.data} scope={scope} loading={health.loading} onChannel={(c) => query.set({ channel: c })} /> : null}
    </>
  );
}

function HealthBody({ data, scope, loading, onChannel }: { data: PaymentHealth; scope: Scope; loading: boolean; onChannel: (channel: string | null) => void }) {
  const returnTo = healthPath(scope);
  const a = data.attempts;
  const scopeLabel = data.channel_label ?? "All channels";
  return (
    <div className={loading ? "health health-loading" : "health"} aria-busy={loading || undefined}>
      <p className="toolbar-note">
        <span>
          {scopeLabel} · {data.period.label}: {data.period.range_label} · Baseline: {data.baseline.range_label} ({data.baseline.days_with_completed} of {data.baseline.days} days with
          completed attempts)
        </span>
      </p>

      <AttentionSummary data={data} scope={scope} returnTo={returnTo} />

      {a.completed === 0 ? (
        <EmptyState
          title="No completed attempts in this period"
          body={
            a.pending > 0 ? (
              <>
                {formatCount(a.pending)} attempt{a.pending === 1 ? " is" : "s are"} still pending, so there is no success rate to show.{" "}
                <Link to={attemptsLink(scope, { outcome: "pending" }, returnTo)}>View pending attempts</Link>
              </>
            ) : (
              "There is no success rate to show. Try a wider period or another channel."
            )
          }
        />
      ) : (
        <>
          <div className="cards cards-4">
            <section className="card stat-card" aria-label="Success rate">
              <p className="stat-label">Success rate</p>
              <p className="stat-value">{formatRate(a.success_rate_bp)}</p>
              <p className="stat-foot">
                Baseline {formatRate(a.baseline_rate_bp)} · {formatPointChange(a.change_bp)}
              </p>
            </section>
            <section className="card stat-card" aria-label="Completed attempts">
              <p className="stat-label">Completed attempts</p>
              <p className="stat-value">{formatCount(a.completed)}</p>
              <p className="stat-foot">
                {formatCount(a.succeeded)} succeeded · {formatCount(a.failed)} failed
              </p>
            </section>
            <section className="card stat-card" aria-label="Failed attempts">
              <p className="stat-label">Failed attempts</p>
              <p className="stat-value">{formatCount(a.failed)}</p>
              <p className="stat-foot">{a.failed > 0 ? <Link to={attemptsLink(scope, { outcome: "failed" }, returnTo)}>View failed attempts</Link> : "No failed attempts"}</p>
            </section>
            <section className="card stat-card" aria-label="Pending attempts">
              <p className="stat-label">Pending attempts</p>
              <p className="stat-value">{formatCount(a.pending)}</p>
              <p className="stat-foot">
                {a.pending > 0 ? (
                  <>
                    Not counted in the rate · <Link to={attemptsLink(scope, { outcome: "pending" }, returnTo)}>View</Link>
                  </>
                ) : (
                  "None awaiting an outcome"
                )}
              </p>
            </section>
          </div>

          <div className="health-grid">
            <section className="card chart-card" aria-labelledby="trend-heading">
              <h2 id="trend-heading" className="section-title">
                Daily success rate · {scopeLabel}
              </h2>
              <RateChart
                title={`Daily success rate, ${scopeLabel}, ${data.period.range_label}`}
                baselineBp={a.baseline_rate_bp}
                baselineLabel={`Baseline ${data.baseline.range_label}`}
                formatRate={formatRate}
                points={data.trend.map((p) => ({
                  label: formatDateShort(p.day),
                  rateBp: p.success_rate_bp,
                  lowVolume: p.low_volume,
                  detail:
                    p.completed === 0
                      ? `no completed attempts${p.pending ? `, ${p.pending} pending` : ""}`
                      : `${formatRate(p.success_rate_bp)} (${p.succeeded} of ${p.completed} completed attempts succeeded, ${p.failed} failed${p.pending ? `, ${p.pending} pending` : ""})${p.low_volume ? ", low volume" : ""}`,
                }))}
              />
              <p className="muted chart-legend">
                <span className="legend legend-line">Success rate</span>
                <span className="legend legend-baseline">Baseline {formatRate(a.baseline_rate_bp)}</span>
                <span className="legend legend-low">Fewer than {data.rules.low_volume_day_completed} completed</span>
              </p>
            </section>
            <FailureSignals data={data} scope={scope} returnTo={returnTo} />
          </div>

          <ChannelTable data={data} onChannel={onChannel} />
        </>
      )}

      <RecoveryPanel data={data} scope={scope} returnTo={returnTo} />
      <Definitions rules={data.rules} />
    </div>
  );
}
