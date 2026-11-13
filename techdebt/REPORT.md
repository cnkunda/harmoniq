# Harmoniq Technical Debt Audit

**Date:** 2026-11-11  
**Scope:** whole repository (frontend, backend, tests, CI, packaging, docs)  
**Method:** read-only static inspection, git history mining, dependency audits, and a passing `tsc --noEmit` check. Exact commands are in [`METHODOLOGY.md`](./METHODOLOGY.md).

---

## Executive summary

Harmoniq is a feature-rich, unusually well-documented prototype whose type layer is clean and whose backend has a substantial test suite (1,747 test functions). The main risk is not broken code today; it is **concentration and verification**: every commit on `main` (202) belongs to one person, and CI never exercises the UI, native build, or audio tests. The codebase also carries several very large "god" files, two independently maintained database clients, 55 npm advisories, and ~500 MiB of Git history bloated by model and audio binaries. A focused 90-day program can remove most of the velocity and reliability risk without a rewrite.

**Overall health rating: C+**

- Strong: TypeScript strict mode passes; broad backend tests; extensive docs and UX automation; centralized error handler; upload size limits; no committed secrets; Prometheus/Grafana present.
- Weak: bus factor 1; no coverage measurement; CI gaps; god modules; duplicated native/web persistence; dependency backlog; repository bloat.

---

## Top 10 priorities

Ranked by `(severity x impact spread) / effort`, with a severity override for the bus-factor item. The full scored backlog is in [`backlog.json`](./backlog.json).

| # | Priority | Score | Severity | Effort | Evidence |
|---|----------|-------|----------|--------|----------|
| 1 | Restore CI quality gates (ffmpeg, Playwright smoke, Python lint, coverage) | 20.0 | 4 | S (2d) | `.github/workflows/ci.yml`, `scoring-tests.yml`; `skipif` guards at `backend/tests/test_audio_quality.py:112`, `test_audio_fingerprint.py:77` |
| 2 | Add coverage measurement and thresholds | 20.0 | 4 | S (2d) | `vitest.config.ts` (`environment: node`, only `src/**/*.test.ts`); zero `*.test.tsx` files |
| 3 | Reduce single-maintainer bus factor | 3.1 (severity override) | 5 | L (15d) | `git shortlog -sne HEAD` -> 202/202 by `cnkunda` |
| 4 | Remove Docker/config drift | 9.0 | 3 | S (2d) | root `Dockerfile:13-14`, `backend/Dockerfile:8-12`, `docker-compose.yml:10-12,37` |
| 5 | Triage dependency advisories and non-major upgrades | 5.3 | 4 | M (3d) | `npm audit`: 1 critical, 18 high, 35 moderate, 1 low; `npm outdated`: 47 |
| 6 | Narrow broad exception handling | 4.0 | 3 | M (4d) | 209 `except Exception` in 56 backend files; silent `pass` at `backend/app/metrics.py:241-260` |
| 7 | Unify native/web database implementations | 2.0 | 4 | L (15d) | `src/db/client.native.ts` (1,593) vs `client.web.ts` (1,123); `AGENTS.md:234-239` |
| 8 | Split god modules and the 807-line pipeline function | 1.5 | 4 | L (15d) | `backend/app/main.py` (1,248 / 30 endpoints), `analyze_audio.py:267` (807 lines) |
| 9 | Document configuration (5 of 88 backend env vars) | 6.0 | 2 | S (1d) | `.env.example`; 88 distinct `os.getenv` names under `backend/app/` |
| 10 | Archive/remove dead research snapshots and repo bloat | 4.0 | 2 | S (1d) | `backend/research/h-gain-v1.0.1..v1.0.5` (9,312 py lines), `backend/app/bak_phase1/`, 507.35 MiB pack |

---

## Findings by category

Labels: **Confirmed** = directly verified in code or command output; **Likely** = strongly indicated but not executed; **Speculative** = judgement call.

### 1. Code quality

