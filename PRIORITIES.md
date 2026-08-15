# Harmoniq — Engineering Roadmap

Three-phase product roadmap for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**. **Phase 2 ML (commits 98–103)** — **complete**. **Phase 3 (commits 108–109)** — **complete**. **Phase 4 (commits 104, 105, 114)** — **complete**. **MLOps (commits 136–140)** — **complete**. **Commit 106 (Solo Rhythm Quantization & Measure-Level Sanity)** — **complete**.

---

## At a glance

| | |
|--|--|
| **Roadmap status** | **Phase 0–4 + MLOps complete. Commits 100, 101, 103 complete (Segment Boundary Tie, Real Dataset Integration, Training Infrastructure). Commit 106 complete (Solo Rhythm Quantization & Measure-Level Sanity). Product milestone "ML Fallback Logic" ✅ DONE (composite transcription confidence + auto skeleton-tab fallback). Pending: SWE features, remaining ML refinement, remaining product milestones. Open goal: >75% Isophonics test root accuracy (66.1% as of Commit 103).** |
| **Product spec** | [`README.md`](README.md) |
| **UI spec** | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Scoring** | [`docs/SCORING.md`](docs/SCORING.md) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (Phase 0–4 + MLOps + Product Milestones) |

---

## Phase 2: Product Milestones

---

### Milestone: Play Engagement Analytics

System for tracking user engagement during play-along sessions: duration, completion, and discard rates.

**Scope:**
- Build lightweight event analytics system (custom event bus, no third-party SDK)
- Track play-along start/stop events with duration counters per session
- Track chart discard events (user closes tab or exits Play step mid-performance)
- Track session step progression (which steps user reaches before exiting)
- Compute per-user per-song engagement metrics:
  - % sessions with play-along duration >60s
  - % sessions completed without discard
  - Mean play time and mean step depth reached
- Wire analytics hooks into session exit handlers and Play capture lifecycle
- Store events to local DB (SQLite mobile / IndexedDB web) with batched writes
- Add developer-facing engagement summary to review panel or debug screen
- Ensure analytics tracking is zero-cost during playback (deferred writes, no latency impact)
- Make all tracking opt-out with privacy notice

**Acceptance Criteria:**
- [ ] Play-along duration recorded per session with second precision
- [ ] Chart discard events captured (user exits Play step with unanswered take)
- [ ] Session progression tracked: which of [tune, listen, study, slow, play, review] were visited
- [ ] "Processed songs with >60s play-along without discard" metric is computable
- [ ] Events persisted to local DB and survive app restart
- [ ] Analytics adds zero latency to audio playback or capture
- [ ] Privacy notice displayed; user can opt out

---

## Phase 2: ML Refinement — Pending Commits

### Commit 107: MusicXML as Primary Render Format

**Goal:** Switch the frontend from GP5-based AlphaTab rendering to MusicXML-based rendering, making MusicXML the canonical render format for chord symbols and solo notation as declared in the product spec.

**Current State:** MusicXML is produced by the analysis pipeline but only used for download export. The frontend AlphaTab harness renders GP5 base64 exclusively. `README.md` declares MusicXML canonical but it is not the active rendering path.

**Scope:**
- Update the AlphaTab WebView harness (`assets/alphatab-harness/`) to accept and render MusicXML (`.musicxml` / XML string) as primary input via `api.loadMusicXML()` or equivalent
- Add MusicXML loading path in `AlphaTabWeb.web.tsx` alongside existing GP5 path
- Add MusicXML loading path in `ScoreViewer.tsx` / `AlphaTabWebView.tsx` for native rendering
- Complete the MusicXML builder (`musicxml_builder.py`) with all standard notation elements:
  - Dynamics (`<dynamics>`: p, mf, f, etc. mapped from note velocity)
  - Articulations (`<articulations>`: staccato, accent, tenuto)
  - Slurs (`<slur>` for legato passages)
  - Beams (`<beam>` grouped by beat and tuplet structure from Commit 106)
  - Chord diagrams (`<frame>` elements for fretboard positions)
  - Parallel tablature staff (`<staff type="tab">`) below standard notation staff
- Add `musicxml` primary field to `LessonJSON` schema; deprecate `tab_full_gp5_base64` as primary
- Update `alphatab_prerender.py` to generate prerender SVGs from MusicXML instead of GP5
- Update all frontend consumers to read from `musicxml` field with GP5 fallback
- Remove `tab_full_gp5_base64`, `tab_skeleton_gp5_base64`, `tab_alt_position_gp5_base64` from primary `LessonJSON` type; move to export-only fields
- Add integration tests: MusicXML round-trip through AlphaTab rendering on web and native
- Update README to reflect MusicXML as active canonical format (remove "aspirational" language)
- Persist Score.musicxml as standalone file in job directory:
  write `data/jobs/{job_id}/score.musicxml` alongside existing JSON artifacts
  (BeatGrid.json, chordTimeline.json, SoloNotes.json), enabling direct file
  download and cache reuse of the MusicXML artifact
- Add `<defaults>` with `<scaling>` (7mm/40 tenths matching
  `gp_export_musicxml.py`), `<page-layout>`, and `<system-layout>` to the
  music21 MusicXML output path. Without these, AlphaTab applies its own layout
  defaults which may differ from the score designer's intent
- Add MusicXML schema validation in CI: validate all generated MusicXML output
  against the MusicXML 3.1 Partwise DTD in `tests/test_exporter.py`. Currently
  only one test exists that parses with music21 — no DTD/XSD-level validation
- Expose `beat_grid: BeatGrid`, `chord_timeline: ChordTimeline`, and
  `solo_notes: SoloNotes` as top-level fields in `LessonJSON` schema.
  Currently they're only in `MusicXMLJsonExportRequest` and per-section via
  `extra="allow"`, requiring clients to reconstruct from sections
- **Add cross-platform MusicXML rendering test suite:**
  - Render each generated MusicXML on both web (DOM AlphaTab via `AlphaTabWeb.web.tsx`)
    and native (WebView AlphaTab via `AlphaTabWebView.tsx`)
  - Compare rendered output via Playwright visual regression screenshots (web)
    and native screenshot comparison (Android/iOS sim)
  - Track known AlphaTab rendering quirks as a living doc: list unsupported
    MusicXML elements, layout differences between web and native backends
- **Build edge-case MusicXML corpus for AlphaTab semantic loading:**
  - Generate MusicXML with: irregular time sigs (5/4, 7/8), nested tuplets,
    polyrhythms, extreme tempo changes, multi-voice staves
  - Verify each edge case renders without crash on both platforms
  - Document any parsing failures or visual discrepancies as AlphaTab bugs
    to track upstream

**Acceptance Criteria:**
- [ ] Frontend AlphaTab renders MusicXML via `api.loadMusicXML()` on web (GP5 retained as fallback)
- [ ] Native WebView harness renders MusicXML on both Android and iOS
- [ ] Chord symbols render as `<harmony>` elements in the score
- [ ] Solo notation renders with correct note types, beams, rests, and ties across measures
- [ ] Tablature staff appears below standard notation staff with correct string/fret
- [ ] Chord diagrams (`<frame>`) display inline with chord symbols
- [ ] Dynamics, articulations, and slurs present in generated MusicXML and render in AlphaTab
- [ ] GP5 artifacts removed from primary `LessonJSON` schema; exported-only
- [ ] AlphaTab prerender produces SVGs from MusicXML input
- [ ] Existing export flows (MusicXML download, GP5 download) continue to work
- [ ] README updated
- [ ] `data/jobs/{job_id}/score.musicxml` written as standalone file during analysis
- [ ] `<defaults>` block present in MusicXML output with `<scaling>`,
      `<page-layout>`, and `<system-layout>`
