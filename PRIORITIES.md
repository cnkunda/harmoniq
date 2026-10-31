# Harmoniq — AMT Research Roadmap

Harmoniq is a research project and demo app for **Automatic Music Transcription (AMT)**, focused on guitar. This file is the active work plan. Completed work lives in [`priorities-archive.md`](priorities-archive.md); every new spec follows [`docs/COMMIT_TEMPLATE.md`](docs/COMMIT_TEMPLATE.md).

The immediate research question is no longer “can the pipeline transcribe a song?” — it can, with documented failure modes. The question is whether the pipeline can become a **measured, reproducible guitar-AMT system** whose teacher/student choices, evaluation protocol, and tablature output are defensible against the current research landscape.

---

## At a glance

| | |
| --- | --- |
| **Active research** | **Commit 1 — Harmoniq AMT Research Program** (Stage 0 CPU-ready; W1–W4 GPU-gated) |
| **Publication** | **Commit 2 — Part 3 Blog Post — The Meta-Layer** (deferred until Commit 1 produces results) |
| **Archive** | [`priorities-archive.md`](priorities-archive.md) (completed and superseded work) |
| **Spec template** | [`docs/COMMIT_TEMPLATE.md`](docs/COMMIT_TEMPLATE.md) |
| **Research framework** | [`docs/RESEARCH.md`](docs/RESEARCH.md) |
| **Evaluation results** | [`docs/EVALUATION.md`](docs/EVALUATION.md) |
| **Known failures** | [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md) |
| **Implementation workflow** | [`docs/CODER.md`](docs/CODER.md) |

---

## Research context

The current pipeline is a four-tier fallback chain:

```
Audio → Demucs 6-stem → two-branch transcription
                          ├── Branch A (chords): full mix / harmonic bed → MT3 → CRNN → chroma
                          └── Branch B (solo):   guitar stem + full mix → MT3 (program-filtered)
                          ↓
                    MusicXML → LessonJSON → practice UI
```

What is already true:

- MT3 is the primary transcriber; the CRNN and chroma paths are confidence-gated fallbacks.
- Two-branch routing is implemented: chords from the full mix, solo from the guitar stem.
- Evaluation exists but is small: 5 songs, 3 pass / 1 warn / 1 fail, chord-focused.
- CRNN real-world accuracy is **34.7%**; MT3 is the teacher at >80% MIREX-25 on GuitarSet.
- CPU latency is roughly **5 minutes per song**.
- Confidence is a hand-tuned heuristic; the Commit 184 measurement found **ECE 0.7441** on 3 GuitarSet tracks — severe overconfidence. Raw percentages are deliberately not shown in the UI.
- The research community has moved past vanilla MT3: the 2025 AI4Musicians challenge was won by YourMT3+/MusicFM-based systems (F1 ≈ 0.60 vs MT3 ≈ 0.39), and guitar-specific tablature work now treats string/fret assignment as a separate learned task.

This program exists to close the gap between “working demo” and “credible, measured AMT research.”

---

## How this roadmap works

- **One commit = one spec.** Do not combine unrelated work.
- Every spec follows [`docs/COMMIT_TEMPLATE.md`](docs/COMMIT_TEMPLATE.md): status, evidence, goal, research questions, current state, prior art, scope, workstreams, acceptance criteria, verification, risks, references.
- **Acceptance criteria are gates.** A criterion that cannot be verified by a command, artifact, or documented decision is not a criterion.
- **Archive on completion.** Move the full spec to [`priorities-archive.md`](priorities-archive.md) with a completion date and verification summary.
- **Renumbering is allowed.** Active-roadmap numbers are local; archived commits keep their original numbers for traceability.
- **Superseded work stays traceable.** The original spec is preserved in the archive with a pointer to its replacement.

---

## Commit 1 — Harmoniq AMT Research Program

**Status:** blocked — GPU for W1–W4; **Stage 0 (W0, W5, W6) is ready now**
**Priority:** P0
**Depends on:** archived 174, 175, 176, 180; existing MT3/CRNN/chroma pipeline; GuitarSet, IDMT-SMT-Guitar, RWC-P, and pseudo-label tooling; GPU access for W1–W4.
**Evidence:** [`docs/RESEARCH.md`](docs/RESEARCH.md), [`docs/EVALUATION.md`](docs/EVALUATION.md), [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md); CRNN 34.7%; 5-song eval; ~5 min/song CPU; ECE 0.7441 (3 tracks).

