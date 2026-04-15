import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT_DIR = process.cwd();
const APP_DIR = path.join(ROOT_DIR, "app");
const COMPONENTS_DIR = path.join(ROOT_DIR, "components");
const SRC_DIR = path.join(ROOT_DIR, "src");
const OUTPUT_DIR = path.join(ROOT_DIR, "docs", "audit");

const ROUTE_EXTENSIONS = new Set([".tsx", ".jsx", ".ts", ".js"]);
const REACT_NATIVE_PRIMITIVES = new Set([
  "ActivityIndicator",
  "Button",
  "FlatList",
  "Image",
  "Modal",
  "Pressable",
  "SafeAreaView",
  "ScrollView",
  "SectionList",
  "Switch",
  "Text",
  "TextInput",
  "TouchableOpacity",
  "View",
]);

function walkFiles(dirPath) {
  const output = [];
  const stack = [dirPath];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) {
      break;
    }
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
      } else if (entry.isFile() && ROUTE_EXTENSIONS.has(path.extname(entry.name))) {
        output.push(fullPath);
      }
    }
  }
  return output;
}

function toPosix(absolutePath) {
  return path.relative(ROOT_DIR, absolutePath).replaceAll("\\", "/");
}

function toRoute(absolutePath) {
  const relative = toPosix(absolutePath).replace(/^app\//, "").replace(path.extname(absolutePath), "");
  const parsedName = path.parse(relative).name;
  if (parsedName.startsWith("_") || parsedName.startsWith("+")) {
    return null;
  }
  const segments = relative
    .split("/")
    .filter(Boolean)
    .filter((segment) => !(segment.startsWith("(") && segment.endsWith(")")))
    .map((segment) => {
      if (segment === "index") {
        return "";
      }
      const dynamic = segment.match(/^\[(.+)\]$/);
      if (dynamic) {
        return `:${dynamic[1]}`;
      }
      return segment;
    })
    .filter(Boolean);
  return segments.length === 0 ? "/" : `/${segments.join("/")}`;
}

function extractJsxTags(code) {
  const tags = new Set();
  const regex = /<([A-Za-z][A-Za-z0-9_.]*)\b/g;
  for (const match of code.matchAll(regex)) {
    tags.add(match[1].split(".")[0]);
  }
  return Array.from(tags).sort((a, b) => a.localeCompare(b));
}

function hasState(code, state) {
  const normalized = code.toLowerCase();
  const tests = {
    loading:
      normalized.includes("loading") ||
      normalized.includes("activityindicator") ||
      normalized.includes("isloading"),
    empty:
      normalized.includes("empty") ||
      normalized.includes("no data") ||
      normalized.includes("nodata"),
    error:
      normalized.includes("error") ||
      normalized.includes("role=\"alert\"") ||
      normalized.includes("seterror"),
    modal: normalized.includes("modal") || normalized.includes("role=\"dialog\""),
  };
  return tests[state];
}

function inferComponentCategory(relativePath, usageCount) {
  const lower = relativePath.toLowerCase();
  if (lower.startsWith("app/")) {
    return "screen-level";
  }
  if (
    lower.includes("/ui/") ||
    lower.includes("/primitives/") ||
    /(button|input|card|badge|chip|icon|modal|sheet|text)\.tsx?$/.test(lower)
  ) {
    return "ui-primitives";
  }
  return usageCount > 1 ? "shared" : "screen-level";
}

function buildScreenInventory(screenPaths) {
  return screenPaths.map((screenAbsolutePath) => {
    const code = readFileSync(screenAbsolutePath, "utf-8");
    const tags = extractJsxTags(code);
    const primitiveElements = tags.filter((tag) => REACT_NATIVE_PRIMITIVES.has(tag));
    const customComponents = tags.filter((tag) => /^[A-Z]/.test(tag) && !REACT_NATIVE_PRIMITIVES.has(tag));
    const hasLoading = hasState(code, "loading");
    const hasEmpty = hasState(code, "empty");
    const hasError = hasState(code, "error");
    const hasModal = hasState(code, "modal");

    return {
      route: toRoute(screenAbsolutePath),
      screenPath: toPosix(screenAbsolutePath),
      visibleElements: tags,
      primitiveElements,
      customComponents,
      stateCoverage: {
        loading: hasLoading,
        empty: hasEmpty,
        error: hasError,
        modal: hasModal,
      },
      missingStates: ["loading", "empty", "error", "modal"].filter(
        (stateKey) =>
          !{
            loading: hasLoading,
            empty: hasEmpty,
            error: hasError,
            modal: hasModal,
          }[stateKey],
      ),
    };
  });
}

function buildComponentInventory(componentPaths, screenInventory) {
  const screenSources = screenInventory.map((screen) => ({
    route: screen.route,
    path: screen.screenPath,
    source: readFileSync(path.join(ROOT_DIR, screen.screenPath), "utf-8"),
  }));

  const components = componentPaths.map((componentAbsolutePath) => {
    const relativePath = toPosix(componentAbsolutePath);
    const componentName = path.parse(componentAbsolutePath).name;
    const usageScreens = screenSources
      .filter((screen) => screen.source.includes(`<${componentName}`))
      .map((screen) => ({ route: screen.route, screenPath: screen.path }));

    return {
      name: componentName,
      path: relativePath,
      usageCount: usageScreens.length,
      usedByScreens: usageScreens,
      category: inferComponentCategory(relativePath, usageScreens.length),
    };
  });

  const nameCounts = new Map();
  for (const component of components) {
    nameCounts.set(component.name, (nameCounts.get(component.name) ?? 0) + 1);
  }

  const duplicateComponentNames = Array.from(nameCounts.entries())
    .filter(([, count]) => count > 1)
    .map(([name]) => name)
    .sort((a, b) => a.localeCompare(b));

  const componentsByCategory = {
    "screen-level": components.filter((item) => item.category === "screen-level").length,
    shared: components.filter((item) => item.category === "shared").length,
    "ui-primitives": components.filter((item) => item.category === "ui-primitives").length,
  };

  return {
    generatedAt: new Date().toISOString(),
    totalComponents: components.length,
    duplicateComponentNames,
    componentsByCategory,
    components: components.sort((a, b) => a.path.localeCompare(b.path)),
  };
}

function ensureOutputDir() {
  mkdirSync(OUTPUT_DIR, { recursive: true });
}

function writeJson(filename, payload) {
  const outputPath = path.join(OUTPUT_DIR, filename);
  writeFileSync(outputPath, `${JSON.stringify(payload, null, 2)}\n`, "utf-8");
  return toPosix(outputPath);
}

function run() {
  ensureOutputDir();

  const screenPaths = walkFiles(APP_DIR).filter((screenPath) => toRoute(screenPath) !== null);
  const componentPaths = [...walkFiles(COMPONENTS_DIR), ...walkFiles(SRC_DIR)];

  const screenInventory = buildScreenInventory(screenPaths).sort((a, b) =>
    (a.route || "").localeCompare(b.route || ""),
  );
  const componentInventory = buildComponentInventory(componentPaths, screenInventory);
  const stateCoverage = {
    generatedAt: new Date().toISOString(),
    screens: screenInventory.map((screen) => ({
      route: screen.route,
      screenPath: screen.screenPath,
      stateCoverage: screen.stateCoverage,
      missingStates: screen.missingStates,
      customComponents: screen.customComponents,
      primitiveElements: screen.primitiveElements,
    })),
  };

  const screenPath = writeJson("screen-inventory.json", {
    generatedAt: new Date().toISOString(),
    totalScreens: screenInventory.length,
    screens: screenInventory,
  });
  const componentPath = writeJson("component-inventory.json", componentInventory);
  const statePath = writeJson("ui-state-coverage.json", stateCoverage);

  console.log(
    JSON.stringify(
      {
        status: "ok",
        outputs: [screenPath, componentPath, statePath],
      },
      null,
      2,
    ),
  );
}

run();

