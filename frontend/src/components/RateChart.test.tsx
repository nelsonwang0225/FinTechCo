import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { formatRateBps } from "../lib/format";
import { RateChart, type RatePoint } from "./RateChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

const point = (label: string, rateBps: number | null, lowVolume = false): RatePoint => ({ label, rateBps, lowVolume, detail: `${label} counts` });

describe("RateChart", () => {
  it("breaks the line at days without a rate instead of drawing zero", () => {
    const points = [point("Sep 29", 9300), point("Sep 30", 9100), point("Oct 1", null), point("Oct 2", 6000), point("Oct 3", null), point("Oct 4", 9000, true)];
    const el = mount(<RateChart title="Daily success rate" points={points} baselineBps={9080} baselineLabel="Baseline" formatRate={formatRateBps} />);
    const lines = Array.from(el.querySelectorAll("path.chart-line")).map((p) => p.getAttribute("d") ?? "");
    expect(lines.length).toBe(3);
    expect(lines.map((d) => (d.match(/[ML]/g) ?? []).length)).toEqual([2, 1, 1]);
    expect(el.querySelectorAll(".chart-gap").length).toBe(2);
    expect(el.querySelectorAll(".chart-point").length).toBe(4);
    expect(el.querySelectorAll(".chart-point-low").length).toBe(1);
  });

  it("describes every point, the gaps, the low-volume days and the baseline in text", () => {
    const el = mount(<RateChart title="Daily success rate" points={[point("Oct 1", 5714), point("Oct 2", null), point("Oct 3", 6250, true)]} baselineBps={9127} baselineLabel="Baseline, Aug 30 – Sep 28" formatRate={formatRateBps} />);
    const svg = el.querySelector("svg[role=img]")!;
    expect(svg.querySelector("title")?.textContent).toBe("Daily success rate");
    const desc = svg.querySelector("desc")?.textContent ?? "";
    expect(desc).toContain("Baseline, Aug 30 – Sep 28: 91.3%.");
    expect(desc).toContain("Oct 1: 57.1% (Oct 1 counts)");
    expect(desc).toContain("Oct 2: no completed attempts (Oct 2 counts)");
    expect(desc).toContain("Oct 3: 62.5%, low volume (Oct 3 counts)");
    expect(svg.querySelector(".chart-baseline title")?.textContent).toBe("Baseline, Aug 30 – Sep 28: 91.3%");
    expect(svg.querySelector("a")).toBeNull();
  });

  it("draws no baseline when there is none", () => {
    const el = mount(<RateChart title="Daily success rate" points={[point("Oct 1", 10000)]} baselineBps={null} baselineLabel="Baseline" formatRate={formatRateBps} />);
    expect(el.querySelector(".chart-baseline")).toBeNull();
    expect(el.querySelector("desc")?.textContent).toContain("No baseline.");
  });
});
