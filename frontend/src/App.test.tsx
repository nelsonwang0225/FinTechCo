import { StrictMode, act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";
import { MAYA, PRIYA, mockFetch, sessionFlow } from "./test/mockApi";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

async function render(path = "/overview") {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(
      <StrictMode>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </StrictMode>,
    );
  });
  return container;
}

async function click(el: Element | null) {
  if (!el) throw new Error("element not found");
  await act(async () => {
    (el as HTMLElement).click();
  });
}

function buttonByText(scope: Element, text: string): HTMLButtonElement | null {
  return Array.from(scope.querySelectorAll("button")).find((b) => b.textContent?.includes(text)) ?? null;
}

afterEach(() => {
  if (root) {
    act(() => root?.unmount());
  }
  container?.remove();
  root = null;
  container = null;
});

describe("App", () => {
  it("shows the persona chooser when there is no session, then the portal for the chosen persona", async () => {
    const { calls } = mockFetch(sessionFlow([MAYA, PRIYA]));
    const el = await render();
    expect(el.textContent).toContain("Choose who you are");
    expect(el.textContent).toContain("Maya Chen");
    expect(el.querySelector("nav[aria-label='Sections']")).toBeNull();

    await click(buttonByText(el, "Maya Chen"));

    const started = calls.find((c) => c.url === "/api/dev/session");
    expect(started?.body).toEqual({ user_id: MAYA.user.id, merchant_id: MAYA.merchant.id });
    const nav = el.querySelector("nav[aria-label='Sections']");
    expect(nav).not.toBeNull();
    const labels = Array.from(nav!.querySelectorAll("a")).map((a) => a.textContent);
    expect(labels).toEqual(["Overview", "Payments", "Payment Health", "Customers", "Disputes", "Reports"]);
    expect(el.querySelector(".topbar-merchant-name")?.textContent).toBe("Alder & Loom");
    expect(el.textContent).toContain("Demo environment · Synthetic data");
    expect(el.textContent).toContain("Signed in as");
  });

  it("switching persona remounts the product for the other business", async () => {
    mockFetch(sessionFlow([MAYA, PRIYA]));
    const el = await render();
    await click(buttonByText(el, "Priya Shah"));
    expect(el.querySelector(".topbar-merchant-name")?.textContent).toBe("Juniper Trail Outfitters");

    const select = el.querySelector<HTMLSelectElement>("#persona-switch");
    expect(select).not.toBeNull();
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
      setter?.call(select, `${MAYA.user.id}|${MAYA.merchant.id}`);
      select!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(el.querySelector(".topbar-merchant-name")?.textContent).toBe("Alder & Loom");
  });

  it("renders the forbidden state for a section the role lacks", async () => {
    mockFetch(sessionFlow([MAYA]));
    const el = await render("/payouts");
    await click(buttonByText(el, "Maya Chen"));
    expect(el.textContent).toContain("Your role does not include this section");
  });

  it("returns to the chooser after signing out", async () => {
    mockFetch(sessionFlow([MAYA]));
    const el = await render();
    await click(buttonByText(el, "Maya Chen"));
    await click(buttonByText(el, "Sign out"));
    expect(el.textContent).toContain("Choose who you are");
  });
});
