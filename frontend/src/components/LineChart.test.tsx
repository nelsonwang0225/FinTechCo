import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { LineChart, type LineChartPoint } from "./LineChart";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

async function render(points: LineChartPoint[], reference: number | null = 9000): Promise<HTMLDivElement> {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root!.render(<LineChart title="Daily rate" points={points} reference={reference} referenceLabel="Baseline" formatValue={(v) => `${v / 100}%`} domainMax={10_000} />);
  });
  return container;
}

const POINTS: LineChartPoint[] = [
  { label: "Oct 1", value: 9500, detail: "Oct 1: 95%" },
  { label: "Oct 2", value: 9100, detail: "Oct 2: 91%" },
  { label: "Oct 3", value: null, detail: "Oct 3: no completed attempts" },
  { label: "Oct 4", value: 6000, lowVolume: true, detail: "Oct 4: 60% · low volume" },
];

describe("LineChart", () => {
  it("breaks the line at a missing value and marks low-volume points with a different shape", async () => {
    const el = await render(POINTS);
    const segments = el.querySelectorAll(".chart-line");
    expect(segments.length).toBe(2);
    expect(segments[0]?.getAttribute("d")).toMatch(/^M[\d.]+,[\d.]+ L[\d.]+,[\d.]+$/);
    expect(segments[1]?.getAttribute("d")).toMatch(/^M[\d.]+,[\d.]+$/);
    expect(el.querySelectorAll(".chart-point").length).toBe(3);
    expect(el.querySelectorAll(".chart-point-low").length).toBe(1);
    expect(el.querySelector(".chart-gap[data-day='Oct 3']")).not.toBeNull();
    expect(el.querySelector(".chart-reference")).not.toBeNull();
  });

  it("describes every point and the reference for assistive technology", async () => {
    const el = await render(POINTS);
    const svg = el.querySelector("svg");
    expect(svg?.getAttribute("role")).toBe("img");
    expect(svg?.getAttribute("tabindex")).toBe("0");
    expect(el.querySelector("title")?.textContent).toContain("arrow keys");
    expect(el.querySelector("desc")?.textContent).toBe("Baseline: 90%. Oct 1: 95%; Oct 2: 91%; Oct 3: no completed attempts; Oct 4: 60% · low volume");
  });

  it("reads each day with the arrow keys and announces it", async () => {
    const el = await render(POINTS);
    const svg = el.querySelector("svg")!;
    const press = async (key: string) => act(async () => svg.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true })));
    await press("ArrowRight");
    expect(el.querySelector(".chart-tooltip")?.textContent).toBe("Oct 1: 95%");
    expect(el.querySelector("[aria-live]")?.textContent).toBe("Oct 1: 95%");
    await press("End");
    expect(el.querySelector(".chart-tooltip")?.textContent).toBe("Oct 4: 60% · low volume");
    await press("ArrowLeft");
    expect(el.querySelector(".chart-tooltip")?.textContent).toBe("Oct 3: no completed attempts");
    await press("Escape");
    expect(el.querySelector(".chart-tooltip")).toBeNull();
  });

  it("draws without a reference line or any values", async () => {
    const el = await render([{ label: "Oct 1", value: null, detail: "Oct 1: no completed attempts" }], null);
    expect(el.querySelector(".chart-reference")).toBeNull();
    expect(el.querySelectorAll(".chart-line").length).toBe(0);
    expect(el.querySelector("desc")?.textContent).toBe("Oct 1: no completed attempts");
  });
});
