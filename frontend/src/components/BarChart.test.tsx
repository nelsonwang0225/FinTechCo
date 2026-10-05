import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { formatCents } from "../lib/format";
import { BarChart, niceCeiling } from "./BarChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

describe("BarChart", () => {
  it("rounds maxima to readable gridline values", () => {
    expect(niceCeiling(0)).toBe(1);
    expect(niceCeiling(4155882)).toBe(5000000);
    expect(niceCeiling(1200)).toBe(2000);
    expect(niceCeiling(70)).toBe(100);
    expect(niceCeiling(1000)).toBe(1000);
  });

  it("draws one bar per point with a text tooltip, an accessible title and no links", () => {
    const series = [
      { label: "Sep 29", value: 2670484 },
      { label: "Sep 30", value: 4155882 },
      { label: "Oct 1", value: 0 },
    ];
    const el = mount(<BarChart title="Collected by day" series={series} formatValue={(v) => formatCents(v)} formatTick={(v) => formatCents(v).replace(/\.00$/, "")} />);
    const svg = el.querySelector("svg[role=img]");
    expect(svg).not.toBeNull();
    expect(svg?.querySelector("title")?.textContent).toBe("Collected by day");
    expect(svg?.querySelector("desc")?.textContent).toContain("Sep 30: $41,558.82");
    const bars = el.querySelectorAll(".chart-bar");
    expect(bars.length).toBe(3);
    expect(bars[1]?.querySelector("title")?.textContent).toBe("Sep 30: $41,558.82");
    expect(bars[2]?.querySelector("rect")?.getAttribute("height")).toBe("0");
    expect(el.querySelectorAll(".chart-grid").length).toBe(5);
    expect(Array.from(el.querySelectorAll(".chart-tick")).map((t) => t.textContent)).toEqual(["$0", "$12,500", "$25,000", "$37,500", "$50,000"]);
    expect(el.querySelectorAll("a").length).toBe(0);
  });

  it("supports a horizontal layout", () => {
    const el = mount(<BarChart title="By location" series={[{ label: "Fulton", value: 10 }]} formatValue={(v) => String(v)} horizontal />);
    expect(el.querySelectorAll(".chart-bar rect").length).toBe(1);
    expect(el.querySelector(".chart-label")?.textContent).toBe("Fulton");
  });
});
