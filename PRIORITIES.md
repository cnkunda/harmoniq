# Harmoniq — Engineering Roadmap

Three-phase product roadmap for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**.

---

## At a glance

| | |
|--|--|
| **Roadmap status** | **Phase 2: Feedback, Retention & ML Refinement. Phase 3: Planned.** |
| **Product spec** | [`README.md`](README.md) |
| **UI spec** | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Scoring** | [`docs/SCORING.md`](docs/SCORING.md) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (Phase 0 + Phase 1) |

---

## PHASE 2: Feedback, Retention & ML Refinement

## PHASE 2: Feedback, Retention & ML Refinement

**Status:** Planned

### Milestone: User Feedback & Manual Overrides

System to tag and save manual tab corrections to refine ML confidence levels.

**Scope:**
- UI for users to mark incorrect notes/chords
- Backend persistence of corrections
- ML retraining pipeline incorporating user feedback

---

### Milestone: Lick Library Persistence

Full CRUD for saved phrases and "Drill This" micro-session logic.

**Scope:**
- SQLite schema for saved licks
- UI for browsing, tagging, and organizing licks
- "Drill This" generates focused micro-sessions from saved phrases

---

### Milestone: Jam Mode Summary Agent

Claude-powered post-jam analysis and vocabulary mapping.

**Scope:**
- Post-jam analysis endpoint
- Vocabulary pattern detection
- Claude integration for summary generation
- **Concrete model-to-coach JSON bundle schema**:
  ```json
  {
    "chord": "G:maj7",
    "clarity": 0.61,
    "intonation_cents": {"B2": -8, "high_E": +14},
    "timing_ms": +35,
    "transition_from": "C:maj",
    "transition_gap_ms": 120
  }
  ```
- **Persona-switching via system prompt**: learner → encouragement, simplified language; intermediate → technical feedback; transcriber → notation decisions explained
- Model outputs fast deterministic numbers on-device; Claude is called once per phrase/segment to convert numbers into coaching language

---

### Milestone: ML Fallback Logic

Implement auto-switching to "Skeleton" tabs when transcription_confidence < 0.7.

**Scope:**
- Confidence threshold detection
- Skeleton tab generation (simplified notation)
- Graceful degradation UI

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

### Commit 98: Advanced Extension Recognition

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

### Commit 98a: Chord Data Generation Improvements

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

### Commit 98b: 36-Bin CQT Feature Extraction

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

### Commit 98c: CRNN Architecture with Bidirectional LSTM

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

### Commit 98d: Multi-Head Self-Attention Mechanism

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