### Goal

Turn the existing fallback-chain demo into a reproducible guitar-AMT research system: a challenge-grade evaluation harness, a SOTA-informed teacher/student pipeline, and a tablature-assignment track that is measured rather than heuristic.

### Research questions

1. Can a guitar-conditioned student match or beat the current MT3→CRNN→chroma chain on chord and solo metrics while fitting a <100 ms/frame on-device budget?
2. Does pseudo-labeling real guitar audio with MT3 (or a stronger teacher) close the CRNN’s 34.7% → ≥70% synthetic-to-real gap?
3. Which teacher minimizes instrument leakage and confusion for the guitar solo branch: standard MT3, HT-MT3, or a YourMT3+/MusicFM-style model?
4. Can a single shared encoder with separate chord and guitar-vocabulary solo heads replace the separate CRNN/chroma fallbacks without regression?
5. Does a learned string/fret assignment with playability constraints beat the current `allCellsForMidi` heuristic on tablature usability?
6. What is the calibrated confidence (ECE) of the full pipeline, and which confidence gate should be the release gate?
7. What evaluation protocol — instrument ID, pitch, onset, offset, dynamics, polyphony strata, runtime — should replace the current 5-song verdict?

### Current state

**Exists:**

- Demucs 6-stem separation, MT3 teacher path, two-branch chord/solo routing.
- CRNN TFLite fallback with noise/uncertainty gates, chroma last resort.
- GuitarSet/IDMT/RWC-P CQT pipelines, pseudo-label generation, `build_chord_tflite.py`, `promote_model.py`.
- A 5-song evaluation and a documented failure catalogue.
- Confidence-band UI and an ECE measurement script (Commit 184).

**Missing / weak:**

- Evaluation is too small and chord-focused; no instrument-ID, onset/offset, dynamics, polyphony-stratified, or runtime scoring.
- The CRNN domain gap is unresolved; pseudo-labels exist only as tooling, not at scale.
- No two-head student; the fallback chain remains two separate engines.
- HT-MT3 was never evaluated; newer SOTA teachers were not considered.
- String/fret assignment is a heuristic (`allCellsForMidi`); no playability or tuning/capo model.
- Confidence is not calibrated; the ECE is measured but the release gate is not defined.

**Consolidates:** Commit 174 (pseudo-label retraining), 175 (two-head distillation), 176 (HT-MT3), 180 (evaluation-set expansion). Full original specs are preserved in the archive as superseded.

### Prior art and transferable ideas

External signals were reviewed on **2026-10-31**. The detailed synthesis belongs in [`docs/RESEARCH.md`](docs/RESEARCH.md); this table records only decisions.

| Source | Signal | What to borrow | What to avoid |
| --- | --- | --- | --- |
| Songscription | Instrument-specific isolation, multi-format output, editor-assisted cleanup, lead sheets and difficulty arrangements | Instrument-focused modes; MIDI/MusicXML/Guitar Pro exports; editable corrections | Marketing accuracy claims; opaque “AI assistant” edits without a confidence trail |
| Klang.io | Instrument-specific models, rhythm quantization, downbeat/beat tracking, recording-quality prediction, DAW/API delivery, guitar-technique transcription | Rhythm quantization as an explicit stage; recording-quality gate; quantized/unquantized MIDI; Guitar Pro export | Treating source separation or note detection as the whole transcription problem |
| AI4Musicians 2025 challenge | Scoring covers instrument ID, pitch, onset, offset, and dynamics; MT3 baseline; polyphony is the dominant failure mode | Challenge-style harness; instrument-ID penalty; polyphony strata; runtime reporting | Benchmarking only on a handful of curated songs |
| Spotify AMT overview | AMT = multipitch estimation + onset/offset + instrument recognition + beat/rhythm + expressive timing/dynamics + score typesetting | Evaluate the full notation-level stack, not just chord labels | Reducing AMT to frame-level pitch accuracy |
| arXiv 2406.15249 survey | Frame → note → stream → notation hierarchy; onset+frames and onset+velocity designs; pitch/time augmentation; 50 ms onset tolerance | Onset-aware losses; augmentation; explicit metric definitions; real-time CNN student path | Overfitting to piano-only MAESTRO assumptions |
| YourMT3+ / MIROS | Hierarchical time-frequency attention, mixture of experts, multi-channel decoding for partial labels, cross-stem augmentation, MusicFM self-supervised encoder | Teacher candidate; cross-stem augmentation; multi-channel partial-label training | Assuming a bigger model alone closes data scarcity |
| Fretting-Transformer / TART / HeavyCNN | String/fret ambiguity is a learned translation task; tuning/capo conditioning; joint string-activity prediction; playability constraints | W4 tablature track; tuning/capo tokens; string-activity auxiliary head; playability metrics | Ignoring physical playability in favor of pitch-only accuracy |