- [ ] CI validates every MusicXML output against MusicXML 3.1 Partwise DTD;
      test fails on invalid XML
- [ ] `LessonJSON` schema has top-level `beat_grid`, `chord_timeline`,
      `solo_notes` fields
- [ ] Cross-platform rendering test suite runs in CI: web screenshots match within
      `maxDiffPixelRatio: 0.02`; native screenshots pass visual regression
- [ ] Edge-case corpus (20+ files) renders without crash on both platforms
- [ ] Known AlphaTab rendering limitations documented in repo for test writer reference

---

## Phase 2: Stem Routing & Audio Pipeline

### Commit 110: Stem Routing Fix — Wire Bass+Other for Chords, Dynamic Melodic Stem for Solo

**Goal:** Wire `build_stem_routing_hints()` output into the main analysis pipeline so chords are inferred from the `bass + other` stem mix (cleaner harmonic signal) and solo is inferred from a dynamically selected melodic stem, not always the guitar stem.

**Current State:** `build_stem_routing_hints()` in `demucs_engine.py:105-139` computes correct routing hints (RMS-based melodic stem selection, bass+other for chords) but they are returned from `/transcription/prepare` as dead metadata. The main pipeline in `jobs.py` → `analyze_audio.py` ignores all hints: chords use the full mix, solo always uses the guitar stem. No audio mixing utility exists to combine stems.

**Scope:**
- Add audio mixing utility `mix_stems(stem_paths: list[Path], output_path: Path)` in a new module `app/audio_mix.py`:
  - Load stem WAVs, sum waveforms, normalize to prevent clipping
  - Handle stems of different lengths (truncate to shortest or pad with silence)
  - Return output path for downstream inference
- Refactor `analyze_audio.py` `build_lesson_json_from_librosa()` to accept `StemRoutingHints`:
  - For chord inference: mix `bass` + `other` stems → pass mixed path to `infer_chords()`
  - For solo inference: use `selected_melodic_stem` from hints (with fallback chain: selected → guitar → vocals)
- Update `jobs.py` `_process_analyze_job()` to call `build_stem_routing_hints()` and pass hints into `build_lesson_json_from_librosa()`
- Preserve the current hardcoded paths as fallback when hints are unavailable or all stems are silent
- Add stem routing telemetry: log which stems were used for chord and solo per job
- Add integration test: verify bass+other mix is used for chord inference, correct melodic stem for solo
- Update `StemRoutingHints` schema to include the actual paths used (not just hints) after routing is resolved

**Acceptance Criteria:**
- [ ] `mix_stems()` utility correctly sums 2+ stem WAVs into a single normalized WAV
- [ ] Chord inference uses `bass + other` stem mix (not full mix) when both stems have non-zero RMS
- [ ] Solo inference uses dynamically selected melodic stem (falls back: selected → guitar → vocals)
- [ ] Stem quality flags (`guitar_near_silent`, `guitar_buried_in_mix`) influence routing decisions
- [ ] Full hardcoded path fallback preserved when hints are unavailable
- [ ] Routing decisions logged per job for observability
- [ ] Integration test confirms multi-source chord input path

---

### Commit 111: Dual-Path Confidence-Weighted Stem Fusion (MT3 Paper Insight)

**Goal:** Run chord inference on both the guitar stem AND the full mix simultaneously, then fuse predictions weighted by stem quality confidence — mimicking MT3's multi-instrument attention without needing the model.

**Rationale (from MT3 paper, Section 4.3):** MT3 achieves strong transcription on the full mix because it learns cross-instrument attention patterns. When Demucs produces a poor guitar stem (piano-dominant mix, buried guitar), our chord model gets degraded input. A dual-path approach gives the model access to both the isolated stem and the full harmonic context, fusing them based on confidence.

**Current State:** `stem_quality.py` detects bad stems with binary flags but falls back to piano stem or full mix as an either/or choice. No confidence-weighted fusion exists.

**Scope:**
- Add dual-path chord inference in `chord_inference.py`:
  - Path A: run inference on guitar stem (or selected melodic stem)
  - Path B: run inference on full mix
  - Both paths produce per-beat chord predictions with confidence scores
- Implement confidence-weighted fusion:
  - Use stem quality score from `stem_quality.py` as the fusion weight
  - `final_prediction = w * stem_prediction + (1-w) * mix_prediction`
  - Where `w` is the continuous stem confidence (0-1, not binary)
  - When stem confidence is high (>0.8): prefer stem path
  - When stem confidence is low (<0.3): prefer full mix path
  - When moderate: blend both predictions
- Upgrade `stem_quality.py` from binary flags to continuous confidence:
  - Compute stem confidence from RMS ratio, spectral overlap, and onset correlation
  - Return `stem_confidence: float` (0-1) alongside existing quality flags
- Pass stem confidence to scoring system so it can adjust its own confidence
- Add instrument confusion diagnostic: large divergence between stem and mix predictions = instrument confusion
- Log fusion decisions per job for observability

**Acceptance Criteria:**
- [ ] Dual-path inference runs on both stem and full mix
- [ ] Confidence-weighted fusion produces more accurate chords on piano-dominant mixes
- [ ] Stem quality returns continuous confidence score (0-1), not binary flag
- [ ] Instrument confusion detected when stem vs mix predictions diverge significantly
- [ ] Fusion decisions logged per job
- [ ] No regression on songs with clean guitar stems
- [ ] Chord accuracy improves by ≥5% on songs flagged with `guitar_buried_in_mix`

---

### Commit 112: Fretboard Sync Parity — Enable Chord/Note Highlighting in All Session Screens

**Goal:** Extend `MusicProvider` wrapping to all session screens (`slow.tsx`, `play.tsx`, `listen.tsx`, `warmup.tsx`) so the fretboard highlights the current chord and active solo notes during every step, not only in `study.tsx`. Use tab string/fret positions from the score instead of recalculating from MIDI.

**Current State:** `MusicProvider` only wraps `study.tsx` (line 128). The `slow`, `play`, `listen`, and `warmup` screens have no MusicProvider, so `FretboardDiagram` receives no chord events or solo notes — the `try/catch` at `FretboardDiagram.tsx:372-377` silently swallows the error, leaving the fretboard blank during playback. Additionally, `findActiveNotes()` in `MusicContext.tsx:165-182` always picks `cells[0]` (lowest-fret MIDI resolution), ignoring the actual string/fret positions from the tab file.

**Scope:**
- Add `<MusicProvider>` wrapping to `app/session/slow.tsx`:
  - Extract `chordEvents`, `soloNotesArr`, `barTimestamps` from lesson/section data (same pattern as `study.tsx:122-125`)
  - Wire `onPlaybackTick` → `musicActions.setPosition()` for playback-driven chord/note lookup
- Add `<MusicProvider>` wrapping to `app/session/play.tsx`:
  - Same pattern; position comes from reference track playback during capture
- Add `<MusicProvider>` wrapping to `app/session/listen.tsx`:
  - Display current chord symbol during orient (listening) phase
- Add `<MusicProvider>` wrapping to `app/session/warmup.tsx`:
  - Display chord/note highlights during drill exercises
- Refactor `findActiveNotes()` in `MusicContext.tsx` to accept optional pre-resolved string/fret positions:
  - When available from `LessonJSON` tab data, use the actual score string/fret
  - Fall back to `allCellsForMidi()` (current behavior) when tab data is unavailable
- Ensure `FretboardDiagram` renders correctly in all four additional screens:
  - Verify chord circle rendering, active note dot rendering, scale degree overlays
  - Test graceful fallback when MusicProvider is absent (existing try/catch pattern)

