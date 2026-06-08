# Harmoniq — Engineering Roadmap

Three-phase product roadmap for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**. **Phase 2 commits 98-112, 115, 117, 118** — archived. **Phase 2 commits 106, 116, 119-147** — planned/deferred.

---

## At a glance

|                    |                                                                      |
| ------------------ | -------------------------------------------------------------------- |
| **Roadmap status** | **Phase 2: Feedback, Retention & ML Refinement. Phase 3: Planned.**  |
| **Product spec**   | [`README.md`](README.md)                                             |
| **UI spec**        | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md)                               |
| **E2E / release**  | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md)                               |
| **Manual QA**      | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md)                             |
| **Scoring**        | [`docs/SCORING.md`](docs/SCORING.md)                                 |
| **Archive**        | [`priorities-archive.md`](priorities-archive.md) (Phase 0 + Phase 1 + Phase 2 commits 98-115) |

---

## PHASE 2: Feedback, Retention & ML Refinement

**Status:** In Progress — commits 98-112, 115, 117, 118 archived. Commits 106, 116, 119-147 remain as planned/deferred backlog below.

### Milestone: User Feedback & Manual Overrides

System to tag and save manual tab corrections to refine ML confidence levels.

**Scope:**

- UI for users to mark incorrect notes/chords
- Backend persistence of corrections
- ML retraining pipeline incorporating user feedback

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
    "intonation_cents": { "B2": -8, "high_E": +14 },
    "timing_ms": +35,
    "transition_from": "C:maj",
    "transition_gap_ms": 120
  }
  ```

- **Persona-switching via system prompt**: learner → encouragement, simplified language; intermediate → technical feedback; transcriber → notation decisions explained
- Model outputs fast deterministic numbers on-device; Claude is called once per phrase/segment to convert numbers into coaching language

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

### Commit 106: Quantization-Aware Training [DEFERRED]

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

### Commit 116: LLM-Enhanced Chord Correction & Roman Numeral Analysis [DEFERRED]

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

### Commit 119: Semantic Section Label Classification

**Goal:** Replace cyclic label assignment with audio-feature-based classification that distinguishes
Intro, Verse, Chorus, Bridge, Solo, and Outro by their actual musical characteristics.

**Current State:** Labels are assigned from a fixed list cyclically (`labels[i % 6]`), ignoring
actual musical content. A bridge and a verse get different labels only because of position,
not because the algorithm detected a bridge.

**Scope:**

- Extract per-section audio features for classification:
  - **Energy**: RMS mean and variance (chorus = high, intro/outro = low)
  - **Spectral centroid**: brightness indicator (solo = high, verse = moderate)
  - **Chord change density**: chords per second (bridge = high, intro = low)
  - **Harmonic stability**: chroma variance over section (intro = unstable, verse = stable)
  - **Position in song**: first/last section, relative duration
- Build rule-based classifier (no ML training needed):

  ```python
  def classify_section(features, position, duration):
      if position == 'first' and duration < 15 and energy < threshold:
          return 'Intro'
      if position == 'last' and energy_declining:
          return 'Outro'
      if energy > chorus_threshold and is_repeated:
          return 'Chorus'
      if harmonic_shift and not is_repeated:
          return 'Bridge'
      if spectral_centroid > solo_threshold and chord_density < verse_threshold:
          return 'Solo'
      return 'Verse'  # default
  ```

- Add `label_confidence: float` (0-1) to `LessonSectionStub` schema
- If confidence < 0.6, fall back to generic "Section N" label
- Add pre-chorus detection:
  - Short section (< 10s) between Verse and Chorus
  - Rising energy profile, increasing chord density
  - Label as "Pre-Chorus" when detected
- Add instrumental section detection:
  - Low vocal energy (from Demucs vocals stem)
  - High instrumental energy
  - Label as "Instrumental" or "Solo" accordingly
- Preserve existing labels as fallback when classification confidence is low

**Acceptance Criteria:**

- [ ] Intro detected as low-energy opening section (< 15s typical)
- [ ] Chorus detected as high-energy repeated section
- [ ] Bridge detected as harmonically distinct non-repeated section
- [ ] Pre-chorus detected as short rising-energy section before chorus
- [ ] Outro detected as declining-energy final section
- [ ] Solo/instrumental sections distinguished from vocal sections
- [ ] `label_confidence` reported per section
- [ ] Fallback to "Section N" when confidence < 0.6
- [ ] Integration test: real song with known structure correctly labeled

**Implementation:**

- Add `classify_section()` function in `backend/app/pipeline_proof.py`
- Update `librosa_summarize()` to call classifier after boundary detection
- Update `LessonSectionStub` schema with `label_confidence` field
- Update frontend to display confidence indicator for uncertain labels

---

### Commit 120: Authentic Chord Diagrams via chords-db Integration

**Goal:** Replace algorithmic fretboard chord shapes with authentic finger-position diagrams from
`@tombatossals/chords-db`, displaying traditional chord-box diagrams across all session screens
with multiple position alternatives and capo-aware transposition.

**Current State:** `FretboardDiagram.tsx` computes fret positions algorithmically from hardcoded
templates (E-shape, A-shape, C-shape, etc.). No traditional chord-box diagrams are rendered.
Users see colored dots on the fretboard but not the small vertical chord diagrams found in
chord books. No multiple position alternatives are offered.

**Scope:**

- Install dependencies:

  ```bash
  npm install @tombatossals/chords-db @tombatossals/react-chords
  ```

- Create chord name normalization layer (`src/music/chordDbAdapter.ts`):
  - Map Harmoniq backend format (`C:maj`, `F#:min7`) to chords-db format (`C/major`, `Fsharp/m7`)
  - Handle flat-to-sharp normalization (Bb → A#, Eb → D#, etc.)
  - Handle quality renames: `min7 → m7`, `min9 → m9`, `min6 → m6`, `alt7 → alt`, `7#5 → aug7`
  - Return `{ key, suffix }` for database lookup
- Create `ChordDiagram` component (`components/ChordDiagram.tsx`):
  - Wraps `@tombatossals/react-chords` for SVG chord-box rendering
  - Accepts `chordSymbol` prop (e.g., `"C:maj"`)
  - Retrieves all positions from chords-db for the chord
  - Default to open/low position (fret 0-5) for beginner-friendly display
  - Position cycling UI: `< 2/5 >` to browse alternative voicings
  - Displays finger numbers, barre indicators, and base fret
  - Falls back to algorithmic shapes if chord not in database
- Add chord diagrams to all session screens:
  - **study.tsx**: Small diagram above fretboard, next to current chord symbol
  - **slow.tsx**: Diagram above fretboard during slow practice
  - **play.tsx**: Compact diagram near pitch indicator during play-along
  - **review.tsx**: Diagram in playback summary for chord reference
- Layout pattern on each screen:

  ```
  ┌─────────────────────────────────┐
  │  [Diagram]  Cmaj7               │
  │           I - Tonic             │
  │           < 2/5 >               │
  └─────────────────────────────────┘
  ```

- Optional: enhance `chordToFretboardCells()` in `src/music/chordVoicing.ts`
  to use chords-db positions for fretboard dot rendering (more authentic shapes)
- Handle edge cases:
  - Slash chords: chords-db has limited `/E`, `/F`, `/G` support — fall back to algorithmic
  - Rare qualities (`7#9`, `alt7`): may not exist in database — fall back gracefully
  - Web vs native: `react-chords` renders SVG — verify on React Native,
    fall back to custom SVG rendering if needed

**Acceptance Criteria:**

- [ ] `@tombatossals/chords-db` and `@tombatossals/react-chords` installed
- [ ] `chordDbAdapter.ts` correctly maps all 277 chord types to database format
- [ ] `ChordDiagram` component renders traditional chord-box diagrams
- [ ] Position cycling works for chords with multiple voicings
- [ ] Chord diagrams displayed on study, slow, play, and review screens
- [ ] Fallback to algorithmic shapes for chords not in database
- [ ] Flat-to-sharp normalization works (Bb → A#, etc.)
- [ ] Finger numbers and barre indicators render correctly
- [ ] No regression: existing fretboard dot rendering unchanged
- [ ] Web rendering verified; native rendering verified or fallback active

**Implementation:**

- New file: `src/music/chordDbAdapter.ts` — normalization and lookup layer
- New file: `components/ChordDiagram.tsx` — chord diagram component
- New file: `components/ChordPositionSelector.tsx` — position carousel UI
- Modify: `app/session/study.tsx`, `app/session/slow.tsx`, `app/session/play.tsx`, `app/session/review.tsx`
- Optional: `src/music/chordVoicing.ts` — add chords-db fallback to `chordToFretboardCells()`

---

### Commit 121: Instrument Confusion Diagnostic (MT3 Paper Insight)

**Goal:** Add an instrument confusion diagnostic to the analysis pipeline that detects when the chord model's predictions differ significantly between the isolated stem and the full mix, flagging sections where coaching feedback should be hedged.

**Rationale (from MT3 paper, Table 3):** MT3's multi-instrument F1 shows the model rarely confuses instruments when it gets notes right (multi-instrument F1 ≈ onset-offset F1). Our pipeline has no instrument-aware evaluation — we can't distinguish "wrong chord because model confused guitar with piano" from "wrong chord because model misidentified the notes." This matters for coaching: the feedback should differ.

**Current State:** No instrument confusion detection exists. The scoring system has no way to know if a poor transcription is due to instrument interference or genuine model uncertainty.

**Scope:**

- Add instrument confusion metric to `analyze_audio.py`:
  - After dual-path inference (Commit 112), compute divergence between stem and mix predictions
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

| Persona          | Output                                             | Key features                                                                                                   |
| ---------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Learner**      | Scrolling chord chart + solo line + fretboard sync | Chord symbols over bars, color-coded fretboard, simplified notation, metronome-aligned playback                |
| **Intermediate** | Slash chord chart + beat grid                      | Slash notation (G/B, D/F#), stable beat grid with downbeat markers, chord-change timing annotations            |
| **Transcriber**  | Printable/exportable MusicXML                      | Full score with structure labels (intro/verse/chorus), measure-level formatting, MusicXML export for MuseScore |

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

### Commit 122: MT3 as Auxiliary Training Tool (Enhanced with Paper Insights)

**Goal:** Use Google's MT3 (Music Transcription Transformer) as an auxiliary tool to improve the custom pipeline — not as a replacement — via transfer learning, synthetic data generation, ensemble voting, and label bootstrapping. Enhanced with key insights from the MT3 paper (ICLR 2022).

**Rationale:** Building a custom pipeline from scratch means limited training data and no exposure to diverse instrument timbres. MT3 was trained on thousands of hours of polyphonic audio and can serve as a free pre-trained feature extractor and label generator. The custom pipeline remains the primary inference path; MT3 is a data/features/labels augmentation layer.

**Key paper insights informing this commit:**

- **Model size matters less than data diversity**: MT3's T5-small (60M params) outperformed larger models because larger models overfit on music data. Our TFLite model is already appropriately sized — focus on data, not architecture.
- **Temperature sampling is critical**: MT3's `(n_i / Σn_j)^0.3` sampling boosted guitar F1 by 263%. Apply this to our chord type sampling (see Commit 104, archived).
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
  - User corrects errors in beat grid editor / chord timeline (Commit 109/110, both archived)
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

### Commit 123: Scale/Mode Library & Interval Constants

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

### Commit 124: Scale Explorer Screen

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

### Commit 125: Fretboard Theory Overlay in Study Step

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

### Commit 126: Expanded Jam Scale Detection

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

### Commit 127: Chord Progression Labels

**Goal:** Analyze consecutive chord events to identify common progressions (ii-V-I, I-IV-V, I-vi-IV-V, etc.) and display bracketed labels on the chord timeline, helping users recognize harmonic patterns.

**Current State:** Each chord gets an independent Roman numeral from `chordFunction.ts`. No analysis of consecutive chord relationships exists. The chord timeline shows individual chord symbols only.

**Scope:**

- Define common progression patterns as sequences of scale-degree intervals:

  ```typescript
  const PROGRESSION_PATTERNS = [
    { name: "ii-V-I", degrees: ["ii", "V", "I"] },
    { name: "I-IV-V", degrees: ["I", "IV", "V"] },
    { name: "I-vi-IV-V", degrees: ["I", "vi", "IV", "V"] },
    { name: "ii-V-I-VI", degrees: ["ii", "V", "I", "VI"] },
    { name: "I-V-vi-IV", degrees: ["I", "V", "vi", "IV"] },
    { name: "i-iv-v-i", degrees: ["i", "iv", "v", "i"] },
    { name: "ii-V", degrees: ["ii", "V"] },
    { name: "V-I", degrees: ["V", "I"] },
  ];
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

### Commit 128: Slonimsky-Expanded Warmup Pool

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

### Commit 129: Slonimsky Pattern Generator ("Lick of the Day")

**Goal:** Build an algorithmic generator that creates a new melodic pattern each practice session from Slonimsky principles — interpolation, infrapolation, ultrapolation — transposed to the user's current key/scale of focus and rendered as tab/fretboard with optional backing. Feeds the "Daily Lick" concept from Phase 3 Discovery.

**Current State:** No algorithmic pattern generation exists. The "Daily Lick" in Phase 3 is aspirational with no implementation. The warmup pool is hand-written JSON only.

**Scope:**

- Create `src/music/slonimskyGenerator.ts` (frontend-side, for fast local generation):

  ```typescript
  interface SlonimskyPattern {
    name: string;
    family: "interpolation" | "infrapolation" | "ultrapolation" | "compound";
    baseInterval: number; // semitones
    patternNotes: number[]; // absolute MIDI notes
    fretboardCells: { string: number; fret: number; finger: number }[];
    difficulty: 1 | 2 | 3 | 4 | 5;
    description: string;
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

### Commit 130: Inversion & Slash Chord Logic

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

### Commit 131: Voicing & Position Inference

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

### Commit 132: Live Mic Mode

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

### Commit 133: The "Chord Pulse" Dashboard

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

### Commit 134: Multi-Instrument Diagram Support

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

### Commit 135: 6-Stem High-Fidelity Demucs

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

### Commit 136: Real-Time Stem Mixer & Export — Extended with Stem Routing Override

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

### Commit 137: Dynamic Session Engine

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

### Commit 138: Orient-as-Hint

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

### Commit 139: Mastery & Integrity

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

### Commit 140: Dynamic Tempo Support (Variable BPM)

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

### Commit 141: Redis Job Queue + Celery Workers + Push-Based Job Updates

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
- **Progressive job status stages** (in `JobStatus` schema, shared with Commit 109 [archived]):
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

### Commit 142: Dedicated ML Model Server

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

### Commit 143: GPU Job Queue for Demucs

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

### Commit 144: Error Resilience (Circuit Breakers, Retry, DLQ)

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

### Commit 145: Monitoring & Observability (Prometheus, Grafana)

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

### Commit 146: Audio Fingerprinting & Quality Scoring

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

### Commit 147: Solo Harmony Enrichment — Chord-Tone Classification & Position Inference

**Goal:** Post-process raw Basic Pitch solo notes through a harmony analysis layer that labels every note with its role in the current chord (root, 3rd, 5th, tension, chromatic) and infers the fretboard position (CAGED shape) per bar — making solo output "make sense" as a musical narrative, not just raw MIDI events.

**Current State:** Solo inference via Basic Pitch (`solo_inference.py:283`) runs independently of chord inference. The two outputs are stored as sibling fields in LessonJSON (`chord_timeline` vs `solo_notes`) with zero cross-referencing. A user sees "MIDI 59, 62, 64" instead of "B2, D3, E4 over G:maj7 — that's the 3rd and 5th of the chord resolving to the root." No position/CAGED inference exists — `guitar_position.py` only converts individual MIDI notes to string/fret for MusicXML rendering, with no per-bar shape awareness.

**Scope:**

- **New module: `backend/app/solo_harmony_analyzer.py`:**
  - `ChordToneClassifier`: takes chord `(root, quality)` + MIDI pitch → `{ scale_degree, scale_degree_name, chord_tone_type, semitone_distance }`
    - Parse chord string (e.g. `"G:maj7"`) into root pitch class + interval set using existing `chord_vocab.py`
    - Normalize MIDI pitch to pitch class (0–11)
    - Match against chord intervals → "chord_tone" (exact match), "tension" (in key via Krumhansl-Schmuckler root but not in chord), "chromatic" (outside key)
    - Return human-readable label: `"R"`, `"b3"`, `"3"`, `"5"`, `"b7"`, `"7"`, etc.
  - `PositionInferenceEngine`: given MIDI notes + chord + key → inferred CAGED position label
    - For each of 5 CAGED shapes of the current chord, check if played notes are reachable within a 4-fret span on adjacent strings
    - Score each shape: hit rate × span tightness
    - Winner → label like `"position 2 (CAGED: E-form)"`
    - Uses existing `guitar_position.py` for string/fret mapping
  - `SoloHarmonizer`: orchestrator — takes `ChordTimeline` + `SoloNotes` + `BeatGrid` + key
    - Per solo note: look up active chord from timeline, classify tone, attach context
    - Per bar: collect notes, infer position, suggest scale(s)
    - Aggregate into enriched output structures

- **New schemas in `backend/app/schemas.py`:**
  - `ChordToneAnalysis`: `{ scale_degree: int, scale_degree_name: str (e.g. "b7", "3"), chord_tone_type: Literal["chord_tone", "tension", "chromatic", "pedal"], semitone_distance: int }`
  - `BarScope`: `{ bar_index: int, start_time: float, end_time: float, chord: str | None, suggested_scales: list[str], primary_position: str | None, notes: list[int] }`
  - `HarmonizedSoloNotes`: `{ notes: list[ { start_time, duration, pitch, velocity, chord: str | None, chord_analysis: ChordToneAnalysis | None } ], note_count: int, chord_tone_pct: float, tension_note_pct: float, chromatic_pct: float }`

- **Add to `LessonJSON` schema:**
  - `harmonized_solo: HarmonizedSoloNotes | None = None`
  - `per_bar_analysis: list[BarScope] | None = None`
  - Both optional with `None` fallback (no regression when analysis is unavailable)

- **Pipeline integration in `backend/app/analyze_audio.py`:**
  - After both `infer_chords` and `infer_solo` complete (after line 287), call `SoloHarmonizer`:
    ```python
    harmonized_solo = None
    per_bar = None
    if chord_timeline and solo_notes and chord_timeline.events and solo_notes.notes:
        try:
            harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, summary.key_name)
            harmonized_solo = harmonizer.harmonized_solo
            per_bar = harmonizer.per_bar_analysis
        except Exception:
            logger.exception("solo harmony analysis failed for job_id=%s; skipping", job_id)
    ```
  - Pass into `LessonJSON` constructor
  - Falls back silently (no regression) when chords, solo, or key are unavailable

- **Frontend types in `src/types/soloHarmony.ts`:**
  - TypeScript mirrors of `ChordToneAnalysis`, `BarScope`, `HarmonizedSoloNotes`
  - `chord_tone_type` as `'chord_tone' | 'tension' | 'chromatic' | 'pedal'`

- **Tests in `backend/tests/test_solo_harmony_analyzer.py`:**
  - Pitch 60 (C4) against "C:maj" → root, scale_degree=1, chord_tone
  - Pitch 64 (E4) against "C:maj" → 3rd, scale_degree=3, chord_tone
  - Pitch 65 (F4) against "C:maj" → 4th, tension (in G major scale, not in C chord)
  - Pitch 66 (F#4) against "C:maj" → chromatic (outside key)
  - Position inference: known solo phrase against known chord → correct CAGED label
  - Edge: no chord at note time → chord_analysis = null
  - Edge: "N" (no-chord) beats → skip analysis
  - Edge: empty chord_timeline or solo_notes → graceful None return

**Not in scope (follow-up commits):**
- Frontend display of enriched data (Study fretboard overlay, Review feedback) — Commit 125 already covers theory overlay
- Claude coaching prompt changes to reference chord-tone data — belongs in coach prompt tuning
- Position inference refinement (beyond CAGED) — can be iterated later

**Acceptance Criteria:**

- [ ] `ChordToneClassifier` correctly classifies a pitch against any of the 277 chord types
- [ ] `PositionInferenceEngine` returns CAGED label for known solos with ≥70% accuracy
- [ ] `SoloHarmonizer` runs silently after chord+solo inference; never blocks the pipeline
- [ ] `HarmonizedSoloNotes` contains per-note chord context for every note with a matching chord
- [ ] `per_bar_analysis` contains per-bar position inference for bars with active solo notes
- [ ] Both fields are `None` when chord_timeline or solo_notes is empty (no regression)
- [ ] All backend tests pass (`python -m pytest -q`)
- [ ] No new dependencies required (uses existing `chord_vocab.py`, `guitar_position.py`, `schemas.py`)
- [ ] Integration test: full song analysis → harmonized solo output with chord-tone percentages

---

### Supporting Improvements (absorbed into existing commits)

The following improvements are already partially scoped in existing commits.
Extend their scope rather than creating new entries:

| Concern                                                     | Existing commit                                         | Extension                                                                                                                                                                                                                                                                                                                                                                                                             |
| ----------------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Perceptual audio fingerprinting                             | **Commit 146** (Audio Fingerprinting & Quality Scoring) | Already covers Chromaprint-based cache keys. Ensure fallback to SHA256 when fingerprinting unavailable.                                                                                                                                                                                                                                                                                                               |
| On-device real-time chord inference                         | **Commit 132** (Live Mic Mode)                          | Add React Native TFLite bridge for `chord_model.tflite` inference on mic input. Web path: TensorFlow.js or ONNX runtime. Reuse existing model.                                                                                                                                                                                                                                                                        |
| Confidence-weighted ensemble                                | **Commit 99** (Viterbi Decoding)                        | Before Viterbi smoothing, run TFLite model + Basic Pitch harmonic analysis + librosa chroma features through a weighted voting layer. Track per-chord confidence as weighted average.                                                                                                                                                                                                                                 |
| Generative accompaniment (Lyria)                            | Already exists in `jam_backing.py`                      | Use `BeatGrid` as a conditioning signal: generate MIDI patterns locked to the detected beat grid and chord changes, then render through AlphaTab's SoundFont.                                                                                                                                                                                                                                                         |
| AlphaTab WebView hardening (CDN, message protocol, offline) | **Commit 108** (MusicXML as Primary Render Format, archived) | Bundle AlphaTab JS locally via Metro asset instead of jsDelivr CDN for offline support; tighten `postMessage` `targetOrigin` from `'*'` to explicit allowed origins; align SoundFont timeout values (25s harness vs 16s web path); wire prerender SVG display on native WebView; add navigation gating unit tests with malicious URL corpus; add CDN-unreachable fallback path that loads AlphaTab from bundled asset |

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
