import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Page, Request } from "@playwright/test";
import type { RouteDefinition, UiState } from "../../routes";
import { runVisualChecks, type DeterministicFinding } from "./visualChecks";

type CaptureResult = {
  route: string;
  directory: string;
  fullPageScreenshot: string;
  viewportScreenshot: string;
  stateScreenshots: Partial<Record<UiState, string>>;
  deterministicFindings: DeterministicFinding[];
};

// Static assets are expected to be re-requested only once; repeated dynamic
// GETs are the missing-cache signal.
const STATIC_ASSET_RE = /\.(js|css|png|jpe?g|gif|svg|webp|avif|woff2?|ttf|otf|mp3|wav|m4a|ico|map)(\?|$)/i;

function collectDuplicateRequests(counts: Map<string, number>): DeterministicFinding[] {
  const repeated: string[] = [];
  for (const [url, count] of counts) {
    if (count < 3) continue;
    let pathname = url;
    try {
      pathname = new URL(url).pathname;
    } catch {
      // keep the raw URL for non-absolute requests
    }
    repeated.push(`${pathname} ×${count}`);
  }
  if (repeated.length === 0) return [];
  return [
    {
      check: "duplicate-request",
      issue: "Missing caching",
      severity: "warning",
      detail: `The same GET is issued repeatedly during one load — e.g. ${repeated.slice(0, 3).join(", ")}`,
    },
  ];
}

/**
 * Press up to three visible controls with real pointer input and compare the
 * pressed-state computed styles. Only flags a route when *no* sampled control
 * shows any visual change (opacity/transform/background), i.e. tap feedback is
 * missing across the board — individual non-animated controls (segmented
 * toggles) are not flagged.
 */
async function probeTapFeedback(page: Page): Promise<DeterministicFinding[]> {
  const sampled = await page.evaluate(() => {
    const isInteractive = (el: Element): boolean => {
      const tag = el.tagName.toLowerCase();
      if (tag === "button" || tag === "a") return true;
      const role = el.getAttribute("role");
      return role === "button" || role === "link" || role === "tab";
    };
    return Array.from(document.querySelectorAll("button, a, [role=button], [role=link], [role=tab]"))
      .filter((el) => {
        // Bottom/top tab bars are platform navigation chrome — their feedback
        // is the active-state tint from the navigator, not a press spring.
        if (el.closest('[role="tablist"], nav')) return false;
        if (el.getAttribute("aria-disabled") === "true" || el.hasAttribute("disabled")) return false;
        const r = el.getBoundingClientRect();
        if (
          r.width < 40 ||
          r.height < 32 ||
          r.top < 0 ||
          r.left < 0 ||
          r.bottom > window.innerHeight ||
          (el.textContent || "").trim().length === 0
        ) {
          return false;
        }
        // The control must actually receive pointer events at its center —
        // otherwise the probe would measure whatever overlay sits on top.
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return hit !== null && (hit === el || el.contains(hit));
      })
      .slice(0, 3)
      .map((el, i) => {
        el.setAttribute("data-ux-probe", String(i));
        const r = el.getBoundingClientRect();
        return {
          i,
          x: r.left + r.width / 2,
          y: r.top + r.height / 2,
          name: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 20),
        };
      });
  });

  if (sampled.length < 2) return [];

  const signature = (index: number) =>
    page.evaluate((idx) => {
      const el = document.querySelector(`[data-ux-probe="${idx}"]`);
      if (!el) return "missing";
      const sig = (node: Element | null): string => {
        if (!node) return "";
        const cs = window.getComputedStyle(node);
        return `${cs.opacity}|${cs.transform}|${cs.backgroundColor}|${cs.filter}`;
      };
      const parts: string[] = [sig(el)];
      let parent: Element | null = el;
      for (let depth = 0; depth < 4 && parent; depth += 1) {
        parent = parent.parentElement;
        parts.push(sig(parent));
      }
      for (const child of Array.from(el.querySelectorAll("*")).slice(0, 30)) {
        parts.push(sig(child));
      }
      return parts.join("~");
    }, index);

  let changed = 0;
  for (const target of sampled) {
    const before = await signature(target.i);
    await page.mouse.move(target.x, target.y);
    await page.waitForTimeout(80);
    await page.mouse.down();
    await page.waitForTimeout(320);
    const during = await signature(target.i);
    // Cancel the press by releasing away from the control (no click fires).
    await page.mouse.move(target.x + 300, target.y + 300, { steps: 4 });
    await page.mouse.up();
    await page.waitForTimeout(120);
    if (before !== during) changed += 1;
  }

  if (changed > 0) return [];
  return [
    {
      check: "tap-feedback",
      issue: "Missing tap feedback",
      severity: "warning",
      detail: `None of ${sampled.length} sampled control(s) (${sampled.map((s) => `"${s.name}"`).join(", ")}) changed at all while pressed — taps give no visual feedback`,
    },
  ];
}

