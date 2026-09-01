import { useState } from "react";
import { ArrowRight, Boxes, Eye, EyeOff, Lock, Mail, Moon, Sun } from "lucide-react";
import { useLogin } from "@/api/queries";
import { ApiError } from "@/api/client";
import { useTheme } from "@/hooks/useTheme";

export function LoginPage() {
  const login = useLogin();
  const { theme, toggle: toggleTheme } = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const err =
    login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? "Login failed."
        : null;

  return (
    <div className="relative flex min-h-screen flex-col justify-between overflow-hidden bg-bg text-text transition-colors duration-200 antialiased selection:bg-accent/20 selection:text-accent">
      {/* Subtle technical background grid & ambient radial glow */}
      <div className="pointer-events-none absolute inset-0 im-auth-grid opacity-70 dark:opacity-40" />
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 h-[520px] w-[520px] rounded-full im-ambient-glow opacity-15 dark:opacity-25"
        aria-hidden="true"
      />

      {/* Top Header */}
      <header className="relative z-10 flex w-full items-center justify-between px-6 py-6 sm:px-10">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div className="grid size-7 place-items-center rounded-md bg-accent text-accent-fg shadow-sm">
            <Boxes className="size-4" />
          </div>
          <span className="text-sm font-semibold tracking-tight text-text">InferMesh</span>
        </div>

        {/* Header Right Actions: Status Indicator & Theme Toggle */}
        <div className="flex items-center gap-2.5">
          {/* System Status Indicator */}
          <div className="flex items-center gap-2 rounded-full border border-border bg-panel/90 px-2.5 py-1 text-xs font-medium text-text-muted backdrop-blur-sm shadow-xs">
            <span className="relative flex size-2 items-center justify-center">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400/50 opacity-75 duration-1000" />
              <span className="relative inline-flex size-1.5 rounded-full bg-emerald-500" />
            </span>
            <span className="text-[11px] tracking-wide text-text-muted">Operational</span>
          </div>

          {/* Theme Toggle Button */}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            className="flex size-8 items-center justify-center rounded-md border border-border bg-panel/90 text-text-muted hover:bg-bg-subtle hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 transition-colors shadow-xs"
          >
            {theme === "dark" ? (
              <Sun className="size-4 transition-transform hover:rotate-12" />
            ) : (
              <Moon className="size-4 transition-transform hover:-rotate-12" />
            )}
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="relative z-10 flex flex-1 items-center justify-center px-4 py-8 sm:px-6">
        <div className="w-full max-w-[400px]">
          {/* Card Container */}
          <div className="im-rise relative overflow-hidden rounded-xl border border-border bg-panel/95 p-7 sm:p-8 shadow-xl shadow-black/5 dark:shadow-2xl dark:shadow-black/60 backdrop-blur-md">
            {/* Top progress indicator when submitting */}
            {login.isPending && (
              <div className="absolute inset-x-0 top-0 h-0.5 bg-accent/20 overflow-hidden">
                <div className="h-full w-1/3 bg-accent animate-[im-progress_1s_ease-in-out_infinite]" />
              </div>
            )}
            {/* Header / Intro */}
            <div className="text-left">
              <h1 className="text-xl font-semibold tracking-tight text-text sm:text-2xl">
                Welcome back.
              </h1>
              <p className="mt-1.5 text-sm text-text-muted">
                Sign in to your gateway console.
              </p>
            </div>

            {/* Login Form */}
            <form
              className="mt-6 space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                login.mutate({ email, password });
              }}
            >
              {/* Admin Email */}
              <div className="space-y-1.5">
                <label
                  htmlFor="email"
                  className="block text-xs font-medium text-text-muted"
                >
                  Admin email
                </label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-faint" />
                  <input
                    id="email"
                    type="email"
                    autoComplete="username"
                    placeholder="admin@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="h-10 w-full rounded-lg border border-border-strong bg-bg px-3 pl-9 text-sm text-text placeholder:text-text-faint outline-none transition duration-150 ease-in-out focus:border-accent focus:ring-2 focus:ring-accent/25 disabled:opacity-50"
                  />
                </div>
              </div>

              {/* Password */}
              <div className="space-y-1.5">
                <label
                  htmlFor="password"
                  className="block text-xs font-medium text-text-muted"
                >
                  Password
                </label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-faint" />
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="h-10 w-full rounded-lg border border-border-strong bg-bg pl-9 pr-10 text-sm text-text placeholder:text-text-faint outline-none transition duration-150 ease-in-out focus:border-accent focus:ring-2 focus:ring-accent/25 disabled:opacity-50"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-text-faint transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
                  >
                    {showPassword ? (
                      <EyeOff className="size-4" />
                    ) : (
                      <Eye className="size-4" />
                    )}
                  </button>
                </div>
              </div>

              {/* Error Message */}
              {err && (
                <div
                  role="alert"
                  className="animate-in rounded-lg border border-err/30 bg-err-bg px-3.5 py-2.5 text-xs font-medium text-err"
                >
                  {err}
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={login.isPending}
                className="group relative flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-accent-fg shadow-sm transition duration-150 ease-in-out hover:opacity-90 active:scale-[0.99] disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-panel"
              >
                {login.isPending ? (
                  <>
                    <span className="size-4 animate-spin rounded-full border-2 border-accent-fg/30 border-t-accent-fg" />
                    <span>Signing in…</span>
                  </>
                ) : (
                  <>
                    <span>Sign in</span>
                    <ArrowRight className="size-4 transition-transform duration-150 ease-out group-hover:translate-x-0.5" />
                  </>
                )}
              </button>
            </form>

            {/* Footer Trust Note */}
            <div className="mt-6 pt-4 border-t border-border/70 text-center">
              <p className="text-[11px] text-text-muted">
                <span className="text-accent mr-1">◇</span>
                Secure session · Short-lived JWT with rotating refresh
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Subtle Bottom Bar / Spacer */}
      <footer className="relative z-10 flex w-full justify-center px-6 py-4 text-xs text-text-faint" />
    </div>
  );
}
