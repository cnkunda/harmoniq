#!/usr/bin/env node
/**
 * UX Improvement Loop — Orchestrator
 *
 * Usage:
 *   node scripts/audit/ux-improve-loop.mjs              # fresh run (capture + analyze)
 *   node scripts/audit/ux-improve-loop.mjs --verify      # re-analyze existing screenshots
 *   node scripts/audit/ux-improve-loop.mjs --skip-server  # skip web server start (use running one)
 *
 * Output:
 *   docs/audit/ui-feedback-report.json  — full gap report
 *   docs/audit/ux-improve-state.json    — loop state tracker
 */
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import os from "node:os";

const ROOT_DIR = process.cwd();
const VISION_PROXY = "/home/kunda/vision-tool/vision_proxy.py";
const OUTPUT_DIR = path.join(ROOT_DIR, "docs", "audit");
const CAPTURE_DIR = path.join(ROOT_DIR, "artifacts", "playwright", "screenshots");
const CAPTURE_MANIFEST = path.join(ROOT_DIR, "artifacts", "playwright", "route-capture-manifest.json");
const REPORT_PATH = path.join(OUTPUT_DIR, "ui-feedback-report.json");
const STATE_PATH = path.join(OUTPUT_DIR, "ux-improve-state.json");
const FIXED_MARKER = path.join(OUTPUT_DIR, ".ux-loop-complete");

const args = new Set(process.argv.slice(2));

// Detect platform: Git Bash (Windows) vs WSL vs native Linux
const IS_WINDOWS = os.platform() === "win32";
function pythonCmd() {
  return IS_WINDOWS ? "wsl.exe python3" : "python3";
}

function toWslPath(winPath) {
  if (!IS_WINDOWS) return winPath;
  const abs = path.resolve(winPath);
  // Windows absolute: C:\foo\bar → /mnt/c/foo/bar
  const m = abs.match(/^([a-zA-Z]):\\(.*)$/);
  if (m) {
    return `/mnt/${m[1].toLowerCase()}/${m[2].replaceAll("\\", "/")}`;
  }
  // Cygwin absolute: /c/foo/bar (single letter, then /) → /mnt/c/foo/bar
  const m2 = abs.match(/^\/([a-zA-Z])\/(.+)$/);
  if (m2) {
    return `/mnt/${m2[1].toLowerCase()}/${m2[2]}`;
  }
  // Already a WSL/Linux path or relative — pass through
  return abs;
}

function ensure(dir) {
  mkdirSync(dir, { recursive: true });
}

