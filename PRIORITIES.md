# Harmoniq — Engineering Roadmap

Research project + demo app for Automatic Music Transcription (AMT), focused on guitar. Start here for the plan; see [`README.md`](README.md) for the build spec.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**.  
**Phase 2 commits 98–148** — archived.  
**Milestone A (MT3-Primary Pipeline)** — archived, complete.  
**Milestone B (Fretboard Dual-Mode)** — archived, complete.  
**Milestone C (Engagement & Retention)** — promoted into the active backlog (commits 159–167; 159 completed → archived).  
**Milestone D (Infrastructure)** — partially implemented; remaining gaps at commits 169–172 (151 SSE progress stream completed → archived).  
**Current Phase 2** — Pipeline validation & publication close-out (commits 149–150).  
**Active backlog** — numbered commits **149–183** below (one commit = one spec; 151–159 completed → archived).  
**Phase 3** — Planned, blocked on GPU (commits 174–176; aspirational 177–180; verification fixes 181–182 sit in the active backlog, not Phase 3).

---

## At a glance

| | |
| ------------------ | -------------------------------------------------------------------- |
| **Roadmap status** | **Phase 2 close-out (149–150), then backlog 160–183** (151–159 completed → archived). Phase 3 blocked on GPU (174–176). |
| **Research doc** | [`docs/RESEARCH.md`](docs/RESEARCH.md) |
| **Known failures** | [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md) |
| **Evaluation** | [`docs/EVALUATION.md`](docs/EVALUATION.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Blog** | [`docs/blog/why-harmoniq-part-2.md`](docs/blog/why-harmoniq-part-2.md) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (completed work only; deferred work was promoted here in Sep 2026) |

---

## PHASE 2: Pipeline Validation & Publication — Commits 149–150

**Status:** In Progress — clean-clone verification green (6/7 release-gate ACs); Part 2 external publication held open by owner

**What this phase is:**
- Validate the MT3-primary + CRNN-fallback pipeline on a real song set (done — see [`docs/EVALUATION.md`](docs/EVALUATION.md))
- Document known failure modes and evaluation results (done — see [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md))
- Publish Part 2 and Part 3 blog posts (Part 2 announced in-repo at [`docs/RESEARCH.md`](docs/RESEARCH.md); external publication pending owner; Part 3 = commit 150)
- Verify everything works from a clean clone and sync the roadmap to reality (commit 149 — verification done, see below)

**What this phase is not:**
- New feature development (engagement features start at commit 159)
- Custom model training (requires GPU — see Phase 3)
- On-device optimization (the existing on-device active listener beta is separate)

### Strategic Context

The pipeline uses a four-tier fallback architecture:

```
Audio → Demucs 6-stem → MT3 (primary transcription)
                              ↓
                         CRNN TFLite (fallback — chord only)
                              │  quality gate: >80% N → chroma
                              ↓
                         Chroma template matching (last resort)
                              ↓
                         LessonJSON with per-tier confidence scores
```

**Two-branch structure:**
- **Branch A (chords, instrument-agnostic):** full mix or harmonic-bed submix → aggregate pitch/chroma → template matching → chord timeline
- **Branch B (solo, guitar-conditioned):** guitar stem (Demucs) as soft prior + full mix as parallel feature → MT3 program-filtered solo decoder → solo notes

**Why the CRNN is kept:** It serves as a confidence-aware fallback. At 34.7% real-world accuracy, it correctly identifies out-of-distribution audio (>80% N predictions) and defers to chroma matching. This is not a bug — it is correct behavior for a well-designed fallback. The quality gate (`_neural_model_too_noisy()` in `chord_inference.py`) prevents the system from presenting garbage output.

**What we'd do with a GPU:** Retrain the CRNN on MT3-generated pseudo-labels to close the synthetic-to-real gap (commit 174).

---

### Commit 149: Phase 2 Release-Gate Verification & Roadmap Sync

**Status:** In Progress — 6/7 ACs green (verification complete; AC6 external publication held open by owner decision)

**Goal:** Verify the Phase 2 release gate from a clean clone, tick the acceptance criteria that pass, close stale criteria, and leave the roadmap matching reality.

**Current State:** Clean-clone verification completed Oct 10 2026 at commit `d61b8d9` (clone of local main; Node 24.15.0, Python 3.11.15 for CI parity, Python 3.12.1 for the MT3 extra). Frontend: `npm ci` exit 0, `npm run lint` exit 0, vitest **439/439** (the old 399 claim was stale). Backend CI parity: scoring set (11 files per `scoring-tests.yml`) **237 passed / 2 skipped exit 0**; full `ci.yml`-env suite **1270 passed / 11 failed / 10 skipped** — the 11 are environment-coupled, not regressions, and are filed as commits 181 (8 CI env-toggle × unit-test conflicts) and 182 (3 AlphaTab optional-dep guards). Smoke test green: `quick_smoke_test.py` exit 0 on bundled `reggae_clean_30s.wav` via the full MT3 pipeline (first run 643s CPU; cache-hit rerun ~5s). Seven trivial clean-clone fixes were made along the way (smoke audio fallback `827f87e`, AlphaTab lint `fdc62fb`, music21+tenacity deps `abc2bef`, mt3-extra resolvability `f4cbcda`, tensorboard dep `75a19e1`, gin fetch in download script `892faac`, smoke `--timeout` `d61b8d9`). R1 (Pipeline Validation) and R3 (Open-Source Hardening) are complete in substance with clean-clone evidence; R2 is complete in-repo except external publication of Part 2, which the owner will do later. The stale archived AC 98c (mobile latency) is closed as superseded by the Milestone A on-device benchmark (`tests/benchmarks/chordModelLatency.ts`).

**Scope:**

- Run clean-clone verification end-to-end:
  - Fresh clone → `npm ci` → `npm run lint` → `npm run test`
  - Fresh venv → `pip install -e ".[dev]"` → `python -m pytest -q`
  - `python scripts/quick_smoke_test.py` on the bundled reference audio
- Fix or file issues: any failure found becomes a new backlog commit (do not silently drop ACs)
- Tick every R1–R3 acceptance criterion that the verification proves
- Close the stale 98c AC in [`priorities-archive.md`](priorities-archive.md) as *superseded by the Milestone A on-device benchmark*
- Leave R2's publication AC open — external publication of Part 2 is an owner action (in-repo announcement at [`docs/RESEARCH.md`](docs/RESEARCH.md))
- Fold this section's ACs into the release-gate list below and tick them
- Sync "At a glance" / phase headers so no stale "deferred" claims remain (Milestone C/D status notes are already updated — verify)

**Acceptance Criteria:** ticked and merged into the release-gate ledger at the end of this file ("Acceptance Criteria (Phase 2 release gate → Commit 149)"). Result: **6/7 green** — AC6 (Part 2 external publication to harmoniq.ai/blog) is held open by owner decision; in-repo announcement lives at [`docs/RESEARCH.md`](docs/RESEARCH.md).

---

### Commit 150: Part 3 Blog Post — The Meta-Layer (was R4)

**Status:** ready

**Goal:** Write and publish Part 3 of the Harmoniq blog series: building an AI product with AI assistance — the recursive loop of planning, implementing, reviewing, and deciding when to push through a plateau versus change approach.

**Current State:** Part 2 draft is in-repo (`docs/blog/why-harmoniq-part-2.md`) and announced at [`docs/RESEARCH.md`](docs/RESEARCH.md) (external publication pending owner); it promises Part 3 at its conclusion: *"Part 3 will be about the meta-layer of this project: building an AI product with AI assistance, and what that recursive loop taught me about learning, building, and when to push through a plateau versus when to find a different path."* No Part 3 draft exists.

**Scope:**

- Draft `docs/blog/why-harmoniq-part-3.md` covering: the agent-driven development workflow (roadmap → spec → commit → review), what the merge/code-review passes surfaced (dead code, stale roadmaps), honest lessons on process vs. velocity
- Include concrete examples from this repo (evaluation results, fallback architecture honesty)
- Publish to harmoniq.ai/blog
- Link Part 3 from Part 2's closing paragraph, README, and [`docs/blog/`](docs/blog/) index

**Acceptance Criteria:**

- [ ] Part 3 published to harmoniq.ai/blog
- [ ] Part 2, README, and docs cross-link to Part 3
- [ ] Post includes real metrics/results from the repo (no placeholder claims)

---

## Active Backlog — Commits 160–183

Each commit below is a self-contained spec (Goal / Current State / Scope / Acceptance Criteria). Recommended execution order is numeric. Status labels: **ready** (can start now), **deferred** (planned, lower priority), **blocked** (external dependency), **aspirational** (far-future).

---

**Group: Engagement features — promoted from Milestone C (159–167), then left-handed parity (168)**

---

### Commit 160: Jam Mode Summary Agent (was C2)

**Status:** deferred

**Goal:** Post-jam, Claude-powered phrase-level analysis with a persona toggle — grade, strengths/weaknesses, and a one-tap "practice this phrase" loop launcher.

**Current State:** `POST /jam-score` (`main.py:844`) already returns a coach paragraph via `generate_jam_coach_summary()` (deterministic focus-key + reliability tags from duration/pitch maps), and `app/(tabs)/jam.tsx` has the full save flow. Missing: per-phrase structured analysis (`phrase_index`, `intonation_cents`, `timing_ms`, `transition_gap_ms`, `suggestion`), persona switching, grade + strengths modal, `summary_json` persistence, and a jam history screen (no `app/(tabs)/jam/` directory exists).

**Scope:**
- Add `POST /jam/summary` backend endpoint triggered on jam save
- Claude Haiku-powered post-jam analysis:
  - Input: jam snapshot (scale, confidence, phrase features, backing track, duration)
  - Output: structured summary with per-phrase feedback
- Persona-switching via system prompt: "Encouraging coach" vs "Technical analyst" (user toggle in Jam settings)
- Output schema: `{ phrase_index, chord, clarity, intonation_cents, timing_ms, transition_from, transition_gap_ms, suggestion }`
- Display jam summary in a post-jam modal:
  - Overall grade (A-F) from weighted phrase scores
  - Top 3 strengths and top 3 areas for improvement
  - "Practice this phrase" button → launches slow loop on weakest phrase
- Persist summary to `jam_snapshots.summary_json` column
- Add jam history list screen: `app/(tabs)/jam/history.tsx` showing past jams with summary previews

**Acceptance Criteria:**

- [ ] Saving a jam triggers summary generation without blocking the save
- [ ] Post-jam modal shows grade, strengths, improvements, and per-phrase suggestions
- [ ] "Practice this phrase" launches slow loop on the weakest phrase
- [ ] Summaries persist and appear in jam history
- [ ] Both personas toggle correctly
- [ ] Backend tests green; LLM failure degrades gracefully (jam saves without summary)

---

### Commit 161: Play Engagement Analytics (was C3)

**Status:** deferred

**Goal:** A lightweight, opt-out client event bus that records practice behavior so engagement metrics (completion rate, session frequency, most-practiced songs) can be measured and exported.

**Current State:** No analytics infrastructure exists. The only telemetry is `src/analytics/firstAudioPlay.ts` — a dev-only one-shot console logger, not an event bus. No `AnalyticsEvent` union, no `analytics_events` table, no metric queries, no opt-out preference, no CSV export.

**Scope:**
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

**Acceptance Criteria:**

- [ ] Events emitted at documented points and flushed to SQLite (batch + background)
- [ ] Opt-out stops emission; default-on with onboarding notice
- [ ] CSV export produces parseable file
- [ ] Metrics queries power a basic engagement view
- [ ] Migration + tests green on mobile and web

---

### Commit 162: Dynamic Session Engine (was C4)

**Status:** deferred

**Goal:** Make practice plans self-adjusting — re-evaluate remaining slots after each one completes, insert remediation or skip ahead, and survive app restarts.

**Current State:** `backend/app/sequencer.py` builds deterministic slot plans (`generate_practice_plan()`, mood-aware since commit 76) and the frontend drives them via `src/stores/planStore.ts` + `src/session/practicePlanNavigation.ts`. Missing: no `POST /session/plan/adapt` endpoint, no mid-session re-evaluation, no `practice_plans` persistence columns (`current_slot_index`, `slot_results_json`, `adaptation_log`) — plans are ephemeral, no resume-after-restart, no plan history or regenerate UI. SM-2 (`src/spaced/sm2.ts`) computes skill scores but they do not feed slot selection.

**Scope:**
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

**Acceptance Criteria:**

- [ ] Low-scoring slot triggers remediation insertion; high-scoring slot skips forward
- [ ] SM-2 skill scores influence next-slot selection
- [ ] Plan resumes after app restart from last completed slot
- [ ] Plan history lists completed plans with per-slot scores
- [ ] Regenerate button produces an updated plan
- [ ] Backend endpoint + frontend flow tested

---

### Commit 163: Orient-as-Hint (was C5)

**Status:** deferred

**Goal:** Demote Orient from a mandatory session step to an on-demand amber overlay in Study and Play — orient content without a screen the learner must pass through.

**Current State:** `SESSION_STEPS` in `src/constants/sessionFlow.ts:5` still mandates `'listen'` between `musical-tolerance` and `study`; orient content only exists on that standalone screen. Backend `POST /session/orient-clip` (`main.py:1064`) and `generate_orient_clip()` already work — only frontend routing changes. No `?` overlay, no "Skip to Study" shortcut.

**Scope:**
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

**Acceptance Criteria:**

- [ ] Default session flow no longer mandates `listen`; Study reachable directly
- [ ] Orient `?` overlay plays clip + shows annotation inside Study and Play
- [ ] Backend orient-clip endpoint unchanged (non-regressed)
- [ ] Full listen screen still reachable from session settings
- [ ] Session flow tests + `npm run test` green

---

### Commit 164: Mastery & Integrity (was C6)

**Status:** deferred

**Goal:** Make dynamic-session state crash-safe (atomic transactions, resume-on-restart) and add an explicit single-song vs follow-a-plan mode toggle.

**Current State:** Skill mutations (`skill_mutator.ts`) and plan-completion writes are not wrapped in transactions; no `session_state` table exists (repo-wide search finds no `session_state`); the app is single-file mode only with no Home-screen mode toggle and no resume flow for interrupted sessions.

**Scope:**
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

**Acceptance Criteria:**

- [ ] Skill + plan mutations are transactional (kill-mid-write leaves consistent state)
- [ ] Incomplete session detected on restart with resume offer
- [ ] Home toggle switches single vs dynamic modes
- [ ] Replaying the same session result does not double-count mastery
- [ ] Migration + tests green on both platforms

---

### Commit 165: Chord Pulse Dashboard (was C7)

**Status:** deferred

**Goal:** A beat-synced "pulse" practice visualizer — falling-note chord tones, downbeat ring, accuracy trend, and a chord mastery heatmap — as the Progress tab's engagement centerpiece.

**Current State:** The Progress tab has no pulse screen (no `app/(tabs)/progress/pulse.tsx`). Adjacent pieces exist: `components/WeakAreaPulse.tsx` and `components/BeatFlashPulse.tsx` (small indicators, not a visualizer), `ChordsAndLyrics` rendering to reuse for the chord timeline, and correction/scoring history that could populate the heatmap. No accuracy-trend chart exists.

**Scope:**
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
- Chord mastery heatmap: 12xN grid (one column per chord type) showing hit rate per chord
- Accessible from Home screen "Pulse" card or Progress tab

**Acceptance Criteria:**

- [ ] Pulse screen renders chord timeline + falling-notes visualizer from real session data
- [ ] Ring pulses on downbeats with confidence-mapped intensity
- [ ] Accuracy trend chart shows last 10 sessions
- [ ] Chord mastery heatmap populated from correction/scoring history
- [ ] Reachable from Home and Progress tab
- [ ] Animation performance holds 60fps on mid-tier device (reanimated, no JS-thread jank)

---

### Commit 166: Three-Tier Output Strategy (was C8)

**Status:** deferred

**Goal:** Three render personas (Learner / Intermediate / Transcriber) derived from the same LessonJSON so notation complexity matches the user instead of one fixed view.

**Current State:** A single rendering path ships today — MusicXML viewer, full theory, and tab always on. No `output_tier` preference exists anywhere (`app_prefs` has no such column; repo-wide search for `output_tier` is empty), no tier selector in Settings, no experience-level auto-detect wiring. LessonJSON already carries everything all three tiers need (chord timeline, solo notes, MusicXML, theory) — this is pure presentation gating.

**Scope:**
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

**Acceptance Criteria:**

- [ ] All three tiers render from one analysis (no re-analysis)
- [ ] Settings selector persists and switches views live
- [ ] First-launch auto-detect from experience level works
- [ ] Learner tier hides notation/theory; Transcriber tier exposes export/print
- [ ] Default remains Intermediate (non-regression)

---

### Commit 167: Multi-Instrument Diagram Support (was C9)

**Status:** deferred

**Goal:** Extend chord/fretboard diagrams beyond standard-tuning guitar — piano and ukulele layouts plus alternate/custom guitar tunings.

**Current State:** `FretboardDiagram` and `ChordDiagram` are guitar-only with standard EADGBE baked in; `chordToFretboardCells()` / `fretboardCell.ts` assume a fixed tuning array; no instrument toggle, no `guitar_tuning` preference (repo-wide search empty), no piano/ukulele rendering anywhere.

**Scope:**
- Extend `FretboardDiagram` to support multiple instrument types:
  - Guitar (6-string, standard tuning) — existing
  - Piano (keyboard layout with 2-octave range)
  - Ukulele (4-string, GCEA tuning)
- Add instrument selector toggle in session toolbar (guitar / piano / ukulele)
- Alternate tuning support for guitar:
  - Preset tunings: Standard (EADGBE), Drop D (DADGBE), Open G (DGDGBD), DADGAD, Half-step down (EbAbDbGbBbEb)
  - Custom tuning: user inputs per-string notes
  - Tuning stored in `app_prefs` as `guitar_tuning: string[]`
- Update `chordToFretboardCells()` and `fretboardCell.ts` to accept tuning array
- Update chord diagram rendering (`ChordDiagram.tsx`) to show correct string/fret for ukulele
- Piano mode: render 2-octave keyboard with highlighted notes for current chord/scale
- Transposition engine: when tuning changes, recompute all fretboard positions

**Acceptance Criteria:**

- [ ] Instrument toggle switches guitar/piano/ukulele diagrams in session screens
- [ ] All preset tunings recompute correct string/fret positions
- [ ] Custom tuning input persists and applies
- [ ] Ukulele chord diagrams correct for GCEA
- [ ] Piano keyboard highlights current chord/scale
- [ ] Music theory outputs (chords, scales) unchanged — only rendering/tuning-aware mapping

---

### Commit 168: Left-Handed Mode Fretboard Parity (was Phase 1 commit 64, skipped)

**Status:** ready

**Goal:** Full left-handed parity for fretboard and diagram rendering — the one Phase 1 feature explicitly skipped with zero code in the repo.

**Current State:** Commit 64 was marked *skipped* in Phase 1. Repo-wide search finds no left-handed handling: `FretboardDiagram` renders strings high-E-at-top/right-handed only, `ChordDiagram` chord boxes assume right-handed orientation, and no `guitar_hand` preference exists.

**Scope:**

- Add `guitar_hand: 'right' | 'left'` preference (default `right`) in `app_prefs` + Settings UI (Display section)
- Mirror `FretboardDiagram` under left mode: string row order reversed, fret numbering mirrored, scale-degree/label overlays re-anchored; cell mapping helper unit-tested both orientations
- Mirror `ChordDiagram` chord-box rendering (vertical string order flipped, base-fret indicator side swapped)
- Mirror fretboard tap→note mapping (`onNoteTap`, `allCellsForMidi` resolution) so taps land on the visually mirrored cell
- Check `ScaleExplorer`, `Jam`, and warmup fretboard surfaces for the same mirror requirement
- Visual regression snapshots for left-handed mode (Playwright + Detox)

**Acceptance Criteria:**

- [ ] Left-handed pref mirrors fretboard + chord diagram on study/slow/play/warmup/scale-explorer/jam
- [ ] Tap targets match mirrored visuals (correct note on tap)
- [ ] Preference persists across restarts; right-handed default unchanged (visual snapshots non-regressed)
- [ ] Unit tests for mirrored cell mapping; visual snapshots for both orientations
- [ ] `npm run lint` + `npm run test` + `npm run test:visual` green

---

**Group: Infrastructure gaps — remainder of Milestone D, reality-checked (169–172)**

*Already implemented and therefore not planned: Redis-backed job store (`job_store.py`), Celery dispatch (`tasks.py`/`celery_app.py`), SSE endpoint (full stack, completed as commit 151 → archived), Prometheus `/metrics` (`metrics.py`), circuit breaker (used by `model_server.py`), model server (serves MT3).*

---

### Commit 169: Variable-Tempo Beat Grid (was Milestone D commit 140)

**Status:** deferred

**Goal:** Support songs with tempo ramps, accelerandos, and live performances with variable BPM.

**Current State:** Static BPM only. `_uniform_beat_grid()` uses a constant `step = 60.0 / bpm`; `bpm_override` (`beat_grid.py:93-120`) replaces the value but still generates a uniform grid — no tempo mapping. Evidence: `beat_grid.py:46-57` (`_uniform_beat_grid`), `beat_grid.py:125`.

**Scope:**

- Replace `_uniform_beat_grid()` with a function that accepts an array of `(time, bpm)` pairs or tempo curve
- Use `librosa.beat.beat_track()` with estimated tempo as a reference, not an override
- Store tempo change events in the returned schema alongside `beats` and `downbeats`
- Support gradual tempo changes (rubato) and sudden tempo shifts
- Maintain backward compatibility with static BPM interface (`bpm_override` keeps working)

**Acceptance Criteria:**

- [ ] Beat grid handles variable BPM songs with tempo ramps
- [ ] Tempo curve can be provided as `(time, bpm)` array
- [ ] Grid subdivisions respect local tempo at each point
- [ ] Downbeats calculated correctly through tempo transitions
- [ ] Static BPM interface (`bpm_override`) continues to work unchanged
- [ ] Performance: variable BPM grid generation <100ms for 5-minute track
- [ ] Backend tests green (`tests/` beat-grid suites)

**Implementation Notes:**

- Consider tempo segment interpolation (linear vs exponential ramps)
- Store base pulse tempo vs instantaneous tempo separately
- UI consideration: visual indicator when tempo changes detected
- May require updating `_subdivide_beats()` to handle non-uniform pulse spacing

---

### Commit 170: Job-Queue Hardening — GPU Scheduling for Demucs + DLQ Wiring (was Milestone D commits 143 + 145)

**Status:** deferred

**Goal:** Give the job queue real priority/GPU handling and make the dead-letter queue actually run — today DLQ code exists in two places and is never called.

**Current State:** Demucs runs synchronously per job (`separate.py`) blocking the request thread for minutes; no GPU/priority/queue-depth handling exists (`queue.py` has no CUDA or priority logic). Celery dispatch exists (`jobs.py:759`) but without priority tiers. The DLQ is implemented **twice** — `app/dead_letter.py` (`push_to_dlq`/`pop_from_dlq`/`inspect_dlq`) and `job_store.py:206-235` (`dlq:{job_id}` Redis helpers) — and **neither is called from the failure path**: `jobs.py` failure handling (`_repo_fail_job`, `status="failed"`) never pushes to a DLQ, and no inspection endpoint exists.

**Scope:**

- **DLQ wiring (first — small, high value):**
  - Consolidate to a single implementation (prefer `job_store.py`'s Redis helpers; delete or re-export from `dead_letter.py` — no duplicates)
  - On terminal job failure, push `{job_id, error, error_code, retry_count}` to the DLQ from the actual fail path in `jobs.py`
  - Add `GET /jobs/dlq` inspection endpoint (limit, auth-guarded/localhost) + re-queue action
  - Tests: failed job lands in DLQ; re-queue re-dispatches
- **GPU queue for Demucs:**
  - Integrate Demucs separation with the Celery queue with priority levels (urgent, normal, low) on the job schema
  - Queue-depth monitoring to prevent overload; GPU utilization tracking (nvidia-smi integration when CUDA present)
  - Batch processing for multiple audio files
  - Operator visibility: queue depth + DLQ length via existing `/metrics`

**Acceptance Criteria:**

- [ ] Failed analysis jobs land in exactly one DLQ implementation (duplicate removed)
- [ ] `GET /jobs/dlq` lists failures with error codes; re-queue re-dispatches successfully
- [ ] Demucs jobs queue through Celery with priority levels honored
- [ ] Queue depth + DLQ length exposed as Prometheus metrics
- [ ] GPU utilization tracked when CUDA available (graceful skip on CPU)
- [ ] Batch path processes multiple files without serial blocking
- [ ] Backend tests green

---

### Commit 171: Audio Fingerprinting & Quality Scoring (was Milestone D commit 146)

**Status:** deferred

**Goal:** Detect duplicate/near-duplicate uploads across encodings and reject low-quality audio upfront, reducing wasted compute.

**Current State:** Content-addressed caching with SHA256 (`cache.py`) catches byte-identical re-uploads only — a re-encoded or trimmed copy of the same song re-runs the full ~5-minute pipeline. No quality gate on input audio beyond duration checks (30–300s).

**Scope:**

- Integrate audio fingerprinting (e.g., dejavu-style chromaprint/dejavu) for duplicate detection across encodings
- Implement quality scoring (SNR, clipping detection, silence ratio)
- Fingerprint-based cache key alongside SHA256; similarity search for near-duplicates (same song, different encode)
- Quality gate: reject or warn on low-quality audio early (before Demucs/MT3) with actionable message
- Track cache hit-rate improvement

**Acceptance Criteria:**

- [ ] Same song in two encodings detected as duplicate → served from cache (no re-analysis)
- [ ] Quality score computed on ingest; below-threshold uploads rejected/warned with clear message
- [ ] Fingerprint cache key improves hit rate (metric logged)
- [ ] Byte-identical SHA256 path unchanged (non-regression)
- [ ] Backend tests green

---

### Commit 172: Stem Export from StemMixer (was Milestone D "Real-Time Stem Mixer & Export")

**Status:** deferred

**Goal:** Let users export the separated stems they're already mixing — the mixer shipped, the export never did.

**Current State:** `components/StemMixer.tsx` provides mute/solo/defaults across the 6 Demucs stems in session screens; stems exist on disk per job (`data/jobs/{job_id}/stems/`). No export path exists (no stems download endpoint, no UI export action).

**Scope:**

- Backend: `GET /jobs/{job_id}/stems` returning a ZIP of stem WAVs (or per-stem `?stem=guitar` single-file response); 404 when stems absent; stream (don't buffer whole ZIP in memory)
- Frontend: "Export stems" action in StemMixer (long-press or overflow menu) → download/save via existing download flows (web: blob download; native: share/save to file)
- Optional format choice (WAV default; MP3/transcode only if trivially available via ffmpeg)
- Respect job retention: stems older than cleanup retention → clear error, not crash
- Integration test for endpoint (zip contains expected WAVs, 404 path); component test for export action

**Acceptance Criteria:**

- [ ] ZIP download contains all non-muted stems (or single stem when selected)
- [ ] Works on web and native save/share flows
- [ ] Missing/evicted stems produce a clear user-facing error
- [ ] Large songs stream without OOM
- [ ] Tests green

---

**Group: Blocked / aspirational (173–180)**

---

### Commit 173: RWC Music Database Pipeline (was 101 Phase 2)

**Status:** blocked — requires free AIST Japan registration (credentials not configured)

**Goal:** Add the RWC Music Database (~100 professionally annotated songs) as a conditional training-data source to widen chord-class coverage beyond GuitarSet's 33/277 classes.

**Current State:** No RWC-specific code exists — only a mention in `backend/scripts/analyze_label_noise.py:247`. The archive (Commit 101 Phase 2) marked this deferred: free AIST Japan registration required, credentials never configured. The GuitarSet/EGSet12 download→parse→extract pattern (`download_guitarset.py` → `parse_guitarset.py` → `extract_guitarset_cqt.py`) is the reusable template; no downloader has been written.

**Scope:**

- Add RWC Music Database (~100 songs) as optional/conditional pipeline step
- Script skips gracefully when credentials are not configured
- Same CQT extraction + chord alignment pipeline as GuitarSet
- Register conditional CI/manual step in the dataset pipeline docs

**Acceptance Criteria:**

- [ ] RWC pipeline runs conditionally when registration credentials are configured
- [ ] Clean skip (no errors) when credentials absent
- [ ] RWC windows merge into training data with per-source loss weighting

---

### Commit 174: Phase 3.1 — Retrain CRNN on MT3 Pseudo-Labels (blocked: GPU)

**Status:** blocked — GPU access

**Goal:** Close the 34.7% → 70%+ synthetic-to-real gap by training the CRNN student on MT3-generated pseudo-labels for real guitar recordings.

**Current State:** CRNN real-world accuracy is 34.7% (v1.0.5); MT3 scores >80% (MIREX-25) as teacher. The pseudo-label tooling already exists: `python scripts/pseudo_label_generate.py --audio-dir <dir>` (`data/pseudo_label` ready, 1 file), and the full training pipeline (`build_chord_tflite.py`, temperature sampling, QAT) is preserved. What's missing is GPU time for thousands of labels + training runs.

**Scope:**

- Generate MT3 pseudo-labels at scale for real guitar audio (target ≥1,000 tracks; use available licensed audio + user-feedback exports from commit 159 when available)
- Train CRNN on pseudo-labeled real data mixed with synthetic (domain-gap mixing via `cqt_stats.npz` pattern)
- Evaluate on GuitarSet held-out test; promote via `scripts/promote_model.py` gatekeeper (only if metrics beat active)
- Document results in [`docs/RESEARCH.md`](docs/RESEARCH.md) + training log

**Acceptance Criteria:**

- [ ] ≥1,000 real tracks pseudo-labeled by MT3
- [ ] Retrained CRNN ≥70% GuitarSet root accuracy (or documented ceiling + analysis)
- [ ] Promotion gated by `promote_model.py` (no force)
- [ ] Inference latency unchanged (<100ms/frame on-device benchmark still passes)

---

### Commit 175: Phase 3.2 — Two-Head Student Distillation (blocked: GPU)

**Status:** blocked — GPU access

**Goal:** Replace the separate CRNN + chroma fallback with a single shared-encoder model distilled from MT3: one chord head, one guitar-vocabulary solo head.

**Current State:** The fallback chain is still two separate engines (CRNN TFLite chords → chroma; Basic Pitch/CRNN solo) with no shared encoder. MT3 teacher outputs are already produced by the primary pipeline (Branch A/B outputs in `LessonJSON`), and the training tooling (`build_chord_tflite.py`, temperature sampling, QAT) is preserved — but no two-head student exists and no distillation dataset has been assembled. Blocked on GPU.

**Target architecture:**

```
Shared encoder (CQT → Conv → BiLSTM, ~200K params)
    ├── Chord head (classifier, 277 classes, frame-level)
    └── Solo head (autoregressive token decoder, guitar vocabulary)
```

**Scope:**

- Distill from MT3 teacher outputs (chord sequences + filtered solo token streams from Branch A/B)
- Guitar-vocabulary solo head structurally incapable of emitting non-guitar notes
- Evaluate against current fallback chain on the 5-song set + GuitarSet
- Swap into the fallback orchestrator behind a feature flag; keep chroma as last resort

**Acceptance Criteria:**

- [ ] Single model produces both chord frames and solo tokens
- [ ] Accuracy ≥ current MT3→CRNN chain on the 5-song eval (no regression)
- [ ] Model size + latency suitable for server-side serving (and path to on-device noted)
- [ ] Feature-flagged rollout with instant fallback to existing chain

---

### Commit 176: Phase 3.3 — HT-MT3 Exploration (blocked: GPU)

**Status:** blocked — GPU access; upstream model availability

**Goal:** Evaluate Headed and Tailed MT3 (per-instrument decoder heads) as a higher-quality teacher for pseudo-labels and distillation.

**Current State:** Only standard MT3 (T5-small checkpoint via `scripts/download_mt3_checkpoint.py`) is integrated; no HT-MT3 code, weights, or upstream wiring exists. The instrument-confusion metric that the comparison needs is computed but not yet surfaced (`instrument_confusion` at `analyze_audio.py:406`, unwired to coach — commit 156). Blocked on GPU + upstream availability.

**Scope:**

- Acquire/build HT-MT3 teacher (check upstream availability)
- Run side-by-side pseudo-label quality vs standard MT3 on a 50-track sample (measure instrument-confusion rate — infrastructure from commit 156 supplies the metric)
- If better: regenerate pseudo-labels with HT-MT3 and retrain student (feeds 174/175)
- Document decision + results in [`docs/RESEARCH.md`](docs/RESEARCH.md)

**Acceptance Criteria:**

- [ ] Side-by-side teacher comparison documented with numbers
- [ ] Go/no-go decision recorded (with instrument-confusion deltas)
- [ ] If go: student retrained on HT-MT3 labels with measured improvement

---

### Commit 177: Lead Sheet Agent (MIDI + Lyrics → MusicXML)

**Status:** aspirational

**Goal:** Generate a lead sheet (melody + chord symbols + lyrics) in MusicXML from a MIDI file plus raw lyrics text.

**Current State:** `musicxml_builder.py` builds full scores from analysis output (chords + solo + beat grid); `LessonJSON` carries `lyrics_aligned` (schema line 441) and Whisper transcription exists from commit 8 — but there is no lead-sheet layout, no MIDI+lyrics ingestion path, and no syllable-to-note alignment routine. Aspirational, not started.

**Scope:**

- Align MIDI melody events to lyric syllables (timing-based)
- Merge with chord symbols (from analysis or manual input)
- Emit MusicXML lead-sheet layout via the existing `musicxml_builder.py` primitives
- Tests: known MIDI + lyrics fixture → valid MusicXML (DTD check already in CI)

**Acceptance Criteria:**

- [ ] Fixture MIDI + lyrics → valid MusicXML with aligned lyric underlay
- [ ] Renders in AlphaTab web + native
- [ ] DTD validation passes

---

### Commit 178: Zero-Latency Pitch Detection (C++/JSI Bridge)

**Status:** aspirational

**Goal:** Sub-frame pitch detection on native via a C++ JSI module for real-time tuner/tracking without JS-thread latency.

**Current State:** Native pitch goes through `usePitchStream`'s JS-side processing (react-native-audio-api path); no C++/JSI module, CMake config, or autocorrelation/YIN implementation exists in the repo. Web path already uses `getUserMedia` + AudioWorklet. Aspirational, not started.

**Scope:**

- C++ autocorrelation/YIN implementation compiled via CMake into the dev build
- JSI bridge exposing `start()/getPitchHz()/stop()` with no async hop
- Replace `usePitchStream` native path behind a flag; benchmark vs current
- Web path unchanged (getUserMedia + AudioWorklet)

**Acceptance Criteria:**

- [ ] Native pitch round-trip <30ms (vs current baseline, measured)
- [ ] Existing tuner/play flows work with the flag on
- [ ] Dev-build instructions in AGENTS.md

---

### Commit 179: Virtual Mentor Agent (Long-Term Skill Trajectory)

**Status:** aspirational

**Goal:** A mentor persona that reasons over months of skill-node history, journal, and corrections to propose long-term direction (repertoire choices, plateau diagnosis, next milestones).

**Current State:** The raw material exists — skill nodes mutated from session accuracy (commit 63), Riff DNA playing fingerprint (commit 74), correction history (`useCorrectionStore`), and practice-plan history — but nothing aggregates them into a long-term trajectory, and no mentor UI or Claude trajectory prompt exists. Aspirational, not started.

**Scope:**

- Data layer: query skill nodes + session journal + DNA into a compact trajectory summary
- Claude-powered mentor with monthly cadence (on-demand too); output stored as mentor notes
- UI: "Mentor" section in Progress with trajectory chart + proposed next month
- Guardrails: never edits plans automatically — proposals only

**Acceptance Criteria:**

- [ ] Mentor summary generated from real ≥30-day history (or synthetic fixture)
- [ ] Proposals rendered with trajectory context; no auto-mutation of plans
- [ ] Failure/absence degrades to empty state, no crashes

---

### Commit 180: Evaluation Set Expansion

**Status:** ready

**Goal:** Broaden the evaluation set per [`docs/EVALUATION.md`](docs/EVALUATION.md) "Next Steps" so conclusions generalize beyond blues/pop studio guitar.

**Current State:** [`docs/EVALUATION.md`](docs/EVALUATION.md) documents exactly 5 songs (3 pass / 1 warn / 1 fail — the improv-blues self-recording fails on gain staging/reverb), and [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md) records failure modes for those 5. No out-of-distribution, jazz-harmony, or fair live-recording cases are covered yet; GPU timing has not been captured.

**Scope:**

- Re-record test #4 (improv blues) with proper gain staging and minimal room reverb — replaces the current ❌ Fail with a fair signal
- Add a clean kora/mbira recording to test out-of-distribution behavior (expected: quality gate → chroma; documents graceful degradation)
- Add a song with extended jazz harmony to stress-test the 277-class vocabulary
- Capture pipeline timing with GPU (when available — coordinate with 174) to document speedup factor
- Update [`docs/EVALUATION.md`](docs/EVALUATION.md) with the expanded table + revised pass/warn/fail summary

**Acceptance Criteria:**

- [ ] Test set ≥7 songs covering studio / live / self-recorded / OOD / jazz-harmony
- [ ] All new songs produce complete LessonJSON (no crashes) — pass/warn/fail recorded
- [ ] EVALUATION.md summary table updated with revised verdict counts
- [ ] Failure modes for new categories documented in KNOWN_FAILURES.md

---

**Group: Clean-clone verification fixes — Commit 149 follow-ups (181–182)**

---

### Commit 181: CI env-toggle × unit-test conflicts (8 tests)

**Status:** ready

**Goal:** Make the 8 currently-failing tests pass under the exact `ci.yml` env set (`HARMONIQ_SKIP_*`).

**Current State:** Full `python -m pytest -q` with ci.yml's 12 `HARMONIQ_SKIP_*` env vars fails 8 tests that assume an un-toggled route: `tests/test_spotify_playback.py` (4 — route returns 503 under `HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1`), `tests/test_style_detect.py` (2) + `tests/test_analyze_audio_style.py` (1) (`HARMONIQ_SKIP_STYLE_DETECT=1` forces 'general'), `tests/test_curriculum.py` (1) (`HARMONIQ_SKIP_CURRICULUM=1` → 503). All of these pass without the env vars — verified in the Commit 149 clean clone: 10 passed across those 4 files. Deterministic environment-coupling, not flaky.

**Scope:**

- Decide per test: make the test toggle-aware (`pytest.skip` or expect 503 when the matching `HARMONIQ_SKIP_*` is set) or unset the toggle inside the test
- Do not weaken the routes' toggle behavior — tests must follow the env contract
- Re-run the full suite under the ci.yml env set; expect failures drop 11 → 3 (remaining = commit 182)

**Acceptance Criteria:**

- [ ] Full pytest under ci.yml's `HARMONIQ_SKIP_*` env set: the 8 env-coupled failures resolved
- [ ] Each of the 8 tests still validates its original behavior when its toggle is unset
- [ ] No route behavior changed (503 / forced-'general' semantics preserved)

---

### Commit 182: AlphaTab optional-dep guard on clean clones (3 tests)

**Status:** ready

**Goal:** The 3 AlphaTab node-bridge tests skip (not fail) when `backend/node_modules/@coderline/alphatab` is absent.

**Current State:** On a clean clone, `tests/test_alphatab_prerender.py` (2 tests) and `tests/test_musicxml_corpus.py` (1 test) fail with `ERR_MODULE_NOT_FOUND`: their guard checks `shutil.which("node")` but not whether the npm package `@coderline/alphatab` is installed under `backend/node_modules`. In the working repo (node_modules present) all 3 pass — verified in the Commit 149 clean-clone session. CI runners install frontend deps at the repo root (`npm ci`), not under `backend/`, so these tests would fail on a runner too.

**Scope:**

- Extend each test's availability guard to also probe `backend/node_modules/@coderline/alphatab` (or a shared helper)
- `pytest.skip` with a clear reason when absent; keep running when present
- Document `cd backend && npm install` for MusicXML corpus rendering only if a doc already references that workflow

**Acceptance Criteria:**

- [ ] Clean clone (no `backend/node_modules`): the 3 tests skip cleanly under full pytest
- [ ] With `backend/node_modules` installed: all 3 still run and pass
- [ ] Full ci.yml-env suite failures drop from 11 to 0

---

**Group: Native Detox environment — Commit 155 follow-up (183)**

---

### Commit 183: Native Detox Environment — onnxruntime-web Bundling + Emulator Prerequisites

**Status:** ready (user chose backlog-first; run when native verification is needed)

**Goal:** Make `npm run test:mobile` (`android.emu.debug`, Detox 20.x) green on the Android emulator, unblocking the Commit 155 ChordDiagram smoke assertion and all future on-device gates.

**Current State:** No Detox suite can boot the app (verified 2026-10-14 during Commit 155; reproduced on clean `main` with changes stashed — pre-existing, unrelated to any feature commit). Metro cannot build the Android dev bundle: `node_modules/onnxruntime-web/dist/ort.bundle.min.mjs` line 11 uses a dynamic `import(/*webpackIgnore:true*/ /*@vite-ignore*/…)` comment form that Metro's parser rejects (`Invalid call … at line 11`). The one bundle that did download then failed Hermes compilation on-device (`'}' expected at end of object literal`). Emulator itself boots (`Pixel_7` AVD; the Detox default `Pixel_7_API_34` does not exist — `DETOX_ANDROID_AVD=Pixel_7` override required), the prebuilt dev APK installs, and Metro serves over `adb reverse tcp:8081`. Ancillary environment findings: stale npm `.bin/.*` temp symlinks crash Metro's `FallbackWatcher` with `EACCES` (deleted 18 repo-wide during Commit 155 — recurs on every `npm install`); Expo CLI needs `--offline` in sandboxed networks; the emulator has no external network (8.8.8.8 100% loss; host 10.0.2.2 reachable). Full evidence in [`docs/ALPHATAB_LIMITATIONS.md`](docs/ALPHATAB_LIMITATIONS.md) ("Commit 155" section).

**Scope:**

- Keep `onnxruntime-web` out of the native bundle (platform-split import, `Platform.OS` guard, Metro `resolver.blockList`, or lazy `require` — whichever is minimal): it is a web-only dependency and must never enter the Android dev graph
- Verify the Android dev bundle builds cleanly AND compiles on-device (Hermes) via a Metro bundle fetch before touching Detox
- Do NOT touch `tests/mobile/musicxml-render.e2e.js` (out of scope for the env fix; it must simply go green again as a side effect)
- Document the emulator prerequisites (AVD name + `DETOX_ANDROID_AVD`, Expo dev build vs Expo Go, `adb reverse`, `--offline`, `.bin` dotfile cleanup) where the Detox docs live; do not invent new scripts if `npm run detox:build:android` + `npm run test:mobile` suffice
- Re-run the full `npm run test:mobile`, including the Commit 155 `chord-diagram` smoke assertion

**Acceptance Criteria:**

- [ ] Metro builds the Android dev bundle with zero transform errors; bundle compiles on-device (no Hermes errors in logcat)
- [ ] `npm run test:mobile` green on Android emulator (smoke incl. ChordDiagram visibility + dimensions; musicxml corpus suite)
- [ ] Emulator prerequisites documented (AVD, env override, Metro flags)
- [ ] No app-code behavior changed on web (web bundle still builds; `npm run test:ui` unaffected)

---

### Commit 184: Confidence-Band UI Display + ECE Calibration (Commit 156 follow-up)

**Status:** ready

**Goal:** Surface Commit 156's confidence outputs to the user in plain language, then measure whether the heuristic score is actually calibrated — without ever implying false precision.

**Current State:** Commit 156 shipped the data; two of three consumers exist, but with gaps:
- **Song/confusion display — exists but is gated dead on the primary path.** `components/InstrumentConfusionIndicator.tsx` (`InstrumentConfusionBadge` + `PerSectionConfusionBars`) is wired into `app/session/review.tsx`, but the render gate keys off the song-level `LessonJSON.instrument_confusion`, which only the CRNN dual-path branch sets — MT3-primary jobs (the primary path) leave it `null`, so the badge and per-section bars never render. Commit 156's per-section MT3 proxy data is therefore invisible until the gate also considers `instrument_confusion_per_section`. The badge also renders a raw percentage ("Instrument confusion: 42%"), which the heuristic score cannot support.
- **`confidence_band` + per-section `chord_confidence` / `leakage_risk` — zero consumers.** Populated on every analysis job and typed in `src/types/index.ts` (optional fields), read by nothing under `src/` / `app/`. Verified by grep 2026-10-14.
- **Coach-side hedging — done (Commit 156):** tiers ≥ 0.3 / ≥ 0.6 plus a deterministic appended-caveat backstop, unit-tested end-to-end. This commit only surfaces the equivalent learner-facing wording and the calibration measurement.

**Scope:**

- Confidence band display (plain-language wording, per [`docs/EVALUATION.md`](docs/EVALUATION.md) Commit 156 section):
  - Review/summary surface: one chip or line ("Good match", "Some fuzziness", "Rough transcription") driven by `confidence_band`; `null` renders nothing (unknown ≠ low)
  - Study/score surface: per-section cue when `sections[].chord_confidence` is low or `sections[].instrument_confusion` ≥ 0.3 (e.g. "check this part by ear" — same wording as the coach hedge, single source)
  - Never render the raw 0–1 number, never a percentage, never the word "probability" — the score is a hand-tuned heuristic (ECE unmeasured). Applies to `InstrumentConfusionIndicator` too: replace its `"Instrument confusion: 42%"` percentage with Low/Moderate/High wording (thresholds in `backend/app/confidence_thresholds.py`, mirrored in TS)
- Confusion display gate: extend `app/session/review.tsx` render condition so per-section data (Commit 156's MT3 proxy) shows even when the song-level `instrument_confusion` is `null`
- Graceful absence: older jobs without `confidence_band` / per-section fields degrade silently (all new fields are optional)
- Unit tests for band → wording mapping + null/absence paths; Playwright structural test for the chip on the review route
- Calibration measurement (no model changes): assemble a small labeled chord set (GuitarSet annotations already parsed in `backend/data`), bin predicted confidence, plot predicted vs empirical chord accuracy, report Expected Calibration Error in [`docs/EVALUATION.md`](docs/EVALUATION.md)
  - If ECE is poor: temperature/isotonic/Platt scaling behind `confidence_band` only (keep the raw field untouched), and only then consider numeric UI

**Acceptance Criteria:**

- [ ] `confidence_band` visible with plain-language wording on the review/summary surface; absent (`null`) renders nothing
- [ ] Low-confidence / high-confusion sections show a "check by ear" cue in Study, consistent with the coach hedge wording
- [ ] Confusion badge/bars render on MT3-primary jobs (render gate no longer keyed to the dual-path-only song-level value)
- [ ] No raw score/percentage/probability language anywhere in the UI (incl. `InstrumentConfusionIndicator`)
- [ ] Unit + structural tests green; `npm run lint` + `npm run test` green
- [ ] ECE of the heuristic confidence measured on the labeled set and reported in `docs/EVALUATION.md`

---

## PHASE 3: Custom Model Distillation (Planned — Commits 174–176)

**Status:** Blocked on GPU access — see commits 174 (retrain on pseudo-labels), 175 (two-head distillation), 176 (HT-MT3 teacher).

The pipeline currently relies on MT3 (JAX, CPU, ~5 min per song) as the primary transcriber. With GPU access, Phase 3 executes commits 174–176 in order.

**Aspirational (further out):** lead sheet agent (commit 177), zero-latency pitch detection (commit 178), virtual mentor agent (commit 179), evaluation set expansion (commit 180). Dynamic backing track generation (MRT2) already shipped — see `backend/app/jam_backing.py`.

---

## Acceptance Criteria (Phase 2 release gate → Commit 149)

Merged ledger of the former R1/R2/R3 commit-spec ACs (deleted by restructure commit `6182193`), the original Phase 2 release-gate list, and the Commit 149 spec. Verified from a clean clone of local main at commit `d61b8d9` (Oct 10 2026). Origin tags: **R1** pipeline validation, **R2** documentation & publication, **R3** open-source hardening, **gate** original release-gate list, **149** Commit 149 clean-clone verification.

- [x] MT3-powered pipeline produces chord-solo LessonJSON for a defined 5-song test set — all 5 returned complete LessonJSON (pass/warn/fail are quality verdicts: 3 pass / 1 warn / 1 fail) — **see [`docs/EVALUATION.md`](docs/EVALUATION.md)** (R1-AC1 + gate)
- [x] Fallback chain documented with real examples — **see [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md)** (R1-AC2 + gate)
- [x] 5-song smoke test documented with pass/warn/fail per song — **3 pass / 1 warn / 1 fail** (gate)
- [x] CI test suite passes from a clean clone (R1-AC3), split into precise lines below (149-AC1/AC2):
  - [x] `npm run lint` passes (0 errors) on a clean clone — **exit 0 after the `expo-env.d.ts` fix `fdc62fb`; Node 24.15.0 used (env has no Node 22; CI uses 22/20)** (R3-AC1 + 149-AC1)
  - [x] `npm run test` passes on a clean clone — **439/439 vitest (the old 399 claim was stale)** (R3-AC2 + 149-AC1)
  - [x] Backend core pytest set passes on a clean clone — **237 passed / 2 skipped, exit 0** on the CI scoring set (11 files per `scoring-tests.yml`; the old "12 core files" count was stale) (R3-AC3 + 149-AC2); full `ci.yml`-env suite: **1270 passed / 11 failed / 10 skipped** — the 11 are environment-coupled, not regressions (8 CI env-toggle × unit-test conflicts → commit 181; 3 AlphaTab optional-dep guards → commit 182)
- [x] Quick-smoke-test script runs without errors on a reference audio file — **clean-clone exit 0 on bundled `reggae_clean_30s.wav` via the full MT3 pipeline (first run 643s CPU, cache-hit rerun ~5s; `--timeout` default 900s)** (R3-AC4 + gate + 149-AC3)
- [x] Every former R1–R3 AC is ticked with evidence, filed as a backlog commit (181/182), or explicitly held open — **nothing silently dropped** (149-AC4)
- [x] Stale 98c mobile-latency AC closed as superseded by `tests/benchmarks/chordModelLatency.ts` — **closed in [`priorities-archive.md`](priorities-archive.md)** (149-AC5)
- [ ] Part 2 blog post published to harmoniq.ai/blog — **in-repo announcement at [`docs/RESEARCH.md`](docs/RESEARCH.md); harmoniq.ai unreachable at verification time; owner will publish externally later — held open by owner decision (R2-AC1 + gate + 149-AC6)**
- [x] README has research abstract at the top — **verified** (R2-AC2)
- [x] `python scripts/download_mt3_checkpoint.py` automates MT3 setup — **verified clean-clone end-to-end after the Commit 149 fix `892faac` (tensors + gin configs); the MT3 extra resolves on Python 3.12 — current flax requires ≥3.12** (R2-AC3 + gate)
- [x] `docs/KNOWN_FAILURES.md` and `docs/EVALUATION.md` exist and are accurate — **verified against repo state** (R2-AC4)
- [x] Roadmap status sections match codebase reality (this file + archive pointers) — **stale claims fixed by this commit: Milestone D line (151 done), 399/1270 baselines, Part 2 publication wording, `docs/E2E_DEMO.md` 98c reference, `docs/VISUAL_AUDIT.md` commit-106 row** (149-AC7)
