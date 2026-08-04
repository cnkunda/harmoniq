# PORTFOLIO_PLAN.md — Harmoniq Portfolio Push

> **Goal:** One project that carries both the **MLOps** and **Software Engineering** stories for job applications.
> **Timeline:** 2+ months, committed. **Status snapshot date:** 2026-08-02.

---

## 1. Status Snapshot (verified against code)

| Area | State |
|------|-------|
| Commits | 58 on `main`; Phase 0 + Phase 1 (commits 1–97) complete |
| Phase 2 ML work done | Commit 98 (277-class vocab), 98a (data augmentation), 98b (36-bin CQT), 98d (multi-head attention) |
| 98c leftover | CRNN/BiLSTM works; mobile inference-latency benchmark still unchecked (run on Android emulator) |
| Chord model | `backend/app/chord_model.tflite` (1.1 MB), CRNN + attention + BiLSTM, 277 classes, val_acc ~82%, trained on fully synthetic data |
| Backend pipeline (real) | ingest (yt-dlp/upload) → Demucs htdemucs_6s stems → beat grid → TFLite chord inference → basic-pitch solo → Whisper lyrics → MusicXML + GP5 → AlphaTab prerender |
| Job execution | Thread-per-job, **in-memory dict** (`jobs.py:58`) — lost on restart, no queue, no concurrency |
| Infra present | **None**: no Redis, Celery, MLflow, Prometheus, retry, circuit breakers, DLQ, Docker |
| MT3 | 186 MB `mt3_t5_small` checkpoint staged but **unwired** (`app/mt3/` empty) |
| Tests | 226 frontend unit tests (35 files), 36 backend test files, Playwright, Detox configured |
| Blockers | **Phase 0 baseline clean:** `npm run lint` passes, `vitest run` 226/226 pass, CI gates lint + full test suites |

---

## 2. Portfolio Narrative

**MLOps story:** "I productionized a music-transcription ML pipeline — from in-process threads and in-memory state to a distributed Redis/Celery queue with SSE push updates, circuit breakers, Prometheus observability, an MLflow-tracked model server with drift detection, and Docker deployment."

**SWE story:** "I shipped full-stack product features end-to-end — a beat-grid editor with a dependent-artifact recompute chain, analysis persistence with corrections, and MusicXML rendering on mobile + web."

Both stories are told by the same project; the work order below interleaves them deliberately.

---

## 3. Phase 0 — Presentability Baseline (do first, ~1 week)

Anything a recruiter sees before clicking the repo must be clean. Gate: **`npm run lint` passes, `vitest run` passes, zero tracked junk, README rewritten, CI gates lint + tests.**

### 3.1 Rewrite `README.md` as a case study (highest priority) ✅ DONE
Current line 1 is `# Harmoniq — v1 Build Prompt` — it reads as AI-build instructions, not a project. Replace with:
- Product pitch (2–3 sentences), target user, core promise
- **Screenshots** — add `docs/screenshots/` (home, session loop, fretboard, jam mode; use Expo web or emulator captures)
- Architecture diagram (Mermaid): frontend → FastAPI → Demucs / TFLite / basic-pitch / Whisper / Anthropic
- Tech stack table (frontend, backend, ML, infra)
- Quickstart (backend + frontend, referencing AGENTS.md)
- Testing instructions (`npm run lint`, `npm run test`, `test:ui`, `pytest`)
- Roadmap status pointing to PRIORITIES.md
- **Honest "Known limitations / stubs" section**: stub tab catalog, synthetic-only training data, in-memory job store (until Phase 2), basic-pitch install constraint on Windows/Py3.11, TFLite Flex ops dependency

### 3.2 Fix `npm run lint` (tsc --noEmit, 6 errors) ✅ DONE
- `components/AnimatedPressable.tsx:56` — `style` prop function-form not assignable to `Animated.View` style; flatten/resolve with `StyleSheet.flatten` or narrow the type
- `components/FretboardDiagram.tsx:436-438` — possibly-undefined in `.sort()`/`.filter()`/`.map()` over `chordCells` intervals; add type guard / non-null narrowing

### 3.3 Fix the 7 failing unit tests ✅ DONE
- `src/music/harmonicSimilarity.test.ts` — all 5 fail (module broken or tests stale): fix module or rewrite tests
- `src/music/chordVoicing.test.ts` — 1 fail (open Dm7 shape)
- `src/utils/base64ToUint8Array.test.ts` — 1 fail (1315-byte GP5 fixture stale after MusicXML switch)

### 3.4 Remove tracked junk (visible in GitHub file browser) ✅ DONE
```
git rm debug-566c8e.log
git rm backend/backend.log backend/training.log backend/training_output.log
git rm backend/scripts/training_fixed.log backend/research/h-gain-v1.0.5/training_output.log
git rm -r backend/app/bak_phase1
git rm -r backend/app/mt3        # empty module dir
```
Also delete stale docs: `.github/copilot-instructions.md`, `docs/FULL_BRANCH_REVIEW.md`, `docs/STAGED_REVIEW.md` (archive locally first if wanted).

### 3.5 Repo metadata ✅ DONE
- Add `LICENSE` (MIT)
- Add `ruff` + `mypy` (or `pyright`) config to `backend/pyproject.toml`; run ruff on `backend/app`
- Set GitHub repo About: description, topics (`react-native`, `fastapi`, `mlops`, `music-transcription`, `tensorflow`, `demucs`), website link to Expo web demo if any

### 3.6 Expand CI (`.github/workflows/ci.yml`) ✅ DONE
- Add `tsc --noEmit` gate (frontend job)
- Add full `vitest run` (frontend job)
- Add full `pytest -q` (backend job, keep `HARMONIQ_SKIP_*` envs for stub paths)
- Green checkboxes on the repo become recruiter-visible proof

