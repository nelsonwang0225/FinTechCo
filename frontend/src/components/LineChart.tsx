import { useId } from "react";
import { useContainerWidth } from "./BarChart";

export interface LineChartPoint {
  label: string;
  /** null leaves a gap: nothing to plot on that day, never drawn as zero. */
  value: number | null;
  /** Marked with a hollow point and called out in the description. */
  lowVolume?: boolean;
  /** Hover text for the point, e.g. counts behind the value. */
  detail: string;
}

/**
 * Hand-written SVG line chart for one rate series with an optional flat reference line. Null values break the line,
 * low-volume points are hollow, and every point carries a text tooltip. The caller formats values and supplies the
 * accessible description; a data table next to the chart remains the keyboard and touch path to the counts.
 */
export function LineChart({
  title,
  series,
  reference,
  referenceLabel,
  formatValue,
  minValue,
  maxValue,
  height = 240,
}: {
  title: string;
  series: LineChartPoint[];
  reference?: number | null;
  referenceLabel?: string;
  formatValue: (value: number) => string;
  minValue: number;
  maxValue: number;
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
  const span = Math.max(1, maxValue - minValue);
  const slot = series.length === 0 ? plotWidth : plotWidth / series.length;
  const xAt = (i: number) => left + i * slot + slot / 2;
  const yAt = (v: number) => top + plotHeight - ((Math.min(Math.max(v, minValue), maxValue) - minValue) / span) * plotHeight;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(minValue + span * f));
  const labelEvery = Math.max(1, Math.ceil(series.length / 14));

  // Consecutive non-null points form one segment; a null ends it.
  const segments: string[] = [];
  let current: string[] = [];
  series.forEach((p, i) => {
    if (p.value === null) {
      if (current.length) segments.push(current.join(" "));
      current = [];
    } else {
      current.push(`${current.length ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)}`);
    }
  });
  if (current.length) segments.push(current.join(" "));

  const description = series.length === 0 ? "No days in range." : series.map((p) => p.detail).join("; ");

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart line-chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {ticks.map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={yAt(t)} y2={yAt(t)} />
            <text x={left - 8} y={yAt(t) + 4} textAnchor="end" className="chart-tick">
              {formatValue(t)}
            </text>
          </g>
        ))}
        {reference !== undefined && reference !== null ? (
          <g className="chart-reference">
            <title>{referenceLabel ?? formatValue(reference)}</title>
            <line x1={left} x2={width - right} y1={yAt(reference)} y2={yAt(reference)} />
          </g>
        ) : null}
        {segments.map((d, i) => (
          <path key={i} className="chart-line" d={d} />
        ))}
        {series.map((p, i) => (
          <g key={`${p.label}-${i}`} className={p.lowVolume ? "chart-point chart-point-low" : "chart-point"} data-gap={p.value === null || undefined}>
            <title>{p.detail}</title>
            {p.value !== null ? (
              <>
                <circle className="chart-point-hit" cx={xAt(i)} cy={yAt(p.value)} r={10} />
                <circle className="chart-point-dot" cx={xAt(i)} cy={yAt(p.value)} r={p.lowVolume ? 4.5 : 3.5} />
              </>
            ) : (
              <rect className="chart-point-hit" x={xAt(i) - slot / 2} y={top} width={slot} height={plotHeight} />
            )}
            {i % labelEvery === 0 ? (
              <text x={xAt(i)} y={height - 8} textAnchor="middle" className="chart-label">
                {p.label}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
    </div>
  );
}
