import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useTheme } from "./useTheme";

type MqListener = () => void;

function mockMatchMedia(dark: boolean) {
  const listeners = new Set<MqListener>();
  const mq = {
    matches: dark,
    media: "(prefers-color-scheme: dark)",
    addEventListener: (_: string, l: MqListener) => listeners.add(l),
    removeEventListener: (_: string, l: MqListener) => listeners.delete(l),
  };
  vi.stubGlobal("matchMedia", () => mq);
  return {
    setSystem(next: boolean) {
      mq.matches = next;
      listeners.forEach((l) => l());
    },
  };
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});
afterEach(() => vi.unstubAllGlobals());

describe("useTheme", () => {
  it("falls back to the OS preference when nothing is stored", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("honours an explicit stored choice over the OS", () => {
    localStorage.setItem("gw-theme", "light");
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
  });

  it("toggle persists the choice and flips the html class", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    act(() => result.current.toggle());
    expect(result.current.theme).toBe("dark");
    expect(localStorage.getItem("gw-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("follows a live OS change while there is no explicit choice", () => {
    const os = mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    act(() => os.setSystem(true));
    expect(result.current.theme).toBe("dark");
  });

  it("ignores OS changes after the user has toggled", () => {
    const os = mockMatchMedia(false);
    const { result } = renderHook(() => useTheme());
    act(() => result.current.toggle()); // now explicit "dark"
    act(() => os.setSystem(false));
    expect(result.current.theme).toBe("dark");
  });
});
