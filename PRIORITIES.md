# Harmoniq — Engineering Roadmap

Research project + demo app for Automatic Music Transcription (AMT), focused on guitar. Start here for the plan; see [`README.md`](README.md) for the build spec.

**Phase 0 (0.1–0.6)** — **complete**. **Phase 1 (commits 1–97)** — **complete**.  
**Phase 2 commits 98–121** — archived. **Phase 2 commits 122–148** — archived.  
**Milestone A (MT3-Primary Pipeline)** — archived, complete.  
**Milestone B (Fretboard Dual-Mode)** — archived, complete.  
**Milestone C (Engagement & Retention)** — deferred to archive (not scoped for MVP).  
**Current Phase 2** — Pipeline maintenance, evaluation, and publication.  
**Phase 3** — Planned (requires GPU resources).

---

## At a glance

| | |
| ------------------ | -------------------------------------------------------------------- |
| **Roadmap status** | **Phase 2: Pipeline Validation & Publication.** Phase 3: Planned (blocked on GPU). |
| **Research doc** | [`docs/RESEARCH.md`](docs/RESEARCH.md) |
| **Known failures** | [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md) |
| **Evaluation** | [`docs/EVALUATION.md`](docs/EVALUATION.md) |
| **E2E / release** | [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) |
| **Manual QA** | [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md) |
| **Blog** | [`docs/blog/why-harmoniq-part-2.md`](docs/blog/why-harmoniq-part-2.md) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (all completed + deferred commits) |

---

## PHASE 2: Pipeline Validation & Publication

**Status:** In Progress

**What this phase is:**
- Validate the MT3-primary + CRNN-fallback pipeline on a real song set
- Document known failure modes and evaluation results
- Publish Part 2 and Part 3 blog posts
- Make the project easy to clone, configure, and run for new contributors

**What this phase is not:**
- New feature development (Milestone C is deferred)
- Custom model training (requires GPU — see Phase 3)
- On-device optimization (the existing ONNX active listener beta is separate)

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

**What we'd do with a GPU:** Retrain the CRNN on MT3-generated pseudo-labels to close the synthetic-to-real gap. This is the obvious next experiment but requires GPU resources currently unavailable.

---

### R1: Pipeline Validation

**Scope:**
- Run the full pipeline on a 5-song test set (3 studio + 1 live + 1 self-recorded)
- Document results in [`docs/EVALUATION.md`](docs/EVALUATION.md)
- Document known failure modes in [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md)
- Verify the fallback chain fires correctly for each failure mode

**Acceptance Criteria:**
- [ ] All 5 songs produce a complete LessonJSON (no crashes)
- [ ] Fallback chain documented with real examples
- [ ] CI test suite passes (`npm run lint`, `npm run test`, `pytest` on core files)

---

### R2: Documentation & Publication

**Scope:**
- Write and publish Part 2 blog post: honest engineering walkthrough of the pipeline
- Add research abstract + quick-start to README.md
- Create MT3 checkpoint download script for new developers
- Ensure AGENTS.md covers research workflows

**Acceptance Criteria:**
- [ ] Part 2 published to harmoniq.ai/blog
- [ ] README has research abstract at the top
- [ ] `python scripts/download_mt3_checkpoint.py` automates MT3 setup
- [ ] `docs/KNOWN_FAILURES.md` and `docs/EVALUATION.md` exist and are accurate

---

### R3: Open-Source Hardening

**Scope:**
- Verify all CI paths work on a clean clone
- Fix any broken tests or lint errors
- Archive Milestone C to priorities-archive.md
- Add quick-smoke-test script for new developers

**Acceptance Criteria:**
- [ ] `npm run lint` passes (0 errors)
- [ ] `npm run test` passes on core test files
- [ ] Backend CI test set (`pytest` on 12 core files) passes
- [ ] Quick-smoke-test script runs without errors on a reference audio file

---

### R4: Part 3 Blog Post

**Scope:**
- Write and publish Part 3: the meta-layer (building an AI product with AI assistance)

**Acceptance Criteria:**
- [ ] Part 3 published to harmoniq.ai/blog

---

### Deferred: Milestone C — Engagement & Retention Features

Milestone C (commits C1–C9) covered: user feedback overrides, jam summary agent, play analytics, dynamic session engine, orient-as-hint, mastery & integrity, chord pulse dashboard, three-tier output, and multi-instrument support. These are not scoped for the current MVP. Full specs are archived in [`priorities-archive.md`](priorities-archive.md).

---

## PHASE 3: Custom Model Distillation (Planned)

**Status:** Planned — blocked on GPU access

The pipeline currently relies on MT3 (JAX, CPU, ~5 min per song) as the primary transcriber. With GPU access, the next phase would:

1. **Retrain CRNN on MT3 pseudo-labels** — use MT3 to label thousands of real guitar recordings, then train the CRNN on this expanded dataset. This could close the 34.7% → 70%+ gap that limited the original CRNN.

2. **Two-head student distillation** — train a shared-encoder model with chord classification and solo token decoding heads, distilled from MT3's full output. This would replace the current separate CRNN + chroma fallback with a single model.

3. **Explore HT-MT3** — Headed and Tailed MT3 adds per-instrument decoder heads that reduce instrument confusion. If available as a teacher, it would produce higher-quality pseudo-labels.

**Target student architecture** (if GPU becomes available):

```
Shared encoder (CQT → Conv → BiLSTM, ~200K params)
    ├── Chord head (classifier, 277 classes, frame-level)
    └── Solo head (autoregressive token decoder, guitar vocabulary)
```

**Other Phase 3 milestones** (aspirational, further out):
- Lead sheet agent (MIDI + lyrics → MusicXML)
- Zero-latency pitch detection (C++/JSI bridge)
- Dynamic backing track generation (MRT2 or similar)
- Virtual mentor agent (long-term skill trajectory analysis)

---

## Acceptance Criteria (Phase 2 release gate)

- [ ] MT3-powered pipeline produces chord-solo LessonJSON for a defined 5-song test set
- [ ] Fallback chain documented with real examples (see [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md))
- [ ] 5-song smoke test documented with pass/warn/fail per song (see [`docs/EVALUATION.md`](docs/EVALUATION.md))
- [ ] `npm run lint`, `npm run test`, core `pytest` files pass
- [ ] Part 2 blog post published
- [ ] MT3 checkpoint download is automated
- [ ] Quick-smoke-test script works from a clean clone

---

## Milestone D: Infrastructure & Scale (Deferred)

Infrastructure improvements (Redis/Celery job queue, GPU job scheduling, error resilience, monitoring, audio fingerprinting, smart capo, predictive beat recovery) are defined in [`priorities-archive.md`](priorities-archive.md) and deferred until Phase 2 validation is complete and Phase 3 becomes active.