**Acceptance Criteria:**
- [ ] `slow.tsx` fretboard highlights current chord and active solo notes during playback
- [ ] `play.tsx` fretboard highlights chord/notes from the reference track during capture
- [ ] `listen.tsx` displays current chord symbol during orient playback
- [ ] `warmup.tsx` fretboard responds to playback position
- [ ] `findActiveNotes()` prefers tab string/fret positions when available; falls back to MIDI resolution
- [ ] Fretboard renders gracefully when MusicProvider is absent (no crash)
- [ ] Existing `study.tsx` behavior is unchanged (non-regressed)

---

### Commit 113: Input Normalization & Long-Track Chunking Fix

**Goal:** Add proper loudness normalization (EBU R128), fix long-track chunking so chunks are consumed downstream, add chunk offset metadata, and secure yt-dlp with a subprocess timeout.

**Current State:** `ffmpeg_normalize_wav()` in `pipeline_proof.py:74-108` does resampling and channel downmix only — no loudness normalization. Chunking in `audio_processing.py:45-90` generates 5-minute chunks for tracks ≥15 minutes, but no downstream module reads them (Demucs, librosa, beat_grid all operate on the full `song.wav`). yt-dlp subprocess at `pipeline_proof.py:201` has no timeout.

**Scope:**
- Upgrade `ffmpeg_normalize_wav()` to perform loudness normalization:
  - Add `-af loudnorm=I=-16:TP=-1.5:LRA=11` (EBU R128 standard, -16 LUFS integrated target)
  - Maintain existing resampling (44.1kHz) and downmix (mono) behavior
  - Preserve backward compatibility for all downstream consumers
- Fix chunk consumption: refactor `separate_song_to_stems()` and `build_lesson_json_from_librosa()` to accept chunked audio:
  - Process each chunk through Demucs → produce per-chunk stems
  - Stitch per-chunk stems back into full-song stems (concatenate WAVs)
  - Run librosa/beat_grid/chord/solo on the stitched stems
  - Add chunk offset tracking: `(chunk_index, start_time_s, end_time_s)` per chunk
- Add chunk offset metadata to `AudioPreparationResult`:
  - Store as `list[dict]` with `chunk_index`, `start_seconds`, `end_seconds`
  - Pass through to job result for observability
- Add subprocess timeout to `yt_dlp_download_wav()`:
  - `subprocess.run(cmd, check=True, timeout=600)` (10-minute timeout for downloads)
  - Raise `YouTubeDownloadError` on timeout with user-friendly message
- Add test suite for:
  - Loudness normalization: verify output LUFS meets target within ±1dB
  - Chunking: verify chunk → separate → stitch produces same result as full-file processing
  - Chunk offset metadata: verify timestamps are correct
  - yt-dlp timeout: verify exception raised on timeout

**Acceptance Criteria:**
- [ ] `ffmpeg_normalize_wav()` applies EBU R128 loudnorm targeting -16 LUFS
- [ ] Normalized WAV loudness measures within ±1dB of -16 LUFS
- [ ] All downstream pipelines (Demucs, librosa, beat_grid) accept normalized audio without regression
- [ ] Chunked tracks (≥15 min) are separated per-chunk and stitched into complete stems
- [ ] Stitched stems reproduce identical results to non-chunked processing for sub-15-min tracks
- [ ] Chunk offset metadata recorded and accessible in job output
- [ ] yt-dlp download times out after 10 minutes with user-friendly error
- [ ] Test suite covers loudness, chunking round-trip, offset accuracy, and timeout behavior
- [ ] Minimum 30-second and maximum 300-second duration checks preserved

---

## Phase 2: ML Pipeline Refinement

### Commit 115: Structural Segmentation Refinement

**Goal:** Improve section boundary detection beyond RMS-only novelty by fusing chord change density, Whisper word-cluster boundaries, and energy envelope.

**Current State:** `librosa_summarize()` uses RMS + onset novelty for boundary detection. Sections are unlabeled (just timestamps). ChordMini's SongFormer provides dedicated structural segmentation (intro/verse/chorus/bridge/outro).

**Scope:**
- Add `refine_section_boundaries()` module that fuses three signals:
  - Chord change density: high change rate suggests section boundary
  - Whisper word-cluster boundaries: silence/gap between vocal phrases
  - Energy envelope novelty: existing librosa onset novelty
  - Fusion: weighted average (0.4 chord, 0.3 vocal, 0.3 energy) → peak detection for boundary candidates
- Add section label inference from heuristics:
  - First section → "Intro" (if < 15s) or "Verse"
  - Sections with similar chord progression → same label
  - Repeated chord patterns → "Chorus" when highest energy + repetition
  - Final section → "Outro" (if last 10s declining energy)
  - Default → "Verse" / "Chorus" alternating
- Add confidence metric per section boundary
- Surface section labels and confidence in `LessonSectionStub.label`
- Preserve existing RMS boundaries as fallback when refinement fails
- Add test: real song with known structure (e.g., "Gravity" verse/chorus)

**Acceptance Criteria:**
- [ ] Section boundaries refined using chord density + vocal gap + energy fusion
- [ ] Sections labeled "Intro", "Verse", "Chorus", "Bridge", "Outro" where confident
- [ ] Repeated chord progressions detected and grouped under same label
- [ ] Less than 50% of boundaries moved from librosa baseline (stable at high confidence)
- [ ] Label confidence reported per section
- [ ] Fallback to unlabeled RMS boundaries when refinement confidence < 0.6
- [ ] Integration test: 4-section verse-chorus-verse-chorus song correctly segmented

---

### Commit 116: Instrument Confusion Diagnostic (MT3 Paper Insight)

**Goal:** Add an instrument confusion diagnostic to the analysis pipeline that detects when the chord model's predictions differ significantly between the isolated stem and the full mix, flagging sections where coaching feedback should be hedged.

**Rationale (from MT3 paper, Table 3):** MT3's multi-instrument F1 shows the model rarely confuses instruments when it gets notes right (multi-instrument F1 ≈ onset-offset F1). Our pipeline has no instrument-aware evaluation — we can't distinguish "wrong chord because model confused guitar with piano" from "wrong chord because model misidentified the notes." This matters for coaching: the feedback should differ.

**Current State:** No instrument confusion detection exists. The scoring system has no way to know if a poor transcription is due to instrument interference or genuine model uncertainty.

**Scope:**
- Add instrument confusion metric to `analyze_audio.py`:
  - After dual-path inference (Commit 111), compute divergence between stem and mix predictions
  - Divergence = fraction of beats where stem and mix predict different chords
  - High divergence (>30%) = instrument confusion likely
- Add `instrument_confusion: float` (0-1) to `LessonJSON` metadata
- Add `instrument_confusion_per_section: list[dict]` with per-section scores
- Pass instrument confusion to scoring system:
  - When confusion is high, reduce scoring confidence
  - Flag sections in coaching feedback: "The transcription here is uncertain — the piano may be interfering"
- Add instrument confusion visualization in review panel:
  - Show per-section confusion bars
  - Highlight high-confusion sections in the chord timeline
- Log instrument confusion per job for model improvement tracking

**Acceptance Criteria:**
- [ ] Instrument confusion metric computed per section (0-1 scale)
- [ ] High-divergence sections flagged in LessonJSON metadata
- [ ] Scoring confidence reduced when instrument confusion is high
- [ ] Coaching feedback hedged for high-confusion sections
- [ ] Instrument confusion displayed in review panel
- [ ] Per-job confusion logged for model improvement tracking
- [ ] Integration test: piano-dominant mix shows higher confusion than guitar-forward mix

---

### Commit 117: MT3 as Auxiliary Training Tool (Enhanced with Paper Insights)

**Goal:** Use Google's MT3 (Music Transcription Transformer) as an auxiliary tool to improve the custom pipeline — not as a replacement — via transfer learning, synthetic data generation, ensemble voting, and label bootstrapping. Enhanced with key insights from the MT3 paper (ICLR 2022).

