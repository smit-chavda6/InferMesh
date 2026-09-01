import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { ToastProvider } from "./toast";
import { useToast } from "@/hooks/useToast";

function Harness({ duration }: { duration?: number }) {
  const { toast } = useToast();
  return (
    <button onClick={() => toast({ title: "Saved", description: "all good", tone: "ok", duration })}>
      go
    </button>
  );
}

afterEach(() => vi.useRealTimers());

describe("toast", () => {
  it("shows a polite status message and auto-dismisses after the default duration", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );

    act(() => void fireEvent.click(screen.getByRole("button", { name: "go" })));
    const toast = screen.getByRole("status");
    expect(toast).toHaveTextContent("Saved");
    expect(toast).toHaveTextContent("all good");
    expect(toast).toHaveAttribute("aria-live", "polite");

    act(() => vi.advanceTimersByTime(4100));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("with duration 0 it stays until closed", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Harness duration={0} />
      </ToastProvider>,
    );
    act(() => void fireEvent.click(screen.getByRole("button", { name: "go" })));
    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByRole("status")).toBeInTheDocument();

    act(() => void fireEvent.click(screen.getByRole("button", { name: /dismiss notification/i })));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("throws if useToast is used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Harness />)).toThrow(/ToastProvider/);
    spy.mockRestore();
  });
});
