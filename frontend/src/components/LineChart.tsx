import { useId, useState, type KeyboardEvent, type MouseEvent } from "react";
import { niceCeiling, useContainerWidth } from "./BarChart";

export interface LineChartPoint {
  label: string;
  /** null leaves a gap: the line is not drawn through a point with no value. */
  value: number | null;
  /** Marked with a hollow point and said in words; still plotted. */
  lowVolume?: boolean;
  /** Full sentence for the tooltip and screen readers, e.g. "Oct 2: 65.0%, 40 succeeded, 21 failed". */
  detail: string;
}

/**
 * Hand-written SVG line chart for one daily series against a flat reference line (a baseline). Gaps for null values,
 * hollow markers for low-volume points, and a tooltip that follows the pointer or the arrow keys. Values share one
 * unit; the caller formats them.
 */
export function LineChart({
  title,
  points,
  reference,
  referenceLabel,
  formatValue,
  domainMax,
  height = 240,
}: {
  title: string;
  points: LineChartPoint[];
  reference: number | null;
  referenceLabel: string;
  formatValue: (value: number) => string;
  /** The top of the value axis, e.g. 10000 for a rate in basis points. */
  domainMax: number;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, width] = useContainerWidth();
  const [active, setActive] = useState<number | null>(null);
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;

  // The axis runs from a round value just below the lowest point (or the reference) up to domainMax, ticked on a 1-2-5 step.
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  const lowest = values.length === 0 && reference === null ? 0 : Math.min(domainMax, ...values, ...(reference === null ? [] : [reference]));
  const padded = Math.max(0, lowest - domainMax / 20);
  const tickStep = niceCeiling(Math.max(1, (domainMax - padded) / 4));
  const min = Math.max(0, Math.floor(padded / tickStep) * tickStep);
  const ticks: number[] = [];
  for (let t = min; t <= domainMax; t += tickStep) ticks.push(t);

  const left = 56;
  const right = 12;
  const top = 10;
  const bottom = 28;
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = height - top - bottom;
  const slot = points.length === 0 ? plotWidth : plotWidth / points.length;
  const x = (i: number) => left + i * slot + slot / 2;
  const y = (v: number) => top + plotHeight - ((v - min) / Math.max(1, domainMax - min)) * plotHeight;
  const labelEvery = Math.max(1, Math.ceil(points.length / 12));

  // One path segment per run of consecutive values, so a missing day leaves a visible gap.
  const segments: string[] = [];
  let current: string[] = [];
  points.forEach((p, i) => {
    if (p.value === null) {
      if (current.length) segments.push(current.join(" "));
      current = [];
      return;
    }
    current.push(`${current.length ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`);
  });
  if (current.length) segments.push(current.join(" "));

  const description =
    (reference === null ? "" : `${referenceLabel}: ${formatValue(reference)}. `) + (points.length === 0 ? "No days." : points.map((p) => p.detail).join("; "));

  function onMove(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const scale = rect.width > 0 ? width / rect.width : 1;
    const px = (event.clientX - rect.left) * scale;
    const i = Math.floor((px - left) / slot);
    setActive(i >= 0 && i < points.length ? i : null);
  }

  function onKey(event: KeyboardEvent<SVGSVGElement>) {
    if (points.length === 0) return;
    const last = points.length - 1;
    let next: number | null;
    if (event.key === "ArrowRight") next = active === null ? 0 : Math.min(last, active + 1);
    else if (event.key === "ArrowLeft") next = active === null ? last : Math.max(0, active - 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    else if (event.key === "Escape") next = null;
    else return;
    event.preventDefault();
    setActive(next);
  }

  const activePoint = active === null ? null : points[active];
  const tipLeft = active === null ? 0 : Math.min(Math.max(x(active), 80), width - 80);

  return (
    <div className="chart-wrap line-chart" ref={wrapRef}>
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        style={{ height }}
        role="img"
        aria-labelledby={titleId}
        aria-describedby={descId}
        tabIndex={0}
        onMouseMove={onMove}
        onMouseLeave={() => setActive(null)}
        onKeyDown={onKey}
        onBlur={() => setActive(null)}
      >
        <title id={titleId}>{`${title}. Use the left and right arrow keys to read each day.`}</title>
        <desc id={descId}>{description}</desc>
        {ticks.map((t) => (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
            <text x={left - 8} y={y(t) + 4} textAnchor="end" className="chart-tick">
              {formatValue(t)}
            </text>
          </g>
        ))}
        {reference !== null ? <line className="chart-reference" x1={left} x2={width - right} y1={y(reference)} y2={y(reference)} /> : null}
        {segments.map((d, i) => (
          <path key={i} className="chart-line" d={d} />
        ))}
        {active !== null ? <line className="chart-cursor" x1={x(active)} x2={x(active)} y1={top} y2={top + plotHeight} /> : null}
        {points.map((p, i) => (
          <g key={`${p.label}-${i}`}>
            {p.value !== null ? (
              <circle
                className={`chart-point${p.lowVolume ? " chart-point-low" : ""}${active === i ? " chart-point-active" : ""}`}
                cx={x(i)}
                cy={y(p.value)}
                r={active === i ? 5 : p.lowVolume ? 4 : 3}
                data-day={p.label}
              />
            ) : (
              <text className="chart-gap" x={x(i)} y={top + plotHeight - 4} textAnchor="middle" data-day={p.label}>
                ·
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
      {activePoint ? (
        <div className="chart-tooltip" style={{ left: tipLeft }} aria-hidden="true">
          {activePoint.detail}
        </div>
      ) : null}
      <p className="visually-hidden" aria-live="polite">
        {activePoint ? activePoint.detail : ""}
      </p>
    </div>
  );
}
