# Platform Audit Report

## Prioritized Issue List
### Critical — Oversized view modules increase regression risk and render churn
- Evidence: Found 7 files over 450 LOC, including `app/(tabs)/design-preview.tsx`, `app/(tabs)/jam.tsx`, `components/AlphaTabWeb.web.tsx`, `components/ListenStemPanel.tsx`
- Impact: Large files are difficult to test and optimize, and they hide expensive recompute paths behind broad state dependencies.
- Recommendation: Split each oversized screen into feature panels + hooks. Enforce a soft limit of 300 LOC per screen container file.

### High — Missing loading/empty/error state coverage across user journeys
- Evidence: 19 of 19 screens are missing one or more key states.
- Impact: Users encounter dead-ends or blank transitions under network latency and partial data scenarios, especially on mobile.
- Recommendation: Adopt a mandatory state contract (loading, empty, error, success) for every route-level screen with shared state components.

### High — Accessibility labels are inconsistent on interactive controls
- Evidence: Detected 10 files with interactive elements and no explicit accessibility labels, e.g. `app/session/review.tsx`, `app/onboarding/phrase/[index].tsx`, `app/(tabs)/analyze-debug.tsx`, `app/(tabs)/design-preview.tsx`
- Impact: Screen-reader navigation and automated accessibility checks cannot reliably identify intents for controls.
- Recommendation: Add `accessibilityLabel`, `accessibilityRole`, and `testID` conventions for all interactive primitives.

### Medium — Design tokens are not consistently centralized
- Evidence: 1 files contain >=6 direct hex values and 0 files contain >=6 inline font sizes.
- Impact: Visual consistency drifts over time, creating spacing/typography/color mismatches across platforms.
- Recommendation: Move color + typography to a typed token system and replace direct literals with semantic design tokens.

### Low — Component inventory still classifies many utility modules as screen-level components
- Evidence: Static categorization currently marks utility and test modules in `src/**` as screen-level due filename-based heuristics.
- Impact: Architecture metrics are directionally useful but not yet strict enough for governance gating.
- Recommendation: Improve inventory rules to classify hooks, stores, API modules, and tests separately from UI components.

## Concrete Refactor Suggestions

### 1) Route-state shell contract
```tsx
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
```

### 2) Accessibility-safe interactive primitive
```tsx
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
```

### 3) Stable virtualized list contract
```tsx
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
```

## Design System Recommendation
- Adopt a token package (`color`, `spacing`, `radius`, `typography`, `elevation`, `motion`) in `src/design-system/tokens.ts`.
- Add platform-safe primitives (`AppText`, `AppPressable`, `AppSurface`, `AppStack`) and deprecate direct style literals in screens.
- Establish component maturity levels: primitive -> composed -> screen container.
- Add visual regression baselines per primitive in Playwright visual snapshots.

## Component Standardization Plan
- Phase 1: normalize screen state handling with a single route-shell contract for loading/empty/error.
- Phase 2: replace direct `Pressable` usage with an accessibility-safe wrapper and minimum 44x44 touch targets.
- Phase 3: migrate repeated layout patterns (header, section block, CTA row) into shared composed components.
- Phase 4: enforce architecture boundaries: `app/` routes only orchestrate, feature logic in `src/features/`, primitives in `components/ui/`.
- Phase 5: add lint rules for inline hex colors, raw font sizes, and missing test IDs on interactive controls.
## CI Integration Checklist
- [x] Add `npm run test:ui` for structural route capture.
- [x] Add `npm run test:visual` for Playwright snapshot diffing.
- [x] Add `npm run test:mobile` for Detox Android smoke.
- [x] Persist Playwright traces/screenshots as workflow artifacts.
- [ ] Add a nightly mobile matrix (Android + iOS on macOS runner) for full Detox coverage.
- [ ] Add a failing quality gate when severity Critical findings are present in generated audit report.

## Audit Metadata
- Generated at: 2026-04-15T19:47:16.316Z
- Screens indexed: 19
- Components indexed: 155
- Component category split: screen-level=140, shared=11, ui-primitives=4
- Large files (>450 LOC): 7
- Interactive files without accessibility labels: 10