/**
 * Nested-interactive double-fire test. Nesting a control inside another
 * pressable is a legal pattern when the inner handler stops propagation
 * (e.g. a favorite button inside a selectable chip). Only flag pairs where a
 * real tap on the inner control also activates the outer one — detected as a
 * change in the outer element's state (class/aria) or a route change.
 */
async function probeDoubleActivation(page: Page): Promise<DeterministicFinding[]> {
  const pairs = await page.evaluate(() => {
    const isInteractive = (el: Element): boolean => {
      const tag = el.tagName.toLowerCase();
      if (tag === "button" || tag === "a") return true;
      const role = el.getAttribute("role");
      return role === "button" || role === "link" || role === "tab" || role === "switch" || role === "checkbox";
    };
    const out: { i: number; x: number; y: number; name: string }[] = [];
    for (const el of Array.from(document.querySelectorAll("button, a, [role=button], [role=link], [role=tab]"))) {
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) continue;
      let outer: Element | null = el.parentElement;
      let depth = 0;
      while (outer && depth < 6) {
        if (isInteractive(outer)) break;
        outer = outer.parentElement;
        depth += 1;
      }
      if (!outer || depth >= 6) continue;
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      if (!hit || (hit !== el && !el.contains(hit))) continue;
      const i = out.length;
      el.setAttribute("data-ux-inner", String(i));
      outer.setAttribute("data-ux-outer", String(i));
      out.push({
        i,
        x: r.left + r.width / 2,
        y: r.top + r.height / 2,
        name: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 20),
      });
      if (out.length >= 3) break;
    }
    return out;
  });

  if (pairs.length === 0) return [];

  const outerSignature = (index: number) =>
    page.evaluate((idx) => {
      const outer = document.querySelector(`[data-ux-outer="${idx}"]`);
      if (!outer) return `missing|${window.location.href}`;
      return [
        outer.getAttribute("class") || "",
        outer.getAttribute("aria-selected"),
        outer.getAttribute("aria-pressed"),
        outer.getAttribute("aria-expanded"),
        window.location.href,
      ].join("|");
    }, index);

  const confirmed: string[] = [];
  for (const pair of pairs) {
    const before = await outerSignature(pair.i);
    await page.mouse.click(pair.x, pair.y);
    await page.waitForTimeout(350);
    const after = await outerSignature(pair.i);
    if (before !== after) confirmed.push(pair.name);
  }

  if (confirmed.length === 0) return [];
  return [
    {
      check: "double-activation",
      issue: "Double activation",
      severity: "warning",
      detail: `Tapping the inner control also fired the outer action for: ${confirmed.join(", ")} — inner handler should stop propagation`,
    },
  ];
}

