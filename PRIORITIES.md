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
- Long-term distillation target: use MT3-generated pseudo-labels to train two smaller student models — a framewise chord student (non-autoregressive, piano-roll) and a guitar-vocabulary token solo student (autoregressive, program-filtered)

**Architecture — two-branch (chord/solo split):**

```
Audio → Demucs 6-stem ─┬→ full mix / harmonic bed ─→ Branch A: MT3 (Flat granularity) ─→ Chord Timeline
                        │                               or chroma extractor
                        │
                        └→ guitar stem (as soft prior) ─→ Branch B: MT3 conditioned on                           ─→ Solo Notes
                            + full mix (parallel feature)   guitar-program embedding
                                                             + MR-MT3 memory retention
                                                             + prior token sampling
                                                             + token shuffling
                                                             + post-hoc program filter
                                                                  ↓
                                                  CRNN TFLite (on-device fallback for chords, full mix)
                                                   │  quality gate: >80% N → chroma
                                                  Chroma matching (tertiary fallback for chords)
```

**CRNN quality gate:** When the neural model predicts >80% N (no-chord) across frames, `_neural_model_too_noisy()` in `chord_inference.py` bypasses the CRNN result and falls through to chroma template matching. This handles the known 34.7% real accuracy limitation where the model defaults to N on unfamiliar audio.

**Basic Pitch caching:** `basic_pitch_predict_events()` in `pipeline_proof.py` caches results by audio path and model variant. Prevents duplicate 60s+ Basic Pitch inference between solo note extraction and tab generation — the solo inference path (`solo_inference.py`) and tab generation path both call the same cached function.

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
  - [x] Four-mode toggle cycles correctly with instant visual feedback
  - [x] `both` mode clearly distinguishes chord shapes from active solo notes
  - [x] Dual-color rings show when solo note matches chord tone
  - [x] Purple ring shows when solo note is outside chord (tension/chromatic)
  - [x] Tapped note displays chord tone status correctly
  - [x] MT3 confidence shown in note detail
  - [x] No regression on existing `chords` and `solo` modes
  - [x] Touch targets ≥ 44px on mobile

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
  - [x] Scale tones visible as green circles when "Key context" mode active
  - [x] Chord tones render on top of scale tones
  - [x] Outside notes have no highlight
  - [x] Toggle cycles through three modes
  - [x] Tapped note displays scale degree and chord tone status

#### Commit B3: Expanded Jam Scale Detection
- **Scope:**
  - Replace 6-template pentatonic-only matcher with full 30+ scale library from `src/music/scales.ts`
  - Improved scoring: weighted = 0.5 × overlap + 0.3 × root alignment + 0.2 × pentatonic skeleton match
  - Surface detected mode in Jam UI with top 3 candidates and confidence bars
  - Add `inferred_mode` field to `BestScaleMatch` and `jam_snapshots`

- **Acceptance Criteria:**
  - [x] Jam detects all 7 diatonic modes, not just pentatonic
  - [x] Weighted scoring used for mode detection
  - [x] Top 3 candidates shown with confidence bars
  - [x] Confidence < 0.5 shows "Mixed mode" with note bias breakdown

#### Commit B4: Scale/Mode Library (Foundational)
- **Scope:**
  - Create `src/music/scales.ts` with 30+ scales as pitch class sets (diatonic, harmonic/melodic minor, pentatonic, symmetrical)
  - Create `src/music/intervals.ts` with `Interval` enum and helper functions
  - Export as `SCALE_DB: Record<string, ScaleEntry>`
  - Unit tests for all scales

- **Acceptance Criteria:**
  - [x] All 30+ scales exported as pitch class sets
  - [x] Interval enum and helpers exported
  - [x] Unit tests verify correctness

#### Commit B5: Scale Explorer Screen
- **Scope:**
  - `app/scale-explorer/index.tsx` — interactive scale browser
  - Scale picker with root + mode selection, grouped by family
  - Fretboard highlighting with scale degrees, note names, interval overlays
  - CAGED position zones, tap-to-audition, "Play scale" with tempo
  - Favorites persisted to SQLite

- **Acceptance Criteria:**
  - [x] Scale picker shows all 30+ scales
  - [x] Fretboard highlights with root distinguished
  - [x] Overlay toggles work correctly
  - [x] Note audition and scale playback functional

#### Commit B6: Chord Progression Labels
- **Scope:**
  - Sliding-window progression matcher in `src/music/progressionAnalysis.ts`
  - Define common patterns (ii-V-I, I-IV-V, etc.)
  - Bracketed labels below chord symbols in timeline
  - Educational tooltip on tap

- **Acceptance Criteria:**
  - [x] Sliding window matches common progressions
  - [x] ii-V-I in C major correctly labeled
  - [x] Bracketed annotations display below chord symbols
  - [x] Tapping label shows educational tooltip

#### Commit B7: Warmup Pool Expansion + Slonimsky Generator
- **Scope:**
  - Add 15+ Slonimsky exercises to `warmup_pool.json` (3 families + compound)
  - Algorithmic pattern generator in `src/music/slonimskyGenerator.ts`
  - Daily lick rotation for home screen
  - Difficulty-aware selection

- **Acceptance Criteria:**
  - [x] 15+ Slonimsky exercises added with valid fretboard data
  - [x] Pattern generator produces valid `SlonimskyPattern` objects
  - [x] Daily lick appears on home screen and persists to `licks` table
  - [x] Difficulty scales by player skill level

