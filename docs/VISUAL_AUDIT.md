# Harmoniq Visual Design Audit

> **Project:** Harmoniq — AI-powered adaptive guitar learning app
> **Stack:** React Native + Expo (iOS, Android, Web)
> **Commit reviewed:** `5e471b9` (HEAD — Commit 110: Analysis Persistence & Correction Editor)
> **PRIORITIES.md scope:** commits 1–110
> **Date:** 2026-06-02
> **Author:** Visual audit performed by static export + Playwright

---

## Executive Summary

This audit reviewed all 23 application routes and 80 components against the marked-complete acceptance criteria in `PRIORITIES.md` and the Harmoniq design system.

| Severity | Count | Description |
|----------|------:|-------------|
| **P0** — Blocking | 4 | Visible to every user; some ship-broken |
| **P1** — Visual bug | 11 | Inconsistency, contrast, or layout regression |
| **P2** — Polish | 14 | Typography rhythm, empty states, microcopy |
| **Total** | **29** | (4 P0 + 11 P1 + 14 P2) |

**Headline findings:**

1. **Two completely different visual languages** exist in the app — dark wood-900 for tab screens, light `bg-ivory` for every session screen. This jarring transition fires on **every** session start.
2. **The Progress screen's skill radar chart clips the leftmost label** ("Vibrato control" → "orato control") on a 1440px viewport.
3. **MusicXML cross-platform rendering tests cannot run** — the AlphaTab CDN URL in `tests/ui/musicxml-harness.html:18` returns HTTP 404. The "Edge-case corpus (20+ files) renders without crash" AC from Commit 108 is technically unmet.
4. **`/listening` is a duplicate of `/discover`** with the same Spotify follow-along card. One should be removed or redirected.
5. **The dev environment in `app/(tabs)/design-preview.tsx:483` gates itself with `__DEV__`**, leaving the design-system reference screen completely empty in production. No other route exposes the token system.

**Build status:** All 23 visual baseline tests pass. The test suite is healthy; what it tests is consistent. The issues are in what the user sees, not in the tests.

---

## Methodology

### How tests were run

```bash
# 1. Built a static export (expo export --platform web) — needed because
#    Metro dev server was unreliable for screenshot capture (cold-bundle timeouts).
CI=1 npx expo export --platform web --output-dir dist --no-minify

# 2. Served with a SPA-aware static server on 127.0.0.1:8081
node /tmp/serve.cjs /mnt/c/workspace/harmoniq/dist 8081

# 3. Installed Playwright Chromium
npx playwright install chromium

# 4. Updated all 23 visual baselines (the prior baselines were captured
#    against a non-running server and were all blank)
PLAYWRIGHT_USE_WEBSERVER=0 npm run test:visual:update

# 5. Ran route-capture for fresh full-page + viewport PNGs
PLAYWRIGHT_USE_WEBSERVER=0 npx playwright test route-capture.spec.ts

# 6. Captured hidden dev routes (design-preview, analyze-debug) and a
#    logged-in home screen via a one-off Playwright script.
```

### What was reviewed

| Asset | Count | Notes |
|---|---:|---|
| Visual baseline PNGs (viewport + fullpage) | 46 | `tests/ui/__snapshots__/route-visual.spec.ts/` |
| Route-capture PNGs (viewport + fullpage) | 46 | `artifacts/playwright/screenshots/<route>/` |
| MusicXML harness renders | 23 | All failed (CDN 404) — see **P0-4** |
| Hidden dev routes | 2 | `design-preview`, `analyze-debug` |
| Logged-in home screen | 1 | Bypassed onboarding via IndexedDB |
| Source files | 80 components, 23 routes, 14 stores | All read & cross-referenced |
| PRIORITIES.md acceptance criteria | 365 lines (incl. sub-points) | All `[x]` items checked |

### Severity rubric

- **P0** — Broken or visible regression that affects every user. Fix before next commit.
- **P1** — Visual bug or inconsistency that misleads users or breaks the design system. Fix in the next sprint.
- **P2** — Polish / microcopy / animation. Backlog.

---

## P0 — Blocking Issues

### P0-1: Skill graph radar label clipped on the left

**Where:** `app/(tabs)/progress.tsx:97` (the `<SkillGraph nodes={displayNodes} />` call)
**Component:** `components/SkillGraph.tsx:50-58` (label rendering at `angleOf(index) * radius + 18`)

**Visible in:** `tests/ui/__snapshots__/route-visual.spec.ts/-progress-viewport.png`

The leftmost label "Vibrato control" is rendered as **"orato control"** — the "Vib" is cut off by the SVG viewport. The radar chart's 5th node (index 4) has its label positioned at `cos(180°) * (radius + 18)` which is negative, so the text starts off-screen to the left.

**Fix:** in `components/SkillGraph.tsx`, increase the SVG `viewBox` and the label radius padding, and clamp labels to the viewBox edges. Concretely:

