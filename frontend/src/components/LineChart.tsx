import { useId } from "react";
import { useContainerWidth } from "./BarChart";

export interface LineChartPoint {
  label: string;
  /** Null leaves a gap: the line breaks and no point is drawn. */
  value: number | null;
  /** Drawn as a hollow point and explained in the legend. */
  lowVolume?: boolean;
  /** Tooltip and description text for this point, e.g. the counts behind the value. */
  detail: string;
}

/** Lower bound for the value axis: a whole step below the smallest value, so small dips stay visible. */
export function axisFloor(values: number[], max: number, step: number): number {
  if (values.length === 0) return 0;
  const min = Math.min(...values);
  return Math.max(0, Math.min(max - step, Math.floor((min - step / 2) / step) * step));
}

/** Runs of consecutive non-null points; each run is drawn as its own line so empty days are gaps, never zeros. */
export function segments<T extends { value: number | null }>(points: T[]): { index: number; value: number }[][] {
  const out: { index: number; value: number }[][] = [];
  let run: { index: number; value: number }[] = [];
  points.forEach((p, index) => {
    if (p.value === null) {
      if (run.length) out.push(run);
      run = [];
    } else {
      run.push({ index, value: p.value });
    }
  });
  if (run.length) out.push(run);
  return out;
}

/**
 * Hand-written SVG line chart for one daily series against a flat reference line. Null values are gaps, low-volume
 * points are hollow, every point has a text tooltip, and the description lists every point for assistive technology.
 */
export function LineChart({
  title,
  points,
  reference,
  formatTick,
  max,
  step,
  seriesLabel,
  lowVolumeLabel,
  gapLabel,
  height = 240,
}: {
  title: string;
  points: LineChartPoint[];
  /** A flat comparison line (e.g. a baseline), or null to omit it. */
  reference: { value: number; label: string } | null;
  formatTick: (value: number) => string;
  /** Top of the value axis. */
  max: number;
  /** Gridline spacing on the value axis. */
  step: number;
  /** Legend text for the line, the hollow points and the gaps. */
  seriesLabel: string;
  lowVolumeLabel: string;
  gapLabel: string;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const values = points.flatMap((p) => (p.value === null ? [] : [p.value]));
  const floor = axisFloor(reference ? [...values, reference.value] : values, max, step);
  const ticks: number[] = [];
  for (let t = floor; t <= max; t += step) ticks.push(t);

  const left = 56;
  const right = 24;
  const top = 10;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const x = (i: number) => left + (points.length <= 1 ? plotWidth / 2 : (i / (points.length - 1)) * plotWidth);
  const y = (v: number) => top + plotHeight - ((Math.min(Math.max(v, floor), max) - floor) / (max - floor)) * plotHeight;
  const labelEvery = Math.max(1, Math.ceil(points.length / 10));
  const description = [
    reference ? reference.label : null,
    ...points.map((p) => `${p.label}: ${p.detail}`),
  ].filter(Boolean).join("; ");

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart line-chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {ticks.map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {formatTick(t)}
            </text>
          </g>
        ))}
        {reference ? (
          <g className="chart-reference">
            <title>{reference.label}</title>
            <line x1={left} x2={width - right} y1={y(reference.value)} y2={y(reference.value)} />
          </g>
        ) : null}
        {segments(points).filter((run) => run.length > 1).map((run) => (
          <polyline key={run[0]?.index} className="chart-line" points={run.map((p) => `${x(p.index)},${y(p.value)}`).join(" ")} />
        ))}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`} className={p.value === null ? "chart-point chart-gap" : p.lowVolume ? "chart-point low-volume" : "chart-point"}>
            <title>{`${p.label}: ${p.detail}`}</title>
            {p.value === null ? (
              <rect className="chart-hit" x={x(i) - 6} y={top} width={12} height={plotHeight} />
            ) : (
              <>
                <circle className="chart-hit" cx={x(i)} cy={y(p.value)} r={10} />
                <circle className="chart-dot" cx={x(i)} cy={y(p.value)} r={p.lowVolume ? 4 : 3.5} />
              </>
            )}
            {i % labelEvery === 0 ? (
              <text x={x(i)} y={height - 8} textAnchor={i === points.length - 1 && points.length > 1 ? "end" : "middle"} className="chart-label">
                {p.label}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
      <ul className="chart-legend">
        <li>
          <span className="legend-swatch legend-line" aria-hidden="true" />
          {seriesLabel}
        </li>
        {reference ? (
          <li>
            <span className="legend-swatch legend-reference" aria-hidden="true" />
            {reference.label}
          </li>
        ) : null}
        {points.some((p) => p.lowVolume) ? (
          <li>
            <span className="legend-swatch legend-hollow" aria-hidden="true" />
            {lowVolumeLabel}
          </li>
        ) : null}
        {points.some((p) => p.value === null) ? (
          <li>
            <span className="legend-swatch legend-gap" aria-hidden="true" />
            {gapLabel}
          </li>
        ) : null}
      </ul>
    </div>
  );
}
