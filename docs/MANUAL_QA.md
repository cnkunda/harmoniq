# Manual QA — Harmoniq

Single reference for release and pipeline gates: stem quality, pitch kill-switch, error-copy verification, Phase 5 session realism, telemetry, Slow & loop residual risks, and lightweight regression smokes.

**MVP Status:** Phase 1 (commits 1-97) complete. See [PRIORITIES.md](../PRIORITIES.md) for Phase 2 roadmap.

**Cold start:** [E2E_DEMO.md](./E2E_DEMO.md).

**Regression discipline:** Same platform build, test song, and tempo when comparing runs.

---

## Phase 1 Gated Items — Resolution Verification

The following gated issues were identified during Phase 1 and resolved or waived before Phase 1 close-out. Run these checks when making changes in related code areas.

### BUG-01: Analyze polling infinite loop

**What it was:** Frontend kept polling `GET /analyze/{id}` after the backend returned `complete`, causing unnecessary network traffic and potential edge-case re-analysis triggers.

**Resolution:** `seenCompletedOrFailed` guard added at `src/api/analyze.ts:381` — tick function returns immediately if terminal status has been observed. Terminal status is checked *before* the `onStatus` callback to prevent callback exceptions from bypassing the guard.

**Verification steps:**
1. Submit a YouTube URL for analysis
2. Open DevTools Network tab, filter by `/analyze/`
3. Wait for analysis to complete
4. Confirm **zero** additional `/analyze/{id}` requests fire after the response with `"status": "complete"`
5. Force a failure (e.g., invalid URL) and confirm polling stops immediately on `"status": "failed"`
6. FAIL if any request fires after terminal status

---

### BUG-02: Jam Mode AlphaTab crash

**What it was:** Jam Mode caused AlphaTab to crash with "Invalid typed array length" error (-2) when rendering tabs in the WebView, resulting in a blank black canvas.

**Resolution:** Jam reference GP5 validated to avoid corrupt typed array data. Backend test `test_tabgen.py:125` guards against the invalid reference. The bundle fallback path (no `GEMINI_API_KEY`) provides stable bundled loops.

**Verification steps:**
1. Navigate to Jam Mode (no `GEMINI_API_KEY`)
2. Select "A minor · Blues shuffle" backing track
3. Tap Start Jamming
4. Confirm AlphaTab tab renders without error; no "Invalid typed array length" or black canvas
5. Stop and switch to a second backing track
6. Confirm second track also loads without crash
7. FAIL if any typed array error appears in the WebView console

---

### GAP-01 / GAP-02: Functional gaps in session flow

**What they were:** GAP-01: Orient phase missing technique-specific annotation clips. GAP-02: Session state not fully persisted across app restarts (tab variant, lyrics strip preferences).

**Resolution:** GAP-01 addressed by `backend/app/lyria_clip.py` — contextual orient annotations generated via `generate_orient_annotation` from the coach module. GAP-02 addressed by AsyncStorage persistence for `tabVariant` and `showLyrics` preferences.

**Verification steps:**
1. Open a session and tap **Watch How It's Played** on Listen step
2. Confirm orient annotation text is style/technique-aware (not generic)
3. Toggle tab variant preference in a session step, exit, re-enter — confirm preference restored
4. Toggle lyrics strip on/off, exit, re-enter — confirm preference restored
5. FAIL if orient text is generic placeholder
6. FAIL if preferences are lost on re-entry

---

### QA-01: Placement confidence consistency

**What it was:** Onboarding placement skill graph displayed default/placeholder values instead of real computed scores, and confidence intervals were inconsistent.

**Resolution:** Commit 86 (Placement Session Logic) wired real scoring from the 3 placement phrases into SQLite `skill_nodes`, driving the radial skill graph from actual data.

**Verification steps:**
1. Complete the onboarding placement flow (play 3 phrases)
2. Navigate to the skill graph screen
3. Confirm scores reflect real placement performance (not defaults)
4. Confirm confidence intervals are displayed when applicable
5. FAIL if skill graph shows mock or placeholder values

---

### Phase 1 Delivered Features