### Scope

**In:**

- A unified evaluation harness with challenge-style metrics and reproducible manifests.
- Expanded evaluation corpus (studio, live, home, OOD, jazz harmony).
- Large-scale pseudo-labeling and dataset hygiene.
- Teacher comparison and selection (MT3 / HT-MT3 / YourMT3+-class / MusicFM-class).
- Two-head student distillation with a guitar-vocabulary solo head.
- Learned string/fret assignment and playability-aware tablature.
- Confidence calibration, recording-quality gating, and a feature-flagged rollout.
- Research write-up and reproducibility package.

**Out:**

- New instruments beyond guitar.
- Real-time on-device inference beyond the student latency target.
- Commercial deployment, billing, or marketplace features.
- Rewriting the practice UI or session flow.
- Downloading or redistributing datasets without a licence audit.

### Workstreams and gates

| ID | Workstream | Deliverable | Gate |
| --- | --- | --- | --- |
| **W0** | Evaluation harness & reproducibility | New `scripts/eval_amt.py` (or an extension of existing eval tooling) producing a machine-readable report; ≥7-song manifest; challenge-style metrics; MT3/CRNN/chroma/full-pipeline baselines; fixed splits; per-instrument-count strata; latency and ECE | **G0:** harness reproduces the current 5-song verdicts and emits one report that can be diffed across commits |
| **W1** | Data engine | ≥1,000 real tracks pseudo-labeled with confidence filtering; dataset card; licence audit; cross-stem augmentation; multi-channel partial-label decoding (or a documented rejection) | **G1:** ≥1,000 tracks labeled; held-out split uncontaminated; one command reproduces the manifest |
| **W2** | Teacher selection | Side-by-side MT3 vs HT-MT3 vs YourMT3+/MusicFM on a 50-track sample; instrument-confusion/leakage deltas; chord/solo metrics; latency | **G2:** documented go/no-go and a chosen teacher (or ensemble) for W3 |
| **W3** | Two-head student | Shared encoder; chord head (277-class frame-level); guitar-vocabulary solo head (autoregressive token); QAT/INT8 student; feature flag with instant fallback | **G3:** ≥70% GuitarSet root accuracy or a documented ceiling; no regression on the 5-song eval; <100 ms/frame |
| **W4** | Guitar tablature intelligence | String/fret assignment (Fretting-Transformer-style); tuning/capo conditioning; playability constraints; string-activity auxiliary head; technique-label prototype; metrics for pitch accuracy, tab accuracy, and playability | **G4:** measurable improvement over `allCellsForMidi` on a GuitarSet/DadaGP subset, or an explicit no-go |
| **W5** | Calibration & honest productization | ECE report; recording-quality predictor; confidence gate; fallback orchestration behind a flag; export formats; no raw percentages in UI | **G5:** ECE reported; rollback tested; user-facing wording matches the calibration evidence |
| **W6** | Research write-up | RESEARCH/EVALUATION/KNOWN_FAILURES updates; dataset card; reproducibility commands; publication inputs | **G6:** a clean checkout reproduces the headline numbers with the documented commands |

### Acceptance criteria

