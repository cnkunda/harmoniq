# Harmoniq — Engineering Roadmap

Three-phase product roadmap for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**. **Phase 2 commits 98–121** — archived. **Phase 2 commits 122–148** — archived (superseded by MT3-primary strategy). **NEW Phase 2** — MT3-Powered MVP & Product Completion.

---

## At a glance

|                    |                                                                      |
| ------------------ | -------------------------------------------------------------------- |
| **Roadmap status** | **Phase 2: MT3-Powered MVP & Product Completion. Phase 3: Planned.** |
| **Product spec**   | [`README.md`](README.md)                                             |
| **UI spec**        | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md)                               |
| **E2E / release**  | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md)                               |
| **Manual QA**      | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md)                             |
| **Scoring**        | [`docs/SCORING.md`](docs/SCORING.md)                                 |
| **Archive**        | [`priorities-archive.md`](priorities-archive.md) (Phase 0 + Phase 1 + Phase 2 commits 98-148) |

---

## PHASE 2: MT3-Powered MVP & Product Completion

**Status:** In Progress — all pre-MT3 commits 98-148 archived. Phase is rebuilt around MT3 as the primary transcription engine with the custom CRNN as on-device/inference fallback.

**Strategic rationale:**

The custom chord model hit a hard data ceiling. Training log v1.0.5 shows **34.7% real validation accuracy** vs **70.3% synthetic** — a persistent **35.6-point domain gap** that advanced architecture changes (multi-task heads, distribution matching, PCA perturbation) could not close. Available labeled data (12,825 real CQT windows) is simply insufficient for a production-quality AMT model.

Google's MT3 (Music Transcription Transformer, ICLR 2022) solves this: a T5-small backbone (60M params) trained on thousands of hours of multi-instrument audio. It outputs a token-level event stream that encodes both chords and solo notes simultaneously — exactly the dual output Harmoniq needs.

**Why keep the custom model:**
- On-device real-time inference (Live Mic Mode, <120ms latency) — MT3 is too large to run on-device
- Fallback when the MT3 server is unavailable
- Long-term distillation target: use MT3-generated pseudo-labels to train a smaller student model

**Architecture:**

```
Audio → Demucs 6-stem → guitar stem → MT3 inference ─┬→ Chord Timeline (event decoder)
                                                        └→ Solo Notes (event decoder)
                                                              ↓
                                              CRNN TFLite (on-device fallback)
                                              Chroma matching (tertiary fallback)
```

---

### Milestone A: MT3-Primary AMT Pipeline

**Goal:** Replace the CRNN + Basic Pitch analysis pipeline with MT3 as the primary backend transcription engine, producing simultaneous chord and solo note outputs with higher accuracy.

**Scope:**

#### A1 — MT3 Inference Backend
- **DONE - Commit A1.1** — MT3 Model Server:
  - Download and serve MT3 checkpoint (T5-small, ~236M params checkpoint) via a dedicated FastAPI service or subprocess
  - Accept audio tensor input (44.1kHz mono guitar stem, resampled to 16kHz for MT3)
  - Run inference via JAX inference path (preserve GPU support) or TF Serving
  - Output raw token-level event stream: onset, pitch, velocity, instrument, offset per event
  - Multi-track event stream covers all detected notes, not just guitar — filter by instrument class (piano/guitar = keep, drums/vocals = discard)
  - Warm-start model loading on server boot; cache model weights in `data/models/mt3/`
  - API spec: `POST /mt3/infer` → accepts WAV path, returns `Mt3EventStream` (list of `{time, pitch, velocity, program, is_onsetevent, is_offsetevent}`)
  - Batch mode for multi-song processing
  - Graceful degradation: if MT3 server is unavailable, fall back to existing CRNN + Basic Pitch pipeline

- **DONE - Commit A1.2** — MT3 Event Stream → Chord Decoder:
  - Convert MT3 multi-track event stream into chord timeline via music21 deterministic analysis
  - For each time slice (0.1s hops): aggregate all sounding pitches → pitch class set → match against `CHORD_INTERVALS` template set (same methodology as Guitar-TECHS/EGSet12 parsing — Jaccard score, >0.66 coverage threshold)
  - Output 277-class vocabulary but map to 25-class MIREX for consistency with existing frontend chord display
  - Per-chord confidence derived from pitch set coverage fraction
  - Handle polyrhythmic sections: if simultaneous guitar and piano detected, prefer guitar pitches for chord inference
  - Handle non-chord regions (rests, percussion-only): emit "N" (no-chord) when pitch density falls below threshold

