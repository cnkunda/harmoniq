# Manual QA — Harmoniq

Single reference for release and pipeline gates: stem quality, pitch kill-switch, error-copy verification, Phase 5 session realism, telemetry, Slow & loop residual risks, and lightweight regression smokes.

**MVP Status:** Phase 1 (commits 1-97) complete. Commits 98-100 (chord model expansion, Viterbi, boundary tie) complete. See [PRIORITIES.md](../PRIORITIES.md) for Phase 2 roadmap.

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

## Phase 1.1 Gated Items — Chord Model & Transcription (Commits 98-100)

These commits upgraded the chord transcription pipeline from 25-class major/minor to a 277-class extended vocabulary with temporal smoothing and boundary continuity. Run these checks when modifying chord inference, CQT extraction, or solo transcription.

### Phase 1.1 Delivered Features

| Feature | Location | QA Notes |
|---------|----------|----------|
| Advanced Extension Recognition (98) | `backend/app/build_chord_tflite.py` | 277-class vocab: 7ths, 9ths, 11ths, 13ths, altered dominants (7#9, 7b13, alt7), sus2/4, dim/dim7/aug. Smoke: D7, Cmaj7, Am7 recognized. |
| Chord Data Generation (98a) | `backend/app/build_chord_tflite.py` | Inversion simulation (1st/2nd), missing note dropout 15%, pitch shift ±2 semitones, time stretch 0.9-1.1x, pink noise, transition samples at chord boundaries. |
| 36-Bin CQT Features (98b) | `backend/app/build_chord_tflite.py` | Model input `(WINDOW, 40)`: 36 CQT bins + 4 bass-channel bins. Bass chroma separated for bass-note detection. val_acc 82.9% @ 19 epochs. |
| CRNN + BiLSTM (98c) | `backend/app/build_chord_tflite.py` | 128-frame temporal windows (~2.5-6s). CNN → BiLSTM architecture. SELECT_TF_OPS for TFLite conversion. val_acc 82.9% @ 19 epochs. |
| Multi-Head Attention (98d) | `backend/app/build_chord_tflite.py` | 4 heads, key_dim=64. Attention weights visualizable via `build_attention_vis_model()`. Model size 1.1MB. Overall accuracy 81.4%. |
| Viterbi Decoding (99) | `backend/app/chord_inference.py` | Chord flicker <5%. Beat-alignment >90%. Half-beat (8th-note) resolution with tie-detection (confidence diff <0.15). Key-constrained transitions. Duration-aware filtering. |
| Segment Boundary Tie (100) | `backend/app/chord_inference.py`, `backend/app/solo_inference.py` | 50% overlap processing with triangular windowing. Active-note tracking between segments (MT3-style). Boundary confidence penalty (2-frame edge zone). |

### Commits 98-100 Verification Checklist

| # | Feature (Commit) | Manual Check | PASS/FAIL | Notes |
|---|-------------------|--------------|-----------|-------|
| 15 | Advanced Extension Recognition (98) | Analyze jazz/blues song with known 7th/9th chords → chord timeline shows extended symbols (D7, Cmaj7, Am7), not just major/minor | | |
| 16 | Chord Data Generation (98a) | Backend training logs show inversion/missing-note/pitch-shift augmentation active; transition samples improve boundary detection | | |
| 17 | 36-Bin CQT Features (98b) | Backend logs show CQT extraction with 36 bins + 4 bass-channel bins; chord accuracy on bass-heavy songs improved vs 12-bin baseline | | |
| 18 | CRNN + BiLSTM (98c) | Chord timeline shows smooth transitions across 2.5-6s windows; no rapid flickering on sustained chords | | |
| 19 | Multi-Head Attention (98d) | Extended chords (7#9, alt7, dim7) recognized in jazz audio; attention diagnostics available in dev mode | | |
| 20 | Viterbi Decoding (99) | Analyze ii-V-I progression → chord timeline shows smooth Dm7→G7→Cmaj7 without flicker; >90% changes on beat boundaries | | |
| 21 | Half-beat resolution (99) | Song with 8th-note chord changes → two chord events emitted per beat with correct timestamps when confidence diff <0.15 | | |
| 22 | Duration-aware filtering (99) | Sub-1-beat chord outliers suppressed unless legitimate transition; chord-change rate histogram reportable in metadata | | |
| 23 | Segment Boundary Tie — chords (100) | Chord held across segment boundary → emitted as single event, not duplicated; no gap in chord coverage at boundary | | |
| 24 | Segment Boundary Tie — solo (100) | Sustained solo note crossing boundary → no duplicate onset or premature offset; active-note tracking preserves continuity | | |
| 25 | Boundary confidence penalty (100) | Predictions within 2 frames of segment edges show reduced confidence; scoring timing errors decrease for boundary-crossing notes | | |
| 26 | Overlap-and-blend (100) | 50% overlap processing merges predictions by higher-confidence in overlap zone; boundary chord flicker reduced ≥50% | | |

---

## Phase 2 Gated Items — Beat Grid Editor (Commit 109)

User-facing beat grid editor (expand panel in metronome card) with async recompute endpoint that re-derives chord timeline, solo notes, and MusicXML after beat grid edits. Run these checks when modifying beat estimation, time signature handling, or the recompute pipeline.

### Phase 2 Delivered Features

| Feature | Location | QA Notes |
|---------|----------|----------|
| Beat Grid Timeline | `components/BeatGridTimeline.tsx` | SVG visualization: beat ticks, downbeat accents, bar lines, playhead. Accepts `BeatGrid` prop; renders from `beats[]` and `time_signature`. |
| Time Signature Picker | `components/TimeSignaturePicker.tsx` | Numerator: 2/3/4/6/9/12. Denominator: 4/8. Chip-based selection. |
| BPM Editor | `components/BpmEditor.tsx` | Fine (±0.5) and coarse (±5) adjustment. Reset-to-auto button restores librosa-detected BPM. |
| Beat Grid Editor Panel | `components/BeatGridEditorPanel.tsx` | Expandable panel with timeline preview, undo/redo, apply button, recompute progress bar. Real-time preview shows synthetic beat grid from user values when dirty. |
| Beat Grid Edit Store | `src/stores/beatGridEditStore.ts` | Zustand store with undo/redo history. Tracks `bpm`, `timeSignature`, `isDirty`, `overrideApplied`. |
| Recompute Endpoint | `backend/app/routers/analyze.py` | `POST /analyze/{id}/beat-grid/recompute` + `GET` poll. Re-runs beat estimation → chord inference → solo inference → MusicXML. |
| Analysis Stage | `backend/app/jobs.py` | Progressive `analysis_stage` field on `JobStatus`: `initializing` → `stems_separating` → `chords_inferring` → `solo_inferring` → `building_musicxml` → `complete`. |
| bar_timestamps Fix | `backend/app/analyze_audio.py` | Derived from `beat_grid.downbeats` instead of hardcoded 4/4. |

### Commit 109 Verification Checklist

| # | Feature | Manual Check | PASS/FAIL | Notes |
|---|---------|--------------|-----------|-------|
| 27 | Beat Grid Timeline renders | After analysis, expand beat grid panel → timeline shows beats as ticks, downbeats as accents, bar lines as vertical separators | | |
| 28 | Time signature picker | Select 3/4 → timeline re-renders with 3 beats per bar; select 6/8 → 6 beats per bar | | |
| 29 | BPM editor (fine) | Tap +0.5 three times → BPM increases by 1.5; timeline spacing adjusts | | |
| 30 | BPM editor (coarse) | Tap +5 → BPM increases by 5; tap −5 → returns to original | | |
| 31 | Reset to Auto | After editing, tap Reset → BPM returns to librosa-detected value; `isDirty` clears | | |
| 32 | Real-time preview | Edit BPM → timeline updates immediately (synthetic grid from user values, not original) | | |
| 33 | Undo/Redo | Make 3 edits → undo twice → redo once → state matches expected history position | | |
| 34 | Recompose trigger | Edit BPM/time sig → tap Apply → progress bar appears; chord timeline, solo notes, MusicXML update when complete | | |
| 35 | analysis_stage polling | During initial analyze, poll `GET /analyze/{id}` → `analysis_stage` transitions through all stages in order | | |
| 36 | bar_timestamps (non-4/4) | Analyze song in 3/4 or 6/8 → `bar_timestamps` has correct number of bars (not hardcoded 4/4) | | |
| 37 | Chord re-pooling | Edit time sig 4/4→3/4 → Apply → chord timeline re-aligns to new beat boundaries | | |
| 38 | Solo re-quantization | Edit BPM ±10% → Apply → solo note durations reflect new tempo | | |
| 39 | Disk persistence | After recompute, check job directory for updated `BeatGrid.json`, `chordTimeline.json`, `SoloNotes.json`, `score.musicxml` | | |

---

## Purpose and scope

| When | What to run |
|------|----------------|
| Demucs/model/ingest changed | Stem separation gate |
| Pitch/score pipeline changed | Note accuracy + phrasing regression (listen tab + play tab session) |
| Chord model / CQT / Viterbi / boundary tie changed | Extended chord recognition + Viterbi smoothing + boundary continuity (commits 98-100) |
| Beat grid / recompute / bar_timestamps changed | Beat grid editor, recompute endpoint, progressive analysis_stage, bar_timestamps derivation (commit 109) |
| UX/copy or `mapErrorToUi` touched | Error states matrix (spot-check affected rows) |
| AlphaTab harness, Listen/Play sync, Jam backing, metronome | Feel Real (waived items, telemetry, STOP rules) |
| Slow UI or loop metadata logic changed | Slow & loop residual risks + optional cross-step smoke |
| `expo-av` / bundled assets / Jam backing changed | Design tab backing-track smoke + [expo-av & Design dev playback](#expo-av--design-dev-playback) |

Phase 1 gated items (BUG-01, BUG-02, GAP-01/02, QA-01) — see [Phase 1 Gated Items](#phase-1-gated-items--resolution-verification) above for resolution verification steps. Phase 1.1 gated items (commits 98-100) — see [Phase 1.1 Gated Items](#phase-11-gated-items--chord-model--transcription-commits-98-100) above. Phase 2 gated items (commit 109) — see [Phase 2 Gated Items](#phase-2-gated-items--beat-grid-editor-commit-109) above. See [PRIORITIES.md](../PRIORITIES.md) for Phase 2 roadmap.

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
| **Beat grid editor overrides** | No persistence across restarts | Overrides live in Zustand in-memory store; navigating away from session clears. Document as known limitation until commit 110 adds DB persistence. |

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
| `driftMs` | **> 80 ms** sustained | Stem transport vs `syncTimelineMs`; `stemPlaybackRate` vs AlphaTab speed; `bar_timestamps` / `beat_align_offset_sec`. Note: beat grid overrides (commit 109) affect these values — drift may change after a manual recompute. |
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

Scope: `app/session/slow.tsx`, `SessionStemAndTab`, `ListenStemPanel`; data: `LessonJSON.sections`, `bar_timestamps`, `tempo`. Note: `bar_timestamps` and `tempo` can now come from user overrides (commit 109) — not just auto-detection.

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

Total: **39 test files** in `backend/tests/`. CI runs 10 files: `test_jam_score.py`, `test_score.py`, chord model (4 files), Viterbi (3 files), boundary tie (1 file).
Full suite: `cd backend && python3 -m pytest -q`

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
12. **Extended chord recognition:** Analyze a jazz song (e.g., "All of Me") → chord timeline shows 7ths, 9ths, maj7 (not just major/minor).
13. **Viterbi smoothing:** Analyze ii-V-I progression → no rapid chord flickering; changes land on beat boundaries.
14. **Boundary continuity:** Analyze song >30s → sustained chord at segment boundary appears as single event, not duplicated.
15. **Beat grid recompute:** Edit BPM in beat grid editor → tap Apply → chord timeline, solo notes, and MusicXML all update; `analysis_stage` transitions through stages in poll response.
16. **bar_timestamps (non-4/4):** Analyze a song in 3/4 or 6/8 → `bar_timestamps` has correct number of bars (not hardcoded 4/4).

---

## Automated test coverage — Commits 98-100

These backend test files cover the chord model expansion, Viterbi decoding, and boundary tie mechanism. Run when modifying chord inference or solo transcription:

```bash
# Chord model (commits 98-98d): CQT features, augmentation, CRNN, attention
cd backend && python -m pytest -q \
  tests/test_cqt_features.py \
  tests/test_chord_augmentation.py \
  tests/test_chord_metrics.py \
  tests/test_inference_logic.py

# Viterbi decoding (commit 99): smoothing, transitions, half-beat resolution
cd backend && python -m pytest -q \
  tests/test_viterbi_decoder.py \
  tests/test_viterbi_chord_progression.py \
  tests/test_chord_transitions.py

# Boundary tie (commit 100): overlap-and-blend, active-note tracking
cd backend && python -m pytest -q \
  tests/test_boundary_tie.py
```

**CI status:** These 8 test files are now included in `scoring-tests.yml` alongside `test_jam_score.py` and `test_score.py` (10 backend files total in CI).

---

## Automated test coverage — Commit 109

Beat grid editor, recompute endpoint, and progressive analysis_stage. Run when modifying beat estimation, recompute pipeline, or the editor UI:

```bash
# Beat grid recompute: dependent artifacts, analysis_stage, schemas, bar_timestamps
cd backend && python -m pytest -q \
  tests/test_beat_grid_recompute.py
```

**CI status:** `test_beat_grid_recompute.py` (12 tests) is not yet in `scoring-tests.yml` — add it when ready to gate on beat grid recompute in CI.

---

## Phase 2.1 Gated Items — Analysis Persistence & Correction Editor (Commit 110)

User-facing correction editor for chords, solo notes, and voicings with backend persistence. Run these checks when modifying chord inference, solo transcription, correction endpoints, or the correction UI.

### Phase 2.1 Delivered Features

| Feature | Location | QA Notes |
|---------|----------|----------|
| Job Persistence | `backend/app/jobs.py` | Completed/failed jobs saved as `JobStatus.json` in job directory. Reloaded on server startup via `load_jobs_from_disk()`. |
| Chord Correction Endpoint | `backend/app/routers/analyze.py` | `PATCH /analyze/{job_id}/chord/{beat_index}` — accepts chord symbol, updates timeline, rebuilds MusicXML. |
| Note Correction Endpoint | `backend/app/routers/analyze.py` | `PATCH /analyze/{job_id}/solo-note/{note_index}` — partial update of pitch/duration/start_time/velocity. |
| Voicing Override Endpoint | `backend/app/routers/analyze.py` | `PATCH /analyze/{job_id}/chord/{beat_index}/voicing` — stores CAGED shape (E/A/D/C/G). |
| Correction History | `backend/app/routers/analyze.py` | `GET /analyze/{job_id}/corrections` — returns all corrections with count and coverage. |
| Correction Export | `backend/app/routers/analyze.py` | `GET /analyze/{job_id}/corrections/export` — JSON format for ML retraining pipeline. |
| Correction Store | `src/stores/correctionStore.ts` | Zustand store persisted to `app_prefs` via `getAppPref`/`setAppPref`. Undo via revert. |
| Diatonic Chord Helper | `src/music/diatonicChords.ts` | `getDiatonicChords(key)` — returns diatonic chords filtered by key with Roman numerals. |
| Chord Correction Modal | `components/ChordCorrectionModal.tsx` | Modal with diatonic + chromatic chord picker, fretboard preview, confirm/cancel. |
| Chord Strip | `components/ChordStrip.tsx` | Horizontal scrollable chord strip for Listen screen. Tap chord → correction modal. |
| Note Correction Panel | `components/NoteCorrectionPanel.tsx` | Modal with pitch stepper, string/fret selector, duration slider. |
| Voicing Selector | `components/VoicingSelector.tsx` | Chip-based CAGED shape picker. |
| Correction History UI | `components/CorrectionHistory.tsx` | List of corrections with revert button per entry. |
| Lesson Merge Helper | `src/utils/applyCorrections.ts` | `applyCorrectionsToLesson()` — patches chord timeline + solo notes from corrections. |

### Commit 110 Verification Checklist

| # | Feature | Manual Check | PASS/FAIL | Notes |
|---|---------|--------------|-----------|-------|
| 40 | Job persistence | Complete analysis → restart backend → `GET /analyze/{job_id}` returns cached result | | |
| 41 | Chord correction (backend) | `PATCH /analyze/{id}/chord/0` with valid chord → returns updated timeline, confidence=1.0 | | |
| 42 | Chord correction (frontend, Listen) | Tap chord in chord strip → modal opens → select new chord → confirm → chord updates | | |
| 43 | Chord correction (frontend, Study) | Tap chord symbol in chord sheet → modal opens → select diatonic chord → confirm | | |
| 44 | Note correction (backend) | `PATCH /analyze/{id}/solo-note/0` with pitch=62 → returns updated note | | |
| 45 | Note correction (frontend) | Tap red note on fretboard → panel opens → adjust pitch → confirm → note updates | | |
| 46 | Voicing override | `PATCH /analyze/{id}/chord/0/voicing` with "E-shape" → stored on event | | |
| 47 | Correction history | After corrections, `GET /analyze/{id}/corrections` returns all with correct counts | | |
| 48 | Correction revert | In CorrectionHistory, tap Revert → correction removed, lesson reverts | | |
| 49 | Correction metrics | `correction_count` and `correction_coverage` appear in lesson metadata | | |
| 50 | Corrections export | `GET /analyze/{id}/corrections/export` returns JSON with chord_corrections array | | |
| 51 | Fretboard sync | After chord correction, fretboard shows new chord voicing during playback | | |
| 52 | Cross-session persistence | Apply correction → navigate away → return → correction still applied | | |

---

## Automated test coverage — Commit 110

Backend correction tests: schema behavior, persistence, and metrics.

```bash
# Correction schemas, persistence, and merge logic
cd backend && python -m pytest -q \
  tests/test_corrections.py
```

**CI status:** `test_corrections.py` (8 tests) — not yet in `scoring-tests.yml`.

---

## Future — MusicXML lead sheet (PRIORITIES 78-81, 106-107)

Run when the Demucs → beat grid → chord + solo → MusicXML → alphaTab path is fully integrated (replaces stub-only expectations). Chord model (commits 98-98d), Viterbi decoding (99), and boundary tie (100) are complete — the chord inference pipeline now produces extended chord vocabulary with temporal smoothing and boundary continuity.

| Check | PASS criteria |
|--------|----------------|
| **Harness / Study load** | `Score.musicxml` loads in the alphaTab WebView without crash; staff renders. |
| **Chord symbols** | Beat-aligned chord symbols appear **above the staff** (MusicXML `<harmony>`). |
| **Solo line** | Monophonic melody line is readable (no dense polyphonic clutter); micro-spam notes absent subjectively. |
| **Fretboard sync** | During playback, fretboard highlights **current chord** and **current solo note** in time with audio/cursor. |
| **TS / BPM overrides** | ✅ Implemented (commit 109). User-edited time signature and BPM rebuild the beat grid via `POST /analyze/{id}/beat-grid/recompute`; chord timeline, solo notes, and MusicXML are re-derived. |

Regression: combine with [Feel Real](#phase-5-session-realism-feel-real) Listen sync if shared transport changes.

---