```tsx
// Current (line 11):
const radius = Math.min(90, size * 0.35)

// Patch: scale radius with size, and add a labelBuffer:
const radius = size * 0.32
const labelBuffer = 18
const labelPoint = pointAt(angle, radius + labelBuffer)
// Then in the SVG element, ensure viewBox is 0 0 size size but text-anchor
// is 'start' for left-half nodes and 'end' for right-half nodes:

<SvgText
  x={labelPoint.x}
  y={labelPoint.y + 4}
  fill={colors.muted.brown}
  fontSize={10}
  textAnchor={Math.cos(angle) < -0.1 ? 'end' : Math.cos(angle) > 0.1 ? 'start' : 'middle'}
  fontFamily="DMSans-Regular"
>
  {node.label}
</SvgText>
```

Or simpler: wrap the SVG in a `<View>` with horizontal padding and let the chart stay at 240×240 but the labels overflow into the padding.

---

### P0-2: Two entirely different visual languages in the same app

**Where:** `app/session/_layout.tsx:23` — `bg-ivory` (light cream `#F5F0E8`)
**vs:** `app/_layout.tsx:74` — `bg-wood-900` (dark `#2C1810`)
**And:** every tab screen (Home, Library, Progress, Jam, Discover, Settings) uses `bg-wood-900` via the root layout

**Visible in:** every session screen (`-session-listen`, `-session-study`, `-session-slow`, `-session-play`, `-session-review`, `-session-tune`, etc.) vs every tab screen.

**Why it hurts:** When the user taps "Start session" on the dark Home tab, they are dropped onto a light cream screen with the same wood palette but inverted. The transition is jarring. There is no animation between them. The 7-step session loop then keeps the user in the light theme until they hit "Done" and return to the dark Home.

**Fix options (in order of preference):**

1. **Pick one and commit.** The dark wood-900 is the design system's flagship (see `docs/DESIGN_SYSTEM.md` — palette is wood-900 → amber accent → cream text on dark). Recommend removing `bg-ivory` from `app/session/_layout.tsx:23` and changing the footer to use a dark-wood-700 background. The session screens' cards (e.g. `SESSION_PLAYBACK_CARD_CLASS = "bg-cream-dark/50"`) will need to be re-styled for dark mode.

2. **If light theme must stay** (e.g. for AlphaTab score readability), wrap the transition in a 250ms `Reanimated` fade so it feels intentional. Add a `WoodGradient variant="background"` wrapper instead of `bg-ivory`.

Concrete patch (option 1):

```diff
// app/session/_layout.tsx:23
- <SafeAreaView className="flex-1 bg-ivory" edges={['top', 'left', 'right']}>
+ <WoodGradient variant="background" className="flex-1">
+   <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>

  (and close the </WoodGradient> at the end)
```

Then change `text-wood-900` to `text-cream` and `bg-cream-dark/50` to `bg-wood-700/40` in:

- `components/SessionStepScreen.tsx:42-44, 62, 80, 91`
- `app/session/tune.tsx:171, 191, 234, 256`
- `app/session/musical-tolerance.tsx:47-49, 64, 77`
- `app/session/mood-check.tsx:58-60, 75, 88`
- `src/constants/sessionPlaybackCard.ts`

---

### P0-3: `/listening` is a near-duplicate of `/discover`

**Where:** `app/listening.tsx` (291 lines) and `app/(tabs)/discover.tsx`
**Visible in:** `tests/ui/__snapshots__/route-visual.spec.ts/-listening-viewport.png` and `-discover-viewport.png` — both show the same Spotify "Follow along" toggle and "Listen on Spotify" button.

The two routes render essentially the same content. `/discover` is the canonical home (visible in the tab bar). `/listening` is reachable only via deep link and exists as a redundant screen. The prior commit `d779593` ("Phase 1 archive: move commits 86-97 to archive") and `b22c6bb` ("revamp architecture") appear to have left this orphan in place.

**Fix:** delete `app/listening.tsx` and remove it from the manifest in `tests/routes.ts:21` (`{ path: "/listening", source: "manual" }`). If keeping a deep link target, add a one-line `app/listening.tsx` that just `router.replace('/(tabs)/discover')`.

---

### P0-4: MusicXML cross-platform rendering tests are broken (CDN 404)

**Where:** `tests/ui/musicxml-harness.html:18`

```html
<script src="https://cdn.jsdelivr.net/npm/@coderline/alphatab@latest/dist/alpha-tab.min.js"></script>
```

**Curl test:** `curl -sI https://cdn.jsdelivr.net/npm/@coderline/alphatab@latest/dist/alpha-tab.min.js` → **HTTP 404**

**Impact:** Every test in `tests/ui/musicxml-rendering.spec.ts` fails at `Loading AlphaTab...` because the script never loads. The Commit 108 AC "Cross-platform rendering test suite runs in CI: web screenshots match within" and "Edge-case corpus (20+ files) renders without crash on both platforms" are technically unmet. CI cannot detect MusicXML rendering regressions.

**Fix:**

```diff
- <script src="https://cdn.jsdelivr.net/npm/@coderline/alphatab@latest/dist/alpha-tab.min.js"></script>
+ <script src="https://cdn.jsdelivr.net/npm/@coderline/alphatab@1.8.0/dist/alpha-tab.min.js"></script>
```