- [ ] **W0 / G0:** evaluation manifest covers ≥7 songs (studio, live, re-recorded home blues with proper gain staging, kora/mbira OOD, jazz harmony); the harness reproduces the current 5-song verdicts.
- [ ] **W0 metrics:** instrument ID, pitch, onset/offset F1 at 50 ms, dynamics, overlap, runtime, and confidence ECE are reported; results are stratified by instrument count.
- [ ] **W0 baselines:** MT3, CRNN, chroma, and the full fallback chain are compared on the same manifest.
- [ ] **W1 / G1:** ≥1,000 real tracks are pseudo-labeled with confidence filtering; a dataset card and licence audit are committed; the held-out split is uncontaminated.
- [ ] **W1 augmentation:** cross-stem augmentation and multi-channel partial-label decoding are implemented or explicitly rejected with evidence.
- [ ] **W2 / G2:** a 50-track teacher comparison is documented with instrument-confusion/leakage deltas and a go/no-go decision.
- [ ] **W3 / G3:** one model produces both chord frames and guitar-vocabulary solo tokens; ≥70% GuitarSet root accuracy or a documented ceiling; no regression on the 5-song eval; <100 ms/frame.
- [ ] **W3 rollout:** the student ships behind a feature flag with instant fallback to the existing chain.
- [ ] **W4 / G4:** string/fret assignment beats the `allCellsForMidi` heuristic on pitch accuracy, tab accuracy, or playability — or is documented as a no-go; tuning/capo conditioning is evaluated.
- [ ] **W5 / G5:** confidence ECE is measured on the expanded set; the recording-quality gate is evaluated; no raw confidence percentages appear in the UI; rollback is verified.
- [ ] **W6 / G6:** `docs/RESEARCH.md`, `docs/EVALUATION.md`, and `docs/KNOWN_FAILURES.md` match the measured results; a clean checkout reproduces them.
- [ ] `npm run lint` and `npm run test` pass; backend pytest passes for touched areas.
- [ ] No regression in chord/solo output, right/left-handed diagrams, export formats, or the runtime fallback chain.

### Verification

```bash
# Frontend health (run after any touched TS/TSX)
npm run lint
npm run test

# Backend health (from backend/)
python -m pytest -q

# Evaluation harness (new in W0; exact path finalized there)
python scripts/eval_amt.py --manifest data/eval/manifest.json --report docs/audit/amt-eval.json

# Pseudo-label generation (existing tool)
python scripts/pseudo_label_generate.py --audio-dir <dir>

# Latency benchmark (existing on-device / CRNN benchmark command)
```

Artifacts: evaluation report JSON + Markdown, dataset card, teacher-comparison table, student benchmark table, ECE report, and the updated research docs.

### Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| No GPU or insufficient GPU budget | High | Blocks W1–W4 | Execute W0/W5/W6 on CPU now; rent GPU time or use a hosted notebook only for the gated runs |
| Pseudo-label confirmation bias | Medium | Student learns teacher errors | Hold out real labels; human spot-check a stratified sample; compare against GuitarSet ground truth |
| Dataset licensing (RWC-P is non-commercial) | Medium | Cannot redistribute training data | Licence audit; keep restricted data out of the public release; document provenance |
| Instrument leakage / polyphony | High | Solo branch accuracy collapses in dense mixes | Instrument-ID head, leakage metric, polyphony-stratified evaluation |
| Tab playability vs pitch accuracy | Medium | Playable but wrong tabs, or correct but unplayable | Joint playability constraints; report both metrics; human review on a small set |
| Evaluation overfitting | Medium | Headline gains do not generalize | Fixed holdout, separate challenge-style test, document ceilings |
| Scope creep into product work | Medium | Research commit never closes | W5 is limited to calibration/gating/export; UI work stays out |

### Open questions and assumptions

- 🛑 **GPU access and budget:** W1–W4 cannot start without a concrete GPU provider/timeline. Stage 0 proceeds regardless.
- 🛑 **Teacher licences:** confirm availability and licence terms for HT-MT3, YourMT3+, and MusicFM weights before W2.
- ⚠️ **W4 delivery:** if GPU time is constrained, W4 may be documented as a no-go and split into a follow-up; the gate must still be recorded.
- ⚠️ **Target venue:** ISMIR 2027 late-breaking demo is a stretch goal; no submission is committed here.
- ⚠️ **Dataset release:** RWC-P audio remains opt-in and non-commercial; public reproducibility uses labels/scripts, not restricted audio.

