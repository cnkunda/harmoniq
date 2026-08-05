# PORTFOLIO_PLAN.md — Harmoniq Portfolio Push

> **Goal:** One project that carries both the **MLOps** and **Software Engineering** stories for job applications.
> **Timeline:** 2+ months, committed. **Status snapshot date:** 2026-08-05.

---

## 1. Status Snapshot (verified against code)

| Area | State |
|------|-------|
| Commits | 58 on `main`; Phase 0 + Phase 1 (commits 1–97) + Phase 2 MLOps + Phase 3 SWE + Phase 4 ML Rigor complete |
| Phase 2 ML done | Commit 98 (277-class vocab), 98a (data augmentation), 98b (36-bin CQT), 98d (multi-head attention) |
| Phase 4 ML Rigor done | Commit 104 (temperature sampling), 105 (QAT), 114 (LLM chord enrichment + Roman numerals) |
| Phase 2 MLOps done | Redis/Celery/SSE, error resilience (retry/circuit breaker/DLQ), observability (Prometheus/Grafana), ML model server + MLflow + drift detection, Docker compose |
| 98c leftover | CRNN/BiLSTM works; mobile inference-latency benchmark still unchecked (run on Android emulator) |
| Chord model | `backend/app/chord_model.tflite` (1.1 MB), CRNN + attention + BiLSTM, 277 classes, val_acc ~82%, trained on fully synthetic data |
| Backend pipeline (real) | ingest (yt-dlp/upload) → Demucs htdemucs_6s stems → beat grid → TFLite chord inference → basic-pitch solo → Whisper lyrics → MusicXML + GP5 → AlphaTab prerender |
| Job execution | **Redis-backed** job store with Celery dispatch; SSE push updates; thread fallback when Redis unavailable |
| Infra present | **Redis**, **Celery**, **MLflow**, **Prometheus**, **Grafana**, retry, circuit breakers, DLQ, **Docker compose** (6 services) |
| Tests | 87 backend tests passing (53 Viterbi + 34 label noise + 22 Phase 2 MLOps + existing inference tests) |
| Blockers | **Phase 0 baseline clean:** `npm run lint` passes, `vitest run` 226/226 pass, CI gates lint + full test suites |

---

## 2. Portfolio Narrative

**MLOps story:** "I productionized a music-transcription ML pipeline — from in-process threads and in-memory state to a distributed Redis/Celery queue with SSE push updates, circuit breakers, Prometheus observability, an MLflow-tracked model server with drift detection, and Docker deployment."

**SWE story:** "I shipped full-stack product features end-to-end — a beat-grid editor with a dependent-artifact recompute chain, analysis persistence with corrections, and MusicXML rendering on mobile + web."

Both stories are told by the same project; the work order below interleaves them deliberately.

---

## 3. Phase 0 — Presentability Baseline ✅ COMPLETE

Anything a recruiter sees before clicking the repo must be clean. Gate: **`npm run lint` passes, `vitest run` passes, zero tracked junk, README rewritten, CI gates lint + tests.**

- **3.1 Rewrite `README.md` as a case study** ✅ DONE
- **3.2 Fix `npm run lint`** ✅ DONE
- **3.3 Fix the 7 failing unit tests** ✅ DONE
- **3.4 Remove tracked junk** ✅ DONE
- **3.5 Repo metadata** ✅ DONE
- **3.6 Expand CI** ✅ DONE

---

## 4. Phase 1 — Close Out the ML-Quality Story ✅ COMPLETE

### Commit 99 — Viterbi Decoding for Chord Progressions ✅ DONE
Transition matrix from training data, Viterbi decoder, log-prob computation, backtracking, beat-alignment gate, key-constrained transition costs, duration-aware filtering, half-beat chord-change resolution, flicker-rate metric (<5%).

### Commit 102 — Label-Noise Analysis (MT3 Appendix D.2 methodology) ✅ DONE
`analyze_label_noise.py`: chord F1 at tolerances 10–500 ms, F1-vs-tolerance curves, per-chord-type noise sensitivity; ±30 ms temporal jitter augmentation; label quality gate (>100 ms jitter rejected); results in `docs/LABEL_QUALITY.md`.

**Deliverable:** chord-inference quality story complete: 25 → 277 classes, synthetic augmentation, CRNN+attention, Viterbi smoothing, measured label noise.

---

## 5. Phase 2 — The MLOps Production Arc ✅ COMPLETE

1. **Commit 136 — Redis + Celery + SSE.** ✅ DONE
2. **Commit 139 — Error resilience.** ✅ DONE
3. **Commit 140 — Observability.** ✅ DONE
4. **Commit 137 — ML model server + MLflow.** ✅ DONE
5. **Docker + docker-compose** ✅ DONE

**Deliverable:** the resume headline — horizontally scalable, observable, resilient, versioned ML pipeline, deployable via Docker, BUG-01 fixed at root.

---

## 6. Phase 3 — SWE Flagship Feature ✅ COMPLETE

### Commit 108 — Beat Grid Editor (UI + recomputation) ✅ DONE
Full vertical slice: beat-grid timeline visualization, time-sig picker, per-section BPM editor, `POST /analyze/{job_id}/beat-grid/recompute`, progressive `analysis_stage` reveal, override persistence, Reset to Auto, undo/redo.

