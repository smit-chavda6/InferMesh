import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Route → the <h1> text that proves it finished its first render.
const PAGES: [string, RegExp][] = [
  ["/", /System Overview/],
  ["/requests", /^Requests$/],
  ["/providers", /^Providers$/],
  ["/costs", /Cost Analytics/],
  ["/cache", /Cache Analytics/],
  ["/rate-limits", /Rate Limits/],
  ["/projects", /API Keys/],
  ["/alerts", /^Alerts$/],
  ["/live", /Live Activity/],
  ["/system", /System Health/],
];

for (const [path, heading] of PAGES) {
  test(`no critical/serious axe violations: ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    // let charts/tables settle
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    if (blocking.length) {
      console.log(
        JSON.stringify(
          blocking.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
          null,
          2,
        ),
      );
    }
    expect(blocking, `${blocking.length} critical/serious a11y violations on ${path}`).toEqual([]);
  });
}
