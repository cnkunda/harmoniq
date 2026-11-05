#!/usr/bin/env node
/**
 * UX Improvement Loop — Orchestrator
 *
 * Usage:
 *   node scripts/audit/ux-improve-loop.mjs                # fresh run (capture + analyze)
 *   node scripts/audit/ux-improve-loop.mjs --verify       # post-fix verification: fresh capture + analyze
 *   node scripts/audit/ux-improve-loop.mjs --analyze-only # re-analyze existing screenshots (no capture)
 *   node scripts/audit/ux-improve-loop.mjs --skip-server  # skip web server check (use running one)
 *   node scripts/audit/ux-improve-loop.mjs --waive "<route>::<gapId>" --reason "..."   # persist a waiver
 *
 * Output:
 *   docs/audit/ui-feedback-report.json  — full gap report (schema v2)
 *   docs/audit/ux-improve-state.json    — loop state tracker
 *   docs/audit/ux-waivers.json          — persisted false-positive waivers
 *
 * Signal sources (report v2):
 *   - deterministic: DOM-measured checks from route capture (overflow, broken
 *     images, blank screens, off-palette colors, fonts, contrast). Authoritative.
 *   - vision: moondream defect inspection in a describe register (format
 *     instructions make it emit EOS) — parsed with negation-aware keyword
 *     matching. Advisory. Gap derivation never keyword-scans generic prose.
 *
 * Gap derivation is viewport-authoritative. Full-page screenshots are kept as
 * archival artifacts but are not analyzed: the app scrolls inside internal
 * containers, and full-page captures can race to blank.
 */
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import os from "node:os";
import { pathToFileURL } from "node:url";

const ROOT_DIR = process.cwd();
const VISION_PROXY = "/home/kunda/vision-tool/vision_proxy.py";
const OUTPUT_DIR = path.join(ROOT_DIR, "docs", "audit");
const CAPTURE_DIR = path.join(ROOT_DIR, "artifacts", "playwright", "screenshots");
const CAPTURE_MANIFEST = path.join(ROOT_DIR, "artifacts", "playwright", "route-capture-manifest.json");
const REPORT_PATH = path.join(OUTPUT_DIR, "ui-feedback-report.json");
const STATE_PATH = path.join(OUTPUT_DIR, "ux-improve-state.json");
const WAIVERS_PATH = path.join(OUTPUT_DIR, "ux-waivers.json");
const FIXED_MARKER = path.join(OUTPUT_DIR, ".ux-loop-complete");

// Passed unquoted as trailing words to the vision proxy — must contain no
// shell metacharacters (cmd.exe and /bin/sh both see it). Moondream emits an
// immediate EOS when given meta-instructions about output format ("reply in
// this exact format", "write exactly") — the prompt must stay in a pure
// describe register. Verified empirically; see UX_IMPROVE_LOOP.md.
const VISION_PROMPT = [
  "Describe any visual problems you see in this app screenshot, such as overlapping text,",
  "cut off text, unreadable low contrast text, misaligned rows or buttons, broken images,",
  "or colors that clash with the dark brown and cream theme.",
  "The dark brown and cream theme itself is intentional and correct.",
  "If there are no problems, say everything looks fine.",
].join(" ");

// Keyword matching is applied ONLY to the defect-hunting response (never to
// generic descriptions) with negation awareness.
const DEFECT_KEYWORDS = [
  "overlap", "overlapping", "cut off", "cut-off", "clipped", "truncated",
  "misaligned", "misalignment", "not aligned", "off center", "unreadable",
  "hard to read", "low contrast", "poor contrast", "broken image",
  "missing image", "clash", "clashing", "spills", "spilling",
];

