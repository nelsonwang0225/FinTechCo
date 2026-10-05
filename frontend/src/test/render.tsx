import { StrictMode, act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { SessionProvider } from "../session/SessionProvider";

export interface Rendered {
  container: HTMLDivElement;
  unmount: () => void;
}

/** Mount a page inside the session provider and a memory router at `path`; fetch must already be mocked. */
export async function renderPage(element: ReactNode, path: string, routePattern = "*"): Promise<Rendered> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root: Root = createRoot(container);
  await act(async () => {
    root.render(
      <StrictMode>
        <MemoryRouter initialEntries={[path]}>
          <SessionProvider>
            <Routes>
              <Route path={routePattern} element={element} />
            </Routes>
          </SessionProvider>
        </MemoryRouter>
      </StrictMode>,
    );
  });
  // Let the session and the page's first fetches settle.
  await act(async () => {
    await Promise.resolve();
  });
  return {
    container,
    unmount: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

export async function click(el: Element | null): Promise<void> {
  if (!el) throw new Error("element not found");
  await act(async () => {
    (el as HTMLElement).click();
  });
}

export async function setValue(el: Element | null, value: string): Promise<void> {
  if (!el) throw new Error("element not found");
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  await act(async () => {
    setter?.call(el, value);
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

export async function flush(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
