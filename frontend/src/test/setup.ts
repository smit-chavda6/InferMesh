import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// jsdom has no matchMedia / ResizeObserver / scrollTo — Recharts and Radix touch them.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
window.scrollTo ??= (() => {}) as typeof window.scrollTo;

// Recharts' ResponsiveContainer needs a non-zero size in jsdom.
vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(800);
vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(400);
