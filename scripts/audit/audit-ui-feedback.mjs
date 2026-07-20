import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import os from "node:os";

const ROOT_DIR = process.cwd();
const VISION_PROXY = "/home/kunda/vision-tool/vision_proxy.py";
const OUTPUT_DIR = path.join(ROOT_DIR, "docs", "audit");
const CAPTURE_MANIFEST = path.join(ROOT_DIR, "artifacts", "playwright", "route-capture-manifest.json");

const IS_WINDOWS = os.platform() === "win32";
function pythonCmd() {
  return IS_WINDOWS ? "wsl.exe python3" : "python3";
}
function toWslPath(winPath) {
  if (!IS_WINDOWS) return winPath;
  const abs = path.resolve(winPath);
  // Windows absolute: C:\foo\bar → /mnt/c/foo/bar
  const m = abs.match(/^([a-zA-Z]):\\(.*)$/);
  if (m) return `/mnt/${m[1].toLowerCase()}/${m[2].replaceAll("\\", "/")}`;
  // Cygwin absolute: /c/foo/bar → /mnt/c/foo/bar
  const m2 = abs.match(/^\/([a-zA-Z])\/(.+)$/);
  if (m2) return `/mnt/${m2[1].toLowerCase()}/${m2[2]}`;
  // Already a WSL/Linux path or relative — pass through
  return abs;
}

function ensureOutputDir() {
  mkdirSync(OUTPUT_DIR, { recursive: true });
}

function runPlaywrightCapture() {
  console.log("[ui-feedback] Running Playwright route capture...");
  execSync("npx playwright test --config=playwright.config.ts tests/ui/route-capture.spec.ts --reporter=json", {
    cwd: ROOT_DIR,
    stdio: "inherit",
    timeout: 300_000,
  });
}