- **Commit A1.3** — MT3 Event Stream → Solo Notes Decoder:
  - Filter MT3 events for monophonic or primary melodic line (highest confidence pitch track)
  - Convert event stream to `SoloNotes` format compatible with existing `solo_notes` field in `LessonJSON`
  - Apply quantization to nearest beat grid position (existing `beat_grid.py`)
  - Apply tie detection across boundaries (reuse `TieRegistry` from `solo_inference.py`)
  - Extract technique tags: detect bends (pitch slides), vibrato (rapid pitch modulation), grace notes (sub-50ms onsets)
  - Confidence per note: `mt3_event.confidence * pitch_set_coherence`

- **Commit A1.4** — Dual-Output LessonJSON Assembly:
  - Merge chord timeline + solo notes into single `LessonJSON` response
  - Ensure sync: chord events and solo notes share the same beat grid, bar timestamps, and time base
  - Add `transcription_source: "mt3"` field to LessonJSON so frontend knows which pipeline produced the data
  - Pass through existing downstream steps: MusicXML generation, section refinement, coach copy hydration
  - Integration test: known song → MT3 → chord timeline matches ground-truth progression within 85% accuracy

#### A2 — Confidence-Adaptive Fallback Chain

- **Commit A2.1** — Fallback Orchestrator:
  - Implement fallback chain: `MT3 → CRNN TFLite → Chroma matching`
  - At each stage, evaluate `confidence` (MT3: mean event confidence; CRNN: softmax max-prob; Chroma: template correlation score)
  - Use MT3 output if `mean_confidence > 0.7`; fall back to CRNN if MT3 confidence low or MT3 server unavailable; fall back to Chroma if no model available
  - Track fallback decisions in `transcription_metadata` for observability
  - Log per-song: which tier produced the result, and why higher tiers were skipped

- **Commit A2.2** — On-Device CRNN TFLite Preservation:
  - Keep existing `chord_model.tflite` in `backend/app/` for on-device inference path (Live Mic Mode)
  - Keep `chord_inference.py` as-is — it becomes the fallback inference engine
  - CRNN training pipeline (`build_chord_tflite.py`) retained for long-term distillation training
  - The CRNN now serves two roles: (1) on-device real-time inference, (2) future student model for MT3 distillation

#### A3 — Live Mic Mode (On-Device MT3-Distilled or CRNN)
- **Commit A3.1** — React Native TFLite Bridge:
  - Implement low-latency (<120ms) real-time chord detection from mic input using the CRNN TFLite model
  - Web path: TensorFlow.js or ONNX runtime runtime
  - Mobile path: TFLite C++ API via JSI bridge (or TF Lite React Native binding)
  - UI: "Active Listener" screen with live chord display, confidence meter, and history stream
  - Long-term: replace CRNN with MT3-distilled student model (Phase 3)

**Acceptance Criteria for Milestone A:**

- [ ] MT3 inference server processes a 4-minute song in <60 seconds (GPU) or <5 minutes (CPU)
- [ ] MT3 chord accuracy on GuitarSet test set ≥ 80% (25-class MIREX) — baseline: CRNN 34.7%
- [ ] MT3 solo note transcription accuracy on GuitarSet monophonic sections ≥ 85% (onset F1)
- [ ] Chord timeline and solo notes are temporally aligned to the same beat grid
- [ ] Fallback chain produces valid output even when MT3 server is down
- [ ] On-device CRNN TFLite inference <120ms per chord frame on a Pixel 7 / iPhone 13
- [ ] All existing `npm run lint`, `npm run test`, `pytest` tests pass
- [ ] Integration test: known song → full pipeline → LessonJSON with both chord and solo data
- [ ] `transcription_source` field populated correctly per job
- [ ] Fallback tier logged per job for observability

---

### Milestone B: Fretboard Dual-Mode Optimization

**Goal:** Optimize the fretboard and session UI for simultaneous chord and solo line display — the core UX differentiator powered by MT3's dual output.

**Current state:** `FretboardDiagram` already supports a `mode` toggle (`auto | chords | solo | both`) with amber chord circles and red solo note circles. `ChordsAndLyrics` shows bar-by-bar chord symbols. `MusicContext` wires `currentChord` and `activeNotes` to playback position. The foundation is solid — this milestone polishes it for the MT3 dual-output richness.

