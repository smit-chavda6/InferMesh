import { test, expect } from "@playwright/test";

/**
 * Records real numbers against the ~100k-row seed (spec §32). Not a hard gate on
 * an exact ms value (CI hardware varies) — it asserts a generous ceiling and
 * prints the measurement so it can be tracked in PROGRESS.md.
 */
test("overview is interactive quickly against the 100k-row seed", async ({ page }) => {
  const t0 = Date.now();
  await page.goto("/", { waitUntil: "domcontentloaded" });

  // "interactive" = the first KPI shows a real formatted number, not a skeleton
  const kpiValue = page.locator("text=/^[0-9][0-9,]{2,}$/").first();
  await expect(kpiValue).toBeVisible({ timeout: 10_000 });
  const tReady = Date.now() - t0;

  await page.waitForLoadState("networkidle");
  const nav = await page.evaluate(() => {
    const e = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    return {
      domContentLoaded: Math.round(e.domContentLoadedEventEnd),
      load: Math.round(e.loadEventEnd),
      transferKB: Math.round(
        performance
          .getEntriesByType("resource")
          .reduce((s, r) => s + ((r as PerformanceResourceTiming).transferSize || 0), 0) / 1024,
      ),
    };
  });

  console.log(
    `[perf] overview time-to-first-KPI=${tReady}ms  domContentLoaded=${nav.domContentLoaded}ms  ` +
      `load=${nav.load}ms  transfer=${nav.transferKB}KB`,
  );

  // The number is what matters (recorded above). The assertion is a loose guard;
  // a cold Vite dev transform on CI hardware is slower than a warm local run.
  expect(tReady).toBeLessThan(process.env.CI ? 12_000 : 3_000);
});

test("requests explorer paginates a 100k-row table without lag", async ({ page }) => {
  await page.goto("/requests");
  await expect(page.getByRole("navigation")).toBeVisible();

  const firstCell = () => page.getByRole("row").nth(1).locator("td").first();
  await expect(firstCell()).toBeVisible();
  const before = await firstCell().textContent();

  const t0 = Date.now();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(firstCell()).not.toHaveText(before ?? "");
  const dt = Date.now() - t0;
  console.log(`[perf] requests next-page render=${dt}ms`);
  expect(dt).toBeLessThan(process.env.CI ? 6_000 : 2_000);
});