**Rationale:** Building a custom pipeline from scratch means limited training data and no exposure to diverse instrument timbres. MT3 was trained on thousands of hours of polyphonic audio and can serve as a free pre-trained feature extractor and label generator. The custom pipeline remains the primary inference path; MT3 is a data/features/labels augmentation layer.

**Key paper insights informing this commit:**
- **Model size matters less than data diversity**: MT3's T5-small (60M params) outperformed larger models because larger models overfit on music data. Our TFLite model is already appropriately sized — focus on data, not architecture.
- **Temperature sampling is critical**: MT3's `(n_i / Σn_j)^0.3` sampling boosted guitar F1 by 263%. Apply this to our chord type sampling (see Commit 104).
- **LODO reveals dataset gaps**: Leave-one-dataset-out experiments showed the model fails on instruments it never saw. MT3 alone won't solve guitar-specific challenges — our custom pipeline must remain independent.
- **Label noise is real**: Threshold sensitivity analysis (Appendix D.2) revealed significant timing errors in MusicNet/URMP labels. Validate any MT3-generated labels before mixing into training (see Commit 102).
- **Don't expect zero-shot generalization**: LODO experiments show bass/synth F1 drops to 0.02-0.07 without Slakh/Cerberus training. MT3 won't handle instruments outside its training distribution.

**Scope:**
- **Transfer learning — MT3 encoder as feature extractor:**
  - Freeze MT3 encoder backbone (T5-based), feed 84-bin CQT through it
  - Extract encoder hidden states as feature vectors per time step
  - Train custom heads (chord ID, clarity, etc.) on top of frozen MT3 features
  - Compare accuracy vs scratch-trained model on validation set
  - Keep custom pipeline architecture as fallback when MT3 unavailable (on-device inference)

- **Synthetic data generation via MT3 primitive detection:**
  - Run MT3 on unlabeled YouTube/song audio → output raw MIDI event stream
  - Convert MIDI stream → chord labels via music21 (deterministic theory)
  - Mix MT3-generated labels into training set as additional synthetic examples
  - Apply confidence filter: only include MT3 labels where model confidence > 0.8
  - **Run threshold sensitivity analysis on MT3 labels** before mixing (Commit 102 methodology)

- **Ensemble voting for inference:**
  - Run TFLite custom model + lightweight MT3 distilled variant in parallel
  - Weighted voting layer: 0.6 custom model + 0.4 MT3 for final prediction
  - Only in cloud/backend path (on-device uses custom model alone)
  - Track ensemble accuracy improvement vs single-model baselines

- **Label bootstrapping for manual correction pipeline:**
  - MT3 produces initial labels for user-uploaded audio
  - User corrects errors in beat grid editor / chord timeline (Commit 108/109)
  - Corrected labels become training data for next custom model retrain
  - Track label-correction ratio: % of MT3-proposed labels that users accept without change

- **Jazz vocabulary extension exploration:**
  - Evaluate MT3's handling of extended jazz harmony (7#9, alt7, altered tensions)
  - Catalog MT3 failure modes on jazz audio → informs custom model data collection priorities
  - Document which jazz chord types are MT3-competent vs MT3-blind

**Acceptance Criteria:**
- [ ] MT3 encoder features improve custom model chord ID accuracy by ≥5% vs scratch-trained
- [ ] MT3-generated synthetic labels expand training set by ≥100 hours of labeled audio
- [ ] Ensemble voting improves accuracy by ≥3% on extended chord types
- [ ] Label bootstrapping pipeline: MT3 → user correction → retraining data
- [ ] MT3 jazz failure modes documented: which chord types/voicings need more custom data
- [ ] Custom pipeline remains independent (no regression when MT3 unavailable)
- [ ] Integration test: MT3 → chord label round-trip matches known progression within 80%
- [ ] MT3-generated labels pass threshold sensitivity analysis before mixing into training
- [ ] Model size kept at ~60M params (T5-small) — no larger model attempted

---

## Phase 3: Music Theory Foundations

### Milestone: Music Theory Foundations

**Goal:** Build a comprehensive music theory framework across the app — scale/mode library, interactive fretboard visualization, progression analysis, and Slonimsky-based exercise generation — so every session screen shows the user relevant harmonic context at their level.

---

### Commit 118: Scale/Mode Library & Interval Constants

**Goal:** Create foundational music theory data structures — a complete scale/mode library and named interval constants — that all downstream features (fretboard overlay, Jam detection, scale explorer, pattern generator) depend on.

**Current State:** No scale/mode library exists. Only 6 pentatonic templates in `pitchClassHistogram.ts`. No interval constants — intervals are hardcoded as numbers across multiple files.

**Scope:**
- Create `src/music/scales.ts` with every common scale as pitch class sets (number[] 0-11):
  - **Diatonic modes**: Ionian (major), Dorian, Phrygian, Lydian, Mixolydian, Aeolian (natural minor), Locrian
  - **Harmonic minor modes**: harmonic minor, Locrian ♮6, Ionian ♯5, Dorian ♯4, Phrygian dominent, Lydian ♯2, super-Locrian bb7
  - **Melodic minor modes**: melodic minor, Dorian ♭2, Lydian augmented, Lydian dominant, Mixolydian ♭6, Aeolian ♭5, super-Locrian
  - **Pentatonic**: major pentatonic (5 positions), minor pentatonic (5 positions), blues
  - **Symmetrical**: whole-tone, diminished (half-whole, whole-half), augmented, chromatic
- Each scale entry: `{ name, pitchClasses: number[], intervals: string (e.g. "W-W-H-W-W-W-H"), aliases: string[] }`
- Create `src/music/intervals.ts` with:
  - `Interval` enum: `m2 = 1, M2 = 2, m3 = 3, M3 = 4, P4 = 5, TT = 6, P5 = 7, m6 = 8, M6 = 9, m7 = 10, M7 = 11, P8 = 12`
  - `intervalName(semitones: number): { quality: 'major'|'minor'|'perfect'|'augmented'|'diminished', number: string }` helper
  - `intervalFromNotes(note1: string, note2: string): number` — compute interval between two note names
- Export all scales as a single `SCALE_DB: Record<string, ScaleEntry>` for easy lookup
- Write unit tests: every scale's interval string sums to octave, pitch class sets have correct cardinality

**Acceptance Criteria:**
- [ ] `src/music/scales.ts` exports all 30+ scales as pitch class sets
- [ ] `src/music/intervals.ts` exports `Interval` enum and helper functions
- [ ] Every scale entry has valid pitch classes (all in 0-11 range, covers 0..11 or subset)
- [ ] Pentatonic scales have 5 pitch classes, hexatonic 6, heptatonic 7, symmetrical 6-12
- [ ] Unit tests verify interval string consistency and pitch class correctness
- [ ] Existing `pitchClassHistogram.ts` imports from new library (backward compatible)

---

### Commit 119: Scale Explorer Screen

**Goal:** Build an interactive screen where users can explore any scale across the full fretboard — see note positions, scale degree labels, CAGED zones, and hear each note — providing a visual reference that ties directly to practice.

**Current State:** No scale exploration UI exists. The fretboard only highlights chord tones (Study step) or Jam-detected pentatonic notes (Jam step). Users have no way to browse scales visually.

**Scope:**
- Create `app/scale-explorer/index.tsx` — new route reachable from:
  - Fretboard toolbar "Explore" button
  - Home screen "Explore Scales" suggestion card
  - Jam mode detected-scale label tap (navigate to that scale)
- Scale picker component:
  - Root note selector: C, C#, D, D#, E, F, F#, G, G#, A, A#, B (circular scroll)
  - Mode/quality picker: grouped by family tabs (Diatonic, Harmonic Minor, Melodic Minor, Pentatonic, Symmetrical)
  - Quick-favorites: pin scales to top for quick access (persisted to SQLite)
