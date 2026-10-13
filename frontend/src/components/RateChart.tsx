import { useId } from "react";
import { useContainerWidth } from "./BarChart";

export interface RatePoint {
  label: string;
  /** Rate in basis points; null leaves a gap (nothing to rate that day). */
  rateBps: number | null;
  /** Marked with a hollow point and called out in its tooltip. */
  lowVolume: boolean;
  /** Tooltip and description text for the point, e.g. counts. */
  detail: string;
}

const TICKS = [0, 2500, 5000, 7500, 10000];

/**
 * Hand-written SVG line chart for a daily rate on a fixed 0–100% axis. Days without a rate break the line, low-volume
 * days are hollow points, and an optional dashed line shows a baseline. Every point is focusable and carries its counts.
 */
export function RateChart({
  title,
  points,
  baselineBps,
  formatRate,
  height = 240,
}: {
  title: string;
  points: RatePoint[];
  baselineBps: number | null;
  formatRate: (bps: number | null) => string;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const left = 48;
  const right = 12;
  const top = 10;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const slot = points.length === 0 ? plotWidth : plotWidth / points.length;
  const x = (i: number) => left + slot * i + slot / 2;
  const y = (bps: number) => top + plotHeight - (bps / 10000) * plotHeight;
  const labelEvery = Math.max(1, Math.ceil(points.length / 14));

  // Consecutive days with a rate form one segment; a day without one ends it.
  const segments: { i: number; bps: number }[][] = [];
  let current: { i: number; bps: number }[] = [];
  points.forEach((p, i) => {
    if (p.rateBps === null) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push({ i, bps: p.rateBps });
  });
  if (current.length) segments.push(current);

  const baselineText = baselineBps === null ? "No baseline." : `Baseline ${formatRate(baselineBps)}.`;
  const description = [baselineText, ...points.map((p) => `${p.label}: ${p.detail}`)].join(" ");

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart rate-chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="group" aria-labelledby={titleId} aria-describedby={descId}>
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {TICKS.map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {`${t / 100}%`}
            </text>
          </g>
        ))}
        {baselineBps !== null ? <line className="rate-baseline" x1={left} x2={width - right} y1={y(baselineBps)} y2={y(baselineBps)} /> : null}
        {segments.map((seg) => (
          <polyline key={seg[0].i} className="rate-line" points={seg.map((s) => `${x(s.i)},${y(s.bps)}`).join(" ")} />
        ))}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`}>
            {p.rateBps !== null ? (
              <circle
                className={p.lowVolume ? "rate-point rate-point-low" : "rate-point"}
                cx={x(i)}
                cy={y(p.rateBps)}
                r={p.lowVolume ? 4.5 : 3.5}
                tabIndex={0}
                aria-label={`${p.label}: ${p.detail}`}
              >
                <title>{`${p.label}: ${p.detail}`}</title>
              </circle>
            ) : (
              <text className="rate-gap" x={x(i)} y={top + plotHeight - 4} textAnchor="middle">
                <title>{`${p.label}: ${p.detail}`}</title>
                ×
              </text>
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
