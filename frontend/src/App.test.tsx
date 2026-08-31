import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/render";
import App from "./App";
import * as queries from "@/api/queries";
import { ApiError } from "@/api/client";

vi.mock("@/api/queries");
const q = vi.mocked(queries);

// every hook the tree might call → a benign idle result
const idle = { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn() };
beforeEach(() => {
  vi.clearAllMocks();
  for (const key of Object.keys(queries) as (keyof typeof queries)[]) {
    const fn = q[key];
    if (typeof fn === "function") {
      (fn as unknown as { mockReturnValue: (v: unknown) => void }).mockReturnValue({
        ...idle,
        mutate: vi.fn(),
      });
    }
  }
});

describe("App auth gate", () => {
  it("shows a spinner while the session check is in flight", () => {
    q.useAuthMe.mockReturnValue({ ...idle, isLoading: true } as never);
    const { container } = renderWithProviders(<App />);
    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("renders the login screen on a 401", () => {
    q.useAuthMe.mockReturnValue({
      ...idle,
      isError: true,
      error: new ApiError(401, "admin_auth_required", "nope"),
    } as never);
    renderWithProviders(<App />);
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("renders the dashboard shell once authenticated", () => {
    q.useAuthMe.mockReturnValue({ ...idle, data: { email: "admin@example.com" } } as never);
    renderWithProviders(<App />, { route: "/" });
    // sidebar nav is present
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(screen.getAllByText("InferMesh").length).toBeGreaterThan(0);
  });
});