#### Commit B8: Chord Inversion & Slash Notation
- **Scope:**
  - Add `bass` field to `ChordEvent` schema
  - Extract bass note from low CQT bins on full mix (or Branch A's aggregate pitch representation — never from the guitar-stem-only event stream, since the guitar often does not play the bass note)
  - Emit `<bass>` in MusicXML when bass ≠ root
  - Inversion identification (1st/2nd)

- **Acceptance Criteria:**
  - [x] `ChordEvent.bass` stores detected bass note
  - [x] `<bass>` element emitted in MusicXML when needed
  - [x] Inversions identified from bass note analysis

#### Commit B9: Voicing & Position Inference
- **Scope:**
  - Spectral/event analysis for voicing detection
  - CAGED shape recognition from MT3 pitch distribution
  - Position inference from note clustering

- **Acceptance Criteria:**
  - [x] E-shape vs A-shape voicings distinguished
  - [x] CAGED positions inferred from pitch data
  - [x] Fretboard diagrams reflect detected voicing

---

### Milestone C: Engagement & Retention Features

**Commit C1: User Feedback & Manual Overrides**
- UI for users to mark incorrect notes/chords
- Backend persistence of corrections
- Corrections route to two distillation sets: chord corrections → Branch A chord student's training set; note/solo corrections → Branch B solo student's training set

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

### Milestone 3A: Chord Student Distillation

Once Branch A (full-mix chord pipeline) is powering production, distill its Flat-granularity pitch output into a framewise, non-autoregressive piano-roll student model.

**Target student:** framewise piano-roll model, non-autoregressive, real-time-capable on-device. This replaces the existing CRNN for Live Mic Mode chord detection.

**Approach:**
- Branch A (MT3 or chroma) runs on all labeled + unlabeled song audio → generates pseudo-labels with confidence scores
- Filter pseudo-labels at confidence > 0.9 → creates a training set 10-100× larger than current labeled data
- Train framewise student (TFLite-friendly, <600KB) with knowledge distillation loss (KL divergence between teacher logits and student logits in addition to cross-entropy)
- Fine-tune on real guitar audio (GuitarSet, isolated catalog stems) — not only Slakh2100, which is MIDI-rendered and generalizes poorly to real electric/acoustic guitar timbre
- Target: student achieves >70% GuitarSet chord accuracy while running on-device

**If student reaches production quality:** swap Branch A teacher for student in the backend pipeline (reduced cost, faster inference). Keep teacher for continued pseudo-label refreshes.
**If student plateaus:** Branch A teacher (MT3/chroma) remains primary; student stays as on-device fallback.

### Milestone 3B: Solo Student Distillation

Once Branch B (guitar-conditioned, leakage-hardened solo pipeline) is powering production, distill it into a guitar-only-vocabulary token student model.

**Target student:** autoregressive token model with vocabulary limited to guitar program numbers only — structurally incapable of leaking non-guitar notes. Keeps the token-based output (bends, ties, duration matter for tab generation) but is smaller than MT3 because of the restricted vocabulary.

**Approach:**
- Branch B (MT3 with program conditioning + memory retention) runs on all labeled + unlabeled guitar audio → generates pseudo-labels with confidence scores + leakage_risk
- Filter pseudo-labels at confidence > 0.9 AND leakage_risk < 0.3
- Train guitar-vocabulary token student with knowledge distillation loss
- Fine-tune on real isolated guitar audio (GuitarSet, catalog stems) to handle real electric/acoustic timbre, bends, palm-muting — Slakh2100 is insufficient for real-guitar generalization
- Target: solo note accuracy ≥ MT3 teacher on guitar-only passages, with zero instrument-leakage events on held-out mix tests

**If student reaches production quality:** swap Branch B teacher for student. On-device solo transcription gets a major upgrade.
**If student plateaus:** Branch B teacher remains primary; student stays as on-device fallback for solo.

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
| Basic Pitch for solo transcription | **Replaced** by two-branch architecture: full-mix chord branch + guitar-conditioned solo branch with MR-MT3 leakage mitigation |
| Fretboard as secondary concern | **Elevated** — dual-mode display is the core UX differentiator |

---

## Acceptance Criteria (Phase 2 release gate)

All commits within each milestone must meet their individual ACs. The Phase 2 release gate additionally requires:

- [ ] MT3-powered pipeline produces chord-solo LessonJSON for any uploaded song
- [ ] Fretboard dual-mode toggle works across Listen, Study, Slow, Play, Review steps
- [ ] Fallback chain never produces empty/null result (always degrades gracefully)
- [ ] 10-song smoke test: 5 studio recordings + 5 live performances → all produce valid chord timelines
- [ ] **Chord-without-guitar regression test**: mix a chord progression with the guitar stem muted or heavily attenuated in the source audio — chord detection must remain stable/correct from the full-mix branch (Branch A)
- [ ] **Leakage stress test**: mix a guitar melody with a doubling piano or vocal line in the same register/time window — solo transcription must not include notes attributable to the non-guitar part (Branch B)
- [ ] `npm run lint`, `npm run test`, `pytest` pass
- [ ] Manual QA sign-off on session loop for MT3-powered songs vs CRNN-powered songs