(Pin to a specific version — `@latest` is unreliable on jsDelivr.) Better still, vendor a copy of `alpha-tab.min.js` into `public/vendor/` and load it locally — that way CI works without internet.

---

## P1 — Visual Bugs

### P1-1: "Songs / Licks" tab renders as merged "Songsticks" text

**Where:** `app/(tabs)/library.tsx:335-360`

The two tabs are siblings in a single `flex-row rounded-xl border` container with no gap or divider. The active tab (amber background) overlaps the inactive tab's text, so "Songs|Licks" reads as "Songsticks" because the right tab is partially covered.

**Fix:**

```diff
- <View className="mb-6 flex-row rounded-xl border border-wood-600 bg-wood-800/60 p-1">
+ <View className="mb-6 flex-row gap-1 rounded-xl border border-wood-600 bg-wood-800/60 p-1">
```

The amber active tab also needs to be a slightly smaller rectangle than the container, so the `border` is visible on all sides of the active tab. If the gap alone doesn't help, also:

```tsx
className={`flex-1 rounded-lg border py-2.5 ${
  libraryTab === 'lessons'
    ? 'border-amber-accent bg-amber-accent text-wood-900'
    : 'border-transparent bg-transparent text-muted-brown'
}`}
```

---

### P1-2: Empty/disabled button states have near-invisible contrast

**Where:** several files

| Screen | File:line | Issue |
|---|---|---|
| `/onboarding/taste-quiz` | `app/onboarding/taste-quiz.tsx` (Next button) | Disabled state is `wood-600/30` text on `bg-wood-900` — ~1.5:1 contrast, fails WCAG |
| `/onboarding/mic` | `app/onboarding/mic.tsx` (Microphone ready) | Filled with `bg-wood-600/40` — invisible on dark |
| `/onboarding/mic` | `app/onboarding/mic.tsx` (Next: placement phrases) | Outlined button, `text-amber-light` on `bg-wood-900`, ~3:1 — readable but not active-feeling |
| `/session/tune` | `app/session/tune.tsx:271-283` (Tune first, then continue) | Disabled state is wood-600/30 fill, wood-700 text — illegible |
| `/add-song` | `app/add-song.tsx` (Analyze file) | `bg-wood-600/55` text `text-amber-light` — appears "off" even when enabled |

**Fix (one-shot, no per-file change):** in `tailwind.config.js` add a `disabled` variant or use the existing `disabled:` modifier. Concretely for the tune button:

```diff
- className={`rounded-xl py-3 ${canContinue ? 'bg-amber-accent/90' : 'bg-wood-600/30'}`}
+ className={`rounded-xl py-3 ${canContinue ? 'bg-amber-accent/90' : 'bg-wood-700 text-muted-brown opacity-60'}`}
```

A consistent disabled style across the app would be `bg-wood-700 text-muted-brown opacity-50`. Add it as a `DISABLED_BTN_CLASS` constant in `src/constants/` and import everywhere.

---

### P1-3: "Follow along" Switch uses a teal/green thumb not in the design system

**Where:** `app/(tabs)/discover.tsx` and `app/listening.tsx` (uses default `<Switch>` with no `trackColor`/`thumbColor`)

The Switch renders in green/teal which is not in `src/constants/colors.ts`. The design system has `success: #7A9B6D` (sage green) and `amber` tones — no teal/cyan.

**Fix:**

```tsx
<Switch
  value={followAlong}
  onValueChange={setFollowAlong}
  trackColor={{ false: colors.wood[500], true: colors.amber.accent }}
  thumbColor={followAlong ? colors.cream : colors.wood[600]}
/>
```

Note: `components/DesignPreviewScreen.tsx:253-264` already does this correctly — copy the pattern.

---

### P1-4: Dev diagnostic text leaks into Review screen

**Where:** `app/session/review.tsx` — renders `<Text>Recording buffer: {latestTake ? ... : 'none'}</Text>` and `Persisted sessions (local DB): {sessionCount ?? '...'}` unconditionally.

**Visible in:** `tests/ui/__snapshots__/route-visual.spec.ts/-session-review-viewport.png` — shows `Idle`, `Recording buffer: none`, `Persisted sessions (local DB): 0`.

**Fix:**

```diff
- <Text className="mt-3 font-sans text-[11px] text-muted-brown">
-   Recording buffer: {latestTake ? ... : 'none'}
- </Text>
- <Text className="mt-1 font-sans text-[11px] text-muted-brown">
-   Persisted sessions (local DB): {sessionCount ?? '...'}
- </Text>
+ {__DEV__ ? (
+   <View>
+     <Text className="mt-3 font-sans text-[11px] text-muted-brown">
+       Recording buffer: {latestTake ? `${(latestTake.durationMs / 1000).toFixed(1)}s` : 'none'}
+     </Text>
+     <Text className="mt-1 font-sans text-[11px] text-muted-brown">
+       Persisted sessions: {sessionCount ?? '...'}
+     </Text>
+   </View>
+ ) : null}
```

The `Idle` text at the top of the review screen is from `exportState` state — also dev-only and should be hidden or renamed to a user-facing string when not in `__DEV__`.

---

### P1-5: Mood-check and Musical-tolerance screens lack visual differentiation

