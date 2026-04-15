import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT_DIR = process.cwd();
const OUTPUT_DIR = path.join(ROOT_DIR, "docs", "audit");
const SCREEN_INVENTORY_PATH = path.join(OUTPUT_DIR, "screen-inventory.json");
const COMPONENT_INVENTORY_PATH = path.join(OUTPUT_DIR, "component-inventory.json");
const REPORT_PATH = path.join(OUTPUT_DIR, "platform-audit.md");

const SCAN_DIRS = [path.join(ROOT_DIR, "app"), path.join(ROOT_DIR, "components"), path.join(ROOT_DIR, "src")];
const FILE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx"]);
const INTERACTIVE_TAG_REGEX = /<(Pressable|TouchableOpacity|TouchableHighlight|Button)\b/g;
const HEX_COLOR_REGEX = /#(?:[0-9a-fA-F]{3,8})\b/g;
const FONT_SIZE_REGEX = /fontSize\s*:\s*\d+/g;
const FLATLIST_REGEX = /<FlatList\b/g;
const KEY_EXTRACTOR_REGEX = /keyExtractor\s*=\s*\{/g;
const MEMOIZATION_HINT_REGEX = /\b(useMemo|useCallback|memo)\b/g;

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
      } else if (entry.isFile() && FILE_EXTENSIONS.has(path.extname(entry.name))) {
        output.push(fullPath);
      }
    }
  }
  return output;
}

function toPosix(relativePath) {
  return relativePath.replaceAll("\\", "/");
}

function relativePath(absolutePath) {
  return toPosix(path.relative(ROOT_DIR, absolutePath));
}

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, "utf-8"));
}

function countMatches(content, regex) {
  const matches = content.match(regex);
  return matches ? matches.length : 0;
}

function collectCodeHealthSignals() {
  const allFiles = SCAN_DIRS.flatMap((scanDir) => walkFiles(scanDir));
  const fileSignals = [];

  for (const filePath of allFiles) {
    const source = readFileSync(filePath, "utf-8");
    const lines = source.split(/\r?\n/).length;
    const interactiveCount = countMatches(source, INTERACTIVE_TAG_REGEX);
    const hasAccessibilityLabel = source.includes("accessibilityLabel=");
    const flatListCount = countMatches(source, FLATLIST_REGEX);
    const hasKeyExtractor = KEY_EXTRACTOR_REGEX.test(source);
    const colorTokens = new Set(source.match(HEX_COLOR_REGEX) || []);
    const fontSizes = countMatches(source, FONT_SIZE_REGEX);
    const memoizationHints = countMatches(source, MEMOIZATION_HINT_REGEX);

    fileSignals.push({
      filePath: relativePath(filePath),
      lines,
      interactiveCount,
      hasAccessibilityLabel,
      flatListCount,
      hasKeyExtractor,
      colorTokenCount: colorTokens.size,
      fontSizes,
      memoizationHints,
    });
  }

  return fileSignals;
}