### References

- https://www.songscription.ai/ (accessed 2026-10-31) — instrument-specific transcription, multi-format export, editor-assisted cleanup.
- https://www.ai4musicians.org/research/amt (accessed 2026-10-31) — systematic AMT review, competition, interpretable-model direction.
- https://www.ai4musicians.org/transcription (accessed 2026-10-31) — 2025 challenge protocol: instrument ID, pitch, onset, offset, dynamics, runtime.
- https://klang.io/ (accessed 2026-10-31) — instrument-specific apps, quantized/unquantized MIDI, Guitar Pro, DAW/API delivery.
- https://klang.io/about-us/research/ (accessed 2026-10-31) — rhythm quantization, recording-quality prediction, guitar-technique and tablature research.
- https://research.atspotify.com/publications/automatic-music-transcription-an-overview (accessed 2026-10-31) — AMT subtasks and the notation-level framing.
- https://arxiv.org/abs/2406.15249 (accessed 2026-10-31) — frame/note/stream/notation hierarchy, onset+frames, augmentation, evaluation metrics.
- https://arxiv.org/abs/2407.04822 (accessed 2026-10-31) — YourMT3+: hierarchical attention, MoE, multi-channel decoding, cross-stem augmentation.
- https://arxiv.org/abs/2506.14223 (accessed 2026-10-31) — Fretting-Transformer: MIDI-to-tablature string/fret assignment with tuning/capo conditioning.
- https://arxiv.org/html/2510.02597 (accessed 2026-10-31) — TART: technique-aware audio-to-tab pipeline and playability-aware assignment.

---

## Commit 2 — Part 3 Blog Post — The Meta-Layer

**Status:** deferred — after Commit 1 produces results
**Priority:** P1
**Depends on:** Part 2 published; Commit 1 results for concrete metrics
**Evidence:** [`docs/blog/why-harmoniq-part-2.md`](docs/blog/why-harmoniq-part-2.md) closing paragraph.

### Goal

Write and publish Part 3 of the Harmoniq blog series: building an AI product with AI assistance — the recursive loop of planning, implementing, reviewing, and deciding when to push through a plateau versus change approach.

### Current state

Part 2 is published at harmoniq.ai/blog (owner-confirmed live October 20, 2026) and lives in-repo at [`docs/blog/why-harmoniq-part-2.md`](docs/blog/why-harmoniq-part-2.md). It promises Part 3 at its conclusion:

> “Part 3 will be about the meta-layer of this project: building an AI product with AI assistance, and what that recursive loop taught me about learning, building, and when to push through a plateau versus when to find a different path.”

No Part 3 draft exists. Moving it after Commit 1 means the post can cite measured AMT research results rather than only process anecdotes.

### Scope

- Draft `docs/blog/why-harmoniq-part-3.md` covering the agent-driven workflow (roadmap → spec → commit → review), what the merge/code-review passes surfaced (dead code, stale roadmaps), and honest lessons on process vs. velocity.
- Include concrete examples from this repo: evaluation results, fallback-architecture honesty, and the AMT research programme.
- Publish to harmoniq.ai/blog.
- Link Part 3 from Part 2’s closing paragraph, README, and the [`docs/blog/`](docs/blog/) index.

### Acceptance criteria

- [ ] Part 3 published to harmoniq.ai/blog.
- [ ] Part 2, README, and docs cross-link to Part 3.
- [ ] Post includes real metrics/results from the repo (no placeholder claims).

---

## Completed foundation

Completed work is archived; do not re-open it unless a regression is found, in which case create a new commit rather than editing history.

| Track | Commits | Status |
| --- | --- | --- |
| Phase 0 / Phase 1 foundation | 0.1–97 | Archived |
| Phase 2 chord pipeline + MT3-primary migration | 98–155 | Archived |
| Engagement and product features | 159–168 | Archived |
| Infrastructure (tempo, queues, fingerprinting, stem export) | 169–173 | Archived |
| Agents and pitch detection | 177–179 | Archived |
| Verification, calibration, and native environment | 181–184 | Archived |

See [`priorities-archive.md`](priorities-archive.md) for the full specs, implementation notes, and verification records.
