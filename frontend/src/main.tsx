import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/overlays";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/api/client";
import App from "./App";
import "./index.css";

// Apply the saved theme before first paint so every screen — including the
// pre-auth login page, which never mounts AppLayout/useTheme — is themed and
// there's no light-mode flash. AppLayout's useTheme still owns the toggle.
try {
  const saved = localStorage.getItem("gw-theme");
  const dark =
    saved === "dark" ||
    (saved !== "light" && (window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true));
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
} catch {
  /* private mode / storage disabled — fall back to the CSS default (dark) */
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (count, error) => {
        if (error instanceof ApiError && [400, 401, 403, 404].includes(error.status)) return false;
        return count < 2;
      },
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider delayDuration={200}>
          <ToastProvider>
            <App />
          </ToastProvider>
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