#### Commit B1: Fretboard Dual-View Polish
- **Scope:**
  - Refine the four-mode toggle (`chords`, `solo`, `both`, `auto`):
    - `auto` = intelligent default: show solo notes with faint chord shape background
    - `chords` = existing chord circles only
    - `solo` = existing solo note red circles + pitch labels only
    - `both` = chord circles (amber, 30% opacity) + solo notes (red, 100% opacity) overlaid
  - Chord-solo visual separation:
    - Chord shape rendered as filled circles (amber `#D4A574`, `opacity=0.4`)
    - Active solo note rendered as glowing circles (terracotta `#C17B5F` core, amber `#E8B86D` glow ring, `opacity=1.0`)
    - When a solo note matches a chord tone, show a dual-color ring (amber outer, terracotta inner)
    - When a solo note is outside the current chord (tension/chromatic), show a purple indicator ring
  - Real-time note detail on tap: extend `SessionNoteDetailModal` to show:
    - Note name + octave
    - Chord tone status: chord tone (green), tension (amber), chromatic/outside (red)
    - Scale degree in current key
    - Finger suggestion (reuse existing `fingerSuggestion.ts`)
    - "Confidence: 87%" from MT3 event confidence
  - Fretboard responsiveness: larger touch targets on mobile for note selection
  - Keyboard shortcut overlay on web (reuse existing keyboard input)

- **Acceptance Criteria:**
  - [ ] Four-mode toggle cycles correctly with instant visual feedback
  - [ ] `both` mode clearly distinguishes chord shapes from active solo notes
  - [ ] Dual-color rings show when solo note matches chord tone
  - [ ] Purple ring shows when solo note is outside chord (tension/chromatic)
  - [ ] Tapped note displays chord tone status correctly
  - [ ] MT3 confidence shown in note detail
  - [ ] No regression on existing `chords` and `solo` modes
  - [ ] Touch targets ≥ 44px on mobile

#### Commit B2: Harmonic Context Overlay
- **Scope:**
  - Derive scale pitch classes from song key (using new `src/music/scales.ts`)
  - Three visual tiers on `FretboardDiagram`:
    - **Scale tones** — faint green circles (15% opacity) for notes in the key
    - **Chord tones** — existing amber circles for current chord notes
    - **Outside tones** — no highlight (gray or invisible)
  - Toggle in Study toolbar: "Key context" / "Chord only" / "Off"
  - Add `scalePitchClasses` to `MusicContext` alongside existing `chordEvents`/`soloNotesArr`
  - Compute from lesson key on section load

- **Acceptance Criteria:**
  - [ ] Scale tones visible as green circles when "Key context" mode active
  - [ ] Chord tones render on top of scale tones
  - [ ] Outside notes have no highlight
  - [ ] Toggle cycles through three modes
  - [ ] Tapped note displays scale degree and chord tone status

#### Commit B3: Expanded Jam Scale Detection
- **Scope:**
  - Replace 6-template pentatonic-only matcher with full 30+ scale library from `src/music/scales.ts`
  - Improved scoring: weighted = 0.5 × overlap + 0.3 × root alignment + 0.2 × pentatonic skeleton match
  - Surface detected mode in Jam UI with top 3 candidates and confidence bars
  - Add `inferred_mode` field to `BestScaleMatch` and `jam_snapshots`

- **Acceptance Criteria:**
  - [ ] Jam detects all 7 diatonic modes, not just pentatonic
  - [ ] Weighted scoring used for mode detection
  - [ ] Top 3 candidates shown with confidence bars
  - [ ] Confidence < 0.5 shows "Mixed mode" with note bias breakdown

#### Commit B4: Scale/Mode Library (Foundational)
- **Scope:**
  - Create `src/music/scales.ts` with 30+ scales as pitch class sets (diatonic, harmonic/melodic minor, pentatonic, symmetrical)
  - Create `src/music/intervals.ts` with `Interval` enum and helper functions
  - Export as `SCALE_DB: Record<string, ScaleEntry>`
  - Unit tests for all scales

- **Acceptance Criteria:**
  - [ ] All 30+ scales exported as pitch class sets
  - [ ] Interval enum and helpers exported
  - [ ] Unit tests verify correctness

#### Commit B5: Scale Explorer Screen
- **Scope:**
  - `app/scale-explorer/index.tsx` — interactive scale browser
  - Scale picker with root + mode selection, grouped by family
  - Fretboard highlighting with scale degrees, note names, interval overlays
  - CAGED position zones, tap-to-audition, "Play scale" with tempo
  - Favorites persisted to SQLite

- **Acceptance Criteria:**
  - [ ] Scale picker shows all 30+ scales
  - [ ] Fretboard highlights with root distinguished
  - [ ] Overlay toggles work correctly
  - [ ] Note audition and scale playback functional

