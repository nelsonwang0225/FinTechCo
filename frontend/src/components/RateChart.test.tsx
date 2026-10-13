import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { formatBps } from "../lib/format";
import { RateChart } from "./RateChart";

function mount(element: React.ReactNode): HTMLDivElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  act(() => createRoot(container).render(element));
  return container;
}

describe("RateChart", () => {
  const points = [
    { label: "Oct 1", value: 9000, detail: "90 succeeded, 10 failed" },
    { label: "Oct 2", value: 4500, detail: "45 succeeded, 55 failed" },
    { label: "Oct 3", value: null, detail: "0 succeeded, 0 failed" },
    { label: "Oct 4", value: 6000, lowVolume: true, detail: "3 succeeded, 2 failed" },
  ];

  it("breaks the line at days without a value instead of drawing zero", () => {
    const el = mount(<RateChart title="Daily success rate" points={points} baseline={9100} formatValue={formatBps} />);
    const lines = el.querySelectorAll(".chart-line");
    expect(lines.length).toBe(2);
    expect(lines[0]?.getAttribute("points")?.split(" ").length).toBe(2);
    expect(lines[1]?.getAttribute("points")?.split(" ").length).toBe(1);
    expect(el.querySelectorAll(".chart-point circle").length).toBe(3);
  });

  it("marks low-volume days, draws the baseline and carries counts in tooltips and the description", () => {
    const el = mount(<RateChart title="Daily success rate" points={points} baseline={9100} formatValue={formatBps} />);
    expect(el.querySelectorAll(".chart-point-low circle").length).toBe(1);
    expect(el.querySelector(".chart-baseline title")?.textContent).toBe("Baseline: 91.0%.");
    const tips = Array.from(el.querySelectorAll(".chart-point > title")).map((t) => t.textContent);
    expect(tips[1]).toBe("Oct 2: 45.0% · 45 succeeded, 55 failed");
    expect(tips[2]).toBe("Oct 3: no completed attempts · 0 succeeded, 0 failed");
    expect(tips[3]).toBe("Oct 4: 60.0% · low volume · 3 succeeded, 2 failed");
    const desc = el.querySelector("desc")?.textContent ?? "";
    expect(desc).toContain("Baseline: 91.0%.");
    expect(desc).toContain("Oct 4: 60.0% (low volume)");
    expect(Array.from(el.querySelectorAll(".chart-tick")).map((t) => t.textContent)).toEqual(["0%", "25%", "50%", "75%", "100%"]);
  });

  it("omits the baseline when there is none", () => {
    const el = mount(<RateChart title="Daily success rate" points={points} baseline={null} formatValue={formatBps} />);
    expect(el.querySelector(".chart-baseline")).toBeNull();
    expect(el.querySelector("desc")?.textContent).toContain("Baseline: not available.");
  });
});