- Fretboard display:
  - Reuse `FretboardDiagram` or render separate inline SVG with full 12-fret neck
  - Highlight all scale notes in green (root in amber, larger)
  - Three overlay toggles: scale degree labels (1, b2, 2...), note names (C, D, E...), interval names (P1, M2, M3...)
  - CAGED position zones: color-code each of the 5 positions, tap to zoom/isolate
- Audition:
  - Tap any highlighted note → play via `GlobalAudioManager` (sine tone or guitar sample)
  - "Play scale" button → ascending/descending playback at selectable tempo
- Practice integration:
  - "Practice this scale" → generates warmup exercise via `POST /exercises/generate` (or local algorithm)
  - "Add to licks" → persist as a saved lick with scale metadata
- Backing drone: toggleable drone in the selected root key during exploration
- Persist favorites to `user_preferences` table in local DB

**Acceptance Criteria:**
- [ ] Scale picker shows all 30+ scales from the scale library
- [ ] Fretboard highlights all scale notes with root distinguished
- [ ] Overlay toggles cycle through scale degrees, note names, interval names
- [ ] CAGED positions color-coded and tappable to zoom
- [ ] Note audition plays correct pitch when tapped
- [ ] "Play scale" button ascends/descends through the scale at selectable BPM
- [ ] "Practice this scale" button generates a drill session
- [ ] Scale favorites persist across app restarts
- [ ] Navigation accessible from fretboard toolbar, home card, and Jam detection label

---

### Commit 120: Fretboard Theory Overlay in Study Step

**Goal:** Enhance the Study step fretboard to show three tiers of harmonic information — scale tones, chord tones, and outside notes — so the player can see which notes are "safe" and which are tensions at a glance.

**Current State:** Study step fretboard shows chord tones (amber dots) and active notes (red from MusicContext). No scale context is provided. Tapping a note shows its name but no harmonic function.

**Scope:**
- Derive scale pitch classes from song's detected key using new `src/music/scales.ts`
- Render three visual tiers on `FretboardDiagram`:
  - **Scale tones** — faint green circles (15% opacity) for notes in the key's scale
  - **Chord tones** — existing amber circles for notes in the current chord
  - **Outside tones** — no highlight (gray or invisible)
- Add toggle button in Study toolbar: "Key context" / "Chord only" / "Off"
- When a note is tapped (via existing `onCellPress`):
  - Extend `NoteDetailCard` or add inline overlay showing:
    - Note name, octave
    - Scale degree in key (e.g., "4th of C major")
    - Chord tone status: root / 3rd / 5th / 7th / extension / not a chord tone
    - Diatonic vs chromatic: "In key" (green) / "Outside" (red)
- Wire `scalePitchClasses` into `MusicContext` alongside existing `chordEvents`/`soloNotesArr`:
  - Add `scalePitchClasses: number[] | null` to `MusicProvider` state
  - Compute from lesson key on section load
  - Pass to `FretboardDiagram` for rendering

**Acceptance Criteria:**
- [ ] Scale tones visible as green circles in Study fretboard when "Key context" mode is active
- [ ] Chord tones (amber) render as before, on top of scale tones
- [ ] Outside notes have no highlight — visually distinct from scale/chord tones
- [ ] Toggle cycles through "Key context" → "Chord only" → "Off" modes
- [ ] Tapped note displays scale degree and chord tone status
- [ ] Diatonic notes marked green, chromatic notes marked red in note detail
- [ ] `MusicContext` exposes `scalePitchClasses` derived from lesson key
- [ ] Existing chord-only behavior is preserved when "Chord only" or "Off" is selected

---

### Commit 121: Expanded Jam Scale Detection

**Goal:** Replace the current 6-template pentatonic-only scale matcher with the full 30+ scale library, enabling Jam mode to detect Dorian, Mixolydian, Lydian, and other modes in real time.

**Current State:** `pitchClassHistogram.ts:14-22` has 6 hardcoded pentatonic templates (A minor pentatonic, A blues, G major pentatonic, E minor pentatonic, C major pentatonic, D minor pentatonic). Scale detection is limited to these 6, scoring via simple pitch class overlap. No mode awareness.

**Scope:**
- Replace inline template array with dynamic import from `src/music/scales.ts`
- Integrate all 30+ scales as matchable templates:
  - Group by family for secondary scoring (if multiple templates match, prefer the one in the same family)
- Improve scoring algorithm:
  - Current: simple overlap (fraction of matching pitch classes)
  - New: weighted score = 0.5 × overlap + 0.3 × root alignment + 0.2 × pentatonic skeleton match
  - Pentatonic skeleton: most scales contain a pentatonic subset — bonus if user plays pentatonic notes
- Surface detected mode in Jam UI:
  - Replace "A minor pentatonic" with "A Dorian (confidence: 0.82)"
  - Show top 3 candidates with confidence bars
  - If confidence < 0.5, show "Mixed mode" with likely note biases
- Add `inferred_mode` field alongside existing `inferred_scale_label` in `BestScaleMatch`
- Persist mode to `jam_snapshots` table schema
- Add unit tests: known pitch class distributions for each mode return correct match

**Acceptance Criteria:**
- [ ] Jam mode detects all 7 diatonic modes, not just pentatonic
- [ ] Scoring uses weighted formula (overlap + root + pentatonic skeleton)
- [ ] Top 3 candidate modes displayed in Jam UI with confidence bars
- [ ] `inferred_mode` field present in `BestScaleMatch` and `jam_snapshots`
- [ ] Confidence < 0.5 shows "Mixed mode" with note bias breakdown
- [ ] No regression: existing pentatonic templates still match correctly
- [ ] Unit tests verify correct detection of Dorian, Mixolydian, Lydian from synthetic histograms

---

### Commit 122: Chord Progression Labels

**Goal:** Analyze consecutive chord events to identify common progressions (ii-V-I, I-IV-V, I-vi-IV-V, etc.) and display bracketed labels on the chord timeline, helping users recognize harmonic patterns.

**Current State:** Each chord gets an independent Roman numeral from `chordFunction.ts`. No analysis of consecutive chord relationships exists. The chord timeline shows individual chord symbols only.

**Scope:**
- Define common progression patterns as sequences of scale-degree intervals:
  ```typescript
  const PROGRESSION_PATTERNS = [
    { name: 'ii-V-I', degrees: ['ii', 'V', 'I'] },
    { name: 'I-IV-V', degrees: ['I', 'IV', 'V'] },
    { name: 'I-vi-IV-V', degrees: ['I', 'vi', 'IV', 'V'] },
    { name: 'ii-V-I-VI', degrees: ['ii', 'V', 'I', 'VI'] },
    { name: 'I-V-vi-IV', degrees: ['I', 'V', 'vi', 'IV'] },
    { name: 'i-iv-v-i', degrees: ['i', 'iv', 'v', 'i'] },
    { name: 'ii-V', degrees: ['ii', 'V'] },
    { name: 'V-I', degrees: ['V', 'I'] },
  ]
  ```
- Implement sliding-window matcher in `chordFunction.ts` or new `src/music/progressionAnalysis.ts`:
  - After Roman numeral assignment, run a sliding window across consecutive chords
  - Match window against all progression patterns (case-sensitive for major/minor)
  - Support overlapping matches (e.g., I-V-vi-IV matches both I-V and V-vi and I-V-vi-IV)
  - Store longest match per position
- Add `progression_label: string | null` and `progression_position: number | null` (index within progression) to `ChordEvent` schema (frontend type, not backend LessonJSON necessarily)
- Display in chord timeline UI:
  - Bracketed label below chord symbol: "ii → V → I"
  - Optionally color brackets per progression type
  - Tap label → tooltip with educational text: "ii-V-I is the most common jazz progression. The ii builds tension, V pulls hard to I (resolution)."
