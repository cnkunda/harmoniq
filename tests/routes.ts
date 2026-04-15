import { existsSync, readdirSync } from "node:fs";
import path from "node:path";

export type UiState = "loading" | "empty" | "error" | "modal";

export type RouteDefinition = {
  path: string;
  source: "auto" | "manual";
  enabled?: boolean;
  stateSelectors?: Partial<Record<UiState, string>>;
};

const ROUTE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx"]);
const EXCLUDED_FILES = new Set(["_layout", "+not-found", "+html"]);

const MANUAL_ROUTE_OVERRIDES: RouteDefinition[] = [
  { path: "/", source: "manual" },
  { path: "/library", source: "manual" },
  { path: "/progress", source: "manual" },
  { path: "/jam", source: "manual" },
  { path: "/settings", source: "manual" },
  { path: "/add-song", source: "manual" },
  { path: "/onboarding", source: "manual" },
  { path: "/onboarding/mic", source: "manual" },
  { path: "/onboarding/phrase/0", source: "manual", enabled: true },
  { path: "/onboarding/results", source: "manual" },
  { path: "/session/listen", source: "manual" },
  { path: "/session/study", source: "manual" },
  { path: "/session/slow", source: "manual" },
  { path: "/session/play", source: "manual" },
  { path: "/session/review", source: "manual" },
  {
    path: "/review-archive/demo-session",
    source: "manual",
    enabled: true,
  },
];

const DEFAULT_STATE_SELECTORS: Partial<Record<UiState, string>> = {
  loading: '[data-testid*="loading"], [aria-busy="true"]',
  empty: '[data-testid*="empty"], [data-testid*="no-data"]',
  error: '[data-testid*="error"], [role="alert"]',
  modal: '[data-testid*="modal"], [role="dialog"]',
};

function walkFiles(rootDir: string): string[] {
  const out: string[] = [];
  const stack = [rootDir];

  while (stack.length > 0) {
    const nextDir = stack.pop();
    if (!nextDir) {
      break;
    }
    for (const entry of readdirSync(nextDir, { withFileTypes: true })) {
      const fullPath = path.join(nextDir, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      const extension = path.extname(entry.name);
      if (!ROUTE_EXTENSIONS.has(extension)) {
        continue;
      }
      out.push(fullPath);
    }
  }

  return out;
}

function fileToRoute(filePath: string, appDir: string): string | null {
  const relative = path.relative(appDir, filePath).replaceAll("\\", "/");
  const parsed = path.parse(relative);
  if (EXCLUDED_FILES.has(parsed.name)) {
    return null;
  }

  const routeWithoutExtension = relative.replace(path.extname(relative), "");
  const segments = routeWithoutExtension
    .split("/")
    .filter((segment) => segment.length > 0)
    .filter((segment) => !segment.startsWith("_"))
    .filter((segment) => !(segment.startsWith("+") && segment.length > 1))
    .filter((segment) => !(segment.startsWith("(") && segment.endsWith(")")))
    .map((segment) => {
      if (segment === "index") {
        return "";
      }
      const catchAllMatch = segment.match(/^\[\.\.\.(.+)\]$/);
      if (catchAllMatch) {
        return `*${catchAllMatch[1]}`;
      }
      const dynamicMatch = segment.match(/^\[(.+)\]$/);
      if (dynamicMatch) {
        return `:${dynamicMatch[1]}`;
      }
      return segment;
    })
    .filter(Boolean);

  return segments.length === 0 ? "/" : `/${segments.join("/")}`;
}

function discoverExpoRoutesFromFs(appDir = "app"): RouteDefinition[] {
  const appRoot = path.resolve(process.cwd(), appDir);
  if (!existsSync(appRoot)) {
    return [];
  }

  const routes = new Set<string>();
  for (const filePath of walkFiles(appRoot)) {
    const route = fileToRoute(filePath, appRoot);
    if (!route) {
      continue;
    }
    routes.add(route);
  }

  return Array.from(routes)
    .sort((a, b) => a.localeCompare(b))
    .map((route) => ({ path: route, source: "auto" as const }));
}

export function loadRouteDefinitions(appDir = "app"): RouteDefinition[] {
  const autoRoutes = discoverExpoRoutesFromFs(appDir);
  const routeMap = new Map<string, RouteDefinition>();

  for (const autoRoute of autoRoutes) {
    const hasDynamicSegments = autoRoute.path.includes(":") || autoRoute.path.includes("*");
    routeMap.set(autoRoute.path, {
      ...autoRoute,
      enabled: !hasDynamicSegments,
      stateSelectors: DEFAULT_STATE_SELECTORS,
    });
  }

  for (const manualRoute of MANUAL_ROUTE_OVERRIDES) {
    const existing = routeMap.get(manualRoute.path);
    routeMap.set(manualRoute.path, {
      ...existing,
      ...manualRoute,
      enabled: manualRoute.enabled ?? existing?.enabled ?? true,
      stateSelectors: {
        ...DEFAULT_STATE_SELECTORS,
        ...existing?.stateSelectors,
        ...manualRoute.stateSelectors,
      },
    });
  }

  const includeDevRoutes = process.env.PLAYWRIGHT_INCLUDE_DEV_ROUTES === "1";
  const devRouteSegments = new Set(["/design-preview", "/analyze-debug"]);

  return Array.from(routeMap.values())
    .filter((route) => route.enabled !== false)
    .filter((route) => includeDevRoutes || !devRouteSegments.has(route.path))
    .sort((a, b) => a.path.localeCompare(b.path));
}

