import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { RateChart } from "./RateChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

const POINTS = [
  { label: "Oct 1", rateBp: 4464, lowVolume: false, detail: "25 succeeded · 31 failed · 0 pending" },
  { label: "Oct 2", rateBp: 7179, lowVolume: false, detail: "28 succeeded · 11 failed · 0 pending" },
  { label: "Oct 3", rateBp: null, lowVolume: true, detail: "0 succeeded · 0 failed · 2 pending" },
  { label: "Oct 4", rateBp: 6000, lowVolume: true, detail: "3 succeeded · 2 failed · 0 pending" },
  { label: "Oct 5", rateBp: 9000, lowVolume: false, detail: "18 succeeded · 2 failed · 0 pending" },
];

describe("RateChart", () => {
  it("breaks the line at days with no completed attempts and never plots them", () => {
    const el = mount(<RateChart title="Daily success rate" points={POINTS} baselineBp={9087} baselineLabel="Baseline, Sep 1 – Sep 30, 2026" />);
    const lines = el.querySelectorAll("polyline.chart-line");
    expect(lines.length).toBe(2);
    expect(lines[0]?.getAttribute("points")?.split(" ").length).toBe(2);
    expect(lines[1]?.getAttribute("points")?.split(" ").length).toBe(2);
    const groups = el.querySelectorAll(".chart-point");
    expect(groups.length).toBe(5);
    expect(groups[2]?.classList.contains("chart-point-gap")).toBe(true);
    expect(groups[2]?.querySelector("circle")).toBeNull();
    expect(groups[2]?.querySelector("title")?.textContent).toBe("Oct 3 · No completed attempts · 0 succeeded · 0 failed · 2 pending");
  });

  it("marks low-volume days in shape and words, shows counts on hover and a dashed baseline", () => {
    const el = mount(<RateChart title="Daily success rate" points={POINTS} baselineBp={9087} baselineLabel="Baseline, Sep 1 – Sep 30, 2026" />);
    const low = el.querySelectorAll(".chart-point-low");
    expect(low.length).toBe(1);
    expect(low[0]?.querySelector("title")?.textContent).toBe("Oct 4 · 60.0% · low volume · 3 succeeded · 2 failed · 0 pending");
    expect(el.querySelectorAll(".chart-point")[0]?.querySelector("title")?.textContent).toBe("Oct 1 · 44.6% · 25 succeeded · 31 failed · 0 pending");
    expect(el.querySelector(".chart-baseline title")?.textContent).toBe("Baseline, Sep 1 – Sep 30, 2026: 90.9%");
    expect(Array.from(el.querySelectorAll(".chart-tick")).map((t) => t.textContent)).toEqual(["0%", "25%", "50%", "75%", "100%"]);
    const desc = el.querySelector("desc")?.textContent ?? "";
    expect(desc).toContain("Baseline, Sep 1 – Sep 30, 2026: 90.9%.");
    expect(desc).toContain("Oct 3: no completed attempts");
    expect(desc).toContain("Oct 4: 60.0%, low volume");
    expect(el.querySelectorAll("a").length).toBe(0);
  });

  it("omits the baseline when the baseline had no completed attempts", () => {
    const el = mount(<RateChart title="Daily success rate" points={POINTS} baselineBp={null} baselineLabel="Baseline" />);
    expect(el.querySelector(".chart-baseline")).toBeNull();
    expect(el.querySelector("desc")?.textContent).toContain("Baseline: no completed attempts.");
  });
});