#### Commit B6: Chord Progression Labels
- **Scope:**
  - Sliding-window progression matcher in `src/music/progressionAnalysis.ts`
  - Define common patterns (ii-V-I, I-IV-V, etc.)
  - Bracketed labels below chord symbols in timeline
  - Educational tooltip on tap

- **Acceptance Criteria:**
  - [ ] Sliding window matches common progressions
  - [ ] ii-V-I in C major correctly labeled
  - [ ] Bracketed annotations display below chord symbols
  - [ ] Tapping label shows educational tooltip

#### Commit B7: Warmup Pool Expansion + Slonimsky Generator
- **Scope:**
  - Add 15+ Slonimsky exercises to `warmup_pool.json` (3 families + compound)
  - Algorithmic pattern generator in `src/music/slonimskyGenerator.ts`
  - Daily lick rotation for home screen
  - Difficulty-aware selection

- **Acceptance Criteria:**
  - [ ] 15+ Slonimsky exercises added with valid fretboard data
  - [ ] Pattern generator produces valid `SlonimskyPattern` objects
  - [ ] Daily lick appears on home screen and persists to `licks` table
  - [ ] Difficulty scales by player skill level

#### Commit B8: Chord Inversion & Slash Notation
- **Scope:**
  - Add `bass` field to `ChordEvent` schema
  - Extract bass note from low CQT bins (or MT3 event stream lowest note)
  - Emit `<bass>` in MusicXML when bass ≠ root
  - Inversion identification (1st/2nd)

- **Acceptance Criteria:**
  - [ ] `ChordEvent.bass` stores detected bass note
  - [ ] `<bass>` element emitted in MusicXML when needed
  - [ ] Inversions identified from bass note analysis

#### Commit B9: Voicing & Position Inference
- **Scope:**
  - Spectral/event analysis for voicing detection
  - CAGED shape recognition from MT3 pitch distribution
  - Position inference from note clustering

- **Acceptance Criteria:**
  - [ ] E-shape vs A-shape voicings distinguished
  - [ ] CAGED positions inferred from pitch data
  - [ ] Fretboard diagrams reflect detected voicing

---

### Milestone C: Engagement & Retention Features

**Commit C1: User Feedback & Manual Overrides**
- UI for users to mark incorrect notes/chords
- Backend persistence of corrections
- Corrections feed into MT3 distillation dataset for future custom model training

**Commit C2: Jam Mode Summary Agent**
- Claude-powered post-jam analysis and vocabulary mapping
- Persona-switching via system prompt
- Output schema: `{ chord, clarity, intonation_cents, timing_ms, transition_from, transition_gap_ms }`

**Commit C3: Play Engagement Analytics**
- Lightweight event analytics (custom event bus, no third-party SDK)
- Track play-along duration, discard events, session step progression
- Per-user per-song engagement metrics
- Local DB persistence with batched writes
- Opt-out privacy notice

**Commit C4: Dynamic Session Engine**
- PlanJSON ingestion + orchestrator for dynamic practice plans via SM-2
- Plan: Warmup → Song Workflow → Jam Session
- Caching in SQLite for resumption

**Commit C5: Orient-as-Hint**
- Remove Orient as linear step; integrate as non-intrusive amber overlay in Study/Play with '?' toggle

**Commit C6: Mastery & Integrity**
- Atomic SQLite updates for dynamic sessions with dual-entry state integrity
- Single file mode + dynamic session mode

**Commit C7: Chord Pulse Dashboard**
- Scrolling chord timeline with falling notes visualizer
- Beat-synced Pulse ring animation on downbeats

**Commit C8: Three-Tier Output Strategy**
- Learner / Intermediate / Transcriber personas from shared LessonJSON
- Learner: scrolling chord chart + solo line + fretboard sync
- Intermediate: slash chords + beat grid
- Transcriber: printable MusicXML

**Commit C9: Multi-Instrument Diagram Support**
- Guitar, Piano, Ukulele diagram toggles
- Alternate tuning support

---

### Milestone D: Infrastructure & Scale

**Commit D1: Stem Mixer & Export (Extended)**
- Real-time mute/solo per-stem UI
- Stem routing override for analysis correction
- Individual stem .WAV export

**Commit D2: Dynamic Tempo Support**
- Variable BPM songs with tempo ramps, accelerandos
- Replace `_uniform_beat_grid()` with tempo curve support
- Store tempo change events in BeatGrid schema

**Commit D3: Redis/Celery Job Queue**
- Replace in-memory job store with Redis-backed queue
- Celery workers for horizontal scaling
- SSE push-based job status updates (fixes BUG-01)
- Progressive job status stages

