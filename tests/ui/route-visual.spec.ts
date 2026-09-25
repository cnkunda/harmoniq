import { expect, test } from "@playwright/test";
import { loadRouteDefinitions } from "../routes";

const routes = loadRouteDefinitions();

test.describe.configure({ mode: "serial", timeout: 120_000 });

for (const route of routes) {
  test(`@visual visual baseline: ${route.path}`, async ({ page }) => {
    await page.goto(route.path, { waitUntil: "domcontentloaded" });
    try {
      await page.waitForLoadState("networkidle", { timeout: 15_000 });
    } catch {
      // Ignore when the app keeps long-lived requests open.
    }
    await page.waitForTimeout(500);

    const routeKey = route.path === "/" ? "root" : route.path.replaceAll("/", "__").replaceAll(":", "_");
    await expect(page).toHaveScreenshot(`${routeKey}-viewport.png`, {
      fullPage: false,
      timeout: 30_000,
    });
    await expect(page).toHaveScreenshot(`${routeKey}-fullpage.png`, {
      fullPage: true,
      timeout: 30_000,
    });
  });
}

