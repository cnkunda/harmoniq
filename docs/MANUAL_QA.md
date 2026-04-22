# Manual QA — Harmoniq

Single reference for release and pipeline gates: stem quality, pitch kill-switch, error-copy verification, Phase 5 session realism, telemetry, Slow & loop residual risks, and lightweight regression smokes.

**MVP Status:** Commits 1-85 complete. See [PRIORITIES.md](../PRIORITIES.md) for full roadmap. Commits 86-87 (Lyria RealTime backing band + adaptive steering) deferred to Future Features.

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

The following backend tests fail due to missing optional ML dependencies (librosa, basic_pitch, music21) that are not installed in the CI/test environment. These failures are pre-existing and not related to recent commits:

- `test_export_musicxml_from_json_basic` - missing music21
- `test_chord_inference_silence_threshold` - missing librosa
- `test_chord_majority_vote_pooling` - missing librosa
- `test_solo_monophonic_truncation` - missing basic_pitch
- `test_solo_micro_note_filtering` - missing basic_pitch

**Status:** These failures are tracked but do not block commits. The optional dependencies are only needed for the full transcription pipeline and are not required for core Harmoniq functionality.

## Regression smokes

Quick paths that do not duplicate full PASS grids:

1. **Cross-step:** From a lesson with stems — **Listen** (seek + optional metronome) → **Slow** (confirm ~**0.65×**, loop plays, **Clear loop** once) → **Study** (tap score note → fretboard highlights).
2. **Jam backing seam:** With `GEMINI_API_KEY`, exercise **`POST /jam/backing`** WAV path; compare loop seam vs **two** bundled loops and note MP3 fallback behavior if API absent.
3. **Review / score:** After a Play pass, open **Review** — diagnostics/reliability UI matches [SCORING.md](./SCORING.md); force score failure → **Do it again** recovers ([Error states](#score-endpoint-failure)).
4. **Telemetry (native):** On iOS/Android, confirm **bridge RTT** and **driftMs** over one reference song vs [Thresholds](#thresholds).
5. **Onboarding:** If changing pitch/score aggregation, verify placement path shows confidence when applicable ([SCORING.md](./SCORING.md) Phase 3).
6. **Design `expo-av`:** If touching `BACKING_TRACKS` or `expo-av`, run the **Smoke-test all … backing tracks** control on the Design tab and confirm `OK — played N tracks` (see [expo-av & Design dev playback](#expo-av--design-dev-playback)).

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

