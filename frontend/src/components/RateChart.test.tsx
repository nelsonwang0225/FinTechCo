import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { formatRate } from "../lib/format";
import { RateChart, type RatePoint } from "./RateChart";

let cleanup: (() => void) | null = null;

afterEach(() => {
  cleanup?.();
  cleanup = null;
});

async function render(points: RatePoint[], baselineBp: number | null): Promise<HTMLElement> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<RateChart title="Daily success rate" points={points} baselineBp={baselineBp} baselineLabel="Baseline" formatRate={formatRate} />);
  });
  cleanup = () => {
    act(() => root.unmount());
    container.remove();
  };
  return container;
}

const POINTS: RatePoint[] = [
  { label: "Sep 29", rateBp: 9500, lowVolume: false, detail: "95.0% (19 of 20)" },
  { label: "Sep 30", rateBp: 9000, lowVolume: false, detail: "90.0% (18 of 20)" },
  { label: "Oct 1", rateBp: null, lowVolume: false, detail: "no completed attempts, 2 pending" },
  { label: "Oct 2", rateBp: 6000, lowVolume: true, detail: "60.0% (3 of 5), low volume" },
  { label: "Oct 3", rateBp: 8000, lowVolume: false, detail: "80.0% (16 of 20)" },
];

describe("RateChart", () => {
  it("breaks the line on a day without a rate instead of drawing zero", async () => {
    const el = await render(POINTS, 9100);
    const lines = el.querySelectorAll("polyline.chart-line");
    expect(lines.length).toBe(2);
    expect(lines[0]?.getAttribute("points")?.split(" ").length).toBe(2);
    expect(lines[1]?.getAttribute("points")?.split(" ").length).toBe(2);
    expect(el.querySelectorAll("circle.chart-point").length).toBe(4);
  });

  it("marks low-volume days, draws the baseline and gives every day a text tooltip", async () => {
    const el = await render(POINTS, 9100);
    expect(el.querySelectorAll("circle.chart-point-low").length).toBe(1);
    expect(el.querySelector(".chart-baseline title")?.textContent).toBe("Baseline: 91.0%");
    const tips = Array.from(el.querySelectorAll(".chart-day > title")).map((t) => t.textContent);
    expect(tips).toEqual(POINTS.map((p) => `${p.label}: ${p.detail}`));
    const desc = el.querySelector("svg > desc")?.textContent ?? "";
    expect(desc).toContain("Baseline: 91.0%.");
    expect(desc).toContain("Oct 1: no completed attempts, 2 pending");
  });

  it("puts gridlines on whole 10-point steps, or 20-point steps when the range is wide", async () => {
    const ticks = (el: HTMLElement) => Array.from(el.querySelectorAll(".chart-tick")).map((t) => t.textContent);
    let el = await render(POINTS, 9100);
    expect(ticks(el)).toEqual(["50.0%", "60.0%", "70.0%", "80.0%", "90.0%", "100.0%"]);
    cleanup?.();
    el = await render([{ label: "Oct 1", rateBp: 4387, lowVolume: false, detail: "43.9%" }], 9087);
    expect(ticks(el)).toEqual(["20.0%", "40.0%", "60.0%", "80.0%", "100.0%"]);
  });

  it("renders with no rates and no baseline", async () => {
    const el = await render([{ label: "Aug 1", rateBp: null, lowVolume: false, detail: "no completed attempts" }], null);
    expect(el.querySelectorAll("polyline").length).toBe(0);
    expect(el.querySelector(".chart-baseline")).toBeNull();
    expect(el.querySelector("svg > desc")?.textContent).toContain("No baseline.");
  });
});
