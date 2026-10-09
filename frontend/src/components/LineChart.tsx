import { useId } from "react";
import { useContainerWidth } from "./chartSize";

export interface LineChartPoint {
  label: string;
  /** Integer basis points on the fixed 0..10000 domain; null draws a gap (no completed attempts). */
  value: number | null;
  /** Drawn as a hollow marker so a rate computed from a handful of attempts reads differently. */
  lowVolume?: boolean;
  /** The marker's tooltip text and its entry in the accessible description. */
  tooltip: string;
}

const Y_MAX = 10000;
const TICKS = [0, 2500, 5000, 7500, 10000];
const MARKER_RADIUS = 4;
const HOVER_RADIUS = 10;
const GAP_TEXT = "no completed attempts";

/**
 * Generic hand-written SVG line chart for a daily rate series on a fixed 0..10000 basis-point domain: gridlines
 * at every quarter, a marker with a text tooltip per value, gaps where a day has no value, hollow markers for
 * low-volume days and an optional dashed baseline. It never navigates anywhere; the caller formats values.
 */
export function LineChart({
  title,
  series,
  baseline,
  baselineLabel,
  formatTick,
  lowVolumeLegend,
  height = 240,
}: {
  title: string;
  series: LineChartPoint[];
  /** A reference rate in basis points drawn as a dashed horizontal line; nothing is drawn when null or undefined. */
  baseline?: number | null;
  /** Small text at the right end of the baseline. */
  baselineLabel?: string;
  /** Formats gridline labels, e.g. 7500 -> "75%". */
  formatTick: (value: number) => string;
  /** Shown under the chart with a hollow marker when any point is low volume. */
  lowVolumeLegend?: string;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const left = 64;
  const bottom = 28;
  const top = 8;
  const right = 8;
  const plotHeight = height - top - bottom;
  const plotWidth = width - left - right;
  const slot = series.length === 0 ? plotWidth : plotWidth / series.length;
  const labelEvery = Math.max(1, Math.ceil(series.length / 14));
  const xAt = (i: number) => left + (i + 0.5) * slot;
  const yAt = (value: number) => top + plotHeight - (Math.min(Math.max(value, 0), Y_MAX) / Y_MAX) * plotHeight;

  const description =
    series.length === 0 ? "No values." : series.map((p) => `${p.label}: ${p.value === null ? GAP_TEXT : p.tooltip}`).join("; ");

  // Consecutive non-null points form one run; a run is a line segment, and a null between runs leaves a gap.
  const runs: Array<Array<{ x: number; y: number }>> = [];
  series.forEach((p, i) => {
    if (p.value === null) {
      if (runs[runs.length - 1]?.length) runs.push([]);
      return;
    }
    if (runs.length === 0) runs.push([]);
    runs[runs.length - 1]?.push({ x: xAt(i), y: yAt(p.value) });
  });
  const paths = runs
    .filter((run) => run.length >= 2)
    .map((run) => run.map((pt, j) => `${j === 0 ? "M" : "L"}${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(" "));

  const hasBaseline = typeof baseline === "number";
  const baselineY = hasBaseline ? yAt(baseline) : 0;
  // The label sits above the line unless the line is close to the top of the plot.
  const baselineLabelY = baselineY - 6 < top + 10 ? baselineY + 14 : baselineY - 6;
  const showLegend = Boolean(lowVolumeLegend) && series.some((p) => p.lowVolume && p.value !== null);

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {TICKS.map((t) => {
          const y = yAt(t);
          return (
            <g key={t} className="chart-grid">
              <line x1={left} x2={width - right} y1={y} y2={y} />
              <text x={left - 8} y={y + 4} textAnchor="end" className="chart-tick">
                {formatTick(t)}
              </text>
            </g>
          );
        })}
        {hasBaseline ? (
          <g className="chart-baseline-group">
            <line className="chart-baseline" x1={left} x2={width - right} y1={baselineY} y2={baselineY} />
            {baselineLabel ? (
              <text className="chart-baseline-label" x={width - right} y={baselineLabelY} textAnchor="end">
                {baselineLabel}
              </text>
            ) : null}
          </g>
        ) : null}
        {paths.map((d, i) => (
          <path key={i} className="chart-line" d={d} />
        ))}
        {series.map((p, i) => {
          const x = xAt(i);
          const label =
            i % labelEvery === 0 ? (
              <text x={x} y={height - 8} textAnchor="middle" className="chart-label">
                {p.label}
              </text>
            ) : null;
          if (p.value === null) {
            return <g key={`${p.label}-${i}`}>{label}</g>;
          }
          const y = yAt(p.value);
          return (
            <g key={`${p.label}-${i}`} className="chart-point-group">
              <title>{p.tooltip}</title>
              <circle className="chart-point-target" cx={x} cy={y} r={HOVER_RADIUS} />
              <circle className={p.lowVolume ? "chart-point chart-point-low" : "chart-point"} cx={x} cy={y} r={MARKER_RADIUS} />
              {label}
            </g>
          );
        })}
      </svg>
      {showLegend ? (
        <p className="chart-legend">
          <svg className="chart-legend-marker" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
            <circle className="chart-point chart-point-low" cx="6" cy="6" r="4" />
          </svg>
          <span>{lowVolumeLegend}</span>
        </p>
      ) : null}
    </div>
  );
}
