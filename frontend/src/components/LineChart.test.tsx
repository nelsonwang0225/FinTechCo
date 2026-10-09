import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { axisFloor, LineChart, segments } from "./LineChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

const pct = (bp: number) => `${bp / 100}%`;

describe("LineChart", () => {
  it("splits the series into runs at every gap", () => {
    const runs = segments([{ value: 1 }, { value: 2 }, { value: null }, { value: 3 }, { value: null }, { value: null }, { value: 4 }, { value: 5 }]);
    expect(runs.map((r) => r.map((p) => p.index))).toEqual([[0, 1], [3], [6, 7]]);
    expect(segments([{ value: null }])).toEqual([]);
  });

  it("starts the axis a whole step below the lowest value", () => {
    expect(axisFloor([7204, 9079], 10000, 1000)).toBe(6000);
    expect(axisFloor([9900], 10000, 1000)).toBe(9000);
    expect(axisFloor([], 10000, 1000)).toBe(0);
    expect(axisFloor([200], 10000, 1000)).toBe(0);
  });

  it("draws gaps, hollow low-volume points, a dashed reference and per-point detail", () => {
    const points = [
      { label: "Sep 29", value: 9494, detail: "94.9% · 94 succeeded, 5 failed, 0 pending" },
      { label: "Sep 30", value: null, detail: "no completed attempts · 0 pending" },
      { label: "Oct 1", value: 6885, detail: "68.9% · 62 succeeded, 28 failed, 0 pending" },
      { label: "Oct 2", value: 8182, lowVolume: true, detail: "81.8% · 9 succeeded, 2 failed, 1 pending" },
    ];
    const el = mount(
      <LineChart title="Success rate by day" points={points} reference={{ value: 9127, label: "Baseline 91.3%" }} formatTick={pct} max={10000} step={1000}
        seriesLabel="Daily success rate" lowVolumeLabel="Fewer than 20 completed attempts" gapLabel="No completed attempts" />,
    );
    const svg = el.querySelector("svg[role=img]");
    expect(svg?.querySelector("title")?.textContent).toBe("Success rate by day");
    const desc = svg?.querySelector("desc")?.textContent ?? "";
    expect(desc).toContain("Baseline 91.3%");
    expect(desc).toContain("Oct 2: 81.8% · 9 succeeded, 2 failed, 1 pending");
    expect(desc).toContain("Sep 30: no completed attempts");
    // Sep 29 stands alone before the gap, Oct 1–2 form one line: one polyline, never a line through the gap.
    const lines = el.querySelectorAll("polyline.chart-line");
    expect(lines.length).toBe(1);
    expect(lines[0]?.getAttribute("points")?.split(" ").length).toBe(2);
    expect(el.querySelectorAll(".chart-point .chart-dot").length).toBe(3);
    expect(el.querySelectorAll(".chart-point.low-volume .chart-dot").length).toBe(1);
    expect(el.querySelectorAll(".chart-point.chart-gap .chart-dot").length).toBe(0);
    expect(el.querySelector(".chart-point.low-volume title")?.textContent).toBe("Oct 2: 81.8% · 9 succeeded, 2 failed, 1 pending");
    expect(el.querySelector(".chart-reference line")).not.toBeNull();
    expect(Array.from(el.querySelectorAll(".chart-tick")).map((t) => t.textContent)).toEqual(["60%", "70%", "80%", "90%", "100%"]);
    expect(Array.from(el.querySelectorAll(".chart-legend li")).map((li) => li.textContent)).toEqual([
      "Daily success rate", "Baseline 91.3%", "Fewer than 20 completed attempts", "No completed attempts",
    ]);
    expect(el.querySelectorAll("a").length).toBe(0);
  });

  it("omits the reference line and legend entries it does not need", () => {
    const el = mount(
      <LineChart title="t" points={[{ label: "Oct 5", value: 10000, detail: "100%" }]} reference={null} formatTick={pct} max={10000} step={1000}
        seriesLabel="Daily success rate" lowVolumeLabel="low" gapLabel="gap" />,
    );
    expect(el.querySelector(".chart-reference")).toBeNull();
    expect(Array.from(el.querySelectorAll(".chart-legend li")).map((li) => li.textContent)).toEqual(["Daily success rate"]);
  });
});
