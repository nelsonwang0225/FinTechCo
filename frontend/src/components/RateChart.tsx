import { useId } from "react";
import { useContainerWidth } from "./BarChart";

export interface RatePoint {
  label: string;
  /** Basis points, or null on a day with nothing to rate: the line breaks there instead of drawing a zero. */
  rateBps: number | null;
  lowVolume: boolean;
  /** Counts behind the point, shown on hover and in the text description. */
  detail: string;
}

const TICKS = [0, 2500, 5000, 7500, 10000];

/**
 * Hand-written SVG line chart for a rate on a fixed 0–100% scale. Days without a rate are gaps, low-volume days are
 * hollow markers, and an optional dashed baseline is drawn across. Every point carries a text tooltip and the whole
 * series is described in text, so nothing relies on colour or hover alone.
 */
export function RateChart({
  title,
  points,
  baselineBps,
  baselineLabel,
  formatRate,
  height = 240,
}: {
  title: string;
  points: RatePoint[];
  baselineBps: number | null;
  baselineLabel: string;
  formatRate: (bps: number) => string;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const left = 56;
  const right = 12;
  const top = 10;
  const bottom = 28;
  const plotHeight = height - top - bottom;
  const plotWidth = width - left - right;
  const slot = points.length === 0 ? plotWidth : plotWidth / points.length;
  const labelEvery = Math.max(1, Math.ceil(points.length / 14));
  const x = (i: number) => left + i * slot + slot / 2;
  const y = (bps: number) => top + plotHeight - (bps / 10000) * plotHeight;

  // Consecutive days with a rate form one segment; a day without one ends it.
  const segments: number[][] = [];
  let current: number[] = [];
  points.forEach((p, i) => {
    if (p.rateBps === null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push(i);
    }
  });
  if (current.length) segments.push(current);

  const description = [
    baselineBps === null ? "No baseline." : `${baselineLabel}: ${formatRate(baselineBps)}.`,
    ...points.map((p) => `${p.label}: ${p.rateBps === null ? "no completed attempts" : formatRate(p.rateBps)}${p.lowVolume && p.rateBps !== null ? ", low volume" : ""} (${p.detail})`),
  ].join(" ");

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart rate-chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {TICKS.map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {formatRate(t)}
            </text>
          </g>
        ))}
        {baselineBps !== null ? (
          <g className="chart-baseline">
            <title>{`${baselineLabel}: ${formatRate(baselineBps)}`}</title>
            <line x1={left} x2={width - right} y1={y(baselineBps)} y2={y(baselineBps)} />
          </g>
        ) : null}
        {segments.map((seg) => (
          <path key={seg[0]} className="chart-line" d={seg.map((i, n) => `${n === 0 ? "M" : "L"}${x(i)} ${y(points[i].rateBps as number)}`).join(" ")} />
        ))}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`} className={p.rateBps === null ? "chart-gap" : p.lowVolume ? "chart-point chart-point-low" : "chart-point"}>
            <title>{`${p.label}: ${p.rateBps === null ? "no completed attempts" : formatRate(p.rateBps)}${p.lowVolume && p.rateBps !== null ? " (low volume)" : ""} · ${p.detail}`}</title>
            {p.rateBps === null ? (
              <line x1={x(i) - 4} x2={x(i) + 4} y1={top + plotHeight} y2={top + plotHeight} />
            ) : (
              <circle cx={x(i)} cy={y(p.rateBps)} r={p.lowVolume ? 4.5 : 3.5} />
            )}
            {/* A wide transparent target so the tooltip is easy to reach. */}
            <rect x={left + i * slot} y={top} width={slot} height={plotHeight} className="chart-hit" />
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
