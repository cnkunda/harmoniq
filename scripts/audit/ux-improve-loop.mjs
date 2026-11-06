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
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
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
const GUARD_REPORT_PATH = path.join(OUTPUT_DIR, "ux-guard-report.json");

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
  "Purple gradient": "purple-gradient",
  "Excessive padding": "excessive-padding",
  "Floating elements": "floating-element",
  "Keyboard overlap": "keyboard-overlap",
  "Tap target too small": "small-tap-target",
  "Missing caching": "missing-caching",
  "Text too small": "tiny-text",
  "Double activation": "double-activation",
  "Empty screen": "empty-screen",
  "Text scaling breakage": "text-scaling",
  "Raw error text": "raw-error-text",
  "Missing tap feedback": "tap-feedback",
  "Preferences not persisted": "preferences-wiped",
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
  "Purple gradient": {
    approach: "Replace the off-palette purple gradient with a wood/amber token from the palette.",
    allowed: "color tokens from src/constants/colors.ts only",
  },
  "Excessive padding": {
    approach: "Reduce the oversized padding to the app's spacing scale (p-4/p-6), keeping the layout intact.",
    allowed: "spacing props only",
  },
  "Floating elements": {
    approach: "Anchor the detached fixed element (edge alignment) or convert it into normal flow content.",
    allowed: "layout/positioning props only",
  },
  "Keyboard overlap": {
    approach: "Put the form inside a scrollable container or replace the fixed height with flex so the focused input can scroll above the keyboard.",
    allowed: "layout props only",
  },
  "Tap target too small": {
    approach: "Increase the control's hit area to at least 28px with padding; keep the visual size if it must stay compact.",
    allowed: "padding/size props only",
  },
  "Missing caching": {
    approach: "Cache the repeated request (React Query/SWR or a module-level memo). This is usually a functional change — log it if so.",
    allowed: "styling only; caching is functional",
  },
  "Text too small": {
    approach: "Bump long body copy from 9-11px to text-xs/text-sm; short mono labels may stay small.",
    allowed: "font-size class swap only",
  },
  "Double activation": {
    approach: "Remove the nested interactive wrapper so one tap fires one handler (e.g. move the child button outside the pressable card).",
    allowed: "structure/cosmetic; report if behavior would change",
  },
  "Empty screen": {
    approach: "Add an empty-state message/illustration or fix the render path that leaves the screen bare.",
    allowed: "cosmetic only; report if data is missing",
  },
  "Text scaling breakage": {
    approach: "Replace fixed heights/overflow-hidden on text containers with flex and min-height so text can grow.",
    allowed: "layout props only",
  },
  "Raw error text": {
    approach: "Replace the raw exception copy with a friendly message and keep the technical detail in console logging.",
    allowed: "copy/UI text only; no logic changes",
  },
  "Missing tap feedback": {
    approach: "Use AnimatedPressable from components/AnimatedPressable.tsx (scale spring on press) instead of a bare Pressable.",
    allowed: "component swap only",
  },
  "Preferences not persisted": {
    approach: "Stop clearing storage on mount/migration; preserve existing keys. Usually functional — log if so.",
    allowed: "styling only; persistence is functional",
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
  // UX_AUDIT_ROUTE_GREP narrows the run to matching routes (test title
  // contains "capture route artifacts: <route>"). A superset is captured —
  // Playwright --grep is substring matching — which only costs time, never
  // correctness, for the guard.
  const grep = process.env.UX_AUDIT_ROUTE_GREP || "";
  const grepArgs = grep ? ` --grep "${grep.replace(/"/g, "")}"` : "";
  execSync(`npx playwright test --config=playwright.config.ts tests/ui/route-capture.spec.ts${grepArgs}`, {
    cwd: ROOT_DIR,
    stdio: "inherit",
    // 30min: the 30-route serial crawl takes ~17min on a loaded machine
    // (AlphaTab mounts + onboarding audio), so a 10min ceiling killed the
    // loop mid-capture and orphaned Playwright.
    timeout: 1_800_000,
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

  const flatGaps = allGaps.flatMap((r) => r.gaps);
  return {
    schemaVersion: 2,
    generatedAt: new Date().toISOString(),
    routesAnalyzed: entries.length,
    totalUiGapsFound: flatGaps.length,
    note: "Cosmetic-only fixes. Never change functionality or business logic. Deterministic gaps are DOM-measured and authoritative; vision gaps are advisory.",
    summary: {
      error: flatGaps.filter((g) => g.severity === "error").length,
      warning: flatGaps.filter((g) => g.severity === "warning").length,
      info: flatGaps.filter((g) => g.severity === "info").length,
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

// ---- Pre-commit guard (changed routes only, deterministic checks, no vision) ----

function knownRoutePaths() {
  const src = readFileSync(path.join(ROOT_DIR, "tests", "routes.ts"), "utf-8");
  const paths = new Set();
  for (const m of src.matchAll(/path:\s*"([^"]+)"/g)) paths.add(m[1]);
  // Mirror tests/routes.ts FS discovery: auto routes exist for every screen
  // file, minus dynamic segments and framework files.
  const appDir = path.join(ROOT_DIR, "app");
  const walkApp = (dir, rel) => {
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (e.isDirectory()) { walkApp(path.join(dir, e.name), [...rel, e.name]); continue; }
      if (!/\.(tsx|ts)$/.test(e.name)) continue;
      const base = e.name.replace(/\.(tsx|ts)$/, "");
      if (/^_/.test(base) || /^\+/.test(base) || base.endsWith(".d")) continue;
      const segments = rel
        .filter((s) => !s.startsWith("("))
        .filter((s) => !s.startsWith("["));
      if (base === "index") {
        paths.add(segments.length ? `/${segments.join("/")}` : "/");
      } else {
        paths.add(`/${[...segments, base].join("/")}`);
      }
    }
  };
  walkApp(appDir, []);
  return Array.from(paths);
}

/** Map an app/ screen file to the concrete crawl routes that render it. */
function appFileToRouteCandidates(absFile) {
  const appDir = path.join(ROOT_DIR, "app");
  if (!absFile.startsWith(appDir + path.sep)) return [];
  const base = path.basename(absFile);
  if (/^_layout\.|^_template\.|^\+html\.|^\+api\.|^\+not-found\.|^\+error-boundary\./.test(base)) return [];
  let rel = absFile.slice(appDir.length + 1).split(path.sep).join("/");
  rel = rel.replace(/\.(tsx|ts|jsx|js)$/, "");
  const isIndex = rel.endsWith("/index") || rel === "index";
  const segments = (isIndex ? rel.split("/").slice(0, -1) : rel.split("/"))
    .filter((s) => s && !s.startsWith("("));
  return knownRoutePaths().filter((routePath) => {
    const rs = routePath.replace(/^\//, "").split("/").filter(Boolean);
    if (rs.length !== segments.length) return false;
    if (rs.length === 0) return segments.length === 0;
    return rs.every((seg, i) => seg === segments[i] || segments[i].startsWith("["));
  });
}

/**
 * Map changed source files to crawl routes. app/ screen files map directly;
 * shared component/module files map via app/ screens that reference them.
 * Returns null when changes are broad or unidentifiable (→ check all routes).
 */
function changedRouteSet() {
  let files;
  try {
    files = execSync("git diff --name-only HEAD", { cwd: ROOT_DIR, encoding: "utf-8" })
      .split(/\r?\n/).filter(Boolean);
  } catch {
    return null;
  }
  const codeFiles = files.filter((f) => /\.(tsx?|jsx?)$/.test(f) && !/^tests\//.test(f));
  if (codeFiles.length === 0) return { routes: [], broad: false };

  const appDir = path.join(ROOT_DIR, "app");
  const allScreens = [];
  const walkApp = (dir) => {
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walkApp(p);
      else if (/\.(tsx|ts)$/.test(e.name)) allScreens.push(p);
    }
  };
  walkApp(appDir);
  const screenTexts = new Map(allScreens.map((f) => [f, readFileSync(f, "utf-8")]));

  const routes = new Set();
  let unmapped = false;
  for (const rel of codeFiles) {
    const abs = path.resolve(ROOT_DIR, rel);
    const direct = appFileToRouteCandidates(abs);
    if (direct.length > 0) {
      for (const r of direct) routes.add(r);
      continue;
    }
    if (abs.startsWith(appDir + path.sep)) continue; // non-route app file (layouts etc.)
    const base = path.basename(abs).replace(/\.(tsx|ts)$/, "");
    if (!/^[A-Za-z][A-Za-z0-9]+$/.test(base)) { unmapped = true; break; }
    let referenced = false;
    for (const [screen, text] of screenTexts) {
      if (new RegExp(`\\b${base}\\b`).test(text)) {
        referenced = true;
        for (const r of appFileToRouteCandidates(screen)) routes.add(r);
      }
    }
    if (!referenced) { unmapped = true; break; }
  }
  if (unmapped) return null;
  return { routes: Array.from(routes), broad: false };
}

/** Pre-commit guard: checks-only for the routes affected by the working tree. */
async function guardRun() {
  const selection = changedRouteSet();
  if (selection === null) {
    console.log("[guard] Broad or unresolvable change — checking all routes.");
    process.env.UX_AUDIT_ROUTE_GREP = "";
  } else if (selection.routes.length === 0) {
    console.log("[guard] No routes affected by the current changes — nothing to check.");
    process.exit(0);
  } else {
    const pattern = `(${selection.routes.map((r) => r.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`;
    process.env.UX_AUDIT_ROUTE_GREP = `capture route artifacts: ${pattern}`;
    console.log(`[guard] Routes affected by the current changes: ${selection.routes.join(", ")}`);
  }

  const hadManifest = existsSync(CAPTURE_MANIFEST);
  const manifestBackup = hadManifest ? readFileSync(CAPTURE_MANIFEST, "utf-8") : null;
  const summary = { status: "clean", routesAnalyzed: 0, totalGaps: 0, gaps: [], reportPath: GUARD_REPORT_PATH };
  let failMessage = null;
  let exitCode = 0;
  try {
    runPlaywrightCapture();
    if (!existsSync(CAPTURE_MANIFEST)) throw new Error("capture produced no manifest");
    const entries = JSON.parse(readFileSync(CAPTURE_MANIFEST, "utf-8"));

    const waivers = loadWaivers();
    const allGaps = [];
    const routeAnalyses = [];
    for (const entry of entries) {
      const analysis = {
        route: entry.route,
        viewport: null,
        states: {},
        deterministicFindings: entry.deterministicFindings || [],
        analyzedAt: new Date().toISOString(),
        visionSkipped: true,
      };
      const gaps = deriveGaps(analysis).filter((g) => !waivers[g.id]);
      if (gaps.length > 0) allGaps.push({ route: entry.route, gaps });
      routeAnalyses.push({ route: entry.route, gaps, deterministicFindings: analysis.deterministicFindings });
    }

    const report = {
      schemaVersion: 2,
      mode: "guard",
      generatedAt: new Date().toISOString(),
      routesAnalyzed: entries.length,
      totalUiGapsFound: allGaps.flatMap((r) => r.gaps).length,
      note: "Pre-commit guard: deterministic DOM checks only (no vision analysis). Full-loop results live in ui-feedback-report.json.",
      allGapsByRoute: allGaps,
      routes: routeAnalyses,
    };
    ensure(OUTPUT_DIR);
    writeFileSync(GUARD_REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`, "utf-8");

    summary.routesAnalyzed = entries.length;
    summary.totalGaps = report.totalUiGapsFound;
    summary.gaps = allGaps;
    if (report.totalUiGapsFound > 0) {
      summary.status = "needs_fixes";
      exitCode = 1;
    }
  } catch (err) {
    failMessage = err.message;
  } finally {
    // A guard capture rewrites the shared manifest with only the guarded routes —
    // restore the full-loop manifest so a later full run starts from the whole set.
    if (manifestBackup !== null) writeFileSync(CAPTURE_MANIFEST, manifestBackup, "utf-8");
  }
  if (failMessage) {
    console.error("[guard] Failed:", failMessage);
    process.exit(2);
  }
  console.log(JSON.stringify(summary, null, 2));
  process.exit(exitCode);
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

  const isGuard = args.has("--guard");
  if (isGuard) {
    await guardRun();
    return;
  }

  const isVerify = args.has("--verify");
  const isAnalyzeOnly = args.has("--analyze-only");
  const skipServer = args.has("--skip-server");
  const wantHelp = args.has("--help") || args.has("-h");

  if (wantHelp) {
    console.log(`UX Improvement Loop — Orchestrator

Usage:
  npm run ux:improve                      Fresh capture + deterministic checks + vision analysis
  npm run ux:verify                       Post-fix verification: fresh capture + full analysis
  npm run ux:guard                        Pre-commit guard: deterministic checks on changed routes only
                                          (maps "git diff" files to routes; broad changes check all routes)
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

  const currentGapIds = new Set(
    report.allGapsByRoute.flatMap((r) => r.gaps.map((g) => g.id)),
  );
  const resolvedGapIds = Array.from(prevGapIds).filter((id) => !currentGapIds.has(id));
  const newGapIds = Array.from(currentGapIds).filter((id) => !prevGapIds.has(id));

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

  // Persist completion in the report itself — agents and archival checks read
  // `isComplete` from ui-feedback-report.json (Commit 158 precedent).
  report.isComplete = isComplete;
  const reportPath = writeReport(report);

  const state = loadState();
  state.iteration += 1;
  state.lastReportPath = reportPath;
  state.resolvedGapIds = resolvedGapIds;
  state.newGapIds = newGapIds;
  state.remainingGapIds = Array.from(currentGapIds);
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

export { parseVisionVerdict, deriveGaps, gapId, VISION_PROMPT, knownRoutePaths, appFileToRouteCandidates, changedRouteSet };