**Commit D4: GPU Job Queue for Demucs**
- Priority scheduling for Demucs stem separation
- Queue depth management and GPU utilization tracking

**Commit D5: Error Resilience**
- Circuit breakers, exponential backoff, dead letter queues
- Retry for YouTube failures, circuit breaker for LLM API calls

**Commit D6: Monitoring & Observability**
- Prometheus metrics, per-stage latency histograms
- Error rate alerting, distributed tracing (OpenTelemetry)

**Commit D7: Audio Fingerprinting & Quality Scoring**
- Chromaprint-based duplicate detection
- SNR/clipping quality scoring
- Fingerprint-based cache key alongside SHA256

**Commit D8: Smart Capo Suggestions**
- Optimal capo calculation from detected key and position
- Open chord shape mapping for preferred voicings

**Commit D9: Predictive Beat Recovery**
- Look-ahead algorithm for tempo drift and syncopation handling
- Dynamic beat grid adjustment

---

## PHASE 3: Custom Model Distillation & AI-Agent Scaling

**Status:** Planned

### Milestone: MT3 Distillation (Custom Model 2.0)

Once MT3 is powering production, use its pseudo-labels + the existing CRNN training infrastructure to train a much smaller student model that approaches MT3 accuracy.

**Approach:**
- MT3 runs on all labeled + unlabeled song audio → generates pseudo-labels with confidence scores
- Filter pseudo-labels at confidence > 0.9 → creates a training set 10-100× larger than current labeled data
- Train student CRNN (TFLite-friendly, <600KB) on MT3 pseudo-labels + existing real labels
- Knowledge distillation loss: KL divergence between MT3 teacher logits and student logits (in addition to standard cross-entropy on labels)
- Target: student model achieves >70% GuitarSet accuracy while running on-device

**If student model reaches production quality:**
- Swap MT3 for student model in the backend pipeline (reduced cost, faster inference)
- Keep MT3 as teacher for continued distillation (label refreshes on new data)
- On-device inference gets a major upgrade from 34.7% → 70%+ accuracy

**If student model plateaus below production bar:**
- MT3 remains the primary backend engine
- Student model stays as on-device fallback
- Invest in dataset expansion (more real labeled recordings, better coverage of non-triad chords)

### Milestone: Lead Sheet Agent
Agentic workflow to convert MIDI + Whisper lyrics into structured MusicXML.

### Milestone: Zero-Latency Monitoring
C++/JSI bridge for sub-millisecond pitch detection on mobile.

### Milestone: Dynamic Backing Track Agent
Lyria-powered AI instrumental generation, fallback to bundled loops.

### Milestone: Virtual Mentor Agent
Long-term skill trajectory analysis, plateau detection, non-linear practice recommendations.

---

### Product Strengthening
- Infrastructure limitations (Redis/Celery, retry logic, Demucs GPU queue) addressed in Milestone D
- Offline mode: SQLite local-first with periodic Cloud sync
- Discovery: "Daily Lick" curated feed
- Accessibility: high-contrast modes, screen-reader support

---

## At a glance: what changed

| Before (old Phase 2) | After (new Phase 2) |
|----------------------|---------------------|
| Custom CRNN model as primary AMT engine | **MT3 as primary AMT engine** |
| Commit 122: Model overhaul to fix 11.9% accuracy | **Archived** — MT3 delivers >80% out of the box |
| Commit 148: MT3 as auxiliary tool | **Replaced** — MT3 is now primary, not auxiliary |
| Multi-task model architecture (6-output) | **Deferred** to Phase 3 distillation (backed by MT3 data) |
| 277-class chord model training | **Preserved** for long-term distillation pipeline |
| 5-fold GuitarSet CV, CQT visualization | **Archived** — no longer critical path |
| Basic Pitch for solo transcription | **Replaced** by MT3's simultaneous chord+solo output |
| Fretboard as secondary concern | **Elevated** — dual-mode display is the core UX differentiator |

---

## Acceptance Criteria (Phase 2 release gate)

All commits within each milestone must meet their individual ACs. The Phase 2 release gate additionally requires:

- [ ] MT3-powered pipeline produces chord-solo LessonJSON for any uploaded song
- [ ] Fretboard dual-mode toggle works across Listen, Study, Slow, Play, Review steps
- [ ] Fallback chain never produces empty/null result (always degrades gracefully)
- [ ] 10-song smoke test: 5 studio recordings + 5 live performances → all produce valid chord timelines
- [ ] `npm run lint`, `npm run test`, `pytest` pass
- [ ] Manual QA sign-off on session loop for MT3-powered songs vs CRNN-powered songs