- Add `src/music/progressionKnowledge.ts` with educational descriptions per progression type
- Write unit tests: known progression sequences return correct labels

**Acceptance Criteria:**
- [ ] Sliding window matches common progressions in chord timeline
- [ ] ii-V-I in C major correctly labeled (Dm7 → G7 → Cmaj7)
- [ ] I-IV-V correctly labeled across multiple keys
- [ ] Overlapping progressions handle longest-match correctly
- [ ] Progression labels display as bracketed annotations below chord symbols
- [ ] Tapping label shows educational tooltip
- [ ] No regression: single-chord Roman numeral analysis unchanged
- [ ] Unit tests pass for all defined progression patterns

---

### Commit 123: Slonimsky-Expanded Warmup Pool

**Goal:** Add 15+ new warmup exercises derived from Slonimsky's three families (interpolation, infrapolation, ultrapolation) to expand fretboard vocabulary and break linear playing habits.

**Current State:** Warmup pool has 3 Slonimsky exercises (tritone shift, interpolated chromatic, infrapolated major 3rd) with basic fretboard guides but no tab data. Total pool: 22 exercises.

**Scope:**
- Add 15 new exercises to `warmup_pool.json` covering all three Slonimsky families:

  **Interpolation family (5 exercises):**
  - `pool_slon_ic_01` — Major 2nd interpolation: C-D-E across strings (filling in the gap between C and E)
  - `pool_slon_ic_02` — Minor 3rd interpolation: A-C → A-Bb-C pattern
  - `pool_slon_ic_03` — Perfect 4th interpolation: C-F → C-D-E-F on adjacent strings
  - `pool_slon_ic_04` — Major 3rd interpolation ascending and descending
  - `pool_slon_ic_05` — Double interpolation: C-G → C-D-E-F-G (two notes between)

  **Infrapolation family (5 exercises):**
  - `pool_slon_if_01` — Single infrapolation: lower neighbor → root → upper neighbor (B-C-D)
  - `pool_slon_if_02` — Double infrapolation: two below → root → two above
  - `pool_slon_if_03` — Infrapolated perfect 4th: surround C-F with chromatic neighbors
  - `pool_slon_if_04` — Infrapolated minor 6th
  - `pool_slon_if_05` — Infrapolated octave: surround C-C with B-Db in both octaves

  **Ultrapolation family (3 exercises):**
  - `pool_slon_ul_01` — Ultrapolated major 3rd: C → B (M7 below) → E (M3 above) → ...
  - `pool_slon_ul_02` — Ultrapolated tritone
  - `pool_slon_ul_03` — Ultrapolated minor 7th

  **Compound patterns (2 exercises):**
  - `pool_slon_cp_01` — Interpolation + infrapolation combined on a descending P4
  - `pool_slon_cp_02` — Nested subdivision: split a P5 into two m3s, interpolate each

- Each exercise entry includes:
  - `name`, `description`, `duration_seconds` (45-75), `technique_tag`, `opener_kind`, `style_tags`
  - `fretboard_guide.cells` — proper string/fret/finger coordinates for visual highlighting
  - `difficulty` field (1-5) for skill-appropriate selection
  - `slonimsky_family` field: `"interpolation"`, `"infrapolation"`, `"ultrapolation"`, `"compound"`
- Update `warmup_generator.py` selection algorithm:
  - When user profile has "jazz" or "advanced" taste preference, weight Slonimsky exercises higher
  - Prefer exercises from a Slonimsky family the user hasn't seen recently (rotate families)
  - Difficulty-aware: beginner (1-2), intermediate (3), advanced (4-5)

**Acceptance Criteria:**
- [ ] 15 new Slonimsky exercises added to `warmup_pool.json`
- [ ] Each exercise has valid `fretboard_guide.cells` with string/fret/finger
- [ ] Each exercise has `difficulty` and `slonimsky_family` fields
- [ ] Warmup generator selects Slonimsky exercises for jazz/advanced users
- [ ] Warmup generator rotates Slonimsky families across sessions
- [ ] Exercise descriptions help the user understand the Slonimsky concept
- [ ] All existing exercises remain unchanged (no regression)

---

### Commit 124: Slonimsky Pattern Generator ("Lick of the Day")

**Goal:** Build an algorithmic generator that creates a new melodic pattern each practice session from Slonimsky principles — interpolation, infrapolation, ultrapolation — transposed to the user's current key/scale of focus and rendered as tab/fretboard with optional backing. Feeds the "Daily Lick" concept from Phase 3 Discovery.

**Current State:** No algorithmic pattern generation exists. The "Daily Lick" in Phase 3 is aspirational with no implementation. The warmup pool is hand-written JSON only.

**Scope:**
- Create `src/music/slonimskyGenerator.ts` (frontend-side, for fast local generation):
  ```typescript
  interface SlonimskyPattern {
    name: string
    family: 'interpolation' | 'infrapolation' | 'ultrapolation' | 'compound'
    baseInterval: number         // semitones
    patternNotes: number[]       // absolute MIDI notes
    fretboardCells: { string: number, fret: number, finger: number }[]
    difficulty: 1 | 2 | 3 | 4 | 5
    description: string
  }
  ```
- **Pattern generation algorithm:**
  - **Interpolation**: Given outer interval `(root, root+interval)`, insert N chromatic steps between them. N = floor(interval/2). Result: root → root+1 → root+2 → ... → root+interval
  - **Infrapolation**: Given center note `root`, place (root-1) and (root+1) around it. For double infrapolation, (root-2) → (root-1) → root → (root+1) → (root+2)
  - **Ultrapolation**: Given an interval crossing octave, extend beyond the range. E.g., C below → Bb (m7 above root) → D (9th above root)
  - **Compound**: Chain two families together
- **Fretboard mapping:**
  - Given pattern notes as MIDI, find playable positions using existing `allCellsForMidi()` / `midiToFretboardRow()` from `fretboardCell.ts`
  - Select first valid position (lowest fret, within 1-12 range)
  - Assign fingerings via existing `fingerSuggestion.ts`
- **Integration with existing systems:**
  - Persist generated pattern to `licks` table with `source: 'slonimsky_daily'`
  - Display on home screen as "Today's Slonimsky Lick" card
  - Tap → opens in existing Jam or Warmup flow with fretboard highlighting
  - Track completion: did user practice it today? SM-2 for re-introduction (existing `skill_nodes` mechanism)
- **Backing accompaniment:**
  - Generate a simple vamp in the user's current key (I-IV or drone)
  - Use existing `jam_backing.py` or local audio generation
  - Lock to user's comfort BPM from `PlayerProfile`
- **Difficulty scaling:**
  - Beginner (1-2): single-family, one string, simple intervals (M2, M3)
  - Intermediate (3): single-family, cross-string, P4/P5 intervals
  - Advanced (4-5): compound family, wide intervals (m7, P8), across all strings
- **Daily rotation:**
  - Seed selection from date + user ID (deterministic, so same user gets same pattern all day)
  - Track which families seen recently → avoid repeating same family within 3 days

**Acceptance Criteria:**
- [ ] `slonimskyGenerator.ts` produces valid `SlonimskyPattern` objects
- [ ] Generated patterns cover all three families plus compound
- [ ] Patterns map to playable fretboard positions within frets 1-12
- [ ] Fingerings assigned correctly per existing `fingerSuggestion.ts`
- [ ] Daily pattern persists to `licks` table and appears on home screen
- [ ] Tap opens fretboard view with pattern highlighted
- [ ] Completion tracked via SM-2 (pattern re-introduced on schedule)
- [ ] Backing vamp generated at user's comfort BPM in current key
- [ ] Difficulty scales correctly by user's PlayerProfile skill level
- [ ] Same user sees same pattern all day (deterministic seed); different pattern next day
- [ ] No regression in existing warmup or lick flows

