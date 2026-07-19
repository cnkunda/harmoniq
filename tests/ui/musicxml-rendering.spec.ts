/**
 * MusicXML cross-platform rendering test suite (Commit 108 AC #16/#17).
 *
 * Loads each edge-case MusicXML file from the corpus into AlphaTab via the
 * test harness and verifies:
 *   1. AlphaTab renders without crash (no JS errors)
 *   2. Render completes (status element shows "RENDER_COMPLETE")
 *   3. Visual regression screenshot matches baseline (tagged @visual)
 *
 * Run:
 *   npm run test:ui          — structural tests only (no screenshots)
 *   npm run test:visual      — visual regression (updates snapshots)
 */
import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync } from "fs";
import { join } from "path";

const CORPUS_DIR = join(__dirname, "musicxml-corpus");
const HARNESS_PATH = join(__dirname, "musicxml-harness.html");
const HARNESS_URL = "/tests/ui/musicxml-harness.html";

function getCorpusFiles(): string[] {
  return readdirSync(CORPUS_DIR)
    .filter((f) => f.endsWith(".musicxml"))
    .sort();
}

const corpusFiles = getCorpusFiles();

async function serveTestAssets(page: any) {
  await page.route("**/tests/ui/musicxml-harness.html", async (route) => {
    await route.fulfill({
      contentType: "text/html",
      body: readFileSync(HARNESS_PATH, "utf-8"),
    });
  });
  await page.route("**/tests/ui/musicxml-corpus/*", async (route) => {
    const url = route.request().url();
    const filename = url.split("/").pop() || "";
    await route.fulfill({
      contentType: "application/xml",
      body: readFileSync(join(CORPUS_DIR, filename), "utf-8"),
    });
  });
}

test.describe("MusicXML rendering — edge-case corpus", () => {
  test.describe.configure({ mode: "serial" });

  for (const file of corpusFiles) {
    const caseName = file.replace(".musicxml", "");

    test(`renders ${caseName} without crash`, async ({ page }) => {
      test.setTimeout(60_000);
      await serveTestAssets(page);
      // Navigate to harness with query param
      await page.goto(`${HARNESS_URL}?file=${encodeURIComponent(`musicxml-corpus/${file}`)}`, {
        waitUntil: "domcontentloaded",
      });

      // Wait for render complete or error (timeout 30s for complex scores)
      const statusEl = page.locator("#status");
      await expect(statusEl).toHaveText("RENDER_COMPLETE", { timeout: 30_000 });

      // Verify no error class
      await expect(statusEl).not.toHaveClass(/error/);
    });
  }
});

test.describe("MusicXML visual regression — edge-case corpus", () => {
  test.describe.configure({ mode: "serial" });

  for (const file of corpusFiles) {
    const caseName = file.replace(".musicxml", "");

    test(`@visual visual baseline: ${caseName}`, async ({ page }) => {
      test.setTimeout(120_000);
      await serveTestAssets(page);
      await page.goto(`${HARNESS_URL}?file=${encodeURIComponent(`musicxml-corpus/${file}`)}`, {
        waitUntil: "domcontentloaded",
      });

      // Wait for render
      const statusEl = page.locator("#status");
      await expect(statusEl).toHaveText("RENDER_COMPLETE", { timeout: 30_000 });

      // Wait a bit for layout to settle
      await page.waitForTimeout(500);

      // Take viewport screenshot for visual regression
      await expect(page).toHaveScreenshot(`${caseName}-viewport.png`, {
        fullPage: false,
      });
    });
  }
});
