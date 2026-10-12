import { useId } from "react";
import { useContainerWidth } from "./BarChart";

export interface LineChartPoint {
  label: string;
  /** null leaves a gap: there is nothing to plot for this point. */
  value: number | null;
  /** Plotted with a hollow marker and called out in the description. */
  lowVolume?: boolean;
  /** Tooltip and description text for the point, e.g. counts behind the value. */
  detail: string;
}

/** Split a series into runs of consecutive plotted points, so a null breaks the line instead of drawing through it. */
export function segments<T extends { value: number | null }>(points: T[]): { index: number; value: number }[][] {
  const runs: { index: number; value: number }[][] = [];
  let current: { index: number; value: number }[] = [];
  points.forEach((p, index) => {
    if (p.value === null) {
      if (current.length) runs.push(current);
      current = [];
    } else {
      current.push({ index, value: p.value });
    }
  });
  if (current.length) runs.push(current);
  return runs;
}

/**
 * Hand-written SVG line chart for one daily series with an optional dashed reference line. Gaps stay gaps, low-volume
 * points get a hollow marker, and every point carries a text tooltip and a line in the accessible description.
 */
export function LineChart({
  title,
  points,
  reference = null,
  referenceLabel = "Baseline",
  min,
  max,
  formatValue,
  height = 240,
}: {
  title: string;
  points: LineChartPoint[];
  reference?: number | null;
  referenceLabel?: string;
  min: number;
  max: number;
  formatValue: (value: number) => string;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const left = 56;
  const right = 12;
  const top = 12;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const span = max - min || 1;
  const slot = points.length === 0 ? plotWidth : plotWidth / points.length;
  const x = (i: number) => left + i * slot + slot / 2;
  const y = (v: number) => top + plotHeight - ((Math.min(Math.max(v, min), max) - min) / span) * plotHeight;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(min + span * f));
  const labelEvery = Math.max(1, Math.ceil(points.length / 14));
  const description = [
    reference !== null ? `${referenceLabel}: ${formatValue(reference)}.` : null,
    ...points.map((p) => `${p.label}: ${p.detail}${p.lowVolume ? " (low volume)" : ""}.`),
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {ticks.map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {formatValue(t)}
            </text>
          </g>
        ))}
        {reference !== null ? (
          <g className="chart-reference">
            <title>{`${referenceLabel}: ${formatValue(reference)}`}</title>
            <line x1={left} x2={width - right} y1={y(reference)} y2={y(reference)} />
          </g>
        ) : null}
        {segments(points).map((run) => (
          <path
            key={run[0]?.index}
            className="chart-line"
            d={run.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.index).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ")}
          />
        ))}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`} className={p.value === null ? "chart-point chart-point-gap" : p.lowVolume ? "chart-point chart-point-low" : "chart-point"}>
            <title>{`${p.label}: ${p.detail}${p.lowVolume ? " (low volume)" : ""}`}</title>
            {/* A full-height hit area so gaps and points both show their tooltip on hover. */}
            <rect className="chart-hit" x={x(i) - slot / 2} y={top} width={slot} height={plotHeight} />
            {p.value !== null ? <circle cx={x(i)} cy={y(p.value)} r={p.lowVolume ? 4 : 3} /> : null}
            {i % labelEvery === 0 ? (
              <text x={x(i)} y={height - 8} textAnchor="middle" className="chart-label">
                {p.label}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
    </div>
  );
}
