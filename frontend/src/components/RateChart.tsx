import { useId } from "react";
import { formatRate } from "../lib/format";
import { useContainerWidth } from "./BarChart";

export interface RatePoint {
  label: string;
  /** Basis points, or null when nothing completed that day: the line breaks there instead of inventing a value. */
  rateBp: number | null;
  /** Counts shown on hover and in the description, e.g. "25 succeeded · 36 failed · 0 pending". */
  detail: string;
  lowVolume: boolean;
}

/**
 * Hand-written SVG line chart of a daily rate on a fixed 0–100% axis, with a dashed baseline. Days with no value
 * leave a gap; low-volume days get a hollow marker and say so in their tooltip, so the distinction is never colour
 * alone. Every point is listed in the description for screen readers.
 */
export function RateChart({ title, points, baselineBp, baselineLabel, height = 240 }: {
  title: string;
  points: RatePoint[];
  baselineBp: number | null;
  baselineLabel: string;
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
  const plotHeight = height - top - bottom;
  const plotWidth = width - left - right;
  const slot = points.length === 0 ? plotWidth : plotWidth / points.length;
  const x = (i: number) => left + i * slot + slot / 2;
  const y = (bp: number) => top + plotHeight - (bp / 10000) * plotHeight;
  const labelEvery = Math.max(1, Math.ceil(points.length / 14));

  // Consecutive non-null points form one segment; a null day ends it.
  const segments: { i: number; bp: number }[][] = [];
  let run: { i: number; bp: number }[] = [];
  points.forEach((p, i) => {
    if (p.rateBp === null) {
      if (run.length) segments.push(run);
      run = [];
    } else {
      run.push({ i, bp: p.rateBp });
    }
  });
  if (run.length) segments.push(run);

  const description = [
    baselineBp === null ? `${baselineLabel}: no completed attempts.` : `${baselineLabel}: ${formatRate(baselineBp)}.`,
    ...points.map((p) => `${p.label}: ${p.rateBp === null ? "no completed attempts" : formatRate(p.rateBp)}${p.lowVolume && p.rateBp !== null ? ", low volume" : ""} (${p.detail})`),
  ].join(" ");

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart rate-chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {[0, 2500, 5000, 7500, 10000].map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {`${t / 100}%`}
            </text>
          </g>
        ))}
        {baselineBp !== null ? (
          <g className="chart-baseline">
            <title>{`${baselineLabel}: ${formatRate(baselineBp)}`}</title>
            <line x1={left} x2={width - right} y1={y(baselineBp)} y2={y(baselineBp)} />
          </g>
        ) : null}
        {segments.map((seg) =>
          seg.length > 1 ? (
            <polyline key={`seg-${seg[0]?.i}`} className="chart-line" points={seg.map((p) => `${x(p.i)},${y(p.bp)}`).join(" ")} />
          ) : null,
        )}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`} className={p.rateBp === null ? "chart-point chart-point-gap" : p.lowVolume ? "chart-point chart-point-low" : "chart-point"}>
            <title>{`${p.label} · ${p.rateBp === null ? "No completed attempts" : formatRate(p.rateBp)}${p.lowVolume && p.rateBp !== null ? " · low volume" : ""} · ${p.detail}`}</title>
            {/* A full-height hit area so the tooltip works on gap days too. */}
            <rect className="chart-hit" x={left + i * slot} y={top} width={slot} height={plotHeight} />
            {p.rateBp !== null ? <circle cx={x(i)} cy={y(p.rateBp)} r={p.lowVolume ? 4 : 3.5} /> : null}
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
