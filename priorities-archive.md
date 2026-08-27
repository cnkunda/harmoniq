# Harmoniq — Engineering Roadmap Archive

This file contains completed work from Phase 0 through Phase 4, archived during the Phase 4 → wrap-up transition.

**Archive Date:** 2026-08-05

---

## Phase 0 — Foundation (Complete)

| Commit | Summary |
|--------|---------|
| 0.1 | Expo + Router + NativeWind + fonts + tooling |
| 0.2 | FastAPI scaffold, health, stub analyze routes, Pydantic shapes |
| 0.3 | Noise overlay, WoodGradient, component stubs, design-preview |
| 0.4 | AlphaTab harness HTML + `tabMessage` types |
| 0.5 | `.env` / `API_BASE_URL`, backing tracks, `docs/` placeholders |
| 0.6 | `AnimatedPressable`, `LoadingSkeleton`, `EmptyState`, `ErrorBanner`, Toast, `src/api/analyze.ts`, animation presets |

---

## Commits 1-85 — Phase 1: Product Discovery & Core Loop (Complete)

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

---

## Commits 86-97 — Phase 1 Completion (Complete)

### Commit 86: Placement Session Logic

**Goal:** SQLite logic to initialize skill_nodes (e.g., bend_accuracy) based on onboarding performance.

**Scope:**
- Onboarding placement session scoring
- SQLite schema for initial skill node population
- Radial skill graph driven by real scores (not mock data)

**Acceptance Criteria:**
- [x] 3 AlphaTab snippets load real GP5 data
- [x] Mic → pitch stream → score path populates initial skill nodes
- [x] Radial skill graph displays real scores from placement session

**Completed:** 2026-04-22

---

### Commit 87: Global Audio Manager

**Goal:** Implement centralized audio architecture to prevent context bloat and handle hot-swapping between screens.

**Scope:**
- Global Audio Manager singleton for all expo-av and react-native-audio-api instances
- Hot swap logic for deep-linking scenarios (e.g., Single File → Full Practice)
- Audio buffer clearing without app crashes
- Support for 6+ parallel audio streams (Demucs stems) + mic input

**Acceptance Criteria:**
- [x] Global Audio Manager singleton controls all audio instances
- [x] Hot swap clears audio buffers without crashes
- [x] No "Audio Stutter" or "Ghost Tracks" after session exit
- [x] Deep-linking from Single File to Full Practice works seamlessly
- [x] 6-stem isolation + mic input managed without bloat

**Completed:** 2026-04-22

---

### Commit 88: Versioned Database Migration Strategy

**Goal:** Implement schema migration system to prevent data loss during app updates as LessonJSON structure evolves.

**Scope:**
- Versioned migration strategy for SQLite (mobile) and IndexedDB (web)
- Migration path for skill_nodes table changes (e.g., Jazz Extensions support)
- Backward compatibility for early beta testers' practice history
- Mastery percentage preservation across schema updates

**Acceptance Criteria:**
- [x] expo-sqlite migrations implemented with version tracking
- [x] IndexedDB migration system for web parity
- [x] skill_nodes schema changes have migration path
- [x] Beta testers retain practice history after app updates
- [x] Mastery percentages preserved across schema migrations
- [x] Rollback mechanism for failed migrations

---

### Commit 89: Predictive UI Rendering

**Goal:** Eliminate visual lag perception by scrolling 50ms before audio reaches timestamp using look-ahead buffer.

**Scope:**
- Look-ahead buffer in usePitchStream hook
- Predictive scrolling for SmartScroll and AlphaTab cursor
- 50ms advance rendering for playback cursor
- Cross-platform implementation (web + native)

**Acceptance Criteria:**
- [x] Predictive scrolling implemented with 50ms look-ahead
- [x] SmartScroll scrolls 50ms before audio timestamp
- [x] AlphaTab cursor highlights notes 50ms early
- [x] Visual sync feels "intelligent" and "pro"
- [x] No perceived lag during playback

---

### Commit 90: AI Coach Variation Agents

**Goal:** Prevent feedback redundancy by varying AI coach focus areas across sessions.

**Scope:**
- Focus area parameter for Claude coach prompts
- Coach "Moods" or "Foci" system (Timing, Vibrato, Dynamics, etc.)
- Session-to-session variation in feedback emphasis
- Avoid repetitive template feedback

**Acceptance Criteria:**
- [x] Claude coach accepts focus_area parameter
- [x] 7 focus areas implemented (Timing, Vibrato, Dynamics, Phrasing, Bending, Rhythm, Expression)
- [x] Focus area varies between sessions
- [x] Feedback doesn't feel like repeated template
- [x] User feedback collection infrastructure in place

---

### Commit 91: Harmonic Similarity Discovery Agent

**Goal:** Implement song discovery based on harmonic similarity to keep users engaged in the Harmoniq ecosystem.

**Scope:**
- Harmonic similarity analysis between songs
- Discovery agent suggesting next songs based on mastered content
- Context-aware recommendations
- Integration with dynamic session engine

**Acceptance Criteria:**
- [x] Harmonic similarity algorithm implemented
- [x] Discovery agent generates song recommendations
- [x] Recommendations based on user's mastered skills/progress
- [x] UI displays discovery suggestions with context
- [x] One-tap deep-link to analyze recommended songs

---

### Commit 92: Musical Tolerance Scoring Modes

**Goal:** Implement "Musical Tolerance" setting to balance accuracy with expressive playing in scoring engine.

**Scope:**
- Expressive mode (lenient timing for musical feel)
- Technique mode (strict timing for precision practice)
- Musical tolerance configuration in scoring algorithm
- User-selectable scoring modes

**Acceptance Criteria:**
- [x] Scoring engine supports musical tolerance parameter
- [x] Expressive mode allows timing drag/push (±50-100ms tolerance)
- [x] Technique mode enforces strict timing (±20ms tolerance)
- [x] User can select scoring mode per session
- [x] Mode preference saved to user profile
- [x] Scoring feedback reflects selected mode's philosophy

---

### Commit 93: Backend API Modularization

**Goal:** Refactor the monolithic `main.py` into feature-specific routers.

**Scope:**
- `backend/app/routers/` (analyze, export, discovery, taste, curriculum)
- Centralized error handling and dependency injection
- Health checks and CORS isolation

**Acceptance Criteria:**
- [x] Backend integration tests pass after migration
- [x] No circular dependencies in router imports
- [x] Clear separation of concerns

---

### Commit 94: Automated Job Data Cleanup

**Goal:** Lifecycle management for backend temporary data to prevent storage bloat.

**Scope:**
- `backend/scripts/cleanup_data.py`
- Pruning logic for `.tmp_test_data_*` and old `data/jobs/` artifacts
- Background task or cron job for periodic execution

**Acceptance Criteria:**
- [x] Cleanup script safely removes orphaned temp folders
- [x] Configurable retention period (e.g., 7 days)
- [x] Dry-run mode for safe verification

---

### Commit 95: ML Inference Stability & Diagnostics

**Goal:** Resolve TensorFlow loading warnings and optimize inference fallback performance.

**Scope:**
- Fix `AttributeError: '_UserObject'` in `solo_inference.py`
- Improve ONNX fallback logging and performance
- Standardize model loading across chord and solo engines

**Acceptance Criteria:**
- [x] Backend logs are free of model loading warnings
- [x] Cold-start inference time reduced
- [x] Detailed diagnostics for model mismatch errors

---

### Commit 96: Unified Player UX Parity

**Goal:** Standardize the "Rich Player" card layout across all session practice screens.

**Scope:**
- Update `app/session/play.tsx` and `app/session/slow.tsx` to match `study.tsx`
- Refine `TabViewport.tsx` card padding and header alignment
- Unified "Lyrics Strip" visibility logic

**Acceptance Criteria:**
- [x] Consistent header/controls/lyrics layout across all 3 practice steps
- [x] No layout shifting when toggling lyrics or variants

---

### Commit 97: Functional Gap Closures

**Goal:** Complete pending functional requirements for orientation clips and UI state persistence.

**Scope:**
- Implement `backend/app/lyria_clip.py` for orientation hints
- Add `AsyncStorage` persistence for user preferences (`tabVariant`, `showLyrics`)
- Refine "Seek to Start" to ensure perfect audio/cursor sync

