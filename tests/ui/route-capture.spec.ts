import { test } from "@playwright/test";
import { loadRouteDefinitions } from "../routes";
import { captureRouteArtifacts, writeCaptureManifest } from "./support/capture";
import {
  installUxAuditApiMocks,
  seedUxAuditState,
  waitForUxAuditDb,
} from "./support/uxSeed";

const routes = loadRouteDefinitions();
const captureResults: Awaited<ReturnType<typeof captureRouteArtifacts>>[] = [];

test.describe.configure({ mode: "serial" });
// Route crawl with full renders (AlphaTab scores, waveforms) — heavy routes
// run close to the default 30s budget.
test.setTimeout(120_000);

test.beforeEach(async ({ page }) => {
  if (process.env.UX_AUDIT_SEED !== "1") return;
  await installUxAuditApiMocks(page);
  await page.goto("/");
  await waitForUxAuditDb(page);
  await seedUxAuditState(page);
});

for (const route of routes) {
  test(`capture route artifacts: ${route.path}`, async ({ page }) => {
    const capture = await captureRouteArtifacts(page, route);
    captureResults.push(capture);
  });
}

test.afterAll(async () => {
  writeCaptureManifest(captureResults);
});

