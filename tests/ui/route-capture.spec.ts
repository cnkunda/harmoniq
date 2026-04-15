import { test } from "@playwright/test";
import { loadRouteDefinitions } from "../routes";
import { captureRouteArtifacts, writeCaptureManifest } from "./support/capture";

const routes = loadRouteDefinitions();
const captureResults: Awaited<ReturnType<typeof captureRouteArtifacts>>[] = [];

test.describe.configure({ mode: "serial" });

for (const route of routes) {
  test(`capture route artifacts: ${route.path}`, async ({ page }) => {
    const capture = await captureRouteArtifacts(page, route);
    captureResults.push(capture);
  });
}

test.afterAll(async () => {
  writeCaptureManifest(captureResults);
});