**Acceptance Criteria:**
- [x] Orient-as-hint clips generated correctly for all songs
- [x] User preferences survive app restarts
- [x] Seek-to-start resolves within 50ms transport sync

---

## Phase 2 ML: Chord Model Quality (Complete)

### Commit 98: Advanced Extension Recognition ✅ DONE

**Goal:** Upgrade the TFLite chord estimator from 25 classes (major/minor/no-chord) to 60+ chord types including 7ths, 9ths, 11ths, 13ths, and altered dominants (7#9, 7b13, alt7).

**Current State:** `build_chord_tflite.py` has only 25 classes (12 major + 12 minor + N) with synthetic 12-bin chroma templates.

**Scope:**
- Extend `CHORD_VOCAB` in `build_chord_tflite.py` with chord qualities:
  - 7th chords: dominant 7 (C7), major 7 (Cmaj7), minor 7 (Cm7)
  - Extended: 9ths (C9, Cm9, Cmaj9), 11ths, 13ths
  - Altered: 7#9, 7b9, 7#5, 7b5, alt7
  - Suspended: sus2, sus4, sus7
  - Other: dim, dim7, aug, 6, m6
- Define `CHORD_INTERVALS` mapping for all qualities
- Update `make_chroma_template()` to generate templates for extended chords including overtones
- Regenerate `chord_model.tflite` with expanded vocabulary

**Acceptance Criteria:**
- [x] Chord vocabulary expanded from 25 to 60+ classes (277 total)
- [x] `CHORD_INTERVALS` defines semitone patterns for all qualities
- [x] Synthetic templates include extended chord tones (9th=+14, 11th=+17, 13th=+21)
- [x] Model trains successfully with expanded vocabulary
- [x] TFLite conversion completes without errors
- [x] Smoke test passes for D7, Cmaj7, Am7 chord types

---

### Commit 98a: Chord Data Generation Improvements ✅ DONE

**Goal:** Enhance synthetic training data to better approximate real-world audio variability.

**Current State:** `generate_dataset()` produces clean synthetic chroma with Gaussian noise only.

**Scope:**
- Add inversion simulation: rotate chord tones so bass ≠ root (1st/2nd inversions)
- Implement missing note simulation: randomly drop chord tones to model sparse arrangements
- Add pitch-shifting augmentation: circular shift chroma bins (±1 semitone)
- Implement time-stretching: interpolate chroma frames (±10% speed variation)
- Add bass-note ambiguity: inject low-frequency energy to simulate non-root bass
- Replace Gaussian white noise with pink noise for more realistic spectral profile
- Generate chord transition samples: 50/50 mixed windows at chord boundaries

**Acceptance Criteria:**
- [x] Inversion parameter generates 1st/2nd inversion templates
- [x] Missing note dropout rate configurable (default 15%)
- [x] Pitch shift augmentation covers ±2 semitones
- [x] Time stretch factor range: 0.9x - 1.1x
- [x] Pink noise generation replaces white Gaussian noise
- [x] Transition samples improve boundary detection accuracy

---

### Commit 98b: 36-Bin CQT Feature Extraction ✅ DONE

**Goal:** Replace 12-bin chroma with 36-bin CQT (3 octaves × 12 bins) to preserve octave information for better chord discrimination.

**Current State:** Model uses 12-bin chroma which loses octave context needed for bass-note detection.

**Scope:**
- Update `CHROMA_BINS = 36` in model input shape
- Implement `librosa.cqt()` extraction with `n_bins=36, bins_per_octave=12`
- Reshape CQT: sum magnitude across octaves but preserve octave structure
- Update `make_chroma_template()` to generate 36-bin templates
- Add bass-chroma separation: low CQT bins (0-3) as separate feature channel
- Update data generation to produce 36-bin synthetic features

**Acceptance Criteria:**
- [x] Model input shape updated to `(WINDOW, 40)` (36 CQT bins + 4 bass-channel bins)
- [x] CQT extraction produces 36-bin features with octave preservation
- [x] Bass chroma (low 4 bins) separated as additional input channel
- [x] Synthetic templates generate 36-bin harmonic distributions
- [x] Training accuracy: val_acc 82.9% @ 19 epochs (85.3% train). Final model: `chord_model.tflite` (920 KB).

---

### Commit 98c: CRNN Architecture with Bidirectional LSTM ✅ DONE

**Goal:** Extend temporal context from 9 frames (~200ms) to 128+ frames (~2.5-6s) and add recurrent layers for chord progression modeling.

**Current State:** Shallow CNN with only 9-frame window cannot model chord progressions or temporal dependencies.

**Scope:**
- Increase `WINDOW` from 9 to 128 frames (configurable 64-256)
- Add CNN frontend: Conv1D(64) → MaxPool → Conv1D(128) → MaxPool
- Insert Bidirectional LSTM layers after CNN:
  - `Bidirectional(LSTM(128, return_sequences=True))`
  - `Bidirectional(LSTM(128, return_sequences=False))`
- Add Dropout(0.3) between recurrent layers
- Update `build_model()` to return CRNN architecture
- Ensure TFLite compatibility with SELECT_TF_OPS

**Acceptance Criteria:**
- [x] Model accepts 128-frame temporal windows
- [x] CNN frontend reduces temporal resolution before LSTM
- [x] Bidirectional LSTM layers capture forward and backward dependencies
- [x] TFLite conversion succeeds with recurrent layers[^1]
- [ ] Inference latency <100ms on target mobile device (requires mobile benchmarking)
- [x] Validation accuracy: 82.9% @ 19 epochs (up from ~55% shallow CNN epoch 6 baseline). Improvement inline with +8% target.

[^1]: Conversion uses `SELECT_TF_OPS` for LSTM ops. Inference requires Flex delegate (`org.tensorflow:tensorflow-lite-select-tf-ops`) on Android.

---

### Commit 98d: Multi-Head Self-Attention Mechanism ✅ DONE

**Goal:** Add attention layers to let model focus on salient harmonic peaks in chroma features.

**Current State:** No attention mechanism; model treats all chroma bins equally.

**Scope:**
- Add `MultiHeadAttention(num_heads=4, key_dim=64)` after CNN frontend
- Implement attention masking for valid sequence positions
- Add LayerNorm after attention block
- Update model architecture: CNN → Attention → LSTM → Dense
- Verify TFLite conversion compatibility with attention ops

**Acceptance Criteria:**
- [x] Multi-head attention attends to chroma bin relationships (4 heads, key_dim=64)
- [x] Attention weights visualizable via `build_attention_vis_model()` for interpretability
- [x] TFLite conversion includes attention ops (SELECT_TF_OPS enabled)
- [x] Model size: 1.1MB (within acceptable range for mobile deployment)
- [x] Accuracy improvement on extended chords: 81.3% (triad: 88.9%, overall: 81.4%, val_acc: 82.3%)

---

### Commit 99: Viterbi Decoding for Chord Progressions ✅ DONE

**Goal:** Post-process frame-wise predictions with Viterbi algorithm to enforce plausible chord transitions and smooth sequences. Add chord stability metrics and a beat-alignment validation gate.

**Current State:** No post-processing; frame-wise predictions can flicker between chords. No metrics exist to measure chord-change stability or beat alignment quality. The only smoothing is a 3-neighbor median filter (`_smooth_chords`). Viterbi decoding, transition matrices, beat-alignment gates, and half-beat chord change resolution are not implemented.

**Scope:**
- Build transition probability matrix from training data (60×60 for extended vocab)
- Implement Viterbi decoder in Python for backend post-processing
- Add log-probability computation for soft-max outputs
- Implement backtracking for optimal path reconstruction
- Integrate into chord inference pipeline after TFLite inference
- Add transition matrix caching for performance
- Add chord flicker detection metric: rate of adjacent-beat chord changes (target <5%)
- Add beat-alignment gate: measure % of chord changes on downbeats/beats from the `beat_grid`
- Add chord-change rate histogram per-song for quality reporting
- Enforce >90% beat-boundary alignment target with CI gate
- Add key-constrained transition costs: prefer diatonic chord movements in detected key
- Implement duration-aware filtering: chords lasting <1 beat penalized unless transition
- Add half-beat (8th-note) chord change resolution: when the beat grid provides subdivided beats or the per-beat confidence-weighted vote reveals a tight tie between two different chords (confidence difference <0.15), emit two `ChordEvent`s per beat (one per half-beat) instead of one

**Acceptance Criteria:**
- [x] Transition matrix computed from real chord progression data
- [x] Viterbi decoder produces smoothed chord sequences
- [x] Decoding latency <10ms for 30-second audio
- [x] Reduced chord flickering in predictions (target: 40% reduction)
- [x] Integration test with known chord progression (e.g., ii-V-I)
- [x] Viterbi decreases chord flicker rate to <5% (chord changes every 1-2 beats filtered)
- [x] Beat-alignment gate measures >90% of chord changes landing on beat/downbeat boundaries
- [x] Chord-change rate histogram reportable per-song in analysis metadata
- [x] Duration-aware filtering suppresses sub-1-beat chord outliers
- [x] Key-constrained transition costs reduce improbable chord movements (e.g., C → F#)
- [x] Chord timeline supports half-beat resolution: when 8th-note subdivisions are active, two chord events emitted per beat with correct timestamps
- [x] Beat-subdivision tie-detection: two competing chords within a single beat window with confidence difference <0.15 triggers half-beat split

---

### Commit 102: Threshold Sensitivity Analysis & Label Noise Robustness (MT3 Paper Insight) ✅ DONE

**Goal:** Run threshold sensitivity analysis on the validation set to detect label timing noise, then add temporal jitter augmentation to make the model robust to imperfect ground truth — following MT3's Appendix D.2 methodology.

**Rationale (from MT3 paper, Appendix D.2):** The paper systematically varied the onset-offset tolerance from 10ms to 500ms and found that datasets with noisy labels (MusicNet, URMP) had F1 scores that kept climbing past 50ms — revealing significant timing errors in ground truth. Our synthetic training data likely has similar alignment issues. If the model learns from smeared temporal boundaries, it will produce smeared predictions.

**Current State:** No label quality analysis exists. Training assumes ground truth timing is accurate. No temporal jitter augmentation is applied during training.

**Scope:**
- Build `analyze_label_noise.py` script:
  - Compute chord F1 at tolerances [10ms, 25ms, 50ms, 100ms, 200ms, 500ms]
  - Plot F1 vs tolerance curve for each validation subset
  - If F1 keeps climbing past 50ms → labels have timing noise
  - Report per-chord-type noise sensitivity (extended chords may be noisier)
- Add temporal jitter augmentation to training pipeline:
  - Randomly shift chord boundaries by ±30ms during training
  - Apply to both real and synthetic training data
  - Model learns to be robust to label timing uncertainty
- Add label quality gate to dataset ingestion:
  - Reject training examples with boundary jitter >100ms
  - Flag borderline examples for manual review

**Acceptance Criteria:**
- [x] Threshold sensitivity analysis script produces F1-vs-tolerance curves
- [x] Label noise report identifies which dataset subsets have timing issues
- [x] Temporal jitter augmentation (±30ms) active during training
- [x] Model accuracy on noisy-label validation set improves by ≥3%
- [x] Label quality gate rejects examples with >100ms boundary jitter
- [x] Analysis results documented in `docs/LABEL_QUALITY.md`

---

### Commit 100: Segment Boundary Tie Mechanism (MT3 Paper Insight) ✅ DONE

**Goal:** Eliminate chord/note transcription errors at segment boundaries by implementing an overlap-and-blend strategy with active-note tracking — inspired by MT3's "tie" mechanism that declares which notes are already active at the start of each segment.

**Rationale (from MT3 paper, Section 3.2):** MT3 solves the "forgotten note" problem by requiring the model to emit a "tie section" at the beginning of each segment declaring active notes. Notes not re-declared in the next segment are gracefully ended. Our TFLite chord model (128-frame sliding window) and Basic Pitch process segments independently with no cross-segment state, causing onset/offset errors at boundaries that directly corrupt scoring (`_score_timing()` in `score.py`).

**Scope (completed):**
- ✅ 50% overlap-and-blend for chord inference windows — `_window_layout()` + `_predict_overlap_blend()` in `chord_inference.py`: windows placed every `_WINDOW_STRIDE` (64 = 50%) frames, per-frame predictions accumulated with triangular weights (`1 - |f − center| / half`), argmax after weight-normalized blending. Frames in the overlap zone are dominated by the window holding them near its center (MT3-style cross-window state)
- ✅ Active-note tie mechanism for Basic Pitch — `merge_segments_with_ties()` in `solo_inference.py`: active-note table (keyed by pitch) carried across segment boundaries; same-pitch onset within `TIE_WINDOW_S` (0.15s) of the previous end = re-declaration → tied into a single note; notes never re-declared survive from first detection ("forgotten note" fixed); `_infer_segmented()` splits long tracks (≥60s) into overlapping segments (15s overlap) with temp-WAV per-segment transcription
- ✅ Boundary confidence penalty — `_apply_boundary_penalty()` scales confidence ×0.85 for raw frames within 2 frames of track edges; `_dampen_boundary_onsets()` velocity-dampens fresh onsets within 0.2s after segment boundaries
- ✅ Boundary tie telemetry — `blend_windows`, `boundary_frames_penalized`, `edge_flicker_events` merged into `infer_chords()` metrics; segmented solo stats logged per job
- ✅ Unit tests — `tests/test_boundary_ties.py` (17 tests): chord held across boundary → single event, forgotten-note survival, distinct attacks never merged, boundary penalty zones, edge-flicker counting, blend disagreement resolution, segment geometry, plus 2 mocked-ML end-to-end segmented tests

**Acceptance Criteria:**
- [x] Overlap-and-blend reduces boundary chord flicker by ≥50% — per-frame argmax stable across overlap zones (verified: blend resolves window disagreement, changes only at intended midpoints; `edge_flicker_events` metric per job)
- [x] Active-note tracking prevents "forgotten note" offsets in solo transcription — `merge_segments_with_ties()` + end-to-end test (`test_infer_solo_segmented_forgotten_note_survives`)
- [x] Boundary confidence penalty reduces false positives at segment edges — chord edge confidence ×0.85; solo fresh-onset velocity ×0.85
- [x] Scoring timing errors decrease for notes held across boundaries — tied notes span boundaries as ONE quantized event (single start/end), removing duplicate/truncated onsets that feed `_score_timing()`
- [x] Unit test: chord held across boundary → single event emitted — `test_chord_held_across_boundary_is_single_event` (+ blend-disagreement test for chord windows)
- [x] No regression on within-segment prediction accuracy — single-pass path unchanged for tracks ≤60s; `test_inference_logic.py` chord/solo truncation tests pass; CI suites (`test_jam_score`, `test_score`, `test_viterbi`) 77/77 passing

---

### Commit 101: Real Dataset Integration (GuitarSet + Isophonics) ✅ DONE

**Goal:** Train on real annotated audio instead of purely synthetic data to improve real-world accuracy.

**Current State:** ✅ Model now trains on 70% real windows mixed with temperature-sampled synthetic batches; real test-set root accuracy 66.1% on a completely unseen guitarist (Commit 103 build; 63.7% at Commit 101 time) — **+54.4 pts over the synthetic-only baseline (9.3%)** on the same split, same seed. Official Isophonics downloads were pulled by the university, so Isophonics content is fetched as YouTube audio matched to the original `.lab` annotations by duration; GuitarSet (the only freely-licensed corpus with *guitar comp* audio + chord annotations) became the primary source.

**Scope:**
- Download Isophonics-annotated audio (Beatles/Queen via YouTube, duration-matched to lab spans) ✅
- Download + prep GuitarSet (180 tracks, all players, no artist overlap in splits) ✅
- Write preprocessing script to extract 40-dim CQT and align with chord labels ✅
- Convert annotations to extended chord vocabulary (map rare qualities to closest match) ✅
- Combine real + synthetic data (70/30 split recommended) ✅
- Add dataset mixing + real-window evaluation to training pipeline ✅

**Acceptance Criteria:**
- [x] Isophonics dataset loaded and preprocessed (180 GuitarSet + 2+ Isophonics-YouTube tracks cached, gated, in manifest)
- [x] CQT features extracted and aligned with chord labels (`prepare_real_datasets.py prep`, 54,936 usable frames)
- [x] Train/val/test split with no artist overlap (train: players 00/01/02/04 + Beatles; val: 05; test: 03)
- [x] Real data comprises 70% of training batches (`--real-ratio 0.7`, verified by `make_mixed_batch` test)
- [ ] Open roadmap item (not archived): >75% root accuracy on Isophonics test set — 66.1% as of Commit 103; tracked in PRIORITIES.md status line

---

### Commit 103: Training Infrastructure Improvements ✅ DONE

**Goal:** Add proper training callbacks, augmentation, and evaluation metrics.

**Current State:** Only 12 epochs, no callbacks, no validation metrics beyond accuracy.

**Scope:**
- Add `EarlyStopping` callback (patience=5, restore_best_weights)
- Add `ReduceLROnPlateau` callback (factor=0.5, patience=3)
- Implement time-stretch augmentation in training loop
- Add pitch-shift augmentation (±2 semitones)
- Generate confusion matrix during validation
- Compute per-class precision/recall/F1 metrics
- Add class weighting to handle chord imbalance
- Increase training epochs from 12 to 50

**Acceptance Criteria:**
- [x] Early stopping prevents overfitting
- [x] Learning rate reduces automatically on plateau
- [x] Time stretch and pitch shift augmentations active
- [x] Confusion matrix identifies confused chord pairs
- [x] Per-class metrics reveal rare chord performance
- [x] Training completes in <2 hours on available hardware

**Status (Commit 103 build, 2026-08-13):**
- **Shipped model:** augment-only 50-epoch run (seed 42, callbacks on, real_ratio 0.7, class weights off) — val root **0.664** @ epoch 22 (early-stopped e27), test root **0.661** / full **0.638** on unseen guitarist 03, smoke test PASS (threshold 0.50). Confusion pairs now G↔C/F↔C/4ths; min F1 0.729. Run completed in 52 min (<2 h budget).
- **Class weighting investigated, disabled for the shipped model:** real-window inverse-frequency weights (`class_weight_map`, applied to real samples only — synthetic already temperature-balanced; the initial version applied them to synthetic too and double-boosted rare classes, collapsing val root to 0.36) improve rare-quality F1 (dim 0.583, 7 0.658, min 0.679) but cost ~7 pts top-line (test root 0.589). Both paths verified by `tests/test_real_dataset.py` (54 passing).

---

## Product Milestones (Complete)

### Milestone: User Feedback & Manual Overrides ✅ DONE

System to tag and save manual tab corrections to refine ML confidence levels.

**Scope (completed):**
- ✅ UI for users to mark incorrect notes/chords — ChordCorrectionDropdown, NoteCorrectionSheet integrated into study.tsx
- ✅ Backend persistence of corrections — PATCH endpoints for chord/solo-note/voicing corrections, history tracking, revert support
- ✅ ML retraining pipeline — `backend/scripts/prepare_retraining_data.py` consumes exported corrections and generates augmented training data
- ✅ Correction history panel in review screen
- ✅ Type consolidation into `src/types/index.ts`
- ✅ Backend tests: 20 passing tests covering all correction endpoints and retraining pipeline

---

### Milestone: Lick Library Persistence ✅ DONE

Full CRUD for saved phrases and "Drill This" micro-session logic.

**Scope (completed):**
- ✅ SQLite schema for saved licks — v1 `licks` table with full CRUD (create, read, update via re-save, delete)
- ✅ UI for browsing, tagging, and organizing licks — `app/(tabs)/library.tsx` (581 lines) with search, filter, technique tags, transpose controls
- ✅ "Drill This" generates focused micro-sessions — `drill()` function converts lick to synthetic LessonJSON via `lessonFromSavedLick()` and navigates to `/session/study`
- ✅ Save to Library button on Review screen
- ✅ Home screen integration via `homeSuggestionFromLicks.ts`
- ✅ DNA/Progress integration via `dnaStore.ts` and `dnaComputer.ts`

---

### Milestone: Jam Mode Summary Agent ✅ DONE

Claude-powered post-jam analysis and vocabulary mapping.

**Scope (completed):**
- ✅ Post-jam analysis endpoint — `POST /jam/summary` with Claude integration + deterministic fallback
- ✅ Vocabulary pattern detection — `backend/app/jam_vocabulary.py` (motifs, sequences, arpeggios, scale runs, bend figures, repeated notes)
- ✅ Claude integration for summary generation — `coach.py` with streaming, circuit breaker, fallback
- ✅ Model-to-coach JSON bundle schema — `JamSummaryBundle` with clarity, intonation, timing, transitions, vocabulary patterns
- ✅ Persona-switching via system prompt — learner/intermediate/transcriber personas
- ✅ Frontend API client — `submitJamSummary()` in `src/api/jam.ts`
- ✅ Backend tests — 14 passing tests covering vocabulary detection, endpoint, fallback, personas
- ✅ Persist phrase data in jam snapshot (device-side)
- ✅ Wire jam summary into jam.tsx "Stop & Save" flow
- ✅ Display rich summary in progress timeline and jam history

---

## Phase 3 SWE: Full-Stack Features (Complete)

### Commit 108: Beat Grid Editor (UI + Recomputation) ✅ DONE

**Goal:** Add frontend UI for editing time signature and BPM per section, with a backend recomputation endpoint that re-derives dependent artifacts (chord timeline, solo notes, MusicXML).

**Current State:** The backend accepts `time_signature_override` and `bpm_override` on `POST /transcription/prepare`, but no frontend UI calls this endpoint. No standalone recompute endpoint exists. Beats and downbeats display read-only in the app with no editing capability.

**Scope:**
- Build beat grid visualization component: horizontal timeline showing beat markers, downbeat highlights, and bar lines overlaid on the waveform or tab area
- Add time signature editor: picker for numerator (2, 3, 4, 6, 12) and denominator (4, 8) per song section
- Add BPM editor: numeric input or slider with fine/coarse adjustment per section
- Create `POST /analyze/{job_id}/beat-grid/recompute` backend endpoint:
  - Accept `time_signature` and/or `bpm_override` per section
  - Re-run `estimate_beat_grid()` with overrides
  - Call `dependent_artifacts_for_grid_override()` → flag `chordTimeline`, `SoloNotes`, `Score.musicxml`
  - Re-run chord inference on updated beat grid (chord frame pooling on new beat boundaries)
  - Re-run solo inference duration quantization on updated tempo
  - Rebuild MusicXML with updated beat grid, chords, and solo
  - Return updated `BeatGrid`, `ChordTimeline`, `SoloNotes`, and `musicxml`
- Add recompute progress reporting: job-like status (`pending → recomputing_chords → recomputing_solo → rebuilding_musicxml → complete`)
- Wire frontend editor to recompute endpoint with loading overlay
- Persist beat grid overrides in job state so they survive page navigations
- Add "Reset to Auto" button to revert overrides to librosa-estimated values
- Add undo/redo for beat grid edit history during a session
- Fix `pipeline_prof.py` bar_timestamps to derive `beats_per_bar` from the `BeatGrid.time_signature` instead of hardcoding `beats_per_bar = 4`

**Progressive delivery — apply the same pattern to the initial `POST /analyze` flow:**
- Extend `JobStatus` schema to include an `analysis_stage` enum field (`"initializing"`, `"stems_separating"`, `"chords_inferring"`, `"solo_inferring"`, `"building_musicxml"`, `"complete"`)
- Refactor `_process_analyze_job()` in `jobs.py` to set `JobStatus.result` multiple times during processing:
  - Set initial (empty) `result` when job starts
  - Set `result` with `chord_timeline` populated when chord inference finishes (stage: `"chords_inferring"`)
  - Set `result` with `chord_timeline` + `solo_notes` when solo inference finishes (stage: `"solo_inferring"`)
  - Set final full `LessonJSON` when MusicXML is built (stage: `"complete"`)
- Persist intermediate artifacts (chord timeline, solo notes) to disk as they complete, so partial results survive server restarts
- Build frontend `ChordChartPreview` component that renders when `analysis_stage >= "chords_inferring"`:
  - Shows chord chart with timeline over waveform region
  - Displays smaller spinner banner: "Refining solo notation..."
  - Replaces monolithic add-song loading spinner with progressive reveal pattern
- Wire `analysis_stage` into the polling response so frontend can conditionally render partial results
- Keep coach hydration as a separate async track (no regression)

**Acceptance Criteria:**
- [x] Beat grid timeline visualizes beats (ticks), downbeats (accented), and bar lines
- [x] Time signature picker supports 2/4, 3/4, 4/4, 6/8, 9/8, 12/8 with correct subdivision
- [x] BPM adjustment per-section recomputes beat spacing in real-time preview
- [x] `POST /analyze/{job_id}/beat-grid/recompute` triggers full dependent artifact chain
- [x] Chord timeline re-pooled on new beat boundaries after time sig change
- [x] Solo durations re-quantized after BPM change
- [x] MusicXML rebuilt with updated time signature, BPM, chords, and solo
- [x] `bar_timestamps` computed from actual time signature (not hardcoded 4/4)
- [x] Frontend polls recompute progress and updates all displays on completion
- [x] Overrides persist across page navigations in the same session
- [x] "Reset to Auto" restores librosa-estimated grid
- [x] Test: 4/4 → 6/8 time signature change correctly recomputes chord beat alignment
- [x] Initial `POST /analyze` returns chord timeline as partial result before solo inference finishes
- [x] `JobStatus.analysis_stage` enum reported in every poll response during processing
- [x] Frontend renders chord chart preview when `analysis_stage >= "chords_inferring"` (before full completion)
- [x] Intermediate artifacts survive server restart (persisted to disk)
- [x] Monolithic loading spinner replaced with progressive reveal (chords first, then solo, then full score)
- [x] Coach hydration remains separate and non-regressed

---

### Commit 109: Analysis Persistence & Correction Editor ✅ DONE

**Goal:** Persist machine-readable analysis outputs (chord timeline, solo notes, beat grid) to a database backend and add a frontend editor for correcting chord assignments, note parameters, and fret positions.

**Current State:** Analysis outputs are held in an in-memory `jobs` dict that does not survive server restarts. No editing capability exists anywhere in the frontend — the fretboard and chord timeline display analysis data read-only. The `User Feedback & Manual Overrides` milestone exists but lacks concrete implementation.

**Scope:**
- Replace the in-memory `jobs` dict with SQLite (or filesystem JSON store) backed by versioned schema
- Add migration support for analysis schema changes
- Add chord correction endpoint `PATCH /analyze/{job_id}/chord/{beat_index}`:
  - Accept new chord symbol (e.g., "G7", "F#m7")
  - Persist correction alongside original prediction with timestamp
  - Flag corrected chords so downstream consumers can distinguish from ML output
- Add note correction endpoint `PATCH /analyze/{job_id}/solo-note/{note_index}`:
  - Accept overrides for pitch (MIDI), start_time, duration, velocity
  - Persist corrected notes with original values preserved
- Add voicing override endpoint `PATCH /analyze/{job_id}/chord/{beat_index}/voicing`:
  - Accept alternative CAGED shape label (E-shape, A-shape, etc.)
  - Store voicing preference for fretboard rendering
- Build frontend chord correction UI:
  - Tap chord symbol on timeline → dropdown of alternatives filtered by detected key
  - Inline replace with visual confirmation
- Build frontend note correction UI:
  - Tap note on fretboard or tab → note detail card with pitch, string, fret editors
  - Real-time preview of correction on fretboard
- Build voicing selection UI:
  - Chord detail panel shows alternative voicings; tap to preview on fretboard
  - Selected voicing persists for that chord in the song
- Add correction history display with ability to revert individual corrections
- Ensure fretboard sync and MusicXML export reflect corrections immediately
- Add `correction_count` and `correction_coverage` metrics to LessonJSON metadata
- Wire corrections to the Phase 4 ML retraining pipeline (export corrections as training data)

**Acceptance Criteria:**
- [x] Analysis outputs persist across server restarts (SQLite or filesystem)
- [x] Chord symbol correction endpoint accepts valid chord and persists it
- [x] Solo note endpoint accepts pitch/duration/string/fret overrides
- [x] Voicing endpoint stores alternative CAGED shape per chord
- [x] Frontend chord correction dropdown filtered by key
- [x] Frontend note correction with real-time fretboard preview
- [x] Correction history tracks original vs. corrected with revert capability
- [x] MusicXML export uses corrected data
- [x] Fretboard sync reflects corrections immediately during playback
- [x] Correction coverage metric (% of ML-predicted events that were corrected) available
- [x] Corrections exportable as training data for ML retraining

---

## Phase 4 ML Rigor: Advanced Training (Complete)

### Commit 104: Temperature Sampling for Chord Type Imbalance (MT3 Paper Insight) ✅ DONE

**Goal:** Apply MT3's temperature sampling strategy `(n_i / Σn_j)^0.3` to oversample rare chord types during training, ensuring extended jazz chords (7#9, alt7, dim7, aug) get adequate training signal.

**Rationale (from MT3 paper, Section 3.3):** MT3 uses temperature sampling to balance high- and low-resource datasets, dramatically improving performance on low-resource instruments (guitar: +263% Onset-Offset F1). Our 277-class vocabulary includes many rare chord types that are underrepresented in training data. Without balanced sampling, the model defaults to maj/min predictions for ambiguous cases.

**Current State:** Training data is sampled uniformly. Extended chord types (7#9, alt7, dim7, aug, 13th chords) are rare in both synthetic and real datasets, leading to poor recall on these classes.

**Scope:**
- Analyze training set chord type distribution:
  - Count examples per chord quality across all datasets
  - Identify chord types with <5% of average representation
- Implement temperature sampling in data loader:
  - Apply `(n_i / Σn_j)^0.3` to chord type frequencies
  - Oversample rare types, undersample common types (maj, min)
  - Configurable temperature parameter (default 0.3, matching MT3)
- Add per-chord-type recall tracking during validation:
  - Report recall for each of the 277 classes
  - Flag classes with recall <0.3 for targeted data collection
- Add "rare chord boost" mode:
  - Temperature = 0.1 for aggressive oversampling of rare types
  - Use during fine-tuning phase after initial convergence

**Acceptance Criteria:**
- [x] Chord type distribution analysis report generated
- [x] Temperature sampling implemented with configurable exponent
- [x] Rare chord type (7#9, alt7, dim7, aug) recall improves by ≥15%
- [x] Common chord type (maj, min) accuracy degrades by <2%
- [x] Per-chord-type recall reported during validation
- [x] Temperature parameter tunable via training config

**Implementation:** `backend/scripts/build_chord_tflite.py` — `compute_temperature_weights()`, `compute_samples_per_quality()`, `compute_per_class_recall()`, `compute_rare_chord_metrics()`. Real-world chord distribution loaded from `data/annotations/chord_distribution.json` (35,613 annotated chords). CLI args: `--temperature 0.3`, `--no-temperature`, `--epochs 20`.

---

### Commit 105: Quantization-Aware Training ✅ DONE

**Goal:** Improve TFLite quantization accuracy by training with quantization constraints rather than post-training quantization.

**Current State:** Post-training quantization may degrade accuracy for extended chord vocabulary.

**Scope:**
- Integrate `tensorflow_model_optimization` toolkit
- Apply `quantize_model()` wrapper to training model
- Implement QAT (Quantization-Aware Training) for 4-5 epochs
- Compare accuracy vs post-training quantization baseline
- Generate INT8 quantized model for mobile deployment

**Acceptance Criteria:**
- [x] QAT model trained with simulated quantization
- [x] INT8 quantized model produced
- [x] Accuracy degradation <3% vs float32 model
- [x] Model size <500KB after quantization
- [x] Inference latency reduction confirmed on mobile device

**Implementation:** `backend/scripts/build_chord_tflite.py` — `run_pipeline(use_qat=True)` wraps model with `tfmot.quantization.keras.quantize_model()`. CLI arg: `--qat`. Tests in `backend/tests/test_qat.py`.

---

### Commit 106: Solo Rhythm Quantization & Measure-Level Sanity ✅ DONE

**Goal:** Quantize solo note durations to standard notation types (quarter, eighth, sixteenth, triplet) and add measure-level rhythmic sanity checks to the MusicXML builder.

**Current State:** Solo note durations were grid-snapped in seconds but not quantized to standard note types. The MusicXML builder used a hardcoded 8th-note grid (`round(... * 8) / 8`) with no measure overflow validation, tied notes produced duplicate `<notations>` blocks, `<divisions>` lacked a stable LCM-anchored reference, and minor keys collapsed to major (C major and A minor both = 0 sharps).

**Scope (completed):**
- ✅ New pure module `app/rhythm_quantization.py` (no music21 dependency, exact Fraction arithmetic):
  - `tick_to_quarter_fraction()` — float beat-grid `tick_value` (e.g. 0.25) → exact `Fraction` (1/4)
  - `quantize_seconds_to_ql()` — variable-resolution tick quantization replacing `round(*8)/8`; tuplet-aware: plain ticks plus 3-in-2, 5-in-4, 6-in-4, 6-in-2 tick positions are candidates and the nearest wins, so triplet/quintuplet durations survive instead of collapsing to the nearest 16th
  - `quantize_to_note_type()` — whole→64th standard types, dotted variants (3/2, 7/4), tuplet shapes; exact match by default, optional tolerance; equal-error ties prefer simpler rhythms (fewer dots, then smaller tuplet numerator)
  - `nearest_grid_index()`, `split_note_into_measures()` — per-measure segments for notes spanning barlines
- ✅ `musicxml_builder.py` — all four duration sites (note, pre-note rests, measure final rest, tie-continuation segments) quantized on the beat tick grid via `_apply_rhythm()`, which assigns explicit `<type>`/`<dot>`/`<time-modification>` elements (triplets render as `3-in-2` tuplets, 4/5 ql as `5-in-4`); tie-queue segment math fixed to duration-additive (multi-tie measures no longer mis-compute cumulative positions); `_add_technical_elements()` regex now detects an existing `<notations>` (tied notes carry `<tied>` there) and merges `<technical>` into the single block — no more duplicate `<notations>`; `_normalize_divisions()` rescales `<divisions>` to `lcm(480, X)` of music21's LCM (480 in the common binary-only case, 10080 when triplets are present) and injects an `<attributes>/<divisions>` block into every measure lacking one; minor-key parsing via `music21.key.Key("A minor")` with legacy split fallback
- ✅ `solo_inference.py` — amplitude-based polyphonic→monophonic selection: raw basic-pitch notes grouped by beat slot (`nearest_grid_index` over `beat_grid.beats`), strongest velocity per slot with highest-MIDI-pitch tie-break (mirrors `build_gp5_from_note_events()` at `pipeline_proof.py:531-544`); chronological truncation remains the fallback for multi-slot overlap; velocity normalization to MIDI 40–120 preserved
- ✅ Test suite — `tests/test_rhythm_quantization.py` (17 tests): tick math, plain-tick/tuplet-position/syncopation seconds quantization, note-type inference (plain, dotted, tuplets incl. 5-in-4, tolerance, invalid), grid snapping, measure splitting; `test_inference_logic.py`: per-slot collapse, pitch tie-break, lone micro-note preserved at min-tick duration; `test_exporter.py`: 16th/dotted `<type>`/`<dot>` rendering, triplet `<time-modification>` (3/2), quintuplet via 1/5 tick grid, divisions multiple of 480 + per-measure `<attributes>`, tied note single `<notations>` with both `<tied>` and `<technical>`, minor-key `<mode>minor</mode>`

**Acceptance Criteria:**
- [x] Note durations quantized to standard types (whole through 64th) with correct `<type>` elements
- [x] Triplet detection correctly groups 3-in-the-time-of-2 patterns — `3-in-2` `<time-modification>` verified in exporter test
- [x] Measure fill validation: total note+rest duration equals measure length within 1-tick tolerance — tick-grid cumulative accounting + final-rest fill, verified in dotted/16th test
- [x] Measure overflow clips notes at bar line and ties to next measure — tie queue start/continue/stop segments across barline, verified in tied-note exporter test
- [x] Unfilled measure time produces rests at beat/sub-beat boundaries (not arbitrary positions) — rests quantized on the same tick grid
- [ ] `<beam>` groupings follow beat structure (no cross-beat beams) and tuplet groups — **deferred**: music21 emits default beams; custom beat-structured beam grouping folds into Commit 107's notation completeness ("Beams grouped by beat and tuplet structure from Commit 106", still scoped there)
- [x] `infer_solo()` selects at most one note per beat slot, preferring highest amplitude (matching `build_gp5_from_note_events` behavior)
- [x] Test suite covers syncopation, triplets, 5-tuplets, dotted quarters, and maximal/minimal durations — unit-level 64th/whole (min/max) via `quantize_to_note_type`; exporter-level 16th, dotted quarter/eighth, triplet, quintuplet; syncopation quantization unit test
- [x] Existing solo duration filtering (sub-32nd note removal) remains active and non-regressed — duration filter unchanged; lone micro-note survivors keep min-tick duration in their own slot
- [x] `_add_technical_elements()` produces valid XML when notes have `<tie>` — single `<notations>` contains both `<technical>` and `<tied>` (verified in exporter test)
- [x] `<divisions>` present in every measure's `<attributes>` — anchored at 480 when rhythms are binary, LCM-rescaled (480-multiple, e.g. 10080) when triplets exist so durations stay integral; AlphaTab consumes per-measure `<attributes>`
- [x] Minor key signatures generate correct MusicXML — `"A minor"` → `<key><fifths>0</fifths><mode>minor</mode></key>` (verified in exporter test)

**Verification:** full backend suite 519 passed / 2 skipped; CI-scoped `test_jam_score.py` + `test_score.py` green on the final build.

**Implementation:** `app/rhythm_quantization.py` (new, pure), `app/musicxml_builder.py` (quantized sites, `_apply_rhythm`, notations merge, `_normalize_divisions`, key parsing), `app/solo_inference.py` (per-slot selection). Tests: `tests/test_rhythm_quantization.py` (new), `tests/test_inference_logic.py`, `tests/test_exporter.py`.

---

### Commit 107: MusicXML as Primary Render Format ✅ DONE

**Goal:** Switch the frontend from GP5-based AlphaTab rendering to MusicXML-based rendering, making MusicXML the canonical render format for chord symbols and solo notation as declared in the product spec.

**Current State:** MusicXML is the active render path — the analysis pipeline emits a DTD-valid MusicXML 3.1 score, persists it as `score.musicxml`, the prerender step renders SVGs from it, and both web (DOM AlphaTab) and native (WebView AlphaTab) render it, with GP5 as fallback for legacy lessons. Edge-case corpus (24 files), DTD validation, cross-platform render suites, and a limitations doc are all in place. (Frontend rendering path landed first in `94412af`; corpus/validation/suites/docs landed in the closing commit.)

**Scope (completed):**
- ✅ AlphaTab WebView harness (`assets/alphatab-harness/`), `AlphaTabWeb.web.tsx`, and native `AlphaTabWebView.tsx` accept MusicXML as primary input (`api.loadMusicXML()`), GP5 as fallback; web banner fixed so MusicXML-only payloads no longer show "Tab preview isn't available"
- ✅ `musicxml_builder.py` notation completeness — dynamics, articulations, slurs (spanned elements across barlines), beams, chord diagrams (`<frame>`), parallel TAB staff, `<defaults>` (`<scaling>` 7mm/40 tenths, `<page-layout>`, `<system-layout>`)
- ✅ `LessonJSON` schema — `musicxml` primary field; top-level `beat_grid` (legacy list-typed union), `chord_timeline`, `solo_notes`; GP5 artifacts export-only; `jobs.py` persists `score.musicxml` standalone in job dir (`or None`, never empty)
- ✅ `alphatab_prerender.py` + `.mjs` render SVGs from MusicXML with GP5 fallback; `score_sha256_from_musicxml`
- ✅ MusicXML 3.1 Partwise DTD validation (vendored `tests/fixtures/musicxml-dtd/`; corpus + exporter tests fail on invalid XML)
- ✅ Edge-case corpus — 24 files (`tests/fixtures/musicxml-corpus/`, generator `scripts/generate_musicxml_corpus.py`): irregular time sigs, nested tuplets, polyrhythms, tempo changes, multi-voice staves, ties/slurs; Node AlphaTab no-crash gate (`scripts/alphatab_corpus_check.mjs` + `test_musicxml_corpus.py`)
- ✅ Cross-platform render suites — web Playwright `tests/ui/musicxml-render.spec.ts` (4 tests, visual baselines `tests/ui/__snapshots__/`); native Detox scaffold `tests/mobile/musicxml-render.e2e.js`; hidden route `app/(tabs)/musicxml-render-test.tsx` with corpus assets bundled (`src/lib/corpusAssets.ts`, metro `assetExts`)
- ✅ `docs/ALPHATAB_MUSICXML_LIMITATIONS.md` (living doc), README updated

**Acceptance Criteria:**
- [⚠️] Native WebView harness renders MusicXML on Android — harness, route, and Detox suite implemented; suite not green yet: the prebuild-generated `android/` lacked Detox wiring (`:detox` project, `testInstrumentationRunner`, `androidTestImplementation`) so the test instrumentation never started. Completed by **Commit 108 (Mobile E2E Fix)**. iOS uses the same `AlphaTabWebView.tsx` path — requires a macOS sim run (`npm run test:mobile:ios`)
- [✅] Chord symbols render as `<harmony>` elements in the score (exporter test + corpus `harmony` cases)
- [✅] Solo notation renders with correct note types, beams, rests, and ties across measures (exporter tests + corpus `ties-and-slurs`, `rest-heavy`)
- [✅] Tablature staff appears below standard notation staff with correct string/fret (P2 part, TAB clef)
- [✅] Chord diagrams (`<frame>`) display inline with chord symbols (harmony + frame in exporter tests)
- [✅] Dynamics, articulations, and slurs present in generated MusicXML and render in AlphaTab
- [⚠️] GP5 artifacts removed from primary `LessonJSON` schema; exported-only — explicit `musicxml` field added to schema
- [✅] AlphaTab prerender produces SVGs from MusicXML input (`alphatab_prerender.py` + `.mjs` accept `musicxml` with GP5 fallback; `score_sha256_from_musicxml`)
- [✅] Existing export flows (MusicXML download, GP5 download) continue to work (backend regression green)
- [✅] README updated (MusicXML = active canonical render path, limitations doc linked)
- [✅] `data/jobs/{job_id}/score.musicxml` written as standalone file during analysis
- [✅] `<defaults>` block present in MusicXML output with `<scaling>`, `<page-layout>`, and `<system-layout>`
- [✅] CI validates every MusicXML output against MusicXML 3.1 Partwise DTD (vendored `tests/fixtures/musicxml-dtd/`; corpus + exporter tests fail on invalid XML)
- [✅] `LessonJSON` schema has top-level `beat_grid`, `chord_timeline`, `solo_notes` fields — note: top-level `beat_grid` stays the legacy beat-timestamp list (`score.py` requires `isinstance(beat_grid, list)`), typed `BeatGrid | list[float] | None`; full `BeatGrid` objects remain per-section
- [⚠️] Cross-platform rendering test suite runs in CI — web green (4/4 Playwright, visual baselines within `maxDiffPixelRatio: 0.02`); native suite blocked on Detox wiring, completed by Commit 108
- [✅] Edge-case corpus (24 files) renders without crash — backend Node AlphaTab gate 24/24 + web Playwright suite; native gate pending Commit 108
- [✅] Known AlphaTab rendering limitations documented in repo for test writer reference (`docs/ALPHATAB_MUSICXML_LIMITATIONS.md`)

**Verification:** backend corpus+exporter+prerender 29 passed; score+jam+rhythm 23 passed; analyze_api+corpus 13 passed; `tsc --noEmit` clean; web Playwright suite 4/4 (user-run); Node corpus gate 24/24.

**Implementation:** `components/AlphaTabWeb.web.tsx` (MusicXML load path + banner fix), `assets/alphatab-harness/` (harness), `backend/app/musicxml_builder.py`, `backend/app/schemas.py` (top-level fields), `backend/app/jobs.py` (score.musicxml persist), `backend/app/alphatab_prerender.py` + `backend/scripts/alphatab_prerender.mjs`, `backend/scripts/generate_musicxml_corpus.py` + `backend/scripts/alphatab_corpus_check.mjs`, `backend/tests/test_musicxml_corpus.py` + `backend/tests/fixtures/musicxml-corpus/` + `backend/tests/fixtures/musicxml-dtd/`, `app/(tabs)/musicxml-render-test.tsx` (hidden route), `src/lib/corpusAssets.ts`, `metro.config.js` (musicxml assetExts), `tests/ui/musicxml-render.spec.ts` + `tests/ui/__snapshots__/`, `tests/mobile/musicxml-render.e2e.js`, `docs/ALPHATAB_MUSICXML_LIMITATIONS.md`, `README.md`.

---

### Commit 114: LLM-Enhanced Chord Correction & Roman Numeral Analysis ✅ DONE

**Goal:** Post-process raw ChordTimeline through a lightweight LLM (Claude Haiku or Gemini Flash) to correct improbable chord changes based on key context and add Roman numeral functional labels, inspired by ChordMini's Gemini integration.

**Current State:** Chord timeline is purely ML-inferred from audio features with no post-processing. The Viterbi decoder (Commit 99) uses statistical transition probabilities but has no musical key-awareness beyond diatonic preferences.

**Scope:**
- Add background worker `_enrich_chord_timeline()` (similar pattern to coach hydration in `jobs.py`) that runs after chord inference completes:
  - Batch chord events by section (30–60s windows)
  - Call Claude Haiku or Gemini Flash with prompt:
    "Given key={key}, correct improbable chord changes in this timeline.
     Return JSON array preserving original timestamps, with corrected chord
     symbols and Roman numeral labels (e.g., I, ii, V7, IV)."
  - Accept/reject logic: apply LLM correction only when confidence delta
    between original and corrected exceeds 0.15
  - Store corrected chord alongside original in `ChordEvent`:
    `llm_corrected_chord: str | None`, `roman_numeral: str | None`
- Add `roman_numeral` field to `ChordEvent` schema
- Add `correction_applied: bool` and `correction_delta: float` fields
- Add rate limiting: max 1 LLM call per 10s (same quota as coach hydration)
- Add fallback: when LLM unavailable, skip enrichment silently (no regression)
- Add metrics: correction rate, per-song accuracy delta, LLM latency P50/P95
- Add frontend display of Roman numeral labels alongside chord symbols in
  chord timeline UI (e.g., "G (V)" in C major)
- Cache enrichment results with SHA256(chord_timeline + key) to avoid re-LLM
- Add integration test: known ii-V-I progression is correctly labeled

**Acceptance Criteria:**
- [x] Chord timeline passes through LLM enrichment after Viterbi decoding
- [x] Improbable chord changes corrected (demonstrated: C → F# → G → C → G
      corrected to C → F → G → C → G in key of C major)
- [x] Roman numeral labels attached to each chord (I, ii, V7, etc.)
- [x] Original ML prediction preserved alongside LLM correction
- [x] Correction applied only when confidence delta > 0.15
- [x] Enrichment worker runs as background thread (no user-visible latency)
- [x] Roman numerals displayed in chord timeline UI
- [x] Integration test: ii-V-I in C major = Dm7 → G7 → Cmaj7 labeled ii → V7 → I

**Implementation:**
- New module: `app/chord_enrichment.py`
- Add to `jobs.py`: enqueue enrichment after chord inference, before MusicXML build
- Uses existing Anthropic client pattern from `coach.py`
- Cache enrichment results with SHA256(chord_timeline + key) to avoid re-LLM
- Deterministic Roman numeral computation via semitone-based key lookup (no LLM needed)
- Tests: `tests/test_chord_enrichment.py` (35 tests — Roman numerals, cache, enrichment, LLM mock, schema)

---

## Phase 2: Stem Routing & Audio Pipeline ✅ DONE

### Commit 110: Stem Routing Fix — Wire Bass+Other for Chords, Dynamic Melodic Stem for Solo ✅ DONE

**Goal:** Wire `build_stem_routing_hints()` output into the main analysis pipeline so chords are inferred from the `bass + other` stem mix (cleaner harmonic signal) and solo is inferred from a dynamically selected melodic stem, not always the guitar stem.

**Scope:**
- New module `app/audio_mix.py`: `mix_stems()` sums 2+ stem WAVs, truncate-to-shortest, peak-normalize to 0.89
- `analyze_audio.py`: `_resolve_chord_mix_path()` builds `bass+other` mix via `mix_stems`, falls back to `full_mix`/`guitar`; `_resolve_melodic_stem_path()` chains `selected → guitar → vocals`, influenced by `guitar_near_silent`/`guitar_buried_in_mix` flags
- `jobs.py`: calls `build_stem_routing_hints(stem_abs_paths)` and passes hints + `job_dir` into `build_lesson_json_from_librosa()`
- `schemas.py`: `StemRoutingHints` extended with `chord_mix_path`, `melodic_stem_path`, `chord_source`, `solo_source`
- Routing telemetry logged per job

**Acceptance Criteria:**
- [x] `mix_stems()` utility correctly sums 2+ stem WAVs into a single normalized WAV
- [x] Chord inference uses `bass + other` stem mix (not full mix) when both stems have non-zero RMS
- [x] Solo inference uses dynamically selected melodic stem (falls back: selected → guitar → vocals)
- [x] Stem quality flags (`guitar_near_silent`, `guitar_buried_in_mix`) influence routing decisions
- [x] Full hardcoded path fallback preserved when hints are unavailable
- [x] Routing decisions logged per job for observability
- [x] Integration test confirms multi-source chord input path

**Implementation:** `backend/app/audio_mix.py` (new), `backend/app/analyze_audio.py`, `backend/app/jobs.py`, `backend/app/schemas.py`, `backend/tests/test_stem_routing.py` (4 tests).

---

### Commit 111: [SKIPPED] Dual-Path Confidence-Weighted Stem Fusion

**Skipped:** Dual-path chord inference (run on both guitar stem AND full mix, then fuse) would double `infer_chords()` latency — already the slowest pipeline step. Commit 110's single-path routing covers the core use cases without the 2x regression. May revisit if inference becomes fast enough.

---

## MLOps: Production Infrastructure (Complete)

### Commit 136: Redis Job Queue + Celery Workers + Push-Based Job Updates ✅ DONE

**Goal:** Replace in-memory job store with Redis-backed queue and Celery workers for horizontal scaling and persistence. Add push-based job status updates (SSE/WebSocket) to eliminate polling fragility (BUG-01) and enable real-time UI progress.

**Current State:** In-memory dict (jobs.py:57) that loses jobs on restart and cannot handle concurrent load. Frontend polls `GET /analyze/{job_id}` every 2-8s with setTimeout — fragile pattern with known infinite-loop bug (BUG-01). No push mechanism exists.

**Scope:**
- Redis for job state persistence
- Celery workers for distributed processing
- Job recovery on startup (re-queue in-flight jobs)
- Worker auto-scaling based on queue depth
- **Push-based job status via SSE**:
  - Add `GET /analyze/{job_id}/stream` SSE endpoint using `sse-starlette`:
    - Emits `JobStatus` JSON payloads on each state/stage/progress change
    - Uses Redis pub/sub channel per `job_id` so Celery workers push updates without coupling to the HTTP process
    - Sends keep-alive pings every 15s to prevent connection drops
    - Closes stream on terminal status (`complete` or `failed`)
  - Frontend `pollAnalyzeJobCancelable()` gets an SSE code path:
    - Detect SSE support (`EventSource` on web, or `fetch` streaming on React Native)
    - Fall back to existing polling when SSE is unavailable
    - Remove `seenCompletedOrFailed` guard (root cause of BUG-01) — SSE naturally ends on terminal event
    - Keep `onStatus` and `onError` callbacks identical for consumer compatibility
- **Progressive job status stages** (in `JobStatus` schema, shared with Commit 108):
  - Add `analysis_stage: str` field to `JobStatus` with values `"initializing"`, `"stems_separating"`, `"chords_inferring"`, `"solo_inferring"`, `"building_musicxml"`, `"complete"`
  - Add `partial_result: bool` flag indicating whether `result` contains intermediate data
  - Celery worker emits stage updates via Redis pub/sub on each pipeline step
  - SSE endpoint forwards stage updates to connected clients in real-time

**Acceptance Criteria:**
- [x] Jobs persist across server restarts
- [x] Multiple Celery workers can process jobs concurrently
- [x] In-flight jobs are recovered and re-queued on startup
- [x] Queue depth monitoring enables worker auto-scaling
- [x] Backward compatibility with existing job API
- [x] `GET /analyze/{job_id}/stream` SSE endpoint delivers real-time job status updates
- [x] Celery workers push status changes to Redis pub/sub; HTTP process forwards them via SSE
- [x] SSE connection closes automatically on terminal status
- [x] Keep-alive pings prevent proxy timeout disconnections
- [x] Frontend SSE path eliminates the `seenCompletedOrFailed` polling guard (BUG-01 fixed at root)
- [x] Frontend falls back gracefully to polling on environments without SSE support
- [x] `analysis_stage` and `partial_result` available in every `JobStatus` update
- [x] `onStatus`/`onError` callbacks identical between SSE and polling paths (transparent swap)

---

### Commit 137: Dedicated ML Model Server + MLflow ✅ DONE

**Goal:** Deploy dedicated inference service for chord model with batched inference, model versioning, and GPU batching. Add MLflow tracking and drift detection.

**Current State:** TFLite inference runs in-process (chord_inference.py:75-114) with no batching or versioning.

**Scope:**
- Separate chord inference service with batched inference
- Model versioning and A/B testing support
- GPU batching for throughput
- Model loading/unloading without server restart
- **MLflow integration for model performance tracking:**
  - Configure MLflow tracking server (tracking_uri, experiment_name)
  - Log every training run with hyperparameters, loss curves, per-class metrics
  - Register trained models in MLflow Model Registry with stage promotion (staging → production)
  - Compare runs across experiments (architecture variants, dataset mixes, augmentation configs)
- **Automated accuracy drift detection:**
  - Store deployment baseline accuracy per model version
  - Compare validation accuracy on each retrain vs. deployment baseline
  - Alert if accuracy drops below configurable threshold (>3% degradation)

**Acceptance Criteria:**
- [x] Dedicated inference service handles batch requests
- [x] Multiple model versions can be deployed simultaneously
- [x] GPU batching improves throughput by 3-5x
- [x] Model can be hot-swapped without server restart
- [x] A/B testing framework for model comparison
- [x] MLflow tracking server logs every training run with hyperparameters and metrics
- [x] Model Registry contains versioned artifacts with stage metadata
- [x] Drift detection alerts on accuracy degradation >3% vs deployment baseline

---

### Commit 139: Error Resilience (Circuit Breakers, Retry, DLQ) ✅ DONE

**Goal:** Implement circuit breakers, exponential backoff, and dead letter queues for transient failures.

**Current State:** Basic try/except with user-friendly messages (jobs.py:391-431) but no retry logic.

**Scope:**
- Retry logic for transient YouTube failures with exponential backoff
- Circuit breaker for LLM API calls
- Dead letter queue for failed analysis jobs
- Automatic retry for recoverable errors

**Acceptance Criteria:**
- [x] YouTube download failures are retried with exponential backoff
- [x] Circuit breaker prevents cascading LLM API failures
- [x] Failed jobs are sent to dead letter queue for inspection
- [x] Recoverable errors are automatically retried
- [x] Error rate monitoring triggers circuit breaker

---

### Commit 140: Monitoring & Observability (Prometheus, Grafana) ✅ DONE

**Goal:** Add structured metrics, distributed tracing, and alerting for operational visibility.

**Current State:** Basic logging with elapsed time tracking (jobs.py:246-247) but no metrics or alerting.

**Scope:**
- Prometheus metrics endpoint
- Per-stage latency histograms
- Error rate alerting
- Distributed tracing (OpenTelemetry)

**Acceptance Criteria:**
- [x] Prometheus metrics endpoint exposes job metrics
- [x] Per-stage latency histograms identify bottlenecks
- [x] Error rate alerting triggers on threshold breaches
- [x] Distributed tracing tracks requests across services
- [x] Grafana dashboards visualize system health

---

### Docker Compose ✅ DONE

**Goal:** Containerize all services for one-command deployment.

**Scope:**
- `backend` (FastAPI) + `worker` (Celery) + `redis` + `prometheus` + `grafana` + `mlflow` in one compose file
- `Dockerfile` multi-stage build; `.dockerignore` excludes dev artifacts
- `docker/prometheus.yml` scrape config
- `docker/grafana/provisioning/` auto-provisions datasource + dashboard

---

## Technology Resolution Notes (Archived)

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