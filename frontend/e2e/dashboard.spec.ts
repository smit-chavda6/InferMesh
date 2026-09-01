import { test, expect, type Page } from "@playwright/test";

// Session comes from the `setup` project (e2e/.auth/admin.json). Each test just
// navigates; the sidebar being present confirms we're authenticated.
async function open(page: Page, path = "/") {
  await page.goto(path);
  await expect(page.getByRole("navigation")).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test.describe("§31 dashboard journey", () => {
  test("login → the overview loads real data", async ({ page }) => {
    await open(page);
    await expect(page.getByRole("heading", { name: "System Overview" })).toBeVisible();
    await expect(page.getByText("Total requests")).toBeVisible();
    // a KPI shows a formatted integer, not a skeleton
    await expect(page.locator("text=/^[0-9][0-9,]*$/").first()).toBeVisible();
  });

  test("requests explorer: filter by provider and open a details drawer", async ({ page }) => {
    await open(page, "/requests");
    await page.getByRole("button", { name: "OpenAI" }).click();
    await expect(page).toHaveURL(/provider=openai/);

    const firstRow = page.getByRole("row").nth(1);
    await expect(firstRow).toContainText("OpenAI");
    await firstRow.click();

    const drawer = page.getByRole("dialog");
    await expect(drawer.getByText("Provider", { exact: true })).toBeVisible();
    await expect(drawer.getByText("Input tokens", { exact: true })).toBeVisible();
    await expect(drawer.getByText("Cost", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
  });

  test("requests explorer: debounced text search updates the query string", async ({ page }) => {
    await open(page, "/requests");
    await page.getByPlaceholder(/Search request ID/i).fill("req_");
    await expect(page).toHaveURL(/search=req_/, { timeout: 5000 });
  });

  test("cost analytics: breakdown tabs re-query", async ({ page }) => {
    await open(page);
    await page.getByRole("link", { name: "Costs" }).click();
    await expect(page.getByRole("heading", { name: "Cost Analytics" })).toBeVisible();
    await expect(page.getByText("Projected monthly")).toBeVisible();

    await page.getByRole("button", { name: "By provider" }).click();
    await expect(page.getByRole("columnheader", { name: "Provider" })).toBeVisible();
    await page.getByRole("button", { name: "By project" }).click();
    await expect(page.getByRole("columnheader", { name: "Project" })).toBeVisible();
  });

  test("range picker rewrites ?range", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "7d", exact: true }).click();
    await expect(page).toHaveURL(/range=7d/);
    await page.getByRole("button", { name: "1h", exact: true }).click();
    await expect(page).toHaveURL(/range=1h/);
  });

  test("providers page lists every provider with a health status", async ({ page }) => {
    await open(page, "/providers");
    for (const name of ["OpenAI", "Anthropic", "Gemini", "Azure AI Foundry"]) {
      await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
    }
  });

  test("system health shows gateway + dependencies", async ({ page }) => {
    await open(page, "/system");
    await expect(page.getByText("PostgreSQL").first()).toBeVisible();
    await expect(page.getByText("Redis").first()).toBeVisible();
    await expect(page.getByText("Azure AI Foundry").first()).toBeVisible();
  });

  test("live activity: pause/resume toggles the stream", async ({ page }) => {
    await open(page, "/live");
    await expect(page.getByText("LIVE", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Pause" }).click();
    await expect(page.getByText("Paused", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Resume" }).click();
    await expect(page.getByText("LIVE", { exact: true })).toBeVisible();
  });

  test("theme switch toggles and persists across reload", async ({ page }) => {
    await open(page);
    const html = page.locator("html");
    const wasDark = await html.evaluate((el) => el.classList.contains("dark"));
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await expect.poll(() => html.evaluate((el) => el.classList.contains("dark"))).toBe(!wasDark);
    await page.reload();
    await expect.poll(() => html.evaluate((el) => el.classList.contains("dark"))).toBe(!wasDark);
    // put it back so later tests start from the same theme
    await page.getByRole("button", { name: "Toggle theme" }).click();
  });

  test("API keys: create a project, reveal its key once, then revoke it", async ({ page }) => {
    await open(page, "/projects");
    const unique = `e2e-${Date.now()}`;

    await page.getByRole("button", { name: "New API key" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Project name").fill(unique);
    await dialog.getByRole("button", { name: "Create", exact: true }).click();

    const reveal = page.getByRole("dialog");
    await expect(reveal.getByText(/^sk-gw-/)).toBeVisible();
    await reveal.getByRole("button", { name: "Done" }).click();

    const row = page.getByRole("row", { name: new RegExp(unique) });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Revoke" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Revoke", exact: true }).click();
    await expect(row).toContainText(/revoked/i);
  });

  test("error state: a failing endpoint renders the retry affordance", async ({ page }) => {
    await page.route("**/v1/usage/summary**", (r) => r.fulfill({ status: 500, body: "{}" }));
    await open(page, "/?range=24h");
    await expect(page.getByText("Couldn't load this data")).toBeVisible();
    await expect(page.getByRole("button", { name: /Retry/i })).toBeVisible();
  });

  test("sign out returns to the login screen", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("heading", { name: "Sign in to InferMesh" })).toBeVisible();
    await expect(page.getByRole("navigation")).toBeHidden();
    // the session is really gone — a reload stays on login
    await page.reload();
    await expect(page.getByRole("heading", { name: "Sign in to InferMesh" })).toBeVisible();
  });
});
