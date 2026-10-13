import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { formatRate } from "../lib/format";
import { LineChart, type LineChartPoint } from "./LineChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

const SERIES: LineChartPoint[] = [
  { label: "Oct 1", value: 9000, detail: "Oct 1: 90.0%" },
  { label: "Oct 2", value: 8000, detail: "Oct 2: 80.0%" },
  { label: "Oct 3", value: null, detail: "Oct 3: no completed attempts" },
  { label: "Oct 4", value: 9500, lowVolume: true, detail: "Oct 4: 95.0% (low volume)" },
];

describe("LineChart", () => {
  it("breaks the line at a null value instead of drawing zero", () => {
    const el = mount(<LineChart title="Rate" series={SERIES} formatValue={formatRate} minValue={6000} maxValue={10000} />);
    const paths = el.querySelectorAll("path.chart-line");
    expect(paths.length).toBe(2);
    expect(paths[0]?.getAttribute("d")?.match(/[ML]/g)?.length).toBe(2);
    expect(paths[1]?.getAttribute("d")?.startsWith("M")).toBe(true);
    expect(el.querySelectorAll(".chart-point-dot").length).toBe(3);
  });

  it("marks low-volume points, gives every point a tooltip and describes the series", () => {
    const el = mount(<LineChart title="Rate" series={SERIES} reference={9100} referenceLabel="Baseline 91.0%" formatValue={formatRate} minValue={6000} maxValue={10000} />);
    const points = el.querySelectorAll(".chart-point");
    expect(points[3]?.classList.contains("chart-point-low")).toBe(true);
    expect(Array.from(points).map((p) => p.querySelector("title")?.textContent)).toEqual(SERIES.map((p) => p.detail));
    expect(el.querySelector(".chart-reference title")?.textContent).toBe("Baseline 91.0%");
    expect(el.querySelector("desc")?.textContent).toBe(SERIES.map((p) => p.detail).join("; "));
    expect(el.querySelector(".chart-tick")?.textContent).toBe("60.0%");
  });

  it("draws no reference line when there is no baseline", () => {
    const el = mount(<LineChart title="Rate" series={SERIES} reference={null} formatValue={formatRate} minValue={0} maxValue={10000} />);
    expect(el.querySelector(".chart-reference")).toBeNull();
  });
});