- **Confirmed - God modules.** `backend/app/main.py` is 1,248 lines with 30 inline `@app.*` endpoints plus 8 routers; `backend/app/schemas.py` holds 119 classes in 1,763 lines; `backend/scripts/build_chord_tflite.py` is 5,016 lines. The largest functions are `build_lesson_json_from_librosa` (807 lines, `backend/app/analyze_audio.py:267`), `analyze_job_task` (327, `backend/app/tasks.py:64`), `build_musicxml` (322, `backend/app/musicxml_builder.py:997`), and `_process_analyze_job` (309, `backend/app/jobs.py:557`).
- **Confirmed - God screens.** `app/(tabs)/jam/index.tsx` is 1,641 lines with 13 `useState` and 8 `useEffect` hooks; `app/session/study.tsx` 1,159 lines with 14 `useState`; `app/(tabs)/index.tsx` 1,119 lines. Deeply nested JSX is concentrated in these files (332 lines indented 20+ spaces in the jam screen).
- **Confirmed - Dead artifacts and duplication.** `backend/app/bak_phase1/` has no references. Five archived model snapshots (`backend/research/h-gain-v1.0.1..v1.0.5`) repeat 9,312 Python lines plus five TFLite models; only v1.0.5 differs materially from the others (three files share the same SHA-256). A 1.2 MB `chord_model_stage1_best.keras.backup` is tracked.
- **Confirmed - Markers.** 13 TODO/@deprecated markers in 9 source files. Themes: auth/user identity (`app/(tabs)/index.tsx:232`), unimplemented product flows (`app/onboarding/results.tsx:164`, `backend/app/coach.py:1428`), GP5 export deprecation (`src/utils/lessonTabs.ts:3`, `src/types/index.ts:376-380`, `components/AlphaTabWebView.tsx:28`), and future work (`src/session/persistGhostTake.ts:40`, `src/music/fingerSuggestion.ts:40`).

### 2. Architecture

- **Confirmed - Two persistence implementations with independent schema histories.** `src/db/client.native.ts` (1,593 lines) and `src/db/client.web.ts` (1,123 lines) implement the `HarmoniqDbClient` contract; the diff is ~2,100 non-whitespace lines and `AGENTS.md:234-239` records 14 mobile migrations vs v4 on web. Divergence here silently breaks user progress.
- **Confirmed - Leaky API layer, narrower than first reported.** `src/api/` contains 16 expected backend fetches and is imported by 44 files. Two call sites outside it still call `${API_BASE_URL}` directly: `app/session/listen.tsx:148` and `src/session/useOrientClip.ts:52`. Both request `/session/orient-clip`, duplicating the same request and error-handling logic.
- **Confirmed - Main module boundary bypassed.** `backend/app/main.py` still owns discovery, taste, curriculum, Spotify, mentor, jam, export, and job endpoints that its own docstring says belong in routers (`backend/app/main.py:1`).
- **Confirmed - Unused direct dependency.** `@tombatossals/react-chords` (`package.json:37`) has zero imports; `priorities-archive.md:2221` already records it as unused.
- **Likely - Coupled job runtime.** `backend/app/jobs.py:902-923` silently falls back from Celery to daemon threads; behavior depends on Redis/Celery availability and process lifetime. This is documented as intentional for v1, so it is classified as monitor rather than defect.

### 3. Dependencies

- **Confirmed - npm exposure.** `npm audit --json` reports 55 vulnerabilities: 1 critical (`shell-quote`), 18 high, 35 moderate, 1 low. `expo-router` is a direct high finding; the critical and most high findings are transitive. All report a fix path, but the direct `expo-router` fix requires a major version.
- **Confirmed - Major versions behind.** `npm outdated` reports 47 packages, including Expo 54.0.35 -> 58.0.24, React Native 0.81.5 -> 0.88.1, React 19.1.0 -> 19.3.1, `react-native-audio-api` 0.11.7 -> 1.0.0, `lucide-react-native` 0.544 -> 1.72, and `expo-router` 6.0.24 -> 58.0.31.
- **Confirmed - Python is unpinned and unaudited.** `backend/pyproject.toml` uses `>=` for 24 dependencies (only `torch`/`torchaudio` are pinned); there is no constraints/lock file. `pip-audit` is not installed in the WSL environment, so Python CVE status is unknown.
- **Confirmed - Heavy dependencies in the default install.** `backend/pyproject.toml:12-38` includes PyTorch, Demucs, Whisper, TensorFlow model optimization, and librosa. `tensorflow-model-optimization` is used only by training/QAT scripts and tests (`backend/scripts/build_chord_tflite.py`, `backend/app/student/model.py`, `scripts/run_qat_only.py`), not by the serving API.
- **Confirmed - Unused package** `@tombatossals/react-chords` (see Architecture).

