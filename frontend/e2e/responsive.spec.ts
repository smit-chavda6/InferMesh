import { test, expect, devices } from "@playwright/test";

test.describe("responsive layout", () => {
  test.use({ viewport: devices["Pixel 7"].viewport }); // 412 x 915

  test("mobile: sidebar collapses behind a hamburger, no horizontal overflow", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "System Overview" })).toBeVisible();

    // the persistent desktop sidebar is hidden at this width
    await expect(page.getByRole("navigation")).toBeHidden();

    // body doesn't scroll sideways
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    );
    expect(overflow, "no horizontal page overflow").toBe(true);

    // hamburger opens the nav drawer
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(page.getByRole("navigation")).toBeVisible();
    await page.getByRole("link", { name: "Costs" }).click();
    await expect(page.getByRole("heading", { name: "Cost Analytics" })).toBeVisible();
  });
});
