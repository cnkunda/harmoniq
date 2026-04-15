import { expect, test } from "@playwright/test";
import { loadRouteDefinitions } from "../routes";

const routes = loadRouteDefinitions();

test.describe.configure({ mode: "serial" });

for (const route of routes) {
  test(`@visual visual baseline: ${route.path}`, async ({ page }) => {
    await page.goto(route.path, { waitUntil: "domcontentloaded" });
    try {
      await page.waitForLoadState("networkidle", { timeout: 7_500 });
    } catch {
      // Ignore when the app keeps long-lived requests open.
    }

    const routeKey = route.path === "/" ? "root" : route.path.replaceAll("/", "__").replaceAll(":", "_");
    await expect(page).toHaveScreenshot(`${routeKey}-viewport.png`, {
      fullPage: false,
    });
    await expect(page).toHaveScreenshot(`${routeKey}-fullpage.png`, {
      fullPage: true,
    });
  });
}