### 4. Testing

- **Confirmed - No coverage measurement or gate.** Neither `vitest.config.ts`, `playwright.config.ts`, nor CI configures coverage; there is no coverage threshold anywhere.
- **Confirmed - Component layer is not unit-tested.** Vitest runs with `environment: 'node'` and includes only `src/**/*.test.ts`; there are zero `*.test.tsx` files. All 158 `.tsx` files depend on Playwright, which CI does not run.
- **Confirmed - Critical modules lack direct tests.** There are no direct tests for `src/audio/GlobalAudioManager.ts`, `src/audio/Mixer.*`, `src/audio/recordSession.*`, `src/db/client.native.ts`, `src/db/client.web.ts`, or `src/config.ts`. The API layer has tests (`src/api/analyze.test.ts`, `analyzeSse.test.ts`), but the two call sites outside it are untested.
- **Confirmed - Audio tests can silently skip.** `ci.yml` does not install `ffmpeg`; three modules are `skipif(shutil.which("ffmpeg") is None)`-guarded (`backend/tests/test_audio_quality.py:112`, `test_audio_fingerprint.py:77`, `test_commit171_audio_cache.py:123`), so they skip on any runner without it. Five skip/xfail markers exist overall.
- **Confirmed - UI and mobile suites are not in CI.** `ci.yml` and `scoring-tests.yml` never invoke `npm run test:ui` or `npm run test:mobile`. Playwright is configured with `retries: 2` under CI, suggesting known flakiness.
- **Confirmed - Small assertion weakness, not emptiness.** 1,747 backend test functions and 3,840 asserts is healthy; some tests rely on `toBeDefined()` only (e.g. `src/music/progressionAnalysis.test.ts:8-104`), but I found no tests that assert nothing.
- **Confirmed - Long full suite.** `ci.yml` allows 45 minutes for the complete backend suite and runs it alongside a second workflow that reruns a large subset.

### 5. Build, CI/CD, and infrastructure

- **Confirmed - Two overlapping CI workflows.** `ci.yml` and `scoring-tests.yml` trigger on the same push/PR events and duplicate lint + test work, doubling compute and queue time.
- **Confirmed - No Python static analysis.** CI runs pytest only; there is no `ruff`, `flake8`, `mypy`, or `pyright` step. `npm run lint` is `tsc --noEmit` only, with no ESLint.
- **Confirmed - Docker drift.** The root `Dockerfile` copies `backend/setup.cfg*`/`backend/setup.py*` (both absent, `Dockerfile:13-14`) and is not the file Compose uses. Compose builds `backend/Dockerfile` (`docker-compose.yml:10-12`), which runs `pip install -e .` before copying `README.md`/`app/` (`backend/Dockerfile:8-12`), so the install relies on an incomplete source tree. Compose sets `DATABASE_URL` to `postgresql+asyncpg` (`docker-compose.yml:37`), but the app only reads `DATABASE_URL_SYNC` (`backend/app/db.py:15`) and only `psycopg2-binary` is declared (`backend/pyproject.toml:68`). The asyncpg URL is dead configuration; the editable-install ordering is a separate **likely** build risk.
- **Confirmed - No deployment pipeline.** `.github/workflows/` contains test jobs only. There is no image build/publish, migration check, EAS build, or environment promotion. Cerebrium (`cerebrium_w2/cerebrium.toml`) is research-only.
- **Confirmed - Configuration drift.** 88 distinct backend environment variables are read under `backend/app/`, while `.env.example` documents 5 client-facing values (and none of the backend flags).
- **Confirmed - No dangerous secrets committed.** `.env` is untracked and no key patterns matched. Compose contains only local dev credentials (`harmoniq_dev`).

### 6. Documentation and knowledge