function loadCaptureManifest() {
  if (!existsSync(CAPTURE_MANIFEST)) {
    console.error("[ui-feedback] No capture manifest found. Run npm run test:capture first.");
    return [];
  }
  const raw = readFileSync(CAPTURE_MANIFEST, "utf-8");
  return JSON.parse(raw);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function analyzeScreenshot(screenshotPath) {
  const absPath = path.resolve(ROOT_DIR, screenshotPath);
  if (!existsSync(absPath)) {
    await sleep(2000);
    return { error: `File not found: ${absPath}` };
  }
  try {
    const imgPath = IS_WINDOWS ? toWslPath(absPath) : absPath;
    const description = execSync(
      `${pythonCmd()} "${VISION_PROXY}" "${imgPath}"`,
      { encoding: "utf-8", timeout: 60_000 },
    ).trim();
    await sleep(2000);
    return { description };
  } catch (err) {
    await sleep(2000);
    if (err.stderr) {
      return { error: err.stderr.toString().trim() };
    }
    return { error: err.message };
  }
}

async function analyzeRoute(entry) {
  const viewportResult = await analyzeScreenshot(entry.viewportScreenshot || path.join(entry.directory, "viewport.png"));
  const fullPageResult = await analyzeScreenshot(entry.fullPageScreenshot || path.join(entry.directory, "full-page.png"));
  const stateResults = {};
  if (entry.stateScreenshots) {
    for (const [state, screenshotPath] of Object.entries(entry.stateScreenshots)) {
      stateResults[state] = await analyzeScreenshot(screenshotPath);
    }
  }
  return {
    route: entry.route,
    directory: entry.directory,
    viewport: viewportResult,
    fullPage: fullPageResult,
    states: stateResults,
    analyzedAt: new Date().toISOString(),
  };
}

function deriveUiGaps(analysis) {
  const gaps = [];
  const text = [
    analysis.viewport.description || "",
    analysis.fullPage.description || "",
    ...Object.values(analysis.states).map((s) => s.description || ""),
  ].join(" ").toLowerCase();

  if (text.includes("empty") && text.includes("state")) {
    gaps.push({ severity: "info", issue: "Empty state detected", detail: "Screen may need empty-state placeholder content" });
  }
  if (text.includes("error") || text.includes("alert")) {
    gaps.push({ severity: "warning", issue: "Error state present", detail: "Review error state appearance and messaging" });
  }
  if (text.includes("modal") || text.includes("dialog")) {
    gaps.push({ severity: "info", issue: "Modal/dialog visible", detail: "Confirm modal follows design system patterns" });
  }
  if (text.includes("loading") || text.includes("spinner") || text.includes("skeleton")) {
    gaps.push({ severity: "info", issue: "Loading state present", detail: "Check loading indicator matches design spec" });
  }
  if (text.includes("overlap") || text.includes("overflow") || text.includes("clipped") || text.includes("cut off")) {
    gaps.push({ severity: "error", issue: "Layout overflow or clipping", detail: "Content may be overflowing its container" });
  }
  if (text.includes("alignment") && (text.includes("misalign") || text.includes("off-center") || text.includes("not centered"))) {
    gaps.push({ severity: "warning", issue: "Alignment issue", detail: "Elements may not be properly aligned" });
  }
  if (text.includes("color") && (text.includes("contrast") || text.includes("readability") || text.includes("hard to read"))) {
    gaps.push({ severity: "warning", issue: "Contrast / readability", detail: "Text or elements may have insufficient contrast" });
  }
  if (text.includes("color") && (text.includes("palette") || text.includes("tone") || text.includes("mismatch"))) {
    gaps.push({ severity: "warning", issue: "Color mismatch", detail: "Colors may not follow design system tokens" });
  }
  if (text.includes("font") || text.includes("typography") || text.includes("typeface")) {
    gaps.push({ severity: "warning", issue: "Typography", detail: "Font may not match design system (Playfair Display / DM Sans / JetBrains Mono)" });
  }
  if (text.includes("spacing") && (text.includes("inconsistent") || text.includes("too tight") || text.includes("too loose"))) {
    gaps.push({ severity: "info", issue: "Spacing inconsistency", detail: "Check spacing follows design tokens" });
  }
  if (text.includes("padding") || text.includes("margin")) {
    gaps.push({ severity: "info", issue: "Padding / margin", detail: "Inconsistent padding or margin" });
  }
  if (text.includes("missing") || text.includes("not found")) {
    gaps.push({ severity: "warning", issue: "Missing element", detail: "Expected UI element may be absent" });
  }
  if (text.includes("responsive") || text.includes("mobile") || text.includes("narrow")) {
    gaps.push({ severity: "info", issue: "Responsive layout concern", detail: "Element may not adapt well to viewport" });
  }
  if (text.includes("broken") || text.includes("corrupt") || text.includes("blank") || text.includes("white screen")) {
    gaps.push({ severity: "error", issue: "Broken / blank screen", detail: "Screen may not render correctly" });
  }

  return gaps;
}

async function buildReport(results) {
  const allGaps = [];
  let totalIssues = 0;
  const routeAnalyses = [];

  for (const entry of results) {
    const analysis = await analyzeRoute(entry);
    const gaps = deriveUiGaps(analysis);
    if (gaps.length > 0) {
      totalIssues += gaps.length;
      allGaps.push({ route: entry.route, gaps });
    }
    routeAnalyses.push({ ...analysis, gaps });
  }

  return {
    generatedAt: new Date().toISOString(),
    routesAnalyzed: results.length,
    totalUiGapsFound: totalIssues,
    summary: {
      critical: allGaps.filter((r) => r.gaps.some((g) => g.severity === "error")).length,
      warnings: allGaps.filter((r) => r.gaps.some((g) => g.severity === "warning")).length,
      info: allGaps.filter((r) => r.gaps.some((g) => g.severity === "info")).length,
    },
    routes: routeAnalyses,
    allGaps,
  };
}

function writeReport(report) {
  ensureOutputDir();
  const outputPath = path.join(OUTPUT_DIR, "ui-feedback-report.json");
  writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf-8");
  return outputPath;
}

async function run() {
  console.log("[ui-feedback] Starting UI/UX audit...");

  if (!existsSync(CAPTURE_MANIFEST)) {
    runPlaywrightCapture();
  }

  const entries = loadCaptureManifest();
  console.log(`[ui-feedback] Analyzing ${entries.length} routes via vision-tool...`);

  const report = await buildReport(entries);
  const outputPath = writeReport(report);

  console.log(JSON.stringify({
    status: "ok",
    routesAnalyzed: report.routesAnalyzed,
    totalUiGapsFound: report.totalUiGapsFound,
    summary: report.summary,
    output: outputPath,
  }, null, 2));
}

run().catch((err) => {
  console.error("[ui-feedback] Fatal error:", err.message);
  process.exit(1);
});