### Commit 109 — Analysis persistence & correction editor ✅ DONE
SQLite job store (survives restarts) + migrations; `PATCH` endpoints for chord symbols, solo-note parameters, voicing overrides; correction history with revert; `correction_count` / `correction_coverage` metrics; corrections exportable as training data.

**Deliverable:** demonstrable full-stack depth — schema design, API design, recompute orchestration, React Native UI, dual-DB persistence (SQLite mobile / IndexedDB web).

---

## 7. Phase 4 — ML Rigor Round 2 ✅ COMPLETE

- **Commit 104 — Temperature sampling** ✅ DONE
- **Commit 105 — QAT** ✅ DONE
- **Commit 114 — LLM chord enrichment** ✅ DONE

---

## 8. Wrap-Up (in progress)

- [ ] Final README refresh with before/after numbers (in-memory → Redis, polling → SSE, no metrics → dashboards, 25 → 277 chord classes, ~55% → 82%+ val acc)
- [ ] Architecture diagram update
- [ ] Portfolio write-up + bullet points

---

## 9. Explicitly Skip (low ROI for these roles)

| Item | Why |
|------|-----|
| Commit 117 (MT3 as training tool) | 186 MB checkpoint unwired, huge scope, high risk — not needed for the narrative |
| Commits 118–125 (music theory screens, scale explorer) | Product features, little MLOps/SWE signal |
| Commits 126–131 (live mic, Chord Pulse, stem mixer, multi-instrument) | Moderate value; only if weeks run long |
| Commits 132–135 (dynamic sessions, mastery, tempo) | Already-covered product territory |

---

## 10. Risks

- **Celery on Windows** — broken paths on native Windows; do this work in WSL (per AGENTS.md) or rely on Docker from day 1
- **basic-pitch / TensorFlow on Python 3.11+ Windows** — tests must stay stub-gated via `HARMONIQ_SKIP_*` envs (codebase already does this)
- **TFLite Flex ops** — model requires `tensorflow-lite-select-tf-ops`; fine for backend inference, document it
- **README rewrite scope creep** — keep Phase 0 fixes bounded; don't restructure the repo at the same time

---

## 11. Pre-Application Checklist (final gate)

- [ ] Repo is **public** and GitHub About/description/topics set
- [x] `npm run lint` passes locally and in CI
- [x] `vitest run` passes locally and in CI
- [ ] Backend `pytest -q` passes (with skip envs) and in CI
- [x] README rewritten: screenshots render, architecture diagram correct, known-limitations honest
- [x] Zero tracked junk (logs, `bak_phase1`, stale review docs)
- [x] LICENSE present
- [ ] `PORTFOLIO_PLAN.md` Phase 2 items complete: docker-compose demo runs from cold clone
- [ ] Resume bullet points drafted from the Deliverables lines in Phases 0–4

---

## Appendix A — Code Quality & Presentability Audit (2026-08-02)

### Critical
| # | Issue | Evidence |
|---|-------|----------|
| 1 | README.md is a "Build Prompt" (`# Harmoniq — v1 Build Prompt`, "What You Are Building", "Do not use the default 4-stem model") | README.md:1–47 |
| 2 | No screenshots / demo media anywhere in repo | — |
| 3 | `npm run lint` fails: 6 tsc errors | `components/AnimatedPressable.tsx:56`, `components/FretboardDiagram.tsx:436–438` |
| 4 | 7 failing unit tests across 3 files | `src/music/harmonicSimilarity.test.ts` (5), `src/music/chordVoicing.test.ts` (1), `src/utils/base64ToUint8Array.test.ts` (1) |
| 5 | No LICENSE | — |
| 6 | CI runs only 2 backend + 3 frontend test files; no lint gate | `.github/workflows/scoring-tests.yml` |

### High
| # | Issue | Evidence |
|---|-------|----------|
| 7 | Tracked junk in git history | `debug-566c8e.log`, `backend/*.log` ×4, `backend/research/h-gain-v1.0.5/training_output.log`, `backend/app/bak_phase1/` (~160 MB model files) |
| 8 | Stale/inconsistent README content | "Phase 0 complete; Phase 1 onward is active" (now Phase 2); Phosphor (line 39) vs lucide (line 62); pipeline spec duplicated at lines 86–104 and 386–405 with GP5-primary language (MusicXML is canonical since Commit 107) |
| 9 | Legacy docs | `.github/copilot-instructions.md` (flagged partially stale in AGENTS.md), `docs/FULL_BRANCH_REVIEW.md`, `docs/STAGED_REVIEW.md` |
| 10 | No backend lint/format tooling | no ruff/black/mypy in `backend/pyproject.toml` |

### Green (verified)
- `.env` files not tracked; only `.env.example` — no leaked secrets
- Zero TODO/FIXME markers in `src/`
- 22 GB `backend/data` not tracked; no `__pycache__` tracked
- Strict TypeScript (`strict: true`), `@/*` alias working
- 226 frontend unit tests, 36 backend test files, Playwright + Detox configured
- AGENTS.md, DESIGN_SYSTEM.md, PRIORITIES.md, docs/E2E_DEMO.md present; recent commits well-messaged