function severityBucket(signalSummary, stateCoverageSummary) {
  const issues = [];

  if (signalSummary.largeComponentFiles.length > 0) {
    issues.push({
      severity: "Critical",
      title: "Oversized view modules increase regression risk and render churn",
      evidence:
        `Found ${signalSummary.largeComponentFiles.length} files over 450 LOC, including ` +
        signalSummary.largeComponentFiles.slice(0, 4).map((item) => `\`${item.filePath}\``).join(", "),
      impact:
        "Large files are difficult to test and optimize, and they hide expensive recompute paths behind broad state dependencies.",
      recommendation:
        "Split each oversized screen into feature panels + hooks. Enforce a soft limit of 300 LOC per screen container file.",
    });
  }

  if (stateCoverageSummary.screensMissingAnyState > 0) {
    issues.push({
      severity: "High",
      title: "Missing loading/empty/error state coverage across user journeys",
      evidence: `${stateCoverageSummary.screensMissingAnyState} of ${stateCoverageSummary.totalScreens} screens are missing one or more key states.`,
      impact:
        "Users encounter dead-ends or blank transitions under network latency and partial data scenarios, especially on mobile.",
      recommendation:
        "Adopt a mandatory state contract (loading, empty, error, success) for every route-level screen with shared state components.",
    });
  }

  if (signalSummary.filesWithInteractionsNoA11y.length > 0) {
    issues.push({
      severity: "High",
      title: "Accessibility labels are inconsistent on interactive controls",
      evidence:
        `Detected ${signalSummary.filesWithInteractionsNoA11y.length} files with interactive elements and no explicit accessibility labels, e.g. ` +
        signalSummary.filesWithInteractionsNoA11y.slice(0, 4).map((item) => `\`${item.filePath}\``).join(", "),
      impact: "Screen-reader navigation and automated accessibility checks cannot reliably identify intents for controls.",
      recommendation:
        "Add `accessibilityLabel`, `accessibilityRole`, and `testID` conventions for all interactive primitives.",
    });
  }

  if (signalSummary.flatListsMissingKeyExtractor.length > 0) {
    issues.push({
      severity: "Medium",
      title: "FlatList usage without explicit keyExtractor risks unstable list virtualization",
      evidence:
        `Detected ${signalSummary.flatListsMissingKeyExtractor.length} files using FlatList without keyExtractor, including ` +
        signalSummary.flatListsMissingKeyExtractor.slice(0, 3).map((item) => `\`${item.filePath}\``).join(", "),
      impact: "Unstable list keys increase re-renders and may corrupt item state during incremental updates.",
      recommendation: "Require `keyExtractor` and extract memoized `renderItem` callbacks for all list components.",
    });
  }

  if (signalSummary.highColorTokenFiles.length > 0 || signalSummary.highTypographyVariationFiles.length > 0) {
    issues.push({
      severity: "Medium",
      title: "Design tokens are not consistently centralized",
      evidence:
        `${signalSummary.highColorTokenFiles.length} files contain >=6 direct hex values and ${signalSummary.highTypographyVariationFiles.length} files contain >=6 inline font sizes.`,
      impact: "Visual consistency drifts over time, creating spacing/typography/color mismatches across platforms.",
      recommendation:
        "Move color + typography to a typed token system and replace direct literals with semantic design tokens.",
    });
  }

  issues.push({
    severity: "Low",
    title: "Component inventory still classifies many utility modules as screen-level components",
    evidence:
      "Static categorization currently marks utility and test modules in `src/**` as screen-level due filename-based heuristics.",
    impact: "Architecture metrics are directionally useful but not yet strict enough for governance gating.",
    recommendation:
      "Improve inventory rules to classify hooks, stores, API modules, and tests separately from UI components.",
  });

  return issues;
}

function markdownIssue(issue) {
  return [
    `### ${issue.severity} — ${issue.title}`,
    `- Evidence: ${issue.evidence}`,
    `- Impact: ${issue.impact}`,
    `- Recommendation: ${issue.recommendation}`,
    "",
  ].join("\n");
}

function buildRefactorExamples() {
  return `## Concrete Refactor Suggestions

### 1) Route-state shell contract
\`\`\`tsx
// components/screen/ScreenStateShell.tsx
type ScreenState = "loading" | "empty" | "error" | "ready";

export function ScreenStateShell(props: {
  state: ScreenState;
  loading: React.ReactNode;
  empty: React.ReactNode;
  error: React.ReactNode;
  children: React.ReactNode;
}) {
  if (props.state === "loading") return <>{props.loading}</>;
  if (props.state === "empty") return <>{props.empty}</>;
  if (props.state === "error") return <>{props.error}</>;
  return <>{props.children}</>;
}
\`\`\`

### 2) Accessibility-safe interactive primitive
\`\`\`tsx
// components/ui/AppPressable.tsx
import { Pressable, type PressableProps } from "react-native";

type AppPressableProps = PressableProps & {
  label: string;
  testID: string;
};

export function AppPressable({ label, testID, ...props }: AppPressableProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      testID={testID}
      hitSlop={8}
      {...props}
    />
  );
}
\`\`\`

### 3) Stable virtualized list contract
\`\`\`tsx
const renderItem = useCallback(({ item }: { item: Song }) => {
  return <SongRow song={item} />;
}, []);

<FlatList
  data={songs}
  keyExtractor={(item) => item.id}
  renderItem={renderItem}
  initialNumToRender={8}
  windowSize={7}
/>;
\`\`\`
`;
}

