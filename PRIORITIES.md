# Harmoniq — Engineering Roadmap

Three-phase product roadmap for **risk first**, **vertical slices**, and **mobile + web** parity. Follow in sequence unless a kill-switch fails.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**. **Phase 2 commits 98–121** — archived. **Phase 2 commits 122–148** — archived (superseded by MT3-primary strategy). **NEW Phase 2** — MT3-Powered MVP & Product Completion.

---

## At a glance

|                    |                                                                      |
| ------------------ | -------------------------------------------------------------------- |
| **Roadmap status** | **Phase 2: MT3-Powered MVP & Product Completion (Milestone B archived). Phase 3: Planned.** |
| **Product spec**   | [`README.md`](README.md)                                             |
| **UI spec**        | [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md)                               |
| **E2E / release**  | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md)                               |
| **Manual QA**      | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md)                             |
| **Scoring**        | [`docs/SCORING.md`](docs/SCORING.md)                                 |
| **Archive**        | [`priorities-archive.md`](priorities-archive.md) (Phase 0 + Phase 1 + Phase 2 commits 98-148 + Milestone A + Milestone B) |

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

### Milestone C: Engagement & Retention Features

**Current state:** Correction store (`useCorrectionStore`) fully implemented with chord/note/voicing overrides and DB persistence. Jam mode (`app/(tabs)/jam.tsx`) is a full single-tab experience with backing tracks, scale detection, phrase coaching, and save flow. SM-2 spaced repetition engine (`src/spaced/sm2.ts`) powers skill node mutations. Practice plan sequencer (`backend/app/sequencer.py`) generates slot-based plans. No analytics infrastructure, no three-tier output, no multi-instrument support, no chord pulse dashboard exist yet.

#### Commit C1: User Feedback & Manual Overrides
- **Scope:**
  - Extend existing `useCorrectionStore` with a "report incorrect" action on any chord/note in the fretboard or chord timeline
  - Add `POST /analyze/{job_id}/feedback` backend endpoint accepting structured feedback:
    - `{ type: "chord_correction" | "note_correction" | "wrong_chord", event_index, original, corrected, reason? }`
  - Persist feedback to `user_feedback` SQLite table with `job_id`, `song_id`, `user_id`, `timestamp`, `feedback_type`, `original_value`, `corrected_value`
  - Route corrections to two distillation sets:
    - Chord corrections → Branch A chord student's training set (exportable as `chord_feedback.json`)
    - Note/solo corrections → Branch B solo student's training set (exportable as `solo_feedback.json`)
  - Add feedback summary in Review screen: "You corrected 3 chords and 2 notes in this session"
  - Add cumulative feedback stats to player profile: total corrections, most-corrected chord types
  - Feedback dashboard in Settings: list of all corrections with revert capability

- **Acceptance Criteria:**
  - [ ] Long-press or tap-and-hold on chord/note opens "Report incorrect" menu
  - [ ] Feedback persisted to `user_feedback` table with full metadata
  - [ ] Chord corrections exported as `chord_feedback.json` for Branch A training
  - [ ] Note corrections exported as `solo_feedback.json` for Branch B training
  - [ ] Review screen shows correction summary for current session
  - [ ] Settings > Feedback shows all historical corrections with revert
  - [ ] Corrections flow through to `correction_count` / `correction_coverage` metrics in LessonJSON

#### Commit C2: Jam Mode Summary Agent
- **Scope:**
  - Add `POST /jam/summary` backend endpoint triggered on jam save
  - Claude Haiku-powered post-jam analysis:
    - Input: jam snapshot (scale, confidence, phrase features, backing track, duration)
    - Output: structured summary with per-phrase feedback
  - Persona-switching via system prompt: "Encouraging coach" vs "Technical analyst" (user toggle in Jam settings)
  - Output schema: `{ phrase_index, chord, clarity, intonation_cents, timing_ms, transition_from, transition_gap_ms, suggestion }`
  - Display jam summary in a post-jam modal:
    - Overall grade (A–F) from weighted phrase scores
    - Top 3 strengths and top 3 areas for improvement
    - "Practice this phrase" button → launches slow loop on weakest phrase
  - Persist summary to `jam_snapshots.summary_json` column
  - Add jam history list screen: `app/(tabs)/jam/history.tsx` showing past jams with summary previews

