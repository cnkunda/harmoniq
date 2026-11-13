import { expect, test } from "@playwright/test";
import {
  installUxAuditApiMocks,
  seedUxAuditState,
  waitForUxAuditDb,
} from "./support/uxSeed";

/**
 * Commit 2 — CI route smoke.
 *
 * Keeps the PR Playwright gate small and deterministic: a handful of seeded
 * routes are rendered with the same API/IndexedDB fixtures as the UX audit, and
 * any uncaught exception fails the run. Visual regression and the full route
 * crawl stay out of the PR path.
 */

type SmokeRoute = {
  path: string;
  landmark: string;
};

const SMOKE_ROUTES: SmokeRoute[] = [
  { path: "/", landmark: "Ready to play?" },
  { path: "/add-song", landmark: "Add Song" },
  { path: "/library", landmark: "Library" },
  { path: "/progress", landmark: "Your Progress" },
  { path: "/settings", landmark: "Settings" },
];

test.describe.configure({ mode: "serial" });
// First navigation pays for the cold Metro bundle, which can take minutes on a
// cold CI runner.
test.setTimeout(300_000);
test.use({ navigationTimeout: 240_000 });

test.beforeEach(async ({ page }) => {
  await installUxAuditApiMocks(page);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await waitForUxAuditDb(page);
  await seedUxAuditState(page);
});

for (const route of SMOKE_ROUTES) {
  test(`@smoke renders ${route.path} without an uncaught error`, async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => {
      pageErrors.push(error.message);
    });

    await page.goto(route.path, { waitUntil: "domcontentloaded" });

    await expect(page.getByText(route.landmark, { exact: false }).first()).toBeVisible({
      timeout: 30_000,
    });
    expect(pageErrors).toEqual([]);
  });
}
