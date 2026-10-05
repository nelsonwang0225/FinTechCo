import { useEffect, useId, useRef, useState, type RefObject } from "react";

export interface BarChartPoint {
  label: string;
  value: number;
}

/** Round a maximum up to a 1, 2 or 5 multiple of a power of ten so gridlines land on readable values. */
export function niceCeiling(max: number): number {
  if (max <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const unit = max / magnitude;
  const factor = unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10;
  return factor * magnitude;
}

const DEFAULT_WIDTH = 720;

/** The rendered width of the chart's container, so the SVG draws at 1:1 and labels keep their type size. */
function useContainerWidth(): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const w = Math.round(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/**
 * Generic hand-written SVG bar chart: one series of numbers with labels, gridlines, a text tooltip per bar and an
 * accessible title and description. It never navigates anywhere; the caller formats values.
 */
export function BarChart({
  title,
  series,
  formatValue,
  formatTick = formatValue,
  horizontal = false,
  height = 240,
}: {
  title: string;
  series: BarChartPoint[];
  /** Formats bar values for tooltips and the description. */
  formatValue: (value: number) => string;
  /** Formats gridline labels; defaults to formatValue. */
  formatTick?: (value: number) => string;
  horizontal?: boolean;
  height?: number;
}) {
  const id = useId();
  const [wrapRef, measured] = useContainerWidth();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const max = niceCeiling(Math.max(0, ...series.map((p) => p.value)));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));
  const description = series.length === 0 ? "No values." : series.map((p) => `${p.label}: ${formatValue(p.value)}`).join("; ");

  if (horizontal) {
    const rowHeight = 28;
    const labelWidth = 96;
    const width = measured;
    const chartHeight = Math.max(rowHeight, series.length * rowHeight) + 24;
    const plotWidth = width - labelWidth - 16;
    return (
      <div className="chart-wrap" ref={wrapRef}>
      <svg className="chart" viewBox={`0 0 ${width} ${chartHeight}`} style={{ height: chartHeight }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
        <title id={titleId}>{title}</title>
        <desc id={descId}>{description}</desc>
        {ticks.map((t) => {
          const x = labelWidth + (max === 0 ? 0 : (t / max) * plotWidth);
          return (
            <g key={t} className="chart-grid">
              <line x1={x} x2={x} y1={0} y2={chartHeight - 20} />
              <text x={x} y={chartHeight - 6} textAnchor="middle" className="chart-tick">
                {formatTick(t)}
              </text>
            </g>
          );
        })}
        {series.map((p, i) => {
          const barWidth = max === 0 ? 0 : (p.value / max) * plotWidth;
          const y = i * rowHeight + 6;
          return (
            <g key={`${p.label}-${i}`} className="chart-bar">
              <title>{`${p.label}: ${formatValue(p.value)}`}</title>
              <text x={labelWidth - 8} y={y + 14} textAnchor="end" className="chart-label">
                {p.label}
              </text>
              <rect x={labelWidth} y={y} width={Math.max(barWidth, 0)} height={rowHeight - 12} rx={2} />
            </g>
          );
        })}
      </svg>
      </div>
    );
  }

  const width = measured;
  const left = 64;
  const bottom = 28;
  const top = 8;
  const plotHeight = height - top - bottom;
  const plotWidth = width - left - 8;
  const slot = series.length === 0 ? plotWidth : plotWidth / series.length;
  const barWidth = Math.max(4, Math.min(72, slot * 0.6));
  const labelEvery = Math.max(1, Math.ceil(series.length / 14));
  return (
    <div className="chart-wrap" ref={wrapRef}>
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} style={{ height }} role="img" aria-labelledby={titleId} aria-describedby={descId} focusable="false">
      <title id={titleId}>{title}</title>
      <desc id={descId}>{description}</desc>
      {ticks.map((t) => {
        const y = top + plotHeight - (max === 0 ? 0 : (t / max) * plotHeight);
        return (
          <g key={t} className="chart-grid">
            <line x1={left} x2={width - 8} y1={y} y2={y} />
            <text x={left - 8} y={y + 4} textAnchor="end" className="chart-tick">
              {formatTick(t)}
            </text>
          </g>
        );
      })}
      {series.map((p, i) => {
        const barHeight = max === 0 ? 0 : (p.value / max) * plotHeight;
        const x = left + i * slot + (slot - barWidth) / 2;
        const y = top + plotHeight - barHeight;
        return (
          <g key={`${p.label}-${i}`} className="chart-bar">
            <title>{`${p.label}: ${formatValue(p.value)}`}</title>
            <rect x={x} y={y} width={barWidth} height={Math.max(barHeight, 0)} rx={2} />
            {i % labelEvery === 0 ? (
              <text x={x + barWidth / 2} y={height - 8} textAnchor="middle" className="chart-label">
                {p.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
    </div>
  );
}
