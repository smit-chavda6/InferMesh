import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end suite (spec §31). Brings up the gateway (backend/.env + seeded
 * Postgres/Redis must be available) and the Vite dev server, then drives the
 * dashboard through Chromium. Set PW_NO_SERVER=1 to run against an already-running
 * stack.
 */
const PORT = 5173;
const baseURL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/admin.json" },
      dependencies: ["setup"],
    },
  ],
  webServer: process.env.PW_NO_SERVER
    ? undefined
    : [
        {
          command: "node e2e/backend-server.mjs",
          url: "http://127.0.0.1:8000/health",
          reuseExistingServer: !process.env.CI,
          timeout: 90_000,
          stdout: "pipe",
        },
        {
          command: `npm run dev -- --host 127.0.0.1 --port ${PORT} --strictPort`,
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: 60_000,
        },
      ],
});