function buildReport() {
  const screenInventory = readJson(SCREEN_INVENTORY_PATH);
  const componentInventory = readJson(COMPONENT_INVENTORY_PATH);
  const codeSignals = collectCodeHealthSignals();

  const signalSummary = {
    largeComponentFiles: codeSignals.filter((signal) => signal.lines >= 450),
    filesWithInteractionsNoA11y: codeSignals.filter(
      (signal) => signal.interactiveCount > 0 && !signal.hasAccessibilityLabel,
    ),
    flatListsMissingKeyExtractor: codeSignals.filter(
      (signal) => signal.flatListCount > 0 && !signal.hasKeyExtractor,
    ),
    highColorTokenFiles: codeSignals.filter((signal) => signal.colorTokenCount >= 6),
    highTypographyVariationFiles: codeSignals.filter((signal) => signal.fontSizes >= 6),
  };

  const stateCoverageSummary = {
    totalScreens: screenInventory.totalScreens,
    screensMissingAnyState: screenInventory.screens.filter((screen) => screen.missingStates.length > 0).length,
  };

  const issues = severityBucket(signalSummary, stateCoverageSummary);

  const issueSection = issues.map(markdownIssue).join("\n");
  const designSystemSection =
    "## Design System Recommendation\n" +
    "- Adopt a token package (`color`, `spacing`, `radius`, `typography`, `elevation`, `motion`) in `src/design-system/tokens.ts`.\n" +
    "- Add platform-safe primitives (`AppText`, `AppPressable`, `AppSurface`, `AppStack`) and deprecate direct style literals in screens.\n" +
    "- Establish component maturity levels: primitive -> composed -> screen container.\n" +
    "- Add visual regression baselines per primitive in Playwright visual snapshots.\n";

  const standardizationSection =
    "## Component Standardization Plan\n" +
    "- Phase 1: normalize screen state handling with a single route-shell contract for loading/empty/error.\n" +
    "- Phase 2: replace direct `Pressable` usage with an accessibility-safe wrapper and minimum 44x44 touch targets.\n" +
    "- Phase 3: migrate repeated layout patterns (header, section block, CTA row) into shared composed components.\n" +
    "- Phase 4: enforce architecture boundaries: `app/` routes only orchestrate, feature logic in `src/features/`, primitives in `components/ui/`.\n" +
    "- Phase 5: add lint rules for inline hex colors, raw font sizes, and missing test IDs on interactive controls.\n";

  const ciChecklistSection = `## CI Integration Checklist\n- [x] Add \`npm run test:ui\` for structural route capture.\n- [x] Add \`npm run test:visual\` for Playwright snapshot diffing.\n- [x] Add \`npm run test:mobile\` for Detox Android smoke.\n- [x] Persist Playwright traces/screenshots as workflow artifacts.\n- [ ] Add a nightly mobile matrix (Android + iOS on macOS runner) for full Detox coverage.\n- [ ] Add a failing quality gate when severity Critical findings are present in generated audit report.\n`;

  const metadataSection = `## Audit Metadata\n- Generated at: ${new Date().toISOString()}\n- Screens indexed: ${screenInventory.totalScreens}\n- Components indexed: ${componentInventory.totalComponents}\n- Component category split: screen-level=${componentInventory.componentsByCategory["screen-level"]}, shared=${componentInventory.componentsByCategory.shared}, ui-primitives=${componentInventory.componentsByCategory["ui-primitives"]}\n- Large files (>450 LOC): ${signalSummary.largeComponentFiles.length}\n- Interactive files without accessibility labels: ${signalSummary.filesWithInteractionsNoA11y.length}\n`;

  return `# Platform Audit Report\n\n## Prioritized Issue List\n${issueSection}\n${buildRefactorExamples()}\n${designSystemSection}\n${standardizationSection}${ciChecklistSection}\n${metadataSection}\n`;
}

function run() {
  mkdirSync(OUTPUT_DIR, { recursive: true });
  const report = buildReport();
  writeFileSync(REPORT_PATH, report, "utf-8");
  console.log(
    JSON.stringify(
      {
        status: "ok",
        report: relativePath(REPORT_PATH),
      },
      null,
      2,
    ),
  );
}

run();