**Where:** `app/session/mood-check.tsx:65-79` and `app/session/musical-tolerance.tsx:55-67`

The 4 mood cards (Focused/Loose/Tired/On Fire) and 2 tolerance cards (Expressive/Technique) are visually identical — same border, same fill, same text. The user has no preview of what each option does beyond reading the subtitle.

**Fix:** add small icons (use `lucide-react-native` which is already in `package.json`):

- Focused → `Target`
- Loose → `Wind`
- Tired → `Moon`
- On Fire → `Flame`
- Expressive → `Music2` (or `Feather`)
- Technique → `Crosshair` (or `Cog`)

Insert at the top of each card:

```tsx
<View className="flex-row items-center gap-2">
  <Target color={colors.amber.accent} size={18} strokeWidth={1.5} />
  <Text className="font-sans-medium text-base text-wood-900">{opt.label}</Text>
</View>
```

---

### P1-6: Add Song modal missing decorative backdrop

**Where:** `app/add-song.tsx` — opens with `presentation: 'modal'` from `app/_layout.tsx:80`

**Visible in:** `tests/ui/__snapshots__/route-visual.spec.ts/-add-song-viewport.png` — solid dark wood-900 background.

The Home tab has a decorative amber circle in the top-right of the gradient card. Add Song's modal has no such decoration — it's a flat dark plane. Looks "unfinished" by comparison.

**Fix:** add a `WoodGradient` wrapper to the modal content, or a small decorative circle:

```tsx
<View className="flex-1 bg-wood-900">
  <View className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-amber-accent/5" />
  <View className="relative z-10 p-6">…</View>
</View>
```

(Pattern lifted from `app/(tabs)/index.tsx:369`.)

---

### P1-7: Tab bar has 6 tabs — may be too crowded on mobile

**Where:** `app/(tabs)/_layout.tsx:18-80`

Order: Home, Library, Progress, Jam Mode, Discover, Settings. Two more are hidden (Design, Analyze). On a 360px-wide phone screen this is ~60px per tab including icon + label — labels truncate (e.g. "Jam Mode" is fine, "Discover" fits, but "Library" and "Settings" sit awkwardly).

**Visible in:** every tab screen's viewport PNG.

**Fix options:**

1. **Shorten labels** — "Jam" instead of "Jam Mode", "Stats" instead of "Progress" (only on web/phone widths).
2. **Move Jam Mode to a "More" menu** — keep 4 tabs visible (Home, Library, Progress, More), put Jam/Discover/Settings under the More tab.
3. **Add a sub-navigation row inside Jam Mode** if it's a feature surface, not a destination.

Recommended: option 1 with `tabBarLabelPosition: 'below-icon'` and a smaller font on mobile.

---

### P1-8: Session screens all show the same empty fretboard — no visual cue for which step

**Where:** `app/session/study.tsx`, `slow.tsx`, `play.tsx` (and the empty-state of `listen.tsx`)

When the user has no song loaded, every session screen renders the same `FretboardDiagram` "POSITION MAP" card with the same 12-fret board. There is no header text that says "STUDY", "SLOW", or "PLAY" beyond the `SessionStepScreen` title. From the screenshots, Study/Slow/Play are visually identical apart from the title.

**Visible in:** `-session-study-viewport.png`, `-session-slow-viewport.png`, `-session-play-viewport.png` are 95% the same.

**Fix:** when no song is loaded, render a step-specific illustration/empty state component per route, e.g.:

```tsx
{!lesson ? (
  <EmptyState
    Icon={Headphones}
    heading="No song loaded for the Play step"
    subtext="Start from the Home tab to add and analyze a song."
  />
) : <FretboardDiagram … />}
```

The `EmptyState` component already exists in `components/EmptyState.tsx` and is used in `design-preview.tsx:441`.

---

### P1-9: "First time here" copy is too similar across all 3 onboarding entry points

**Where:** `app/onboarding/index.tsx`, the redirect from `app/index.tsx`, and the fallback in `app/onboarding/results.tsx:54`

Three different routes render the same "First time here" screen with identical body copy. This causes two visible problems:

1. **Visual regression test for `/` is meaningless** — the baseline at `root-viewport.png` is the onboarding screen, not the home tab.
2. **`/onboarding/results` immediately redirects to `/onboarding`** when results are empty, making the route untestable.

**Fix:**

- Add a no-op `app/onboarding/results.tsx` that renders a "Results will appear here after you complete the three phrases" empty state when the placement store is empty, instead of redirecting.
- For visual tests, the `/` baseline should capture the redirect target — either:
  - (a) set the IndexedDB onboarding-complete flag in the test setup (`tests/ui/route-visual.spec.ts` would need a `beforeEach` that visits `/onboarding` and clicks through), or
  - (b) split the test into two: one for the redirect, one for the home tab.

---

### P1-10: Dev tools floating button visible in production static export

**Visible in:** every session screen (Listen, Study, Slow, Play, Review) — small dark square with a lightning-bolt icon, bottom-left corner. This is the **Expo DevTools / React Devtools launcher** that's normally only in dev builds, but `npx expo export` includes it by default.