function runPlaywrightCapture() {
  console.log("[loop] Capturing route screenshots via Playwright...");
  execSync("npx playwright test --config=playwright.config.ts tests/ui/route-capture.spec.ts", {
    cwd: ROOT_DIR,
    stdio: "inherit",
    timeout: 300_000,
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function execPython(args, timeout = 60_000) {
  return execSync(`${pythonCmd()} ${args}`, { encoding: "utf-8", timeout });
}

async function analyzeScreenshot(screenshotPath) {
  const absPath = path.resolve(screenshotPath);
  if (!existsSync(absPath)) {
    return { error: `File not found: ${absPath}` };
  }
  try {
    const imgPath = IS_WINDOWS ? toWslPath(absPath) : absPath;
    const description = execPython(
      `"${VISION_PROXY}" "${imgPath}"`,
      60_000,
    ).trim();
    // Rate limit: 2s between vision API calls
    await sleep(2000);
    return { description };
  } catch (err) {
    await sleep(2000);
    return { error: err.stderr?.toString().trim() || err.message };
  }
}

async function analyzeRoute(entry) {
  const dir = entry.directory;
  const viewportResult = await analyzeScreenshot(path.join(dir, "viewport.png"));
  const fullPageResult = await analyzeScreenshot(path.join(dir, "full-page.png"));
  const stateResults = {};
  if (entry.stateScreenshots) {
    for (const [state, screenshotPath] of Object.entries(entry.stateScreenshots)) {
      stateResults[state] = await analyzeScreenshot(screenshotPath);
    }
  }
  return {
    route: entry.route,
    viewport: viewportResult,
    fullPage: fullPageResult,
    states: stateResults,
    analyzedAt: new Date().toISOString(),
  };
}

function deriveGaps(analysis) {
  const text = [
    analysis.viewport.description || "",
    analysis.fullPage.description || "",
    ...Object.values(analysis.states).map((s) => s.description || ""),
  ].join(" ").toLowerCase();

  const gaps = [];
  const checks = [
    { severity: "error", keywords: ["overlap", "overflow", "clipped", "cut off"], issue: "Layout overflow / clipping" },
    { severity: "error", keywords: ["broken", "corrupt", "blank screen", "white screen"], issue: "Broken / blank screen" },
    { severity: "error", keywords: ["inaccessible"], issue: "Accessibility issue" },
    { severity: "warning", keywords: ["error", "alert"], issue: "Error state visible" },
    { severity: "warning", keywords: ["missing", "not found"], issue: "Missing element" },
    { severity: "warning", keywords: ["contrast", "readability", "hard to read"], issue: "Contrast / readability" },
    { severity: "warning", keywords: ["misalign", "off-center", "not centered"], issue: "Alignment issue" },
    { severity: "warning", keywords: ["color", "palette", "tone"], issue: "Color mismatch" },
    { severity: "warning", keywords: ["font", "typography", "typeface"], issue: "Typography" },
    { severity: "info", keywords: ["empty state"], issue: "Empty state detected" },
    { severity: "info", keywords: ["modal", "dialog"], issue: "Modal / dialog visible" },
    { severity: "info", keywords: ["loading", "spinner", "skeleton"], issue: "Loading state" },
    { severity: "info", keywords: ["spacing"], issue: "Spacing inconsistency" },
    { severity: "info", keywords: ["responsive", "mobile", "narrow"], issue: "Responsive layout" },
    { severity: "info", keywords: ["padding", "margin", "gap"], issue: "Padding / margin" },
  ];
  for (const check of checks) {
    if (check.keywords.some((kw) => text.includes(kw))) {
      gaps.push({ severity: check.severity, issue: check.issue, keywords: check.keywords });
    }
  }
  return gaps;
}

async function buildReport(entries) {
  const allGaps = [];
  const routeAnalyses = [];
  let totalIssues = 0;

  for (const entry of entries) {
    const analysis = await analyzeRoute(entry);
    const gaps = deriveGaps(analysis);
    if (gaps.length > 0) {
      totalIssues += gaps.length;
      allGaps.push({ route: entry.route, gaps });
    }
    routeAnalyses.push({ ...analysis, gaps });
  }

  const cosmeticOnly = (issue) => ["Layout overflow / clipping", "Broken / blank screen", "Error state visible",
    "Missing element", "Contrast / readability", "Alignment issue", "Color mismatch", "Typography",
    "Empty state detected", "Modal / dialog visible", "Loading state", "Spacing inconsistency",
    "Responsive layout", "Padding / margin", "Accessibility issue"].includes(issue);

  return {
    generatedAt: new Date().toISOString(),
    routesAnalyzed: entries.length,
    totalUiGapsFound: totalIssues,
    note: "Cosmetic-only fixes. Never change functionality or business logic.",
    summary: {
      error: allGaps.filter((r) => r.gaps.some((g) => g.severity === "error")).length,
      warning: allGaps.filter((r) => r.gaps.some((g) => g.severity === "warning")).length,
      info: allGaps.filter((r) => r.gaps.some((g) => g.severity === "info")).length,
    },
    allGapsByRoute: allGaps,
    routes: routeAnalyses,
    designSystem: {
      colors: "src/constants/colors.ts — wood/amber/cream tokens",
      typography: "Playfair Display (headings), DM Sans (body), JetBrains Mono (mono)",
      components: "AnimatedPressable, NoiseOverlay, WoodGradient, lucide-react-native",
      animation: "react-native-reanimated, spring/timing presets in src/constants/animations.ts",
    },
  };
}

function loadState() {
  if (existsSync(STATE_PATH)) {
    return JSON.parse(readFileSync(STATE_PATH, "utf-8"));
  }
  return { iteration: 0, fixedGapIds: [], lastReportPath: null };
}

function saveState(state) {
  ensure(OUTPUT_DIR);
  writeFileSync(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`, "utf-8");
}

function findSourceFiles(route) {
  const appDir = path.join(ROOT_DIR, "app");
  if (route === "/" || route === "root") {
    return [path.join(appDir, "index.tsx"), path.join(appDir, "index.ts")].filter((f) => existsSync(f));
  }
  const segments = route.replace(/^\//, "").split("/").filter(Boolean);
  let candidate = appDir;
  for (const seg of segments) {
    candidate = path.join(candidate, seg);
  }
  const files = [];
  for (const ext of [".tsx", ".ts", ".jsx", ".js"]) {
    if (existsSync(candidate + ext)) files.push(candidate + ext);
  }
  const indexFiles = [];
  for (const ext of [".tsx", ".ts", ".jsx", ".js"]) {
    const p = path.join(candidate, "index" + ext);
    if (existsSync(p)) indexFiles.push(p);
  }
  return [...files, ...indexFiles];
}

function isServerRunning(url = "http://127.0.0.1:8081") {
  return new Promise((resolve) => {
    const req = http.get(url, () => { resolve(true); req.destroy(); });
    req.on("error", () => resolve(false));
    req.setTimeout(2000, () => { req.destroy(); resolve(false); });
  });
}

async function run() {
  const isVerify = args.has("--verify");
  const skipServer = args.has("--skip-server");
  const wantHelp = args.has("--help") || args.has("-h");

  if (wantHelp) {
    console.log(`UX Improvement Loop — Orchestrator

Usage:
  npm run ux:improve               Fresh capture + analyze
  npm run ux:verify                Re-analyze existing screenshots
  npm run ux:improve -- --skip-server  Skip web server start (attach to running one)

Prerequisites:
  - Expo web server running on http://127.0.0.1:8081
    (run \`npm run web\` in another terminal, or let Playwright auto-start it)

Output:
  docs/audit/ui-feedback-report.json  — gap report
  docs/audit/ux-improve-state.json    — loop iteration state
`);
    process.exit(0);
  }

  ensure(OUTPUT_DIR);

  // Clear vision-tool backend memory before fresh capture+analysis (not on --verify)
  if (!isVerify) {
    try {
      execSync(`rm -f /home/kunda/vision-tool/backend_memory.json`, { encoding: "utf-8", timeout: 5000 });
      console.log("[loop] Cleared vision-tool backend memory.");
    } catch {}
  }

  if (!isVerify) {
    if (!skipServer) {
      const alive = await isServerRunning();
      if (!alive) {
        console.log("[loop] No running server detected at http://127.0.0.1:8081.");
        console.log("[loop] Playwright will auto-start Expo (this may take ~3 min on first run).");
        console.log("[loop] Tip: run `npm run web` in another terminal and use --skip-server.\n");
      }
    }
    runPlaywrightCapture();
  }

  if (!existsSync(CAPTURE_MANIFEST)) {
    console.error("[loop] No capture manifest found. Run without --verify first.");
    process.exit(1);
  }

  const entries = JSON.parse(readFileSync(CAPTURE_MANIFEST, "utf-8"));
  const report = await buildReport(entries);
  const reportPath = writeReport(report);
  const state = loadState();
  state.iteration += 1;
  state.lastReportPath = reportPath;

  const errorRoutes = report.allGapsByRoute.filter((r) => r.gaps.some((g) => g.severity === "error"));
  const warningRoutes = report.allGapsByRoute.filter((r) => r.gaps.some((g) => g.severity === "warning"));

  const actionable = [];
  for (const { route, gaps } of [...errorRoutes, ...warningRoutes]) {
    const files = findSourceFiles(route);
    actionable.push({
      route,
      gaps: gaps.filter((g) => g.severity !== "info"),
      sourceFiles: files,
    });
  }

  const isComplete = actionable.length === 0;
  if (isComplete) {
    writeFileSync(FIXED_MARKER, new Date().toISOString(), "utf-8");
  } else {
    try { unlinkSync(FIXED_MARKER); } catch {}
  }

  saveState(state);

  console.log(JSON.stringify({
    status: isComplete ? "complete" : "needs_fixes",
    iteration: state.iteration,
    routesAnalyzed: report.routesAnalyzed,
    totalGaps: report.totalUiGapsFound,
    summary: report.summary,
    actionableIssues: actionable.length,
    actionable,
    output: reportPath,
    stateFile: STATE_PATH,
    isComplete,
  }, null, 2));
}

function writeReport(report) {
  ensure(OUTPUT_DIR);
  const p = REPORT_PATH;
  writeFileSync(p, `${JSON.stringify(report, null, 2)}\n`, "utf-8");
  return p;
}

run().catch((err) => {
  console.error("[loop] Fatal error:", err.message);
  process.exit(1);
});