type PersistenceSnapshot = { counts: Record<string, number> };
async function readStoredCounts(page: Page): Promise<PersistenceSnapshot> {
  return page.evaluate(async () => {
    const counts: Record<string, number> = {};
    if (typeof indexedDB.databases !== "function") return { counts };
    const databases = await indexedDB.databases();
    for (const db of databases) {
      if (!db.name) continue;
      counts[db.name] = await new Promise<number>((resolve) => {
        const request = indexedDB.open(db.name as string);
        request.onerror = () => resolve(-1);
        request.onsuccess = () => {
          const connection = request.result;
          const stores = Array.from(connection.objectStoreNames);
          if (stores.length === 0) {
            connection.close();
            resolve(0);
            return;
          }
          let pending = stores.length;
          let total = 0;
          for (const store of stores) {
            const countRequest = connection.transaction(store, "readonly").objectStore(store).count();
            const done = () => {
              pending -= 1;
              if (pending === 0) {
                connection.close();
                resolve(total);
              }
            };
            countRequest.onsuccess = () => {
              total += countRequest.result;
              done();
            };
            countRequest.onerror = done;
          }
        };
      });
    }
    return { counts };
  });
}

/**
 * Reload the route and verify persisted records survive. Catches update paths
 * that clear storage on mount (preferences wiped on update).
 */
async function probePersistence(page: Page): Promise<DeterministicFinding[]> {
  const before = await readStoredCounts(page);
  const total = Object.values(before.counts).reduce((sum, n) => sum + Math.max(0, n), 0);
  if (total < 5) return [];

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(750);
  const after = await readStoredCounts(page);

  const lost = Object.keys(before.counts).filter(
    (name) => (after.counts[name] ?? 0) < before.counts[name],
  );
  if (lost.length === 0) return [];
  return [
    {
      check: "persistence",
      issue: "Preferences not persisted",
      severity: "warning",
      detail: `Stored records dropped after a reload (${lost.join(", ")}) — preferences may be wiped between updates`,
    },
  ];
}

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
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(750);
}

export async function captureRouteArtifacts(page: Page, route: RouteDefinition): Promise<CaptureResult> {
  const routePath = route.path;
  const outputDir = ensureRouteOutputDir(routePath);

  const requestCounts = new Map<string, number>();
  const onRequest = (request: Request): void => {
    if (request.method() !== "GET") return;
    const url = request.url();
    if (STATIC_ASSET_RE.test(url)) return;
    requestCounts.set(url, (requestCounts.get(url) ?? 0) + 1);
  };
  page.on("request", onRequest);

  let deterministicFindings: DeterministicFinding[] = [];
  let stateScreenshots: Partial<Record<UiState, string>> = {};
  let viewportScreenshot = "";
  let fullPageScreenshot = "";

  try {
    await page.goto(routePath, { waitUntil: "domcontentloaded" });
    await waitForPageReady(page);

    // Viewport is the authoritative capture; full-page is archival only.
    viewportScreenshot = path.join(outputDir, "viewport.png");
    await page.screenshot({ path: viewportScreenshot, fullPage: false });

    fullPageScreenshot = path.join(outputDir, "full-page.png");
    await page.screenshot({ path: fullPageScreenshot, fullPage: true });

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

    deterministicFindings = await runVisualChecks(page);
    deterministicFindings.push(...collectDuplicateRequests(requestCounts));
    deterministicFindings.push(...(await probeTapFeedback(page)));
    // Clicking probes: run after screenshots, before the persistence reload.
    deterministicFindings.push(...(await probeDoubleActivation(page)));
    // Reload-based: must run last, after all screenshots/checks are captured.
    deterministicFindings.push(...(await probePersistence(page)));
  } finally {
    page.off("request", onRequest);
  }

  return {
    route: routePath,
    directory: outputDir,
    fullPageScreenshot,
    viewportScreenshot,
    stateScreenshots,
    deterministicFindings,
  };
}

export function writeCaptureManifest(entries: CaptureResult[]): string {
  const outputPath = path.resolve(process.cwd(), "artifacts", "playwright", "route-capture-manifest.json");
  mkdirSync(path.dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, `${JSON.stringify(entries, null, 2)}\n`, "utf-8");
  return outputPath;
}

