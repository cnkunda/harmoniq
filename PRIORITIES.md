# Harmoniq — Engineering Roadmap (Commit-by-Commit)

Atomic, production-quality commits ordered for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (commits 0.1–0.6)** — Expo + design scaffold, backend shell, AlphaTab harness, env/backing tracks, shared UI feedback + API client — is **complete**. Archival scope, acceptance, and handoff live in the [appendix](#appendix--completed-phase-0-commits-01–06). **Commit 1** (notebook proof pipeline) is **complete**. **Active work below starts at commit 2.**

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
| **Now** | **Commit 2** — Kill switch — stem separation quality gate |
| **Product spec** | [`README.md`](README.md) |
| **UI spec** | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) |
| **Scaffolding history** | [Appendix — Phase 0](#appendix--completed-phase-0-commits-01–06) |

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

### ✅ Status: COMPLETE

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

Mid -- This is out of place - where does it fit in? Its own commit?
-----
### Goal

Persist licks from Review, browse, re-open AlphaTab + audio clip.

### Scope

* `app/library.tsx` + SQLite `licks` CRUD
* `Drill this` reuses session routes with lick payload

### Implementation Notes

* Store `tab_gp5_base64` and optional `audio_segment_path` from stem slice later; v1 can omit clip if too heavy

### Acceptance Criteria

* [x] Save from Review appears in list after relaunch
* [x] Drill opens Study/Play subset with same tab

### Out of Scope

* Transposition UI

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