- **Acceptance Criteria:**
  - [ ] Post-jam modal shows overall grade and per-phrase breakdown
  - [ ] Persona toggle switches between encouraging/technical modes
  - [ ] "Practice this phrase" launches slow loop on the selected phrase
  - [ ] Jam history screen lists past jams with summary previews
  - [ ] Summary persisted to `jam_snapshots.summary_json`
  - [ ] Backend returns structured JSON matching defined schema
  - [ ] Graceful fallback when Claude API unavailable (generic summary)

#### Commit C3: Play Engagement Analytics
- **Scope:**
  - Create `src/analytics/eventBus.ts`: lightweight custom event bus (no third-party SDK)
    - `emit(event: AnalyticsEvent)` and `subscribe(handler)` pattern
    - Events batched in memory, flushed to SQLite every 30 seconds or on app background
  - Define `AnalyticsEvent` type union:
    - `session_start`, `session_complete`, `session_step_progress`, `session_abandon`
    - `play_along_start`, `play_along_complete`, `play_along_discard`
    - `feature_usage`, `correction_made`, `jam_complete`
  - Add `analytics_events` SQLite table: `id, user_id, event_type, payload_json, timestamp`
  - Track per-user per-song engagement metrics:
    - Total play-along duration, average session length, completion rate
    - Most-practiced songs, most-corrected chord types
    - Session frequency (sessions per day/week)
  - Add opt-out toggle in Settings: "Share practice data" (default: on)
  - Add privacy notice in onboarding: "We track practice patterns to improve your experience. Opt out anytime."
  - Export analytics as CSV in Settings > Privacy > Export my data

- **Acceptance Criteria:**
  - [ ] Event bus emits and batches events correctly
  - [ ] Events flushed to SQLite on interval and app background
  - [ ] `analytics_events` table created with correct schema
  - [ ] Session start/complete/abandon events tracked automatically
  - [ ] Play-along duration and discard events tracked
  - [ ] Per-song engagement metrics computed from raw events
  - [ ] Opt-out toggle disables event collection (existing events retained)
  - [ ] Privacy notice shown during onboarding
  - [ ] CSV export produces downloadable analytics file

#### Commit C4: Dynamic Session Engine
- **Scope:**
  - Extend `PracticePlanPayload` to support mid-session adaptation:
    - After each slot completes, re-evaluate remaining slots based on actual performance
    - If a slot scored <50%, insert a remediation slot before the next planned slot
    - If a slot scored >90%, skip the next easier slot and advance
  - Add `POST /session/plan/adapt` backend endpoint:
    - Input: current plan state, last slot performance (accuracy, timing, completion)
    - Output: updated remaining slots with possible insertions/removals
  - Wire SM-2 spaced repetition into plan sequencing:
    - `skill_mutator.ts` already computes per-skill scores — feed these into slot selection
    - Weak skills get more frequent practice slots; strong skills get review-only slots
  - Add plan progress persistence to `practice_plans` table:
    - `current_slot_index`, `slot_results_json`, `adaptation_log`
    - Resume plan after app restart from last completed slot
  - Add plan history UI: list of completed plans with per-slot scores
  - Add "Regenerate plan" button that re-runs `generate_practice_plan()` with updated profile

- **Acceptance Criteria:**
  - [ ] Mid-session adaptation inserts/removes slots based on performance
  - [ ] `POST /session/plan/adapt` returns updated slot list
  - [ ] SM-2 scores influence slot selection (weak skills get more practice)
  - [ ] Plan state persists across app restarts (resume from last slot)
  - [ ] Plan history screen shows completed plans with per-slot scores
  - [ ] "Regenerate plan" produces new plan from updated player profile
  - [ ] Adaptation log records all mid-session changes for debugging