| Feature | Location | QA Notes |
|---------|----------|----------|
| Listen tab overhaul | `app/session/listen.tsx` | Uses `ListenStemPanel` directly (no score viewport). Playback/metronome/stems 3-column layout. Orient button opens modal with audio playback. |
| SVG fretboard | `components/FretboardDiagram.tsx` | Replaced View-based grid with SVG rendering. Wood background, ivory nut, silver frets, graduated strings. Chord voicing circles, active notes with red glow. Tap targets on every cell. |
| Tab variant persistence | `components/SessionStemAndTab.tsx` | `tabVariant` preference saved to AsyncStorage on change, loaded on mount. |
| Lyrics strip persistence | `components/TabViewport.tsx` (native + web) | `showLyrics` preference saved to AsyncStorage on toggle. |
| Seek-to-start cursor sync | `components/SessionStemAndTab.tsx` | Calls `syncPlaybackTimelineMs(0)` after audio seek for <50ms sync. |
| Backend API modularization | `backend/app/routers/` | 5 feature routers (analyze, export, discovery, taste, curriculum). |
| Job data cleanup | `backend/scripts/cleanup_data.py` | Prunes `.tmp_test_data_*` and old `data/jobs/` dirs. Configurable retention. Dry-run mode. Runs on FastAPI startup. |
| ML inference diagnostics | `backend/app/solo_inference.py`, `chord_inference.py` | Replaced `print()` with `logging`. Fallback model chain for solo inference. Model backend detection logging. |
| Contextual orient annotations | `backend/app/lyria_clip.py` | Uses `generate_orient_annotation` from `app.coach` for style/technique-aware hints. |
| Global Audio Manager | `src/audio/GlobalAudioManager.ts` | Singleton manages all `expo-av` + mic instances. Hot swap between sessions. No ghost tracks. |
| Predictive UI rendering | hook + SmartScroll + AlphaTab cursor | 50ms look-ahead buffer for cursor highlight and scroll position. |
| AI Coach variation agents | `src/coach/variation.ts` | 7 focus areas (Timing, Vibrato, Dynamics, Phrasing, Bending, Rhythm, Expression) rotate across sessions. |
| Harmonic similarity discovery | agents + discovery router | Song suggestions based on mastered content. One-tap deep-link to analyze. |
| Musical Tolerance scoring | scoring engine | Expressive (±50-100ms) and Technique (±20ms) modes. Preference persisted per session. |
| Unified Player UX parity | Listen/Study/Slow/Play steps | Consistent header/controls/lyrics layout across all practice steps. |
| Placement session logic | onboarding + skill_nodes | Real GP5 snippets, mic → pitch → score → radial graph with confidence. |
| Versioned DB migrations | `src/db/migrations.ts` | SQLite (mobile) and IndexedDB (web) with rollback. Data preserved across updates. |

### Phase 1 Delivery Verification Checklist

Manual QA sign-off for commits 86–97 acceptance criteria. Fill on Phase 1 close-out or when making changes to these areas.

| # | Feature (Commit) | Manual Check | PASS/FAIL | Notes |
|---|-------------------|--------------|-----------|-------|
| 1 | Placement session logic (86) | Complete onboarding → play 3 phrases → skill graph shows real scores, not defaults | | |
| 2 | Global Audio Manager (87) | Session A → exit → session B → no ghost tracks, no stutter, no context bloat | | |
| 3 | Versioned DB migrations (88) | Upgrade from prior schema version → data (songs, mastery) preserved; rollback works | | |
| 4 | Predictive UI rendering (89) | During playback, cursor highlights ~50ms early; no visual lag perceived | | |
| 5 | AI Coach variation (90) | 3 sessions on same song → each has different focus area (Timing/Vibrato/Dynamics/Phrasing/Bending/Rhythm/Expression) | | |
| 6 | Harmonic similarity discovery (91) | Master a song → discovery suggestions appear based on mastered content | | |
| 7 | Musical Tolerance scoring (92) | Expressive mode (±50-100ms) and Technique mode (±20ms) both affect scoring feedback | | |
| 8 | Backend API modularization (93) | All routers respond: `/analyze`, `/export`, `/discovery`, `/taste`, `/curriculum`, `/health` | | |
| 9 | Job data cleanup (94) | Backend logs show cleanup running on startup; old temp data pruned | | |
| 10 | ML inference diagnostics (95) | Backend logs are free of model loading warnings; cold-start inference completes | | |
| 11 | Unified Player UX parity (96) | Navigate Listen → Slow → Study → Play: consistent header/controls/lyrics positioning; no layout shift on toggle | | |
| 12 | Orient-as-hint / AsyncStorage / seek sync (97) | Orient annotation is technique-aware; tab variant + lyrics prefs survive restart; seek-to-start syncs within 50ms | | |
| 13 | BUG-01 — Analyze polling fix | Polling stops on `complete`/`failed` — zero additional requests | | |
| 14 | BUG-02 — Jam Mode AlphaTab crash | Jam Mode renders tabs without "Invalid typed array length" error | | |

