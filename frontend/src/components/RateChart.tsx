import { useId } from "react";
import { useContainerWidth } from "./BarChart";

export interface RatePoint {
  label: string;
  /** Basis points (10000 = 100%), or null when there is nothing to rate; null points leave a gap in the line. */
  value: number | null;
  /** Drawn as a hollow marker and named in the description. */
  lowVolume?: boolean;
  /** Tooltip and description text for this point, e.g. counts behind the rate. */
  detail: string;
}

const FULL = 10000;

/**
 * Hand-written SVG line chart for a daily rate on a fixed 0–100% scale, with an optional dashed baseline. Days without
 * a value break the line instead of being drawn as zero; low-volume days get a hollow marker. Every point carries a
 * text tooltip and the whole series is spelled out in the accessible description.
 */
export function RateChart({
  title,
  points,
  baseline,
  formatValue,
  baselineLabel = "Baseline",
  height = 240,
}: {
  title: string;
  points: RatePoint[];
  baseline: number | null;
  formatValue: (bps: number | null) => string;
  baselineLabel?: string;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const left = 48;
  const right = 12;
  const top = 12;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const slot = points.length === 0 ? plotWidth : plotWidth / points.length;
  const x = (i: number) => left + slot * i + slot / 2;
  const y = (bps: number) => top + plotHeight - (Math.min(Math.max(bps, 0), FULL) / FULL) * plotHeight;
  const labelEvery = Math.max(1, Math.ceil(points.length / 14));

  // Consecutive valued points form one segment; a null value ends it.
  const segments: { i: number; v: number }[][] = [];
  let current: { i: number; v: number }[] = [];
  points.forEach((p, i) => {
    if (p.value === null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push({ i, v: p.value });
    }
  });
  if (current.length) segments.push(current);

  const baselineText = baseline === null ? `${baselineLabel}: not available.` : `${baselineLabel}: ${formatValue(baseline)}.`;
  const description = `${baselineText} ${points.map((p) => `${p.label}: ${p.value === null ? "no completed attempts" : formatValue(p.value)}${p.lowVolume ? " (low volume)" : ""}, ${p.detail}`).join("; ")}`;

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart rate-chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {[0, 2500, 5000, 7500, FULL].map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {`${t / 100}%`}
            </text>
          </g>
        ))}
        {baseline !== null ? (
          <g className="chart-baseline">
            <title>{baselineText}</title>
            <line x1={left} x2={width - right} y1={y(baseline)} y2={y(baseline)} />
          </g>
        ) : null}
        {segments.map((seg) => (
          <polyline key={seg[0]!.i} className="chart-line" points={seg.map((p) => `${x(p.i)},${y(p.v)}`).join(" ")} />
        ))}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`} className={`chart-point${p.lowVolume ? " chart-point-low" : ""}${p.value === null ? " chart-point-empty" : ""}`}>
            <title>{`${p.label}: ${p.value === null ? "no completed attempts" : formatValue(p.value)}${p.lowVolume ? " · low volume" : ""} · ${p.detail}`}</title>
            {p.value !== null ? <circle cx={x(i)} cy={y(p.value)} r={p.lowVolume ? 4.5 : 3.5} /> : null}
            <rect className="chart-hit" x={x(i) - slot / 2} y={top} width={slot} height={plotHeight} />
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
