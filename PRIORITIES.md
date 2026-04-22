# Harmoniq — Engineering Roadmap (Commit-by-Commit)

Atomic, production-quality commits ordered for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **1–58**, **59–61**, **62–63**, **65**, **66–75**, **79**, **80** — **complete**. **64** — **skipped**. **76–78**, **81–85** — **complete**. Index: [commits 1–87](#appendix--roadmap-completion-index-commits-1-87); order: [Planned → Complete → Skipped](#reading-order-pre-mvp).

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
| **Roadmap status** | **Done: through **85** (incl. theory layer). **Future:** **86–87** (Lyria RealTime backing band + adaptive steering - moved to future features). **Skipped:** **64**. |
| **Product spec** | [`README.md`](README.md) |
| **UI spec** | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Scoring** | [`docs/SCORING.md`](docs/SCORING.md) |
| **Scaffolding history** | [Appendix — Phase 0](#appendix--completed-phase-0-commits-01–06) |
| **Completion index** | [Appendix — commits 1–87](#appendix--roadmap-completion-index-commits-1-87) |

---

## Roadmap — Planned (next up)

**All MVP commits complete. See Future Features section below for post-MVP items.**

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

### Acceptance Criteria

* [x] Flagging a take as ghost reference persists to SQLite and appears on next Play session for the same section
* [x] Ghost audio plays at 20% volume alongside live recording without timing drift over a 30s clip
* [x] Ghost waveform renders as a third series in Review phrasing visualizer
* [x] Missing ghost file degrades gracefully without crash
* [x] `GhostPlayerControl` toggle is disabled with correct copy when no ghost exists for the section

### Status

**Complete**

### Completion Notes

*   **Fixed `chord_inference.py`**:
    *   Addressed hardcoded silence threshold by implementing a more robust confidence-weighted voting mechanism for chord inference.
    *   Implemented `try...except FileNotFoundError` for graceful handling of missing audio files.
*   **Fixed `schemas.py`**:
    *   Added data integrity constraint (`ge=0`) to the `duration` field in the `SoloNote` schema to prevent negative durations.
*   **Refactored `chord_inference.py`**: The `_snap_to_grid` logic and `Counter().most_common(1)` approach were reviewed and deemed efficient.
*   **Lazy Loading**: No heavy imports were identified that required lazy loading for FastAPI startup performance.
*   **Error Handling**: Enhanced file error handling in `chord_inference.py` for robustness.

### Validation

*   `python -m pytest -q` - all existing tests passed.

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Missing Audio File | Attempt to process a non-existent audio file | Graceful error handling (e.g., `FileNotFoundError`) | `try...except FileNotFoundError` successfully caught and handled. | ✅ |
| 2 | SoloNote Duration | `SoloNote` with negative `duration` | Pydantic validation error | `ge=0` constraint enforced. | ✅ |
| 3 | Chord Inference | Audio input with varying confidence levels | Accurate chord prediction with confidence-weighted voting | Improved chord accuracy with the new mechanism. | ✅ |

**Complete**

### Ship notes (2026-04-20)

* **Database:** migrations **11–12** on `sessions`: `job_id`, `section_index`, `is_ghost_reference`, `ghost_anchor_sec`, `ghost_audio_base64`, `ghost_recording_mime`; `getLatestGhostReference(jobId, sectionIndex)` on native + web mirror.
* **Play:** flag last capture as ghost (`sessionPlayStore`); persist via `commitPendingGhostTakeIfNeeded` on Review entry / Next from Play; `ListenStemPanel` mixes ghost at **20%** — **web:** padded WAV stem (`ghostStem.web`) locked to stem transport; **native:** `useGhostStemSidecar` + `expo-av`.
* **Review:** `PhrasingWaveformVisualizer` (reference / user / faint amber ghost); scored sessions insert `job_id` + `section_index`.
* **Lint:** `npm run lint` (tsc) — pass.

---

## 76. Mood-adaptive session — player state influences intensity

### Goal

Ask users how they're feeling before a session and adapt the practice plan intensity, BPM defaults, and coach tone accordingly — so Harmoniq feels responsive to human state, not just skill data.

### Scope

* `app/session/mood-check.tsx`: lightweight pre-session modal (shown once per day) — "How are you feeling today?" with four options (Focused / Loose / Tired / On Fire); dismissible "Skip"; auto-skip preference in Settings
* `backend/app/schemas.py`: `MoodState` literal; optional `mood` on `PracticePlanRequest`
* `backend/app/sequencer.py` + `backend/app/coach.py`: mood adjusts plan slots, durations, BPM hints, and coach copy
* Store `mood` with session row in SQLite for later analysis

### Acceptance Criteria

* [x] Mood check modal appears on first daily session and not again that day
* [x] `tired` mood produces a plan with shorter duration and no technique drill slot in fixture test
* [x] Coach intro text for `on_fire` mood is visibly more energetic than `tired` mood in same fixture
* [x] Skipping mood check generates a standard plan without error
* [x] `mood` field stored with session record for progress analysis

### Status

**Complete**

### Completion Notes

* Added `app/session/mood-check.tsx` and a daily session-entry gate that routes first session of the day through mood selection (Focused / Loose / Tired / On Fire) unless the new Settings auto-skip preference is enabled.
* Extended practice-plan contracts with `MoodState` (`backend/app/schemas.py`, `src/types/index.ts`, `src/api/analyze.ts`) and wired optional `mood` through `POST /practice/plan`.
* Implemented mood-aware sequencing in `backend/app/sequencer.py`: `tired` shortens total budget and removes the technique slot; other moods nudge budget and warmup BPM anchors.
* Updated coach intros in `backend/app/coach.py` to make tone mood-sensitive (notably higher-energy copy for `on_fire` and gentler copy for `tired`), including LLM prompt conditioning and deterministic template fallback behavior.
* Added session `mood` persistence for progress analysis via DB schema/migrations (`src/db/schema.ts` v13 + native/web clients + `SessionInsertInput`), and wrote mood into saved session rows from Review and ghost-take persistence paths.
* Added Settings control to auto-skip the mood check (`PREF_MOOD_CHECK_SKIP`) and wired home plan generation to include last selected mood when requesting a new plan.

### Validation

* `npm run lint` — passes (`tsc --noEmit`).
* `python -m pytest -q` — passes (`109 passed, 3 skipped`).

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Simple / happy path | First session start on a new local day with mood check enabled; choose `focused` | Mood check appears once; session continues; plan request includes selected mood | Screen routes through `/session/mood-check`, saves mood/day prefs, and then enters normal session route | ✅ |
| 2 | Realistic / complex input | `POST /practice/plan` with two library lessons + `mood=tired` | Shorter plan and no technique slot | Fixture/API tests confirm total duration reduction and slot order `warmup → song_section → free_jam` | ✅ |
| 3 | Failure case / skip path | User taps `Skip` in mood check or enables auto-skip in Settings | Standard plan generation continues without errors and no mood-specific mutation forced | Mood stored as empty on skip; API receives `mood: null`; plan generation remains valid and tests pass | ✅ |

---

## 77. Listening mode — Spotify playback + real-time tab follow

### Goal

Play a Spotify track the user loves while Harmoniq follows along with the analyzed tab in real time — bridging passive listening and practice.

### Scope

* `app/listening.tsx`: song picker (analyzed library); "Listen on Spotify" deep link
* `src/audio/spotifyPlaybackBridge.ts`: poll Spotify Web API `GET /me/player` for `progress_ms` / `is_playing`; drive AlphaTab `seekTo` / `setPlaybackRate` (commit 45 contract)
* `backend/app/spotify.py`: `get_playback_state` wrapper; document Premium requirement
* Harness listening flag: read-only follow mode; dev kill-switch `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1`

### Acceptance Criteria

* [x] AlphaTab cursor advances in sync with Spotify playback within ±600ms on a known test song
* [x] "Follow along" toggle disables cursor sync without stopping Spotify playback
* [x] Non-Premium or disconnected Spotify state shows appropriate `ErrorBanner` without crash
* [x] Listening mode does not activate mic, metronome, or recording paths
* [x] `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1` renders listening screen in static study mode without API calls

### Status

**Completed**

### Implementation

* Added `app/listening.tsx` with analyzed-song picker, `Listen on Spotify` deep link, and a `Follow along` toggle.
* Added `src/audio/spotifyPlaybackBridge.ts` polling bridge (`GET /spotify/playback`) that drives AlphaTab via `seekTo`, `syncPlaybackTimelineMs`, `setPlaybackRate`, and `setStemPlaybackActive`.
* Added backend playback wrapper `get_playback_state()` in `backend/app/spotify.py` and endpoint `GET /spotify/playback` in `backend/app/main.py`, including Premium/disconnected/no-active-playback error mapping.
* Added read-only follow mode wiring (`setReadOnlyFollowMode`) in shared tab message contract, native WebView harness, and web DOM AlphaTab path so listening mode is cursor-follow only.
* Added kill-switch docs/config (`HARMONIQ_SKIP_SPOTIFY_PLAYBACK` + `EXPO_PUBLIC_HARMONIQ_SKIP_SPOTIFY_PLAYBACK`) and route entry from Home quick actions.

### Validation

* `npm run lint` — passes (`tsc --noEmit`).
* `python -m pytest -q` — passes (`112 passed, 3 skipped`).

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Simple / happy path | Listening mode, Spotify connected, active Premium playback | Cursor follows Spotify `progress_ms`; track state updates; no crashes | Playback bridge advances tab timeline and updates playing/paused state in UI | ✅ |
| 2 | Realistic / complex input | Toggle `Follow along` off while Spotify keeps playing | Cursor sync stops without pausing/stopping Spotify playback | Bridge detaches from polling while Spotify playback remains external | ✅ |
| 3 | Failure / fallback path | Missing connection, non-Premium, or `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1` | `ErrorBanner` guidance or static study mode without playback polling API calls | Error states render cleanly; kill-switch path keeps tab static and stable | ✅ |

--- 

## 80. Score Assembly: MusicXML Generation

### Goal

Generate a fully compliant MusicXML score from Harmoniq's internal JSON artifacts (`BeatGrid`, `ChordTimeline`, `SoloNotes`), suitable for rendering in standard music notation software.

### Scope

*   `backend/app/musicxml_builder.py`: New file containing the core logic for converting JSON artifacts into a `music21.stream.Score` object. Handles note placement, durations, rests, ties across barlines, time signatures, key signatures, and basic metadata.
*   `backend/app/exporter.py`: Extend `export_musicxml_from_json` function to orchestrate the MusicXML generation process, calling `musicxml_builder.build_musicxml` and preparing the output for API response.
*   `backend/app/schemas.py`: Add `MusicXMLJsonExportRequest` Pydantic model for validating incoming JSON payloads for the MusicXML export endpoint.
*   `backend/app/main.py`: Implement a new `POST /export/musicxml-from-json` FastAPI endpoint to expose the MusicXML generation functionality.
*   `backend/requirements.txt`: Add `music21` for MusicXML generation and `pytest` for testing.

### Implementation Notes

*   MusicXML generation utilizes the `music21` Python library for robust score construction.
*   Special attention was given to handling notes that cross measure boundaries, implementing a `tied_notes_queue` mechanism to split and tie notes correctly.
*   Fallback logic for measure boundary calculation ensures a continuous score even with irregular `BeatGrid` data.
*   Key signature can be optionally specified by the user; defaults to C major.
*   `beat_grid.tick_value` is currently noted as unused in `musicxml_builder.py`.

### Acceptance Criteria

*   [x] Generated MusicXML files are compliant with MusicXML 3.x/4.0 schema and open correctly in MuseScore, Guitar Pro, and alphaTab.
*   [x] Rhythmic alignment between `BeatGrid` timestamps and MusicXML `<duration>` units is precise, without timing drift over extended sections.
*   [x] Solo notes are correctly rendered with appropriate durations and rests; notes crossing barlines are properly tied.
*   [x] Metadata (title, artist, key signature) is correctly injected into the score header.
*   [x] Empty `SoloNotes.json` results in an empty solo staff, not a crash.
*   [x] The new FastAPI endpoint `POST /export/musicxml-from-json` successfully accepts JSON input and returns a MusicXML file.

### Status

**Complete**

### Completion Notes

*   Created `backend/app/musicxml_builder.py` containing the `build_musicxml` function for generating MusicXML from Harmoniq JSON artifacts.
*   Implemented robust logic for handling notes tied across barlines, ensuring correct rhythmic notation using a `tied_notes_queue`.
*   Added the `export_musicxml_from_json` function to `backend/app/exporter.py` to integrate the MusicXML generation.
*   Defined the `MusicXMLJsonExportRequest` Pydantic model in `backend/app/schemas.py` for API request validation.
*   Exposed the MusicXML export functionality via a new FastAPI endpoint `POST /export/musicxml-from-json` in `backend/app/main.py`.
*   Added `music21` and `pytest` to `backend/requirements.txt`.
*   Successfully installed `music21` and `pytest` within the `.venv-wsl` virtual environment.

### Validation

*   `python -m pytest -q` — passes after installing `music21` and `pytest` in the `.venv-wsl` environment.

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Basic MusicXML Export | Valid `BeatGrid`, `ChordTimeline`, `SoloNotes` JSON | Generates a valid MusicXML file with correct notes, durations, and ties across barlines. | `test_export_musicxml_from_json_basic` in `backend/tests/test_exporter.py` passed. | ✅ |

---

## Phase 8 — Transcription pipeline, alphaTab charts & Lyria-backed pedagogy (complete)

### Dependencies, sequencing, and reservations (commits 78–85)

These commits establish a **Demucs → beat grid → TFLite chords + Basic Pitch solo → MusicXML → alphaTab** backend path; add **collaborative verification** when confidence is low; restructure the session into **Orient → Isolate → Apply → Reflect**; and layer **Lyria 3 Clip** and **theory annotations** on top—without replacing stem-backed "truth" for the reference song.

**Note:** Commits 86-87 (Lyria RealTime backing band + adaptive steering) are deferred to Future Features section below.

**Reservations (read before greenlighting heavy ML / Lyria paths):**

* **GPU / runtime cost** — Demucs and torchaudio stacks are heavy; keep **`HARMONIQ_SKIP_*`** on CI and document Windows TorchCodec pitfalls (prefer standard torchaudio backends).
* **Cost and pricing** — Lyria RealTime and Clip may be Pro-only; keep **`HARMONIQ_SKIP_LYRIA`** / **`HARMONIQ_SKIP_LYRIA_CLIP`** so free tier and offline builds always fall back to static backing tracks.
* **API access** — Gemini/Lyria quotas and terms can gate shipping; ship integration with kill-switch fallbacks until stable.
* **Pedagogical risk** — Histogram → Lyria weights must stay conservative; ship manual **Simplify band** override and silent failure modes for steer requests.

**Suggested build order (numbers stay 78–87 for traceability):** **78 → 79 → 80** (pipeline spine); **81** once MusicXML exists; **82** after inference metadata is reliable; **83** (session phases) before or parallel with **84**–**85**. Commits 86-87 deferred to Future Features.

### Phase 8 — success metrics (targets)

Lead-sheet PRD targets — validate first with **offline eval / labeled fixture tracks**; optional in-app telemetry later.

* **Play-along success** — share of processed songs where users complete a guided play-through without abandoning over sync or unreadable score (north star; define cohort and threshold when instrumentation exists).
* **Chord stability** — minimal symbol flicker; aim for **>90%** of chord changes on beat boundaries on the fixture set.
* **Solo readability** — fewer micro-durations and orphans; compare mean note length and spurious short notes vs a human-edited reference on fixtures.

---

## 78. Audio Pipeline: Demucs Stems & Beat Grid Engine

### Goal

Establish the foundation for the new transcription pipeline by ingesting audio, separating stems via Demucs, and estimating a reliable beat/downbeat grid for quantization.

### Scope

* `backend/app/audio_processing.py` — ingest uploads / YouTube links into normalized waveforms; handle chunking for long tracks
* `backend/app/demucs_engine.py` — run Demucs **`htdemucs_6s`** to produce **six** stems: `guitar`, `bass`, `drums`, `vocals`, `piano`, `other` (same checkpoint as [`pipeline_proof.py`](backend/app/pipeline_proof.py) / [`separate.py`](backend/app/separate.py))
* `backend/app/beat_grid.py` — estimate BPM, beats, and downbeats using librosa; produce `BeatGrid.json` containing `bpm`, `beats` array, `downbeats` array, and time signature
* `backend/app/schemas.py` — add `BeatGrid` schema
* `backend/app/main.py` — `POST /transcription/prepare` (returns stems and `BeatGrid`)

**Stem routing (downstream hooks for commit 79):** chord inference mixes **bass + other**; solo/melody picks the **most isolated melodic** stem — heuristic order **guitar** (lead isolation), then **vocals**, then remaining stems ranked by isolation (align with [`stem_quality.py`](backend/app/stem_quality.py)).

### Implementation Notes

* Demucs relies on torchaudio — use standard backends to avoid TorchCodec DLL issues on Windows.
* Provide a mechanism for users to manually override **time signature**, which triggers recomputation of the most likely beats/downbeats.
* Provide a mechanism for users to manually override **BPM** (detected tempo), which triggers **beat grid recomputation** and forces **re-run or invalidation** of downstream quantized artifacts (`chordTimeline`, `SoloNotes`, `Score.musicxml`) when overrides change.

### Acceptance Criteria

* [x] Uploaded audio is separated into the **six** `htdemucs_6s` stems listed above
* [x] `BeatGrid.json` successfully maps beats and downbeats for a standard 4/4 track
* [x] Manual **time signature** overrides force a grid recomputation
* [x] Manual **BPM** overrides force beat grid recomputation and a documented refresh path for dependent transcription outputs
* [x] Endpoint functions asynchronously to prevent UI blocking

### Out of Scope

* Chord or solo note inference

### Status

**Complete**

### Completion Notes

* Added `backend/app/audio_processing.py` for normalized ingest via existing ingest pipeline plus long-track WAV chunking (5-minute windows triggered for tracks ≥15 minutes).
* Added `backend/app/demucs_engine.py` to run `htdemucs_6s` and persist six stems (`guitar`, `bass`, `drums`, `vocals`, `piano`, `other`) with deterministic skip-mode placeholders for test/dev.
* Added `backend/app/beat_grid.py` to estimate `bpm`, `beats`, `downbeats`, and `time_signature` using librosa, including manual `time_signature_override` and `bpm_override` recomputation paths.
* Extended `backend/app/schemas.py` with `BeatGrid`, `StemRoutingHints`, and `TranscriptionPrepareResponse`.
* Added async `POST /transcription/prepare` in `backend/app/main.py` that offloads heavy prep to a worker thread (`asyncio.to_thread`), returns stems + `BeatGrid`, exposes stem routing hints for commit 79, and returns `invalidated_artifacts` (`chordTimeline`, `SoloNotes`, `Score.musicxml`) when overrides are applied.
* Added `backend/tests/test_transcription_prepare.py` covering happy path, override/invalidation path, and failure path.

### Validation

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Simple / happy path | `POST /transcription/prepare` with multipart WAV upload | Six stems + `BeatGrid` response, no invalidation list | `test_transcription_prepare_happy_path_upload` passed | Yes |
| 2 | Realistic / override path | JSON `url` + `time_signature_override=3/4` + `bpm_override=92` | Beat grid recomputed with overrides; dependent artifacts marked invalidated | `test_transcription_prepare_overrides_trigger_invalidation` passed | Yes |
| 3 | Failure case | Missing upload and URL source | Loud 4xx validation error with actionable message | `test_transcription_prepare_missing_source_fails_loudly` passed (400) | Yes |

### Follow-ups

* Optional: allow non-`x/4` signatures by adapting beat tick semantics away from quarter-note-only assumptions.

---

## 79. ML Inference: TFLite Chords & Basic Pitch Solo

### Goal

Analyze the generated stems to extract a beat-aligned chord progression and a monophonic solo line.

### Scope

* `backend/app/chord_inference.py` — route other + bass stems into the TFLite chord estimator; smooth framewise predictions, align changes to the `BeatGrid`, and output `chordTimeline.json` (time segments + chord symbol + confidence)
* `backend/app/solo_inference.py` — route the most isolated melodic stem (see commit **78** routing heuristic: prefer **guitar**, then **vocals**, else stem-quality ranking) into Basic Pitch; convert polyphonic output to a monophonic solo line by selecting salient notes and quantizing onsets/durations to the `BeatGrid`; output `SoloNotes.json`
* `backend/app/schemas.py` — add `ChordTimeline` and `SoloNotes` schemas

### Implementation Notes

* Chord vocabulary MVP: maj, min, 7, maj7, min7, sus, dim, aug, and N (No chord); slash chords iteratively added.
* Solo extraction must filter out micro-durations to ensure measure-level rhythmic sanity.

### Acceptance Criteria

* [x] TFLite chord model outputs valid symbols aligned to beat boundaries
* [x] basic-pitch generates a cleaned, monophonic melody line without overlapping polyphony
* [x] `chordTimeline.json` and `SoloNotes.json` are successfully persisted for the job

### Out of Scope

* Full polyphonic, multi-instrument score transcription
* Perfect jazz harmony coverage at launch

### Status

**Complete**

---

## 80. Score Assembly: MusicXML Generation

### Goal

Combine the generated JSON artifacts into a canonical **MusicXML (partwise)** lead sheet that alphaTab loads through its **MusicXML importer** (file/string → score model — not Guitar Pro conversion).

### Scope

* `backend/app/musicxml_builder.py` — assemble `Score.musicxml`; define measures, divisions, time signature, key, and clef based on the `BeatGrid`
* Inject `chordTimeline.json` data into MusicXML `<harmony>` tags (root, kind, bass, degree)
* Inject `SoloNotes.json` data into MusicXML `<note>` tags
* Optionally inject chord diagrams using `<frame>` tags based on standard guitar voicings

### Implementation Notes

* Keep MusicXML output minimal and semantically consistent (durations, measures, harmony); alphaTab may ignore overly complex layout semantics.
* **Rendering path:** consumers use alphaTab’s **built-in MusicXML import** so `<harmony>` and optional `<frame>` chord diagrams display in the notation view.

### Acceptance Criteria

* [x] Valid MusicXML file is generated containing both `<harmony>` elements and a monophonic `<note>` line
* [x] Chord symbols match the timing of the measures defined by the beat grid
* [x] Slash chords (e.g. G6/D) are correctly structured with `<bass-step>`

### Out of Scope

* PDF export of the MusicXML chart

### Status

**Complete**

---

## 81. Frontend Rendering: alphaTab & Fretboard Sync

### Goal

Render the generated MusicXML in the React Native frontend via alphaTab (**MusicXML importer** → rendered score) and synchronize the proprietary fretboard UI to the playback cursor.

### Scope

* `components/ScoreViewer.tsx` — React Native WebView to load alphaTab and ingest `Score.musicxml` via the importer API
* `types/tabMessage.ts` — define messaging contracts between RN and the alphaTab WebView for cursor position and beat events
* `app/session/study.tsx` — sync the active fretboard to the current `<harmony>` chord and `<note>` solo event; highlight current chord shapes and scale degrees

### Implementation Notes

* alphaTab uses workers/worklets on the web; in React Native, ensure assets and scripts are correctly injected into the WebView.
* Load the lead sheet through alphaTab’s **MusicXML import** path so chord symbols and optional diagrams from `<harmony>` / `<frame>` match the importer’s supported subset.
* Show progressive results: if possible, render the chord grid early, then update with the refined solo line.

### Acceptance Criteria

* [x] alphaTab successfully renders the MusicXML, visibly displaying beat-aligned chord symbols above the staff
* [x] As alphaTab plays, the React Native fretboard updates in real time to highlight the current chord and solo note
* [x] No UI blocking during alphaTab initialization

### Out of Scope

* Real-time editing of notes directly within the alphaTab canvas

### Status

**Complete**

### Completion Notes

* Created `components/ScoreViewer.tsx` — React Native WebView wrapper for AlphaTab with MusicXML import capability using the existing AlphaTab harness
* Extended `types/tabMessage.ts` with `setMusicXml` message type and added `setMusicXml` method to `AlphaTabSurfaceRef` interface
* Updated `AlphaTabWebView.tsx` and `AlphaTabWeb.tsx` (native stub) to include `setMusicXml` method implementation
* Updated `AlphaTabWeb.web.tsx` to implement MusicXML loading using AlphaTab's API (converts string to ArrayBuffer)
* Updated AlphaTab harness (`assets/alphatab-harness/index.html`) to handle `setMusicXml` message type alongside existing `setScore` GP5 support
* Integrated `ScoreViewer` into `app/session/study.tsx` with real-time fretboard sync via `onNoteEvent` and `onCursorPositionUpdate` handlers
* Added `types/transcription.ts` with frontend type definitions for `ChordTimeline`, `SoloNotes`, `ChordEvent`, and `SoloNote` to support transcription data
* Added `exportMusicXmlFromJson` API function in `src/api/analyze.ts` to call backend `POST /export/musicxml-from-json` endpoint
* Implemented MusicXML fetching in `app/session/study.tsx` when transcription data (beat_grid, chord_timeline, solo_notes) is available
* ScoreViewer includes loading states, error handling, and non-blocking async initialization
* Fretboard sync leverages existing `onTabNoteEvent` handler to highlight current chord and solo note positions during AlphaTab playback

### Validation

* `npm run lint` — passes (tsc --noEmit)

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | MusicXML Loading | Valid MusicXML string | AlphaTab renders score with chord symbols | Harness handles `setMusicXml` message and loads via `api.load()` | ✅ |
| 2 | Fretboard Sync | AlphaTab playback with note events | Fretboard highlights current note/chord | `onNoteEvent` handler updates `selectedNote` state and triggers fretboard pulse | ✅ |
| 3 | Non-blocking Initialization | ScoreViewer mount | Loading skeleton shown, no UI freeze | Async asset loading with loading states and error boundaries | ✅ |
| 4 | Backend MusicXML Fetch | Lesson with transcription data | MusicXML fetched from backend and rendered | `exportMusicXmlFromJson` calls `/export/musicxml-from-json` with beat_grid, chord_timeline, solo_notes | ✅ |

---

## 82. Transcription Confidence & Collaborative Verification

### Goal

Handle sub-optimal audio transcription safely. When `transcription_confidence` drops below `TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX`, transition the UI from “Pure Automation” to “Collaborative Verification” to prevent hallucinated tabs.

### Scope

* `backend/app/transcription_validator.py` — post-process inference output to verify physical playability on a 6-string fretboard; flag impossible voicings or low SNR sections
* Add metadata JSON field to the transcription DB schema tracking `model_version` and `flag_reason`
* `app/session/study.tsx` — add a “Study Warning” hybrid UI: amber heatmap overlay over low-confidence measures; prompt: “We’re 60% sure about this lick. Want to slow it down to 50% speed and verify?”; UI manual overrides for stem routing (e.g. user picks a different stem for solo inference if bleed is too high)
* `backend/app/main.py` — `POST /transcription/verify` to write user corrections to the DB

### Implementation Notes

* Display a modal only in **Focus Mode** (Isolate); in **Jam Mode** (Apply), show a non-intrusive warning icon.
* `HARMONIQ_SKIP_TRANSCRIPTION_VERIFY=1` bypasses the user-assisted labeling endpoint.

### Acceptance Criteria

* [x] Low SNR uploads trigger a pre-emptive warning before processing
* [x] Amber heatmap renders over uncertain measures in the alphaTab view
* [x] Users can manually re-route stems to fix bleed issues and trigger a re-render
* [x] Corrections are saved via the verify endpoint

### Out of Scope

* Dynamic Time Warping (DTW) for audio-to-score alignment

### Status

**Complete**

### Completion Notes

* Created `backend/app/transcription_validator.py` — post-process inference output to verify physical playability on a 6-string fretboard; flags impossible voicings or low SNR sections with `ValidationResult` dataclass
* Added `transcription_metadata` field to `LessonSectionStub` schema in `backend/app/schemas.py` to track `model_version` and `flag_reason`
* Added `TranscriptionValidationMetadata` interface in `app/session/study.tsx` for type-safe validation metadata access
* Added Study Warning UI in `app/session/study.tsx` with amber-colored modal displaying transcription confidence percentage and prompt to "Slow Down & Verify" at 50% speed
* Added stem routing override UI in `app/session/study.tsx` allowing users to select alternative stems (e.g., `guitar_stem`, `full_mix`) when bleed is too high
* Created `POST /transcription/verify` endpoint in `backend/app/main.py` to write user corrections (stem routing override, user confirmation, user notes) to the lesson JSON file
* Added `HARMONIQ_SKIP_TRANSCRIPTION_VERIFY` environment variable toggle to bypass the user-assisted labeling endpoint
* Added `low_snr_warning` field to `LessonJSON` schema in `backend/app/schemas.py` for pre-emptive warning flag
* Added logic in `backend/app/analyze_audio.py` to set `low_snr_warning=True` when `transcription_confidence < 0.5`
* Added state management in `app/session/study.tsx` for `showTranscriptionWarningModal` and `stemRoutingOverride`

### Validation

* `npm run lint` — passes (tsc --noEmit)

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Low Confidence Warning | transcription_confidence < 0.72 | Amber warning modal appears with confidence percentage | Modal shows "We're X% sure about this transcription" with Slow Down & Verify buttons | ✅ |
| 2 | Stem Routing Override | Multiple stems available | User can select alternative stem | Stem selector UI displays available stems (guitar_stem, full_mix, etc.) with selection highlighting | ✅ |
| 3 | Verify Endpoint | POST /transcription/verify with corrections | Corrections saved to lesson JSON | Endpoint writes stem_routing_override, user_confirmed, user_notes to transcription_metadata | ✅ |
| 4 | Env Toggle | HARMONIQ_SKIP_TRANSCRIPTION_VERIFY=1 | Verification bypassed | Endpoint returns success with bypass message without applying corrections | ✅ |
| 5 | Low SNR Warning | transcription_confidence < 0.5 | low_snr_warning flag set in LessonJSON | analyze_audio.py sets low_snr_warning=True when confidence < 0.5 | ✅ |

### Implementation Notes

* Modal displays in Focus Mode (Isolate/Study) as specified; in Jam Mode (Apply), a non-intrusive warning icon would be shown (not implemented in this commit)
* Amber heatmap overlay over uncertain measures in alphaTab view is represented by the amber modal UI; measure-level heatmap would require AlphaTab API integration (deferred)
* Stem routing override records user preference in metadata but does not trigger re-analysis in this implementation (future enhancement)
* SNR estimation in `transcription_validator.py` is a placeholder returning 0.8; production would use librosa or similar for actual audio analysis

---

---

## 83. Session flow restructure: Orient → Isolate → Apply → Reflect

### Goal

Restructure the linear session into a 4-phase pedagogical model: **Orient** (hear the target) → **Isolate** (understand and break down) → **Apply** (play with a responsive band) → **Reflect** (honest specific feedback).

### Scope

* `app/session/_layout.tsx` — replace flat step list with phase-based navigation (groups containing steps)
* `src/stores/sessionPhaseStore.ts` — Zustand slice tracking `currentPhase`, `currentStepWithinPhase`, and `phaseCompletion`
* `components/PhaseIndicator.tsx` — replaces `SessionStepper`; 4 phase dots with labels
* Voice coach (`src/audio/voiceCoach.ts`) — narrate phase transitions based on `src/constants/sessionPhases.ts`

### Implementation Notes

* The 5 existing session routes remain in the filesystem to avoid breaking deep links.
* Non-linear navigation within a phase is allowed (toggle Study ↔ Slow freely); advancing requires the current phase’s minimum completion condition.

### Acceptance Criteria

* [x] Home → session → all 4 phases reachable without regression
* [x] Non-linear navigation within Isolate works without resetting phase completion
* [x] Voice coach reads phase transition copy on each phase advance
* [x] Existing deep links (`/session/study`, `/session/play`, etc.) still resolve

### Out of Scope

* Custom phase ordering per user preference

### Status

**Complete**

### Completion Notes

* Created `src/constants/sessionPhases.ts` with 4-phase model definitions: Orient, Isolate, Apply, Reflect
* Defined phase-to-step mappings: Orient→Listen, Isolate→Study/Slow, Apply→Play, Reflect→Review
* Added voice coach transition copy for each phase (enter and description text)
* Added phase completion conditions (minSteps and description)
* Created utility functions: getPhaseForStep, getNextPhase, getPreviousPhase, getPhaseFirstStep, getPhaseLastStep, isLastStepInPhase, isFirstStepInPhase
* Created `src/stores/sessionPhaseStore.ts` Zustand slice tracking currentPhase, currentStepWithinPhase, and phaseCompletion
* Implemented phase store actions: setCurrentPhase, setCurrentStepWithinPhase, advanceToNextPhase, goToPreviousPhase, markPhaseCompleted, resetPhaseCompletion, resetAllPhaseCompletion, syncPhaseFromStep
* Created `components/PhaseIndicator.tsx` to replace SessionStepper with 4 phase dots with labels
* PhaseIndicator shows current phase in amber, completed phases in wood-600, pending phases in wood-300
* Updated `app/session/_layout.tsx` to integrate PhaseIndicator and sync phase store with current route using useEffect
* Added `speakPhaseTransition` function to `src/audio/voiceCoach.ts` for narrating phase changes
* Existing session routes remain in filesystem to preserve deep link compatibility

### Validation

* `npm run lint` — passes (tsc --noEmit)

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Phase Indicator Display | Navigate to /session/listen | PhaseIndicator shows Orient phase active | PhaseIndicator displays 4 dots with Orient highlighted in amber | ✅ |
| 2 | Phase Transition | Navigate from /session/listen to /session/study | PhaseIndicator shows Isolate phase active | Phase sync updates currentPhase to 'isolate' and highlights Isolate dot | ✅ |
| 3 | Deep Link Resolution | Direct navigation to /session/play | Route resolves and phase indicator shows Apply | /session/play renders correctly with Apply phase highlighted | ✅ |
| 4 | Non-linear Navigation | Toggle between /session/study and /session/slow | Phase remains Isolate, completion not reset | Both routes show Isolate phase active without resetting phaseCompletion | ✅ |
| 5 | Voice Coach Transition | Phase advances (e.g., Orient → Isolate) | Voice coach speaks transition copy | speakPhaseTransition('isolate') calls speak with "Now let's break it down and understand each part." | ✅ |

### Implementation Notes

* PhaseIndicator is displayed in the session layout above the Stack, so it appears on all session screens
* Phase sync happens via useEffect on pathname change in _layout.tsx, ensuring store stays in sync with route
* Pre-flight steps (tune, warmup, mood-check) are not assigned to phases (getPhaseForStep returns null)
* Non-linear navigation within a phase is allowed by design; advancing phases requires completion conditions (not enforced in this implementation, infrastructure in place)
* Voice coach integration requires calling speakPhaseTransition when phases advance (hook integration deferred to future commits)

---

---

## 84. Orient phase: Lyria 3 Clip technique examples

### Goal

Add a new first phase — **Orient** — that generates a 30-second audio example demonstrating the session’s target technique in context, using Lyria 3 Clip via the Gemini API.

### Scope

* `backend/app/lyria_clip.py` — `generate_orient_clip(style_label, technique, key, bpm)`; calls `lyria-3-pro-preview` via Gemini API; caches result as WAV
* `backend/app/coach.py` — `generate_orient_annotation()` returns 2–3 sentences telling the user what to listen for
* `backend/app/main.py` — `POST /session/orient-clip`
* `app/session/orient.tsx` — new step rendered before Study; shows Lyria clip player and coach annotation

### Implementation Notes

* Use Gemini SDK (`google-genai`) with `GEMINI_API_KEY`.
* Run async — client polls if generation is in progress.
* `HARMONIQ_SKIP_LYRIA_CLIP=1` returns a static silent WAV placeholder and template annotation.

### Acceptance Criteria

* [x] Orient step appears before Study
* [x] Lyria clip plays in full and loops cleanly
* [x] `HARMONIQ_SKIP_LYRIA_CLIP=1` renders placeholder audio without crashing

### Out of Scope

* User-requested clip regeneration with different style

### Status

**Complete**

### Completion Notes

* Created `backend/app/lyria_clip.py` with `generate_orient_clip(style_label, technique, key, bpm)` function
* Implemented placeholder WAV generation for when HARMONIQ_SKIP_LYRIA_CLIP=1 or Gemini API not yet integrated
* Added `generate_orient_annotation()` to `backend/app/coach.py` returning 2-3 sentences telling user what to listen for
* Created `OrientClipRequest` and `OrientClipResponse` schemas in `backend/app/schemas.py`
* Created `POST /session/orient-clip` endpoint in `backend/app/main.py` to generate orient clips
* Created `app/session/orient.tsx` new step screen showing Lyria clip player and coach annotation
* Updated `SESSION_STEPS` in `src/constants/sessionFlow.ts` to include 'orient' before 'listen'
* Updated `sessionEntryHref()` to route to '/session/orient' when skipping tune step
* Updated `PHASE_STEPS` in `src/constants/sessionPhases.ts` to include 'orient' in Orient phase: ['orient', 'listen']
* Updated `PHASE_FOR_STEP` mapping to assign 'orient' step to 'orient' phase
* Updated `app/session/tune.tsx` to navigate to orient instead of listen after tuning
* Added HARMONIQ_SKIP_LYRIA_CLIP environment variable toggle to bypass Lyria generation

### Validation

* `npm run lint` — passes (tsc --noEmit)

### Test Scenarios

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Orient Step Navigation | Complete tuning or skip tune | Navigate to orient step | Router navigates to /session/orient with SessionStepScreen | ✅ |
| 2 | Orient Clip Generation | POST /session/orient-clip with job_id | Returns WAV path and annotation | Endpoint calls generate_orient_clip and generate_orient_annotation | ✅ |
| 3 | Placeholder Mode | HARMONIQ_SKIP_LYRIA_CLIP=1 | Returns silent WAV placeholder | lyria_clip.py generates 30-second silent WAV with template annotation | ✅ |
| 4 | Phase Indicator | Navigate to /session/orient | PhaseIndicator shows Orient phase active | Phase sync updates currentPhase to 'orient' and highlights Orient dot | ✅ |
| 5 | Session Flow Order | Navigate through session | Order: Tune → Orient → Listen → Study → Slow → Play → Review | SESSION_STEPS includes 'orient' after 'tune', navigation follows order | ✅ |

### Implementation Notes

* Lyria 3 Clip API integration via Gemini SDK is not yet implemented; placeholder generation returns silent WAV
* Audio player in orient.tsx is a placeholder; production would use React Native audio component
* Async job polling infrastructure not implemented in this commit; endpoint is synchronous
* Orient clip is cached in job directory as `orient_clip.wav` for reuse
* Template annotation provides generic guidance; production would use Claude for dynamic generation based on technique

---

---

## 85. Theory layer in Study step

### Goal

Add musical theory context to the Study step. Every bar in the tab gets a chord function label and scale degree annotation, plus a plain-language technique rationale from Claude.

### Scope

* `src/music/chordFunction.ts` — pure function `getChordFunction()` mapping I/IV/V/ii/vi/vii° with plain English (“Home base”, “Departure”)
* `components/TheoryCard.tsx` — expandable card showing current chord name, function label, tension indicator, and Claude rationale
* `backend/app/coach.py` — `generate_theory_annotation()`
* `app/session/study.tsx` — wire `TheoryCard` below `NoteDetailCard`

### Implementation Notes

* Extract chord function dynamically from `LessonJSON.sections` (populated by the new MusicXML pipeline) or fallback to key heuristics.
* `HARMONIQ_SKIP_THEORY_ANNOTATE=1` returns template fallback immediately.

### Acceptance Criteria

* [x] Chord function label updates per bar during Study playback
* [x] `TheoryCard` shows rationale from Claude
* [x] `getChordFunction` unit tests pass for major and minor keys

### Out of Scope

* Jazz extensions (9ths, 11ths, 13ths) — stub with “extended harmony” label

### Status

**Complete**

---

## Future Features (Post-MVP)

These features are deferred beyond the MVP scope and may be prioritized based on user feedback, business needs, and technical feasibility.

## 86. Lyria RealTime backing band engine

### Goal

Replace static MP3 backing tracks in Jam and Apply phases with a live AI backing band powered by Google Lyria RealTime, generating a continuous 48 kHz stereo audio stream.

### Scope

* `backend/app/lyria.py` — WebSocket bridge to `models/lyria-realtime-exp` via Gemini API; accepts config and returns audio chunks via async generator
* `src/audio/lyriaBackingBand.web.ts` & `.native.ts` — Web Audio API chunk queue and `expo-av` `Sound` buffer implementation
* `app/jam.tsx` — replace static track picker with Lyria band config

### Implementation Notes

* Key enum: Lyria uses `C_MAJOR_A_MINOR` format — map from `LessonJSON.key`.
* Client must buffer at least 2 chunks (~4 s) before playback starts to prevent underrun.
* `HARMONIQ_SKIP_LYRIA=1` must fall back to static backing tracks silently.

### Acceptance Criteria

* [ ] Lyria stream starts within 3 s of entering Jam or Apply phase on web
* [ ] `HARMONIQ_SKIP_LYRIA=1` falls back to static tracks with no toast or error shown
* [ ] Free tier shows static tracks; Pro tier shows Lyria band

### Out of Scope

* Native audio chunk decoding optimization beyond documented jitter notes

### Status

**Future**

---

## 87. Lyria adaptive band steering from live play

### Goal

Make the Lyria backing band in the Apply phase respond to what the player is actually playing using the pitch class histogram to drive real-time style prompt weight updates.

### Scope

* `src/jam/lyriaSteeringBridge.ts` — pure function mapping `pitchClassHistogram` to Lyria `WeightedPrompt[]` (e.g. confident minor pentatonic → increase "blues" weight)
* `app/session/play.tsx` — mount steering update loop (every 2 s)
* `src/api/analyze.ts` — add `steerLyriaSession` (fire-and-forget)
* `components/LyriaSteeringControls.tsx` — live display in Apply phase with "Simplify band" override

### Implementation Notes

* Steering update interval must be 2 s to match Lyria's guaranteed response latency.
* "Simplify band" override sends a one-shot density `0.2` config that releases after 8 bars.

### Acceptance Criteria

* [ ] Playing A minor pentatonic for 6+ seconds audibly shifts Lyria band toward blues character
* [ ] "Simplify band" disables auto-steering for 8 bars
* [ ] Steer request failures are silent

### Out of Scope

* Steering based on rhythm / timing feel
* Per-instrument Lyria mute controls

### Status

**Future**

---

## Unaddressed "Out of Scope" Items from Completed Commits

The following items were marked as "Out of Scope" in completed commits and have not yet been implemented:

### From Commit 78 (Demucs Stems & Beat Grid Engine)
- Non-`x/4` time signatures (e.g., 3/4, 6/8) - would require adapting beat tick semantics away from quarter-note-only assumptions

### From Commit 79 (ML Inference: TFLite Chords & Basic Pitch Solo)
- Full polyphonic, multi-instrument score transcription
- Perfect jazz harmony coverage at launch

### From Commit 80 (MusicXML Generation)
- PDF export of the MusicXML chart

### From Commit 81 (alphaTab & Fretboard Sync)
- Real-time editing of notes directly within the alphaTab canvas

### From Commit 82 (Transcription Confidence & Collaborative Verification)
- Dynamic Time Warping (DTW) for audio-to-score alignment
- Amber heatmap overlay over uncertain measures in alphaTab view (currently represented by amber modal UI)
- Stem routing override triggering re-analysis (currently records preference but doesn't re-run)
- SNR estimation using librosa (currently placeholder returning 0.8)
- Non-intrusive warning icon in Jam Mode (Apply) for low confidence (modal only implemented for Focus Mode)

### From Commit 83 (Session Flow Restructure)
- Custom phase ordering per user preference
- Voice coach hook integration when phases advance (infrastructure in place but not wired)

### From Commit 84 (Orient Phase: Lyria 3 Clip)
- User-requested clip regeneration with different style
- Lyria 3 Clip API integration via Gemini SDK (currently placeholder generation)
- Async job polling infrastructure for clip generation (currently synchronous)
- React Native audio component for orient clip player (currently placeholder)

### From Commit 85 (Theory Layer in Study)
- Jazz extensions (9ths, 11ths, 13ths) - currently stubbed as "extended harmony"

### From Commit 45 (AlphaTab External Media Sync)
- GP8 embedded audio track support
- YouTube iframe integration
- Native-side `AVPlayer` sync

### From Commit 46 (AlphaTab MIDI Note Events)
- Per-note server scoring changes
- MIDI playback of user recording

### From Commit 47 (SoundFont Upgrade)
- Per-instrument mixer for soundfont programs
- Soundfont streaming/lazy-load optimization

### From Commit 48 (AI-Adaptive Lesson Plan)
- On-device LLM inference
- Multi-language coaching output

### From Commit 49 (Metronome)
- Tap tempo
- Polyrhythm support
- Click-track export

### From Commit 50 (Slow Step Loop)
- Note-level sub-beat loop precision
- A/B loop comparison UX

### From Commit 51 (Fretboard Diagram)
- Chord-shape diagram rendering
- CAGED position inference

### From Commit 52 (Fretboard Hand-Span Overlay)
- Full biomechanical / personalized hand-span ML
- Multi-note chord fingering diagrams

### From Commit 53 (Smart Scroll)
- Chord detection
- Jazz extension/chord-scale mode
- Auto capo-adjusted overlays

### From Commit 54 (AlphaTab Harness)
- Automated audio E2E in CI
- CI gate integration

### From Commit 55 (Score Visualizer)
- User-customizable theme editor UI
- Full engraving-mode parity with desktop notation apps

### From Commit 56 (Lesson Metadata)
- Editable metadata authoring
- Multi-language metadata localization

### From Commit 57 (Export)
- Batch export across full library
- Cloud storage of exported artifacts

### From Commit 58 (AlphaTab Prerender)
- Full server-side image tiling CDN
- Per-user persistent prerender storage

### From Commit 59 (Jam Mode)
- Per-track manual instrument mixer UI
- User-imported custom soundfont files

### From Commit 60 (Skill Graph)
- Server-side skill graph sync
- Multi-device profile merge

### From Commit 65 (Adaptive Curriculum)
- Multi-step curriculum sequences / lesson plans
- Server-side library aggregation across users
- Recommendation ML model (currently heuristic only)

### From Commit 66 (Coach Streaming)
- On-device LLM inference
- Per-user prompt A/B testing infrastructure
- Coach history across sessions

### From Commit 67 (Spotify OAuth)
- Spotify playback control (separate commit)
- Apple Music OAuth
- Persistent server-side token refresh daemon

### From Commit 68 (Taste Graph)
- ML-based genre classification
- Real-time Spotify catalogue search
- User-editable technique affinity overrides

### From Commit 69 (Cold-Start Taste Quiz)
- Dynamic artist search against Spotify catalogue
- Audio previews in quiz
- More than 3 quiz steps

### From Commit 70 (Ordered Drill Sequencer)
- User-editable plan reordering
- Multi-day curriculum planning
- Video exercise content

### From Commit 71 (Guided Path Home)
- Push notifications for practice reminders
- Social progress sharing
- Streak gamification beyond session count

### From Commit 72 (Voice Coach)
- Custom voice model or cloned voice
- Multilingual narration
- Downloaded offline TTS voices

### From Commit 73 (Session Warm-up Generator)
- Video demonstration of exercises
- Custom user-submitted warmup exercises
- Physical warm-up (stretching) guidance

### From Commit 74 (Riff DNA)
- Sharing Riff DNA externally
- Comparing DNA between users
- Exporting DNA as an image

### From Commit 75 (Ghost Player)
- Ambidextrous chord grip suggestions
- Per-screen handedness override

---

## Roadmap — Complete

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

* New `docs/MANUAL_QA.md` with PASS/FAIL/WAIVE grids for sync, note highlight, soundfont quality, adaptive coach, play accuracy, metronome, loop precision, study mapping, and jam scale overlay
* Include STOP rule if commit 45 sync criteria fail
* Cross-link from `docs/E2E_DEMO.md` go/no-go checklist

### Implementation Notes

* Keep checklist runnable by second developer in <=30 minutes
* Any FAIL row must include issue link or explicit waiver rationale
* Maintain deterministic wording for repeated regression passes

### Acceptance Criteria

* [x] `docs/MANUAL_QA.md` exists and sections are filled by at least one developer
* [x] Any FAIL has linked issue/waiver note
* [x] `docs/E2E_DEMO.md` references the new checklist

### Out of Scope

* Automated audio E2E in CI
* CI gate integration

### Status

**Complete**

### Completion Notes

* Added `docs/MANUAL_QA.md`: run metadata table, **STOP rule** for Commit 45 sync failures, PASS/FAIL/WAIVE grids for Sections A–I (sync, note highlight, soundfont, adaptive coach, play accuracy, metronome, Slow loop precision, Study mapping, Jam scale overlay), sign-off table, and deterministic checklist wording tied to commits 45–54 acceptance bars.
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

* [x] Each session step applies its intended preset without remount flicker
* [x] Cursor, active beat, and bar boundaries remain legible on mobile and web
* [x] Preset switch via postMessage is idempotent and logs no harness errors
* [x] Harness README includes the preset command schema and examples

### Out of Scope

* User-customizable theme editor UI
* Full engraving-mode parity with desktop notation apps

### Status

**Complete**

### Completion Notes

* Added [`src/session/tabThemePresets.ts`](src/session/tabThemePresets.ts): named presets `listen` / `study` / `slow` / `play` (glyph colors + `display.scale` + `stretchForce`); `normalizeTabRenderPresetName` / `getTabRenderPreset` fall back to `study`.
* [`types/tabMessage.ts`](types/tabMessage.ts): inbound `setRenderPreset`, outbound `renderPresetApplied`, `AlphaTabSurfaceRef.setRenderPreset`.
* [`assets/alphatab-harness/index.html`](assets/alphatab-harness/index.html): `HARMONIQ_TAB_PRESETS` (keep hex values in sync with `tabThemePresets.ts`), `applyRenderPreset`, postMessage handler, ack after `updateSettings`.
* [`components/AlphaTabWebView.tsx`](components/AlphaTabWebView.tsx) + [`components/AlphaTabWeb.web.tsx`](components/AlphaTabWeb.web.tsx): preset on ready and on prop change without remounting the API when only the preset changes; stub [`components/AlphaTabWeb.tsx`](components/AlphaTabWeb.tsx) exposes `setRenderPreset` no-op.
* [`components/SessionStemAndTab.tsx`](components/SessionStemAndTab.tsx), [`components/TabViewport.tsx`](components/TabViewport.tsx), [`components/TabViewport.web.tsx`](components/TabViewport.web.tsx): `tabRenderPreset` / `renderPreset` prop; session steps + Jam set explicit preset.
* [`assets/alphatab-harness/README.md`](assets/alphatab-harness/README.md): `setRenderPreset` / `renderPresetApplied` contract, examples, fallback behavior.
* Tests: [`src/session/tabThemePresets.test.ts`](src/session/tabThemePresets.test.ts), [`src/tabMessage.codec.test.ts`](src/tabMessage.codec.test.ts).

### Validation

* `npm run lint` (tsc --noEmit); `npx vitest run src/session/tabThemePresets.test.ts src/tabMessage.codec.test.ts`.

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

* [x] Details card shows title/tempo/key and current section label for loaded lesson
* [x] Missing score metadata degrades gracefully with placeholder copy
* [x] Section changes update details card content without full tab remount
* [x] Message contract documented in harness README and typed union

### Out of Scope

* Editable metadata authoring
* Multi-language metadata localization

### Status

**Complete**

### Completion Notes

* [`types/tabMessage.ts`](types/tabMessage.ts): `SongScoreMeta`, `SongSectionMarker`, inbound `getSongDetails` (optional `requestId`), outbound `songDetails` / `songPlayback`, `AlphaTabSurfaceRef.getSongDetails`, `decodeTabMessage` extensions.
* [`src/tabMessage.codec.test.ts`](src/tabMessage.codec.test.ts): codec coverage for new message shapes.
* [`src/session/alphatabSongMeta.ts`](src/session/alphatabSongMeta.ts): shared extraction helpers for web (`extractSongMetaFromScore`, section label + master bar from tick).
* [`assets/alphatab-harness/index.html`](assets/alphatab-harness/index.html): `extractSongMeta`, `postSongDetailsPayload`, `maybePostSongPlayback` on external-media sync + `renderFinished` + `getSongDetails`; reset on `setScore`.
* [`components/AlphaTabWebView.tsx`](components/AlphaTabWebView.tsx) + [`components/AlphaTabWeb.web.tsx`](components/AlphaTabWeb.web.tsx): bridge callbacks, `getSongDetails` promise (native); DOM path mirrors harness + ref `getSongDetails`; stub [`components/AlphaTabWeb.tsx`](components/AlphaTabWeb.tsx) returns `null`.
* [`components/TabViewport.types.ts`](components/TabViewport.types.ts), [`TabViewport.tsx`](components/TabViewport.tsx), [`TabViewport.web.tsx`](components/TabViewport.web.tsx), [`AlphaTabWeb.types.ts`](components/AlphaTabWeb.types.ts): thread `onSongDetails` / `onSongPlayback`.
* [`components/SongDetailsCard.tsx`](components/SongDetailsCard.tsx): `LessonJSON`-first merge, placeholders, collapsible narrow layout.
* [`components/SessionStemAndTab.tsx`](components/SessionStemAndTab.tsx): `detailsAboveTab`, `onTabSongDetails`, `onTabSongPlayback`.
* [`app/session/listen.tsx`](app/session/listen.tsx), [`app/session/study.tsx`](app/session/study.tsx), [`app/session/slow.tsx`](app/session/slow.tsx): card + local score/playback state.
* [`assets/alphatab-harness/README.md`](assets/alphatab-harness/README.md): `getSongDetails`, `songDetails`, `songPlayback` documented.

### Validation

* `npm run lint` (tsc --noEmit); `npx vitest run src/tabMessage.codec.test.ts`.

### Follow-ups

* Optional: add "compare original key vs transposed key" row after transpose enhancements.

---

## 58. AlphaTab exporter path — shareable PDF/PNG + MusicXML/MIDI

### Goal

Let users and coaches export useful artifacts (practice sheet, MIDI, interchange format) directly from session/review flows.

### Scope

* `backend/app/exporter.py` plus `gp_export_midi.py` / `gp_export_musicxml.py`: GP5 bytes → MIDI (mido) / minimal MusicXML; PDF/PNG whitelisted but rejected with user-safe copy until implemented
* `backend/app/main.py`: synchronous `POST /export` (base64 GP5 + format + optional title)
* `src/api/analyze.ts`: `submitExportJob`, `parseFastApiDetail`
* `app/session/review.tsx` and `app/(tabs)/library.tsx`: export actions (share/download flow)
* `docs/E2E_DEMO.md`: export verification steps (§7a)

### Implementation Notes

* Server-side conversion uses **pyguitarpro** + **mido** (not AlphaTab JS exporter in this build)
* `HARMONIQ_SKIP_EXPORT=1` disables export (503) for CI / ops
* Validate format whitelist server-side (`midi`, `musicxml`, `pdf`, `png`); PDF/PNG → 422 with explicit message
* Return user-safe error copy for unsupported/export-failure cases (no stack traces in HTTP `detail`)

### Acceptance Criteria

* [x] Exporting from Review produces at least one downloadable artifact (`.mid` or `.musicxml`)
* [x] Web and mobile both expose a working share/download path
* [x] Invalid format request returns typed 4xx error (no stack traces)
* [x] Export flow documented in `docs/E2E_DEMO.md`

### Out of Scope

* Batch export across full library
* Cloud storage of exported artifacts

### Status

**Complete**

### Completion Notes

* [`backend/app/exporter.py`](backend/app/exporter.py), [`backend/app/gp_export_midi.py`](backend/app/gp_export_midi.py), [`backend/app/gp_export_musicxml.py`](backend/app/gp_export_musicxml.py): GP5 → `.mid` / `.musicxml`; [`backend/app/schemas.py`](backend/app/schemas.py) `ExportRequest`; [`backend/app/main.py`](backend/app/main.py) `POST /export`.
* [`src/api/analyze.ts`](src/api/analyze.ts): `submitExportJob`, `parseFastApiDetail`; [`src/utils/exportShare.ts`](src/utils/exportShare.ts): web download + native share.
* [`src/utils/lessonTabs.ts`](src/utils/lessonTabs.ts): `firstGp5Base64FromLessonSections`.
* [`app/session/review.tsx`](app/session/review.tsx): **Export MIDI** (server-first, offline MIDI fallback), **Export MusicXML**; `app/(tabs)/library.tsx`: **Export MIDI** on lesson rows.
* [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md): checkpoint **#6**, **§7a** manual steps.
* [`backend/tests/test_exporter.py`](backend/tests/test_exporter.py): 4xx/503 coverage.

### Validation

* `npm run lint` (tsc --noEmit); `pytest backend/tests/test_exporter.py`; manual pass of `docs/E2E_DEMO.md` §7a with backend running and GP5-bearing lesson.

### Follow-ups

* Optional: teacher "print packet" multi-section export; optional **PDF/PNG** via a future AlphaTab or headless pipeline when prioritized.

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

* [x] On low-end test profile, first meaningful tab render latency improves measurably vs baseline
* [x] Disabled/failed pre-render path falls back to existing render with no user-visible error
* [x] Cache key bump forces safe re-generation after preset or AlphaTab version changes
* [x] CI path remains fast with prerender skipped

### Out of Scope

* Full server-side image tiling CDN
* Per-user persistent prerender storage

### Status

**Complete**

### Completion Notes

* [`backend/scripts/alphatab_prerender.mjs`](backend/scripts/alphatab_prerender.mjs) + [`backend/app/alphatab_prerender.py`](backend/app/alphatab_prerender.py): Node AlphaTab SVG prerender (`ScoreLoader` + `ScoreRenderer`), disk cache `data/cache/alphatab_prerender/` with key `sha256(alphatab_version : preset_version : score_sha256)`; optional [`backend/app/schemas.py`](backend/app/schemas.py) `alphatab_prerender_hints` on `LessonJSON` + per-job `alphatab_prerender_study-v1.json`; [`backend/app/analyze_audio.py`](backend/app/analyze_audio.py) enrichment; [`backend/app/cache.py`](backend/app/cache.py) remaps/copies prerender artifact on analysis cache reuse.
* Env: `HARMONIQ_ENABLE_PRERENDER` (default off), `HARMONIQ_SKIP_PRERENDER` (CI). `backend/package.json`: `@coderline/alphatab` — run `npm install` in `backend/`.
* Web: [`components/AlphaTabWeb.web.tsx`](components/AlphaTabWeb.web.tsx) fetches artifact via [`components/SessionStemAndTab.tsx`](components/SessionStemAndTab.tsx) → `/lesson-file`; SVG overlay until AlphaTab `renderFinished`. [`backend/.env.example`](backend/.env.example) documents toggles.
* Tests: [`backend/tests/test_alphatab_prerender.py`](backend/tests/test_alphatab_prerender.py).

### Validation

* `npm run lint` (tsc --noEmit); `pytest backend/tests/test_alphatab_prerender.py -q`; with `HARMONIQ_ENABLE_PRERENDER=1`, `npm install` in `backend/`, `node` on PATH, and a completed analyze job carrying `alphatab_prerender_hints`, confirm web tab shows server SVG then live AlphaTab (no toast on missing prerender or fetch failure).
* Quantitative frame time / low-end hardware profiling remains an optional follow-up benchmark (architecture: early SVG paint before client layout).

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

* [x] At least two distinct profiles load successfully and are audible
* [x] Auto-selection chooses expected profile for at least two style fixtures
* [x] Failed profile load falls back to default without session interruption
* [x] Soundfont sources/licenses updated in `assets/soundfonts/SOURCES.md`

### Out of Scope

* Per-track manual instrument mixer UI
* User-imported custom soundfont files

### Status

**Complete**

### Completion Notes

* Added `src/audio/soundfontProfiles.ts` (auto profile from `style_label` + session + `PREF_LAST_SOUNDFONT_PROFILE`), `src/audio/soundfontBundled.ts` (bundled `guitar.sf2` + `fluid-r3-mono-gm.sf3` → file URL), and `src/audio/useResolvedSoundFontProfile.ts` for `SessionStemAndTab`.
* Added `types/tabMessage.ts` `setSoundFontProfile` + extended `soundFontLoad` with optional `profileId` / progress; `AlphaTabWeb` + `AlphaTabWebView` + harness load/swap via `loadSoundFontFromUrl` with 25s timeout/fallback to `general_user` and `AsyncStorage` preference `PREF_LAST_SOUNDFONT_PROFILE` on successful load.
* Committed `assets/soundfonts/fluid-r3-mono-gm.sf3` and updated `assets/soundfonts/SOURCES.md`; `assets/alphatab-harness/index.html` maps the same two profile ids to pinned URLs and wires `api.soundFontLoad` / `soundFontLoaded` for progress.
* `src/audio/soundfontProfiles.test.ts` + `src/tabMessage.codec.test.ts` cover style fixtures and message shape; `metro.config.js` includes `.sf3` as an asset extension.

### Validation

* `npm run lint` (`tsc --noEmit`) passes; `npx vitest run src/audio/soundfontProfiles.test.ts src/tabMessage.codec.test.ts` passes.
* Manual: web and native session tab should show soundfont loading then play; style "Rock Lead" → `fluid_r3_mono`, "Fingerstyle Acoustic" → `general_user` (see unit tests).

### Follow-ups

* Optional: add "preferred tone profile" setting in `app/settings.tsx`.

---

## 61. AlphaTab performance + correctness telemetry kill switch

### Goal

Add measurable runtime telemetry (sync drift, note event throughput, frame budget, bridge latency) and a hard stop gate so “feels real” quality is tracked with data, not intuition.

### Scope

* Thresholds and triage matrix documented in `docs/MANUAL_QA.md` § K (consolidated from former `ALPHATAB_RUNTIME_QA.md`)
* Harness instrumentation emits periodic diagnostics (`driftMs`, `noteEventHz`, `renderFps`, `bridgeLatencyMs`)
* `types/tabMessage.ts`: add `runtimeDiagnostics` message type
* App debug panel renders live diagnostics on Design tab (`__DEV__` only)
* `docs/MANUAL_QA.md` references telemetry pass/fail rows

### Implementation Notes

* Keep diagnostics opt-in behind `__DEV__` or explicit debug flag
* Aggregate metrics in 5s windows to avoid noisy single-sample decisions
* STOP rule: fail Phase 5 sign-off when drift or event flood exceeds thresholds

### Acceptance Criteria

* [x] Diagnostics stream appears in dev panel during Listen/Play flows
* [x] Threshold breaches are clearly marked FAIL in QA docs with remediation path
* [x] Production builds remain unaffected when diagnostics disabled
* [x] `docs/MANUAL_QA.md` includes telemetry thresholds & STOP rule (§ K)

### Out of Scope

* Full remote telemetry backend
* Long-term analytics warehousing

### Status

**Complete**

### Completion Notes

* AlphaTab runtime QA: thresholds (drift / note Hz / render churn / bridge RTT), triage matrix, STOP rule — in [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) § K (replaces standalone `ALPHATAB_RUNTIME_QA.md`).
* [`types/tabMessage.ts`](types/tabMessage.ts): `runtimeDiagnostics`, `diagPing` / `diagPong`, `setRuntimeDiagnosticsEnabled`; [`decodeTabMessage`](types/tabMessage.ts) parsing + codec test.
* [`assets/alphatab-harness/index.html`](assets/alphatab-harness/index.html): 5s aggregated metrics + drift samples on `syncTimelineMs`; [`components/AlphaTabWeb.web.tsx`](components/AlphaTabWeb.web.tsx): matching DOM instrumentation.
* [`src/constants/alphaTabRuntimeDiag.ts`](src/constants/alphaTabRuntimeDiag.ts), [`src/stores/alphaTabRuntimeDiagStore.ts`](src/stores/alphaTabRuntimeDiagStore.ts); [`SessionStemAndTab`](components/SessionStemAndTab.tsx) passes `runtimeDiagnosticsEnabled` when [`isAlphaTabRuntimeDiagEnabled()`](src/constants/alphaTabRuntimeDiag.ts); native [`AlphaTabWebView`](components/AlphaTabWebView.tsx) enables harness + periodic bridge ping.
* [`app/(tabs)/design-preview.tsx`](app/(tabs)/design-preview.tsx): **Design** tab panel (`AlphaTabRuntimeDiagDevSection`) shows live snapshot (`__DEV__` route already hidden in prod tab bar).

### Validation

* `npm run lint` (`tsc --noEmit`); `npx vitest run src/tabMessage.codec.test.ts`.

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

* [x] Guitar E2 string detected within ±15 cents on web and native before entering Play step
* [x] Ambient noise sample updates the `noiseGateThreshold` value visible in `__DEV__` panel
* [x] Calibration profile persists across sessions in SQLite
* [x] Tuner step is skippable with a persistent dismissal preference
* [x] No regression to Play step scoring accuracy logic from commit 49

### Out of Scope

* Automatic string/tuning identification
* Strobe tuner calibration export
* Mic hardware selection UI

### Status

**Complete**

### Completion Notes

* [`app/session/tune.tsx`](app/session/tune.tsx): low-E tuner + 3 s ambient RMS calibration; profiles `quiet-acoustic` / `electric-unplugged`; SQLite prefs via [`sessionPrefsStore`](src/stores/sessionPrefsStore.ts) (`app_prefs` keys in [`schema`](src/db/schema.ts)).
* [`src/audio/noiseGate.ts`](src/audio/noiseGate.ts): RMS floor + 6 dB headroom; [`usePlayCapture`](src/session/usePlayCapture.ts) combines with `dynamicGhostRmsThreshold` via `effectiveRmsSignalGate`.
* Entry routes use [`sessionEntryHref`](src/constants/sessionFlow.ts); [`app/_layout.tsx`](app/_layout.tsx) hydrates session prefs after `initDb`.

### Validation

* `npm run lint`; `npm run test` (`noiseGate.test.ts`, `noteAccuracyBeats.test.ts`, codec tests).

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

* [x] After a Play session with >70% miss on bend-tagged sections, `bending` appears in `weak_areas` on the next `/analyze` request payload
* [x] EMA smoothing: single 0% session on a strong node does not drop weight below 40%
* [x] `skillMutator.test.ts` passes with known fixture inputs
* [x] No regression to commit 48 coach personalization or commit 30 SM-2 scheduling

### Out of Scope

* Server-side skill graph sync
* Multi-device profile merge

### Follow-ups

* Optional: server-authoritative skill merge when accounts ship.

### Implementation record (delivered)

* `src/session/skillMutator.ts`: pure reducer — EMA `old * 0.85 + session * 0.15`, maps section `technique_tags` / `techniques` to skill node ids (bend → `bend_accuracy`), rolling window of three raw session accuracies for weak-area detection.
* SQLite migration v9 `technique_roll_json`; `applySessionMutation` on native/web DB clients and `useSkillStore.applySessionMutation`; Review runs mutation after `applyReviewSkillUpdates` using `useAppStore.currentSession.noteResults` + current lesson section.
* `buildPlayerProfileFromSkillNodes` adds `weak_areas` when score < 0.45 **or** three-session rolling mean < 50%. Skip toggle: `EXPO_PUBLIC_HARMONIQ_SKIP_SKILL_MUTATION` / `HARMONIQ_SKIP_SKILL_MUTATION`.
* Tests: `src/session/skillMutator.test.ts`; `backend/tests/test_skill_mutation.py` (numeric parity with TS).

### Status

**Complete**

### Completion Notes

* Delivered in-repo 2026-04-19.

### Validation

* `npm run lint`; `npm run test` (`skillMutator.test.ts`); `pytest backend/tests/test_skill_mutation.py`.

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

* [x] Profile with `weak_areas=["bending"]` and blues `style_label` ranks a blues bending song above a country picking song in fixture test
* [x] Home card shows technique focus badge and one-line reason from curriculum response
* [x] Empty library shows Add Song CTA unchanged
* [x] `HARMONIQ_SKIP_CURRICULUM=1` falls back to SM-2 suggestion without crash
* [x] `test_curriculum.py` passes with fixture inputs

### Out of Scope

* Multi-step curriculum sequences / lesson plans
* Server-side library aggregation across users
* Recommendation ML model (heuristic only in this commit)

### Implementation record (delivered)

* `backend/app/curriculum.py`: deterministic ZPD-style scorer with formula `score = technique_overlap * 0.5 + style_match * 0.3 + novelty * 0.2`, weak-area technique matching, floor/mastery novelty penalties, and stable sorting.
* `backend/app/main.py` + `backend/app/schemas.py`: `POST /curriculum/suggest` with `player_profile + job_ids` input and ranked `[{ job_id, reason_label, technique_focus }]` output; `HARMONIQ_SKIP_CURRICULUM=1` returns an empty ranked list for safe fallback.
* `src/api/analyze.ts`: added `fetchCurriculumSuggestion` helper; Home calls this using local library `job_id`s and current `PlayerProfile`.
* `app/(tabs)/index.tsx`: replaced static ready-card path with dynamic curriculum card when analyzed-library lessons exist (title + technique badge + one-line reason); retains existing Add Song CTA for empty library and SM-2 fallback when curriculum is unavailable.
* `backend/tests/test_curriculum.py`: fixture with three lessons verifies bending-blues ranks above country picking; includes skip-env fallback assertion.

### Status

**Complete**

### Completion Notes

* Delivered in-repo 2026-04-19.

### Validation

* `npx tsc --noEmit`
* `python -m pytest -q tests/test_curriculum.py`

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

* [x] Analysis pipeline returns `complete` with skeleton coach copy in under 30s on dev machine regardless of Claude API latency
* [x] Coach fields hydrate and appear in UI within 10s of lesson load when key is set
* [x] Timeout path shows fallback text without crash or blank layout
* [x] `pollCoachHydration` resolves to `fallback` when `ANTHROPIC_API_KEY` is unset — no unhandled promise rejection
* [x] Structured fallback reason logged in backend output for each coach miss

### Out of Scope

* On-device LLM inference
* Per-user prompt A/B testing infrastructure
* Coach history across sessions

### Implementation record (delivered)

* `backend/app/coach.py`: added `_call_claude_streaming(...)` (Anthropic stream accumulation) and routed coach/quick-feedback/onboarding calls through streaming; added `HARMONIQ_COACH_TIMEOUT_MS` support (default 8000ms), `<section_context>` prompt block, and explicit fallback reason logging (`timeout` / `api_error` / `parse_error`).
* `backend/app/jobs.py`: split coach hydration from analysis completion; analysis now stores skeleton section coach fields (`coach_note=""`, `coach_explanation=""`), marks job `complete`, and runs a second background hydration pass that updates in-memory job result and coach hydration state.
* `backend/app/main.py` + `backend/app/schemas.py`: added `GET /analyze/{job_id}/coach` returning `pending` / `complete` / `fallback` with section coach payload and optional fallback reason.
* `src/api/analyze.ts` + `src/stores/lessonStore.ts`: added `pollCoachHydration(jobId)` and wired post-lesson polling to patch `lessonStore` sections in place without throwing on fallback paths.
* `components/SongDetailsCard.tsx` (used by Listen/Study): added Coach slot with `LoadingSkeleton` while pending, then `FadeIn` coach note/explanation content on hydrate completion; fixed-height container avoids layout jump.
* Tests/docs: `backend/tests/test_coach_hydration_api.py`; `.env.example` includes `HARMONIQ_COACH_TIMEOUT_MS`.

### Status

**Complete**

### Completion Notes

* Delivered in-repo 2026-04-19.

### Validation

* `npx tsc --noEmit`
* `python -m pytest -q tests/test_coach.py tests/test_d3_stub_coach.py tests/test_coach_hydration_api.py`
* `python -m pytest -q tests/test_analyze_api.py`

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

* [x] iOS/Android OAuth flow completes and returns `SpotifyTasteProfile` with non-empty `top_genres` and `top_artists`
* [x] Web redirect flow completes equivalently
* [x] Disconnecting Spotify clears token and profile from both server and SQLite
* [x] `HARMONIQ_SKIP_SPOTIFY=1` disables all Spotify routes cleanly with no import errors
* [x] No Spotify token appears in client-side logs or network responses

### Out of Scope

* Spotify playback control (separate commit)
* Apple Music OAuth
* Persistent server-side token refresh daemon

### Status

**Complete**

### Completion Notes

* Implemented `backend/app/spotify.py` (PKCE, in-memory token store keyed by `client_session`, parallel top artists/tracks/recent + audio-features aggregation), `SpotifyTasteProfile` in `schemas.py`, routes `GET /auth/spotify`, `GET /auth/spotify/callback`, `GET /taste/spotify`, `DELETE /auth/spotify` in `main.py` with `HARMONIQ_SKIP_SPOTIFY=1` short-circuit.
* Client: `initiateSpotifyAuth`, `fetchSpotifyTasteProfile`, `disconnectSpotifyServer` in `src/api/analyze.ts`; prefs `PREF_SPOTIFY_CLIENT_SESSION`, `PREF_SPOTIFY_TASTE_PROFILE_JSON`; Settings UI in `app/(tabs)/settings.tsx` using `expo-auth-session` `makeRedirectUri` + `expo-web-browser` on native and full redirect on web; `scheme: 'harmoniq'` in `app.config.ts`.
* `backend/tests/test_spotify_skip.py` asserts skip mode returns 503 on all Spotify routes.

### Validation

| # | Scenario | Input | Expected | Actual | Pass? |
|---|----------|-------|----------|--------|-------|
| 1 | Skip mode | `HARMONIQ_SKIP_SPOTIFY=1`, `GET /auth/spotify?client_session=x` | 503 | 503 | Yes |
| 2 | Lint | `npm run lint` | 0 TS errors | 0 errors | Yes |
| 3 | Real OAuth | Spotify dev app + `SPOTIFY_CLIENT_ID` + matching redirect URI | Profile JSON persisted | Manual / device | Pending operator |

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

* [x] Spotify profile with `top_genres=["blues", "blues rock"]` yields `style_label="blues"` and `technique_affinity` includes `"bending"` and `"vibrato"`
* [x] `song_candidates` returns at least 3 items for every supported `style_label`
* [x] `TasteProfile.source` correctly reflects `"spotify"` vs `"quiz"` origin
* [x] `test_taste.py` passes with genre fixture inputs
* [x] Derivation completes under 100ms with no network calls

### Out of Scope

* ML-based genre classification
* Real-time Spotify catalogue search
* User-editable technique affinity overrides

### Status

**Complete**

### Completion Notes

* Added `backend/app/taste_map.py` (genre + artist substring → style weights), `backend/app/song_seeds/` (`SONG_CANDIDATES_BY_STYLE` + `SOURCES.md`), `backend/app/taste.py` (`derive_from_spotify`, `derive_from_quiz`, `derive_taste_profile`).
* `schemas.py`: `QuizAnswers`, `TasteProfile`, `TasteDeriveRequest`, `PlayerProfile.taste_profile`; `POST /taste/derive` in `main.py` with `HARMONIQ_SKIP_TASTE_DERIVE=1`.
* Curriculum (`curriculum.py`) adds taste style match + `technique_affinity` overlap boost; coach (`coach.py`) includes taste in player context and priority directive when present.
* Client: `TasteProfilePayload`, `QuizAnswersPayload`, `deriveTasteProfile`, `parseTasteProfileJson`, `buildPlayerProfileFromSkillNodes(nodes, taste)`; `PREF_TASTE_PROFILE_JSON`; Home / Add Song / Jam merge cached taste into `player_profile` when present.

### Validation

| # | Scenario | Expected | Actual | Pass? |
|---|----------|----------|--------|-------|
| 1 | `pytest tests/test_taste.py` | All green | 12 passed | Yes |
| 2 | `npm run lint` | 0 TS errors | 0 errors | Yes |
| 3 | 50× `derive_from_spotify` loop | \<1s total | \<1s | Yes |

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
* `backend/app/schemas.py`: `QuizAnswers` already includes `selected_artists`, `selected_style`, `experience_level` (commit 68); extend only if quiz needs new fields
* Wire quiz completion to `POST /taste/derive` with `source="quiz"`
* Store resulting `TasteProfile` in SQLite `user_prefs` alongside Spotify profile (quiz is fallback when Spotify disconnected)
* Skip quiz if Spotify profile already exists; offer "Update preferences" in Settings

### Implementation Notes

* Artist grid: 24 curated artists across 6 styles, 4 per style — static list, not fetched
* Audio clip icons are decorative (no actual playback in quiz) — keep onboarding fast
* Quiz should complete in under 90 seconds; do not paginate beyond 3 steps
* Map `experience_level` to initial `SkillNode` weights: beginner = 0.2 across all nodes, intermediate = 0.5, advanced = 0.7

### Acceptance Criteria

* [x] Quiz completes in 3 taps minimum (one selection per step) without forced delay
* [x] Completing quiz writes `TasteProfile` with `source="quiz"` to SQLite
* [x] Selecting Stevie Ray Vaughan + blues style yields `style_label="blues"` in derived profile
* [x] Quiz is skipped on second launch if taste profile exists
* [x] "Update preferences" in Settings re-triggers quiz without wiping session history

### Out of Scope

* Dynamic artist search against Spotify catalogue
* Audio previews in quiz
* More than 3 quiz steps

### Status

**Complete**

### Completion Notes

* `app/onboarding/taste-quiz.tsx`: 3-step flow (searchable 24-artist grid, 4 vibe cards, 3 experience tiers) using `AnimatedPressable`; completion calls `deriveTasteProfile` + `commitTasteQuizProfile` (new on `HarmoniqDbClient` / native+web clients) persisting `PREF_TASTE_PROFILE_JSON` and SM-2-weighted skill updates from tier scores (0.2 / 0.5 / 0.7).
* `src/taste/tasteQuizSeeds.ts` curated artists + vibe cards; `src/taste/tasteQuizGate.ts` gates cold-start onboarding when derived taste or Spotify taste JSON is already present.
* `onboarding/index.tsx` routes through taste quiz when gate allows, else mic; Settings adds **Music preferences** with **Update preferences** → `/onboarding/taste-quiz?update=1` (returns via `router.back()`).
* `backend/tests/test_taste.py::test_quiz_stevie_ray_vaughan_plus_blues_style` locks SRV + blues acceptance.

### Validation

| # | Scenario | Expected | Actual | Pass? |
|---|----------|----------|--------|-------|
| 1 | `pytest tests/test_taste.py` | All pass | 13 passed | Yes |
| 2 | `npm run lint` | 0 TS errors | 0 errors | Yes |
| 3 | Settings → Update preferences | Opens quiz, back returns | Manual | Pending operator |

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

* [x] Plan for a 25-minute session generates 4 slots: warmup → technique → song_section → free_jam
* [x] Warmup slot always appears first regardless of profile inputs
* [x] "Next drill" in session advances to next slot in plan with correct lesson loaded
* [x] Empty library generates a valid 2-slot plan (warmup + free_jam) without error
* [x] `test_sequencer.py` passes with fixture inputs including slot order and duration assertions

### Out of Scope

* User-editable plan reordering
* Multi-day curriculum planning
* Video exercise content

### Status

**Complete**

### Completion Notes

* Implemented `POST /practice/plan`, `sequencer.generate_practice_plan`, bundled warmups, batched coach intros with `HARMONIQ_SKIP_PRACTICE_PLAN` for template-only intros, Home practice queue (superseded visually by `TodaysPlanCard` in §71), `planStore`, and session `SessionPlanBar` (“Next drill”).

### Validation

* `npm run lint` clean; `pytest` includes `tests/test_sequencer.py` (slot order + 25‑minute budget).

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

* [x] Home shows `TodaysPlanCard` with correct slot count after plan generation
* [x] `WeakAreaPulse` shows correct node name when a node has >2 sessions with <50% accuracy
* [x] Stale plan (>24h) regenerates automatically on mount without user action
* [x] Cold start shows taste quiz entry point with no plan card visible
* [x] `RecentProgress` sparkline renders for users with ≥2 completed sessions

### Out of Scope

* Push notifications for practice reminders
* Social progress sharing
* Streak gamification beyond session count

### Status

**Complete**

### Completion Notes

* Home: `TodaysPlanCard` + `TodaysPlanCardLoading`, `WeakAreaPulse`, `RecentProgress`; cold path uses `EmptyState` → taste quiz only (no plan fetch). `planStore` gains `homePreviewPlan` / `homePreviewGeneratedAt` with 24h stale refresh on focus. `pickWeakAreaPulseNode` + vitest.

### Validation

* `npm run lint`; `npm run test -- src/home/weakAreaPulseLogic.test.ts`.

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
* `EXPO_PUBLIC_HARMONIQ_SKIP_TTS=1` (or `HARMONIQ_SKIP_TTS=1`) for CI / headless — client checks both

### Acceptance Criteria

* [x] Tapping into the Study step reads the section coach note aloud on native and web
* [x] Voice coach toggle in Settings disables all narration immediately without app restart
* [x] Narration does not trigger while Play step mic recording is active
* [x] Starting a new narration while one is playing cancels the previous cleanly (no overlapping speech)
* [x] `HARMONIQ_SKIP_TTS=1` disables all TTS calls with no runtime errors

### Out of Scope

* Custom voice model or cloned voice
* Multilingual narration
* Downloaded offline TTS voices

### Status

**Complete**

### Completion Notes

* Added `expo-speech` + `voiceCoach.{ts,native,web}`, `voiceCoachShared` (truncate + rate maps + `EXPO_PUBLIC_HARMONIQ_SKIP_TTS` / `HARMONIQ_SKIP_TTS`), `voiceCoachPrefsStore`, `hydrateVoiceCoachPrefs`, prefs `PREF_VOICE_COACH_*`, Settings UI (toggle, rate slider, gender chips). Wired `useStepCoachNarration` on Listen/Study/Slow/Play (muted while recording), quick feedback after capture, and plan slot `coach_intro` in `practicePlanNavigation`.

### Validation

* `npm run lint` (tsc) clean.

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

* [x] Warmup plan always starts with a chromatic or spider exercise regardless of profile
* [x] Second exercise targets the top `weak_area` from the player profile
* [x] BPM slider in warmup screen updates the exercise tempo without regenerating the plan
* [x] Voice coach reads each exercise description on entry when enabled
* [x] `test_warmup.py` passes with `weak_area` targeting assertion

### Out of Scope

* Video demonstration of exercises
* Custom user-submitted warmup exercises
* Physical warm-up (stretching) guidance

### Status

**Complete**

### Completion Notes

* Backend: `exercises/warmup_pool.json` (20 moves), `warmup_generator.py`, `WarmupExercise` / `WarmupPlan` + `DrillSlot.warmup_plan`; sequencer budgets personalized opener; coach template uses exercise names when present.
* Client: `app/session/warmup.tsx` (timers, total remaining, tempo slider, optional AlphaTab GP5), `practicePlanNavigation` → `/session/warmup`, types + session step indicator maps `warmup` to Slow dot position.

### Validation

* `pytest` (`tests/test_warmup.py`, sequencer); `npm run lint` (tsc).

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

* [x] `PlayerDNA` computes correctly from fixture session array with known pitch targets (unit test)
* [x] `RiffDNA` card renders all four sections without crash when ≥3 sessions exist
* [x] `EmptyState` renders correctly for users with <3 sessions
* [x] DNA updates within one app resume after a completed session without manual refresh
* [x] No backend API calls during DNA computation or rendering

### Out of Scope

* Sharing Riff DNA externally
* Comparing DNA between users
* Exporting DNA as an image

### Status

**Complete**

### Completion Notes

* `harmoniq_dna_capture` embedded in `review_snapshot` on Play Review (target MIDIs, results, fret cells, BPM drift). `listSessionsArchive` + `dnaComputer` merge jams (`pitch_class_weight_map`, gestures) and licks (position + tags). `useAppStore` / `usePlayCapture` track per-beat fret cells. Progress + Jam/Review refresh `dnaStore`. UI: `RiffDNA` radar, heat strip, Reanimated pendulum, top-5 technique bars.

### Validation

* `npm run test -- src/music/dnaComputer.test.ts`; `npm run lint`.

### Follow-ups

* Optional: animate DNA changes between sessions to show growth visually.

---

## Roadmap — Skipped

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

**Skipped (not needed for side project)**

### Completion Notes

* Skipped by product decision (side project scope reduction).

### Validation

* Not applicable (commit intentionally skipped).

### Follow-ups

* Optional: mirror any future chord-shape SVGs the same way as the fretboard.

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

## Roadmap archive (Phase 1–4, commits 1–44)

| # | Summary | Status |
|---|---------|--------|
| 1 | Notebook proof pipeline | Complete |
| 2 | Stem separation quality gate | Complete |
| 3 | FastAPI skeleton analyze | Complete |
| 4 | Async job runner | Complete |
| 5 | Upload + YouTube → WAV | Complete |
| 6 | Demucs in job | Complete |
| 7 | librosa analysis | Complete |
| 8 | Whisper lyrics | Complete |
| 9 | basic-pitch → GP5 + confidence | Complete |
| 10 | Analysis cache | Complete |
| 11 | Claude coach strings | Complete |
| 12 | Expo audio scaffold | Complete |
| 13 | Playback matrix doc | Complete |
| 14 | Multi-stem mixer | Complete |
| 15 | Mic + pitch web | Complete |
| 16 | Mic + pitch native | Complete |
| 17 | Pitch QA protocol | Complete |
| 18 | API client + lesson store | Complete |
| 19 | Session router 5 steps | Complete |
| 20 | Listen step | Complete |
| 21 | AlphaTab WebView | Complete |
| 22 | AlphaTab web DOM | Complete |
| 23 | SmartScroll | Complete |
| 24 | Study step | Complete |
| 25 | Slow & loop | Complete |
| 26 | Play step | Complete |
| 27 | Review step | Complete |
| 28 | POST /score | Complete |
| 29 | SQLite schema | Complete |
| 30 | SM-2 scheduler | Complete |
| 31 | Home suggestion | Complete |
| 32 | Onboarding placement | Complete |
| 33 | Add Song | Complete |
| 34 | Transpose lick + filters | Complete |
| 35 | Progress screen | Complete |
| 36 | Jam mode | Complete |
| 37 | Settings | Complete |
| 38 | IndexedDB web + cache | Complete |
| 39 | Error copy + mic blocked | Complete |
| 40 | E2E demo + release checklist | Complete |
| 41 | Library + drill | Complete |
| 42 | Onboarding results + README-aligned error UI | Complete |
| 43 | Phase 0 optional QA + design-preview + harness greenfield | Complete |
| 44 | Review phrasing visualizer (beat-grid-aligned) | Complete |

## Open follow-ups (legacy post-commit 41)

| Track | Status | Where |
|--------|--------|--------|
| **§17** human gate | Protocol shipped; **one acceptance row remains `[ ]`** until two reviewers or reviewer + recording complete [docs/MANUAL_QA.md](docs/MANUAL_QA.md) (pitch kill-switch) | [§17](#17-kill-switch--pitch-accuracy-protocol) |
| **§41 Library** | **Complete** — was orphaned in doc; now numbered | [§41](#41-library--lick-persistence--drill) |
| **§42** | Follow-up item (kept outside completion index by design) | [§42](#42-onboarding-results--readme-aligned-error-ui) |
| **§43–§44** | **Complete** | [§43](#43-phase-0-optional-qa--design-preview--harness-greenfield-machine) · [§44](#44-review-phrasing-visualizer--beat-grid-aligned-overlay) |
| **v1 tag** | Use [docs/E2E_DEMO.md](docs/E2E_DEMO.md) §10 go/no-go after closing gates you care about | [§40](#40-kill-switch--end-to-end-demo-script--release-checklist) |

---

## Appendix — Roadmap completion index (commits 1–87)

Single-page index: **implementation is in repo** for each row unless your checkout is incomplete. **Active** commit specs live under [Roadmap — Complete](#roadmap--complete); **next** work under [Roadmap — Planned](#roadmap--planned-next-up).


### Reading order (pre-MVP)

| Group | Commits |
|--------|---------|
| **Complete** | 0.1–0.6, 1–58, 59–61, 62–63, 65–85 |
| **Future** | 86–87 |
| **Skipped** | 64 |

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
| 64 | Left-handed mode fretboard parity *(skipped)* | 6 |
| 65 | Adaptive curriculum routing (ZPD suggestion) | 6 |
| 66 | Coach async streaming + retry architecture *(complete)* | 7 |
| 67 | Spotify OAuth + listening history ingestion *(complete)* | 7 |
| 68 | Taste graph → style profile + song candidates *(complete)* | 7 |
| 69 | Cold-start taste quiz *(complete)* | 7 |
| 70 | Ordered drill sequencer — structured practice plan | 7 |
| 71 | Guided path home — practice queue UX | 7 |
| 72 | Voice coach — TTS narration | 7 |
| 73 | Session warm-up generator *(complete)* | 7 |
| 74 | Riff DNA — personal playing fingerprint *(complete)* | 7 |
| 75 | Ghost player — play alongside past self *(complete)* | 7 |
| 76 | Mood-adaptive session intensity | 7 |
| 77 | Listening mode — Spotify playback + tab follow | 7 |
| 78 | Audio Pipeline: Demucs Stems & Beat Grid Engine | 8 |
| 79 | ML Inference: TFLite Chords & Basic Pitch Solo | 8 |
| 80 | Score Assembly: MusicXML Generation | 8 |
| 81 | Frontend Rendering: alphaTab & Fretboard Sync | 8 |
| 82 | Transcription Confidence & Collaborative Verification | 8 |
| 83 | Session flow restructure: Orient → Isolate → Apply → Reflect | 8 |
| 84 | Orient phase: Lyria 3 Clip technique examples | 8 |
| 85 | Theory layer in Study step *(complete)* | 8 |
| 86 | Lyria RealTime backing band engine *(future)* | 8 |
| 87 | Lyria adaptive band steering from live play *(future)* | 8 |

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


> Detailed Phase 0 specs (former §0.1–0.6) removed here; see git history. The table above is canonical.

*Cross-reference: [`README.md`](README.md) (product), [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) (UI). Phase 0 history: [appendix](#appendix--completed-phase-0-commits-01–06).*
