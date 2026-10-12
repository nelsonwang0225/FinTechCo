import { useId } from "react";
import { useContainerWidth } from "./BarChart";

export interface RatePoint {
  label: string;
  /** Integer basis points, or null when nothing completed that day (drawn as a gap, never as zero). */
  rateBp: number | null;
  lowVolume: boolean;
  /** Tooltip and description text for the day, e.g. counts behind the rate. */
  detail: string;
}

const FULL_BP = 10000;
const STEP_BP = 1000;

/** Gridlines on whole 10-point steps (20-point when the range is wide), the lowest at least 5 points below the lowest value. */
function gridlines(values: number[]): number[] {
  const lowest = values.length === 0 ? 0 : Math.min(...values) - STEP_BP / 2;
  const step = FULL_BP - lowest > 6 * STEP_BP ? 2 * STEP_BP : STEP_BP;
  const lo = Math.max(0, Math.floor(lowest / step) * step);
  const ticks: number[] = [];
  for (let t = lo; t <= FULL_BP; t += step) ticks.push(t);
  return ticks;
}

/** Consecutive runs of days that have a rate; a day without one breaks the line. */
function runs(points: RatePoint[]): number[][] {
  const out: number[][] = [];
  let current: number[] = [];
  points.forEach((p, i) => {
    if (p.rateBp === null) {
      if (current.length) out.push(current);
      current = [];
    } else {
      current.push(i);
    }
  });
  if (current.length) out.push(current);
  return out;
}

/**
 * Hand-written SVG line chart of a daily rate with an optional dashed baseline. Days with no rate leave a gap; low-volume
 * days are hollow markers. Each marker carries a text tooltip, and the description lists every day for screen readers.
 */
export function RateChart({
  title,
  points,
  baselineBp,
  baselineLabel,
  formatRate,
  height = 240,
}: {
  title: string;
  points: RatePoint[];
  baselineBp: number | null;
  baselineLabel: string;
  formatRate: (bp: number) => string;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const rated = points.flatMap((p) => (p.rateBp === null ? [] : [p.rateBp]));
  const ticks = gridlines(baselineBp === null ? rated : [...rated, baselineBp]);
  const lo = ticks[0] ?? 0;
  const span = FULL_BP - lo || FULL_BP;

  const left = 52;
  const right = 12;
  const top = 10;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const slot = points.length === 0 ? plotWidth : plotWidth / points.length;
  const x = (i: number) => left + slot * i + slot / 2;
  const y = (bp: number) => top + plotHeight - ((bp - lo) / span) * plotHeight;
  const labelEvery = Math.max(1, Math.ceil(points.length / 14));
  const description = [
    baselineBp === null ? "No baseline." : `${baselineLabel}: ${formatRate(baselineBp)}.`,
    ...points.map((p) => `${p.label}: ${p.detail}`),
  ].join(" ");

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart rate-chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {ticks.map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {formatRate(t)}
            </text>
          </g>
        ))}
        {baselineBp !== null ? (
          <g className="chart-baseline">
            <title>{`${baselineLabel}: ${formatRate(baselineBp)}`}</title>
            <line x1={left} x2={width - right} y1={y(baselineBp)} y2={y(baselineBp)} />
          </g>
        ) : null}
        {runs(points).map((run) => (
          <polyline key={run[0]} className="chart-line" points={run.map((i) => `${x(i)},${y(points[i]!.rateBp!)}`).join(" ")} />
        ))}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`} className={p.rateBp === null ? "chart-day chart-day-empty" : "chart-day"}>
            <title>{`${p.label}: ${p.detail}`}</title>
            {p.rateBp === null ? (
              <rect x={x(i) - slot / 2} y={top} width={slot} height={plotHeight} className="chart-hit" />
            ) : (
              <circle cx={x(i)} cy={y(p.rateBp)} r={p.lowVolume ? 4.5 : 3.5} className={p.lowVolume ? "chart-point chart-point-low" : "chart-point"} />
            )}
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
