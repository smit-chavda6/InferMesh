import { test as setup, expect } from "@playwright/test";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "admin-dev-password";

export const AUTH_FILE = "e2e/.auth/admin.json";

// One real login for the whole suite — the gateway IP-rate-limits /v1/auth/login,
// so every spec reuses this saved session instead of signing in again.
setup("authenticate", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Admin email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation")).toBeVisible();
  await page.context().storageState({ path: AUTH_FILE });
});
