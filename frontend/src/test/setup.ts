// Vitest setup: a fetch mock the tests program per case, so no component ever talks to a server.
import { beforeEach, vi } from "vitest";

// React 19 looks for this flag to allow act() in non-React test environments.
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  vi.restoreAllMocks();
});