#### Commit C5: Orient-as-Hint
- **Scope:**
  - Remove Orient (`listen` step) as a mandatory linear step in the session flow
  - Integrate orient content as a non-intrusive amber overlay in Study and Play screens:
    - Small `?` toggle button in the toolbar (amber when active)
    - Toggling shows/hides the orient audio clip + annotation text as a slide-down panel
    - Panel includes play/pause for the orient WAV and the text annotation
  - Update `SESSION_STEPS` in `sessionFlow.ts`: remove `listen` from the mandatory sequence
  - Add orient data to `MusicContext` so it's available in Study/Play without a separate screen
  - Preserve the orient backend endpoint (`POST /session/orient-clip`) — only the frontend routing changes
  - Add "Skip to Study" shortcut that bypasses orient entirely
  - Keep `listen.tsx` as a standalone screen accessible from session settings for users who want the full orient experience

- **Acceptance Criteria:**
  - [ ] `listen` removed from mandatory `SESSION_STEPS` array
  - [ ] Study screen has `?` toggle that shows/hides orient overlay
  - [ ] Play screen has `?` toggle that shows/hides orient overlay
  - [ ] Orient overlay plays audio and shows annotation text
  - [ ] "Skip to Study" button available on session entry
  - [ ] `listen.tsx` still accessible as standalone screen from settings
  - [ ] Session flow navigation updated (Study follows directly after pre-flight)
  - [ ] No regression on orient audio clip fetching

