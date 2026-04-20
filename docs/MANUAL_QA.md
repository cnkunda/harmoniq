# Manual QA — Harmoniq

Single reference for release and pipeline gates: stem quality, pitch kill-switch, error-copy verification, Phase 5 session realism, telemetry, Slow & loop residual risks, and lightweight regression smokes.

**Cold start:** [E2E_DEMO.md](./E2E_DEMO.md).

**Regression discipline:** Same platform build, test song, and tempo when comparing runs.

---

## Purpose and scope

| When | What to run |
|------|----------------|
| Demucs/model/ingest changed | Stem separation gate (below) |
| Shipping Play/score that depends on pitch | Pitch kill-switch (below) |
| UX/copy or `mapErrorToUi` touched | Error states matrix (spot-check affected rows) |
| AlphaTab harness, Listen/Play sync, Jam backing, metronome | Feel Real § (waived items, telemetry, STOP rules) |
| Slow UI or loop metadata logic changed | Slow & loop residual risks + optional cross-step smoke |
| `expo-av` / bundled assets / Jam backing changed | Design tab backing-track smoke + [expo-av & Design dev playback](#expo-av--design-dev-playback) |

Depth on scoring diagnostics: [SCORING.md](./SCORING.md).

---

## Stem separation (`htdemucs_6s`)

Formal go/no-go for **guitar** stem usability before tabs, transcription, or coach features depend on separation.

### Stop here if fail

If **either** the automated smoke script **or** the listening checks fail, **stop**. Do not treat stems as validated. Fix input (different mix/source), re-run Demucs on a capable machine, or adjust expectations — **do not** tune Demucs hyperparameters here (out of scope).

Re-run after changing the separation model, upgrading Demucs, or materially changing ingest (sample rate, mono fold-down, etc.).

### Automated smoke (`backend/scripts/smoke_stems.py`)

From backend (venv + Demucs per `backend/README.md`):

```bash
cd backend
python scripts/smoke_stems.py path/to/mix1.wav path/to/mix2.wav
```

Optional PNGs (`pip install matplotlib`):

```bash
python scripts/smoke_stems.py path/to/mix1.wav path/to/mix2.wav --spectrograms
```

**Input formats:** Each argument is one **full mix** (WAV, MP3, or anything **ffmpeg** + librosa can decode — not only `.wav`).

**Recommended bundled mixes (POSIX paths from `backend/`):**

Better **guitar-forward** bundled picks (still synth beds — see [assets/backing-tracks/SOURCES.md](../assets/backing-tracks/SOURCES.md)): **avoid** `am-drone-ambient.mp3` for this gate — it is **pad-only**, no guitar band stem. Prefer e.g. blues shuffle + two-chord vamp:

```bash
cd backend
source .venv-wsl/bin/activate   # or your backend venv — see backend/README.md
python scripts/smoke_stems.py \
  ../assets/backing-tracks/am-blues-70bpm.mp3 \
  ../assets/backing-tracks/em-two-chord-90bpm.mp3
```

Optional PNGs for the same inputs:

```bash
python scripts/smoke_stems.py \
  ../assets/backing-tracks/am-blues-70bpm.mp3 \
  ../assets/backing-tracks/em-two-chord-90bpm.mp3 \
  --spectrograms
```

**WSL / Linux shells:** Use **forward slashes** and `../` (e.g. `../assets/...`). Windows-style `..\` and `\` are **not** path separators in bash and will produce `not a file` / mangled paths.

**Work dir:** Normalized WAV + Demucs output default to `backend/data/smoke_stems/<slug>/` (under `backend/data/*`, gitignored via [backend/.gitignore](../backend/.gitignore)). Override with `python scripts/smoke_stems.py ... --work-dir /path/to/work`.

Artifacts: `artifacts/stem_smoke/<slug>/` when using `--spectrograms` (under repository root `artifacts/`; gitignored). Non-zero exit if any track fails.

**Automation vs ears:** Heuristics can false-positive (e.g. dense vocal+guitar pop). If the script fails but the guitar stem is clearly usable, **trust listening**, note the override in the verification log, and treat obvious garbage (silent stem, vocal-heavy stem) as **FAIL**.

**Bundled `assets/backing-tracks/*.mp3` caveat:** Those clips are **synth practice beds**, not multi-track stems. The smoke script gates **Demucs “guitar” stem** RMS and energy ratios — **pad-only** tracks (`am-drone-ambient`) and very sparse mixes will often **FAIL** RMS/ratio by design. Prefer **blues / two-chord / ballad** files above for a fairer attempt, or use **your own full-band WAV/MP3** with obvious guitar.

**SNR proxy gate:** The script’s `snr_proxy_db` compares guitar energy to a **coarse** `mix − guitar` residual. Demucs stems are **not** a phase-aligned linear sum of the mix, so this dB figure is often **negative or below 2 dB** even when the guitar stem sounds fine — especially on **dense synth beds** where many instruments overlap. If you see **FAIL only on SNR proxy** but RMS/ratio/corr look OK, treat as **heuristic noise**, confirm by ear, and log an override per below rather than chasing Demucs tuning.

Confirm `ffmpeg` and venv `demucs` run from the same shell if commands fail mysteriously.

**Manual-only:** If Demucs cannot run locally, validate stems produced elsewhere with the same listening criteria and log outcomes.

#### YouTube source (download first)

[`smoke_stems.py`](../backend/scripts/smoke_stems.py) only accepts **local audio paths** — not a YouTube URL. The app’s **Analyze** flow can ingest YouTube server-side; this manual gate expects you to **download audio** yourself, then point the script at the file.

Use **`yt-dlp`** with the same intent as [`yt_dlp_download_audio_command`](../backend/app/pipeline_proof.py) (single video, WAV extract). Strip playlist/radio query params — use a **canonical watch URL** so `--no-playlist` fetches one video:

- **Example:** `https://www.youtube.com/watch?v=3MlOIWBaSX8`
- **Avoid:** `...&list=...&start_radio=1` (unnecessary playlist context)

Respect **copyright and licensing** for any track you download; use for **local QA only** on your machine.

From **`backend/`** (WSL/bash, forward slashes). Downloads go under `backend/data/smoke_youtube_inbox/` (ignored via `backend/data/*`; same pattern as other scratch data):

```bash
mkdir -p data/smoke_youtube_inbox
cd data/smoke_youtube_inbox
yt-dlp --no-playlist --extract-audio --audio-format wav --audio-quality 0 \
  -o "yt_%(id)s.%(ext)s" \
  "https://www.youtube.com/watch?v=3MlOIWBaSX8"
cd ../..
```

Then run smoke on the produced `yt_<video_id>.wav` plus a second mix (bundled MP3 or another file):

```bash
source .venv-wsl/bin/activate   # or your backend venv
python scripts/smoke_stems.py \
  "data/smoke_youtube_inbox/yt_3MlOIWBaSX8.wav" \
  ../assets/backing-tracks/am-blues-70bpm.mp3
```

If the filename differs, use `ls data/smoke_youtube_inbox/yt_*.wav`. Requires **`yt-dlp`** and **`ffmpeg`** on `PATH` (see [backend/README.md](../backend/README.md)).

#### When `smoke_stems` fails (triage)

| Symptom | Likely cause |
|---------|----------------|
| `not a file` / garbled path | Bash/WSL: used `\` or `..\` — switch to `../assets/...` |
| `ModuleNotFoundError` / import errors | Venv not activated or backend not installed per [backend/README.md](backend/README.md) |
| `ffmpeg` errors | `ffmpeg` missing on PATH in WSL (`ffmpeg -version`) |
| Slow run / OOM | First Demucs download or CPU inference — expected; retry with smaller clip |
| Automated FAIL, stem sounds OK by ear | Heuristic false-positive — override in verification log (Automation vs ears, above) |
| Automated FAIL, `guitar.wav` near-silent | Wrong **asset** for guitar gate (ambient, no guitar), bad separation, or threshold mismatch — confirm by listening under `backend/data/smoke_stems/<slug>/` |
| Automated FAIL on **pad-only** drone bed | Expected — track has no guitar band ([SOURCES.md](../assets/backing-tracks/SOURCES.md)); use blues/two-chord mixes or an external guitar-forward mix |
| **FAIL only** on SNR proxy (other gates pass) | Common on bundled synth beds — `mix − guitar` is not a true acoustic residual (see § Bundled caveat above); override by ear if `guitar.wav` is usable |

### Listening checks - CURRENT

Per song: **guitar stem alone**, then mix minus guitar if helpful.

1. **Guitar audible** — not silence/noise-only; the transcribable part is recognizable.
2. **Minimal bleed** — vocals/drums/cymbals not dominant in the guitar stem; occasional leakage OK if guitar stays the focus.

### “No guitar” / bad isolation — FAIL if

- Guitar stem near-silent while the mix obviously has guitar.
- Guitar stem mostly vocals/drums.
- Automated script reports failure (see script output).

Align product copy: users should see a clear “couldn’t isolate a clean guitar track” outcome, not silently bad tabs.

### Verification log (minimum two songs)

Stress-test with **one easy** mix and **one dense** (busy band / vocal-heavy).

| # | Mix type | Song / source | Date | Operator | `smoke_stems` | Audible guitar | Low bleed | Notes |
|---|----------|----------------|------|----------|----------------|----------------|-----------|-------|
| 1 | Easy | `assets/backing-tracks/am-drone-ambient.mp3` | 2026-04-19 | WSL `backend/.venv-wsl` | FAIL | — | — | **Pad-only bed** ([SOURCES.md](../assets/backing-tracks/SOURCES.md)) — not a valid “guitar smoke” positive. Re-run smoke with `am-blues-70bpm.mp3` / `em-two-chord-90bpm.mp3` (see § Automated smoke). |
| 2 | Dense | `assets/backing-tracks/g-major-fingerpicking-80bpm.mp3` | 2026-04-19 | WSL `backend/.venv-wsl` | FAIL | — | — | Synth fingerpicking; automated RMS/ratio/SNR failed — confirm `guitar.wav` under `backend/data/smoke_stems/g-major-fingerpicking-80bpm/` by ear before changing thresholds. |

Rows **1** and **2** must reflect **real** runs (replace dates/operator when you re-verify). Use **—** for listening columns until auditioned.

**Follow-up (recommended bundled pair):** On 2026-04-19, `am-blues-70bpm.mp3` + `em-two-chord-90bpm.mp3` completed Demucs successfully; automated checks **passed** RMS and guitar/mix ratio, but **failed SNR proxy** (below the 2 dB threshold) on both — consistent with synthetic beds and the non-linear `mix − guitar` heuristic (see § Bundled caveat). Use **listening** + verification log override when the isolated `guitar.wav` is musically usable.

---

## Pitch accuracy (kill switch)

Manual QA for live pitch (`usePitchStream` → **Mic + pitch (dev)** on Design) **before** Play/scoring depend on pitch.

### Detector context

| Topic | Detail |
|--------|--------|
| **UI** | `app/(tabs)/design-preview.tsx` — **Mic + pitch (dev)** |
| **Web** | `src/pitch/pitchStream.web.ts` — AudioWorklet, autocorrelation, ~**70–1000 Hz** |
| **Native** | `src/pitch/pitchStream.native.ts` — `react-native-audio-api` |
| **Readout** | Note name, Hz (one decimal), cents vs 12-TET |
| **Logs** | Native: `[PitchStream.native]`; web: worklet lifecycle in devtools |

**STOP if:** mic cannot start (permission, HTTPS on web, or non–dev-build on native), or Hz/note stays blank during a loud steady tone.

### How to run

1. `npm install` (repo root). `npm start` → **Design** → **Mic + pitch (dev)** → **Start mic**.
2. Complete **A–C** on each gated platform (both web and native before cross-platform pitch scoring ships).

**Environment:** Web: **HTTPS** or `localhost`. Native: **Expo dev/production build** (not Expo Go).

### A — Test tones

Second device/tab, clean sine, moderate volume, quiet room, hold **≥3 s** per tone.

| Step | Target | Expected note | Pass criteria |
|------|--------|----------------|---------------|
| A1 | **440.0 Hz** | A4 | \|cents\| ≤ 25; Hz within ±3 Hz of 440 |
| A2 | **220.0 Hz** | A3 | \|cents\| ≤ 25; Hz within ±3 Hz of 220 |
| A3 | **82.41 Hz** (low E) | E2 | \|cents\| ≤ 30; Hz within ±4 Hz (harder in noise — use quiet room or close-mic) |

**Known gap:** Low fundamental (A3) can fail in noisy rooms; fix environment or waive with issue + owner.

### B — Guitar open strings (standard tuning)

Pluck one string at a time; ring **≥2 s**. Reference Hz: E2 82.41, A2 110.00, D3 146.83, G3 196.00, B3 246.94, E4 329.63.

**Pass:** Per string, Hz within **±5%** or \|cents\| **≤ 35** for a majority of stable decay frames.

### C — Bend hold

Half or whole-step bend on G3 or B3; hold **≥2 s**. Pass: readout stays near bent pitch (no persistent wild jumps). Fail: wrong harmonic lock or oscillation between unrelated notes.

### Platform matrix (sign-off)

Repeat A–C per platform.

| Platform | Build / browser / device | A | B | C | Overall |
|----------|---------------------------|---|---|---|---------|
| Web | | | | | |
| iOS | | | | | |
| Android | | | | | |

### Failure triage

| Step / platform | Failure summary | Triage | Link / ticket |
|-----------------|-----------------|--------|----------------|
| | | **Fix** / **Waive** (issue URL) / **Change approach** | |

- **Fix:** code/config change; re-run failed rows.
- **Waive:** tracked issue, risk, owner — **not** for A1+A2 both failing on a primary platform.
- **Change approach:** new detector/preprocessing — document and re-plan validation.

### Sign-off

**Requirement:** at least **two developers** **or** **one developer + screen recording** (Design tab, Start mic, **A1** + one guitar string).

| Role | Name | Date | Notes |
|------|------|------|-------|
| Tester / reviewer 1 | | | |
| Tester / reviewer 2 | | | |

`Recording:` ________________________________________________

**Gate:** Do **not** ship Play/score features that depend on this pitch path until sign-off is complete and failures are triaged.

---

## Error states (README copy)

Aligned with [README.md](../README.md) error table and `README_ERROR_COPY` in `src/errors/mapErrorToUi.ts`.

### Mic permission denied

- **Force:** Native Play → “Start play capture” → deny mic.
- **Expect:** README mic banner; **Open Settings** opens system settings; no raw stack trace.

### YouTube URL invalid

- **Force:** Add Song → invalid/non-YouTube URL → Analyze; or backend 400 with `youtube_url`.
- **Expect:** README message; **Retry** returns to editable URL.

### Analysis job failed

- **Force:** Backend down / bad `EXPO_PUBLIC_API_BASE_URL` / server job failure.
- **Expect:** README analysis-failed message; **Retry**.

### Analysis job timeout (>5 min)

- **Force:** Stuck analyzing >5 min or dev timer simulating timeout.
- **Expect:** README timeout/info; **Dismiss**.

### No internet during analysis

- **Force:** Start analyze → kill network (or offline in devtools on web).
- **Expect:** README offline message; **Dismiss**.

### Audio too short (<30 sec)

- **Force:** Backend 400 / short clip rejected.
- **Expect:** README short-audio message; **Dismiss**.

### Score endpoint failure

- **Force:** Review → “Run score” with backend down or `/score` error.
- **Expect:** README score message; **Do it again** re-runs scoring.
- **Also:** Onboarding “Stop & score” with backend failure — same copy; **Do it again** resubmits without re-record.

### No guitar stem detected

- **Force:** Error body matching stem heuristic in `mapAnalyzeFlowError`.
- **Expect:** README no-guitar-stem message; **Try again**.

### Low transcription confidence

- **Force:** Lesson with `transcription_confidence` below `TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX` (`src/db/schema.ts`).
- **Expect:** Study warning + README message; **Continue** or dismiss until section/job changes.

### Browser mic blocked

- **Force:** Web Jam → block mic → Start Jamming.
- **Expect:** README browser-mic message (no raw `getUserMessage` toast); **Retry** calls `startPitch`.

---

## Phase 5 session realism (Feel Real)

### STOP — external media sync

If **Listen** sync against the guitar stem is **FAIL** without issue + waiver, **stop**: Phase 5 is not shippable until fixed or waived.

**Bar:** Guitar stem audio is the playback clock (`IExternalMediaHandler` / `PlayerMode.EnabledExternalMedia`). No timer-driven SmartScroll fighting external-media cursor updates.

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

## Regression smokes

Quick paths that do not duplicate full PASS grids:

1. **Cross-step:** From a lesson with stems — **Listen** (seek + optional metronome) → **Slow** (confirm ~**0.65×**, loop plays, **Clear loop** once) → **Study** (tap score note → fretboard highlights).
2. **Jam backing seam:** With `GEMINI_API_KEY`, exercise **`POST /jam/backing`** WAV path; compare loop seam vs **two** bundled loops and note MP3 fallback behavior if API absent.
3. **Review / score:** After a Play pass, open **Review** — diagnostics/reliability UI matches [SCORING.md](./SCORING.md); force score failure → **Do it again** recovers ([Error states](#score-endpoint-failure)).
4. **Telemetry (native):** On iOS/Android, confirm **bridge RTT** and **driftMs** over one reference song vs [Thresholds](#thresholds).
5. **Onboarding:** If changing pitch/score aggregation, verify placement path shows confidence when applicable ([SCORING.md](./SCORING.md) Phase 3).
6. **Design `expo-av`:** If touching `BACKING_TRACKS` or `expo-av`, run the **Smoke-test all … backing tracks** control on the Design tab and confirm `OK — played N tracks` (see [expo-av & Design dev playback](#expo-av--design-dev-playback)).

---

## Related docs

- [E2E_DEMO.md](./E2E_DEMO.md) — cold start, end-to-end path
- [SCORING.md](./SCORING.md) — scoring rollout and QA checkpoints
- [PRIORITIES.md](../PRIORITIES.md) — roadmap (Feel Real commits **45–61**, §17 pitch gate)
- [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) — UI tokens and QA cross-links
- [backend/README.md](../backend/README.md) — Demucs / API setup