---

## 4. Phase 1 — Close Out the ML-Quality Story (weeks 1–2)

### Commit 99 — Viterbi Decoding for Chord Progressions ✅ DONE
Transition matrix from training data, Viterbi decoder, log-prob computation, backtracking, beat-alignment gate, key-constrained transition costs, duration-aware filtering, half-beat chord-change resolution, flicker-rate metric (<5%). Run the 98c latency benchmark on the Android emulator to close that item too.

### Commit 102 — Label-Noise Analysis (MT3 Appendix D.2 methodology) ✅ DONE
`analyze_label_noise.py`: chord F1 at tolerances 10–500 ms, F1-vs-tolerance curves, per-chord-type noise sensitivity; ±30 ms temporal jitter augmentation; label quality gate (>100 ms jitter rejected); results in `docs/LABEL_QUALITY.md`. This produces a linkable report artifact — the strongest "rigorous ML evaluation" proof in the roadmap.

**Deliverable:** chord-inference quality story complete: 25 → 277 classes, synthetic augmentation, CRNN+attention, Viterbi smoothing, measured label noise.

---

## 5. Phase 2 — The MLOps Production Arc (weeks 3–6, headline work)

In dependency order:

1. **Commit 136 — Redis + Celery + SSE.** Replace in-memory `jobs` dict; kill BUG-01's polling guard via push-based `GET /analyze/{job_id}/stream` (SSE); job recovery on startup; progressive `analysis_stage` enum; frontend SSE path with polling fallback.
2. **Commit 139 — Error resilience.** Exponential-backoff retry for yt-dlp, circuit breaker for LLM calls, Redis dead-letter queue + inspection/requeue tooling, automatic retry for recoverable errors.
3. **Commit 140 — Observability.** Prometheus metrics endpoint, per-pipeline-stage latency histograms, error-rate alerting, OpenTelemetry tracing, Grafana dashboards.
4. **Commit 137 — ML model server + MLflow.** Dedicated FastAPI inference service with batched inference, model versioning + A/B routing, hot-swap without restart; MLflow run logging + Model Registry (staging → production); drift detection (>3% vs deployment baseline).

**Add (not in PRIORITIES.md, required for the story): Docker + docker-compose**
`backend` (FastAPI) + `worker` (Celery) + `redis` + `prometheus` + `grafana` in one compose file. The repo has zero containerization; compose also solves Celery-on-Windows and makes the demo runnable for interviewers with one command.

**Deliverable:** the resume headline — horizontally scalable, observable, resilient, versioned ML pipeline, deployable via Docker, BUG-01 fixed at root.

---

## 6. Phase 3 — SWE Flagship Feature (weeks 7–8)

### Commit 108 — Beat Grid Editor (UI + recomputation)
Full vertical slice: beat-grid timeline visualization, time-sig picker (2/4, 3/4, 4/4, 6/8, 9/8, 12/8), per-section BPM editor, `POST /analyze/{job_id}/beat-grid/recompute` re-deriving chord timeline → solo notes → MusicXML, progressive `analysis_stage` reveal in the add-song flow, override persistence, Reset to Auto, undo/redo.

### Commit 109 — Analysis persistence & correction editor
SQLite job store (survives restarts) + migrations; `PATCH` endpoints for chord symbols, solo-note parameters, voicing overrides; correction history with revert; `correction_count` / `correction_coverage` metrics; corrections exportable as training data for retraining.

**Deliverable:** demonstrable full-stack depth — schema design, API design, recompute orchestration, React Native UI, dual-DB persistence (SQLite mobile / IndexedDB web).

---

## 7. Phase 4 — ML Rigor Round 2 + Wrap-Up (weeks 9–10)

- **Commit 104 — Temperature sampling** (MT3 §3.3 `(n_i/Σn_j)^0.3`): oversample rare chord types (7#9, alt7, dim7, aug), per-class recall reporting, target +15% rare-chord recall with <2% maj/min regression
- **Commit 105 — QAT**: `tensorflow_model_optimization`, INT8 model <500 KB, <3% accuracy loss, mobile latency check
- **Commit 114 — LLM chord enrichment** (if time): background worker, Claude Haiku/Gemini Flash post-processing, roman numerals, SHA256 caching, rate limiting, accept-only-on-confidence-delta>0.15
- **Wrap-up:** final README refresh with before/after numbers (in-memory → Redis, polling → SSE, no metrics → dashboards, 25 → 277 chord classes, ~55% → 82%+ val acc), architecture diagram update, write the portfolio write-up + bullet points

---

## 8. Explicitly Skip (low ROI for these roles)

| Item | Why |
|------|-----|
| Commit 117 (MT3 as training tool) | 186 MB checkpoint unwired, huge scope, high risk — not needed for the narrative |
| Commits 118–125 (music theory screens, scale explorer) | Product features, little MLOps/SWE signal |
| Commits 126–131 (live mic, Chord Pulse, stem mixer, multi-instrument) | Moderate value; only if weeks run long |
| Commits 132–135 (dynamic sessions, mastery, tempo) | Already-covered product territory |

---

## 9. Risks

- **Celery on Windows** — broken paths on native Windows; do this work in WSL (per AGENTS.md) or rely on Docker from day 1
- **basic-pitch / TensorFlow on Python 3.11+ Windows** — tests must stay stub-gated via `HARMONIQ_SKIP_*` envs (codebase already does this)
- **TFLite Flex ops** — model requires `tensorflow-lite-select-tf-ops`; fine for backend inference, document it
- **Commit 99 "decoding latency <10ms"** — measurable; benchmark before claiming
- **README rewrite scope creep** — keep Phase 0 fixes bounded; don't restructure the repo at the same time

---

## 10. Pre-Application Checklist (final gate)

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