---

### Commit 125: Inversion & Slash Chord Logic

**Goal:** Implement bass-note detection to support accurate slash notation
(e.g., G/B, D/F#) and identify 1st/2nd inversions with schema-level support.

**Current State:** `ChordEvent` has no `bass` field. MusicXML output never
produces `<bass>` inside `<harmony>`. All chords render in root position
regardless of the actual audio.

**Scope:**
- Add `bass` field to `ChordEvent` schema: `bass: str | None`
  (default None, e.g. "B" for G/B, "F#" for D/F#)
- Implement bass-note extraction from low-frequency CQT bins of the
  `bass+other` stem mix in `chord_inference.py`
- Emit `<bass>` element inside MusicXML `<harmony>` when bass ≠ root:
  `<root><root-step>C</root-step></root><bass><bass-step>G</bass-step></bass>`
- Update `_harmoniq_chord_to_music21()` to handle slash notation
  (e.g., `"G:maj/B"` → `"G/B"` for music21)
- Add inversion identification (1st = 3rd in bass, 2nd = 5th in bass):
  expose `inversion: int | None` on `ChordEvent`
- Add integration test: known slash chord (G/B) round-trips through MusicXML
  and renders `<bass>` correctly

**Acceptance Criteria:**
- [ ] `ChordEvent.bass` field stores detected bass note
- [ ] `<bass>` element emitted in MusicXML when bass ≠ root
- [ ] AlphaTab renders slash chord notation (e.g., "G/B") from MusicXML
- [ ] Inversions identified from bass note analysis (1st, 2nd)
- [ ] `_harmoniq_chord_to_music21()` handles "root:quality/bass" format
- [ ] Integration test: G/B → MusicXML → `<bass><bass-step>B</bass-step></bass>`

---

## Product Features

### Commit 126: Voicing & Position Inference

Develop logic to identify specific fretboard shapes (e.g., distinguishing between a 'CAGED' E-shape vs. A-shape voicing) based on spectral peaks.

**Scope:**
- Spectral analysis for voicing detection
- CAGED system shape recognition
- Position inference from audio features

**Acceptance Criteria:**
- [ ] System distinguishes E-shape vs A-shape voicings
- [ ] CAGED positions inferred from spectral peaks
- [ ] Fretboard diagrams reflect detected voicing

---

### Commit 127: Live Mic Mode

Implement a low-latency (<120ms) 'Active Listener' view for real-time chord detection from external audio sources (live bands/radio).

**Scope:**
- Real-time audio processing pipeline
- Low-latency chord detection (<120ms)
- UI for live audio visualization

**Acceptance Criteria:**
- [ ] Chord detection latency under 120ms
- [ ] Live bands/radio audio processed in real-time
- [ ] Active Listener UI displays detected chords

---

### Commit 128: The "Chord Pulse" Dashboard

Build a scrolling chord timeline with 'falling notes' visualizer and a beat-synced 'Pulse' ring that expands on downbeats.

**Scope:**
- Scrolling chord timeline component
- Falling notes visualizer
- Beat-synced Pulse ring animation

**Acceptance Criteria:**
- [ ] Chord timeline scrolls smoothly with playback
- [ ] Falling notes animate on chord changes
- [ ] Pulse ring expands on downbeats

---

### Commit 129: Multi-Instrument Diagram Support

Add real-time toggles to switch between Guitar, Piano, and Ukulele diagrams, including support for alternate tunings.

**Scope:**
- Multi-instrument diagram components
- Real-time instrument toggle UI
- Alternate tuning support

**Acceptance Criteria:**
- [ ] Guitar, Piano, Ukulele diagrams render correctly
- [ ] Real-time switching between instruments
- [ ] Alternate tunings supported (Drop D, Open G, etc.)

---

### Commit 130: 6-Stem High-Fidelity Demucs

Upgrade the analysis pipeline to 'htdemucs_6s' to allow independent 'Guitar' and 'Piano' stem isolation.

**Scope:**
- Upgrade Demucs model to htdemucs_6s
- Guitar stem isolation
- Piano stem isolation

**Acceptance Criteria:**
- [ ] htdemucs_6s produces 6 high-fidelity stems
- [ ] Guitar stem isolated cleanly
- [ ] Piano stem isolated cleanly

---

### Commit 131: Real-Time Stem Mixer & Export — Extended with Stem Routing Override

Add UI controls to mute/solo isolated stems during listening, support .WAV export for individual stems, and provide stem routing override for analysis correction.

**Current State:** Backend accepts `stem_routing_override` on `POST /transcription/verify` but the frontend never sends it, and the inference pipeline ignores it (uses hardcoded `other.wav` / `guitar.wav` paths). The frontend `ListenStemPanel` has per-stem mute toggles but they are local-only. `StemMixer` is a stub component with no controls.

**Scope:**
- Stem mixer UI controls (mute/solo) — replace `StemMixer` stub with full component:
  - Per-stem mute/solo toggle buttons (guitar, bass, drums, vocals, piano, other)
  - Per-stem gain slider
  - Visual stem activity indicators (waveform level during playback)
- Real-time stem mixing with low-latency AudioNode routing (web) / expo-av volume control (native)
- Individual stem .WAV export via download (web) or share sheet (native)
- **Stem routing override for analysis correction**:
  - Build stem routing editor in the listen/study step: dropdown to select which stem mix the analysis pipeline should use for chord and solo inference
  - Options: `auto` (default — use `stem_quality.py` heuristics), `guitar_stem`, `full_mix`, `piano_stem`, `bass+other` (for chord inference)
  - Override selection calls `POST /transcription/prepare` with `stem_routing_override`
  - After override submission, trigger `POST /transcription/analyze/{job_id}` to re-run chord/solo inference with the new stem routing
  - Visual indicator showing which stems are currently being used for analysis (from `StemRoutingHints`)
  - "Re-analyze with stem override" button in song detail panel (post-analysis correction path)
- **Backend: wire stem routing override into analysis pipeline**:
  - Update `POST /transcription/analyze/{job_id}` to read stored `stem_routing_override` from `transcription_metadata`
  - When override is present, select the correct stem file(s) for chord and solo inference instead of using hardcoded paths
  - Preserve current hardcoded paths as fallback when no override is stored
  - Log actual stem paths used per job for observability

**Acceptance Criteria:**
- [ ] Mute/solo controls work for all six stems with real-time effect
- [ ] Per-stem gain sliders adjust volume independently
- [ ] Individual stems exportable as .WAV
- [ ] Stem routing editor displays current routing (from `StemRoutingHints`) and allows override selection
- [ ] Selecting a stem override calls `POST /transcription/prepare` with `stem_routing_override`
- [ ] After override, `POST /transcription/analyze/{job_id}` re-runs inference using the selected stem
- [ ] Backend reads stored `stem_routing_override` and routes chord/solo inference to the correct stem file(s)
- [ ] Hardcoded fallback path used when no override exists (no regression)
- [ ] "Re-analyze with stem override" button available in song detail panel
- [ ] Routing decisions logged per job for observability

---

## Product Features: Session Flow

### Commit 132: Dynamic Session Engine

Implement PlanJSON ingestion and orchestrator for dynamically generated full practice plans via SM-2 scheduler.

**Scope:**
- SessionProvider ingests dynamic PlanJSON object
- Plan structure: Warmup (dynamic drill based on weakest skill_node) → Song Workflow (Listen → Study → Slow → Play → Review) → Jam Session (contextual backing track)
- UI dynamically renders progress tracker based on generated plan length
- PlanJSON caching in SQLite for resumption

**Acceptance Criteria:**
- [ ] SessionProvider accepts and processes PlanJSON
- [ ] Warmup drill generated from weakest skill_node
- [ ] Progress tracker adapts to dynamic plan length
- [ ] `harmoniq://session/resume` re-instantiates cached PlanJSON

---

### Commit 133: Orient-as-Hint

Remove Orient as linear step; integrate as non-intrusive amber overlay (#D4860A) in Study/Play components with '?' toggle.

**Scope:**
- Remove Orient from linear step sequence
- Inject Orient metadata into Study and Play components
- Add '?' toggle / Hint button UI
- Amber overlay showing scale shapes or root notes
- Respect intermediate player flow (no interruptions)

**Acceptance Criteria:**
- [ ] Orient removed from session step sequence
- [ ] Hint toggle available in Study and Play steps
- [ ] Amber overlay displays scale shapes/root notes on activation
- [ ] Overlay is non-intrusive and dismissible

---

### Commit 134: Mastery & Integrity

Implement atomic SQLite updates for dynamic sessions with dual-entry state integrity.

**Scope:**
- Single file mode: Linear 5-step flow updates song mastery
- Dynamic session mode: Orchestrates generated plan
- Atomic DB updates: sessions and skill_nodes tables updated simultaneously on Jam Session completion
- Session marked Complete only when entire generated sequence finishes
- Resumption support from cached PlanJSON

**Acceptance Criteria:**
- [ ] Single file mode updates song mastery correctly
- [ ] Dynamic mode orchestrates full plan sequence
- [ ] Atomic transaction updates sessions + skill_nodes tables
- [ ] Session completion requires full plan completion
- [ ] Resume endpoint restores dynamic plan state

---

### Commit 135: Dynamic Tempo Support (Variable BPM)

**Current State:** Static BPM Only
The current implementation assumes every song is recorded to a static click track. Variable BPM/tempo changes are not supported.

**Evidence:**
- `backend/app/beat_grid.py:46-57` - `_uniform_beat_grid()` uses a constant `step = 60.0 / bpm` with no tempo variation
- The function name itself is `_uniform_beat_grid` - implying a single fixed tempo
- `backend/app/beat_grid.py:125` - When `bpm_override` is provided, it generates a uniform grid without any tempo mapping

**Goal:** Support songs with tempo ramps, accelerandos, and live performances with variable BPM.

**Scope:**
- Replace `_uniform_beat_grid()` with a function that accepts an array of `(time, bpm)` pairs or tempo curve
- Use `librosa.beat.beat_track()` with estimated tempo as a reference, not an override
- Store tempo change events in the returned schema alongside `beats` and `downbeats`
- Support gradual tempo changes (rubato) and sudden tempo shifts
- Maintain backward compatibility with static BPM interface

**Acceptance Criteria:**
- [ ] Beat grid handles variable BPM songs with tempo ramps
- [ ] Tempo curve can be provided as `(time, bpm)` array
- [ ] Grid subdivisions respect local tempo at each point
- [ ] Downbeats calculated correctly through tempo transitions
- [ ] Static BPM interface continues to work unchanged
- [ ] Performance: variable BPM grid generation <100ms for 5-minute track

**Implementation Notes:**
- Consider tempo segment interpolation (linear vs exponential ramps)
- Store base pulse tempo vs instantaneous tempo separately
- UI consideration: visual indicator when tempo changes detected
- May require updating `_subdivide_beats()` to handle non-uniform pulse spacing

---

## Infrastructure

### Commit 138: GPU Job Queue for Demucs

**Goal:** Implement GPU job queue with priority scheduling for Demucs stem separation to improve throughput and cost efficiency.

**Current State:** Demucs runs synchronously per job (separate.py:277) blocking the request thread for minutes.

**Scope:**
- GPU job queue with priority scheduling
- Queue depth management
- GPU utilization tracking
- Batch processing for multiple audio files

**Acceptance Criteria:**
- [ ] Demucs jobs are queued and processed asynchronously
- [ ] Priority scheduling ensures urgent jobs run first
- [ ] Queue depth monitoring prevents overload
- [ ] GPU utilization is tracked and optimized
- [ ] Batch processing improves throughput for multiple files

**Implementation:**
- Integrate Demucs with Celery task queue
- Add priority levels to job schema (urgent, normal, low)
- Implement queue depth monitoring and alerts
- Add GPU utilization tracking (nvidia-smi integration)
- Implement batch processing for multiple audio files
- Add queue management UI for operators

---

### Commit 141: Audio Fingerprinting & Quality Scoring

**Goal:** Implement audio fingerprinting for duplicate detection and quality scoring to reduce compute waste.

**Current State:** Content-addressed caching with SHA256 (cache.py:37-45) but no duplicate detection across different encodings.

**Scope:**
- Audio fingerprinting for duplicate detection
- Quality scoring for audio input
- Smart caching based on audio similarity
- Compute cost reduction through deduplication

**Acceptance Criteria:**
- [ ] Audio fingerprinting detects duplicates across different encodings
- [ ] Quality scoring identifies low-quality audio upfront
- [ ] Smart caching reduces re-analysis of similar audio
- [ ] Compute costs reduced through deduplication
- [ ] Fingerprint-based cache key improves hit rate

**Implementation:**
- Integrate audio fingerprinting library (e.g., dejavu)
- Implement quality scoring algorithm (SNR, clipping detection)
- Add fingerprint-based cache key alongside SHA256
- Implement similarity search for near-duplicates
- Add quality gate to reject low-quality audio early
- Track cache hit rate improvements

---

## Phase 3: AI-Agent Scaling & Pro-App Parity

**Status:** Planned

### Milestone: Lead Sheet Agent

Agentic workflow to convert MIDI + Whisper lyrics into structured MusicXML.

**Scope:**
- Multi-step AI pipeline
- MIDI → MusicXML conversion
- Lyrics alignment and annotation

---

### Milestone: Zero-Latency Monitoring

C++/JSI bridge for real-time high-performance pitch feedback on Mobile.

**Scope:**
- Native module implementation
- JSI bridge architecture
- Sub-millisecond pitch detection

---

### Milestone: Dynamic Backing Track Agent

Integration for AI-generated custom-style jam tracks (Gemini Lyria fallback).

**Scope:**
- Lyria RealTime integration
- Style-aware backing generation
- Fallback to static tracks

---

### Milestone: Virtual Mentor Agent

Long-term data analysis to identify skill plateaus and suggest non-linear practice.

**Scope:**
- Skill trajectory analysis
- Plateau detection algorithms
- Personalized practice recommendations

---

## Product Strengthening

### Robustness & Scaling Gaps (vs Chord.ai)

Infrastructure limitations to address before scaling:

- **No job queue (Redis/Celery)** — uses in-memory dict for job tracking; will not survive restarts or handle concurrent load
- **No retry logic for YouTube failures** — transient network errors cause hard failures; no exponential backoff or circuit breaker
- **Demucs runs synchronously per-request** — blocks the request thread; would bottleneck at scale under concurrent load
- **No audio fingerprinting for duplicate detection** — re-analyzing identical audio wastes compute; no cache key for deduplication
- **No model tracking or performance monitoring** — ML training runs are not logged; no accuracy drift detection or systematic comparison between model versions

---

### Offline Mode

Strategy for SQLite local-first operation with periodic Cloud sync.

**Considerations:**
- Local-first architecture
- Conflict resolution for sync
- Background sync scheduling

---

### Discovery

"Daily Lick" curated feed to reduce choice paralysis.

**Scope:**
- Curated lick selection algorithm
- Daily feed UI
- Personalization based on skill level

---

### Accessibility

High-contrast modes and screen-reader support for the "analog/handcrafted" UI.

**Scope:**
- High-contrast theme variants
- Screen reader labeling
- Keyboard navigation support
