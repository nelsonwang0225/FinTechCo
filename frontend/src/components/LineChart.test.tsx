import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { formatRateBp } from "../lib/format";
import { LineChart, type LineChartPoint } from "./LineChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

const tick = (v: number) => `${v / 100}%`;

const SERIES: LineChartPoint[] = [
  { label: "Sep 29", value: 10000, tooltip: "Sep 29: 100.0% (19 of 19)" },
  { label: "Sep 30", value: 8667, tooltip: "Sep 30: 86.7% (26 of 30)" },
  { label: "Oct 1", value: 4464, tooltip: "Oct 1: 44.6% (25 of 56)" },
  { label: "Oct 2", value: null, tooltip: "Oct 2: no completed attempts" },
  { label: "Oct 3", value: 9000, tooltip: "Oct 3: 90.0% (18 of 20)" },
  { label: "Oct 4", value: 7647, tooltip: "Oct 4: 76.5% (13 of 17)" },
  { label: "Oct 5", value: 10000, lowVolume: true, tooltip: "Oct 5: 100.0% (5 of 5)" },
];

describe("LineChart", () => {
  it("draws one marker per non-null point, breaks the line around a gap and never marks a null", () => {
    const el = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={tick} />);
    const svg = el.querySelector("svg[role=img]");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("aria-labelledby")).toBeTruthy();
    expect(svg?.getAttribute("aria-describedby")).toBeTruthy();
    expect(svg?.querySelector("title")?.textContent).toBe("Success rate by day");
    expect(el.querySelectorAll(".chart-point").length).toBe(6);
    expect(el.querySelectorAll(".chart-point-group").length).toBe(6);
    const paths = Array.from(el.querySelectorAll("path.chart-line"));
    expect(paths.length).toBe(2);
    expect(paths.map((p) => (p.getAttribute("d") ?? "").match(/M/g)?.length ?? 0)).toEqual([1, 1]);
    expect(paths[0]?.getAttribute("d")?.split("L").length).toBe(3);
    expect(paths[1]?.getAttribute("d")?.split("L").length).toBe(3);
    const groups = Array.from(el.querySelectorAll(".chart-point-group"));
    expect(groups.map((g) => g.querySelector("title")?.textContent)).not.toContain("Oct 2: no completed attempts");
    expect(el.querySelectorAll("a").length).toBe(0);
  });

  it("describes every point for assistive technology, with gaps named", () => {
    const el = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={tick} />);
    const desc = el.querySelector("svg desc")?.textContent ?? "";
    expect(desc).toContain("Sep 30: Sep 30: 86.7% (26 of 30)");
    expect(desc).toContain("Oct 2: no completed attempts");
    expect(desc).toContain("Oct 5: Oct 5: 100.0% (5 of 5)");
  });

  it("uses the given tooltip text on each marker", () => {
    const el = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={formatRateBp} />);
    const titles = Array.from(el.querySelectorAll(".chart-point-group title")).map((t) => t.textContent);
    expect(titles).toEqual([
      "Sep 29: 100.0% (19 of 19)",
      "Sep 30: 86.7% (26 of 30)",
      "Oct 1: 44.6% (25 of 56)",
      "Oct 3: 90.0% (18 of 20)",
      "Oct 4: 76.5% (13 of 17)",
      "Oct 5: 100.0% (5 of 5)",
    ]);
  });

  it("shows the five fixed ticks through formatTick", () => {
    const el = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={formatRateBp} />);
    expect(el.querySelectorAll(".chart-grid").length).toBe(5);
    expect(Array.from(el.querySelectorAll(".chart-tick")).map((t) => t.textContent)).toEqual(["0.0%", "25.0%", "50.0%", "75.0%", "100.0%"]);
  });

  it("marks low-volume points and renders the legend only when one is present", () => {
    const withLow = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={tick} lowVolumeLegend="Fewer than 10 completed attempts" />);
    const low = withLow.querySelectorAll("svg[role=img] .chart-point-low");
    expect(low.length).toBe(1);
    expect(low[0]?.classList.contains("chart-point")).toBe(true);
    expect(withLow.querySelector(".chart-legend")?.textContent).toBe("Fewer than 10 completed attempts");
    expect(withLow.querySelector(".chart-legend .chart-point-low")).not.toBeNull();

    const noLow = mount(<LineChart title="Success rate by day" series={SERIES.filter((p) => !p.lowVolume)} formatTick={tick} lowVolumeLegend="Fewer than 10 completed attempts" />);
    expect(noLow.querySelectorAll(".chart-point-low").length).toBe(0);
    expect(noLow.querySelector(".chart-legend")).toBeNull();

    const noLegend = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={tick} />);
    expect(noLegend.querySelectorAll(".chart-point-low").length).toBe(1);
    expect(noLegend.querySelector(".chart-legend")).toBeNull();
  });

  it("draws the baseline with its label when given and nothing when null", () => {
    const el = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={tick} baseline={9079} baselineLabel="Baseline 90.8%" />);
    const line = el.querySelector("line.chart-baseline");
    expect(line).not.toBeNull();
    expect(el.querySelector(".chart-baseline-label")?.textContent).toBe("Baseline 90.8%");
    const gridTop = el.querySelectorAll(".chart-grid line")[4];
    const gridNext = el.querySelectorAll(".chart-grid line")[3];
    const y = Number(line?.getAttribute("y1"));
    expect(y).toBeGreaterThan(Number(gridTop?.getAttribute("y1")));
    expect(y).toBeLessThan(Number(gridNext?.getAttribute("y1")));

    const none = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={tick} baseline={null} baselineLabel="Baseline" />);
    expect(none.querySelector(".chart-baseline")).toBeNull();
    expect(none.querySelector(".chart-baseline-label")).toBeNull();
    const omitted = mount(<LineChart title="Success rate by day" series={SERIES} formatTick={tick} />);
    expect(omitted.querySelector(".chart-baseline")).toBeNull();
  });

  it("thins x labels on long series and keeps the default height", () => {
    const long: LineChartPoint[] = Array.from({ length: 30 }, (_, i) => ({ label: `D${i + 1}`, value: 9000, tooltip: `D${i + 1}: 90.0%` }));
    const el = mount(<LineChart title="Success rate by day" series={long} formatTick={tick} />);
    expect(el.querySelectorAll(".chart-label").length).toBe(10);
    expect(el.querySelector("svg")?.getAttribute("viewBox")).toBe("0 0 720 240");
    expect(el.querySelectorAll("path.chart-line").length).toBe(1);
  });

  it("handles an empty series", () => {
    const el = mount(<LineChart title="Success rate by day" series={[]} formatTick={tick} />);
    expect(el.querySelector("svg desc")?.textContent).toBe("No values.");
    expect(el.querySelectorAll(".chart-point").length).toBe(0);
    expect(el.querySelectorAll("path.chart-line").length).toBe(0);
  });
});
