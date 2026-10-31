# Harmoniq — Engineering Roadmap

Research project + demo app for Automatic Music Transcription (AMT), focused on guitar. Start here for the plan; see [`README.md`](README.md) for the build spec.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**.  
**Phase 2 commits 98–148** — archived.  
**Milestone A (MT3-Primary Pipeline)** — archived, complete.  
**Milestone B (Fretboard Dual-Mode)** — archived, complete.  
**Milestone C (Engagement & Retention)** — promoted into the active backlog (commits 159–167; 159–166 completed, 167 skipped → archived).
**Milestone D (Infrastructure)** — complete; 151 SSE progress stream, 169 variable tempo, 170 queue hardening, 171 fingerprinting/quality, 172 stem export completed → archived.
**Current Phase 2** — Pipeline validation & publication close-out (commit 150; 149 completed → archived).  
**Active backlog** — numbered commits **150–180** below (one commit = one spec; 149, 151–166, 169–173, 177–179, 181, 183 completed and 167 skipped → archived; 184 completed → archived).
**Phase 3** — Planned, blocked on GPU (commits 174–176; aspirational 180; verification fix 182 sits in the active backlog, not Phase 3).

---

## At a glance

| | |
| ------------------ | -------------------------------------------------------------------- |
| **Roadmap status** | **Phase 2 close-out (150), then backlog 168–180** (149, 151–166, 169–173, 177–179, 181, 183, 184 completed → archived; 167 skipped → archived). Phase 3 blocked on GPU (174–176). |
| **Research doc** | [`docs/RESEARCH.md`](docs/RESEARCH.md) |
| **Known failures** | [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md) |
| **Evaluation** | [`docs/EVALUATION.md`](docs/EVALUATION.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Blog** | [`docs/blog/why-harmoniq-part-2.md`](docs/blog/why-harmoniq-part-2.md) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (completed work only; deferred work was promoted here in Sep 2026) |

---

## PHASE 2: Pipeline Validation & Publication — Commit 150 (149 archived)

**Status:** In Progress — Commit 149 complete (7/7 release-gate ACs); Commit 150 (Part 3) ready

**What this phase is:**
- Validate the MT3-primary + CRNN-fallback pipeline on a real song set (done — see [`docs/EVALUATION.md`](docs/EVALUATION.md))
- Document known failure modes and evaluation results (done — see [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md))
- Publish Part 2 and Part 3 blog posts (Part 2 published to harmoniq.ai/blog October 2026; Part 3 = commit 150)
- Verify everything works from a clean clone and sync the roadmap to reality (commit 149 — complete, see [`priorities-archive.md`](priorities-archive.md))

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

### Commit 150: Part 3 Blog Post — The Meta-Layer (was R4)

**Status:** ready

**Goal:** Write and publish Part 3 of the Harmoniq blog series: building an AI product with AI assistance — the recursive loop of planning, implementing, reviewing, and deciding when to push through a plateau versus change approach.

**Current State:** Part 2 is published at harmoniq.ai/blog (owner-confirmed live October 20, 2026) and lives in-repo at `docs/blog/why-harmoniq-part-2.md`; it promises Part 3 at its conclusion: *"Part 3 will be about the meta-layer of this project: building an AI product with AI assistance, and what that recursive loop taught me about learning, building, and when to push through a plateau versus when to find a different path."* No Part 3 draft exists.

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

## Active Backlog — Commits 168–183

Each commit below is a self-contained spec (Goal / Current State / Scope / Acceptance Criteria). Recommended execution order is numeric. Status labels: **ready** (can start now), **deferred** (planned, lower priority), **blocked** (external dependency), **aspirational** (far-future).

---

**Group: Left-handed parity (168) — Milestone C features 159–167 completed or skipped → archived**

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

**Group: Blocked / aspirational (174–176, 180)**

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

## PHASE 3: Custom Model Distillation (Planned — Commits 174–176)

**Status:** Blocked on GPU access — see commits 174 (retrain on pseudo-labels), 175 (two-head distillation), 176 (HT-MT3 teacher).

The pipeline currently relies on MT3 (JAX, CPU, ~5 min per song) as the primary transcriber. With GPU access, Phase 3 executes commits 174–176 in order.

**Aspirational (further out):** evaluation set expansion (commit 180). The virtual mentor agent shipped as commit 179, the lead-sheet agent as commit 177, and zero-latency pitch detection as commit 178 → archived. Dynamic backing track generation (MRT2) already shipped — see `backend/app/jam_backing.py`.
