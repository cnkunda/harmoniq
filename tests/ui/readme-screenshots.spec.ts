/**
 * Regenerates the screenshots embedded in README.md.
 *
 * Disabled during the normal UI suite (set README_CAPTURE=1 to run):
 *   README_CAPTURE=1 npx playwright test --config=playwright.config.ts tests/ui/readme-screenshots.spec.ts
 *
 * Uses the deterministic UX-audit seed for library/progress screens and the
 * offline demo lesson for session screens. Viewport is 1280×900 Chromium.
 */
import { expect, test, type Page } from "@playwright/test";
import { installUxAuditApiMocks, seedUxAuditState, waitForUxAuditDb } from "./support/uxSeed";

test.describe.configure({ mode: "serial", timeout: 180_000 });

test.skip(process.env.README_CAPTURE !== "1", "Set README_CAPTURE=1 to regenerate README screenshots");

async function hideDevOverlay(page: Page): Promise<void> {
  await page.addStyleTag({
    content: ".__expo_fast_refresh, .__expo_fast_refresh_show { display: none !important; }",
  });
}

async function seedOnboardingPrefs(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });
    try {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction("app_prefs", "readwrite");
        const store = tx.objectStore("app_prefs");
        store.put({ key: "onboarding_complete", value: "1" });
        store.put({ key: "mood_check_skip", value: "1" });
        store.put({ key: "session_skip_tune", value: "1" });
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error ?? new Error("IndexedDB write failed"));
      });
    } finally {
      db.close();
    }
  });
}

test("capture library and practice screens", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await installUxAuditApiMocks(page);
  await page.goto("/");
  await waitForUxAuditDb(page);
  await seedUxAuditState(page);

  await page.goto("/");
  await page.waitForTimeout(1200);
  await hideDevOverlay(page);
  await page.screenshot({ path: "docs/screenshots/home.png" });

  await page.goto("/progress");
  await page.waitForTimeout(1200);
  await hideDevOverlay(page);
  await page.screenshot({ path: "docs/screenshots/progress.png" });

  await page.goto("/scale-explorer");
  await page.waitForTimeout(1200);
  await hideDevOverlay(page);
  await page.getByRole("button", { name: "CAGED form E" }).click();
  await page.waitForTimeout(600);
  await page.locator('[data-testid="fretboard-diagram"]:visible').first().scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 420);
  await page.waitForTimeout(800);
  await page.screenshot({ path: "docs/screenshots/scale-explorer.png" });
});

test("capture demo session screens", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await installUxAuditApiMocks(page);
  await page.goto("/");
  await waitForUxAuditDb(page);
  await seedOnboardingPrefs(page);

  await page.goto("/");
  await page.getByRole("button", { name: "Play demo session" }).click();
  await expect(page).toHaveURL(/\/session\/musical-tolerance/, { timeout: 30_000 });
  await page.getByRole("button", { name: "Select mode Expressive" }).click();
  await expect(page).toHaveURL(/\/session\/study/, { timeout: 30_000 });
  await page.waitForTimeout(2200);
  await hideDevOverlay(page);
  await page.mouse.wheel(0, 620);
  await page.waitForTimeout(800);
  await page.screenshot({ path: "docs/screenshots/study.png" });

  await page.getByRole("button", { name: /Next: Slow/ }).click();
  await expect(page).toHaveURL(/\/session\/slow/);
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: /Next: Play/ }).click();
  await expect(page).toHaveURL(/\/session\/play/);
  await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
  await hideDevOverlay(page);
  await page.mouse.wheel(0, 420);
  await page.waitForTimeout(800);
  await page.screenshot({ path: "docs/screenshots/play.png" });
});
