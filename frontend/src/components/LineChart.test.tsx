import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { formatRate } from "../lib/format";
import { LineChart, segments } from "./LineChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

const POINTS = [
  { label: "Oct 1", value: 6885, detail: "68.9% · 84 succeeded, 38 failed, 0 pending" },
  { label: "Oct 2", value: 8182, detail: "81.8% · 81 succeeded, 18 failed, 0 pending" },
  { label: "Oct 3", value: null, detail: "No completed attempts" },
  { label: "Oct 4", value: 7647, lowVolume: true, detail: "76.5% · 13 succeeded, 4 failed, 0 pending" },
];

describe("LineChart", () => {
  it("splits the series at gaps instead of drawing through them", () => {
    expect(segments(POINTS).map((run) => run.map((p) => p.index))).toEqual([[0, 1], [3]]);
    expect(segments([{ value: null }, { value: null }])).toEqual([]);
  });

  it("draws gaps, low-volume markers, a baseline and counts in tooltips and the description", () => {
    const el = mount(<LineChart title="Daily success rate" points={POINTS} reference={9087} referenceLabel="Baseline" min={4000} max={10000} formatValue={formatRate} />);
    const svg = el.querySelector("svg[role=img]");
    expect(svg?.querySelector("title")?.textContent).toBe("Daily success rate");
    expect(el.querySelectorAll("path.chart-line").length).toBe(2);
    expect(el.querySelectorAll(".chart-point circle").length).toBe(3);
    expect(el.querySelectorAll(".chart-point-gap circle").length).toBe(0);
    expect(el.querySelectorAll(".chart-point-low").length).toBe(1);
    expect(el.querySelector(".chart-reference title")?.textContent).toBe("Baseline: 90.9%");
    const tooltips = Array.from(el.querySelectorAll(".chart-point > title")).map((t) => t.textContent);
    expect(tooltips[0]).toBe("Oct 1: 68.9% · 84 succeeded, 38 failed, 0 pending");
    expect(tooltips[2]).toBe("Oct 3: No completed attempts");
    expect(tooltips[3]).toContain("(low volume)");
    const desc = svg?.querySelector("desc")?.textContent ?? "";
    expect(desc).toContain("Baseline: 90.9%.");
    expect(desc).toContain("Oct 3: No completed attempts.");
    expect(Array.from(el.querySelectorAll(".chart-tick")).map((t) => t.textContent)).toEqual(["40.0%", "55.0%", "70.0%", "85.0%", "100.0%"]);
    expect(el.querySelectorAll("a").length).toBe(0);
  });

  it("renders without a reference line or any plotted point", () => {
    const el = mount(<LineChart title="Empty" points={[{ label: "Oct 1", value: null, detail: "No completed attempts" }]} min={0} max={10000} formatValue={formatRate} />);
    expect(el.querySelector(".chart-reference")).toBeNull();
    expect(el.querySelectorAll("path.chart-line").length).toBe(0);
  });
});
