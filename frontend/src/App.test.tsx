import { StrictMode } from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(() => {
  if (root) {
    act(() => root?.unmount());
  }
  container?.remove();
  root = null;
  container = null;
});

describe("App shell", () => {
  it("renders the navigation and the demo indicator", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(
        <StrictMode>
          <MemoryRouter initialEntries={["/overview"]}>
            <App />
          </MemoryRouter>
        </StrictMode>,
      );
    });
    const text = container.textContent ?? "";
    for (const label of ["Overview", "Payments", "Payouts", "Customers", "Disputes", "Reports", "Settings"]) {
      expect(text).toContain(label);
    }
    expect(text).toContain("Demo environment · Synthetic data");
    expect(container.querySelector("nav[aria-label='Sections']")).not.toBeNull();
  });
});
