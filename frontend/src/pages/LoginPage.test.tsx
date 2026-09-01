import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/render";
import { LoginPage } from "./LoginPage";
import * as queries from "@/api/queries";
import { ApiError } from "@/api/client";

vi.mock("@/api/queries");
const q = vi.mocked(queries);

describe("LoginPage", () => {
  const mockMutate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    q.useLogin.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: false,
      error: null,
    } as never);
  });

  it("renders branding, operational status, and form elements", () => {
    renderWithProviders(<LoginPage />);

    expect(screen.getByText("InferMesh")).toBeInTheDocument();
    expect(screen.getByText("Operational")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    expect(screen.getByText("Sign in to your gateway console.")).toBeInTheDocument();

    expect(screen.getByLabelText("Admin email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(
      screen.getByText(/Secure session · Short-lived JWT with rotating refresh/i),
    ).toBeInTheDocument();
  });

  it("toggles password visibility", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    const passwordInput = screen.getByLabelText("Password");
    expect(passwordInput).toHaveAttribute("type", "password");

    const toggleButton = screen.getByRole("button", { name: /show password/i });
    await user.click(toggleButton);

    expect(passwordInput).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: /hide password/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /hide password/i }));
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("submits the form with user credentials", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    await user.type(screen.getByLabelText("Admin email"), "admin@test.com");
    await user.type(screen.getByLabelText("Password"), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate).toHaveBeenCalledWith({
      email: "admin@test.com",
      password: "secret123",
    });
  });

  it("shows loading state when authentication is pending", () => {
    q.useLogin.mockReturnValue({
      mutate: mockMutate,
      isPending: true,
      isError: false,
      error: null,
    } as never);

    renderWithProviders(<LoginPage />);
    const submitBtn = screen.getByRole("button", { name: /signing in/i });
    expect(submitBtn).toBeDisabled();
  });

  it("displays error message on authentication failure", () => {
    q.useLogin.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: true,
      error: new ApiError(401, "invalid_credentials", "Invalid email or password"),
    } as never);

    renderWithProviders(<LoginPage />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Invalid email or password");
  });

  it("renders theme toggle and toggles theme on click", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />);

    const themeBtn = screen.getByRole("button", { name: /switch to (light|dark) mode/i });
    expect(themeBtn).toBeInTheDocument();
    await user.click(themeBtn);
  });
});
