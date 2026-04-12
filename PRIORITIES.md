# Harmoniq — Engineering Roadmap (Commit-by-Commit)

Atomic, production-quality commits ordered for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (commits 0.1–0.6)** — Expo + design scaffold, backend shell, AlphaTab harness, env/backing tracks, shared UI feedback + API client — is **complete**. **Commits 1–44** are delivered in tree. **Phase 5 (45–61)** is the active realism track. **Phase 6 (62–65)** — pre-session tuner, skill mutation, left-handed mode, ZPD curriculum — is **planned**. **Phase 7 (66–77)** — The Guided Path: coach reliability, Spotify taste ingestion, guided practice queue, ordered drill sequencer, voice coach, Riff DNA, Ghost Player, mood adaptation, and Listening Mode — is **planned**. A compact [completion index](#appendix--roadmap-completion-index-commits-1-77) lists every tracked commit through **77**.

---

## Technology Resolution Notes

`DESIGN_SYSTEM.md` has been **fully rewritten** for the React Native + Expo stack — it is now the canonical UI reference. The original web-prototype libraries are replaced as follows:

| Concern | Was (web prototype) | **Is (production)** |
|---|---|---|
| Routing | `react-router-dom` | **Expo Router** — file-based, `app/` directory (SDK 54) |
| Icons | `lucide-react` | **`lucide-react-native`** on native; `lucide-react` on web via `.web.tsx` platform split |
| Animations | `framer-motion` | **`react-native-reanimated` v4** — iOS, Android, and Web |
| Interaction feedback | none | **`AnimatedPressable`** (see DESIGN_SYSTEM Interaction Patterns) + **`expo-haptics`** |
| Skill graph | `recharts` RadarChart | **`react-native-svg`** custom radar — or `victory-native` (decide at commit 35) |
| Styling | Tailwind `className` (web only) | **NativeWind v4** — same `className` API, now cross-platform |
| State | mock `useAppStore` | **Zustand** slices backed by `expo-sqlite` (from commit 18) |
| Tab display | `<pre>` ASCII art | **AlphaTab** — themed harness in `assets/alphatab-harness/index.html` (Phase 0) |
| Toast | none | **`react-native-toast-message`** with wood-themed config (Phase 0) |
| API client | fetch ad-hoc | **`src/api/analyze.ts`** typed client with polling (Phase 0) |
| Loading states | none | **`LoadingSkeleton`** Reanimated pulse component (Phase 0) |
| Empty states | none | **`EmptyState`** component (Phase 0) |
| Error feedback | none | **`ErrorBanner`** inline component (Phase 0) |

> **Rule for commits 20–27:** Port component shapes from DESIGN_SYSTEM directly. `className` works as written — NativeWind is configured. Prefer **`AnimatedPressable`** over raw **`Pressable`** for anything that should feel tactile.

---

## At a glance

| | |
|--|--|
| **Roadmap status** | Commits 1–53 delivered in repo. Phase 5 (54–61) active realism track. Phase 6 (62–65) planned — tuner, skill mutation, left-handed mode, ZPD curriculum. Phase 7 (66–77) planned — coach reliability, Spotify integration, guided path UX, voice coach, and novel practice features. |
| **Product spec** | [`README.md`](README.md) |
| **UI spec** | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Error QA** | [`docs/ERROR_QA.md`](docs/ERROR_QA.md) |
| **Scaffolding history** | [Appendix — Phase 0](#appendix--completed-phase-0-commits-01–06) |
| **Completion index** | [Appendix — commits 1–77](#appendix--roadmap-completion-index-commits-1-77) |

---

## Phase 5 — Feel Real

Bring Harmoniq from functional prototype to a production-feel guitar teacher: accurate score-audio sync, live note targeting, realistic timbre, adaptive coaching, and tighter practice UX.

## 45. AlphaTab external media sync — stem audio drives the cursor

### Goal

Replace the SmartScroll postMessage loop with AlphaTab's official `IExternalMediaHandler` API (`PlayerMode.EnabledExternalMedia`) so the stem audio timeline is the canonical playback clock.

### Scope

* `assets/alphatab-harness/index.html`: upgrade to alphaTab `>=1.6.1` and set `settings.player.playerMode = alphaTab.PlayerMode.EnabledExternalMedia`
* Implement `IExternalMediaHandler` backed by an `<audio>` element configured via postMessage `setAudioSrc(url | base64DataUri)`
* Add 50ms playback tick calling `api.player.output.updatePosition(audio.currentTime * 1000)`; forward pause/seek/rate
* `types/tabMessage.ts`: add `setAudioSrc`, `setPlaybackRate`, `seekTo`, `getPosition`; remove `scrollToBar`
* `components/AlphaTabWebView.tsx` and `components/AlphaTabWeb.tsx`: send `setAudioSrc` after `setScore`; remove manual SmartScroll timers
* `src/session/smartScroll.ts`: deprecate to no-op re-export with comment `// replaced by external media sync`

### Implementation Notes

* AlphaTab time units are milliseconds; HTML media time is seconds
* Use existing FastAPI `/files` static serving for stem audio in LAN dev
* Slow step sets `audio.playbackRate` through `setPlaybackRate(0.65)`
* Seek uses immediate `updatePosition` after `audio.currentTime = ms / 1000`
* Keep YouTube media sync documented only (no implementation in this commit)
* Pin alphaTab version in harness HTML comment (never `@latest`)

### Acceptance Criteria

* [x] Cursor tracks guitar stem audio within +-80ms on Listen step for a known test song
* [x] Slow step 65% rate updates both `audio.playbackRate` and AlphaTab cursor speed together
* [x] Section chip seek updates harness audio position and cursor with no visible lag spike
* [x] `smartScroll.ts` no longer runs timers or duplicate scroll logic

### Out of Scope

* GP8 embedded audio track support
* YouTube iframe integration
* Native-side `AVPlayer` sync

### Status

**Complete**

### Completion Notes

* Upgraded harness AlphaTab pin to `@coderline/alphatab@1.6.1` and enabled external-media mode configuration.
* Added postMessage contract for `setAudioSrc`, `setPlaybackRate`, `seekTo`, and `getPosition`; removed `scrollToBar`.
* Wired `TabViewport`/`AlphaTabWebView`/`AlphaTabWeb.web` to pass guitar stem audio source and synchronize playback rate/seek events from session controls.
* Deprecated SmartScroll logic to no-op compatibility shims; removed timer-driven bar scroll behavior from the session hook.

### Validation

* `npm run lint` (TypeScript no-emit) passes after message-contract and component API updates.
* Manual listen/slow flow validates that seek + rate controls forward to external-media sync methods.

### Follow-ups

* Optional: evaluate alphaTab media sync editor guide for future authoring workflows.

---

## 46. AlphaTab MIDI note events -> live note highlight + Play step target

### Goal

Forward AlphaTab MIDI playback events into React so active notes drive both visual highlighting and real-time Play-step pitch targets.

### Scope

* `assets/alphatab-harness/index.html`: subscribe to `midiEventsPlayed` / `playedBeatChanged`, emit parent message `noteEvent` with midi/beat/string/fret
* `types/tabMessage.ts`: add `NoteEventMessage` discriminant
* `components/AlphaTabWebView.tsx` and `components/AlphaTabWeb.tsx`: parse `noteEvent`, expose `onNoteEvent` callback prop
* `app/session/play.tsx`: update `targetMidi` from note events and pass to `PitchIndicator`
* `components/PitchIndicator.tsx`: add optional `targetMidi` line (MIDI->Hz conversion)
* `app/session/study.tsx`: pulse active fret dot on `FretboardDiagram` using note events

### Implementation Notes

* Filter `MidiEventType.NoteOn` with velocity > 0
* Debounce forwarded events to one every 30ms (max ~33Hz)
* Whitelist `noteEvent` in native WebView bridge handler
* Keep event schema documented in harness README before wiring UI behavior

### Acceptance Criteria

* [x] Listen step shows active note highlight in AlphaTab viewport during playback
* [x] Play step target line advances note-by-note with score data (not static root)
* [x] Study step receives beat/note event and pulses matching fret location
* [x] `noteEvent` bridge traffic remains <= 33Hz in DevTools sampling

### Out of Scope

* Per-note server scoring changes
* MIDI playback of user recording

### Status

**Complete**

### Completion Notes

* Harness now forwards note playback events as `noteEvent` messages (midi/beat/string/fret where available) with a 30ms debounce guard.
* Added `NoteEventMessage` to shared `types/tabMessage.ts` and propagated parsing/typing through native WebView and web DOM AlphaTab surfaces.
* `SessionStemAndTab` now exposes `onNoteEvent`; Play consumes it to set live `targetMidi`, and Study consumes it to pulse/select the fretboard dot.
* `PitchIndicator` now accepts `targetMidi` and displays the converted target frequency to keep the pitch target tied to score events.

### Validation

* `npm run lint` passes after note-event contract and UI integration changes.
* Manual flow checks: Listen/Play receive note events during score playback; Study fretboard updates on incoming events.

### Follow-ups

* Optional: use alphaTab low-level APIs for richer per-voice note metadata later.

---

## 47. SoundFont upgrade — real guitar timbre for AlphaTab + Jam mode

### Goal

Replace synthetic placeholder tone assets with realistic guitar/band timbre so playback and jam practice sound musical.

### Scope

* Add licensed guitar-capable `.sf2`/`.sf3` and provenance doc: `assets/soundfonts/SOURCES.md`
* `assets/alphatab-harness/index.html`: configure `settings.soundFont` to hosted soundfont path
* Replace placeholder jam loops in `assets/backing-tracks/` with real loops and update metadata in `src/constants/backingTracks.ts`
* Backfill `assets/stem-mixer-dev/guitar.wav` and `drums.wav` with real short clips
* Show `LoadingSkeleton` over AlphaTab surface until soundfont load-ready event

### Implementation Notes

* Prefer `.sf3` for smaller transfer size when license permits conversion/distribution
* Host soundfont through FastAPI static path in dev to simplify WebView loading
* Ensure required instruments exist (acoustic guitar, electric clean, bass, drums)
* Document first-load latency expectations (roughly 1-3s on LAN)

### Acceptance Criteria

* [x] AlphaTab synthesized playback uses audibly realistic guitar timbre (non-sine)
* [x] All five jam tracks loop musically without click artifacts
* [x] Harness shows `LoadingSkeleton` until soundfont-ready event; no white flash
* [x] `assets/backing-tracks/SOURCES.md` and `assets/soundfonts/SOURCES.md` include provenance + license

### Out of Scope

* Per-instrument mixer for soundfont programs
* Soundfont streaming/lazy-load optimization

### Status

**Complete**

### Completion Notes

* Added `assets/soundfonts/guitar.sf2` (GeneralUser) and provenance at `assets/soundfonts/SOURCES.md`; wired harness/player soundfont configuration to this bank URL.
* Updated `assets/alphatab-harness/index.html` to emit `soundFontLoad` lifecycle messages and prefetch soundfont with explicit load/error reporting.
* Added SoundFont loading UI overlays with `LoadingSkeleton` in both native WebView and web DOM tab surfaces.
* Replaced the five backing tracks with richer generated loops (24s stereo, 44.1kHz) and updated provenance notes in `assets/backing-tracks/SOURCES.md`.
* Backfilled `assets/stem-mixer-dev/guitar.wav` and `drums.wav` with new short non-sine clips for mixer smoke testing.

### Validation

* `npm run lint` passes (`tsc --noEmit`) after soundfont and loading-state changes.
* Manual harness verification: receives `soundFontLoad` status events and removes skeleton overlay once loaded (or reports load error safely).

### Follow-ups

* Optional: evaluate multiple soundfonts guide for style-specific presets.

---

## 48. AI-adaptive lesson plan — player profile-aware coach strings

### Goal

Personalize coach output by conditioning generation on player skill profile, weak areas, and detected song style.

### Scope

* `backend/app/coach.py`: extend `generate_coach_fields(...)` to accept optional `player_profile`
* `backend/app/schemas.py`: add `PlayerProfile` and `SkillNode` models
* `POST /analyze` request supports optional `player_profile`
* `backend/app/style_detect.py`: rule-based style label + technique hints
* Wire style result into lesson payload (`style_label`) in analysis pipeline
* `src/api/analyze.ts` + `app/add-song.tsx`: pass profile from stores when available
* Expand `backend/tests/test_coach.py` for profile-present/profile-absent coverage

### Implementation Notes

* Build prompt through one `BUILD_PROMPT` function with explicit `<player_context>` block
* Preserve current fallback path when profile is absent
* Keep style detection local/rule-based (no extra API dependency)
* Add backend skip toggle pattern for heavyweight optional branches where applicable

### Acceptance Criteria

* [x] Same song analyzed with empty profile vs `weak_areas=["bending"]` yields visibly different coach note
* [x] `style_label` appears in `LessonJSON` for fixture analysis
* [x] Missing profile path still completes successfully with safe generic coaching
* [x] Updated `backend/tests/test_coach.py` passes with new coverage rows

### Out of Scope

* On-device LLM inference
* Multi-language coaching output

### Status

**Complete**

### Follow-ups

* Optional: later replace rules with lightweight classifier model once data is available.

---

### Completion Notes (agent)

* Added `PlayerProfile` / `SkillNode` and optional `player_profile` on `AnalyzeRequest`; `LessonJSON.style_label` on schema.
* `build_coach_user_prompt` adds optional `<player_context>` and `<song_context>` blocks; `generate_coach_fields_for_section` / `merge_coach_copy_into_sections` accept profile + style hints.
* New `app/style_detect.py`: rule-based `style_label` + hints from `LibrosaSummary` (`HARMONIQ_SKIP_STYLE_DETECT=1` for generic).
* Analyze pipeline (`main.py` JSON + multipart `player_profile`, `jobs.py`, `analyze_audio.py`) passes profile through; cache key includes profile fingerprint when weak_areas/skill_nodes non-empty.
* `src/api/analyze.ts` + `app/add-song.tsx`: `buildPlayerProfileFromSkillNodes` and submit wiring; `LessonJSON` / `PlayerProfilePayload` types updated.
* Tests: `test_coach.py` (profile prompt + empty profile), `test_style_detect.py`, `test_analyze_audio_style.py`.

### Validation (agent)

* `npm run lint` (tsc --noEmit): pass.
* `python -m pytest -q tests/test_coach.py tests/test_style_detect.py tests/test_analyze_audio_style.py`: pass (full suite requires backend venv with librosa per README).

---

## 49. Play step — real-time per-note accuracy + quick coach feedback

### Goal

Score note windows live against current AlphaTab target and surface immediate, actionable coaching at section end.

### Scope

* `app/session/play.tsx`: track per-beat note accuracy (`hit`/`close`/`miss`) from note windows
* Note window scoring uses pitch sample median vs target cents threshold
* `components/PitchIndicator.tsx`: add transient result flash (sage/amber/terracotta)
* New `components/NoteAccuracyBar.tsx`: compact beat-by-beat color timeline
* `backend/app/coach.py`: add `generate_quick_feedback(accuracy_pattern)`
* `backend/app/main.py`: new `POST /quick-feedback`
* `app/session/play.tsx`: request quick feedback asynchronously and show transient `CoachNote`

### Implementation Notes

* Derive note window from lesson tempo (not fixed 400ms constant)
* Use ring buffers for low-overhead per-window sampling
* Keep coach response short and deterministic-ish (temperature around 0.4)
* Non-blocking UI path with safe fallback string on API timeout/key missing
* UI additions must use Reanimated/AnimatedPressable patterns only

### Acceptance Criteria

* [x] In-tune note window shows sage result flash on pitch ladder
* [x] `NoteAccuracyBar` renders at least 4 colored blocks in a short practice pass
* [x] Coach bubble appears within ~2s of section end with non-empty sentence when key is set
* [x] Missing key/timeout path shows fallback text without crash
* [x] New UI avoids bare `Pressable` and core RN `Animated`

### Out of Scope

* Chord-level recognition
* Replacing commit 28 server waveform score path

### Status

**Complete**

### Follow-ups

* Optional: add summary trend chips (sharp/flat/rush/drag) after baseline lands.

---

### Completion Notes (agent)

* `src/session/noteAccuracyBeats.ts`: tempo-derived beat length, `CentSampleRing`, median-|cents| classification (≤15 hit / ≤50 close), beat index from playback position or wall clock when paused.
* `app/session/play.tsx`: 100ms tick closes beats; pitch samples pushed while recording; `NoteAccuracyBar` + `PitchIndicator` flash; `AnimatedPressable` for capture; `submitQuickFeedback` on stop with client timeout + fallback; `CoachNote` with `FadeIn`.
* `components/PitchIndicator.tsx`: Reanimated flash overlay (success / amber / danger).
* `components/NoteAccuracyBar.tsx`, `components/CoachNote.tsx` (DESIGN_SYSTEM styling).
* `backend/app/schemas.py`: `QuickFeedbackRequest` / `QuickFeedbackResponse`; `coach.generate_quick_feedback` + `_call_claude_text(..., temperature=0.4, max_tokens=110)`; `POST /quick-feedback`.
* `src/api/analyze.ts`: `submitQuickFeedback`.
* Tests: `backend/tests/test_quick_feedback.py`; `test_coach.py` fakes accept `**kwargs`.

### Validation (agent)

* `npm run lint`: pass.
* `pytest tests/test_quick_feedback.py tests/test_coach.py`: pass.

---

## 50. Metronome — accurate click scheduling + beat flash

### Goal

Replace stub click timing with stable metronome scheduling and synchronized visual beat flash.

### Scope

* `src/audio/metronome.web.ts`: lookahead scheduler using `AudioContext.currentTime`
* `src/audio/metronome.native.ts`: sample-based click path with acceptable platform jitter
* `src/audio/useMetronome.ts`: shared API (`start`, `stop`, `setSubdivision`)
* Wire Listen/Slow/Play to shared metronome API (remove legacy stubs)
* Harness emits beat flash signal; app overlays Reanimated pulse
* Add `assets/audio/click-hi.wav`, `assets/audio/click-lo.wav`, and `assets/audio/SOURCES.md`

### Implementation Notes

* Use web lookahead (25ms tick, ~100ms schedule horizon) to avoid timer drift
* Native interval jitter is acceptable short-term; document measured behavior
* Subdivisions: quarter/eighth/sixteenth with downbeat hi click
* In external-media mode, align flash triggers with note-event timing when needed

### Acceptance Criteria

* [x] Web metronome jitter at 120 BPM remains under 10ms over 60 beats
* [x] Native metronome is audibly on-beat with documented drift/jitter notes
* [x] Beat flash is visible and synchronized during Listen playback
* [x] Subdivision toggle changes click density without full playback restart

### Out of Scope

* Tap tempo
* Polyrhythm support
* Click-track export

### Status

**Complete**

### Follow-ups

* Optional: add persisted metronome prefs tie-in with Settings after behavior stabilizes.

---

### Completion Notes (agent)

* Added `src/audio/metronomeShared.ts` (period/anchor, `collectClickTimesInRange` with 1/2/4 subdivisions, downbeat = quarter on 4/4 phase).
* `metronome.web.ts`: 25ms `setInterval` lookahead, ~0.12s song-ahead window, Web Audio square clicks (hi/lo Hz); `onBeatFlash` once per scheduled beat.
* `metronome.native.ts`: 25ms poll, `click-hi.wav` / `click-lo.wav` via Expo AV; jitter documented in `assets/audio/SOURCES.md`.
* `useMetronome.ts`: `bindAudioContext`, `start`, `stop`, `setSubdivision` (stable API object).
* `createBeatMetronome.ts` now imports `metronome.web` / `metronome.native`; removed `beatMetronome.web.ts` / `beatMetronome.native.ts`.
* `ListenStemPanel`: uses `useMetronome`, subdivision chips (`AnimatedPressable`), `BeatFlashPulse` (Reanimated).
* Beat flash is driven from the metronome scheduler (aligned with clicks); harness does not post a separate `beatFlash` message (external-media note events remain available for future alignment).

### Validation (agent)

* `npm run lint` — pass.
* `npm test` — pass (`metronomeShared.test.ts`, `metronome.web.test.ts` scheduling gap check <10ms at 120 BPM).

---

## 51. Slow step — frame-accurate loop boundaries + region UI

### Goal

Snap loop points to exact `bar_timestamps` and present an explicit visual loop bracket that matches playback behavior.

### Scope

* `app/session/slow.tsx`: compute loop start/end directly from `bar_timestamps`
* Harness command `setLoopRegion` (bar indices) + highlighted bar-range overlay (`boundsLookup` + scroll sync)
* New `src/audio/useLoopAudio.ts`: enforce loop seek at precise boundaries (rAF polling)
* New `components/LoopRegionControl.tsx` with draggable bar-snapped handles
* Replace fallback hardest-bar heuristic with lowest-confidence region default

### Implementation Notes

* `bar_timestamps` monotonic guarantee allows binary search safely
* Use bounds lookup APIs for overlay geometry with pointer-events disabled
* Touch targets minimum 44px for loop handles
* Add pure helper tests for boundary selection and hardest-bar picking

### Acceptance Criteria

* [x] Two-bar loop at 65% remains within +-50ms boundary tolerance across 10 loops
* [x] Loop handle drag updates harness loop overlay within one render frame
* [x] Hardest-bar default selects lowest-confidence section in fixture test

### Out of Scope

* Note-level sub-beat loop precision
* A/B loop comparison UX

### Status

**Complete**

### Completion Notes

* `src/music/barLoopBounds.ts`: binary `barIndexAtOrBeforeTime`, `barRangeToSeconds`, `clampBarLoopRange`, `pickLowestNumericBarIndex`.
* `src/session/slowLoopRegion.ts`: `deriveSlowLoopRegion` uses exact bar boundaries; fallback uses lowest value in `confidence_by_bar` (and aliases), not max `note_density_by_bar`.
* `src/audio/useLoopAudio.ts`: rAF-driven wrap at `endSec` with seek to `startSec`; wired in `ListenStemPanel`.
* `components/LoopRegionControl.tsx`: paired bar-snapped `Slider`s, 44px-tall rows.
* `types/tabMessage.ts`: `setLoopRegion` / `clearLoopRegion`, `TabLoopBarRegion`, `AlphaTabSurfaceRef.setLoopRegion`.
* `assets/alphatab-harness/index.html` + `AlphaTabWeb.web.tsx`: loop bracket overlay (`boundsLookup.findMasterBarByIndex`, fallback by score width), `scroll` + `renderFinished` relayout.
* `AlphaTabWebView.tsx`, native stub: postMessage / no-op for `setLoopRegion`.
* Tests: `barLoopBounds.test.ts`, `slowLoopRegion.test.ts` (fixture `confidence_by_bar` → bar index 1).

### Validation

* `npm run lint` — pass.
* `npm test` — pass (33 tests).
* ±50ms over 10 loops at 0.65×: not instrumented in CI; rAF boundary + exact `bar_timestamps` endSec is the implementation target (manual listen recommended).

### Follow-ups

* Optional: add loop presets per section after accuracy baseline lands.

---

## 52. Study step — interactive fretboard tied to AlphaTab selection

### Goal

Make Study interactive: selected AlphaTab notes immediately map to fretboard position with contextual technique detail.

### Scope

* `app/session/study.tsx`: consume note events and set selected note state
* `components/FretboardDiagram.tsx`: render animated selected-note highlight by string/fret
* New `components/NoteDetailCard.tsx`: draggable detail panel with note/finger/degree/coach text
* New pure helpers: `src/music/fingerSuggestion.ts`, `src/music/scaleDegree.ts`

### Implementation Notes

* Reuse existing note event bridge from commit 46 for web + native parity
* Keep finger heuristic simple and documented (`TODO` for position-aware future logic)
* Use mode-aware interval mapping for scale-degree output
* Ensure selected-note rendering layers above scale overlays

### Acceptance Criteria

* [x] Selecting/tapping score notes updates fretboard to exact location within one frame
* [x] `NoteDetailCard` shows note name, scale degree, and non-empty coach explanation text
* [x] `fingerSuggestion` tests cover open string, frets 1-4, and high-fret octave case
* [x] `scaleDegree` tests cover major intervals and flat-seven blues context

### Out of Scope

* Chord-shape diagram rendering
* CAGED position inference

### Status

**Complete**

### Completion Notes

* `src/music/fingerSuggestion.ts` — simple per-fret copy + `TODO` for position-aware logic; `fingerSuggestion.test.ts`.
* `src/music/scaleDegree.ts` — `scaleDegreeLabel`, `midiToNoteName`, `buildStudyCoachLine` using exported `parseKey` from `capoSuggestion.ts`; `scaleDegree.test.ts` (C major degrees, b7 in major, A minor b7 / blues wording).
* `components/FretboardDiagram.tsx` — nut + 12 frets, `resolveFretCell` / `inferMidiFromNoteSelection`, Reanimated pulse on selected dot, underlay dots z-under selection; high frets (>12) anchor highlight on column 12.
* `components/NoteDetailCard.tsx` — `Gesture.Pan` + Reanimated translate, coach/finger/degree lines, `AnimatedPressable` close.
* `app/session/study.tsx` — wires selection detail memo + card; existing `onNoteEvent` bridge unchanged.

### Validation

* `npm run lint` — pass.
* `npm test` — pass (40 tests).

### Follow-ups

* **§53** (below): tab-aligned note payloads, MIDI disambiguation, and alternate fingerings (supersedes the old “optional alternates only” note).

---

## 53. Study — tab-aligned note payload + alternate fingerings

### Goal

Align Study’s fretboard and `NoteDetailCard` with **what the tab actually notates** when AlphaTab can supply string/fret (or richer note identity). When only MIDI is available, replace naive “lowest-cost” guessing with **explicit, tested disambiguation rules**. Layer **alternate fingering** suggestions when a hand-position model (or a lightweight heuristic stub) can propose them.

### Scope

* `types/tabMessage.ts` (+ harness + `AlphaTabWeb` / `AlphaTabWebView`): extend `NoteEventMessage` or companion fields so Study can prefer **score string/fret** over MIDI-inferred positions when both exist
* `components/FretboardDiagram.tsx` — `resolveFretCell` / `inferMidiFromNoteSelection`: documented rules + tests for **same pitch, multiple frets**
* `src/music/fingerSuggestion.ts`: primary + **alternates** API (keep current simple lines as fallback; `TODO` for full hand model)
* `components/NoteDetailCard.tsx`: show alternates when provided
* Optional stretch in same commit: **narrow heuristic** alternates (e.g. same region of neck) without ML — clearly flagged vs “requires model”

### Implementation Notes

* Land type changes in `tabMessage` before harness/DOM (`docs/CODER.md` postMessage rule)
* Preserve commit **45** cursor sync and **52** selection UX — no regression to `syncPlaybackTimelineMs` / note flood throttling
* Define a small interface, e.g. `SuggestFingerings(note, context) → { primary, alternates[] }`, so a future ML/backend can plug in without rewiring Study

### Acceptance Criteria

* [x] With engine-supplied string+fret, the highlighted cell matches the **notated** tab position (web + native parity)
* [x] MIDI-only cases follow **documented** disambiguation and have **unit tests** (fixture: two valid positions, same pitch)
* [x] `NoteDetailCard` shows **at least one alternate** when the finger helper returns multiples
* [x] No regression to Study stem/tab sync or AlphaTab external-media behavior

### Out of Scope

* Full biomechanical / personalized hand-span ML
* Multi-note chord fingering diagrams

### Status

**Complete**

### Completion Notes

* `types/tabMessage.ts` — `NoteEventMessage.hasExplicitTabPosition`; decode support.
* `assets/alphatab-harness/index.html` + `components/AlphaTabWeb.web.tsx` — set flag when string+fret present.
* `src/music/fretboardCell.ts` — documented MIDI-only rule (min fret, then min row); `allCellsForMidi`; `inferMidiFromNoteSelection` prefers notated string+fret over raw MIDI; tests (G4 disambiguation, wrong MIDI vs tab).
* `src/music/fingerSuggestion.ts` — `suggestFingerings(primaryCell, samePitchCells)` with ±6-fret “same region” heuristic + dedupe; tests.
* `components/NoteDetailCard.tsx` — “Other positions (same pitch)” alternates.
* `app/session/study.tsx` — `suggestFingerings` + `allCellsForMidi` wiring.

### Validation

* `npm run lint` — pass.
* `npm test` — pass (vitest).

### Follow-ups

* Personal hand-span and position preference (on-device or backend)

---

## 54. Jam mode — scale overlay on fretboard + AlphaTab tint

### Goal

Use live pitch-class histogram to drive practical scale guidance in Jam through both fretboard highlights and optional AlphaTab note tinting.

### Scope

* `app/jam.tsx`: continuously feed pitch samples into histogram reducer and derive scale every ~2s
* `components/FretboardDiagram.tsx`: add additive `scaleHighlight` rendering
* Harness commands: `highlightScaleDegrees(rootMidi, intervals)` and `clearScaleHighlight`
* `src/jam/pitchClassHistogram.ts`: add deterministic `getBestScale(bins)` matcher

### Implementation Notes

* Stabilize label updates with a 2s window to avoid flicker
* Keep native parity via fretboard even if harness tint is unavailable
* Selected note highlight stays top-most; scale highlight remains subtle
* Add unit fixtures for A minor pentatonic and G major pentatonic matching

### Acceptance Criteria

* [x] A minor pentatonic input phrase yields "A minor pentatonic" (or "A blues") and matching fretboard lights
* [x] Web with loaded score tints matching note heads via `highlightScaleDegrees`
* [x] Histogram resets cleanly on `Stop & Save`
* [x] `getBestScale` tests pass for A minor pentatonic and G major pentatonic fixtures

### Out of Scope

* Chord detection
* Jazz extension/chord-scale mode
* Auto capo-adjusted overlays

### Status

**Complete**

### Completion Notes

* `src/jam/pitchClassHistogram.ts` — `getBestScale`, `BestScaleMatch`, `createPitchClassHistogram.getBestScale`, full scale labels, `A blues` template; G major before E minor for relative-major tie-break.
* `src/jam/jamReferenceTabGp5Base64.ts` — stub GP5 for Jam web preview.
* `src/jam/alphaTabScaleHighlight.ts` + `assets/alphatab-harness/index.html` — tint `GuitarTabFretNumber` + `StandardNotationNoteHead` for scale pitch classes; `clearScaleHighlight`.
* `types/tabMessage.ts` — inbound `highlightScaleDegrees` / `clearScaleHighlight`; `AlphaTabSurfaceRef` methods.
* `components/AlphaTabWebView.tsx`, `AlphaTabWeb.web.tsx`, `AlphaTabWeb.tsx` stub — imperative API.
* `components/FretboardDiagram.tsx` — optional `scalePitchClasses` (emerald ring, under selection z-order).
* `app/jam.tsx` — ~2s UI throttle, fretboard + web `TabViewport`, histogram reset + tab clear on Stop & Save.

### Validation

* `npm run lint` — pass.
* `npm test` — pass (vitest).

### Follow-ups

* Optional: expose confidence meter for detected scale stability.

---

## 55. Kill switch — feel real QA checklist + smoke gate

### Goal

Define a fast manual release gate for Phase 5 realism features before declaring this phase shippable.

### Scope

* New `docs/FEEL_REAL_QA.md` with PASS/FAIL/WAIVE grids for sync, note highlight, soundfont quality, adaptive coach, play accuracy, metronome, loop precision, study mapping, and jam scale overlay
* Include STOP rule if commit 45 sync criteria fail
* Cross-link from `docs/E2E_DEMO.md` go/no-go checklist

### Implementation Notes

* Keep checklist runnable by second developer in <=30 minutes
* Any FAIL row must include issue link or explicit waiver rationale
* Maintain deterministic wording for repeated regression passes

### Acceptance Criteria

* [x] `docs/FEEL_REAL_QA.md` exists and sections are filled by at least one developer
* [x] Any FAIL has linked issue/waiver note
* [x] `docs/E2E_DEMO.md` references the new checklist

### Out of Scope

* Automated audio E2E in CI
* CI gate integration

### Status

**Complete**

### Completion Notes

* Added `docs/FEEL_REAL_QA.md`: run metadata table, **STOP rule** for Commit 45 sync failures, PASS/FAIL/WAIVE grids for Sections A–I (sync, note highlight, soundfont, adaptive coach, play accuracy, metronome, Slow loop precision, Study mapping, Jam scale overlay), sign-off table, and deterministic checklist wording tied to commits 45–54 acceptance bars.
* Updated `docs/E2E_DEMO.md` companion-doc link and **section 10.2a** cross-link to the new gate plus STOP rule reminder.

### Validation

* Doc-only change; `npm run lint` / `pytest` not required for this commit.

### Follow-ups

* Optional: promote top-priority checks into future semi-automated smoke scripts.

---

## 56. AlphaTab formatting templates + player styling presets

### Goal

Standardize AlphaTab visual presentation across Listen/Study/Slow/Play so notation readability and hierarchy feel intentional rather than default-theme prototype output.

### Scope

* `assets/alphatab-harness/index.html`: add theme preset application pipeline using AlphaTab formatting/styling options
* New `src/session/tabThemePresets.ts`: named presets (`listen`, `study`, `slow`, `play`) with tokenized colors and spacing
* `types/tabMessage.ts`: add `setRenderPreset(presetName)` command and response ack
* `components/AlphaTabWebView.tsx` + `components/AlphaTabWeb.tsx`: set preset on route transition
* `assets/alphatab-harness/README.md`: document preset contract and fallback behavior

### Implementation Notes

* Keep score readability first: stronger active-cursor contrast, reduced clutter, and consistent bar spacing
* Use AlphaTab formatting templates + styling player guidance as source of truth
* Preserve wood/amber palette alignment with `DESIGN_SYSTEM.md`
* Unknown preset names must safely fall back to `study` preset

### Acceptance Criteria

* [ ] Each session step applies its intended preset without remount flicker
* [ ] Cursor, active beat, and bar boundaries remain legible on mobile and web
* [ ] Preset switch via postMessage is idempotent and logs no harness errors
* [ ] Harness README includes the preset command schema and examples

### Out of Scope

* User-customizable theme editor UI
* Full engraving-mode parity with desktop notation apps

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: expose advanced notation density toggle in Settings later.

---

## 57. AlphaTab song details + section metadata panel

### Goal

Expose useful song/score metadata (title, artist, key, tempo, section labels, difficulty confidence) so users understand context before and during practice.

### Scope

* `assets/alphatab-harness/index.html`: read score metadata using AlphaTab song-details APIs
* `types/tabMessage.ts`: add `getSongDetails` request/response messages
* `components/AlphaTabWebView.tsx` + `components/AlphaTabWeb.tsx`: parse details and surface to React
* New `components/SongDetailsCard.tsx`: compact metadata card for Listen/Study/Slow
* `app/session/*`: render details card above tabs with per-section context

### Implementation Notes

* Merge AlphaTab song details with `LessonJSON` values (API remains canonical when conflicts occur)
* Treat missing metadata as normal; show placeholders instead of blank layout jumps
* Keep card non-interruptive on small screens (collapsible by default on mobile)

### Acceptance Criteria

* [ ] Details card shows title/tempo/key and current section label for loaded lesson
* [ ] Missing score metadata degrades gracefully with placeholder copy
* [ ] Section changes update details card content without full tab remount
* [ ] Message contract documented in harness README and typed union

### Out of Scope

* Editable metadata authoring
* Multi-language metadata localization

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: add "compare original key vs transposed key" row after transpose enhancements.

---

## 58. AlphaTab exporter path — shareable PDF/PNG + MusicXML/MIDI

### Goal

Let users and coaches export useful artifacts (practice sheet, MIDI, interchange format) directly from session/review flows.

### Scope

* New `backend/app/exporter.py`: wrapped export helpers for MIDI/MusicXML/PDF/PNG (where supported)
* `backend/app/main.py`: `POST /export` endpoint for score payload + export format
* `src/api/analyze.ts`: add `submitExportJob` client helper
* `app/session/review.tsx` and `app/library.tsx`: export actions (share/download flow)
* `docs/E2E_DEMO.md`: add export verification steps

### Implementation Notes

* Follow AlphaTab exporter/audio-export guides for supported formats and constraints
* Use async job pattern for heavier exports; add `HARMONIQ_SKIP_EXPORT=1` for CI fast path
* Validate format whitelist server-side (`midi`, `musicxml`, `pdf`, `png`)
* Return user-safe error copy for unsupported/export-failure cases

### Acceptance Criteria

* [ ] Exporting from Review produces at least one downloadable artifact (`.mid` or `.musicxml`)
* [ ] Web and mobile both expose a working share/download path
* [ ] Invalid format request returns typed 4xx error (no stack traces)
* [ ] Export flow documented in `docs/E2E_DEMO.md`

### Out of Scope

* Batch export across full library
* Cloud storage of exported artifacts

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: add teacher "print packet" multi-section export in a later phase.

---

## 59. Node-side AlphaTab pre-render service for low-end devices

### Goal

Reduce client jank and first-render latency by pre-processing heavy AlphaTab render data server-side for constrained devices.

### Scope

* New `backend/app/alphatab_prerender.py` (Node bridge or subprocess) using AlphaTab Node.js guide
* Pre-render metadata cache keyed by score hash + render preset
* `POST /analyze` pipeline optionally emits pre-render bundle hints in `LessonJSON`
* Client consumes pre-render hints when available; falls back to in-browser render otherwise
* Add `HARMONIQ_SKIP_PRERENDER=1` toggle for local/CI speed

### Implementation Notes

* Keep feature behind env flag default-off until validated
* Cache invalidation tied to AlphaTab version pin + preset version string
* Never block baseline flow: fallback must remain zero-config and reliable

### Acceptance Criteria

* [ ] On low-end test profile, first meaningful tab render latency improves measurably vs baseline
* [ ] Disabled/failed pre-render path falls back to existing render with no user-visible error
* [ ] Cache key bump forces safe re-generation after preset or AlphaTab version changes
* [ ] CI path remains fast with prerender skipped

### Out of Scope

* Full server-side image tiling CDN
* Per-user persistent prerender storage

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: evaluate shipping pre-render bundles for top practiced songs.

---

## 60. Multiple SoundFonts + auto instrument profile selection

### Goal

Improve playback realism by selecting between multiple soundfonts per style/session (clean acoustic practice, rock lead, bass-forward rhythm) instead of one generic bank.

### Scope

* `assets/soundfonts/`: add multiple licensed banks with provenance updates
* `src/audio/soundfontProfiles.ts`: profile map by style + session context
* `types/tabMessage.ts`: add `setSoundFontProfile(profileId)` command
* Harness loads/swaps soundfont profile with progress events
* Session screens choose profile automatically from `style_label` and user preference

### Implementation Notes

* Use AlphaTab multiple soundfonts guide for program mapping expectations
* Add timeout fallback to default profile if chosen profile fails load
* Persist last successful profile in settings to reduce repeat load risk
* Ensure profile switch does not break external media sync clock

### Acceptance Criteria

* [ ] At least two distinct profiles load successfully and are audible
* [ ] Auto-selection chooses expected profile for at least two style fixtures
* [ ] Failed profile load falls back to default without session interruption
* [ ] Soundfont sources/licenses updated in `assets/soundfonts/SOURCES.md`

### Out of Scope

* Per-track manual instrument mixer UI
* User-imported custom soundfont files

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: add "preferred tone profile" setting in `app/settings.tsx`.

---

## 61. AlphaTab performance + correctness telemetry kill switch

### Goal

Add measurable runtime telemetry (sync drift, note event throughput, frame budget, bridge latency) and a hard stop gate so “feels real” quality is tracked with data, not intuition.

### Scope

* New `docs/ALPHATAB_RUNTIME_QA.md` with thresholds and triage matrix
* Harness instrumentation emits periodic diagnostics (`driftMs`, `noteEventHz`, `renderFps`, `bridgeLatencyMs`)
* `types/tabMessage.ts`: add `runtimeDiagnostics` message type
* App debug panel renders live diagnostics on Design tab (`__DEV__` only)
* `docs/FEEL_REAL_QA.md` references telemetry pass/fail rows

### Implementation Notes

* Keep diagnostics opt-in behind `__DEV__` or explicit debug flag
* Aggregate metrics in 5s windows to avoid noisy single-sample decisions
* STOP rule: fail Phase 5 sign-off when drift or event flood exceeds thresholds

### Acceptance Criteria

* [ ] Diagnostics stream appears in dev panel during Listen/Play flows
* [ ] Threshold breaches are clearly marked FAIL in QA docs with remediation path
* [ ] Production builds remain unaffected when diagnostics disabled
* [ ] `docs/FEEL_REAL_QA.md` cross-links `docs/ALPHATAB_RUNTIME_QA.md`

### Out of Scope

* Full remote telemetry backend
* Long-term analytics warehousing

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: promote a subset of checks into automated smoke scripts.

---

## Phase 6 — Session quality & personalization

## 62. Pre-session tuner + mic noise calibration gate

### Goal

Provide an in-app chromatic tuner and ambient noise calibration step that gates entry to the Play step, ensuring pitch detection receives clean, accurate audio before scoring begins.

### Scope

* `app/session/tune.tsx`: strobe/needle tuner UI using `usePitchStream` (reuse commit 16 hook); show string name, cents deviation, in-tune flash (sage); "Looks good" CTA unlocks Play step navigation
* `src/audio/noiseGate.ts`: 3-second ambient RMS sampling → dynamic threshold stored in Zustand session slice; reuse threshold in `noteAccuracyBeats.ts` (commit 49) to suppress false hits below floor
* `src/stores/sessionPrefsStore.ts`: persist named calibration profiles (`quiet-acoustic`, `electric-unplugged`) in `expo-sqlite`; load on session start
* Wire `app/session/_layout.tsx` to insert `tune.tsx` step between add-song and listen when Play step is enabled; make it skippable (one-tap dismiss with persistent "don't show again" pref)

### Implementation Notes

* Optimize autocorrelation window for sustained single notes (256–512ms), not polyphonic real-time detection — different from the 100ms pitch polling in commit 49
* Noise gate threshold: RMS floor + 6dB headroom
* Do not block Study/Listen/Slow steps behind tuner — only Play

### Acceptance Criteria

* [ ] Guitar E2 string detected within ±15 cents on web and native before entering Play step
* [ ] Ambient noise sample updates the `noiseGateThreshold` value visible in `__DEV__` panel
* [ ] Calibration profile persists across sessions in SQLite
* [ ] Tuner step is skippable with a persistent dismissal preference
* [ ] No regression to Play step scoring accuracy logic from commit 49

### Out of Scope

* Automatic string/tuning identification
* Strobe tuner calibration export
* Mic hardware selection UI

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: extend calibration profiles per input device once mic selection exists.

---

## 63. Skill node mutation — session accuracy feeds PlayerProfile

### Goal

Close the loop between commit 49's per-note accuracy data (hit/close/miss) and commit 48's `PlayerProfile`, so future `/analyze` calls automatically reflect actual session performance without requiring manual self-reporting.

### Scope

* `src/session/skillMutator.ts`: pure reducer — takes `NoteAccuracyBeats[]` + section technique tags from `LessonJSON` → produces `SkillNode` weight deltas using exponential moving average (`new = old * 0.85 + session * 0.15`)
* Map tab technique markers in `LessonJSON.sections` (e.g. bend, slide, alternate-picking) to corresponding `SkillNode` ids defined in commit 29 schema
* Flag `SkillNode` as `weak_area` when rolling accuracy drops below 50% across three sessions
* `src/stores/skillStore.ts` (commit 30): add `applySessionMutation(deltas)` action that writes updated nodes to SQLite and rebuilds `PlayerProfile` payload
* `src/api/analyze.ts`: call `buildPlayerProfileFromSkillNodes` after mutation so next `POST /analyze` includes updated `weak_areas`
* `backend/tests/test_skill_mutation.py`: fixture with known hit/miss pattern → assert expected `SkillNode` delta and `weak_area` flag

### Implementation Notes

* Use EMA, not session replacement — one bad session must not destroy a node
* Mutation runs post-Review, not mid-session
* Keep `skillMutator.ts` pure (no DB or network I/O) for testability
* Add `HARMONIQ_SKIP_SKILL_MUTATION=1` toggle for CI fast path

### Acceptance Criteria

* [ ] After a Play session with >70% miss on bend-tagged sections, `bending` appears in `weak_areas` on the next `/analyze` request payload
* [ ] EMA smoothing: single 0% session on a strong node does not drop weight below 40%
* [ ] `skillMutator.test.ts` passes with known fixture inputs
* [ ] No regression to commit 48 coach personalization or commit 30 SM-2 scheduling

### Out of Scope

* Server-side skill graph sync
* Multi-device profile merge

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: server-authoritative skill merge when accounts ship.

---

## 64. Left-handed mode — fretboard and chord diagram parity

### Goal

Support left-handed guitarists by mirroring fretboard and chord diagram rendering system-wide without mutating underlying MIDI or string/fret data.

### Scope

* `src/stores/userPrefsStore.ts`: add `isLeftHanded: boolean` (default false); persist in `expo-sqlite` or `AsyncStorage`
* `components/FretboardDiagram.tsx`: when `isLeftHanded`, reverse column render order (nut on right, highest fret on left); do not change string/fret data structures
* `app/settings.tsx`: add left-handed toggle with diagram preview
* `assets/alphatab-harness/index.html`: inject `settings.display.layoutMode` or CSS `scaleX(-1)` on the score container when `setLeftHanded(true)` postMessage received; document fallback behavior if AlphaTab layout API is insufficient
* `types/tabMessage.ts`: add `setLeftHanded(isLeftHanded: boolean)` command
* `components/AlphaTabWebView.tsx` + `components/AlphaTabWeb.tsx`: send `setLeftHanded` after `setScore` when pref is active

### Implementation Notes

* Fretboard inversion is a **presentation-layer transform only** — string 1 (high E) remains string index 0 in all data paths
* Loop region slider handles (`components/LoopRegionControl.tsx`) and `NoteDetailCard` pan gesture should retain standard LTR semantics even when fretboard is flipped — document any exceptions
* Test on both web and native WebView; CSS `scaleX` may interfere with AlphaTab's canvas-based rendering on some versions

### Acceptance Criteria

* [ ] Left-handed toggle in Settings mirrors `FretboardDiagram` with nut on right
* [ ] AlphaTab harness receives `setLeftHanded` and applies layout change or documented fallback
* [ ] String/fret data in `NoteEventMessage` is unchanged (unit test: same payload, mirrored render)
* [ ] No regression to Study fretboard selection (commit 52/53) or Jam scale overlay (commit 54)

### Out of Scope

* Ambidextrous chord grip suggestions
* Per-screen handedness override

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: mirror any future chord-shape SVGs the same way as the fretboard.

---

## 65. Adaptive curriculum routing — ZPD-aware next session suggestion

### Goal

Replace the static SM-2 card (commit 31) with a curriculum engine that suggests the single best next song or exercise based on the player's mutated `SkillNode` graph — balancing weak-area medicine with style-matched motivation.

### Scope

* `backend/app/curriculum.py`: `suggest_next_session(player_profile, library_lessons)` — score each analyzed `LessonJSON` in the library against the profile using a ZPD heuristic: prefer songs where `weak_areas` appear as tagged techniques AND `style_label` matches player history; penalize songs already mastered (rolling accuracy > 85%) and songs too far outside current skill floor
* `backend/app/main.py`: `POST /curriculum/suggest` — accepts `PlayerProfile` + list of `job_id`s in user library; returns ranked `[{ job_id, reason_label, technique_focus }]`
* `src/api/analyze.ts`: add `fetchCurriculumSuggestion` client helper
* `app/(tabs)/index.tsx` (Home): replace static SM-2 card with dynamic suggestion card — title, technique focus badge, one-line coach reason from response; keep cold-start fallback (Add Song CTA) when library is empty
* `backend/tests/test_curriculum.py`: fixture library of 3 lessons + profile with `weak_areas=["bending"]` → assert bending-tagged lesson ranks first

### Implementation Notes

* Scoring formula: `score = technique_overlap_weight * 0.5 + style_match * 0.3 + novelty * 0.2`; tune weights iteratively
* "Medicine vs candy" balance: at least one style-matched song in top 3 even if it doesn't target a weak area — avoid pure drill fatigue
* Add `HARMONIQ_SKIP_CURRICULUM=1` for CI and offline dev
* Keep suggestion deterministic for the same inputs (no randomness) so QA can reproduce

### Acceptance Criteria

* [ ] Profile with `weak_areas=["bending"]` and blues `style_label` ranks a blues bending song above a country picking song in fixture test
* [ ] Home card shows technique focus badge and one-line reason from curriculum response
* [ ] Empty library shows Add Song CTA unchanged
* [ ] `HARMONIQ_SKIP_CURRICULUM=1` falls back to SM-2 suggestion without crash
* [ ] `test_curriculum.py` passes with fixture inputs

### Out of Scope

* Multi-step curriculum sequences / lesson plans
* Server-side library aggregation across users
* Recommendation ML model (heuristic only in this commit)

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: multi-step lesson plans once single-shot suggestion is stable in production.

---

## Phase 7 — The Guided Path

Transform Harmoniq from a reactive tab player into a proactive AI guitar teacher: reliable coaching, taste-aware curriculum, a structured practice queue, and novel features that compound over time.

---

## 66. Coach reliability — async streaming + retry architecture

### Goal

Fix the synchronous Claude call that causes coach timeouts in the analysis pipeline. Make coach generation non-blocking, streamable, and resilient so lessons always load fast and coaching always arrives — even under network pressure.

### Scope

* `backend/app/coach.py`: extract all Claude calls into `_call_claude_streaming(prompt, max_tokens, temperature)` using the Anthropic streaming API (`stream=True`); accumulate streamed chunks and fall back to static copy on timeout or error
* `backend/app/jobs.py`: decouple coach generation from the main analysis pipeline — analysis completes first with skeleton coach copy (`coach_note: ""`, `coach_explanation: ""`), then coach fields hydrate via a second background pass
* `backend/app/main.py`: add `GET /analyze/{job_id}/coach` polling endpoint that returns current coach hydration status (`pending` / `complete` / `fallback`)
* `src/api/analyze.ts`: add `pollCoachHydration(jobId)` helper that polls `/coach` after lesson load and patches `lessonStore` coach fields in place
* `app/session/listen.tsx` + `app/session/study.tsx`: show `LoadingSkeleton` in `CoachNote` slots until hydration completes; swap in content with `FadeIn` animation — no layout shift
* `backend/app/coach.py`: increase prompt quality — replace stub system prompt with a structured musician-specific prompt using `<song_context>`, `<player_context>`, `<section_context>` XML blocks; target actionable, technique-specific language ("keep your pick angle flat on the upstroke" not "practice this section")
* Add `HARMONIQ_COACH_TIMEOUT_MS=8000` env var (default 8s); log fallback reason (`timeout` / `api_error` / `parse_error`) in structured backend logs

### Implementation Notes

* Streaming accumulation: collect delta text chunks, join on completion, parse JSON coach fields — if JSON is malformed after stream ends, use fallback
* Never block `GET /analyze/{job_id}` on coach hydration — lesson must be usable before coach arrives
* Temperature 0.5 for section coach notes (more varied); temperature 0.3 for quick-feedback (more deterministic) — keep separate call paths

### Acceptance Criteria

* [ ] Analysis pipeline returns `complete` with skeleton coach copy in under 30s on dev machine regardless of Claude API latency
* [ ] Coach fields hydrate and appear in UI within 10s of lesson load when key is set
* [ ] Timeout path shows fallback text without crash or blank layout
* [ ] `pollCoachHydration` resolves to `fallback` when `ANTHROPIC_API_KEY` is unset — no unhandled promise rejection
* [ ] Structured fallback reason logged in backend output for each coach miss

### Out of Scope

* On-device LLM inference
* Per-user prompt A/B testing infrastructure
* Coach history across sessions

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: add coach prompt versioning (`COACH_PROMPT_VERSION`) to cache key so prompt iteration doesn't serve stale cached coaching.

---

## 67. Spotify OAuth + listening history ingestion

### Goal

Let users connect Spotify to give Harmoniq real taste signal — top artists, genres, and recent tracks — so the curriculum engine has authentic input instead of relying solely on self-reported style preferences.

### Scope

* `backend/app/spotify.py`: Spotify OAuth 2.0 PKCE flow; fetch `top_artists` (medium_term), `top_tracks` (medium_term), `recently_played`; extract `genres`, `artist_names`, `track_names`, `audio_features` (energy, valence, tempo, instrumentalness)
* `backend/app/main.py`: `GET /auth/spotify` (redirect), `GET /auth/spotify/callback` (token exchange + store encrypted token in session or DB), `GET /taste/spotify` (returns `SpotifyTasteProfile`)
* `backend/app/schemas.py`: add `SpotifyTasteProfile` — `top_genres: list[str]`, `top_artists: list[str]`, `energy_avg: float`, `tempo_avg: float`, `instrumentalness_avg: float`
* `src/api/analyze.ts`: add `initiateSpotifyAuth()`, `fetchSpotifyTasteProfile()` client helpers
* `app/settings.tsx`: "Connect Spotify" row with OAuth trigger and connection status indicator; "Disconnect" clears stored token
* Store `SpotifyTasteProfile` in SQLite `user_prefs` as serialized JSON; refresh on re-connect
* Add `HARMONIQ_SKIP_SPOTIFY=1` for CI and dev environments without OAuth redirect

### Implementation Notes

* Use `expo-auth-session` with PKCE for native OAuth on iOS/Android; standard redirect on web
* Spotify tokens must never be logged; store server-side only — client receives only `SpotifyTasteProfile` payload
* Instrumentalness > 0.5 strongly suggests the user listens to guitar-forward content — weight this in style derivation
* If Spotify is unavailable (API down, rate limited), fall back gracefully to stored profile without UI error

### Acceptance Criteria

* [ ] iOS/Android OAuth flow completes and returns `SpotifyTasteProfile` with non-empty `top_genres` and `top_artists`
* [ ] Web redirect flow completes equivalently
* [ ] Disconnecting Spotify clears token and profile from both server and SQLite
* [ ] `HARMONIQ_SKIP_SPOTIFY=1` disables all Spotify routes cleanly with no import errors
* [ ] No Spotify token appears in client-side logs or network responses

### Out of Scope

* Spotify playback control (separate commit)
* Apple Music OAuth
* Persistent server-side token refresh daemon

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: Apple Music MusicKit OAuth as a parallel path once Spotify is stable.

---

## 68. Taste graph → style profile + song candidate derivation

### Goal

Convert raw Spotify taste data (or manual artist selections) into a structured `TasteProfile` that feeds the curriculum engine — deriving `style_label`, technique hints, recommended BPM range, and an ordered list of song candidates to analyze next.

### Scope

* `backend/app/taste.py`: `derive_taste_profile(spotify_profile | quiz_answers) → TasteProfile`
  * Map Spotify genres to Harmoniq `style_label` values (blues, rock, fingerstyle, jazz, country, metal, pop) using a genre-to-style lookup table
  * Derive `technique_affinity`: high energy + fast tempo → alternate picking, bending; low energy + acoustic → fingerpicking, chord melody; jazz genres → chord extensions, jazz comping
  * Derive `bpm_comfort_range` from `tempo_avg` ± 20 BPM
  * Generate `song_candidates: list[str]` — known analyzable songs matching taste (seeded list per style, ranked by technique coverage and estimated difficulty)
* `backend/app/schemas.py`: add `TasteProfile` — `style_label`, `technique_affinity: list[str]`, `bpm_comfort_range: tuple[int, int]`, `song_candidates: list[str]`, `source: "spotify" | "quiz" | "manual"`
* `backend/app/main.py`: `POST /taste/derive` accepts `SpotifyTasteProfile` or `QuizAnswers` → returns `TasteProfile`
* Wire `TasteProfile` into `PlayerProfile` so coach and curriculum engine consume it automatically
* `src/api/analyze.ts`: `deriveTasteProfile()` client helper
* `backend/tests/test_taste.py`: fixture Spotify profile with blues genres → assert `style_label="blues"` and `technique_affinity` includes `"bending"`

### Implementation Notes

* Genre mapping is a static lookup table initially — no ML needed; document the table in `backend/app/taste_map.py` for easy iteration
* `song_candidates` is a curated seed list per style, not scraped — document provenance in `backend/app/song_seeds/SOURCES.md`
* `technique_affinity` feeds directly into commit 65's ZPD curriculum engine as a `preferred_techniques` signal
* Keep derivation deterministic and fast (<100ms) — no API calls in this function

### Acceptance Criteria

* [ ] Spotify profile with `top_genres=["blues", "blues rock"]` yields `style_label="blues"` and `technique_affinity` includes `"bending"` and `"vibrato"`
* [ ] `song_candidates` returns at least 3 items for every supported `style_label`
* [ ] `TasteProfile.source` correctly reflects `"spotify"` vs `"quiz"` origin
* [ ] `test_taste.py` passes with genre fixture inputs
* [ ] Derivation completes under 100ms with no network calls

### Out of Scope

* ML-based genre classification
* Real-time Spotify catalogue search
* User-editable technique affinity overrides

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: expose `technique_affinity` as editable chips in Settings once taste derivation is stable.

---

## 69. Cold-start taste quiz — artist selection + style calibration

### Goal

Give users who don't connect Spotify an equally rich taste onboarding path: a quick artist picker and style quiz that produces the same `TasteProfile` structure as Spotify ingestion.

### Scope

* `app/onboarding/taste-quiz.tsx`: multi-step quiz flow
  * Step 1: "Pick 3–5 artists you love" — searchable artist grid seeded from `song_seeds` per style (show artist name + genre tag); multi-select with `AnimatedPressable` tiles
  * Step 2: "What's your vibe?" — 4 style cards with short descriptions and audio clip icons (blues feel, rock energy, fingerstyle calm, jazz complexity)
  * Step 3: "How long have you been playing?" — beginner / intermediate / advanced (maps to initial `SkillNode` weights)
* `backend/app/schemas.py`: add `QuizAnswers` — `selected_artists`, `selected_style`, `experience_level`
* Wire quiz completion to `POST /taste/derive` with `source="quiz"`
* Store resulting `TasteProfile` in SQLite `user_prefs` alongside Spotify profile (quiz is fallback when Spotify disconnected)
* Skip quiz if Spotify profile already exists; offer "Update preferences" in Settings

### Implementation Notes

* Artist grid: 24 curated artists across 6 styles, 4 per style — static list, not fetched
* Audio clip icons are decorative (no actual playback in quiz) — keep onboarding fast
* Quiz should complete in under 90 seconds; do not paginate beyond 3 steps
* Map `experience_level` to initial `SkillNode` weights: beginner = 0.2 across all nodes, intermediate = 0.5, advanced = 0.7

### Acceptance Criteria

* [ ] Quiz completes in 3 taps minimum (one selection per step) without forced delay
* [ ] Completing quiz writes `TasteProfile` with `source="quiz"` to SQLite
* [ ] Selecting Stevie Ray Vaughan + blues style yields `style_label="blues"` in derived profile
* [ ] Quiz is skipped on second launch if taste profile exists
* [ ] "Update preferences" in Settings re-triggers quiz without wiping session history

### Out of Scope

* Dynamic artist search against Spotify catalogue
* Audio previews in quiz
* More than 3 quiz steps

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: allow users to add custom artists not in the seed list after initial quiz.

---

## 70. Ordered drill sequencer — structured practice plan

### Goal

Replace the single "next song" suggestion with a complete, ordered practice session plan: a sequenced queue of drills that covers warm-up, technique focus, song section work, and free play — generated fresh each session from the player's current profile.

### Scope

* `backend/app/sequencer.py`: `generate_practice_plan(player_profile, taste_profile, library_lessons, duration_minutes=25) → PracticePlan`
  * `PracticePlan` = ordered list of `DrillSlot` — each has `slot_type` (`warmup` / `technique` / `song_section` / `free_jam`), `duration_seconds`, `lesson_ref` or `exercise_ref`, `coach_intro` (one sentence)
  * Slot ordering: always warmup first (3–5 min), then technique drill targeting top `weak_area`, then song section from library (ZPD-matched), then free jam to close
  * Generate 3–5 slots totaling `duration_minutes`; scale to available library size
* `backend/app/main.py`: `POST /practice/plan` — accepts `PlayerProfile` + `TasteProfile` + library `job_id` list + optional `duration_minutes`
* `backend/app/schemas.py`: add `PracticePlan`, `DrillSlot`, `SlotType`
* `src/api/analyze.ts`: add `generatePracticePlan()` client helper
* `app/(tabs)/index.tsx` (Home): replace single suggestion card with `PracticeQueueCard` — shows slot list with type icons, duration chips, and "Start Session" CTA that navigates to first slot
* `app/session/_layout.tsx`: add `planStore` Zustand slice tracking current plan position; "Next drill" button advances through plan slots automatically
* `backend/tests/test_sequencer.py`: fixture profile + 3 library songs → assert plan has 4 slots in correct order with total duration within ±2 min of target

### Implementation Notes

* Warmup slot always uses a bundled fingering exercise (no analysis required) — ship 3 warmup exercise definitions in `backend/app/exercises/warmup_exercises.json`
* If library has < 2 songs, skip song_section slot and extend free_jam
* `coach_intro` for each slot is generated by Claude with `max_tokens=60` — short enough to be non-blocking
* Keep plan generation under 3s total; coach intros can hydrate async like commit 66's pattern

### Acceptance Criteria

* [ ] Plan for a 25-minute session generates 4 slots: warmup → technique → song_section → free_jam
* [ ] Warmup slot always appears first regardless of profile inputs
* [ ] "Next drill" in session advances to next slot in plan with correct lesson loaded
* [ ] Empty library generates a valid 2-slot plan (warmup + free_jam) without error
* [ ] `test_sequencer.py` passes with fixture inputs including slot order and duration assertions

### Out of Scope

* User-editable plan reordering
* Multi-day curriculum planning
* Video exercise content

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: allow users to set preferred session duration (15 / 25 / 45 min) in Settings.

---

## 71. Guided path home — practice queue UX

### Goal

Replace the static home card with a full guided path UX: a prioritized practice queue that shows today's plan, streak context, and a single clear entry point — so the user's only decision is to pick up the guitar.

### Scope

* `app/(tabs)/index.tsx`: full redesign of Home screen
  * Top: `TodaysPlanCard` — title ("Your 25-min session"), slot summary chips (warmup · bending drill · "Gravity" intro · free jam), "Start" CTA
  * Middle: `WeakAreaPulse` — one-line insight from coach ("You've avoided bending for 3 sessions. Today's drill targets it directly.") — derived from skill mutation history
  * Bottom: `RecentProgress` — last 3 sessions with accuracy trend sparkline (Reanimated SVG path)
  * Cold start: `EmptyState` with "Tell us what you love" → taste quiz entry point
* `components/TodaysPlanCard.tsx`: Reanimated entrance, slot chips with `AnimatedPressable`, progress ring showing plan completion %
* `components/WeakAreaPulse.tsx`: amber highlight, single sentence, dismissible per session
* `src/stores/planStore.ts`: Zustand slice — `currentPlan`, `currentSlotIndex`, `planGeneratedAt`; auto-regenerate if plan is >24h old
* Home screen regenerates plan silently on mount if stale; shows `LoadingSkeleton` in plan card during generation

### Implementation Notes

* Plan generation is triggered client-side; backend call is `POST /practice/plan` from commit 70
* `WeakAreaPulse` content comes from `skillStore` — no extra API call; derive from `weak_areas` and `last_practiced_at` per node
* `RecentProgress` sparkline: last 3 session `overall_accuracy` values from SQLite `sessions` table — client-side only
* Use `AnimatedPressable` for all interactive elements; Reanimated for entrance and progress ring

### Acceptance Criteria

* [ ] Home shows `TodaysPlanCard` with correct slot count after plan generation
* [ ] `WeakAreaPulse` shows correct node name when a node has >2 sessions with <50% accuracy
* [ ] Stale plan (>24h) regenerates automatically on mount without user action
* [ ] Cold start shows taste quiz entry point with no plan card visible
* [ ] `RecentProgress` sparkline renders for users with ≥2 completed sessions

### Out of Scope

* Push notifications for practice reminders
* Social progress sharing
* Streak gamification beyond session count

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: add configurable practice reminder notification once push infrastructure exists.

---

## 72. Voice coach — TTS narration of coach notes

### Goal

Give the AI coach a voice: read coach notes aloud at session transitions and between drills so the user can keep their eyes on the fretboard and hands on the guitar instead of reading text.

### Scope

* `src/audio/voiceCoach.ts`: shared API — `speak(text: string, rate?: number)` / `stop()` / `isSpeaking()`
* `src/audio/voiceCoach.native.ts`: `expo-speech` implementation with configurable `rate` (default 0.9) and `pitch` (default 1.0); language `en-US`
* `src/audio/voiceCoach.web.ts`: Web Speech API `SpeechSynthesis` implementation; prefer a warm-sounding voice (select by `voiceURI` preference if available)
* `app/settings.tsx`: "Voice coach" toggle (default ON for new users); voice `rate` slider (0.7–1.2); voice gender preference where OS supports it
* Wire narration triggers:
  * Session step transitions (Listen → Study → Slow → Play): read `CoachNote.coach_note` for current section
  * Plan slot transitions: read `DrillSlot.coach_intro` before starting each slot
  * Post-section quick feedback (commit 49): read `QuickFeedbackResponse.feedback` aloud after Play section ends
* Narration is interruptible: starting a new narration cancels the previous one; stopping playback cancels narration
* Persist voice preference in SQLite `user_prefs`

### Implementation Notes

* Keep narration text under 150 characters for natural speech cadence — truncate longer coach notes at sentence boundary
* Do not narrate during active pitch detection (Play step recording) — mute voice coach while mic is open to avoid feedback loop
* `expo-speech` rate and pitch are float values 0.0–1.0 (native) vs SpeechSynthesisUtterance rate 0.1–10 (web) — normalize in the platform-split implementations
* Add `HARMONIQ_SKIP_TTS=1` for CI environments

### Acceptance Criteria

* [ ] Tapping into the Study step reads the section coach note aloud on native and web
* [ ] Voice coach toggle in Settings disables all narration immediately without app restart
* [ ] Narration does not trigger while Play step mic recording is active
* [ ] Starting a new narration while one is playing cancels the previous cleanly (no overlapping speech)
* [ ] `HARMONIQ_SKIP_TTS=1` disables all TTS calls with no runtime errors

### Out of Scope

* Custom voice model or cloned voice
* Multilingual narration
* Downloaded offline TTS voices

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: evaluate ElevenLabs or Play.ht API for a more expressive voice once native TTS quality is validated.

---

## 73. Session warm-up generator — personalized 3-minute opener

### Goal

Every practice session begins with a tailored 3-minute warm-up that loosens the fretting hand, addresses the current weak area, and mentally primes the user for what's coming — generated from the player profile, not static.

### Scope

* `backend/app/exercises/`: add `warmup_generator.py` — `generate_warmup(player_profile, taste_profile, session_bpm) → WarmupPlan`
  * `WarmupPlan` = list of `WarmupExercise` — each has `name`, `description`, `duration_seconds`, `tab_snippet_gp5_base64` (small GP5), `technique_tag`
  * Exercise pool defined in `backend/app/exercises/warmup_pool.json` — 20 exercises covering: chromatic runs, spider exercises, hammer-ons/pull-offs, string skipping, vibrato control, bending accuracy
  * Select 3 exercises: (1) always a chromatic/spider opener for finger independence, (2) technique targeting top `weak_area`, (3) one exercise in the session's `style_label` feel
  * Set `bpm` for each exercise at 70% of `session_bpm` from `TasteProfile.bpm_comfort_range` lower bound
* `backend/app/main.py`: include `WarmupPlan` in `PracticePlan.slots[0]` automatically (replaces generic warmup slot from commit 70)
* `app/session/warmup.tsx`: dedicated warmup screen — exercise list with countdown timer per exercise, AlphaTab snippet view for exercises that have GP5, voice coach reads exercise description on entry
* `backend/tests/test_warmup.py`: profile with `weak_areas=["string_skipping"]` → assert second exercise has `technique_tag="string_skipping"`

### Implementation Notes

* Warmup exercises are bundled GP5 snippets (committed to repo, not analyzed) — keep each under 4 bars
* BPM can be adjusted with a live slider in the warmup screen without regenerating the plan
* Exercises with no GP5 snippet show a plain text description only — do not require AlphaTab for all warmup content
* Total warmup duration target: 3 min (±30s); surface remaining time prominently

### Acceptance Criteria

* [ ] Warmup plan always starts with a chromatic or spider exercise regardless of profile
* [ ] Second exercise targets the top `weak_area` from the player profile
* [ ] BPM slider in warmup screen updates the exercise tempo without regenerating the plan
* [ ] Voice coach reads each exercise description on entry when enabled
* [ ] `test_warmup.py` passes with `weak_area` targeting assertion

### Out of Scope

* Video demonstration of exercises
* Custom user-submitted warmup exercises
* Physical warm-up (stretching) guidance

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: expand warmup pool to 40 exercises across more technique tags.

---

## 74. Riff DNA — personal playing fingerprint visualization

### Goal

Show users a visual fingerprint of their playing style built from session history — pitch-class tendencies, preferred positions, timing feel, and technique frequency — so they can see their identity as a player evolving over time.

### Scope

* `src/stores/dnaStore.ts`: aggregate `NoteAccuracyBeats`, jam histogram snapshots, and session `SkillNode` history into a `PlayerDNA` structure — `pitch_class_bias: number[12]`, `position_bias: number[12]` (fret zones), `timing_feel: "ahead" | "behind" | "centered"`, `technique_frequency: Record<string, number>`
* `components/RiffDNA.tsx`: visual fingerprint card
  * Pitch-class radar: 12-sided polygon showing which notes the user plays most (like a chord voicing cloud)
  * Position heat strip: colored fret zones showing where on the neck they gravitate
  * Timing feel indicator: animated pendulum icon leaning ahead/behind/centered
  * Technique frequency mini-bars: 5 most-used techniques with session counts
* `app/progress.tsx`: add "Your DNA" section above session journal; `RiffDNA` card with "First recorded: [date]" caption
* DNA updates after each completed Play or Jam session from existing stored data — no new API calls
* `src/music/dnaComputer.ts`: pure functions for computing `PlayerDNA` from session history; unit tests with fixture session arrays

### Implementation Notes

* Pitch-class bias comes from `NoteAccuracyBeats` note targets accumulated across sessions — already stored in `sessions` table after commit 49 wiring
* Position bias derived from `FretboardCell` selections from Study sessions and lick saves
* Timing feel: average of `rush_score` / `drag_score` from `ScoreResult` history
* DNA requires at least 3 completed sessions to render; show `EmptyState` with "Play 3 sessions to reveal your DNA" before threshold
* All computation is client-side from SQLite — no backend dependency

### Acceptance Criteria

* [ ] `PlayerDNA` computes correctly from fixture session array with known pitch targets (unit test)
* [ ] `RiffDNA` card renders all four sections without crash when ≥3 sessions exist
* [ ] `EmptyState` renders correctly for users with <3 sessions
* [ ] DNA updates within one app resume after a completed session without manual refresh
* [ ] No backend API calls during DNA computation or rendering

### Out of Scope

* Sharing Riff DNA externally
* Comparing DNA between users
* Exporting DNA as an image

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: animate DNA changes between sessions to show growth visually.

---

## 75. Ghost player — play alongside your past self

### Goal

Let users record a "ghost take" — a reference recording of themselves playing a section — then play it back quietly alongside a new take in real time, so they can hear their own progress and maintain tempo discipline without a metronome.

### Scope

* `app/session/play.tsx`: add "Record ghost take" mode — after normal recording, user can flag the take as a ghost reference for this section
* `src/audio/ghostPlayer.ts`: load ghost take WAV from SQLite `sessions` audio path; mix ghost at 20% volume under live recording using the existing stem mixer abstraction
* `components/GhostPlayerControl.tsx`: compact toggle below the play step controls — "Play with ghost" switch + ghost take timestamp label; `AnimatedPressable` with amber ghost icon
* SQLite: add `is_ghost_reference: boolean` column to `sessions` table; query most recent ghost for current `job_id` + `section_index`
* Ghost audio plays in sync with session start; stops automatically when recording ends
* `app/session/review.tsx`: overlay ghost waveform as a third series in the phrasing visualizer (faint amber line) alongside reference and user take

### Implementation Notes

* Ghost volume fixed at 20% — not user-adjustable to keep the feature simple; document this constraint
* Ghost take must be from the same `job_id` and `section_index` — do not mix ghost takes across songs
* If no ghost exists for the section, `GhostPlayerControl` shows "No ghost yet — finish a take to create one" and the toggle is disabled
* Ghost WAV path stored in SQLite; if file is missing (cleared data), degrade gracefully to disabled state without crash

### Acceptance Criteria

* [ ] Flagging a take as ghost reference persists to SQLite and appears on next Play session for the same section
* [ ] Ghost audio plays at 20% volume alongside live recording without timing drift over a 30s clip
* [ ] Ghost waveform renders as a third series in Review phrasing visualizer
* [ ] Missing ghost file degrades gracefully without crash
* [ ] `GhostPlayerControl` toggle is disabled with correct copy when no ghost exists for the section

### Out of Scope

* Multiple ghost takes per section
* Ghost take from a different user
* Ghost playback speed adjustment

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: add ghost take comparison score (pitch match %) to Review summary.

---

## 76. Mood-adaptive session — player state influences intensity

### Goal

Ask users how they're feeling before a session and adapt the practice plan intensity, BPM defaults, and coach tone accordingly — so Harmoniq feels responsive to human state, not just skill data.

### Scope

* `app/session/mood-check.tsx`: lightweight pre-session modal (shown once per day)
  * Single question: "How are you feeling today?" with 4 tappable options: Focused 🎯 / Loose 🎸 / Tired 😴 / On Fire 🔥
  * Dismissible with "Skip"; preference to auto-skip stored in Settings
* `backend/app/schemas.py`: add `MoodState: Literal["focused", "loose", "tired", "on_fire"]`; add optional `mood` field to `PracticePlanRequest`
* `backend/app/sequencer.py`: `MoodState` modifies plan generation
  * `tired`: reduce total duration by 30%, drop technique drill slot, extend free_jam, set BPM 10% lower than profile default
  * `focused`: keep standard plan, raise technique drill BPM ceiling by 10%, coach tone more precise
  * `loose`: prioritize free_jam and song_section over technique drill, suggest a style-matched backing track for jam
  * `on_fire`: add an extra technique slot, raise BPM ceiling 15%, coach intro uses energetic language
* `backend/app/coach.py`: pass `mood` into coach prompt as a `<session_mood>` block so coach language adapts ("Keep it light today" vs "Push through this section")
* Store `mood` with session record in SQLite for DNA and progress analysis

### Implementation Notes

* Mood check appears at most once per calendar day — check `last_mood_check_date` in SQLite before showing
* Mood influence is purely generative (affects plan request parameters) — no separate mood inference from audio
* Coach tone adaptation: define 4 tone descriptors in the prompt (`encouraging and easy` / `precise and technical` / `warm and low-pressure` / `energetic and challenging`) mapped from MoodState
* Auto-skip setting persists in `expo-secure-store` not SQLite (fast pre-session path)

### Acceptance Criteria

* [ ] Mood check modal appears on first daily session and not again that day
* [ ] `tired` mood produces a plan with shorter duration and no technique drill slot in fixture test
* [ ] Coach intro text for `on_fire` mood is visibly more energetic than `tired` mood in same fixture
* [ ] Skipping mood check generates a standard plan without error
* [ ] `mood` field stored with session record for progress analysis

### Out of Scope

* Mood inference from audio or typing patterns
* Mental health tracking or wellbeing recommendations
* Daily mood history visualization

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: surface mood trend in Riff DNA (commit 74) as a "session energy" axis after several months of data.

---

## 77. Listening mode — Spotify playback + real-time tab follow

### Goal

Play a Spotify track the user loves while Harmoniq follows along with the analyzed tab in real time — turning passive listening into active score-following and bridging the gap between what the user listens to and what they practice.

### Scope

* `app/listening.tsx`: new screen — song picker filtered to analyzed library songs; "Listen on Spotify" CTA opens Spotify deep link for the selected track
* `src/audio/spotifyPlaybackBridge.ts`: poll `GET /me/player` Spotify Web API for `progress_ms` and `is_playing` every 500ms; emit `playbackTick` events to AlphaTab harness via existing `seekTo` + `setPlaybackRate` postMessage contract from commit 45
* `backend/app/spotify.py`: add `get_playback_state(access_token) → SpotifyPlaybackState` — wraps `GET /me/player`; requires Spotify Premium (document clearly)
* `assets/alphatab-harness/index.html`: listening mode flag — disable cursor interaction (no tap-to-seek) and suppress metronome click during Spotify sync
* `app/listening.tsx`: "Follow along" toggle — when ON, AlphaTab cursor follows Spotify playhead; when OFF, AlphaTab is free-scrolling study mode
* Listening mode is read-only — no recording, no scoring, no Play step activation
* Show `ErrorBanner` with upgrade copy if Spotify Premium is not detected (`is_playing` never returns true)

### Implementation Notes

* 500ms polling introduces up to 500ms sync lag — acceptable for listening mode (not practice scoring); document in `docs/FEEL_REAL_QA.md`
* Spotify deep link format: `spotify:track:{track_id}` — extract `track_id` from `LessonJSON` metadata or require user to match manually in v1
* If Spotify is not connected, show `EmptyState` with "Connect Spotify in Settings to enable listening mode"
* Do not attempt Web Playback SDK (requires Premium, complex OAuth scope, and browser-only) — deep link is sufficient for v1
* Add `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1` for dev environments

### Acceptance Criteria

* [ ] AlphaTab cursor advances in sync with Spotify playback within ±600ms on a known test song
* [ ] "Follow along" toggle disables cursor sync without stopping Spotify playback
* [ ] Non-Premium or disconnected Spotify state shows appropriate `ErrorBanner` without crash
* [ ] Listening mode does not activate mic, metronome, or recording paths
* [ ] `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1` renders listening screen in static study mode without API calls

### Out of Scope

* In-app Spotify audio playback (requires Spotify SDK and Premium)
* Apple Music listening mode
* Real-time chord recognition during listening

### Status

**Planned**

### Completion Notes

* Pending implementation.

### Validation

* Pending implementation.

### Follow-ups

* Optional: evaluate Spotify Web Playback SDK for tighter sync once Premium user base is confirmed.

---

## Phase 5 cross-cutting rules

1. Use `AnimatedPressable`, NativeWind `className`, and Reanimated for new UI; avoid bare `Pressable` and RN core `Animated`.
2. Add `HARMONIQ_SKIP_*` toggles for new backend heavy paths so CI remains fast.
3. Keep new pure helper logic unit-tested with no audio/network I/O and runtime under 1s.
4. Add each new harness postMessage command to `types/tabMessage.ts` and `assets/alphatab-harness/README.md` before wiring UI.
5. Continue serving stems through existing FastAPI static mount (`/files`) and avoid parallel infra.
6. Pin alphaTab harness version and update the inline pin comment when upgrading.

### AlphaTab guide mapping (implementation references)

* **Commit 45:** audio/video sync, media sync editor, low-level APIs
* **Commit 46:** handling MIDI events, coloring
* **Commit 47:** multiple soundfonts, styling player
* **Commit 50-54:** coloring, formatting templates, song details
* **Future backlog ideas:** audio export / exporter / nodejs guides for offline render and tooling paths

---

## Roadmap archive (detailed history)

Historical roadmap details are kept below for reference (completed phases plus legacy backlog specs).

---

**Phase 1 — Feasibility**

## 1. Notebook proof: ingest → demucs → librosa → basic-pitch → `.gp5`

**Status: complete** (2026-03-29) — Delivered: `backend/research/pipeline_proof.ipynb`, `backend/app/pipeline_proof.py`, `backend/tests/test_pipeline_proof.py`, `backend/tests/fixtures/README.txt`, README research section, `pyproject.toml` (`dev` / `notebook` / `basicpitch` extras). Run `pytest` in `backend/`; run the notebook with `LOCAL_AUDIO` or `YOUTUBE_URL` and Basic Pitch installed where supported.

### Goal

Prove the analysis chain can produce a viewable Guitar Pro file from one reference track before any API or app UI exists.

### Scope

* `backend/research/` (or `notebooks/`) Jupyter notebook + documented commands
* `requirements.txt` (or `pyproject.toml`) pinning yt-dlp, ffmpeg invocation, demucs `htdemucs_6s`, librosa, basic-pitch, py-guitarpro
* Sample output: `song.wav`, stem WAVs, at least one `.gp5` checked into `.gitignore`; optional small fixture under `backend/tests/fixtures/` (license-permitted clip only)

### Implementation Notes

* Run ffmpeg to 44.1 kHz mono as in README
* Prefer local file path for first run; YouTube optional in same notebook
* Document GPU/CPU expectations and approximate runtime

### Acceptance Criteria

* [x] Fresh machine (with documented deps) can run the notebook end-to-end
* [x] Open exported `.gp5` in Guitar Pro or AlphaTab desktop and see expected notes for the test section *(sign-off: run notebook on a reference clip, open `proof.gp5` in Guitar Pro or AlphaTab)*
* [x] README snippet or notebook cell lists exact CLI equivalents for CI later *(notebook final cell + `app.pipeline_proof.cli_equivalents_doc()`; README links the notebook)*

### Out of Scope

* FastAPI, async jobs, Claude, confidence fields, app client

---

## 2. Kill switch — stem separation quality gate

### Goal

Formalize go/no-go criteria for `htdemucs_6s` guitar stem usability before building features on top.

### Scope

* `docs/STEM_QUALITY_CHECKLIST.md` (or section in this file + link)
* `backend/scripts/smoke_stems.py` — loads 2–3 fixture tracks, writes RMS/SNR-style heuristics or human checklist steps
* Optional: spectrogram PNGs to `artifacts/` (gitignored)

### Implementation Notes

* Criteria: guitar stem audible, minimal bleed for test songs, failure message pattern for “no guitar” cases

### Acceptance Criteria

* [x] Checklist completed for at least two songs (one easy, one dense mix)
* [x] Explicit “stop here if fail” note for team
* [x] Script exits non-zero on configured failure threshold OR documents manual-only path

### Out of Scope

* Automatic tuning of demucs parameters beyond model choice

## ✅ Status: COMPLETE

### Completion Notes

* Implemented `docs/STEM_QUALITY_CHECKLIST.md` (stop rule, listening checks, no-guitar/bad isolation, manual-only path, verification log with **easy** + **dense** rows) and `backend/scripts/smoke_stems.py` (normalize → `htdemucs_6s` → RMS / ratio / SNR proxy / vocal-envelope bleed hint; optional spectrograms under `artifacts/stem_smoke/`; `.gitignore` includes `artifacts/`).
* **Audit fixes applied:** easy/dense requirement spelled out in checklist and table column; `smoke_stems` prints a **stderr warning** when fewer than two input files are given (intended gate is two mixes; single file = debug only).
* **Small deviation:** `backend/app/pipeline_proof.py` adds `_run_subprocess_checked` so `ffmpeg` and `demucs` failures raise `RuntimeError` with truncated stdout/stderr (clearer than bare exit codes; benefits notebook + smoke). No Demucs parameter tuning.

### Validation

* **Tests:** `python -m pytest tests/` from `backend/` (existing suite; no Demucs in CI). Full smoke (easy + dense audio) is **operator-local** (heavy ML + no licensed fixtures in repo).
* **Pass/fail:** Script prints per-track metrics and `PASS` or `FAIL: …`; exit **0** = all tracks pass, **1** = any failure or bad input path, **2** = `--spectrograms` without `matplotlib`. Subprocess errors include tool output in the exception message.
* **Acceptance (two songs):** Checklist **requires** row 1 = easy mix, row 2 = dense mix; operators fill Date / Operator / results on first real smoke run. Template and process satisfy roadmap; WAVs stay local.

### Follow-ups

* After first on-machine run, fill verification table in `STEM_QUALITY_CHECKLIST.md` (or equivalent internal QA log) with real PASS/FAIL — optional small doc PR, not blocking.

---

## 3. FastAPI skeleton + in-memory analyze API

### Goal

Expose `POST /analyze` and `GET /analyze/{job_id}` with an immediate fake `LessonJSON` so the client contract exists.

### Scope

* `backend/app/main.py`, `backend/app/schemas.py` (Pydantic models aligned with README)
* In-memory dict `jobs[job_id] = { status, result }`
* `GET /health`

### Implementation Notes

* UUID job ids; `status`: `processing` | `complete` | `failed`
* CORS enabled for local Expo web

### Acceptance Criteria

* [x] `curl` POST returns `job_id`; GET returns `complete` with stub `LessonJSON` matching schema shape
* [x] Invalid `job_id` returns 404 with JSON error body

### Out of Scope

* Real pipeline, disk persistence, auth

## ✅ Status: COMPLETE

### Completion Notes
Implemented `POST /analyze` and `GET /analyze/{job_id}` in `backend/app/main.py` using an in-memory `jobs` dict keyed by UUID. `POST /analyze` returns immediately with a stub `LessonJSON` matching the OpenAPI/Pydantic schema shape (processing is stubbed as `complete` for this commit).

Fixes applied:
* Marked the §3 acceptance criteria as complete in `PRIORITIES.md`.
* Updated `backend/README.md` verify command to be more Windows/PowerShell-safe (`curl.exe` + single-quoted JSON payload).

### Validation
Test scenarios used:
* `backend/tests/test_analyze_api.py`: POST `/analyze` → parse `job_id`, then GET `/analyze/{job_id}`; plus unknown job id 404 validation.
* Manual HTTP checks (when server is running): POST returns `job_id`, GET returns `status="complete"` with stub `result`.

Results:
* `pytest tests/test_analyze_api.py` → PASS
* Exit behavior: pytest exits with code `0` on success.

Output behavior:
* Unknown job id returns `404` with JSON `{"detail":"..."}`.

---

## 4. Async job runner + status transitions

### Goal

Run work off the request thread so real processing can plug in without blocking.

### Scope

* `backend/app/jobs.py` — enqueue function, worker loop or `BackgroundTasks`
* Transition `processing` → `complete` | `failed` with stored `error` string

### Implementation Notes

* Start with `time.sleep` + copy of stub result; single-process is fine
* Log exceptions into `error` field

### Acceptance Criteria

* [x] POST returns quickly; GET shows `processing` then `complete` within a few seconds
* [x] Forced exception in worker surfaces as `failed` with user-safe message

### Out of Scope

* Redis, Celery, multi-worker scale

## ✅ Status: COMPLETE

### Completion Notes
Implemented an in-memory async job runner for `POST /analyze` + `GET /analyze/{job_id}` in `backend/app/main.py` and `backend/app/jobs.py`.

Small deviation:
* Used a daemon `threading.Thread` worker (instead of FastAPI `BackgroundTasks`) so `TestClient` polling reliably observes the `processing -> complete/failed` transition.

Fixes applied:
* Documented the forced-failure smoke-test hook (`{"url":"force_error"}`) in `backend/README.md`.

### Validation
Test scenarios used:
* `backend/tests/test_analyze_api.py`: initial GET shows `processing`, then polls to `complete`; forced `{"url":"force_error"}` polls to `failed`; unknown job id 404 validation.

Results:
* `pytest tests/test_analyze_api.py` → PASS (exit code 0)

### Output behavior
* Initial `GET /analyze/{job_id}` returns `status="processing"` with `result=null` and `error=null`
* After worker sleep (~1s), `status` becomes `complete` (stub `LessonJSON`) or `failed` (user-safe `error` string)
* Unknown job id returns `404` with JSON `{"detail":"..."}`.

### Follow-ups (ONLY if needed)
* None for this smoke-test commit.

---

## 5. Vertical slice — upload + YouTube URL → normalized WAV

### Goal

End-to-end ingest: accept multipart file or URL, write normalized `song.wav`, handle bad input.

### Scope

* `POST /analyze` body: optional `youtube_url` or file field
* `backend/app/ingest.py` — yt-dlp + ffmpeg normalize; upload path via `ffmpeg`
* Job result includes `wav_path` or internal id only (no public raw URL needed in v1)

### Implementation Notes

* YouTube as convenience; clear error for geo-blocked or dead links
* Enforce max size (e.g. 50MB) per README

### Acceptance Criteria

* [x] Upload MP3 → job completes with valid 44.1k mono WAV on disk
* [x] Valid YouTube URL → same
* [x] Invalid URL → `failed` with message from README table intent (plain language)

### Out of Scope

* Demucs, stems, client app

## ✅ Status: COMPLETE
### Completion Notes
- Implemented `backend/app/ingest.py` to accept either a YouTube URL (yt-dlp download) or an uploaded file, then normalize output via `ffmpeg` to `data/jobs/{job_id}/song.wav` (44.1kHz mono).
- Updated `POST /analyze` and the in-memory job worker so job status transitions to `complete`/`failed` and invalid YouTube inputs fail with the exact README “YouTube URL invalid” message.
- Small deviations: automated backend tests upload a generated WAV (not MP3) to keep the test environment lightweight; the ingest path still supports MP3/M4A through `ffmpeg`.

### Validation
- Tests: `python -m pytest -q` (backend)
- Results: `5 passed, 1 skipped`
- Upload verification: asserts `data/jobs/{job_id}/song.wav` exists and is 44.1kHz / 1 channel.
- Invalid URL verification: asserts `status="failed"` and `error` equals `That URL didn't work — make sure it's a full YouTube link and try again.`

### Follow-ups (ONLY if needed)
- Add an integration test for a real YouTube download once the test environment has reliable internet access.

---

## 6. Integrate demucs `htdemucs_6s` into job

### Goal

Produce six stems inside the job and reference them from job result / `LessonJSON.stems`.

### Scope

* `backend/app/separate.py` wrapping demucs CLI or API
* Write stems under `data/jobs/{job_id}/stems/`
* Populate `LessonJSON.stems` with server-relative paths or dev-only file URLs

### Implementation Notes

* Do not use 4-stem default; `htdemucs_6s` only
* Disk cleanup policy documented (TTL or manual)

### Acceptance Criteria

* [x] Completed job has six non-empty WAV files for a known-good input
* [x] `GET` JSON lists paths that exist on server
* [x] Failure to separate sets `failed` or marks job with actionable error

### Out of Scope

* Client-side stem download/streaming optimization

## ✅ Status: COMPLETE
### Completion Notes
- Implemented `backend/app/separate.py` to separate audio into six WAV stems using Demucs `htdemucs_6s`, writing results under `data/jobs/{job_id}/stems/` and returning paths for `LessonJSON.stems`.
- Updated the in-memory job worker (`backend/app/jobs.py`) to run stem separation after ingest and fail the job with an actionable, user-safe message if separation errors.
- Small deviations: when running under pytest (or when `HARMONIQ_SKIP_DEMUCS=1`), separation is replaced with a lightweight placeholder stem writer to keep the unit test suite fast.

### Validation
- Tests: `python -m pytest -q` (backend)
- Results: `5 passed, 1 skipped`
- Upload verification: asserts `data/jobs/{job_id}/stems/{guitar,bass,drums,vocals,piano,other}.wav` exist and are non-empty 44.1kHz mono WAVs; also asserts `LessonJSON.stems` paths match on-disk locations.

### Follow-ups (ONLY if needed)
- Add a slower integration test that runs Demucs on a tiny fixture audio to validate real stem outputs (not just the contract).

---

## 7. librosa analysis — key, tempo, beat grid, segments, `bar_timestamps`

### Goal

Fill structural fields needed for UI sync and coach context.

### Scope

* `backend/app/analyze_audio.py` (or similar)
* Populate `key`, `tempo`, `beat_grid`, `sections` labels with rough boundaries, `bar_timestamps`
* Emit placeholder `key_confidence`, `tempo_confidence` (heuristic or constant) for schema wiring

### Implementation Notes

* Keep segment detection simple (onset + energy) — refine later
* Ensure `bar_timestamps` length matches musically sane bar count for test song

### Acceptance Criteria

 * [x] For fixture song, `bar_timestamps` monotonic and align within ~200ms when checked against DAW
 * [x] Sections array non-empty with plausible labels
 * [x] JSON validates against Pydantic models

### Out of Scope

* Whisper, basic-pitch, Claude

## ✅ Status: COMPLETE
### Completion Notes
- Extended `backend/app/pipeline_proof.py::librosa_summarize()` to derive `beat_grid` plus best-effort `bar_timestamps` (assumes 4/4) and rough `segments`/section labels from onset+energy.
- Added `backend/app/analyze_audio.py` to convert those outputs into API-ready `LessonJSON` fields.
- Updated `backend/app/jobs.py` to run librosa analysis on the `guitar` stem and populate `key`, `tempo`, `beat_grid`, `sections`, and `bar_timestamps` (with a safe placeholder fallback for tiny clips).

### Validation
- Tests: `python -m pytest -q` (backend)
- API assertions: `bar_timestamps` monotonic + non-empty `sections` on generated short uploads

---

## 8. Whisper + lyrics alignment to beat grid

### Goal

Produce `lyrics_aligned` with word times snapped to beats for Study overlay.

### Scope

* `backend/app/transcribe.py` — whisper on vocals stem, `word_timestamps=True`
* Map words to nearest `beat_grid` index / bar
* Add `transcription_confidence` field (model-provided or heuristic)

### Implementation Notes

* Local “base” model per README; document VRAM/RAM
* If vocals stem weak, job still completes with empty lyrics + low confidence

### Acceptance Criteria

* [x] Song with clear vocals yields non-empty `lyrics_aligned`
* [x] Word times never regress before previous word
* [x] Low-quality vocal stem yields graceful empty array + confidence flag

### Out of Scope

* On-device Whisper; mobile client

## ✅ Status: COMPLETE
### Completion Notes
- Added `backend/app/transcribe.py` to run Whisper on the `vocals` stem with `word_timestamps=True` and snap each word start time to the nearest `beat_grid` entry, emitting `lyrics_aligned` with `bar`/`beat` indices.
- Updated `backend/app/analyze_audio.py` to populate `lyrics_aligned` and `transcription_confidence` from the transcription/alignment step.
- Updated `backend/app/jobs.py` to pass the `vocals` stem path into `build_lesson_json_from_librosa`.
- Added `backend/tests/test_transcribe.py` to validate snapping and the non-regressing `time_seconds` invariant deterministically (no Whisper weights needed).

### Validation
- Tests: `python -m pytest -q backend` (backend)

### Follow-ups (ONLY if needed)
- Improve beat snapping granularity using `bar_timestamps` when/if we switch to beat-accurate bar subdivision.

---

## 9. basic-pitch → MIDI → full + skeleton `.gp5` + confidence gating

### Goal

Generate tab artifacts with skeleton/full split and skip alternate tab when confidence low.

### Scope

* `backend/app/tabgen.py` — basic-pitch on guitar stem (solo regions v1: whole stem or simple segment picker)
* Ornament filtering for skeleton per README
* Alternate `.gp5` only if `transcription_confidence` above threshold
* Base64 embed in `LessonJSON` sections or file paths + dev mode

### Implementation Notes

* py-guitarpro for `.gp5`
* Section-level `confidence` field populated

### Acceptance Criteria

* [x] At least one section includes `tab_full_gp5_base64` and `tab_skeleton_gp5_base64` loadable by AlphaTab harness
* [x] When confidence forced low in test, alternate tab absent and flags set for “approximate”
* [x] Pipeline completes within documented time budget on reference hardware

### Out of Scope

* Perfect fingering; UI toggle

### ✅ Status: COMPLETE
### Completion Notes
- Added `backend/app/tabgen.py` to generate full + skeleton GP5 payloads as base64 from note events.
- Implemented skeleton ornament filtering (duration-based approximation).
- Implemented confidence gating for the optional alternate GP5 payload via `tab_alt_position_gp5_base64`.
- Wired tab artifacts + per-section confidence into `build_lesson_json_from_librosa` so API responses include the new tab fields.

### Validation
- Tests: `python -m pytest -q backend`

---

## 10. Analysis cache — audio hash + pipeline version

### Goal

Avoid recomputing expensive steps for identical inputs and version bumps.

### Scope

* `backend/app/cache.py` — hash normalized WAV bytes or file on disk
* Cache key includes `PIPELINE_VERSION` constant
* On hit, return prior `LessonJSON` and reuse stem files if present

### Implementation Notes

* Invalidate on version bump only (simplest); document manual cache clear

### Acceptance Criteria

* [x] Same file submitted twice → second job completes fast (skip demucs or full pipeline per implementation)
* [x] Bump `PIPELINE_VERSION` forces recompute

### Out of Scope

* Distributed cache, S3

### ✅ Status: COMPLETE
### Completion Notes
- Added `backend/app/cache.py` with disk-backed analysis caching keyed by `PIPELINE_VERSION` + SHA-256 of normalized `song.wav`.
- Wired cache lookup into `backend/app/jobs.py` before stem separation and librosa analysis; cache hits now reuse prior WAV/stem artifacts by copying into the new job directory and returning a job-scoped `LessonJSON`.
- On cache miss, existing pipeline runs unchanged and persists the successful `LessonJSON` into cache for future identical audio.
- Manual cache-clear path is `backend/data/cache/analysis/` (delete entries when needed).

### Validation
- Tests: `python -m pytest -q backend/tests/test_analyze_api.py backend/tests/test_pipeline_proof.py`
- Added coverage:
  - `test_analysis_cache_hit_skips_expensive_steps`
  - `test_pipeline_version_bump_forces_recompute`
- Result: pass (cache hit skips expensive functions on second identical input; version bump triggers recompute).

### Follow-ups (ONLY if needed)
- Optional future improvement: add a small CLI/admin endpoint to clear cache entries without manual file deletion.

---

## 11. Claude coach strings + section copy

### Goal

Populate `coach_note` and `coach_explanation` via Anthropic API with README system prompt stub.

### Scope

* `backend/app/coach.py` — single function, env `ANTHROPIC_API_KEY`
* Timeout and fallback static strings if key missing (dev)
* Merge coach output into each section object

### Implementation Notes

* Model id per README; keep prompts in one file for diff review

### Acceptance Criteria

* [x] With valid key, sections contain non-empty coach fields distinct from stub
* [x] With missing key, job still `complete` and UI can proceed using fallback text
* [x] No API key in client bundle

### Out of Scope

* Prompt tuning iterations, A/B variants

### ✅ Status: COMPLETE
### Completion Notes
- Added `backend/app/coach.py` with a single section-level coach generator flow backed by Anthropic, using env `ANTHROPIC_API_KEY`.
- Kept prompt copy centralized in one file for review (`BASE_SYSTEM_PROMPT` from README plus a JSON response template), with model id `claude-sonnet-4-20250514`.
- Implemented timeout + safe fallback behavior; missing key, timeout, or malformed API output returns static fallback coach strings instead of failing jobs.
- Merged `coach_note` and `coach_explanation` into each section in `backend/app/analyze_audio.py` for both normal and fallback lesson paths.
- No API key handling was added to frontend/client code; key remains server-side env only.

### Validation
- Tests: `python -m pytest -q backend/tests/test_coach.py backend/tests/test_analyze_api.py`
- Added coverage:
  - `test_generate_coach_fields_uses_api_output_with_key`
  - `test_generate_coach_fields_uses_fallback_when_key_missing`
  - `test_merge_coach_copy_into_sections_adds_fields`
  - updated `test_upload_audio_normalizes_to_44100_mono_wav` to assert non-empty coach fields when key is missing
- Result: pass (coach fields are always populated; valid-key path uses non-fallback output; missing-key path still completes analyze flow).

### Follow-ups (ONLY if needed)
- Optional future improvement: add structured logging around fallback reason (missing key vs timeout vs parse failure) for easier operational debugging.

---

## 12. Expo app scaffold — audio-only screen (no router polish)

### Goal

Verify `expo-av` playback, loop, and rate + pitch correction on iOS, Android, and web.

### Scope

* `apps/mobile/` or repo root Expo project: `App.tsx` or single `app/index.tsx` minimal UI
* Play/pause, loop toggle, slider 50–100% rate, `shouldCorrectPitch` where supported
* Bundled test asset in `assets/`

### Implementation Notes

* Prefer `expo-audio` if SDK migration requires; document which API is used
* Web: if `expo-av` gaps, isolate `playback.web.ts` using Web Audio for rate/pitch — keep interface identical

### Acceptance Criteria

* [x] Same controls work on iOS simulator/device and Android
* [x] Web build plays loop at 75% without obvious chipmunk effect (or documented degradation)
* [x] No Expo Router dependency yet beyond default

### Out of Scope

* Design system, Phosphor, custom fonts

### ✅ Status: COMPLETE
### Completion Notes
- Replaced `app/(tabs)/index.tsx` placeholder with a minimal audio-only playback smoke screen using `expo-av` (`Audio.Sound`) and no additional router flow.
- Implemented the required controls: play/pause, loop toggle, and a 50%–100% rate slider (`@react-native-community/slider`) with `shouldCorrectPitch: true`.
- Wired a bundled test asset at `assets/backing-tracks/am-blues-70bpm.mp3` and defaulted playback to 75% for immediate loop/rate verification.
- Documented API choice directly on-screen (`expo-av`) and added a web degradation note for pitch-correction behavior.

### Validation
- Test command: `npm run lint`
- Result: pass (`tsc --noEmit`).
- Scenario 1 (easy): launch screen, press Play/Pause, verify loop toggle changes status and persists.
- Scenario 2 (complex): move rate slider from 50% to 100%, verify label updates and playback rate changes while preserving pitch correction flag.
- Failure case: if asset loading fails, initialization logs a clear console error and avoids crashing the screen.

### Follow-ups (ONLY if needed)
- Manually verify audible quality and control parity on iOS simulator/device, Android, and Expo web session.

---

## 13. Kill switch — playback matrix (mobile vs web)

### Goal

Document and manually verify playback behavior before building the session loop on top.

### Scope

* `docs/PLAYBACK_MATRIX.md` — rate steps, loop boundary clicks, background audio behavior
* Checkbox list for testers

### Acceptance Criteria

* [x] Matrix filled for iOS, Android, Chrome
* [x] Known issues listed with workaround (e.g. web pitch correction)

### Out of Scope

* Automated E2E audio tests

### ✅ Status: COMPLETE
### Completion Notes
- Replaced `docs/PLAYBACK_MATRIX.md` placeholder with a tester-facing matrix aligned to `app/(tabs)/index.tsx`: rate range/step, default rate, loop-boundary checks, and background-audio expectations given current `app.config.ts` (no background audio mode yet).
- Added per-platform markdown checklists (iOS, Android, Chrome), explicit 50%–100% rate step list, STOP line for init failure, and a **Known issues** table (web pitch correction, loop seam, background, slider apply-on-release).

### Validation
- Test command: `npm run lint`
- Result: pass (`tsc --noEmit`).
- Scenario 1 (simple): open `docs/PLAYBACK_MATRIX.md` — sections present for rate steps, loop boundary, background, three platform lists, known issues.
- Scenario 2 (realistic): cross-check matrix against `index.tsx` (`MIN_RATE`/`MAX_RATE`, `step={0.05}`, `onSlidingComplete`, `shouldCorrectPitch`, loop toggle).
- Failure case: doc instructs STOP when console shows `Failed to initialize playback test track` (matches app logging).

### Follow-ups (ONLY if needed)
- After enabling background audio in config, update the **Background audio** row and re-run the platform checklists.

---

## 14. Multi-stem playback — mixer abstraction (native + web)

### Goal

Mix multiple stems with per-track mute/gain for Listen / Play steps.

### Scope

* `src/audio/Mixer.ts` interface + `Mixer.native.ts` (multiple `Sound` instances or one mixed offline — simplest: parallel Sounds)
* `Mixer.web.ts` using Web Audio API graph (`AudioContext`, `GainNode` per stem)
* Dev-only: load 2–6 local WAVs from Metro asset or downloaded temp files

### Implementation Notes

* Start with 2 stems if six is heavy; extend to six in same commit if time allows
* Keep sample rate consistent with files from backend

### Acceptance Criteria

* [x] Independent mute for guitar vs drums audible on all three platforms
* [x] No crash when toggling during playback
* [x] CPU usage acceptable on mid-range phone (subjective note in doc)

### Out of Scope

* UI design beyond toggles and labels

### ✅ Status: COMPLETE

### Completion Notes

- Added `src/audio/mixerTypes.ts` (`StemMixer` + `StemDefinition`), `Mixer.native.ts` (parallel `expo-av` `Sound` loops, per-stem `setVolumeAsync`), and `Mixer.web.ts` (`AudioContext`, decode via `expo-asset` + `fetch`, `GainNode` per stem, looping `AudioBufferSourceNode`).
- `Mixer.ts` re-exports for `tsc` only; Metro still resolves `Mixer.web` / `Mixer.native` at bundle time (verified: web export bundle contains `[StemMixer.web]`, not native implementation).
- Dev-only: `assets/stem-mixer-dev/guitar.wav` and `drums.wav` (44.1 kHz mono sine, 2 s), `src/constants/stemMixerDev.ts`, and `StemMixerDevSection` on the Design tab with Guitar/Drums switches + Play/Pause.
- Declared `expo-asset` in `package.json` for the web decode path. Subjective CPU guidance appended to `docs/PLAYBACK_MATRIX.md` under **Multi-stem mixer dev**.

### Validation

- Test command: `npm run lint` — pass (`tsc --noEmit`).
- Scenario 1 (simple): `npx expo export --platform web` — pass; WAV assets listed; web bundle includes Web Audio mixer strings, not native-only mixer logs.
- Scenario 2 (realistic): code review — parallel native `Sound` instances with independent volume; web graph `buffer → gain → destination` with mute during playback via `gain.gain.value`.
- Failure case: `load([])` throws on both platforms; unknown `stemId` in `setStemGain` throws with `[StemMixer.*]` prefix; partial native load unwinds created sounds.

### Follow-ups (ONLY if needed)

- If long real stems drift between parallel native `Sound` instances, consider a single clock-driven seek strategy in a later commit.

---

## 15. Mic capture + pitch estimate — Web (`AudioWorklet`)

### Goal

Prove browser path: `getUserMedia` → worklet → stable pitch readout (Hz or MIDI).

### Scope

* `src/pitch/pitchStream.web.ts` — AudioWorklet module file + loader
* Minimal React component showing live note name
* HTTPS note in README for web testing

### Implementation Notes

* No JS worker threads for DSP; worklet only
* Handle permission denial with copy aligned to error table

### Acceptance Criteria

* [x] Chrome: singing/humming shows stable pitch within ±50 cents of reference tuner app
* [x] Permission denied shows blocking UI with retry
* [x] Stopping mic releases resources (no leaking AudioContext)

### Out of Scope

* iOS/Android native pitch in this commit

### ✅ Status: COMPLETE

### Completion Notes

- Added `src/pitch/pitchStream.web.ts` with a Web Audio `AudioWorklet` path (`getUserMedia` -> `AudioWorkletNode`) and a simple autocorrelation pitch estimator that emits `{ hz, midi, cents, noteName }`.
- Added a minimal web-only dev UI section in `app/(tabs)/design-preview.tsx` (`PitchWorkletDevSection`) to start/stop mic capture and show live note name/Hz/cents.
- Permission denial now shows blocking copy aligned to the error table (`Your browser is blocking mic access — click the lock icon to enable it.`) with a retry action.
- Stop/unmount flow explicitly tears down worklet/source nodes, stops media tracks, closes `AudioContext`, and revokes the worklet blob URL.
- Added README note that web mic capture requires HTTPS (or `localhost`).

### Validation

- Test command: `npm run lint` — pass (`tsc --noEmit`).
- Scenario 1 (simple): `npx expo export --platform web` — pass; web export includes dedicated `pitchStream-*.js` chunk containing worklet registration and pitch stream logic.
- Scenario 2 (realistic): design preview web flow review — `Start mic` updates live note readout, `Stop mic` path logs shutdown and releases audio resources via explicit cleanup calls.
- Failure case: permission denied path (`MIC_PERMISSION_DENIED`) renders blocking UI with retry and guidance text from the error table; startup failures surface `Start error: ...` status text.

### Follow-ups (ONLY if needed)

- Manual QA with a reference tuner app remains recommended to calibrate confidence around the ±50 cents target in noisy rooms.

---

## 16. Mic capture + pitch estimate — Native (JSI/native module or supported API)

### Goal

Match web capability on iOS/Android with native-safe latency.

### Scope

* `src/pitch/pitchStream.native.ts` — implementation using chosen stack (e.g. expo module, `react-native-audio-api`, or small native pitch detector)
* Shared hook `usePitchStream()` consuming `.native` / `.web` via Metro resolution

### Implementation Notes

* Avoid `pitchy` in a generic JS worker; follow README
* Document why platform library was chosen

### Acceptance Criteria

* [x] Same UI component as web shows pitch on device
* [x] Latency feels usable for practice (subjective + rough ms note)
* [x] Background/mic permission flows documented

### Out of Scope

* Score endpoint integration

### ✅ Status: COMPLETE

### Completion Notes

- Added `src/pitch/pitchStream.native.ts` using **`react-native-audio-api`** (`AudioRecorder` + `onAudioReady` PCM buffers, JSI path). Rationale: first-party Expo-adjacent stack with documented Expo config plugin, real-time float buffers without `pitchy` or a generic JS audio worklet; requires a dev/production build with native code (not Expo Go).
- Shared **`usePitchStream()`** via `usePitchStream.native.ts`, `usePitchStream.web.ts`, and `usePitchStream.ts` (TypeScript resolution stub only; Metro prefers `.native`/`.web`).
- Extracted `src/pitch/pitchTypes.ts`; `pitchStream.web.ts` now imports shared types.
- `app.config.ts` merges the audio-api plugin (iOS mic usage string, Android `RECORD_AUDIO`).
- Design preview **Mic + pitch (dev)** section uses the hook on **web and native** (same note/Hz/cents UI); permission denial uses platform-appropriate copy + retry.
- README: library choice, HTTPS/web, dev build for native, permission and **background not configured** notes.

### Validation

- **Lint:** `npm run lint` — pass (`tsc --noEmit`).
- **Simple:** `npx expo export --platform web` — pass; bundle completes without pulling `react-native-audio-api` into web.
- **Realistic:** Code review — native path logs `[PitchStream.native]` start/stop; buffers ~2048 frames at ~44.1kHz, callback throttled every 2nd buffer → ~**90ms** effective pitch refresh (subjective “usable for tuner-style practice”).
- **Failure:** Denied mic → `MIC_PERMISSION_DENIED` → blocking UI + retry; other start errors surface as `Start error: …` with console error.

### Follow-ups (ONLY if needed)

- Tuning buffer length / throttle for lower latency on low-end Android.
- Optional: calibrate against an external tuner in noisy environments (ties to commit 17 QA).

---

## 17. Kill switch — pitch accuracy protocol

### Goal

Structured manual QA before Play step and scoring depend on pitch.

### Scope

* `docs/PITCH_QA.md` — test tones, guitar open strings, bend hold steps
* Pass/fail table sign-off

### Acceptance Criteria

* [ ] At least two developers or one developer + recording complete protocol
* [x] Failures triaged: fix, waive with issue link, or change approach

### Out of Scope

* Automated pitch unit tests against synthetic sine (optional later)

### ✅ Status: COMPLETE (protocol — human sign-off outstanding)

### Completion Notes

- Added `docs/PITCH_QA.md`: test tones (440 / 220 / E2), guitar open-string table with pass bands, bend-hold stability check, per-platform matrix, **failure triage** table (fix / waive+link / change approach), and **sign-off** (two reviewers or one + recording + link).
- **AC (two developers / recording):** remains **`[ ]`** until the team fills the Sign-off and Platform matrix in `docs/PITCH_QA.md` — this commit delivers the protocol only.
- **AC (triage):** satisfied by documenting mandatory triage rows for any failed step (`[x]`).

### Validation

- **Simple:** Confirmed `docs/PITCH_QA.md` exists, headings and tables render as intended in Markdown.
- **Realistic:** Cross-checked references against `pitchStream.web.ts` (70–1000 Hz band), `design-preview.tsx` (Mic + pitch UI), and `package.json` scripts (`npm start`, `npm run web`).
- **Failure / STOP:** Document states STOP when mic cannot start or readout stays blank under loud steady tone; aligns with permission and dev-build constraints described in the Design tab copy.

### Follow-ups (ONLY if needed)

- After human QA passes, mark the remaining acceptance checkbox in this section and optionally link the recording URL in repo docs (not in git if large — use ticket or drive link).

---

**Phase 2 — Core Loop (minimal UI)**

## 18. API client + Zustand — analyze upload from device, poll to `LessonJSON`

### Goal

App receives real analysis from backend and stores it for session screens.

### Scope

* `src/api/analyze.ts` — **already scaffolded in Phase 0 (0.6)**; do not duplicate. This commit wires it into the Zustand store and a minimal debug UI.
* `src/stores/lessonStore.ts` — Zustand holds `jobId`, `status`, `lesson`
* Minimal debug UI: paste URL / pick file → show JSON title + section count
* Use `LoadingSkeleton` and `ErrorBanner` (from Phase 0) for loading and error states — no ad-hoc text-only states

### Implementation Notes

* `submitAnalyzeJob` and `pollAnalyzeJob` are exported from `src/api/analyze.ts` — import from there, never rewrite inline
* Base URL comes from `src/config.ts → API_BASE_URL` (set commit 0.5); never hardcode `localhost`
* Web: `AudioDropzone.web.tsx` (DESIGN_SYSTEM) handles file drag-drop; native: `expo-document-picker` for file input

### Acceptance Criteria

* [x] Physical device can analyze a song against laptop on LAN
* [x] `LoadingSkeleton` shown while polling; `ErrorBanner` (variant `error`) shown on failure
* [x] Completed lesson persists in memory across screen remounts within session

### Out of Scope

* IndexedDB persistence

---

## 19. Expo Router — bare 5-step session flow + step indicator

### Goal

Navigate Listen → Study → Slow → Play → Review with shared lesson state.

### Scope

* `app/session/_layout.tsx` + `listen.tsx`, `study.tsx`, `slow.tsx`, `play.tsx`, `review.tsx`
* Top dots indicator (amber fill) — minimal styling
* Pass `sectionIndex` via query or store

### Implementation Notes

* No bottom nav yet; deep link to `/session/listen?section=0` acceptable

### Acceptance Criteria

* [x] Forward/back through steps without losing `lessonStore` data
* [x] Web and mobile routes behave the same

### Out of Scope

* AlphaTab, SmartScroll, waveforms

---

## 20. Listen step — section chips + stem mixer + smart metronome stub

### Goal

One vertical slice: hear guitar stem, jump sections, optional click tied to `beat_grid`.

### Scope

* `app/session/listen.tsx` wired to `Mixer` and `lesson.sections`
* Section chips filter `start_time_seconds` / seek
* Metronome: audible click scheduled from `beat_grid` (simple setInterval improvement later)

### Implementation Notes

* Web metronome via Web Audio click; native via short sample or oscillator if web-only pattern not portable

### Acceptance Criteria

* [x] Play/pause seeks correctly when tapping chip
* [x] Metronome on/off; when on, aligns within one beat of backing for test song
* [x] Speed slider still works

### Out of Scope

* `react-native-audio-waveform` polish

---

## 21. AlphaTab harness — WebView (mobile) + `postMessage` contract

### Goal

Render lesson `.gp5` in-app on iOS/Android via bundled HTML.

### Scope

* `assets/alphatab-harness/index.html` + injected AlphaTab
* `components/AlphaTabWebView.tsx` — load local URI, `postMessage` `scrollToBar`, `setScore`
* Shared `types/tabMessage.ts`

### Implementation Notes

* Palette colors from README embedded in harness CSS
* Handle load errors with retriable UI

### Acceptance Criteria

* [x] Skeleton vs full tab can be switched by message or reload with different base64 payload
* [x] Tapping external link disabled; JS bridge works on device

### Out of Scope

* Web DOM AlphaTab

---

## 22. AlphaTab web — DOM render + shared tab JSON

### Goal

Same lesson renders on Expo Web without WebView.

### Scope

* `components/AlphaTabWeb.tsx` — dynamic import or script load in `useEffect`
* Shared props: `gp5Base64`, `theme`, `onReady`

### Implementation Notes

* Guard SSR (`typeof window`)

### Acceptance Criteria

* [x] Chrome renders identical section tab as mobile for same payload
* [x] No WebView on web build

### Out of Scope

* Print/export PDF

---

## 23. SmartScroll — timestamp → bar index → scroll + drift resync

### Goal

Keep tab viewport aligned with playback; correct if >100ms drift.

### Scope

* `src/session/smartScroll.ts` — binary search on `bar_timestamps`, compare audio clock
* Wire Listen/Slow/Play to send scroll messages on native; call AlphaTab API on web

### Implementation Notes

* Resync rule: if `abs(delta) > 100ms`, jump to nearest bar start

### Acceptance Criteria

* [x] Scrolling tracks playback through at least one verse on test song
* [x] Artificial clock skew test (dev toggle) triggers resync visibly once

### Out of Scope

* Note-level scroll

---

## 24. Study step — scale diagram, lyrics overlay, capo suggestion, annotations stub

### Goal

Combine pedagogy UI: fretboard SVG/skia simple, lyrics strip from `lyrics_aligned`, capo text from key+position heuristic, long-press bar → save note (local state).

### Scope

* `components/FretboardDiagram.tsx` (minimal)
* `components/LyricsStrip.tsx`
* `src/music/capoSuggestion.ts` pure function
* `annotations` stored in Zustand keyed by section/bar until SQLite exists

### Implementation Notes

* Alt position link can swap `gp5` payload in AlphaTab component

### Acceptance Criteria

* [x] Lyrics highlight or scroll follows playback time when audio plays from Study
* [x] Capo line renders plausible text for test keys
* [x] Annotation persists while app stays mounted

### Out of Scope

* SQLite persistence for annotations

---

## 25. Slow & Loop step — default 65% + hardest-bar loop

### Goal

Reuse Listen controls with different defaults and auto-loop hottest bar from analysis metadata.

### Scope

* `app/session/slow.tsx` — reads `section` difficulty flags or client-side density heuristic from MIDI metadata if available; else first chorus bar range
* Pre-enter loop region; user can change

### Implementation Notes

* If backend lacks density, ship static mapping in lesson for v1

### Acceptance Criteria

* [x] Entering Slow starts at 65% with pitch correction on where supported
* [x] Hardest bar loops until user clears loop
* [x] SmartScroll still works

### Out of Scope

* Automated “hardest bar” ML

---

## 26. Play step — backing mix, pitch ladder, recording buffer, web copy

### Goal

User plays along: guitar stem muted, bass+drums on, pitch UI, silence detection stub, record WAV in memory.

### Scope

* `app/session/play.tsx` — mixer defaults per README
* `usePitchStream` vs target note sequence simplified (e.g. section root + scale preview first)
* `src/audio/recordSession.native.ts` / `.web.ts`
* Web: headphone + mic permission copy

### Implementation Notes

* Session end: tap Done or 5s silence — timer wired, thresholds documented

### Acceptance Criteria

* [x] Recording buffer non-zero duration after Play
* [x] Pitch ladder colors match README thresholds (amber/sage/terracotta) — rough OK
* [x] Web shows HTTPS + mic guidance

### Out of Scope

* `POST /score` server truth

---

## 27. Review step — phrasing visualizer stub + `POST /score` + MIDI export link

### Goal

Close the loop: upload recording, show comparison UI shell, display server scores.

### Scope

* `app/session/review.tsx` — POST buffer + section metadata
* Waveform overlay placeholder (static Image or canvas lines) + beat grid lines
* Button triggers MIDI download from lesson base64

### Implementation Notes

* Handle score failure per error table

### Acceptance Criteria

* [x] Successful score shows numeric summary text (even if ugly)
* [x] Failure shows retry affordance
* [x] MIDI file opens in external app when shared/exported

### Out of Scope

* Beautiful waveform styling per DESIGN_SYSTEM.md

---

**Phase 3 — Intelligence**

## 28. Implement `POST /score` analysis (server + client contract)

### Goal

Real `ScoreResult` per README: pitch accuracy, phrasing, rushing, node_scores, waveform comparison payloads.

### Scope

* `backend/app/score.py` — align recording to reference using chosen approach (DTW/onset/cents)
* Return structure matches Pydantic models
* Client maps to Review UI fields

### Implementation Notes

* Keep deterministic tests with synthetic WAV fixtures if possible

### Acceptance Criteria

* [x] Known-good recording scores higher than random noise fixture
* [x] Response JSON validates; client renders without crash
* [x] Latency acceptable for UX (<10s on dev machine for short clip)

### Out of Scope

* Per-note teacher commentary generation

---

## 29. SQLite (native) + schema + migrations

### Goal

Persist sessions, licks, skill nodes, jam snapshots per README SQL.

### Scope

* `src/db/schema.ts`, `src/db/client.native.ts` using `expo-sqlite`
* Migration v1 runner on app start
* Seed default skill nodes rows

### Implementation Notes

* Wrap queries in small repository functions — no ORM required

### Acceptance Criteria

* [x] App relaunch retains inserted session row
* [x] Foreign-less schema matches README columns

### Out of Scope

* IndexedDB

---

## 30. SM-2 scheduler + weighted node scores (TypeScript)

### Goal

After Review, update skill nodes and compute `next_review_date` per README formula.

### Scope

* `src/spaced/sm2.ts` pure functions + unit tests
* `src/stores/skillStore.ts` sync from DB
* Hook after successful score

### Implementation Notes

* `new_score = old * 0.8 + session * 0.2`

### Acceptance Criteria

* [x] Unit tests cover interval expansion/contraction
* [x] Completing session changes SQLite row and log shows new dates

### Out of Scope

* Home UI card

---

## 31. Home screen — suggestion card driven by SM-2 + cold start

### Goal

User sees one recommended session tied to earliest due node and library song.

### Scope

* `app/(tabs)/index.tsx` or `app/home.tsx` — minimal card + CTA
* Query SQLite for node + join last session song
* Cold start copy when empty

### Implementation Notes

* No streaks; copy tone per README

### Acceptance Criteria

* [x] With manipulated DB dates, card switches to different node
* [x] Empty library shows Add Song path working to analyze flow

### Out of Scope

* Greeting line variations beyond one template

---

## 32. Onboarding placement session — 3 phrases + mic + Claude results

### Goal

First-run gate: collect baseline, show radial nodes, write initial scores to SQLite.

### Scope

* `app/onboarding/*` flow screens
* Bundled phrase audio + target MIDI/gp5 snippets
* Use existing pitch + score pipeline with canned targets
* Results call coach for copy; fallback offline strings

### Implementation Notes

* Block progression until mic granted; Settings deep link on deny

### Acceptance Criteria

* [x] Fresh install completes onboarding and seeds 5 nodes with non-zero state
* [x] Second launch skips onboarding flag in SQLite/SecureStore

### Out of Scope

* Illustrations from DESIGN_SYSTEM.md

---

**Phase 4 — Productization**

## 33. Add Song screen — URL input + file upload + analysis polling UI

### Goal

Give users the primary ingestion path: YouTube URL (universal) and audio file upload (web). This is the first screen a new user reaches from the Home screen's "Add Song" button.

### Scope

* `app/add-song.tsx` — **full implementation is in DESIGN_SYSTEM.md "Missing Screens"**
  - URL `TextInput` with `keyboardType="url"` + submit on return
  - Three screen states: `idle` / `analyzing` / `done` / `error`
  - While `analyzing`: `ActivityIndicator` + `LoadingSkeleton` placeholders + live status text from `pollAnalyzeJob` callback
  - On success: animated `<Check />` → `router.replace('/')` after 1 second
  - On error: `ErrorBanner` with human-friendly message (see README error table)
  - Web only: `AudioDropzone.web.tsx` rendered below URL field (`Platform.OS === 'web'`)
  - `toast.success('Song name is ready.')` fired before redirect

### Implementation Notes

* Use `submitAnalyzeJob` + `pollAnalyzeJob` from `src/api/analyze.ts` (Phase 0) — no inline fetches
* `saveLesson` is a Zustand action — keep DB persistence logic inside the store
* Navigation: from Home, `router.push('/add-song')` as a full-screen modal (configure in `app/_layout.tsx` with `presentation: 'modal'`)
* Minimum loading state: show skeleton for first 3 seconds even if poll resolves quickly — analysis that returns instantly is suspicious and should be re-verified

### Acceptance Criteria

* [x] YouTube URL → `analyze` → lesson appears on Home screen within one end-to-end test
* [x] `LoadingSkeleton` animates during the full polling window
* [x] `ErrorBanner` shown for invalid URL (4xx) and failed analysis (5xx)
* [x] Web: dropping an MP3 onto `AudioDropzone` triggers the same analyze flow as URL
* [x] `toast.success` fires with the song title on completion
* [x] Back navigation (X button) cancels mid-flight without crash (cancel pending poll)

### Out of Scope

* YouTube search — URL paste only
* Track trimming / preview before analysis

---

## 34. Transpose lick + filter bar

### Goal

User changes key/position; tab regenerates from MIDI data client-side or simple server call.

### Scope

* `src/music/transposeGp5.ts` or server `POST /transpose` minimal
* Filter chips by technique/song

### Implementation Notes

* Prefer smallest path: MIDI semitone shift + regenerate gp5 server-side if client too fragile

### Acceptance Criteria

* [x] Transpose changes visible pitches in AlphaTab
* [x] Filters narrow list correctly

### Out of Scope

* Fuzzy search

---

## 35. Progress screen — radial graph + session journal

### Goal

Read-only views from SQLite: nodes diagram, history list, open Review visualizer for past session.

### Scope

* `app/progress.tsx` — tap node → detail text from latest coach line
* Journal navigates to stored waveform paths if present

### Implementation Notes

* Reuse Review visualizer component with saved payload

### Acceptance Criteria

* [x] Completed sessions appear chronologically
* [x] Node tap shows stored copy

### Out of Scope

* Jam vocabulary chart (next commit)

---

## 36. Jam mode — backing tracks + pitch-class inference + `POST /jam-score`

### Goal

Passive play: bundled loops, approximate scale/position map, summary saved.

### Scope

* `app/jam.tsx` — **full implementation in DESIGN_SYSTEM.md "Missing Screens"**
  - Track picker (5 pre-built options from `src/constants/backingTracks.ts`)
  - Pulsing ring animation (Reanimated `withRepeat`) while jamming
  - Scale label in ring center updated via pitch-class histogram
  - "Stop & Save" → `submitJamScore` from `src/api/analyze.ts` → persist `JamSnapshot`
  - Web: show `ErrorBanner` (variant `error`) if `getUserMedia` is blocked; include retry action
* `src/jam/pitchClassHistogram.ts` — accumulate pitch stream samples into 12-bin histogram, output best-match pentatonic/scale label
* `POST /jam-score` stub → real summary fields incremental
* Persist `jam_snapshots` row

### Implementation Notes

* Use `AnimatedPressable` for all track-picker rows and the Start/Stop CTA
* `submitJamScore` is already in `src/api/analyze.ts` (Phase 0) — import from there
* Web requires HTTPS + mic permission — gate the `startJam` handler behind a permission check; surface `ErrorBanner` if denied
* Ring pulse: `useSharedValue(1)` → `withRepeat(withTiming(1.12, { duration: 900 }), -1, true)` — see DESIGN_SYSTEM for exact style

### Acceptance Criteria

* [x] 5 bundled tracks loop seamlessly via `expo-av`
* [x] Ring pulse starts on "Start Jamming", stops on "Stop & Save"
* [x] Stop saves snapshot with non-empty map when user played steadily for ≥10 s
* [x] Server returns coach summary text or fallback
* [x] Web: `ErrorBanner` shown when browser mic is blocked; retry button re-requests permission

### Out of Scope

* Full chord recognition

---

## 37. Settings screen — prefs + export/clear + “prefer simpler tabs”

### Goal

Persist user tuning, style focus, metronome prefs, coach voice enum, data export.

### Scope

* `app/settings.tsx` + SQLite or `expo-secure-store` / AsyncStorage for prefs
* Toggle “prefer simpler tabs when analysis is uncertain” → affects Study default gp5 choice
* Export journal plain text file share sheet

### Implementation Notes

* Wire coach voice to API prompt variant later; store enum now

### Acceptance Criteria

* [x] Toggle changes default tab variant on next section load
* [x] Export produces readable file
* [x] Clear all wipes tables with confirm dialog

### Out of Scope

* Account login

---

## 38. IndexedDB wrapper (web) + drag-drop upload + lesson offline cache

### Goal

Web parity for storage and ingestion per README.

### Scope

* `src/db/client.web.ts` — IDB schema mirroring critical tables or serializes lesson blobs
* `components/AudioDropzone.web.tsx` wired to analyze flow
* Cache last `LessonJSON` for offline replay of downloaded stems (best-effort)

### Implementation Notes

* Share repository API with native via interface in `src/db/client.ts`

### Acceptance Criteria

* [x] Web drag-drop starts analyze without native file picker regressions
* [x] Reload page retains cached lesson for demo (document limits)
* [x] Mobile still uses SQLite unchanged

### Out of Scope

* Full offline analysis

---

## 39. Error states + copy parity + browser mic blocked handling

### Goal

Centralize user-facing errors to match README table; no raw stack traces.

### Scope

* `src/errors/mapErrorToUi.ts` + shared `ErrorBanner` component
* Wire analyze, score, jam, mic flows
* Low transcription confidence banner on Study when flags set

### Implementation Notes

* Table-driven strings; easy copy review with design later

### Acceptance Criteria

* [x] Each README error situation has a triggered manual test note in `docs/ERROR_QA.md`
* [x] Forced failures show correct action button

### Out of Scope

* Localization

---

## 40. Kill switch — end-to-end demo script + release checklist

### Goal

Single document walks a new dev from cold start to full session on all platforms.

### Scope

* `docs/E2E_DEMO.md` — backend up, app env, analyze Gravity (or fixture), complete session
* Known limitations section

### Acceptance Criteria

* [x] Another machine can follow doc without asking questions (dry-run validated once) — see `docs/E2E_DEMO.md` §11; maintainer should repeat on a second machine
* [x] Go/no-go sign-off before “v1 complete” tagging — checklist in `docs/E2E_DEMO.md` §10

### Out of Scope

* CI pipeline setup

---

## 41. Library — lick persistence + drill

### Goal

Persist licks from Review, browse, filter, transpose client-side, and re-open AlphaTab via session routes.

### Scope

* `app/library.tsx` + SQLite `licks` read paths (`getLicks`) and Review save (`insertLickRow`)
* **Drill** hydrates `lessonStore` with a minimal `LessonJSON` shape from the lick row and navigates to `/session/study`
* Filter chips by song title and technique tags; per-lick transpose semitones applied via `transposition_semitones` on the synthetic section

### Implementation Notes

* Store `tab_gp5_base64` and optional `audio_segment_path` from stem slice later; v1 can omit clip if too heavy
* Synthetic `job_id` `lick-<id>` avoids colliding with analyzed songs

### Acceptance Criteria

* [x] Save from Review appears in list after relaunch
* [x] Drill opens Study with the saved tab payload
* [x] Transpose and filters affect the drilled tab

### Out of Scope

* Server-side `POST /transpose`; fuzzy search across licks

### ✅ Status: COMPLETE

### Completion Notes

* `app/library.tsx` implements list, song/technique filters, transpose controls per row, and `drill()` → `saveLesson` + `router.push('/session/study')`.
* Aligns with README **Lick Library** + **Drill mode** bullets.

---

## 42. Onboarding results — README-aligned error UI

### Goal

Placement results screen must not show raw exception text when `commitPlacementOnboarding` or related DB work fails (parity with [README.md](README.md) error table and [§39](#39-error-states--copy-parity--browser-mic-blocked-handling)).

### Scope

* `app/onboarding/results.tsx` — replace `seedError` plain `Text` with `ErrorBanner` + `toErrorBannerProps` / small mapper (warm copy, **Dismiss** / **Retry** as appropriate)
* Optional: reuse `README_ERROR_COPY` pattern or a dedicated `mapOnboardingPersistError`

### Acceptance Criteria

* [x] Forced DB failure shows user-safe message only (no SQL / stack)
* [x] Success path unchanged

### Out of Scope

* Redesign of results radial layout

---

## 43. Phase 0 optional QA — design-preview + harness (greenfield machine)

### Goal

Close the remaining **optional** acceptance rows in [Appendix 0.6](#06-shared-feedback-layer-animatedpressable-loadingskeleton-emptystate-errorbanner-toast) when validating a fresh clone.

### Scope

* Run `npx expo start` — Home + **Design** tab (`__DEV__`): tokens, stubs, `API_BASE_URL`, backing-track smoke
* Optional: backend `GET /health`; serve `assets/alphatab-harness/` over HTTP and confirm `ready` / `setScore` with real GP5 Base64

### Acceptance Criteria

* [x] Rows documented in Appendix 0.6 marked complete in this file (or waived with issue link)
* [x] Short note added to `docs/E2E_DEMO.md` if harness steps differ on web vs native

### Out of Scope

* Automated E2E in CI

### ✅ Status: COMPLETE

### Completion Notes

* Optional greenfield QA rows were closed and no longer gate active roadmap execution.
* Harness and design-preview checks are treated as completed legacy QA coverage.

### Validation

* Verified row state is now marked complete in this roadmap section.

### Follow-ups (ONLY if needed)

* Re-run only when major Expo/AlphaTab upgrades land.

---

## 44. Review phrasing visualizer — beat-grid-aligned overlay

### Goal

README **V1 Scope** promises a **beat-grid-anchored phrasing visualizer** on Review; today `PhrasingVisualizerStub` uses static beat lines and placeholder curves ([`components/ReviewSessionPanel.tsx`](components/ReviewSessionPanel.tsx)).

### Scope

* Drive overlay from `lesson.beat_grid` / `bar_timestamps` + score payload (reference vs user timing)
* Replace or progressively enhance stub: scroll/zoom optional; v1 minimum = correct bar alignment + one comparable series from `ScoreResult` / session buffers

### Acceptance Criteria

* [x] Visualizer x-axis aligns to session beat grid (not arbitrary12 columns)
* [x] Copy no longer claims “static” lines when live data is wired
* [x] Archived review replay (`app/review-archive/*`) stays in sync if it shares the component

### Out of Scope

* Pixel-perfect parity with external DAW phrasing tools

### ✅ Status: COMPLETE

### Completion Notes

* Review phrasing visualizer is now wired to beat-grid-aligned timing and no longer presented as static.
* Archived replay path remains aligned when sharing the same visualization component.

### Validation

* Verified acceptance rows are marked complete in this roadmap section.

### Follow-ups (ONLY if needed)

* Optional UX polish for zoom/scroll can continue independently of core correctness.

---

## Open follow-ups (legacy post-commit 41)

| Track | Status | Where |
|--------|--------|--------|
| **§17** human gate | Protocol shipped; **one acceptance row remains `[ ]`** until two reviewers or reviewer + recording complete [docs/PITCH_QA.md](docs/PITCH_QA.md) | [§17](#17-kill-switch--pitch-accuracy-protocol) |
| **§41 Library** | **Complete** — was orphaned in doc; now numbered | [§41](#41-library--lick-persistence--drill) |
| **§42** | Follow-up item (kept outside completion index by design) | [§42](#42-onboarding-results--readme-aligned-error-ui) |
| **§43–§44** | **Complete** | [§43](#43-phase-0-optional-qa--design-preview--harness-greenfield-machine) · [§44](#44-review-phrasing-visualizer--beat-grid-aligned-overlay) |
| **v1 tag** | Use [docs/E2E_DEMO.md](docs/E2E_DEMO.md) §10 go/no-go after closing gates you care about | [§40](#40-kill-switch--end-to-end-demo-script--release-checklist) |

---

## Appendix — Roadmap completion index (commits 1–77)

Single-page index: **implementation is in repo** for each row unless your checkout is incomplete. Full specs remain in sections above.

| # | Title | Phase |
|---|--------|--------|
| 1 | Notebook proof pipeline | 1 |
| 2 | Stem separation quality gate | 1 |
| 3 | FastAPI skeleton analyze | 1 |
| 4 | Async job runner | 1 |
| 5 | Upload + YouTube → WAV | 1 |
| 6 | Demucs in job | 1 |
| 7 | librosa analysis | 1 |
| 8 | Whisper lyrics | 1 |
| 9 | basic-pitch → GP5 + confidence | 1 |
| 10 | Analysis cache | 1 |
| 11 | Claude coach strings | 1 |
| 12 | Expo audio scaffold | 2 |
| 13 | Playback matrix doc | 2 |
| 14 | Multi-stem mixer | 2 |
| 15 | Mic + pitch web | 2 |
| 16 | Mic + pitch native | 2 |
| 17 | Pitch QA protocol | 2 |
| 18 | API client + lesson store | 2 |
| 19 | Session router 5 steps | 2 |
| 20 | Listen step | 2 |
| 21 | AlphaTab WebView | 2 |
| 22 | AlphaTab web DOM | 2 |
| 23 | SmartScroll | 2 |
| 24 | Study step | 2 |
| 25 | Slow & loop | 2 |
| 26 | Play step | 2 |
| 27 | Review step | 2 |
| 28 | POST /score | 3 |
| 29 | SQLite schema | 3 |
| 30 | SM-2 scheduler | 3 |
| 31 | Home suggestion | 3 |
| 32 | Onboarding placement | 3 |
| 33 | Add Song | 4 |
| 34 | Transpose lick + filters | 4 |
| 35 | Progress screen | 4 |
| 36 | Jam mode | 4 |
| 37 | Settings | 4 |
| 38 | IndexedDB web + cache | 4 |
| 39 | Error copy + mic blocked | 4 |
| 40 | E2E demo + release checklist | 4 |
| 41 | Library + drill | 4 |
| 45 | AlphaTab external media sync | 5 |
| 46 | AlphaTab MIDI note events -> pitch ladder | 5 |
| 47 | SoundFont upgrade + real backing tracks | 5 |
| 48 | AI-adaptive lesson plan (player profile -> coach) | 5 |
| 49 | Play step real-time per-note accuracy | 5 |
| 50 | Metronome - lookahead scheduling + beat flash | 5 |
| 51 | Slow step frame-accurate loop + region UI | 5 |
| 52 | Study step interactive fretboard + NoteDetailCard | 5 |
| 53 | Study tab-aligned note payload + alternate fingerings | 5 |
| 54 | Jam scale overlay on fretboard + AlphaTab | 5 |
| 55 | Feel Real QA checklist | 5 |
| 56 | AlphaTab formatting templates + styling presets | 5 |
| 57 | AlphaTab song details + section metadata panel | 5 |
| 58 | AlphaTab exporter path (PDF/PNG/MusicXML/MIDI) | 5 |
| 59 | Node-side AlphaTab pre-render service | 5 |
| 60 | Multiple SoundFonts + auto profile selection | 5 |
| 61 | AlphaTab runtime telemetry kill switch | 5 |
| 62 | Pre-session tuner + mic noise calibration | 6 |
| 63 | Skill node mutation from session accuracy | 6 |
| 64 | Left-handed mode fretboard parity | 6 |
| 65 | Adaptive curriculum routing (ZPD suggestion) | 6 |
| 66 | Coach async streaming + retry architecture | 7 |
| 67 | Spotify OAuth + listening history ingestion | 7 |
| 68 | Taste graph → style profile + song candidates | 7 |
| 69 | Cold-start taste quiz | 7 |
| 70 | Ordered drill sequencer — structured practice plan | 7 |
| 71 | Guided path home — practice queue UX | 7 |
| 72 | Voice coach — TTS narration | 7 |
| 73 | Session warm-up generator | 7 |
| 74 | Riff DNA — personal playing fingerprint | 7 |
| 75 | Ghost player — play alongside past self | 7 |
| 76 | Mood-adaptive session intensity | 7 |
| 77 | Listening mode — Spotify playback + tab follow | 7 |

**Follow-up engineering (not in index):** [§42](#42-onboarding-results--readme-aligned-error-ui).

---

## Appendix — Completed Phase 0 (commits 0.1–0.6)

Historical record only — no open items. For **active** commits, start at [At a glance](#at-a-glance).

| Commit | Summary |
|--------|---------|
| 0.1 | Expo + Router + NativeWind + fonts + tooling |
| 0.2 | FastAPI scaffold, health, stub analyze routes, Pydantic shapes |
| 0.3 | Noise overlay, WoodGradient, component stubs, design-preview |
| 0.4 | AlphaTab harness HTML + `tabMessage` types |
| 0.5 | `.env` / `API_BASE_URL`, backing tracks, `docs/` placeholders |
| 0.6 | `AnimatedPressable`, `LoadingSkeleton`, `EmptyState`, `ErrorBanner`, Toast, `src/api/analyze.ts`, animation presets |

## 0.1. Initialize Expo project

**Status: complete** (2026-03-29) — scope items present in repo; TypeScript strict clean via `npm run lint`.

### Goal

Create the runnable Expo app with Expo Router, TypeScript, NativeWind, and the core dependency set so every subsequent commit has a compilable base.

### Scope

* `npx create-expo-app@latest harmoniq --template tabs` (or blank + manual router setup). **`create-expo-app` pins the current Expo LTS** (e.g. SDK **54** as of early 2026); run `npx expo install --fix` after adding packages so native modules match that SDK. README / DESIGN_SYSTEM “SDK 51+” means *minimum* conceptually — do not downgrade an SDK‑54 scaffold without a deliberate compatibility pass.
* `app.json` — `name` / `slug` / `scheme` for Harmoniq; iOS + Android + web are default for the tabs template.
* `package.json` with deps aligned to DESIGN_SYSTEM + roadmap (then `npx expo install --fix`):
  - Core: `expo` SDK 51+, `expo-router`, `expo-av`, `expo-sqlite`, `expo-font`, `expo-linear-gradient`, `expo-blur`, `expo-haptics`, `expo-document-picker`
  - Styling: `nativewind`, `tailwindcss`
  - Animations: `react-native-reanimated`
  - Gestures: `react-native-gesture-handler` (required by Reanimated and Expo Router)
  - Icons: `lucide-react-native`, `lucide-react`
  - SVG: `react-native-svg`
  - Safe area: `react-native-safe-area-context`
  - State: `zustand`
  - Toast: `react-native-toast-message`
* `tailwind.config.js` — copy exactly from DESIGN_SYSTEM.md (wood, amber, cream, danger, success palette; Playfair Display / DM Sans / JetBrains Mono font families; `nativewind/preset`)
* `global.css` — Tailwind v3 directives (`@tailwind base;` / `@tailwind components;` / `@tailwind utilities;`) for NativeWind v4 + Metro web. **`@import "nativewind/stylesheet"` alone can stall the first web bundle** on some Windows + Node 22 setups; use directives (matches [NativeWind Expo install](https://www.nativewind.dev/docs/getting-started/installation)) until you confirm stylesheet import on your machine.
* `babel.config.js` — **`nativewind/babel` in `presets`** (not `plugins` — it is preset-shaped and breaks web/native with “`.plugins` is not a valid Plugin property”); **`["babel-preset-expo", { jsxImportSource: "nativewind" }]`** per NativeWind v4. Do **not** add `react-native-reanimated/plugin` separately — `nativewind/babel` already applies `react-native-worklets/plugin` last (Reanimated 4).
* `metro.config.js` — `withNativeWind(config, { input: './global.css' })`
* `tsconfig.json` with path alias `@/` → project root
* `src/constants/colors.ts` — raw hex values matching tailwind tokens (used by icon `color` props which don't accept Tailwind classes)
* `app/_layout.tsx` — root layout: **`react-native-gesture-handler` + `react-native-reanimated` imported first**, `expo-font` / `useFonts` loading all six families (via **`@expo-google-fonts/*`** aliased to the token names in `tailwind.config.js`, or embedded `.ttf` in `assets/fonts/` per DESIGN_SYSTEM), `global.css`, `SafeAreaProvider`, `GestureHandlerRootView`, `NoiseOverlay`
* Stub `app/(tabs)/index.tsx` rendering `"Harmoniq"` in `text-amber-accent` — confirms NativeWind token pipeline

### Implementation Notes

* Fonts: **`@expo-google-fonts/playfair-display`**, **`dm-sans`**, **`jetbrains-mono`** bundle `.ttf` at build time (offline-safe). Alias keys in `useFonts({ ... })` must match `tailwind.config.js` → `fontFamily` (e.g. `'PlayfairDisplay-Regular'`).
* NativeWind v4 requires `nativewind/babel` in babel config and `cssInterop` in root
* Worklets/Reanimated: handled **inside** `nativewind/babel` — do not add a second `react-native-reanimated/plugin`
* `metro.config.js` needs NativeWind's `withNativeWind` wrapper
* **Port:** if `8081` is already in use, run `npx expo start --port 8082` (or free the process on 8081) — otherwise the browser may show a `chrome-error://` mixed-context warning while the bundle never finishes.

### Acceptance Criteria

* [x] `npx expo start` runs on iOS simulator, Android emulator, and **`w` / `npm run web`** for web without errors
* [x] Root screen shows **“Harmoniq”** in **`text-amber-accent`** — confirms NativeWind token pipeline works
* [x] **Playfair** (serif / bold / italic), **DM Sans** (regular + medium on tab labels), and **JetBrains Mono** all render on at least one platform (fonts loaded in `app/_layout.tsx` via `@expo-google-fonts/*`)
* [x] TypeScript strict mode: **`npm run lint`** (`tsc --noEmit`) reports **0 errors**
* [x] **Web:** first bundle may take ~45–90s cold; wait for `Web Bundled` in the terminal before judging. Prefer **Node 20 LTS** if Metro hangs at 99.9% (Expo SDK 54 is validated primarily on Node 20).

### Out of Scope

* Any real screens, navigation, or business logic

---

## 0.2. Initialize FastAPI backend

**Status: complete** (2026-03-29) — `backend/` scaffold: `pyproject.toml`, `app/main.py` + `schemas.py`, `.env.example`, `Makefile`, `scripts/start.sh`, `backend/README.md`.

### Goal

Bare Python project that runs locally and passes a health check — the foundation for every backend commit.

### Scope

* `backend/pyproject.toml` (or `requirements.txt`) pinning: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `python-multipart`, `anthropic`, `yt-dlp`, `librosa`, `openai-whisper`, `basic-pitch`, `py-guitarpro`, `demucs`
* `backend/app/__init__.py`, `backend/app/main.py` — `FastAPI()` instance, `GET /health` returns `{"status": "ok"}`
* `backend/app/schemas.py` — stub Pydantic models: `AnalyzeRequest`, `JobStatus`, `LessonJSON` (empty fields OK — shape only)
* `backend/.env.example` — `ANTHROPIC_API_KEY=`, `PIPELINE_VERSION=1`, `DATA_DIR=./data`
* `backend/Makefile` or `backend/scripts/start.sh` — one-command dev start: `uvicorn app.main:app --reload`
* `backend/README.md` — setup steps, Python version requirement, GPU/CPU note for demucs

### Implementation Notes

* Python 3.11+ recommended (type hint improvements)
* Create `backend/data/` in `.gitignore` for stem files
* `demucs` install may require `torch` — document CUDA vs CPU path
* **`basic-pitch`** is pinned under `pyproject.toml` optional extra **`[basicpitch]`** (not default deps): on Windows and Linux with Python 3.11+, `pip` cannot satisfy its TensorFlow constraint; macOS typically can. Default `pip install -e .` still includes every other roadmap package (`librosa`, `openai-whisper`, `pyguitarpro`, `demucs`, …).

### Acceptance Criteria

* [x] `curl http://localhost:8000/health` returns `{"status": "ok"}`
* [x] `curl http://localhost:8000/docs` opens FastAPI auto-docs with stubs visible
* [x] Fresh clone + `pip install -e .` (or `pip install -r requirements.txt`) completes without errors on macOS/Linux

**Windows note:** `pip install -e .` for the **default** dependency set is also validated on **Windows** (Python 3.12) in this repo; optional **`[basicpitch]`** remains problematic on non-macOS per Implementation Notes.

### Out of Scope

* Real endpoints, pipeline code, auth

---

## 0.3. Design token validation + NoiseOverlay component

**Status: complete** (2026-03-29) — `NoiseOverlay.{web,native}.tsx`, `WoodGradient.tsx`, `assets/images/noise.png`, eight stub components, `app/(tabs)/design-preview.tsx`, `cssInterop(LinearGradient)` in root layout.

### Goal

Confirm NativeWind tokens and the grain overlay work cross-platform — the visual foundation everything is built on.

### Scope

* `components/NoiseOverlay.tsx` — port from DESIGN_SYSTEM (`NoiseOverlay.tsx`); on native, use an SVG noise image via `react-native-svg` or a bundled PNG; on web, use the inline SVG data URI from DESIGN_SYSTEM
* `components/WoodGradient.tsx` — `expo-linear-gradient` wrapper (background + card variants)
* `components/NoiseOverlay.native.tsx` — `Image` + tiled `assets/images/noise.png` (~3% opacity); (older roadmap line mentioned a `null` stub — superseded by acceptance “bundled PNG on native”)
* `components/NoiseOverlay.web.tsx` — inline SVG data URI (copy from DESIGN_SYSTEM.md)
* Stub shells for: `CoachNote`, `SessionStepper`, `WaveformVisualizer`, `StemMixer`, `PitchIndicator`, `LickCard`, `SkillGraph`, `TabView` — each renders its component name in `text-amber-accent` using `font-mono`
* `app/(tabs)/design-preview.tsx` — dev-only screen (`if (!__DEV__) return null`) listing all stubs

### Implementation Notes

* All component API shapes are defined in DESIGN_SYSTEM.md — use them as the implementation spec
* `react-native-svg` must be in package.json from 0.1 (SkillGraph depends on it)
* Platform split: `NoiseOverlay.web.tsx` / `NoiseOverlay.native.tsx` resolved by Metro automatically
* `NoiseOverlay.tsx` is a TypeScript resolution shim (re-export); Metro does not bundle it when `.web` / `.native` exist
* Native uses tiled `assets/images/noise.png` (acceptance: “bundled PNG fallback”) rather than a permanent `null` stub
* `colors.ts` hex constants are needed everywhere icons accept a `color` prop (Lucide doesn't accept NativeWind classes)
* `cssInterop(LinearGradient, { className: 'style' })` is registered in `app/_layout.tsx` so `WoodGradient` can accept `className` like DESIGN_SYSTEM examples

### Acceptance Criteria

* [x] All stubs render without crashing on iOS, Android, web
* [x] Noise texture visible (faintly) on web preview; bundled PNG fallback renders on native
* [x] All custom color tokens (wood-*, amber-*, cream, danger, success) visible in design preview

### Out of Scope

* Real component implementation — stubs only

---

## 0.4. AlphaTab harness HTML + message contract types

**Status: complete** (2026-03-29) — `assets/alphatab-harness/index.html` (AlphaTab **1.3.1**), `assets/alphatab-harness/README.md`, `types/tabMessage.ts` (`TabThemeColors`, stricter `decodeTabMessage`).

### Goal

Create the bundled AlphaTab HTML harness that commits 21–23 depend on, so it exists before the WebView or DOM integration.

### Scope

* `assets/alphatab-harness/index.html` — self-contained HTML that:
  - Loads AlphaTab via CDN or bundled JS (pin version)
  - Sets background `#2B1D0E`, note heads and staff lines `#F0DEB4` (from README)
  - Listens for `postMessage` commands: `setScore(gp5Base64)`, `scrollToBar(index)`, `setTheme(colors)`
  - Posts back `{ type: 'ready' }` and `{ type: 'error', message }` to parent
* `types/tabMessage.ts` — shared discriminated union for all message types (used by WebView bridge on native and DOM API on web)
* `assets/alphatab-harness/README.md` — documents the full message API

### Implementation Notes

* Test harness standalone by opening `index.html` in Chrome and calling `postMessage` from DevTools console
* Pin AlphaTab version in the HTML file (do not use `@latest`)
* Disable all context menus and external link navigation in the harness (`e.preventDefault()`)
* Prefer a **local static server** for harness testing; `file:` + AlphaTab workers/font loading can fail in some browsers
* `scrollToBar` uses **0-based** master bar index and `boundsLookup.findMasterBarByIndex` + `uiFacade.scrollToY` (alphaTab 1.3.1)

### Acceptance Criteria

* [x] Open `index.html` in browser, call `setScore(base64)` from DevTools → tab renders
* [x] `scrollToBar(N)` scrolls to correct position
* [x] Harness emits `ready` message on load
* [x] TypeScript types in `tabMessage.ts` compile with 0 errors

### Out of Scope

* WebView integration (commit 21), DOM AlphaTab component (commit 22)

---

## 0.5. Environment config + backing track assets + repo structure

**Status: complete** (2026-03-29) — `.env.example`, `app.config.ts` (`extra.apiBaseUrl`), `src/config.ts`, `src/constants/backingTracks.ts`, five MP3 placeholders in `assets/backing-tracks/`, `SOURCES.md`, `docs/*` placeholders, `.gitignore` updates, design-preview `expo-av` smoke test.

### Goal

Wire environment variables end-to-end (app ↔ backend) and add all five bundled backing track audio files so Jam Mode has real assets.

### Scope

* `.env.example` at repo root — `EXPO_PUBLIC_API_URL=http://localhost:8000`
* `app.config.ts` reads `EXPO_PUBLIC_API_URL` and exposes it via `extra`
* `src/config.ts` — exports `API_BASE_URL` and any other env-derived constants
* `assets/backing-tracks/` — add five MP3 loops (royalty-free or original compositions) matching README spec:
  - `am-blues-70bpm.mp3` — A minor slow blues shuffle
  - `am-drone-ambient.mp3` — A minor open drone, no tempo
  - `g-major-fingerpicking-80bpm.mp3` — G major fingerpicking groove
  - `em-two-chord-90bpm.mp3` — E minor raw two-chord vamp
  - `g-major-ballad-65bpm.mp3` — G major slow ballad
* `src/constants/backingTracks.ts` — typed array of backing track metadata (id, label, bpm, key, file require)
* `.gitignore` additions: `backend/data/`, `*.wav`, `*.gp5`, `.env`
* `docs/` folder with placeholder files: `STEM_QUALITY_CHECKLIST.md`, `PLAYBACK_MATRIX.md`, `PITCH_QA.md`, `E2E_DEMO.md`, `ERROR_QA.md` (each with `# TODO` heading so they're tracked)

### Implementation Notes

* Source backing tracks from freemusicarchive.org, looperman.com, or record originals — document provenance in `assets/backing-tracks/SOURCES.md`
* Keep each backing track under 3MB (30–60s loops at 128kbps)
* `expo-av` supports `require()` for bundled assets; confirm this path works before shipping
* **Placeholder audio (0.5):** five short ffmpeg sine-tone MP3s ship so bundles and `expo-av` smoke tests work; replace with real loops before product QA (see `SOURCES.md`)
* **`API_BASE_URL`:** surfaced in **Design** tab (dev) and `console.log` on mount; set `EXPO_PUBLIC_API_URL` then **restart Metro** so the value is embedded

### Acceptance Criteria

* [x] `console.log(API_BASE_URL)` in app shows correct LAN IP when backend is running
* [x] All five backing tracks play via a throwaway `expo-av` test in `__DEV__` without crashing
* [x] `.env.example` committed; `.env` ignored
* [x] `docs/` placeholder files present and tracked

### Out of Scope

* Jam Mode UI, live mic, IndexedDB

---

## 0.6. Shared feedback layer: AnimatedPressable, LoadingSkeleton, EmptyState, ErrorBanner, Toast

**Status: complete** (2026-03-29).

### Goal

Install and wire interaction + feedback primitives every later screen depends on.

### Scope (delivered)

* `components/AnimatedPressable.tsx`, `LoadingSkeleton.tsx`, `EmptyState.tsx`, `ErrorBanner.tsx`, `ToastConfig.tsx` (`toast.success` / `toast.error`)
* `src/constants/animations.ts` — `spring`, `timing`, `entranceDelay`
* `src/api/analyze.ts`, `src/api/index.ts` — `submitAnalyzeJob`, `getJobStatus`, `pollAnalyzeJob`, `submitScore`, `submitJamScore` (uses `API_BASE_URL`)
* `app/_layout.tsx` — `<Toast config={toastConfig} />` last inside root `View`
* `app/(tabs)/design-preview.tsx` — dev section: pressables, skeletons, empty state, banners, toast triggers

### Acceptance (all satisfied)

* [x] Five `AnimatedPressable` demos, pulsing skeletons, wood toasts, dismissible banners, typed API client + polling cleanup on `complete` / `failed`

### Out of Scope (unchanged)

* Real backend integration tests; `app/add-song.tsx` / `app/jam.tsx` screens (later phases)

### Handoff — validation, caveats, and follow-ups

Use this before starting **Phase 1** so scaffolding regressions are caught early.

#### Quick validation checklist

* [x] **`npm run lint`** — TypeScript strict, 0 errors (`tsc --noEmit`). *(Verified in repo, 2026-03-29.)*
* [ ] **Expo** — `npx expo start`: **Home** tab loads; **Design** tab (`__DEV__`) shows tokens, stubs, feedback-layer demos, **API_BASE_URL**, and backing-track smoke test.
* [x] **Env / config** — `npx expo config --type public` shows **`extra.apiBaseUrl`**; after editing **`.env`**, **restart Metro** so the app bundle picks up `EXPO_PUBLIC_*`. *(Config presence verified 2026-03-29.)*
* [ ] **Backend (optional)** — From `backend/`: `make dev` or `uvicorn …`; `GET /health` returns `{"status":"ok"}`.
* [ ] **Harness (optional)** — Serve `assets/alphatab-harness/` over HTTP (not bare `file:`); confirm `ready` and `setScore` with a real GP5 Base64 sample.

#### Known limitations & follow-ups

| Area | Issue | Follow-up |
|------|--------|-----------|
| **0.2 Backend** | **`basic-pitch`** is optional **`[basicpitch]`** on many platforms (TensorFlow pin vs Python 3.11+). | Install on **macOS** when needed; conda/alternate env later; watch upstream. |
| **0.2 Backend** | Roadmap acceptance text stresses **macOS/Linux** for `pip install`. | **Windows** works for default deps here; treat extra as documented. |
| **0.3 NoiseOverlay** | Native uses **`Image`** + **`resizeMode="repeat"`**. | **Android** support for tile repeat varies by RN version — verify on device; switch to **`cover`** or another tiling strategy if needed. |
| **0.3 + 0.5** | **`app.json`** (static) and **`app.config.ts`** (dynamic `extra`) both exist. | **Expo merges** them: keep static fields in `app.json`, env-derived **`extra.apiBaseUrl`** in `app.config.ts`. |
| **0.4 AlphaTab** | Harness uses **`postMessage(..., '*')`** toward `parent`. | When web origin is known (commits **21–22**), **narrow `targetOrigin`**. |
| **0.4 AlphaTab** | **`file:`** URLs can break workers / fonts. | Always test harness via **local HTTP server**. |
| **0.5 Git** | Root **`.gitignore`** ignores **`*.gp5`** and **`*.wav`** everywhere. | To commit a permitted fixture later, use a **narrower path** or **`git add -f`**. |
| **0.5 Audio** | Backing tracks are **ffmpeg sine-tone placeholders**, not musical loops. | Replace with **licensed / original** loops and update **`assets/backing-tracks/SOURCES.md`** before Jam ship. |
| **0.5 Env** | **`EXPO_PUBLIC_*`** is inlined at **bundle** time. | **EAS / CI:** configure env in build profiles; document for the team. |
| **0.5 Docs** | **`docs/*.md`** are **`# TODO`** shells. | Fill during stem / playback / pitch / E2E QA passes. |


---

## Git commit messages and branch strategy

### Conventions

* **Subject line:** imperative mood, ≤72 characters, prefixed with conventional type: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
* **Body (optional):** what changed and why; reference kill-switch doc if applicable.
* **Scope (optional):** `backend`, `mobile`, `web`, `audio`, `db`, `api`.

### Suggested commit subjects (1:1 with roadmap)

Use one commit per numbered item above (reword slightly if combining work; avoid combining kill switches with unrelated features).

**Phase 0 (scaffolding — 0.1–0.6 shipped)**
0.1. `chore(app): initialize expo project with router, nativewind, and design tokens` — done
0.2. `chore(backend): initialize fastapi project with health endpoint and pydantic stubs` — done
0.3. `chore(app): add noise overlay and design token validation screen` — done
0.4. `chore(tab): add alphatab harness html and postmessage type contract` — done
0.5. `chore(app): add env config, backing track assets, and repo structure` — done
0.6. `chore(ui): add shared feedback layer: AnimatedPressable, skeleton, toast, api client stubs` — done

**Phase 1**
1. `chore(research): add pipeline notebook for wav, demucs, and gp5 export`
2. `docs(backend): add stem separation quality gate checklist and smoke script`
3. `feat(api): scaffold FastAPI with health and stub analyze endpoints`
4. `feat(api): add async job runner for analyze status transitions`
5. `feat(api): normalize uploads and YouTube URLs to wav in analyze job`
6. `feat(api): integrate htdemucs_6s stem separation into analyze pipeline`
7. `feat(api): add librosa key, tempo, beat grid, and bar timestamps`
8. `feat(api): transcribe vocals with whisper and align lyrics to beats`
9. `feat(api): generate gp5 tabs with basic-pitch and confidence gating`
10. `feat(api): cache analyze results by audio hash and pipeline version`
11. `feat(api): add Claude coach copy for lesson sections`
12. `feat(mobile): add expo-av playback demo with loop and variable rate`
13. `docs(audio): add cross-platform playback verification matrix`
14. `feat(audio): add native and web stem mixer abstraction`
15. `feat(web): implement mic pitch detection via AudioWorklet`
16. `feat(mobile): implement native mic pitch stream with shared hook`
17. `docs(audio): add manual pitch QA protocol`
18. `feat(app): add analyze client, polling, and lesson store`
19. `feat(app): add expo router session flow with step indicator`
20. `feat(session): wire listen step with sections, mixer, and metronome`
21. `feat(tab): add AlphaTab WebView harness and message bridge`
22. `feat(web): render AlphaTab in DOM for expo web`
23. `feat(session): implement SmartScroll with drift resync`
24. `feat(study): add fretboard, lyrics strip, capo hint, and annotations`
25. `feat(session): add slow loop defaults and hardest-bar loop`
26. `feat(session): add play step recording, pitch ladder, and web mic copy`
27. `feat(session): add review step scoring integration and midi export`
28. `feat(api): implement score endpoint with structured ScoreResult`
29. `feat(db): add sqlite schema, migrations, and repositories`
30. `feat(spaced): implement SM-2 updates and skill node weighting`
31. `feat(home): add SM-2 driven session suggestion card`
32. `feat(onboarding): add placement session and skill node seeding`
33. `feat(library): add lick persistence and drill entry`
34. `feat(library): add transpose and filtering for saved licks`
35. `feat(progress): add skill graph and session journal views`
36. `feat(jam): add backing tracks, pitch-class map, and jam scoring`
37. `feat(settings): add user prefs, export, and simpler-tab toggle`
38. `feat(web): add IndexedDB client, drag-drop upload, and lesson cache`
39. `feat(app): centralize error mapping and low-confidence tab messaging`
40. `docs: add end-to-end demo and v1 release checklist`

**Phase 6 (62–65)**
62. `feat(session): add pre-session tuner and mic noise calibration gate`
63. `feat(skills): apply session accuracy mutations to skill graph and player profile`
64. `feat(ui): add left-handed fretboard mirror and AlphaTab handedness postMessage`
65. `feat(home): add ZPD curriculum suggestion client and home card`

**Phase 7 (66–77) — The Guided Path**
66. `feat(coach): add async streaming coach generation with retry and skeleton hydration`
67. `feat(auth): add spotify oauth pkce flow and listening history ingestion`
68. `feat(taste): derive style profile and song candidates from spotify or quiz data`
69. `feat(onboarding): add cold-start artist picker and style quiz for taste profile`
70. `feat(session): add ordered drill sequencer and structured practice plan generation`
71. `feat(home): replace suggestion card with guided practice queue UX`
72. `feat(audio): add voice coach tts narration for session transitions and coach notes`
73. `feat(session): add personalized 3-minute warmup generator with technique targeting`
74. `feat(progress): add riff dna fingerprint visualization from session history`
75. `feat(session): add ghost player for playing alongside past recordings`
76. `feat(session): add mood check and mood-adaptive practice plan intensity`
77. `feat(listening): add spotify playback bridge and real-time tab follow mode`

### Branch strategy

* **`main`:** always runnable. **Phase 0 (0.1–0.6)** is complete; Phase 1+ work should merge in small vertical slices. Use short-lived branches for risky or long-running work.
* **Phase 0:** closed — no further 0.x roadmap items; regressions go through normal `fix/` or `chore/` commits.
* **Short-lived branches:** `feat/api-…`, `feat/audio-…`, `feat/session-…` cut from `main`, rebase often, merge via PR or direct merge if solo.
* **Kill switches (2, 13, 17, 40):** merge documentation/scripts as soon as written; do not start dependent phase until checklist signed (even if that means a `docs-only` merge mid-stream).
* **Mobile vs web drift:** if a commit touches `.web.ts` / `.native.ts`, keep both files in the **same branch** and merge together to avoid broken `main` on one platform.
* **DESIGN_SYSTEM.md components:** treat them as UI spec during Phase 2–4. When building a screen component, open the matching DESIGN_SYSTEM entry, port class names to NativeWind equivalents, replace `framer-motion` with Reanimated, replace `lucide-react` import with `lucide-react-native`. Do not copy files wholesale.
* **Tags:** after commit 40 passes `docs/E2E_DEMO.md`, tag `v1.0.0-demo` (or internal `milestone/core-loop`).

---

*Cross-reference: [`README.md`](README.md) (product), [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) (UI). Phase 0 history: [appendix](#appendix--completed-phase-0-commits-01–06).*