### Commit 99: Viterbi Decoding for Chord Progressions

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
- [ ] Transition matrix computed from real chord progression data
- [ ] Viterbi decoder produces smoothed chord sequences
- [ ] Decoding latency <10ms for 30-second audio
- [ ] Reduced chord flickering in predictions (target: 40% reduction)
- [ ] Integration test with known chord progression (e.g., ii-V-I)
- [ ] Viterbi decreases chord flicker rate to <5% (chord changes every 1-2 beats filtered)
- [ ] Beat-alignment gate measures >90% of chord changes landing on beat/downbeat boundaries
- [ ] Chord-change rate histogram reportable per-song in analysis metadata
- [ ] Duration-aware filtering suppresses sub-1-beat chord outliers
- [ ] Key-constrained transition costs reduce improbable chord movements (e.g., C → F#)
- [ ] Chord timeline supports half-beat resolution: when 8th-note subdivisions are active, two chord events emitted per beat with correct timestamps
- [ ] Beat-subdivision tie-detection: two competing chords within a single beat window with confidence difference <0.15 triggers half-beat split

---

### Commit 100: Segment Boundary Tie Mechanism (MT3 Paper Insight)

**Goal:** Eliminate chord/note transcription errors at segment boundaries by implementing an overlap-and-blend strategy with active-note tracking — inspired by MT3's "tie" mechanism that declares which notes are already active at the start of each segment.

**Rationale (from MT3 paper, Section 3.2):** MT3 solves the "forgotten note" problem by requiring the model to emit a "tie section" at the beginning of each segment declaring active notes. Notes not re-declared in the next segment are gracefully ended. Our TFLite chord model (128-frame sliding window) and Basic Pitch process segments independently with no cross-segment state, causing onset/offset errors at boundaries that directly corrupt scoring (`_score_timing()` in `score.py`).

**Current State:** `chord_inference.py` uses a 128-frame sliding window with no overlap handling. `solo_inference.py` processes segments independently. Notes/chords spanning boundaries are duplicated or dropped, inflating timing errors in the scoring system.

**Scope:**
- Add 50% overlap processing for chord inference windows:
  - Process overlapping windows, merge predictions in overlap zone by taking higher-confidence prediction
  - Weight predictions by distance from window center (triangular windowing)
- Implement active-note tracking for Basic Pitch (like MT3's tie section):
  - Maintain "active notes" state between segments
  - At segment start, check if notes from previous segment should continue
  - End notes not re-declared in the current segment
- Add boundary confidence penalty: reduce confidence for predictions within 2 frames of segment edges
- Add unit test: verify a chord held across a boundary is emitted as a single event, not two

**Acceptance Criteria:**
- [ ] Overlap-and-blend reduces boundary chord flicker by ≥50%
- [ ] Active-note tracking prevents "forgotten note" offsets in solo transcription
- [ ] Boundary confidence penalty reduces false positives at segment edges
- [ ] Scoring timing errors decrease for notes held across boundaries
- [ ] Unit test: chord held across boundary → single event emitted
- [ ] No regression on within-segment prediction accuracy

---

### Commit 101: Real Dataset Integration (Isophonics/Billboard)

**Goal:** Train on real annotated audio instead of purely synthetic data to improve real-world accuracy.

**Current State:** Model trained only on synthetic chroma templates; no exposure to real audio characteristics.

**Scope:**
- Download Isophonics dataset (Beatles, Queen, etc. with chord annotations)
- Download McGill Billboard dataset (pop/rock with chord labels)
- Write preprocessing script to extract CQT and align with chord labels
- Convert annotations to extended chord vocabulary (map rare qualities to closest match)
- Combine real + synthetic data (70/30 split recommended)
- Add dataset mixing to training pipeline

**Acceptance Criteria:**
- [ ] Isophonics dataset loaded and preprocessed
- [ ] Billboard dataset loaded and preprocessed
- [ ] CQT features extracted and aligned with chord labels
- [ ] Train/val/test split with no artist overlap
- [ ] Real data comprises 70% of training batches
- [ ] Validation accuracy on Isophonics test set >75% root accuracy

---

### Commit 102: Threshold Sensitivity Analysis & Label Noise Robustness (MT3 Paper Insight)

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
- [ ] Threshold sensitivity analysis script produces F1-vs-tolerance curves
- [ ] Label noise report identifies which dataset subsets have timing issues
- [ ] Temporal jitter augmentation (±30ms) active during training
- [ ] Model accuracy on noisy-label validation set improves by ≥3%
- [ ] Label quality gate rejects examples with >100ms boundary jitter
- [ ] Analysis results documented in `docs/LABEL_QUALITY.md`

---

### Commit 103: Training Infrastructure Improvements

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
- [ ] Early stopping prevents overfitting
- [ ] Learning rate reduces automatically on plateau
- [ ] Time stretch and pitch shift augmentations active
- [ ] Confusion matrix identifies confused chord pairs
- [ ] Per-class metrics reveal rare chord performance
- [ ] Training completes in <2 hours on available hardware

---

### Commit 104: Temperature Sampling for Chord Type Imbalance (MT3 Paper Insight)

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
- [ ] Chord type distribution analysis report generated
- [ ] Temperature sampling implemented with configurable exponent
- [ ] Rare chord type (7#9, alt7, dim7, aug) recall improves by ≥15%
- [ ] Common chord type (maj, min) accuracy degrades by <2%
- [ ] Per-chord-type recall reported during validation
- [ ] Temperature parameter tunable via training config

---

### Commit 105: Quantization-Aware Training

**Goal:** Improve TFLite quantization accuracy by training with quantization constraints rather than post-training quantization.

**Current State:** Post-training quantization may degrade accuracy for extended chord vocabulary.

**Scope:**
- Integrate `tensorflow_model_optimization` toolkit
- Apply `quantize_model()` wrapper to training model
- Implement QAT (Quantization-Aware Training) for 4-5 epochs
- Compare accuracy vs post-training quantization baseline
- Generate INT8 quantized model for mobile deployment

**Acceptance Criteria:**
- [ ] QAT model trained with simulated quantization
- [ ] INT8 quantized model produced
- [ ] Accuracy degradation <3% vs float32 model
- [ ] Model size <500KB after quantization
- [ ] Inference latency reduction confirmed on mobile device

---

### Commit 106: Solo Rhythm Quantization & Measure-Level Sanity

**Goal:** Quantize solo note durations to standard notation types (quarter, eighth, sixteenth, triplet) and add measure-level rhythmic sanity checks to the MusicXML builder.

**Current State:** Solo note durations are grid-snapped in seconds but not quantized to standard note types. The MusicXML builder uses raw 8th-note fractions (`round(... * 8) / 8`) with no measure overflow validation. Micro-durations (<32nd note) exist despite filtering.

**Scope:**
- Add `quantize_to_note_type()` function: map real durations (seconds) to nearest standard type (whole, half, quarter, 8th, 16th, 32nd, 64th) based on current BPM and tick grid
- Implement tuplet detection: group onset patterns that form triplets, quintuplets, or sextuplets
- Add measure-level duration validation: enforce total note + rest duration == time signature fill
- Add measure overflow detection: clip or redistribute notes exceeding bar capacity
- Add measure underflow detection: insert beat-aligned rests for unfilled time
- **Reinforce beat-grid quantization in `infer_solo()`**: after amplitude selection, quantize the surviving note's onset and duration to the beat grid via `_snap_to_grid()`, removing sub-half-tick micro-notes (already implemented). Verify that the duration passed to MusicXML builder maps to standard note types via the `tick_value` grid
- Replace hardcoded `round(... * 8) / 8` in `musicxml_builder.py` with variable-resolution quantization mapped to the time signature denominator
- Emit proper MusicXML `<type>` elements (eighth, 16th, 32nd, etc.) and `<dot>` for dotted durations
- Add `<beam>` grouping based on beat structure and tuplet detection
- **Add amplitude-based polyphonic→monophonic selection in `infer_solo()`**: group raw basic-pitch note events by beat slot (using `beat_grid.beats`), select at most one note per slot by maximum amplitude (pitch as tiebreaker), mirroring `build_gp5_from_note_events()` behavior at `pipeline_proof.py:531-544`. The existing chronological truncation path becomes a fallback when only one overlapping note exists per slot
- Build test suite covering: syncopation, triplets, dotted rhythms, measure overflow, edge durations
- Fix `_add_technical_elements()` regex injection conflict with `<tie>`:
  change from naive regex append (which produces duplicate `<notations>`
  for tied notes) to music21-native `<technical>` attachment, or detect
  and merge into existing `<notations>` elements when `<tie>` is present
- Add explicit `<divisions>` element in `<attributes>` (set to 480) so
  AlphaTab's MusicXML parser has an unambiguous duration reference
- Add key signature validation: parse "A minor" →
  `music21.key.Key('A', 'minor')` correctly. The current simple split
  heuristic treats all modes as major (both C major and A minor = 0
  sharps, correct pitch-wise but wrong mode)

**Acceptance Criteria:**
- [ ] Note durations quantized to standard types (whole through 64th) with correct `<type>` elements
- [ ] Triplet detection correctly groups 3-in-the-time-of-2 patterns
- [ ] Measure fill validation: total note+rest duration equals measure length within 1-tick tolerance
- [ ] Measure overflow clips notes at bar line and ties to next measure
- [ ] Unfilled measure time produces rests at beat/sub-beat boundaries (not arbitrary positions)
- [ ] `<beam>` groupings follow beat structure (no cross-beat beams) and tuplet groups
- [ ] `infer_solo()` selects at most one note per beat slot, preferring highest amplitude (matching `build_gp5_from_note_events` behavior)
- [ ] Test suite covers syncopation, triplets, 5-tuplets, dotted quarters, and maximal/minimal durations
- [ ] Existing solo duration filtering (sub-32nd note removal) remains active and non-regressed
- [ ] `_add_technical_elements()` produces valid XML when notes have `<tie>`
      elements: single `<notations>` block contains both `<technical>` and `<tie>`
- [ ] `<divisions>480</divisions>` present in every measure's `<attributes>`
- [ ] Minor key signatures generate correct MusicXML (`<key><fifths>0</fifths><mode>minor</mode></key>`)

---

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

### Commit 108: Beat Grid Editor (UI + Recomputation)

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
- [ ] Beat grid timeline visualizes beats (ticks), downbeats (accented), and bar lines
- [ ] Time signature picker supports 2/4, 3/4, 4/4, 6/8, 9/8, 12/8 with correct subdivision
- [ ] BPM adjustment per-section recomputes beat spacing in real-time preview
- [ ] `POST /analyze/{job_id}/beat-grid/recompute` triggers full dependent artifact chain
- [ ] Chord timeline re-pooled on new beat boundaries after time sig change
- [ ] Solo durations re-quantized after BPM change
- [ ] MusicXML rebuilt with updated time signature, BPM, chords, and solo
- [ ] `bar_timestamps` computed from actual time signature (not hardcoded 4/4)
- [ ] Frontend polls recompute progress and updates all displays on completion
- [ ] Overrides persist across page navigations in the same session
- [ ] "Reset to Auto" restores librosa-estimated grid
- [ ] Test: 4/4 → 6/8 time signature change correctly recomputes chord beat alignment
- [ ] Initial `POST /analyze` returns chord timeline as partial result before solo inference finishes
- [ ] `JobStatus.analysis_stage` enum reported in every poll response during processing
- [ ] Frontend renders chord chart preview when `analysis_stage >= "chords_inferring"` (before full completion)
- [ ] Intermediate artifacts survive server restart (persisted to disk)
- [ ] Monolithic loading spinner replaced with progressive reveal (chords first, then solo, then full score)
- [ ] Coach hydration remains separate and non-regressed

---

### Commit 109: Analysis Persistence & Correction Editor

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
- [ ] Analysis outputs persist across server restarts (SQLite or filesystem)
- [ ] Chord symbol correction endpoint accepts valid chord and persists it
- [ ] Solo note endpoint accepts pitch/duration/string/fret overrides
- [ ] Voicing endpoint stores alternative CAGED shape per chord
- [ ] Frontend chord correction dropdown filtered by key
- [ ] Frontend note correction with real-time fretboard preview
- [ ] Correction history tracks original vs. corrected with revert capability
- [ ] MusicXML export uses corrected data
- [ ] Fretboard sync reflects corrections immediately during playback
- [ ] Correction coverage metric (% of ML-predicted events that were corrected) available
- [ ] Corrections exportable as training data for ML retraining

---

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

### Commit 114: LLM-Enhanced Chord Correction & Roman Numeral Analysis

**Goal:** Post-process raw ChordTimeline through a lightweight LLM (Claude Haiku or
Gemini Flash) to correct improbable chord changes based on key context and add
Roman numeral functional labels, inspired by ChordMini's Gemini integration.

**Current State:** Chord timeline is purely ML-inferred from audio features with no
post-processing. The Viterbi decoder (Commit 99) uses statistical transition
probabilities but has no musical key-awareness beyond diatonic preferences.

**Scope:**
- Add background worker `_enrich_chord_timeline()` (similar pattern to coach
  hydration in `jobs.py`) that runs after chord inference completes:
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
- [ ] Chord timeline passes through LLM enrichment after Viterbi decoding
- [ ] Improbable chord changes corrected (demonstrated: C → F# → G → C → G
      corrected to C → F → G → C → G in key of C major)
- [ ] Roman numeral labels attached to each chord (I, ii, V7, etc.)
- [ ] Original ML prediction preserved alongside LLM correction
- [ ] Correction applied only when confidence delta > 0.15
- [ ] Enrichment worker runs as background thread (no user-visible latency)
- [ ] Roman numerals displayed in chord timeline UI
- [ ] Integration test: ii-V-I in C major = Dm7 → G7 → Cmaj7 labeled ii → V7 → I

**Implementation:**
- New module: `app/chord_enrichment.py`
- Add to `jobs.py`: enqueue enrichment after chord inference, before MusicXML build
- Uses existing Anthropic client pattern from `coach.py`
- Cache enrichment results with SHA256(chord_timeline + key) to avoid re-LLM

---

### Commit 115: Structural Segmentation Refinement

**Goal:** Improve section boundary detection beyond RMS-only novelty by fusing
chord change density, Whisper word-cluster boundaries, and energy envelope.

**Current State:** `librosa_summarize()` uses RMS + onset novelty for boundary
detection. Sections are unlabeled (just timestamps). ChordMini's SongFormer
provides dedicated structural segmentation (intro/verse/chorus/bridge/outro).

**Scope:**
- Add `refine_section_boundaries()` module that fuses three signals:
  - Chord change density: high change rate suggests section boundary
  - Whisper word-cluster boundaries: silence/gap between vocal phrases
  - Energy envelope novelty: existing librosa onset novelty
  - Fusion: weighted average (0.4 chord, 0.3 vocal, 0.3 energy) → peak
    detection for boundary candidates
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

### Milestone: Multi-Task Model Architecture

**Goal:** Extend the chord estimation model from single-task classification to a multi-task architecture that outputs richer coaching signals — chord ID, clarity, intonation, timing, and transition quality — all sharing one backbone.

**Rationale:** A coach listens for more than just the chord name. They hear whether strings ring clearly, whether notes are in tune, whether chord changes are smooth, and whether the player is locked to the beat. A model that outputs all five signals enables richer feedback without requiring separate models per signal.

**Architecture:**
- Shared backbone: CNN → Multi-Head Attention → Bidirectional LSTM → common embedding (reuse Commit 103/104 architecture)
- Five regression/classification heads on the shared [CLS] embedding:
  - **Chord ID**: 277-class classification (existing vocabulary, Commit 98)
  - **Clarity**: 0–1 regression score (clean chord vs buzzy/muted strings)
  - **Intonation**: cents deviation per string (regression, 6 outputs)
  - **Timing**: onset deviation in ms vs beat grid (regression, 1 output)
  - **Transition**: gap/overlap in ms between consecutive chord changes (regression, 1 output)
- Loss: cross-entropy for chord ID + MSE for regression heads, weighted sum with tunable λ per head
- Training schedule: pre-train shared backbone on chord ID → fine-tune all heads jointly

**Scope:**
- Design multi-output model in `build_chord_tflite.py` with shared backbone + per-head MLPs
- Add clarity labels to dataset: recordings of clean and intentionally bad (muted, buzzing, out-of-tune) chord performances
- Add intonation labels: record reference MIDI synth alongside guitar for cents-deviation ground truth
- Add timing labels: record with metronome click in a separate track as reference
- Derive transition labels from consecutive onset detections (no extra labeling)
- Mix GuitarSet (NYU) annotated dataset with custom recordings for training
- Implement weighted multi-task loss with per-head normalization
- Verify TFLite conversion supports multi-output graphs (SELECT_TF_OPS)
- Add integration test: model outputs all five signals for a known chord recording

**Acceptance Criteria:**
- [ ] Shared backbone extracts features used by all five heads
- [ ] Chord ID head maintains ≥90% of single-task accuracy
- [ ] Clarity head predicts 0–1 score correlated with string-mute ground truth (r > 0.8)
- [ ] Intonation head predicts cents deviation within ±5 cent MAE on test set
- [ ] Timing head predicts onset deviation within ±10 ms MAE
- [ ] Transition head detects gaps/overlaps >50 ms between chord changes
- [ ] Multi-task model size < 600 KB after INT8 quantization
- [ ] Inference stays under 120 ms on mobile device (TFLite)
- [ ] TFLite multi-output graph conversion succeeds
- [ ] Integration test verifies all five outputs on a real guitar recording

---

### Milestone: Three-Tier Output Strategy

**Goal:** Serve three distinct user personas from a single analysis backbone by rendering the same chord/solo analysis through persona-specific output views.

**Rationale:** A learner, an intermediate player, and a transcriber all need different information from the same song. Maintaining separate pipelines for each would be costly — but all three can share the same ML analysis and diverge only at the presentation layer.

**Personas and renderers:**

| Persona | Output | Key features |
|---------|--------|-------------|
| **Learner** | Scrolling chord chart + solo line + fretboard sync | Chord symbols over bars, color-coded fretboard, simplified notation, metronome-aligned playback |
| **Intermediate** | Slash chord chart + beat grid | Slash notation (G/B, D/F#), stable beat grid with downbeat markers, chord-change timing annotations |
| **Transcriber** | Printable/exportable MusicXML | Full score with structure labels (intro/verse/chorus), measure-level formatting, MusicXML export for MuseScore |

**Scope:**
- Define `LessonJSON` as the shared analysis output consumed by all three renderers (chord timeline, solo notes, beat grid)
- Build **Learner renderer**: chord symbols + bar lines overlay on fretboard, simplified solo notation, metronome sync
- Build **Intermediate renderer**: slash chord notation, beat-aligned grid display, chord-change timing annotations
- Build **Transcriber renderer**: MusicXML → printer-friendly layout, section labels, export to MusicXML/PDF
- Maintain persona persistence per-user in local DB (so the choice survives app restarts)
- Claude coaching persona-switching (system prompt) mirrors the selected renderer persona
- Regression test: same analysis input produces correct output for all three renderers
- Integration test: compare learner vs transcriber rendering of a ii-V-I progression

**Acceptance Criteria:**
- [ ] Learner renderer shows chord symbols over bar lines with fretboard sync during playback
- [ ] Intermediate renderer shows slash chords (G/B) and beat grid markers
- [ ] Transcriber renderer produces printable MusicXML with section labels and structure
- [ ] Shared `LessonJSON` drives all three renderers identically
- [ ] Persona selection persists across app restarts in local DB
- [ ] Claude persona mirrors selected renderer (system prompt changes per mode)
- [ ] Regression tests pass for all three renderers on same input
- [ ] Integration test: ii-V-I in C major renders correctly in all three modes

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

### Milestone: Predictive Beat Recovery

Implement a "look-ahead" algorithm to maintain visual sync during tempo drifts or complex syncopation.

**Scope:**
- Look-ahead beat detection algorithm
- Tempo drift compensation
- Syncopation handling

**Acceptance Criteria:**
- [ ] Visual sync maintained during tempo drifts
- [ ] Look-ahead algorithm handles syncopation
- [ ] Beat grid adjusts dynamically

---

### Milestone: Smart Capo Suggestions

Logic to calculate and suggest optimal capo positions to match the detected key with easier 'open' chord shapes.

**Scope:**
- Capo position calculation algorithm
- Open chord shape mapping
- Suggestion UI

**Acceptance Criteria:**
- [ ] Optimal capo positions calculated for detected key
- [ ] Suggestions use easier open chord shapes
- [ ] UI displays capo recommendations

---

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

### Commit 136: Redis Job Queue + Celery Workers + Push-Based Job Updates

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
- [ ] Jobs persist across server restarts
- [ ] Multiple Celery workers can process jobs concurrently
- [ ] In-flight jobs are recovered and re-queued on startup
- [ ] Queue depth monitoring enables worker auto-scaling
- [ ] Backward compatibility with existing job API
- [ ] `GET /analyze/{job_id}/stream` SSE endpoint delivers real-time job status updates
- [ ] Celery workers push status changes to Redis pub/sub; HTTP process forwards them via SSE
- [ ] SSE connection closes automatically on terminal status
- [ ] Keep-alive pings prevent proxy timeout disconnections
- [ ] Frontend SSE path eliminates the `seenCompletedOrFailed` polling guard (BUG-01 fixed at root)
- [ ] Frontend falls back gracefully to polling on environments without SSE support
- [ ] `analysis_stage` and `partial_result` available in every `JobStatus` update
- [ ] `onStatus`/`onError` callbacks identical between SSE and polling paths (transparent swap)

**Implementation:**
- Add Redis dependency to requirements.txt
- Replace in-memory `jobs` dict with Redis-backed job store
- Integrate Celery for async job processing
- Implement job recovery script that runs on startup
- Add Redis pub/sub helpers (`redis.publish(channel, message)`, `redis.subscribe(channel)`)
- Implement SSE endpoint with `sse-starlette` or `StreamingResponse`
- Add queue depth metrics for auto-scaling decisions
- Update job polling endpoint to work with Redis (backward-compatible)
- Add frontend `EventSource` or `fetch` streaming client in `src/api/analyze.ts`

---

### Commit 137: Dedicated ML Model Server

**Goal:** Deploy dedicated inference service for chord model with batched inference, model versioning, and GPU batching.

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
- [ ] Dedicated inference service handles batch requests
- [ ] Multiple model versions can be deployed simultaneously
- [ ] GPU batching improves throughput by 3-5x
- [ ] Model can be hot-swapped without server restart
- [ ] A/B testing framework for model comparison
- [ ] MLflow tracking server logs every training run with hyperparameters and metrics
- [ ] Model Registry contains versioned artifacts with stage metadata
- [ ] Drift detection alerts on accuracy degradation >3% vs deployment baseline

**Implementation:**
- Create separate FastAPI service for chord inference
- Implement batch inference endpoint
- Add model versioning to model loading logic
- Integrate GPU batching with TensorFlow Serving or ONNX Runtime
- Add model registry for version management
- Implement A/B testing routing logic
- Add MLflow client to training scripts (`build_chord_tflite.py`): wrap training loop with `mlflow.start_run()`, log params, metrics, and model artifact
- Add drift detection module: store baseline accuracy on deployment, compare each new model version's validation accuracy, emit warning on threshold breach

---

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

### Commit 139: Error Resilience (Circuit Breakers, Retry, DLQ)

**Goal:** Implement circuit breakers, exponential backoff, and dead letter queues for transient failures.

**Current State:** Basic try/except with user-friendly messages (jobs.py:391-431) but no retry logic.

**Scope:**
- Retry logic for transient YouTube failures with exponential backoff
- Circuit breaker for LLM API calls
- Dead letter queue for failed analysis jobs
- Automatic retry for recoverable errors

**Acceptance Criteria:**
- [ ] YouTube download failures are retried with exponential backoff
- [ ] Circuit breaker prevents cascading LLM API failures
- [ ] Failed jobs are sent to dead letter queue for inspection
- [ ] Recoverable errors are automatically retried
- [ ] Error rate monitoring triggers circuit breaker

**Implementation:**
- Add retry decorator with exponential backoff for YouTube downloads
- Implement circuit breaker pattern for LLM API calls
- Create dead letter queue in Redis for failed jobs
- Add automatic retry logic for recoverable errors
- Implement error rate monitoring and alerting
- Add DLQ inspection and re-queue tools

---

### Commit 140: Monitoring & Observability (Prometheus, Grafana)

**Goal:** Add structured metrics, distributed tracing, and alerting for operational visibility.

**Current State:** Basic logging with elapsed time tracking (jobs.py:246-247) but no metrics or alerting.

**Scope:**
- Prometheus metrics endpoint
- Per-stage latency histograms
- Error rate alerting
- Distributed tracing (OpenTelemetry)

**Acceptance Criteria:**
- [ ] Prometheus metrics endpoint exposes job metrics
- [ ] Per-stage latency histograms identify bottlenecks
- [ ] Error rate alerting triggers on threshold breaches
- [ ] Distributed tracing tracks requests across services
- [ ] Grafana dashboards visualize system health

**Implementation:**
- Add Prometheus client library to backend
- Implement metrics endpoint for job queue, latency, errors
- Add histogram metrics for each pipeline stage
- Integrate OpenTelemetry for distributed tracing
- Set up Grafana dashboards for key metrics
- Configure alerting rules for error rates and latency

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

### Supporting Improvements (absorbed into existing commits)

The following improvements are already partially scoped in existing commits.
Extend their scope rather than creating new entries:

| Concern | Existing commit | Extension |
|---------|----------------|-----------|
| Perceptual audio fingerprinting | **Commit 141** (Audio Fingerprinting & Quality Scoring) | Already covers Chromaprint-based cache keys. Ensure fallback to SHA256 when fingerprinting unavailable. |
| On-device real-time chord inference | **Commit 127** (Live Mic Mode) | Add React Native TFLite bridge for `chord_model.tflite` inference on mic input. Web path: TensorFlow.js or ONNX runtime. Reuse existing model. |
| Confidence-weighted ensemble | **Commit 99** (Viterbi Decoding) | Before Viterbi smoothing, run TFLite model + Basic Pitch harmonic analysis + librosa chroma features through a weighted voting layer. Track per-chord confidence as weighted average. |
| Generative accompaniment (Lyria) | Already exists in `jam_backing.py` | Use `BeatGrid` as a conditioning signal: generate MIDI patterns locked to the detected beat grid and chord changes, then render through AlphaTab's SoundFont. |
| AlphaTab WebView hardening (CDN, message protocol, offline) | **Commit 107** (MusicXML as Primary Render Format) | Bundle AlphaTab JS locally via Metro asset instead of jsDelivr CDN for offline support; tighten `postMessage` `targetOrigin` from `'*'` to explicit allowed origins; align SoundFont timeout values (25s harness vs 16s web path); wire prerender SVG display on native WebView; add navigation gating unit tests with malicious URL corpus; add CDN-unreachable fallback path that loads AlphaTab from bundled asset |

---

## PHASE 3: AI-Agent Scaling & Pro-App Parity

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