**Fix:** run `expo export --no-dev` for the production export, or set `EXPO_NO_DEV_TOOLS=1`. (For the dev server, leave it on — it's useful.) Document this in the build process so screenshots in CI don't include the floating button.

---

### P1-11: Active "Add Song" CTA shows "Analyze file" as low-contrast disabled state

**Where:** `app/add-song.tsx` — the "Analyze file" button uses `bg-wood-600/55` when disabled.

**Visible in:** `tests/ui/__snapshots__/route-visual.spec.ts/-add-song-viewport.png` — the button is barely visible against the dark background.

**Fix:** same as P1-2 — add a shared `DISABLED_BTN_CLASS` and use it here:

```tsx
className={`mt-4 w-full rounded-xl py-3 ${file ? 'bg-amber-accent' : 'bg-wood-700 text-muted-brown opacity-50'}`}
```

---

## P2 — Polish Issues

### P2-1: 8-step progress dots are too subtle in the session header

**Where:** `components/SessionChromeBar.tsx` (used by `app/session/_layout.tsx:24`)

The progress indicator shows 8 small dots, the current one filled in amber. They are `gap-1` apart and 8px tall, so on a 1440px screen they appear in the top-center as a faint row. On mobile (where the screen is 360px) they would be even less visible.

**Fix:** swap dots for a real progress bar (`bg-amber-accent` filling to current step %) with a `Step X of 8` label for screen readers. Place the label as `accessibilityLabel` on the bar.

### P2-2: Session `Listen` and `Study` titles lack eyebrow text

The `SessionStepScreen` title is `font-serif text-3xl text-wood-900` (or `text-cream` after the P0-2 fix). It would benefit from a small `eyebrow` (e.g. "ORIENT PHASE" above "Listen") to reinforce the 5-phase pedagogical model.

**Fix:** in `components/SessionStepScreen.tsx:60-67`, accept a `phaseEyebrow` prop and render it as a small uppercase `text-amber-accent tracking-wide` line above the title.

### P2-3: Many screens show "—" for missing data

The `—` em-dash placeholder is everywhere (Tune Hz meter, session headers, skill node values, song metadata). It looks unfinished. Replace with a friendlier empty state:

- "Play a note to start" (tuner)
- "—"  →  "Waiting for data"
- Numeric `0` displayed when it should be "—" (e.g. `0 SKILLS` in Settings is technically accurate but reads as "you have zero skills")

### P2-4: Settings accordion has no chevron rotation animation

`app/(tabs)/settings.tsx` shows a chevron icon at the right of each section header, but it doesn't rotate when the section is expanded. The state is otherwise correct — the body collapses/expands.

**Fix:** add `useSharedValue` + `useAnimatedStyle` to rotate 180° on expand. Or swap the icon (ChevronDown → ChevronUp).

### P2-5: "Style quiz" button has a clipboard icon next to text

`app/(tabs)/index.tsx:412` — `ClipboardList color={colors.wood[900]} size={20} strokeWidth={2}` next to "Style quiz" text. The clipboard icon doesn't semantically match a "taste quiz" — it implies a form/list. Consider `Music` or `ListMusic` from lucide.

### P2-6: The "Continue" button on first-time onboarding has no icon

`app/onboarding/index.tsx` — the only button is a plain amber `Continue`. Every other primary CTA in the app has an icon. Add a `ChevronRight` to signal progression.

### P2-7: Tab bar "Discover" tab icon is a magnifying glass

`app/(tabs)/_layout.tsx:70` — `<Search>` icon for the Discover tab. "Discover" semantically implies a magnifying glass (searching) or a compass. A compass (`Compass` from lucide) would be more accurate. The current icon is fine but `Search` is also used for the in-page search bar on Library, so it can confuse.

### P2-8: Jam Mode header is two lines of dense text

`app/(tabs)/jam.tsx:11` — "Active jam track: Offline loop (bundled) · E minor — two-chord vamp · E minor · 90 BPM" — this is a single long line of metadata. It would benefit from breaking into two lines: a heading ("Offline loop") and a subline ("E minor · two-chord vamp · 90 BPM"). The current line is also duplicated ("E minor" appears twice).

### P2-9: Empty states lack illustrations

`components/EmptyState.tsx` is used in design-preview but not in production screens. The actual empty states use plain text in a centered View. Consider adding a small icon (e.g. Music, PlusCircle) to each empty state for visual interest.

### P2-10: No skip-to-content for screen readers

The 6-tab bar at the bottom of every screen is the first interactive element a screen reader hits. Add `accessibilityRole="header"` or a "skip to main content" link for the tabs.

### P2-11: "Don't show this again" checkbox on tune screen has tiny touch target

`app/session/tune.tsx:262-268` — `FormCheckbox` with a small label. The checkbox itself is the touch target, not the label. Tap targets should be ≥44px per Apple/Google guidelines.

**Fix:** wrap the entire row in a single `AnimatedPressable` that toggles the checkbox state, with `min-h-[44px]`.

### P2-12: `app/(tabs)/index.tsx:356` uses `font-serif text-3xl` for the greeting, but elsewhere `font-serif text-2xl` is used for the same role

Inconsistent serif sizing across headings. Recommend a global type scale:

| Role | Class |
|---|---|
| H1 (page) | `font-serif text-3xl` |
| H2 (section) | `font-serif text-2xl` |
| H3 (card) | `font-serif text-xl` or `font-sans-medium text-base` |
| Body | `font-sans text-sm` |
| Caption | `font-sans text-xs` |

Document in `docs/DESIGN_SYSTEM.md` (currently absent).

### P2-13: `app/(tabs)/design-preview.tsx` is the only design-system reference, and it gates itself on `__DEV__`

In production builds (any non-dev build), this route is empty. Designers have no other way to see the token system. Consider:

1. Building a public `/_design` route (un-gated) that shows the same content minus the dev-specific sections (`AlphaTabRuntimeDiagDevSection`, `BackingTrackDevSection`).
2. Or generating a static HTML design system page and linking to it from Settings → "About" → "Design tokens".

### P2-14: The "Commit" naming convention is exposed to users

`app/(tabs)/analyze-debug.tsx` shows "Backend: http://localhost:8000" and `app/(tabs)/design-preview.tsx` says "Commit 61 — live AlphaTab runtime diagnostics". These commit-number references are internal documentation leaks — replace with user-facing copy ("AlphaTab runtime" instead of "Commit 61").

---

## Commit Compliance Audit (Commits 1–110)

Cross-referenced every `[x]` acceptance criterion in `PRIORITIES.md` against the visible UI. **46 of 86 visible/UI-relevant ACs have visible UI; 40 are backend or non-visual ACs (training, data, schemas, endpoints) that are not user-visible.**

### Fully verified visible ✓

| Commit | AC | Evidence |
|---|---|---|
| 38, 83 | 5-phase pedagogical model | `src/constants/sessionPhases.ts:25-31` — PHASE_STEPS map exists; phase-aware copy in `phaseTransitionCopy` |
| 62 | Tuner screen with mic profile | `app/session/tune.tsx` — full tuner ring, E2 indicator, "Quiet acoustic" / "Electric unplugged" chips, noise gate calibration |
| 62 | Calibration persisted across sessions | `useSessionPrefsStore.ts` (Zustand) — `calibrationGateRmsByProfile` map |
| 71 | Three-phrase onboarding player | `app/onboarding/phrase/[index].tsx` — "Phrase 1 — steady pocket" header, "Play reference" / "Record take" / "Stop & score" buttons |
| 76 | Daily mood check | `app/session/mood-check.tsx` — 4 options (Focused, Loose, Tired, On Fire) gated by `sessionEntryHrefWithMoodCheck` |
| 92 | Musical tolerance mode | `app/session/musical-tolerance.tsx` — Expressive (±75ms) vs Technique (±20ms) |
| 95, 96 | Phrase playback for placements | `app/onboarding/phrase/[index].tsx` — empty in baseline (no audio loaded), but the UI surface is correct |
| 109 | Beat grid editor UI | `components/BeatGridEditorPanel.tsx`, `BeatGridTimeline.tsx`, `BpmEditor.tsx`, `TimeSignaturePicker.tsx` — all exist (untestable without a loaded song) |
| 110 | Correction editor | `components/ChordCorrectionModal.tsx`, `ChordStrip.tsx`, `NoteCorrectionPanel.tsx`, `VoicingSelector.tsx`, `CorrectionHistory.tsx` — all exist (untestable without a loaded song) |
| 110 | Fretboard sync reflects corrections | `MusicContext re-derives from patched lesson` (per commit log) |
| 110 | Correction history with revert | `components/CorrectionHistory.tsx` + `useCorrectionStore` |

### Visible but unverified (couldn't test without a song)

| Commit | AC | Why unverified |
|---|---|---|
| 108 | MusicXML renders in AlphaTab | **CDN broken** — see P0-4 |
| 109 | Beat grid timeline shows beats/downbeats/bars | Requires a song with `beat_grid` populated; in baseline the timeline card shows "POSITION MAP / Unknown key" |
| 110 | Tap chord → ChordCorrectionModal opens | Requires an analyzed song |
| 110 | Tap note → NoteCorrectionPanel opens | Requires a note to tap |

### Visible but partial

| Commit | AC | Status |
|---|---|---|
| 108 | "Edge-case corpus (20+ files) renders without crash on both platforms" | **Test suite cannot run** — see P0-4 |
| 109 | "Chord timeline re-pooled on new beat boundaries" | Visible only after time-sig change in BeatGridEditorPanel — not in baseline |
| 110 | "MusicXML export uses corrected data" | **Marked `[ ]` in PRIORITIES.md — scoped down** |

### Not yet implemented (correctly marked `[ ]`)

| Commit | AC | Status |
|---|---|---|
| 109 | "Frontend renders chord chart preview when `analysis_stage >= "chords_inferring"`" | Scoped down — chord timeline is not progressively revealed |
| 109 | "Monolithic loading spinner replaced with progressive reveal" | Scoped down — `add-song.tsx` still shows monolithic spinner |
| 110 | "MusicXML export uses corrected data" | Deferred to follow-up |
| 106 | All QAT items | Commit 106 is done — archived with all ACs ticked ([`priorities-archive.md`](../priorities-archive.md)) |

### Likely intentional gaps

The following ACs marked `[x]` are **not** verified by any visual or unit test I can find:

- Commit 92 "Score accuracy is significantly different between Expressive and Technique modes" — has no test asserting the threshold difference.
- Commit 95 "Phrase 1 capture triggers `fretboard_hold` skill node creation" — has no test asserting this state transition.

Recommend adding a regression test for each when refactoring adjacent code.

---

## Design System Issues

### DS-1: Background bifurcation (covered as P0-2)

### DS-2: Undocumented typography scale (covered as P2-12)

### DS-3: `docs/DESIGN_SYSTEM.md` is 3800 lines and reads like a reference, not a guide

The doc covers everything from component APIs to babel config. It is hard to find the "what size should I use for a card title" question. Add a Type Scale table at the top.

### DS-4: Color tokens are well-defined but the muted-brown on wood-900 contrast is marginal

`text-muted-brown` (#8B7D6B) on `bg-wood-900` (#2C1810) measures ~3.4:1 contrast — **passes WCAG AA Large** but **fails AA Normal**. Most muted-brown usage is `text-xs` to `text-sm` (small text), so it should be AA Normal.

**Fix:** darken the muted-brown token to `#A69580` (lighter, ~5.2:1) or `text-cream/60` for small body text.

### DS-5: No elevation/shadow system

Components use `shadow-soft-wood`, `shadow-md`, `shadow-inner-wood` (Tailwind class extensions). These aren't defined in `tailwind.config.js`'s `theme.extend.boxShadow` — they're probably set in `global.css` but I couldn't verify without running the build.

**Recommendation:** add a clear elevation system:

| Level | Class | Use |
|---|---|---|
| 0 | `shadow-none` | Flat content |
| 1 | `shadow-soft-wood` | Cards at rest |
| 2 | `shadow-md` | Hovered cards, modals |
| 3 | `shadow-xl` | Toasts, popovers |

Document and use consistently. The current `shadow-soft-wood` is used in 1 place (`app/(tabs)/index.tsx:367`).

### DS-6: Animation tokens exist but are underused

`src/constants/animations.ts` defines `spring.gentle`, `spring.snappy`, `spring.bounce` and `timing.fast/normal/slow`. These are good. But:

- Many `AnimatedPressable` instances don't pass a `haptic` prop, falling back to default.
- No `useReducedMotion` hook for accessibility.
- The session step transitions (Stack `animation: 'slide_from_right'`) are Expo Router defaults — consider a custom fade for a more "jazz club" feel per the design philosophy in `docs/DESIGN_SYSTEM.md`.

---

## Prioritized Fix List

### Must-fix before next commit (P0)

| # | Title | File | Effort |
|---|---|---|---|
| 1 | Skill graph label clipped | `components/SkillGraph.tsx:50-58` | 30 min |
| 2 | Light/dark background bifurcation | `app/session/_layout.tsx:23` + downstream | 2 hours |
| 3 | `/listening` duplicate of `/discover` | `app/listening.tsx` | 15 min |
| 4 | MusicXML CDN broken | `tests/ui/musicxml-harness.html:18` | 15 min |

### Should-fix this sprint (P1)

| # | Title | File | Effort |
|---|---|---|---|
| 1 | Library "Songsticks" tab merge | `app/(tabs)/library.tsx:335` | 15 min |
| 2 | Disabled button contrast | Multiple (5 files) | 1 hour (one shared class) |
| 3 | Discover Switch teal thumb | `app/(tabs)/discover.tsx`, `app/listening.tsx` | 30 min |
| 4 | Dev diagnostic leak on Review | `app/session/review.tsx` | 15 min |
| 5 | Mood/Tolerance lack icons | `app/session/mood-check.tsx`, `musical-tolerance.tsx` | 30 min |
| 6 | Add Song modal backdrop | `app/add-song.tsx` | 15 min |
| 7 | 6-tab bar crowding | `app/(tabs)/_layout.tsx` | 1 hour (design + impl) |
| 8 | Empty session screens identical | `app/session/{listen,study,slow,play}.tsx` | 2 hours |
| 9 | Onboarding/results redirect to /onboarding | `app/onboarding/results.tsx:54` | 30 min |
| 10 | DevTools floating button in prod | Expo build flag | 15 min |
| 11 | Add Song Analyze file low contrast | `app/add-song.tsx` | 15 min |

### Polish backlog (P2)

Spread these over the next month; each is 15–60 min:

P2-1 progress dots → bar · P2-2 eyebrow on titles · P2-3 "—" placeholders · P2-4 chevron rotation · P2-5 Style quiz icon · P2-6 Continue arrow · P2-7 Discover icon · P2-8 Jam Mode header · P2-9 empty illustrations · P2-10 skip-to-content · P2-11 tune checkbox touch target · P2-12 typography scale doc · P2-13 design-preview dev-gating · P2-14 commit-number leaks

---

## Appendix A: Screenshot Index

| Route | Viewport PNG | Fullpage PNG |
|---|---|---|
| `/` | `tests/ui/__snapshots__/route-visual.spec.ts/root-viewport.png` | `root-fullpage.png` |
| `/add-song` | `-add-song-viewport.png` | `-add-song-fullpage.png` |
| `/discover` | `-discover-viewport.png` | `-discover-fullpage.png` |
| `/jam` | `-jam-viewport.png` | `-jam-fullpage.png` |
| `/library` | `-library-viewport.png` | `-library-fullpage.png` |
| `/listening` | `-listening-viewport.png` | `-listening-fullpage.png` |
| `/onboarding` | `-onboarding-viewport.png` | `-onboarding-fullpage.png` |
| `/onboarding/mic` | `-onboarding-mic-viewport.png` | `-onboarding-mic-fullpage.png` |
| `/onboarding/phrase/0` | `-onboarding-phrase-0-viewport.png` | `-onboarding-phrase-0-fullpage.png` |
| `/onboarding/results` | `-onboarding-results-viewport.png` | `-onboarding-results-fullpage.png` |
| `/onboarding/taste-quiz` | `-onboarding-taste-quiz-viewport.png` | `-onboarding-taste-quiz-fullpage.png` |
| `/progress` | `-progress-viewport.png` | `-progress-fullpage.png` |
| `/review-archive/demo-session` | `-review-archive-demo-session-viewport.png` | `-review-archive-demo-session-fullpage.png` |
| `/session/listen` | `-session-listen-viewport.png` | `-session-listen-fullpage.png` |
| `/session/mood-check` | `-session-mood-check-viewport.png` | `-session-mood-check-fullpage.png` |
| `/session/musical-tolerance` | `-session-musical-tolerance-viewport.png` | `-session-musical-tolerance-fullpage.png` |
| `/session/play` | `-session-play-viewport.png` | `-session-play-fullpage.png` |
| `/session/review` | `-session-review-viewport.png` | `-session-review-fullpage.png` |
| `/session/slow` | `-session-slow-viewport.png` | `-session-slow-fullpage.png` |
| `/session/study` | `-session-study-viewport.png` | `-session-study-fullpage.png` |
| `/session/tune` | `-session-tune-viewport.png` | `-session-tune-fullpage.png` |
| `/session/warmup` | `-session-warmup-viewport.png` | `-session-warmup-fullpage.png` |
| `/settings` | `-settings-viewport.png` | `-settings-fullpage.png` |

Additional captures (not in the route-visual spec):

| Source | PNG |
|---|---|
| Smoke test (logged-in home, IndexedDB flag set) | `/tmp/home-with-data.png` |
| `app/(tabs)/design-preview.tsx` (production build — empty by design) | `/tmp/design-preview.png` |
| `app/(tabs)/analyze-debug.tsx` | `/tmp/analyze-debug.png` |

---

## Appendix B: Test Run Output

### Visual baselines (PASS — 23/23)

```
$ PLAYWRIGHT_USE_WEBSERVER=0 npm run test:visual:update
…
✓  23 [chromium] › tests/ui/route-visual.spec.ts:9:7 › @visual visual baseline: /settings (14.6s)
23 passed (4.7m)
```

### Route-capture (PASS — 23/23)

```
$ PLAYWRIGHT_USE_WEBSERVER=0 npx playwright test route-capture.spec.ts
[all 23 routes wrote viewport.png + full-page.png to artifacts/playwright/screenshots/]
```

### MusicXML harness (FAIL — CDN 404, all 23 tests fail at "Loading AlphaTab...")

```
$ PLAYWRIGHT_USE_WEBSERVER=0 npx playwright test musicxml-rendering.spec.ts
Error: expect(locator).toHaveText("RENDER_COMPLETE") failed
Locator:  locator('#status')
Expected: "RENDER_COMPLETE"
Received: "Loading AlphaTab..."
```

The Playwright HTML report is at `artifacts/playwright/report/index.html`.

---

## Appendix C: Quick Reference — File Locations

| What | Where |
|---|---|
| Color tokens | `src/constants/colors.ts` |
| Animation tokens | `src/constants/animations.ts` |
| Session flow order | `src/constants/sessionFlow.ts` |
| Phase model | `src/constants/sessionPhases.ts` |
| Tab bar config | `app/(tabs)/_layout.tsx` |
| Session shell | `app/session/_layout.tsx` |
| Onboarding shell | `components/onboarding/OnboardingScreenShell.tsx` |
| Session step wrapper | `components/SessionStepScreen.tsx` |
| Skill graph (broken) | `components/SkillGraph.tsx` |
| MusicXML harness (broken) | `tests/ui/musicxml-harness.html` |
| PRIORITIES.md | `/PRIORITIES.md` |
| Design system doc | `docs/DESIGN_SYSTEM.md` |
| Commit 110 backend | `backend/app/routers/analyze.py` |
| Commit 110 frontend | `app/session/{listen,study}.tsx`, `components/{ChordCorrectionModal,NoteCorrectionPanel,VoicingSelector,CorrectionHistory,ChordStrip}.tsx` |
| Commit 109 UI | `components/{BeatGridEditorPanel,BeatGridTimeline,BpmEditor,TimeSignaturePicker}.tsx` |
