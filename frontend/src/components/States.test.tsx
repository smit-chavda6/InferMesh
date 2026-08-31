import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState, ErrorState } from "./States";
import { ApiError } from "@/api/client";

describe("ErrorState", () => {
  it("shows an ApiError's message", () => {
    render(<ErrorState error={new ApiError(500, "provider_error", "upstream is down")} />);
    expect(screen.getByText("upstream is down")).toBeInTheDocument();
  });

  it("falls back to a generic message for a non-Error value", () => {
    render(<ErrorState error={"weird"} />);
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  });

  it("renders a Retry button only when onRetry is given, and calls it", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ErrorState error={new Error("x")} />);
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();

    rerender(<ErrorState error={new Error("x")} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("EmptyState", () => {
  it("renders the title, optional hint and action", () => {
    render(<EmptyState title="No requests" hint="try a wider range" action={<button>Add</button>} />);
    expect(screen.getByText("No requests")).toBeInTheDocument();
    expect(screen.getByText("try a wider range")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });
});