- **Confirmed - Effectively one maintainer.** All 202 commits on `main` belong to two `cnkunda` addresses (`git shortlog -sne HEAD`: 102 + 100). `--all` adds five "VS Code" entries; no other human author appears. This is the single largest continuity risk.
- **Confirmed - Documentation volume is a strength, but config docs lag.** `README.md` is 49 KB and there are 19 `docs/**/*.md` files plus `AGENTS.md`; the repo has strong design/research write-ups. However, setup docs cannot cover the 88 backend flags, there is no `docs/README.md` index, and two README passages are stale: line 358 routes MIDI export through Basic Pitch even though the exporter converts GP5 to MIDI, and line 709 presents a basic-pitch-only pipeline as the validation gate despite MT3 being primary.
- **Confirmed - Stale product claims.** `app/onboarding/results.tsx:164` simulates analysis with a 500 ms delay instead of calling `/analyze`; `backend/app/coach.py:1428` documents a template-only coach response. These are visible product gaps, not just docs.

### 7. Hotspots (churn x size/complexity)

| File | Changes | Size / signal |
|------|---------|---------------|
| `backend/app/schemas.py` | 51 | 1,763 lines, 119 classes |
| `app/session/study.tsx` | 48 | 1,159 lines, 14 `useState` |
| `components/FretboardDiagram.tsx` | 37 | 1,449 lines |
| `backend/app/main.py` | 37 | 1,248 lines, 30 inline endpoints |
| `backend/app/analyze_audio.py` | 37 | 1,073 lines, 807-line function |
| `app/(tabs)/index.tsx` | 37 | 1,119 lines, hardcoded identity |
| `backend/app/jobs.py` | 33 | 1,310 lines, thread/Celery fallback |
| `backend/app/chord_inference.py` | 28 | 1,653 lines |
| `components/AlphaTabWeb.web.tsx` | 32 | 1,550 lines |
| `backend/scripts/build_chord_tflite.py` | 22 | 5,016 lines |

These files combine high change frequency with high size/complexity and should receive refactor and review attention first.

### 8. Markers (grouped by theme)

- **Identity/auth:** `app/(tabs)/index.tsx:232` (`TODO(auth)`).
- **Unimplemented product flows:** `app/onboarding/results.tsx:164`; `backend/app/coach.py:1428`; `backend/scripts/analyze_label_noise.py:139,161`.
- **Deprecated export path:** `src/utils/lessonTabs.ts:3,23`; `src/types/index.ts:376-380`; `components/AlphaTabWebView.tsx:28`.
- **Future features:** `src/session/persistGhostTake.ts:40`; `src/music/fingerSuggestion.ts:40`.

### 9. Security and reliability smells

- **Confirmed - Broad exception handling.** 209 `except Exception` clauses in 56 backend files. Most log and fall back (acceptable for optional enrichment), but `backend/app/metrics.py:241-260` silently `pass`es, hiding Redis/metric failures. Broad catches in `backend/app/analyze_audio.py` (19 occurrences) can also turn data errors into generic fallback lessons.
- **Confirmed - Reasonable input limits.** Uploads are capped at 50 MB (`backend/app/routers/analyze.py:87`), batch size is capped (`:1402`), operator routes are token-gated (`:1229-1233`), and shell execution avoids `shell=True`.
- **Confirmed - Timeouts exist on most external calls.** `httpx` clients use timeouts (`backend/app/spotify.py:111`, `routers/ws.py:73`), subprocess calls use timeouts (`backend/app/alphatab_prerender.py:91`, `pipeline_proof.py:54`), and `tenacity` retry helpers are present (`backend/app/retry.py`). This is a strength.
- **Confirmed - Job durability risk.** Analysis can run in a daemon thread when Celery is unavailable (`backend/app/jobs.py:902-923`), so work is lost on process restart. The code documents this as a v1 trade-off.
- **Confirmed - Frontend logging noise.** 179 `console.*` calls remain under `src/`, `app/`, and `components/`; many are prefixed, but release builds will still emit them.

---

## Quick wins, strategic investments, monitor, accept

**Quick wins:** TD-01 CI gates, TD-02 coverage tooling, TD-03 Docker drift, TD-04 env docs, TD-05 npm triage, TD-06 Python lock/audit, TD-07 exception narrowing, TD-08 dead artifacts, TD-09 API centralization, TD-10 marker hygiene, TD-24 unused dependency, TD-26 stale docs refresh.