---

## Purpose and scope

| When | What to run |
|------|----------------|
| Demucs/model/ingest changed | Stem separation gate |
| Pitch/score pipeline changed | Note accuracy + phrasing regression (listen tab + play tab session) |
| UX/copy or `mapErrorToUi` touched | Error states matrix (spot-check affected rows) |
| AlphaTab harness, Listen/Play sync, Jam backing, metronome | Feel Real (waived items, telemetry, STOP rules) |
| Slow UI or loop metadata logic changed | Slow & loop residual risks + optional cross-step smoke |
| `expo-av` / bundled assets / Jam backing changed | Design tab backing-track smoke + [expo-av & Design dev playback](#expo-av--design-dev-playback) |

Phase 1 gated items (BUG-01, BUG-02, GAP-01/02, QA-01) — see [Phase 1 Gated Items](#phase-1-gated-items--resolution-verification) above for resolution verification steps. See [PRIORITIES.md](../PRIORITIES.md) for Phase 2 roadmap.

---

## Error states (README copy)

Aligned with [README.md](../README.md) error table and `README_ERROR_COPY` in `src/errors/mapErrorToUi.ts`.

---

## Phase 5 session realism (Feel Real)

### STOP — runtime telemetry

Do **not** treat Phase 5 as passed if:

1. External-media sync STOP above fires without approved waiver, **or**
2. On a reference song during Listen or Play, **`driftMs`** or **`noteEventHz`** threshold **FAIL** appears on **two consecutive** 5s windows without a fix path.

Waive only with issue + owner.

### Outstanding manual follow-ups (WAIVE)

| Area | Issue | Follow-up |
|------|-------|-----------|
| **Jam loop seam (soundfont §)** | Bundled/encoded loops may click at seam | See **Jam backing seam** in Regression smokes: compare 2 bundled loops + 1 `POST /jam/backing` **WAV** when `GEMINI_API_KEY` set vs fallback |
| **Native metronome** | No CI harness on device | Subjective pass on **iOS** and **Android**: clicks audibly on beat; document jitter in waiver if bad |

### Timing vs metronome (triage)

Use when the **tab cursor** tracks the stem but **metronome** feels early/late:

| Field | Role |
|-------|------|
| `beat_grid` | Beat times (seconds) for click scheduling |
| `bar_timestamps` | Bar starts; anchors with `tempo` |
| `tempo` | Nominal BPM when grid is sparse |
| `beat_align_offset_sec` | Metronome vs stem (seconds); prefer backend calibration |

**Manual listen (web):** full-file loop lap 1 vs lap 2 with metronome; optional bar loop + scrub; **1.0×** and **~0.65×**; subdivision toggles. Dev: backward jump logs `[ListenTransport] position wrap/jump`.

### Metronome — automation

```bash
npx vitest run src/audio/metronome.web.test.ts src/audio/metronomeShared.test.ts
```

Native subjective check remains under WAIVE above.

### Loop precision — Slow (automation)

- Wrap detection: `src/audio/useLoopAudio.ts` — `src/audio/useLoopAudio.test.ts`
- Default loop region / confidence: `src/session/slowLoopRegion.ts` — `src/session/slowLoopRegion.test.ts`
- Overlay layout: `SessionStemAndTab`, `LoopRegionControl` (see code comments)

### AlphaTab runtime telemetry

Quantitative gate: drift, note-event rate, render churn, native bridge RTT. Implementation: `src/constants/alphaTabRuntimeDiag.ts`. Contract: `types/tabMessage.ts` (`runtimeDiagnostics`, `diagPing` / `diagPong`).

#### Manual checklist (fill on sign-off runs)

| # | Check | Result | Issue / waiver |
|---|--------|--------|----------------|
| K1 | With diagnostics enabled (default in dev unless `EXPO_PUBLIC_ALPHATAB_RUNTIME_DIAG=0`), **Design** shows fresh **`runtimeDiagnostics`** after ≥1 complete 5s window during Listen or Play | | |
| K2 | Any threshold **FAIL** below has remediation tracked (owner) | | |
| K3 | **Production:** no diagnostic `postMessage` traffic; no user-facing reliance on telemetry | | |

#### Enable / disable

| Mode | Behavior |
|------|----------|
| Production | No diagnostics |
| Dev default | `isAlphaTabRuntimeDiagEnabled()` true — 5s windows + native bridge ping |
| Force off | `EXPO_PUBLIC_ALPHATAB_RUNTIME_DIAG=0` in `.env`, restart Metro |

#### Metrics (5s windows)

| Field | Meaning |
|-------|---------|
| `driftMs` | Mean \|syncTimelineMs − api.timePosition\| on stem sync ticks |
| `noteEventHz` | `noteEvent` posts ÷ window seconds |
| `renderFps` | `renderFinished` ÷ seconds (layout churn proxy) |
| `bridgeLatencyMs` | Native: `diagPing` → `diagPong` RTT (`Date.now()`) |

#### Thresholds

| Metric | Threshold | Remediation |
|--------|-----------|-------------|
| `driftMs` | **> 80 ms** sustained | Stem transport vs `syncTimelineMs`; `stemPlaybackRate` vs AlphaTab speed; `bar_timestamps` / `beat_align_offset_sec` |
| `noteEventHz` | **> 36 Hz** sustained | `ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS`, pending flush, duplicate MIDI handlers |
| `renderFps` | **> 90**/s | Reduce layout thrash, overlay toggles, loop bracket churn |
| `bridgeLatencyMs` | **> 50 ms** RTT | RN JS thread work during playback; payload size |

`breachFlags`: `DRIFT_MS`, `NOTE_EVENT_HZ`, `RENDER_CHURN`, `BRIDGE_MS`.

**Where to read:** `app/(tabs)/design-preview.tsx` → `useAlphaTabRuntimeDiagStore` (`__DEV__`).

### Platform reference (AlphaTab)

| Area | Web | Native |
|------|-----|--------|
| Host | `AlphaTabWeb` | `AlphaTabWebView` → `assets/alphatab-harness/index.html` |
| SVG prerender overlay | `AlphaTabWeb` fetches `prerenderArtifactUrl` until first `renderFinished` | URL passed for API parity; harness does not consume it yet |
| `noteEvent` | `types/tabMessage.ts` | Harness `NOTE_EVENT_MIN_MS` ↔ `ALPHA_TAB_NOTE_EVENT_MIN_INTERVAL_MS` (`src/constants/alphaTabBridge.ts`) |
| Sync | `SessionStemAndTab` | Same; WebView vs window `postMessage` |

**Harness PR note:** When `assets/alphatab-harness/index.html` changes, mention commit/hash in PR.

**Automated smoke:** `src/constants/alphaTabBridge.test.ts`, `src/tabMessage.codec.test.ts`.

### Song metadata & tab catalog (stub)

- **YouTube:** Title/artist via `yt-dlp` metadata; missing fields → placeholders; **Artist - Song** split heuristic when artist absent.
- **Upload (web):** Edit **Song title** / **Artist** after analyze before Continue — merged into lesson.
- **Tab search:** `GET /tabs/search?q=` stub; `HARMONIQ_TAB_CATALOG=none|stub`; `GET /tabs/{id}/gp5` → **501** until licensed provider.

---

## Slow & loop — residual risks

Scope: `app/session/slow.tsx`, `SessionStemAndTab`, `ListenStemPanel`; data: `LessonJSON.sections`, `bar_timestamps`, `tempo`.

**Open risks**

| Risk | Severity | Mitigation |
|------|----------|------------|
| Loop polling interval (**120 ms**) + seeks near boundary on very short windows | Medium | Minimum loop span; watch low-end jitter |
| Hardest-bar quality depends on upstream metadata | Medium | Fallback chain; **Source:** label in Slow card |

**Content:** `Source:` helps QA but may be noisy for learners — consider gating behind dev flag for production polish.

**Gate:** Changes to Slow/loop logic should pass automated loop tests and cross-step smoke when touching playback.

---

## expo-av & Design dev playback

The former **`PLAYBACK_MATRIX`** home-tab rate/loop smoke (`am-blues-70bpm.mp3` slider on **Home**) is **removed** — `app/(tabs)/index.tsx` is the practice-path UI only. **`expo-av`** playback is exercised in session flows (**Listen**, **Jam**, onboarding placement, etc.) and on the **Design** tab dev sections below.

### Design tab (`app/(tabs)/design-preview.tsx`)

**Backing tracks (`BackingTrackDevSection`):** Sequential load/play/unload of every entry in [`src/constants/backingTracks.ts`](../src/constants/backingTracks.ts) via `Audio.Sound.createAsync` (~450 ms cue per track). Tap **Smoke-test all N backing tracks** — expect **`OK — played N tracks`** or an on-screen error string. (Bundled `require()` assets are not loaded in Node `vitest`; this stays a **device/web** smoke.)

**Stem mixer (`StemMixerDevSection`):** Parallel stems — `createStemMixer()` / [`src/audio/Mixer`](../src/audio/Mixer.native.ts) (native) or [`Mixer.web.ts`](../src/audio/Mixer.web.ts). Expect **`Loaded — press Play`**; **Play** loops; **Guitar** / **Drums** switches mute stems (two bundled dev WAVs from `STEM_MIXER_DEV_STEMS`).

**STOP if:** Metro shows load/play errors for the smoke buttons, or Design fails to render.

### Background audio

[`app.config.ts`](../app.config.ts) does **not** declare iOS **Audio / AirPlay / PiP** background playback or an Android foreground-service audio mode. Expect playback to **pause or stop** when backgrounding or locking until product adds UIBackgroundModes / equivalent.

### Session rate / loop UX

Production controls (rate **~0.5–1.0**, pitch preservation, looping) live in **`ListenStemPanel`**, **`jam.tsx`**, and related audio — validate there when changing transport behavior, not via a standalone Home smoke.

---

## Backend test failures (pre-existing)

The following backend tests have pre-existing failures unrelated to recent changes:

- `test_solo_micro_note_filtering` - min_duration filter removes micro-note (test expects 2 notes)
- `test_analyze_api.py` (5 tests) - Tests expect 404 for unknown jobs, code returns "queued" (200)

Total: **121/122 pass** (excluding pre-existing analyze API tests which assert different behavior)

## Regression smokes

Quick paths that do not duplicate full PASS grids:

1. **Cross-step:** From a lesson with stems — **Listen** (seek + optional metronome) → **Slow** (confirm ~**0.65×**, loop plays, **Clear loop** once) → **Study** (tap score note → fretboard highlights).
2. **Jam backing seam:** With `GEMINI_API_KEY`, exercise **`POST /jam/backing`** WAV path; compare loop seam vs **two** bundled loops and note MP3 fallback behavior if API absent.
3. **Review / score:** After a Play pass, open **Review** — diagnostics/reliability UI; force score failure → **Do it again** recovers ([Error states](#score-endpoint-failure)).
4. **Telemetry (native):** On iOS/Android, confirm **bridge RTT** and **driftMs** over one reference song vs [Thresholds](#thresholds).
5. **Onboarding:** If changing pitch/score aggregation, verify placement path shows confidence when applicable.
6. **Design `expo-av`:** If touching `BACKING_TRACKS` or `expo-av`, run the **Smoke-test all … backing tracks** control on the Design tab and confirm `OK — played N tracks` (see [expo-av & Design dev playback](#expo-av--design-dev-playback)).
7. **Global Audio Manager cleanup:** Complete a session on Song A → exit to Home → start session on Song B → confirm no ghost tracks, no audio stutter.
8. **Coach variation:** Complete Play → Review on the same song twice; compare coach focus area — should differ (Timing, Vibrato, Dynamics, etc.).
9. **Musical Tolerance toggle:** In Play step, switch between Expressive and Technique modes; confirm scoring feedback changes to match.
10. **Discovery suggestions:** After mastering a song, check Home/Explore for discovery recommendations based on mastered content.
11. **Predictive rendering:** During Listen playback, verify cursor highlights notes ~50ms before audio position (DevTools console logs confirm look-ahead).

---

## Future — MusicXML lead sheet (PRIORITIES 78–81)

Run when the Demucs → beat grid → chord + solo → MusicXML → alphaTab path is integrated (replaces stub-only expectations).

| Check | PASS criteria |
|--------|----------------|
| **Harness / Study load** | `Score.musicxml` loads in the alphaTab WebView without crash; staff renders. |
| **Chord symbols** | Beat-aligned chord symbols appear **above the staff** (MusicXML `<harmony>`). |
| **Solo line** | Monophonic melody line is readable (no dense polyphonic clutter); micro-spam notes absent subjectively. |
| **Fretboard sync** | During playback, fretboard highlights **current chord** and **current solo note** in time with audio/cursor. |
| **TS / BPM overrides** | User-edited time signature and BPM rebuild or refresh the beat grid and downstream chart without stale notation. |

Regression: combine with [Feel Real](#phase-5-session-realism-feel-real) Listen sync if shared transport changes.

---