const NEGATOR_BEFORE_RE =
  /\b(no|not|none|nothing|never|neither|nor|without|free|isn't|doesn't|n't)\b[\w\s]{0,20}$/i;

const ISSUE_SLUGS = {
  "Layout overflow / clipping": "layout-overflow",
  "Broken / blank screen": "blank-screen",
  "Broken image": "broken-image",
  "Contrast / readability": "contrast",
  "Alignment issue": "alignment",
  "Color mismatch": "color-mismatch",
  "Typography": "typography",
  "Other visual defect": "other",
};

// Maps a defect sentence to the canonical gap taxonomy.
const DEFECT_MAP = [
  { keywords: ["overlap", "cut off", "cut-off", "clipped", "truncated", "spill"], issue: "Layout overflow / clipping", severity: "error" },
  { keywords: ["broken image", "missing image", "image not", "failed to load"], issue: "Broken image", severity: "error" },
  { keywords: ["unreadable", "contrast", "hard to read", "readab"], issue: "Contrast / readability", severity: "warning" },
  { keywords: ["misalign", "not aligned", "off center", "uneven"], issue: "Alignment issue", severity: "warning" },
  { keywords: ["clash", "color", "colour", "palette", "bright"], issue: "Color mismatch", severity: "warning" },
  { keywords: ["font", "typeface", "typograph"], issue: "Typography", severity: "warning" },
];

const FIX_GUIDANCE = {
  "Layout overflow / clipping": {
    approach: "Add flex-shrink to overflowing children, fix container sizing, or overflow-hidden on the container.",
    allowed: "container/layout props only",
  },
  "Broken / blank screen": {
    approach: "Usually a runtime error — check the console. Only fix if caused by styling (missing className, wrong token).",
    allowed: "styling only; if functional, log as requires-functional-change",
  },
  "Broken image": {
    approach: "Verify the asset import/path. If the path itself is wrong that is a functional change — skip and log.",
    allowed: "styling/size only; asset path fixes are functional",
  },
  "Contrast / readability": {
    approach: "Swap to a higher-contrast token — e.g. muted.cream or ivory instead of muted2 for secondary text on wood.900.",
    allowed: "color tokens from src/constants/colors.ts only",
  },
  "Alignment issue": {
    approach: "Review flexbox alignment, gaps, and centering on the container.",
    allowed: "layout props only",
  },
  "Color mismatch": {
    approach: "Replace the off-palette color with the nearest token from src/constants/colors.ts or tailwind.config.js.",
    allowed: "token swap only",
  },
  "Typography": {
    approach: "Use font-serif / font-sans / font-sans-medium / font-mono classes (PlayfairDisplay, DMSans, JetBrainsMono).",
    allowed: "font class swap only",
  },
  "Other visual defect": {
    approach: "Inspect the screenshot and route source; apply a cosmetic fix with existing tokens and components.",
    allowed: "cosmetic only",
  },
};

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
  // UX_AUDIT_SEED mocks the API and seeds IndexedDB so routes render
  // representative content without the FastAPI backend, deterministically.
  execSync("npx playwright test --config=playwright.config.ts tests/ui/route-capture.spec.ts", {
    cwd: ROOT_DIR,
    stdio: "inherit",
    timeout: 600_000,
    env: { ...process.env, UX_AUDIT_SEED: "1" },
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function execPython(args, timeout = 180_000) {
  return execSync(`${pythonCmd()} ${args}`, { encoding: "utf-8", timeout });
}

async function analyzeScreenshot(screenshotPath) {
  const absPath = path.resolve(screenshotPath);
  if (!existsSync(absPath)) {
    return { error: `File not found: ${absPath}` };
  }
  try {
    const imgPath = IS_WINDOWS ? toWslPath(absPath) : absPath;
    // 360s matches the proxy's own call_ollama ceiling — if execSync killed
    // the relay earlier, the Linux-side python would survive as an orphan.
    const description = execPython(
      `"${VISION_PROXY}" "${imgPath}" ${VISION_PROMPT}`,
      360_000,
    ).trim();
    // Rate limit: 2s between vision API calls
    await sleep(2000);
    return { description };
  } catch (err) {
    await sleep(2000);
    return { error: err.stderr?.toString().trim() || err.message };
  }
}

/**
 * Parse the vision model's defect-hunting response. Moondream cannot follow
 * output-format instructions (immediate EOS), so the prompt stays in a
 * describe register and this parser derives the verdict:
 *   - defect sentences (keyword match, negation-aware) → verdict "fail"
 *   - clean sentinel ("everything looks fine" / "no problems") or an
 *     uncontaminated description with no defect keywords → "pass"
 *   - empty model content (Ollama dict repr leak) → null (parse failure)
 */
function parseVisionVerdict(description) {
  if (!description) return { verdict: null, defects: [] };
  // Moondream returned empty content and the proxy fell back to the raw
  // Ollama response dict as a string — treat as a parse failure, not a pass.
  if (/^\{'model':/m.test(description)) return { verdict: null, defects: [] };

  const lines = description
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
    .filter((l) => !/^\[[^\]]*\]$/.test(l))
    // wsl.exe can leak the proxy's stderr diagnostics into stdout — drop them.
    .filter((l) => !/^(SEARCH|KEYS|MEMORY|FALLBACK):/i.test(l));
  const clean = lines.join(" ");
  if (clean.length === 0) return { verdict: null, defects: [] };

  const defects = [];
  for (const sentence of clean.split(/(?<=[.!?])\s+/)) {
    const lower = sentence.toLowerCase();
    for (const kw of DEFECT_KEYWORDS) {
      const idx = lower.indexOf(kw);
      if (idx === -1) continue;
      const before = lower.slice(Math.max(0, idx - 30), idx);
      if (NEGATOR_BEFORE_RE.test(before)) continue;
      defects.push(sentence.trim());
      break;
    }
  }

  if (defects.length > 0) return { verdict: "fail", defects: defects.slice(0, 5) };
  return { verdict: "pass", defects: [] };
}

async function analyzeRoute(entry) {
  const dir = entry.directory;
  const viewportResult = await analyzeScreenshot(path.join(dir, "viewport.png"));
  const stateResults = {};
  if (entry.stateScreenshots) {
    for (const [state, screenshotPath] of Object.entries(entry.stateScreenshots)) {
      stateResults[state] = await analyzeScreenshot(screenshotPath);
    }
  }
  const annotate = (result) => ({
    ...result,
    ...(result.description
      ? parseVisionVerdict(result.description)
      : { verdict: null, defects: [] }),
  });
  return {
    route: entry.route,
    viewport: annotate(viewportResult),
    states: Object.fromEntries(
      Object.entries(stateResults).map(([k, v]) => [k, annotate(v)]),
    ),
    deterministicFindings: entry.deterministicFindings || [],
    analyzedAt: new Date().toISOString(),
  };
}

function mapDefectToGap(defectText) {
  const text = defectText.toLowerCase();
  for (const entry of DEFECT_MAP) {
    if (entry.keywords.some((kw) => text.includes(kw))) {
      return { issue: entry.issue, severity: entry.severity, evidence: [defectText] };
    }
  }
  return { issue: "Other visual defect", severity: "warning", evidence: [defectText] };
}

function gapId(route, issue) {
  const slug = ISSUE_SLUGS[issue] || "other";
  return `${route}::${slug}`;
}

/** Build the merged gap list for one route from vision verdicts + deterministic findings. */
function deriveGaps(analysis) {
  const byIssue = new Map();

  const addGap = (issue, severity, source, evidence) => {
    const existing = byIssue.get(issue);
    if (existing) {
      existing.sources.add(source);
      existing.evidence.push(...evidence);
      if (severity === "error") existing.severity = "error";
    } else {
      byIssue.set(issue, { issue, severity, sources: new Set([source]), evidence: [...evidence] });
    }
  };

  const visionResults = [analysis.viewport, ...Object.values(analysis.states)];
  for (const result of visionResults) {
    if (!result || !result.defects) continue;
    for (const defect of result.defects) {
      const gap = mapDefectToGap(defect);
      addGap(gap.issue, gap.severity, "vision", gap.evidence);
    }
  }

  for (const finding of analysis.deterministicFindings) {
    const detail = `[${finding.check}] ${finding.detail}`;
    addGap(finding.issue, finding.severity, "deterministic", [detail]);
  }

  return Array.from(byIssue.values()).map((g) => ({
    id: gapId(analysis.route, g.issue),
    issue: g.issue,
    severity: g.severity,
    source: Array.from(g.sources).sort().join("+"),
    evidence: g.evidence.slice(0, 6),
    suggestedFix: FIX_GUIDANCE[g.issue] || FIX_GUIDANCE["Other visual defect"],
  }));
}

function loadWaivers() {
  if (!existsSync(WAIVERS_PATH)) return {};
  try {
    return JSON.parse(readFileSync(WAIVERS_PATH, "utf-8")).waivers || {};
  } catch {
    return {};
  }
}

function saveWaivers(waivers) {
  ensure(OUTPUT_DIR);
  writeFileSync(WAIVERS_PATH, `${JSON.stringify({ waivers }, null, 2)}\n`, "utf-8");
}

async function buildReport(entries, waivers) {
  const allGaps = [];
  const routeAnalyses = [];
  const waiversApplied = [];
  let visionParseFailures = 0;
  let visionErrors = 0;

  for (const entry of entries) {
    const analysis = await analyzeRoute(entry);
    let gaps = deriveGaps(analysis);

    for (const gap of gaps) {
      const waiver = waivers[gap.id];
      if (waiver) {
        waiversApplied.push({ id: gap.id, reason: waiver.reason });
      }
    }
    gaps = gaps.filter((g) => !waivers[g.id]);

    if (analysis.viewport.verdict === null && !analysis.viewport.error) visionParseFailures += 1;
    if (analysis.viewport.error) visionErrors += 1;

    if (gaps.length > 0) {
      allGaps.push({ route: entry.route, gaps });
    }
    routeAnalyses.push({ ...analysis, gaps });
  }

  return {
    schemaVersion: 2,
    generatedAt: new Date().toISOString(),
    routesAnalyzed: entries.length,
    totalUiGapsFound: allGaps.reduce((n, r) => n + r.gaps.length, 0),
    note: "Cosmetic-only fixes. Never change functionality or business logic. Deterministic gaps are DOM-measured and authoritative; vision gaps are advisory.",
    summary: {
      error: allGaps.filter((r) => r.gaps.some((g) => g.severity === "error")).length,
      warning: allGaps.filter((r) => r.gaps.some((g) => g.severity === "warning")).length,
      info: allGaps.filter((r) => r.gaps.some((g) => g.severity === "info")).length,
    },
    waiversApplied,
    vision: { parseFailures: visionParseFailures, errors: visionErrors },
    allGapsByRoute: allGaps,
    routes: routeAnalyses,
    designSystem: {
      colors: "src/constants/colors.ts + tailwind.config.js — wood/amber/cream tokens",
      typography: "PlayfairDisplay (headings), DMSans (body), JetBrainsMono (mono)",
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

function previousGapIds() {
  if (!existsSync(REPORT_PATH)) return new Set();
  try {
    const prev = JSON.parse(readFileSync(REPORT_PATH, "utf-8"));
    return new Set(
      (prev.allGapsByRoute || []).flatMap((r) => (r.gaps || []).map((g) => g.id)),
    );
  } catch {
    return new Set();
  }
}

function handleWaiveFlag() {
  const argv = process.argv.slice(2);
  const waiveIdx = argv.indexOf("--waive");
  if (waiveIdx === -1) return false;
  const target = argv[waiveIdx + 1];
  const reasonIdx = argv.indexOf("--reason");
  const reason = reasonIdx !== -1 ? argv[reasonIdx + 1] : "";
  if (!target || !reason) {
    console.error('[loop] --waive requires a gap id ("<route>::<gapId>") and --reason "<text>"');
    process.exit(1);
  }
  const waivers = loadWaivers();
  waivers[target] = { reason, waivedAt: new Date().toISOString() };
  saveWaivers(waivers);
  console.log(`[loop] Waived ${target}. Active waivers: ${Object.keys(waivers).length}`);
  process.exit(0);
}

async function run() {
  handleWaiveFlag();

  const isVerify = args.has("--verify");
  const isAnalyzeOnly = args.has("--analyze-only");
  const skipServer = args.has("--skip-server");
  const wantHelp = args.has("--help") || args.has("-h");

  if (wantHelp) {
    console.log(`UX Improvement Loop — Orchestrator

Usage:
  npm run ux:improve                      Fresh capture + deterministic checks + vision analysis
  npm run ux:verify                       Post-fix verification: fresh capture + full analysis
  node scripts/audit/ux-improve-loop.mjs --analyze-only   Re-analyze existing screenshots (no capture)
  node scripts/audit/ux-improve-loop.mjs --waive "<route>::<gapId>" --reason "..."  Persist a waiver
  npm run ux:improve -- --skip-server     Skip web server check (attach to running one)

Gap ids: "<route>::<slug>" where slug is one of:
  ${Object.values(ISSUE_SLUGS).join(", ")}

Prerequisites:
  - Expo web server running on http://127.0.0.1:8081
    (run \`npm run web\` in another terminal, or let Playwright auto-start it)

Output:
  docs/audit/ui-feedback-report.json  — gap report (schema v2)
  docs/audit/ux-improve-state.json    — loop iteration state
  docs/audit/ux-waivers.json          — persisted waivers
`);
    process.exit(0);
  }

  ensure(OUTPUT_DIR);

  // Clear vision-tool backend memory before fresh capture+analysis (not on re-analysis)
  if (!isAnalyzeOnly) {
    try {
      execSync(
        `${pythonCmd()} -c "import os; f='/home/kunda/vision-tool/backend_memory.json'; os.path.exists(f) and os.remove(f)"`,
        { encoding: "utf-8", timeout: 15000 },
      );
      console.log("[loop] Cleared vision-tool backend memory.");
    } catch {}
  }

  if (!isAnalyzeOnly) {
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
    console.error("[loop] No capture manifest found. Run without --analyze-only first.");
    process.exit(1);
  }

  const entries = JSON.parse(readFileSync(CAPTURE_MANIFEST, "utf-8"));

  // Orphaned vision_proxy processes from a previous timed-out run keep
  // burning CPU inside WSL — killing wsl.exe does not kill the Linux-side
  // process, and orphans starve every subsequent moondream call.
  try {
    execSync(
      `${pythonCmd()} -c "import subprocess; subprocess.run(['pkill', '-f', 'vision_proxy.py'])"`,
      { encoding: "utf-8", timeout: 15000 },
    );
    console.log("[loop] Cleared stale vision-proxy processes.");
  } catch {}

  const waivers = loadWaivers();
  const prevGapIds = previousGapIds();
  const report = await buildReport(entries, waivers);
  const reportPath = writeReport(report);

  const currentGapIds = new Set(
    report.allGapsByRoute.flatMap((r) => r.gaps.map((g) => g.id)),
  );
  const resolvedGapIds = Array.from(prevGapIds).filter((id) => !currentGapIds.has(id));
  const newGapIds = Array.from(currentGapIds).filter((id) => !prevGapIds.has(id));

  const state = loadState();
  state.iteration += 1;
  state.lastReportPath = reportPath;
  state.resolvedGapIds = resolvedGapIds;
  state.newGapIds = newGapIds;
  state.remainingGapIds = Array.from(currentGapIds);

  const errorRoutes = report.allGapsByRoute.filter((r) => r.gaps.some((g) => g.severity === "error"));
  const warningRoutes = report.allGapsByRoute.filter(
    (r) => !errorRoutes.includes(r) && r.gaps.some((g) => g.severity === "warning"),
  );

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
    vision: report.vision,
    waiversApplied: report.waiversApplied,
    resolvedGapIds,
    newGapIds,
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

// Guarded so tests can import the parser without triggering a loop run.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  run().catch((err) => {
    console.error("[loop] Fatal error:", err.message);
    process.exit(1);
  });
}

export { parseVisionVerdict, deriveGaps, gapId, VISION_PROMPT };
