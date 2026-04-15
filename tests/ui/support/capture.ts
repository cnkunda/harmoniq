import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import type { RouteDefinition, UiState } from "../../routes";

type CaptureResult = {
  route: string;
  directory: string;
  fullPageScreenshot: string;
  viewportScreenshot: string;
  stateScreenshots: Partial<Record<UiState, string>>;
};

function slugifyRoute(routePath: string): string {
  if (routePath === "/") {
    return "root";
  }
  return routePath.replaceAll("/", "__").replaceAll(":", "_").replaceAll("*", "all");
}

function ensureRouteOutputDir(routePath: string): string {
  const routeKey = slugifyRoute(routePath);
  const outputDir = path.resolve(process.cwd(), "artifacts", "playwright", "screenshots", routeKey);
  mkdirSync(outputDir, { recursive: true });
  return outputDir;
}

async function waitForPageReady(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  try {
    await page.waitForLoadState("networkidle", { timeout: 7_500 });
  } catch {
    // Some screens stream data or keep sockets open.
  }
}

export async function captureRouteArtifacts(page: Page, route: RouteDefinition): Promise<CaptureResult> {
  const routePath = route.path;
  const outputDir = ensureRouteOutputDir(routePath);

  await page.goto(routePath, { waitUntil: "domcontentloaded" });
  await waitForPageReady(page);

  const fullPageScreenshot = path.join(outputDir, "full-page.png");
  await page.screenshot({ path: fullPageScreenshot, fullPage: true });

  const viewportScreenshot = path.join(outputDir, "viewport.png");
  await page.screenshot({ path: viewportScreenshot, fullPage: false });

  const stateScreenshots: Partial<Record<UiState, string>> = {};
  const states: UiState[] = ["loading", "empty", "error", "modal"];

  for (const state of states) {
    const selector = route.stateSelectors?.[state];
    if (!selector) {
      continue;
    }
    const locator = page.locator(selector).first();
    if ((await locator.count()) === 0) {
      continue;
    }
    if (!(await locator.isVisible())) {
      continue;
    }
    const screenshotPath = path.join(outputDir, `${state}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: false });
    stateScreenshots[state] = screenshotPath;
  }

  return {
    route: routePath,
    directory: outputDir,
    fullPageScreenshot,
    viewportScreenshot,
    stateScreenshots,
  };
}

export function writeCaptureManifest(entries: CaptureResult[]): string {
  const outputPath = path.resolve(process.cwd(), "artifacts", "playwright", "route-capture-manifest.json");
  mkdirSync(path.dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, `${JSON.stringify(entries, null, 2)}\n`, "utf-8");
  return outputPath;
}