**Strategic investments:** TD-11 deployment automation, TD-12 bus factor, TD-13 shipped stubs, TD-14 hotspot ownership, TD-16 DB unification, TD-17 critical-path tests, TD-21 Expo SDK upgrade, TD-22 backend god modules, TD-23 frontend god screens.

**Monitor:** TD-15 in-memory job fallback, TD-18 frontend console noise, TD-19 backend suite runtime.

**Accept (intentionally not backlog items):** bundled soundfonts/WASM assets (required for offline playback) and local Docker development credentials (not used in production). The large in-repo documentation set is also retained; the actionable part is the stale-reference refresh tracked as TD-26.

---

## 30 / 60 / 90-day paydown plan

### Days 0-30 (stop the bleeding)
1. Consolidate CI into one workflow; install `ffmpeg`; run `test:ui` smoke on PRs; add `ruff` (and `mypy` on new modules); fail on coverage regression.
2. Add `vitest` coverage (`v8`) with a baseline threshold; publish the number so it can only go up.
3. Run `npm audit fix` for non-major fixes; document the remaining direct `expo-router` major as a tracked exception.
4. Remove the unused asyncpg `DATABASE_URL` (or consume it with a declared driver), delete or repair the stale root Dockerfile, and add `docker build` to CI.
5. Generate `.env.example`/docs from the 88 env reads; mark required vs optional.
6. Remove `@tombatossals/react-chords` and `backend/app/bak_phase1/`; move research snapshots to release artifacts or Git LFS.
7. Start an ADR/runbook set and pair on the top hotspots to reduce bus factor.
8. Correct the stale Basic Pitch claims in `README.md` and add a docs index.

### Days 31-60 (structural)
1. Extract `main.py` inline endpoints into existing/new routers until `main.py` is composition-only.
2. Break `build_lesson_json_from_librosa` into staged functions (ingest -> analyze -> transcribe -> assemble) with tests at each boundary.
3. Add component tests (`jsdom` + Testing Library) for the five highest-traffic screens and the audio/db modules.
4. Move the two out-of-layer orient-clip fetches into `src/api/` and deduplicate them; add an import boundary.
5. Add `pip-audit` and a constraints lock (`pip-compile`); move QAT-only dependencies to a training extra.
6. Narrow exceptions in `analyze_audio.py`, `jobs.py`, and `metrics.py`; add error counters/metrics.

### Days 61-90 (strategic)
1. Plan and spike the Expo SDK 58 / RN 0.88 upgrade in an isolated branch; do not combine with feature work.
2. Define a shared DB contract test suite that runs against both native and web clients; converge migration versioning.
3. Split the jam and study screens into hooks + presentational components; set a file-size/complexity budget in review.
4. Wire the onboarding analysis flow to `POST /analyze` or gate it behind an explicit "demo" flag; replace the coach template with a real path or label it.
5. Decide the production job runtime (Celery required vs documented thread fallback) and add deployment automation with migration checks.
6. Rotate ownership: assign a second reviewer/owner per hotspot and record it in `CODEOWNERS`.

---

## What I could not assess

- **Python CVE status:** `pip-audit` is not installed in the WSL environment; I did not install tools.
- **Actual cyclomatic complexity:** `radon` is unavailable; I used function length, nesting depth, state counts, and churn as proxies.
- **Runtime/build behavior:** I did not build Docker images, run the backend or Vitest suites, run Playwright/Detox, or start Expo (these write artifacts or need emulators). Docker and test findings are static-analysis based and labelled accordingly.
- **Coverage numbers:** no coverage tool is configured; I could not produce a percentage.
- **Production topology, SLOs, cost, and incident history:** no deploy manifests, infrastructure-as-code, or telemetry configuration exists in the repo beyond local Prometheus/Grafana.
- **Feature-by-feature correctness:** I did not execute the audio/MT3 pipeline or validate model accuracy; research claims in `docs/` were not reproduced.
- **Working-tree changes:** the tree had uncommitted modifications at audit time (e.g. `PRIORITIES.md`, `backend/tests/conftest.py`, `components/ListenStemPanel.tsx`); findings describe the committed state plus current files on disk.