#### Commit C6: Mastery & Integrity
- **Scope:**
  - Atomic SQLite transactions for all dynamic session state updates:
    - Wrap `skill_mutator.ts` mutations in a single transaction
    - Wrap `practice_plans` slot completion + adaptation in a single transaction
    - Prevent partial writes on crash (dual-entry state integrity)
  - Add `session_state` SQLite table:
    - `session_id, plan_id, current_step, slot_results_json, started_at, updated_at`
    - Enables crash recovery: on app restart, check for incomplete sessions and offer to resume
  - Single-file mode vs dynamic session mode:
    - Single-file: current behavior (one song, linear 7-step flow)
    - Dynamic: plan-driven multi-slot flow (warmup → song → jam → review)
  - Add mode toggle on Home screen: "Practice a song" (single) vs "Follow a plan" (dynamic)
  - Ensure skill node updates are idempotent (same session shouldn't double-count)

- **Acceptance Criteria:**
  - [ ] All DB writes during session use atomic transactions
  - [ ] `session_state` table tracks active session for crash recovery
  - [ ] App restart detects incomplete session and offers resume
  - [ ] Single-file mode and dynamic mode coexist without interference
  - [ ] Skill node mutations are idempotent (no double-counting)
  - [ ] Mode toggle on Home screen switches between single/plan modes
  - [ ] No data loss on forced app kill during a session

#### Commit C7: Chord Pulse Dashboard
- **Scope:**
  - New screen: `app/(tabs)/progress/pulse.tsx` — scrolling chord timeline with falling notes visualizer
  - Chord timeline: horizontal scrollable bar showing chord changes over time (reuse `ChordsAndLyrics` rendering)
  - Falling notes: vertical piano-roll-style display below chord bar, notes fall toward a hit line (like Guitar Hero)
    - Chord tones highlighted in amber, non-chord tones in gray
    - Beat grid lines visible as horizontal guides
  - Beat-synced Pulse ring animation:
    - Circular ring at center of screen that pulses on downbeats
    - Ring color intensity maps to current chord confidence
    - Ring size pulses with `pulse_bpm` from BeatGrid
  - Session-over-session chord accuracy trend: line chart showing accuracy % over last 10 sessions
  - Chord mastery heatmap: 12×N grid (one column per chord type) showing hit rate per chord
  - Accessible from Home screen "Pulse" card or Progress tab

- **Acceptance Criteria:**
  - [ ] Pulse screen renders scrolling chord timeline
  - [ ] Falling notes display with correct pitch-to-y mapping
  - [ ] Beat-synced ring pulses on downbeats with correct timing
  - [ ] Ring color intensity reflects chord confidence
  - [ ] Session accuracy trend chart shows last 10 sessions
  - [ ] Chord mastery heatmap displays hit rates per chord type
  - [ ] Screen accessible from Home and Progress tabs
  - [ ] Performance: 60fps rendering with 100+ chord events

#### Commit C8: Three-Tier Output Strategy
- **Scope:**
  - Define three output personas from shared LessonJSON:
    - **Learner**: simplified view — scrolling chord chart + single-line solo melody + fretboard sync. No MusicXML, no complex notation. Large chord symbols, color-coded difficulty.
    - **Intermediate**: standard view — slash chords + beat grid + tab notation. Current default behavior.
    - **Transcriber**: full view — printable MusicXML, complete notation, all metadata. Export-focused.
  - Add `output_tier` preference to `app_prefs` table: `'learner' | 'intermediate' | 'transcriber'`
  - Backend generates all three tiers from the same LessonJSON — no separate analysis needed
  - Frontend conditionally renders based on `output_tier`:
    - Learner: hide MusicXML viewer, show simplified chord chart, hide complex theory
    - Intermediate: current behavior (default)
    - Transcriber: show full notation, add "Print" and "Export" buttons
  - Add tier selector in Settings > Display > "notation_complexity"
  - Auto-detect tier from `experience_level` on first launch (beginner → learner, intermediate → intermediate, advanced → transcriber)

- **Acceptance Criteria:**
  - [ ] `output_tier` preference stored in `app_prefs`
  - [ ] Learner mode shows simplified chord chart + solo line (no MusicXML)
  - [ ] Intermediate mode shows current default behavior
  - [ ] Transcriber mode shows full notation with print/export
  - [ ] Tier selector in Settings switches between modes
  - [ ] Auto-detection from `experience_level` on first launch
  - [ ] All three tiers render from the same LessonJSON without re-analysis
  - [ ] No regression on existing intermediate mode

#### Commit C9: Multi-Instrument Diagram Support
- **Scope:**
  - Extend `FretboardDiagram` to support multiple instrument types:
    - Guitar (6-string, standard tuning) — existing
    - Piano (keyboard layout with 2-octave range)
    - Ukulele (4-string, GCEA tuning)
  - Add instrument selector toggle in session toolbar: 🎸 / 🎹 / 🪕
  - Alternate tuning support for guitar:
    - Preset tunings: Standard (EADGBE), Drop D (DADGBE), Open G (DGDGBD), DADGAD, Half-step down (EbAbDbGbBbEb)
    - Custom tuning: user inputs per-string notes
    - Tuning stored in `app_prefs` as `guitar_tuning: string[]`
  - Update `chordToFretboardCells()` and `fretboardCell.ts` to accept tuning array
  - Update chord diagram rendering (`ChordDiagram.tsx`) to show correct string/fret for ukulele
  - Piano mode: render 2-octave keyboard with highlighted notes for current chord/scale
  - Transposition engine: when tuning changes, recompute all fretboard positions

- **Acceptance Criteria:**
  - [ ] Instrument selector toggle visible in session toolbar
  - [ ] Piano mode renders 2-octave keyboard with highlighted notes
  - [ ] Ukulele mode renders 4-string fretboard with correct chord shapes
  - [ ] Alternate tuning presets selectable (Drop D, Open G, DADGAD, etc.)
  - [ ] Custom tuning accepts per-string note input
  - [ ] Fretboard positions recompute correctly for each tuning
  - [ ] Chord diagrams update for ukulele voicings
  - [ ] Tuning preference persists across sessions

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
| Milestone B: Fretboard Dual-Mode Optimization | **Archived** — all 9 commits complete and verified |

---

## Acceptance Criteria (Phase 2 release gate)

All commits within each milestone must meet their individual ACs. The Phase 2 release gate additionally requires:

- [x] ~~Fretboard dual-mode toggle works across Listen, Study, Slow, Play, Review steps~~ — **Milestone B archived** (all ACs verified)
- [ ] MT3-powered pipeline produces chord-solo LessonJSON for any uploaded song
- [ ] Fallback chain never produces empty/null result (always degrades gracefully)
- [ ] 10-song smoke test: 5 studio recordings + 5 live performances → all produce valid chord timelines
- [ ] **Chord-without-guitar regression test**: mix a chord progression with the guitar stem muted or heavily attenuated in the source audio — chord detection must remain stable/correct from the full-mix branch (Branch A)
- [ ] **Leakage stress test**: mix a guitar melody with a doubling piano or vocal line in the same register/time window — solo transcription must not include notes attributable to the non-guitar part (Branch B)
- [ ] `npm run lint`, `npm run test`, `pytest` pass
- [ ] Manual QA sign-off on session loop for MT3-powered songs vs CRNN-powered songs
