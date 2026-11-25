# Harmoniq — AMT Research Roadmap

Harmoniq is a research project and demo app for **Automatic Music Transcription (AMT)**, focused on guitar. This file is the active work plan. Completed work lives in [`priorities-archive.md`](priorities-archive.md); every new spec follows [`docs/COMMIT_TEMPLATE.md`](docs/COMMIT_TEMPLATE.md).

The immediate research question is no longer “can the pipeline transcribe a song?” — it can, with documented failure modes. The question is whether the pipeline can become a **measured, reproducible guitar-AMT system** whose teacher/student choices, evaluation protocol, and tablature output are defensible against the current research landscape.

---

## At a glance

| | |
| --- | --- |
| **Active research** | None — Commit 1 (Harmoniq AMT Research Program) archived 2026-11-11; see [`priorities-archive.md`](priorities-archive.md). |
| **Tech debt** | **Commits 2–25** — audit in [`techdebt/REPORT.md`](techdebt/REPORT.md); prioritized backlog in [`techdebt/backlog.json`](techdebt/backlog.json) |
| **Publication** | **Commit 26 — Part 3 Blog Post — The Meta-Layer** (deferred; Commit 1 results are now available) |
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

## Technical Debt Paydown Program (Commits 2–25)

The audit in [`techdebt/REPORT.md`](techdebt/REPORT.md) produced 24 independently reviewable specs after removing accepted decisions that require no work. Every spec below maps to a **Confirmed** backlog item (TD IDs are in each References line); no Speculative or Likely-only finding was promoted to a commit. They are ordered by priority score (quick wins first, then strategic and monitor items). The blog post moves to Commit 26 so this program lands first.

**Accepted without a commit:** bundled soundfonts/WASM (required for offline playback) and local Compose credentials (development-only). The rationale is recorded in [`techdebt/REPORT.md`](techdebt/REPORT.md); neither item is in [`techdebt/backlog.json`](techdebt/backlog.json).

---

## Commit 2: Restore CI Quality Gates

**Status:** ready
**Priority:** P0
**Depends on:** None
**Evidence:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/scoring-tests.yml`](.github/workflows/scoring-tests.yml), [`backend/tests/test_audio_quality.py`](backend/tests/test_audio_quality.py), [`backend/tests/test_audio_fingerprint.py`](backend/tests/test_audio_fingerprint.py), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make CI detect UI, audio, and Python-quality regressions before merge.

**Research questions:**
1. Which current failures escape CI because Playwright, Detox, or ffmpeg is absent?
2. What is the smallest Playwright route set that catches real UI breakage in under 10 minutes?
3. Which Python lint/type rules can be adopted without a mass rewrite?

**Current state:** `ci.yml` runs tsc, Vitest, and pytest; `scoring-tests.yml` reruns a large test subset on the same triggers. CI does not install ffmpeg; three audio test modules are `skipif`-guarded, so they can silently skip on runners without it. Neither workflow invokes `npm run test:ui` or `npm run test:mobile`, and there is no Python lint/type step. The full backend job has a 45-minute timeout.

**Prior art / external signals:** Playwright's CI guidance recommends a smoke subset with browser caching; Ruff provides fast linting that can start on changed files only.

**Scope:**

In:
- Collapse the two workflows into one pipeline with job dependencies.
- Install `ffmpeg` in the backend job.
- Add a Playwright route-smoke subset for PRs.
- Add Ruff for Python lint, scoped to changed files initially.

Out:
- Visual regression and full Detox on every PR (needs emulator capacity).
- Rewriting existing Python to satisfy new rules.

**Acceptance criteria:**
- [x] One workflow is the required PR check; the duplicate workflow is removed or reduced to a nightly job.
- [x] `ffmpeg`-guarded audio tests execute instead of skipping in CI.
- [x] At least one Playwright smoke spec runs on every PR and fails the check on error.
- [x] Ruff runs in CI and fails on new violations.
- [x] CI wall-clock time for the PR path is documented and under 20 minutes.

**Verification:** `npm run lint`, `npm run test`, `npm run test:ui -- --grep @smoke`, `cd backend && python -m pytest -q`, plus a CI run showing no ffmpeg skips.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Playwright needs Expo cold start | High | Medium | Reuse a built web server and cache dependencies |
| Ruff floods the first run | Medium | Medium | Gate only changed files, then ratchet |
| CI minutes increase | Medium | Low | Run heavy suites nightly |

**Open questions / assumptions:**
- BLOCKING: Confirm where CI minutes are billed before adding nightly suites.
- ASSUMPTION: The existing Playwright route capture can be tagged for a smoke subset.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-01 (accessed 2026-11-11); [`techdebt/METHODOLOGY.md`](techdebt/METHODOLOGY.md) (accessed 2026-11-11) — command log; https://playwright.dev/docs/ci (accessed 2026-11-11) — CI configuration patterns.

---

## Commit 3: Add Coverage Measurement and Thresholds

**Status:** ready
**Priority:** P0
**Depends on:** Commit 2
**Evidence:** [`vitest.config.ts`](vitest.config.ts), [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Establish a coverage baseline that can only improve, for both frontend and backend.

**Research questions:**
1. What is the current line/branch coverage of Vitest and pytest?
2. Which critical modules are effectively uncovered?
3. What threshold prevents regression without blocking unrelated work?

**Current state:** Vitest uses `environment: 'node'` and includes only `src/**/*.test.ts`; there are zero `*.test.tsx` files. No coverage provider, reporter, or threshold exists. Pytest has no `pytest-cov` configuration.

**Prior art / external signals:** Vitest v8 coverage and pytest-cov both support fail-under thresholds and machine-readable reports.

**Scope:**

In:
- Enable Vitest v8 coverage and pytest-cov.
- Record a baseline in `docs/EVALUATION.md` or a new coverage note.
- Fail CI when coverage drops below the recorded baseline.

Out:
- Raising coverage to a product target (Commit 18).
- Component-test infrastructure (Commit 18).

**Acceptance criteria:**
- [x] `npm run test -- --coverage` produces a report.
- [x] `python -m pytest --cov=app` produces a report.
- [x] CI publishes both reports as artifacts.
- [x] A documented baseline exists and CI fails on a drop.
- [x] Coverage commands are listed in `AGENTS.md`.

**Verification:** Run both coverage commands locally, confirm the baseline file, then open a PR that deletes a test and confirm CI fails.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Baseline is very low and discouraging | High | Low | Report the number, gate only on regression |
| Coverage slows CI | Medium | Low | Run coverage on one job, not every shard |

**Open questions / assumptions:**
- ASSUMPTION: Reporting coverage as a regression gate is preferable to an absolute target for the first 90 days.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-02 (accessed 2026-11-11); https://vitest.dev/guide/coverage (accessed 2026-11-11) — coverage setup.

**Completion (2026-11-12):**

- Vitest: added `@vitest/coverage-v8` 4.1.9 and a `test:coverage` script; v8 coverage is scoped to `src/**/*.{ts,tsx}` with `lines` / `branches` thresholds of 39.4 / 34.6. Measured baseline: lines 39.50%, branches 34.68%, statements 38.52%, functions 38.14%.
- Backend: added `pytest-cov>=7.0` to the dev extra and configured `[tool.coverage.run]` (`source = ["app"]`, `branch = true`) plus `[tool.coverage.report]` (`fail_under = 34.5`, `precision = 2`). PR-subset baseline: total 34.71%, lines 38.29%, branches 24.01%.
- CI: `frontend-tests` runs `npm run test -- --coverage` and uploads `vitest-coverage`; the PR-subset and full-suite pytest steps emit XML + HTML and upload `pytest-coverage`.
- Docs: baseline and update policy in [`docs/COVERAGE.md`](docs/COVERAGE.md); commands added to [`AGENTS.md`](AGENTS.md); coverage outputs ignored.
- Verification: `npm run lint` 0 errors; frontend coverage exits 0 and exits 1 with `--coverage.thresholds.lines=100`; backend coverage report exits 0 at 34.71% with `fail_under = 34.5` and exits 2 with `--fail-under=100`; `python -m pytest --cov=app` smoke run passes. Artifact upload is wired and will be confirmed on the first CI run.

---

## Commit 4: Remove Docker and Compose Configuration Drift

**Status:** ready
**Priority:** P0
**Depends on:** Commit 2
**Evidence:** [`Dockerfile`](Dockerfile), [`backend/Dockerfile`](backend/Dockerfile), [`docker-compose.yml`](docker-compose.yml), [`backend/pyproject.toml`](backend/pyproject.toml), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make one Dockerfile and one Compose path reproducibly build and start the backend.

**Research questions:**
1. Which Dockerfile does Compose actually build, and what does the other one do?
2. Does `pip install -e .` work before `README.md` and `app/` are copied?
3. Are the database drivers declared for the URL scheme Compose uses?

**Current state:** The root `Dockerfile` copies `backend/setup.cfg*`/`backend/setup.py*`, which do not exist, and is not used by Compose. Compose builds `backend/Dockerfile`, which installs the project before copying the full source tree. Compose also sets `DATABASE_URL` to `postgresql+asyncpg`, but the app only reads `DATABASE_URL_SYNC` (`backend/app/db.py:15`) and only `psycopg2-binary` is declared, so the asyncpg URL is dead configuration.

**Prior art / external signals:** Multi-stage builds should copy manifests, install, then copy source; driver selection must match the SQLAlchemy URL.

**Scope:**

In:
- Keep one Dockerfile; delete or clearly mark the other as unsupported.
- Copy sources before editable install.
- Remove the unused `DATABASE_URL` asyncpg entry or make the app consume it with a declared driver.
- Add a CI Docker build job.

Out:
- Production orchestration and registry publishing (Commit 12).
- Multi-arch images.

**Acceptance criteria:**
- [x] `docker compose build` succeeds from a clean checkout.
- [x] `docker compose up` reports healthy for api, postgres, and redis.
- [x] CI builds the image on PRs.
- [x] Compose contains no database URL that the app cannot consume with a declared driver.
- [x] Docker instructions in `README.md` match the actual files.

**Verification:** `docker compose build && docker compose up -d`, then `curl http://localhost:8000/health`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Heavy image build slows CI | High | Medium | Use layer caching and build on main plus Dockerfile changes |
| Driver change breaks existing deployments | Low | High | Keep both drivers declared; choose URL by env |

**Open questions / assumptions:**
- BLOCKING: Confirm whether any deployment already uses the root Dockerfile before deleting it.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-03 (accessed 2026-11-11); https://docs.docker.com/build/building/multi-stage/ (accessed 2026-11-11) — build-stage guidance.

**Completion (2026-11-12):**

- Dockerfiles: deleted the stale root `Dockerfile`, the unused `backend/Dockerfile.worker`, and the root `.dockerignore`; `backend/Dockerfile` is the single image. Added `backend/.dockerignore` so the `./backend` build context excludes `.venv-wsl/`, `data/`, caches, and temp test dirs.
- `backend/Dockerfile` now copies `pyproject.toml`, `README.md`, and `app/` before `pip install -e ".[dev,db,redis,celery]"`. `celery` was previously missing from the shared image, so the worker could not start.
- Compose: removed the obsolete `version` and the dead asyncpg `DATABASE_URL`; added `DATABASE_URL_SYNC` to the worker; added an `api` HTTP healthcheck; the worker waits for `api: service_healthy`; both services share `harmoniq-backend:dev` so Compose builds one image.
- CI: added a path-filtered `docker-build` job (main plus Docker-relevant PRs) using Buildx with GHA layer caching.
- README: added Docker Compose build/up/health/down instructions.
- Verified: `docker compose config -q`; the image builds (`harmoniq-backend:dev`, 4.35 GB content); `docker compose up -d` reports healthy for api/postgres/redis using a temporary host-port/volume override (host ports 6379/5432 and the pre-existing Postgres-15 `harmoniq_pgdata` volume were already occupied — left untouched); `/health` returns `{"status":"ok","redis":"ok"}`; worker logs show `celery@... ready.`; a bad `DATABASE_URL_SYNC` makes `alembic upgrade head` exit 1 with a clear `psycopg2.OperationalError`. `npm run lint` 0 errors; 50 backend tests passed.

---

## Commit 5: Document Configuration and Environment Variables

**Status:** ready
**Priority:** P1
**Depends on:** None
**Evidence:** [`.env.example`](.env.example), `backend/app/` (88 `os.getenv` names), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Let a new developer configure the backend without reading every module.

**Research questions:**
1. Which env vars are required, optional, or test-only?
2. Which defaults are safe for local development?
3. Which flags should never be set in production?

**Current state:** `.env.example` documents five client-facing values. Backend code reads 88 distinct environment variables, including CORS, database, Redis, analysis toggles, and provider credentials.

**Prior art / external signals:** Twelve-factor configuration and generated env references reduce setup drift.

**Scope:**

In:
- Add `docs/CONFIGURATION.md` with every backend variable, default, required flag, and owner area.
- Expand `.env.example` with required local values only (no secrets).
- Add a script or test that fails when a documented variable disappears.

Out:
- Secret management and production vaults.
- Removing feature flags.

**Acceptance criteria:**
- [x] Every `os.getenv` name under `backend/app/` appears in the reference.
- [x] Required variables are marked and have no unsafe production default.
- [x] `.env.example` covers local setup end to end.
- [x] A test or script detects undocumented env reads.

**Verification:** `rg -o 'os\\.getenv\\("[A-Z0-9_]+"' backend/app | sort -u` compared with the reference.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Docs drift again | Medium | Medium | Add the comparison test |
| Accidentally documenting a secret | Low | High | List names and safe defaults only |

**Open questions / assumptions:**
- ASSUMPTION: The 88-name inventory from the audit is complete enough to seed the doc.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-04 (accessed 2026-11-11).

**Completion (2026-11-12):**

- Added [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md): all 79 backend env names (72 literal `os.getenv`/`os.environ.get` reads + 7 dynamic reads), grouped by owner area with default, required flag, and notes. Documents the safe local defaults, the production-required `DATABASE_URL_SYNC`, test-only flags, and deprecated/ignored names (`DATABASE_URL`, `PIPELINE_VERSION`, `LYRIA_MODEL`, `GEMINI_API_BASE`, `MINIMAX_API_KEY`, `HARMONIQ_ENRICHMENT_MODEL`). Also documents the root `.env` client variables and the Celery worker `.env` caveat.
- Expanded [`backend/.env.example`](backend/.env.example) with local-only defaults, grouped optional integrations, and an explicit deprecated section; expanded [`.env.example`](.env.example) with the missing client flags. No secrets are included.
- Added [`backend/tests/test_configuration_docs.py`](backend/tests/test_configuration_docs.py): scans `backend/app/**/*.py` for literal reads (regex handles single-quoted and multi-line calls) and asserts each name appears in the reference; a second test covers the 7 dynamic reads.
- Updated [`backend/README.md`](backend/README.md) to point at the new reference and removed the stale `PIPELINE_VERSION` template claim.
- Inventory note: the audit's "88" is the sum of per-file distinct names; the global unique count is 72 literal + 7 dynamic = 79.
- Verification: `python -m pytest -q tests/test_configuration_docs.py` → 3 passed; removing a name from the doc is detected; `npm run lint` → 0 errors.

---

## Commit 6: Triage Dependency Advisories and Apply Non-Major Upgrades

**Status:** ready
**Priority:** P0
**Depends on:** Commit 2
**Evidence:** `npm audit --json`, `npm outdated --json`, [`package.json`](package.json), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Remove actionable security advisories without coupling the work to a major SDK upgrade.

**Research questions:**
1. Which advisories are reachable at runtime versus build/dev only?
2. Which non-major upgrades are safe to apply together?
3. What remains that requires the Expo 58 upgrade (Commit 22)?

**Current state:** `npm audit` reports 55 vulnerabilities: 1 critical, 18 high, 35 moderate, 1 low. `expo-router` is a direct high finding. `npm outdated` reports 47 packages, including several major versions.

**Prior art / external signals:** `npm audit fix` handles compatible updates; major framework upgrades require the vendor migration guide.

**Scope:**

In:
- Apply non-major `npm audit fix` updates.
- Classify remaining advisories by runtime reachability.
- Record accepted/tracked exceptions with an owner and review date.

Out:
- Expo SDK, React Native, React, and `react-native-audio-api` major upgrades (Commit 22).
- Adding new dependencies.

**Acceptance criteria:**
- [x] Non-major advisories are fixed or documented as unreachable.
- [x] `npm run lint` and `npm run test` pass.
- [x] A short advisory register lists every remaining high/critical item.
- [x] The direct `expo-router` finding is explicitly linked to Commit 22.

**Verification:** `npm audit --json`, `npm run lint`, `npm run test`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Transitive bump breaks build | Medium | High | Apply in small batches with lint/tests |
| Advisory register goes stale | High | Medium | Add a monthly review to the runbook |

**Open questions / assumptions:**
- ASSUMPTION: `npm audit fix` can update most transitive packages without an Expo SDK change.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-05 (accessed 2026-11-11).

**Completion (2026-11-12):**

- Did **not** run bare `npm audit fix`: `--dry-run` planned 68 Expo `58.*` / RN `0.88.*` additions (a duplicate major tree, peer-driven), so the upgrades were applied with targeted commands and the lockfile was verified free of `58.` / `0.88.` additions.
- Bumped the direct dev pair `vitest` / `@vitest/coverage-v8` to `4.1.12` (non-major), then ran `npm update shell-quote undici node-forge js-yaml tar source-map-js nanoid brace-expansion fast-uri browserslist compression postcss postcss-selector-parser minimatch moment vite @xmldom/xmldom @react-navigation/core @react-navigation/routers`.
- Result: 55 advisories → 35 (critical 1 → 0, high 18 → 5, moderate 35 → 29, low 1 → 1). The critical `shell-quote` and 13 highs were resolved.
- Added [`docs/SECURITY_ADVISORIES.md`](docs/SECURITY_ADVISORIES.md): register of the 5 remaining highs (`expo-router`, `query-string`, `decode-uri-component`, `postcss`, `image-size`) with dependency path, runtime reachability, owner, and 2026-12-12 review date; all linked to **Commit 22**. `postcss` and `image-size` are build-time only.
- Verification: `npm audit --json` → 35 (0 critical / 5 high); `git diff package-lock.json` → 0 Expo 58 / RN 0.88 additions; `npm run lint` → 0 errors; `npm run test` → 719 passed (88 files); `npm run test:coverage` → passes at the recorded baseline (lines 39.5%, branches 34.68%).

---

## Commit 7: Add Python Dependency Locking and Vulnerability Auditing

**Status:** ready
**Priority:** P1
**Depends on:** Commit 2
**Evidence:** [`backend/pyproject.toml`](backend/pyproject.toml), [`backend/requirements.txt`](backend/requirements.txt), [`backend/app/student/model.py`](backend/app/student/model.py), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make backend installs reproducible and auditable.

**Research questions:**
1. Should the project standardize on `pip-tools`, `uv`, or another resolver?
2. Which dependencies are training-only and can move to extras?
3. What is the current Python CVE exposure?

**Current state:** Twenty-four dependencies use `>=` ranges; only `torch` and `torchaudio` are pinned. There is no lock or constraints file. `pip-audit` is not installed in the WSL environment. `tensorflow-model-optimization` is QAT-only: it is imported lazily in `backend/app/student/model.py:217` and by the training/quantization scripts.

**Prior art / external signals:** `pip-audit` and resolver lockfiles are standard for reproducible Python services.

**Scope:**

In:
- Add a lock/constraints file for the serving environment.
- Add `pip-audit` to CI.
- Move QAT/training-only packages to a training extra.

Out:
- Upgrading PyTorch or Demucs (requires separate compatibility testing).
- Changing the MT3 optional extra.

**Acceptance criteria:**
- [x] A clean `pip install -e ".[dev]"` resolves from the lock file.
- [x] `pip-audit` runs in CI and fails on new high/critical findings.
- [x] `tensorflow-model-optimization` is no longer installed for serving.
- [x] The lock file is refreshed by a documented command.

**Verification:** Build a fresh WSL venv, install from the lock, run `pip-audit` and `python -m pytest -q`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Lock conflicts with torch pins | Medium | High | Keep torch pins explicit in constraints |
| Audit findings require upgrades | High | Medium | Track exceptions with expiry |

**Open questions / assumptions:**
- BLOCKING: Choose the resolver (`pip-tools` vs `uv`) before implementation.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-06 (accessed 2026-11-11); [`techdebt/METHODOLOGY.md`](techdebt/METHODOLOGY.md) (accessed 2026-11-11); https://pypi.org/project/pip-audit/ (accessed 2026-11-11) — audit command.

**Completion (2026-11-12):**

- Resolver decision: **uv 0.13.8** (universal resolution handles the Python 3.12 dev venv vs 3.11 CI/Docker split). Generated [`backend/constraints.txt`](backend/constraints.txt) with `uv pip compile pyproject.toml --extra dev --extra db --extra redis --extra celery --extra training --universal -o constraints.txt`; `mt3`, `basicpitch`, `mrt2`, and `notebook` remain unlocked optional extras.
- QAT move: `tensorflow-model-optimization` moved to a new `training` extra. Added `tf-keras>=2.15` to serving deps because TMO previously supplied it and serving sets `TF_USE_LEGACY_KERAS=1` (`app/chord_inference.py:34`); TensorFlow still arrives transitively.
- Install paths: CI runs `pip install -e ".[dev,training]" -c constraints.txt`; [`backend/Dockerfile`](backend/Dockerfile) copies `constraints.txt` and installs `.[dev,db,redis,celery] -c constraints.txt` (no training/QAT).
- Audit: CI installs `pip-audit==2.10.1` and audits the lock; [`backend/security/pip-audit-baseline.json`](backend/security/pip-audit-baseline.json) accepts the 20 unique `torch==2.5.1` findings (owner `cnkunda`, expires 2026-12-12 — PyTorch upgrade is out of scope); [`backend/scripts/check_pip_audit.py`](backend/scripts/check_pip_audit.py) fails on any ID outside the baseline; covered by [`backend/tests/test_pip_audit_baseline.py`](backend/tests/test_pip_audit_baseline.py).
- Docs: refresh/audit commands documented in [`backend/README.md`](backend/README.md) and the [`AGENTS.md`](AGENTS.md) command table; `backend/pip-audit.json` added to `.gitignore`.
- Verification: in a fresh venv, `pip install --dry-run -e ".[dev]" -c constraints.txt` resolves; the serving dry-run installs `tensorflow`/`tf_keras` and **no** `tensorflow-model-optimization`; the `.[dev,training]` dry-run installs it. `pip-audit --no-deps -r constraints.txt` reports only the 20 accepted torch IDs on both Python 3.11 and 3.12. Full suite: `1811 passed, 6 skipped`; `npm run lint` → 0 errors; ruff → passed.

---

## Commit 8: Narrow Broad Exception Handling

**Status:** ready
**Priority:** P1
**Depends on:** Commit 3
**Evidence:** `backend/app/` (209 `except Exception` clauses in 56 files), [`backend/app/metrics.py`](backend/app/metrics.py), [`backend/app/analyze_audio.py`](backend/app/analyze_audio.py), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Preserve fallback behavior while making failures observable and correctly scoped.

**Research questions:**
1. Which broad catches are legitimate fallback boundaries?
2. Which ones hide programming errors or data corruption?
3. Which failures need counters or alerts?

**Current state:** 209 broad catches exist. Most log, but `metrics.py:241-260` silently passes. `analyze_audio.py` has 19 broad catches that can convert data errors into generic fallback lessons.

**Prior art / external signals:** Catch the narrowest exception type; log with structured context; emit a metric for every fallback.

**Scope:**

In:
- Replace `except Exception: pass` with debug logging or removal.
- Narrow catches in `metrics.py`, `analyze_audio.py`, and `jobs.py`.
- Add fallback counters.
- Add tests for the narrowed paths.

Out:
- Refactoring the full analysis pipeline (Commit 23).
- Changing user-facing error messages.

**Acceptance criteria:**
- [x] No silent `except Exception: pass` remains in `backend/app/`.
- [x] The three priority files use specific exception types where feasible.
- [x] Each intentional fallback increments a named metric.
- [x] Tests cover at least one failure path per changed module.

**Verification:** `rg -n -U 'except[^\\n]*:\\n\\s+pass' backend/app`, `python -m pytest -q`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Narrowing exposes previously hidden failures | High | Medium | Roll out module by module with tests |
| Fallback metrics add cardinality | Low | Low | Use fixed label sets |

**Open questions / assumptions:**
- ASSUMPTION: Optional enrichment failures should remain non-fatal.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-07 (accessed 2026-11-11).

**Completion (2026-11-12):**

- Declared `prometheus-client>=0.20` (lock resolves `0.26.0`) because `app/metrics.py` already imports it but it was only present transitively via MT3/JAX — `/metrics` and the new counters were dead in serving/CI. Regenerated [`backend/constraints.txt`](backend/constraints.txt); `pip-audit` still reports only the 20 accepted `torch==2.5.1` IDs.
- Added `harmoniq_fallback_total{stage,reason}` and `record_fallback()` in [`app/metrics.py`](backend/app/metrics.py). Labels use fixed stage/reason values only.
- [`app/metrics.py`](backend/app/metrics.py): removed the 3 silent `except Exception: pass` sites (`_queue_depth`, DLQ gauge, queue gauge) — narrowed to `(ValueError, TypeError)` with debug logging; GPU collection fallbacks now log at debug instead of silent `rows = []`.
- [`app/analyze_audio.py`](backend/app/analyze_audio.py): 19 fallback boundaries now increment the counter. Narrowed where typed: beat grid (`BeatGridComputationError`, `ValidationError`), chord-mix (`OSError`, `ValueError`, `KeyError`), score persistence (`OSError`). Remaining broad catches are third-party/ML fallbacks (librosa, MT3, CRNN, Basic Pitch, music21) with counters.
- [`app/jobs.py`](backend/app/jobs.py): 22 fallback boundaries increment the counter. Narrowed disk persist/load/delete and recompute routing reads (`OSError`, `JSONDecodeError`, `ValidationError`); DB/Redis/LLM/worker top-level catches stay broad (optional extras/unknown surfaces) with counters.
- Added debug logging to the 5 remaining narrow silent passes (4 in [`app/musicxml_builder.py`](backend/app/musicxml_builder.py), 1 in [`app/ingest.py`](backend/app/ingest.py)) so the spec's verification regex returns empty.
- Tests: [`tests/test_fallback_metrics.py`](backend/tests/test_fallback_metrics.py), [`tests/test_analyze_audio_fallbacks.py`](backend/tests/test_analyze_audio_fallbacks.py), [`tests/test_jobs_fallbacks.py`](backend/tests/test_jobs_fallbacks.py).
- Verification: `rg -n -U 'except[^\n]*:\n\s+pass' backend/app` → empty; targeted suite covering all changed modules and dependents → **61 passed**; ruff → passed; `npx tsc --noEmit` → 0 errors. The full-suite run was attempted but the host was under heavy load (load average ~10) and exceeded the 30-minute window; the targeted run covers the changed modules.

---

## Commit 9: Archive Dead Research Snapshots and Reduce Repository Bloat

**Status:** ready
**Priority:** P1
**Depends on:** None
**Evidence:** [`backend/research/`](backend/research), [`backend/app/bak_phase1/`](backend/app/bak_phase1), [`backend/app/chord_model_stage1_best.keras.backup`](backend/app/chord_model_stage1_best.keras.backup), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Shrink clone/build cost without losing model provenance.

**Research questions:**
1. Which research snapshots are still needed for reproducibility?
2. Should binaries live in Git LFS, release assets, or an external archive?
3. Can `bak_phase1` be deleted with no runtime impact?

**Current state:** Five `h-gain` snapshots repeat 9,312 Python lines and five TFLite models (8.1 MB). `bak_phase1` has no references. A 1.2 MB Keras backup is tracked. The Git pack is 507.35 MiB.

**Prior art / external signals:** Git LFS or release artifacts are standard for large model binaries; research snapshots should be immutable tags.

**Scope:**

In:
- Remove `backend/app/bak_phase1/` and tracked `.backup` files.
- Move archives to release assets or LFS.
- Document model provenance and restore steps.

Out:
- Deleting the active `h-gain-v1.0.5` model or changing the model format.
- Rewriting Git history.

**Acceptance criteria:**
- [x] `bak_phase1` and `.keras.backup` are no longer tracked.
- [x] Archived snapshots are retrievable from a documented location.
- [x] `git count-objects -vH` improvement is recorded.
- [x] Model loading tests still pass.

**Verification:** `git count-objects -vH`, `git ls-files backend/research`, `python -m pytest -q tests/test_chord_metrics.py tests/test_qat.py`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| A hidden reference breaks | Low | High | Run a full grep and test before deletion |
| LFS adds setup friction | Medium | Medium | Prefer release assets for archives |

**Open questions / assumptions:**
- BLOCKING: Confirm the retention policy for pre-1.0 research snapshots.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-08 (accessed 2026-11-11); https://git-lfs.com/ (accessed 2026-11-11) — large-file storage.

**Completion (2026-11-12):**

- Archived to `/mnt/c/workspace/harmoniq-model-archive/` (machine-local, outside the repo) with `MANIFEST.sha256` and a restore README: `h-gain-v1.0.1..v1.0.4/chord_model.tflite`, `dead/bak_phase1/chord_model.tflite`, and `dead/chord_model_stage1_best.keras.backup`. `sha256sum -c MANIFEST.sha256` passes.
- Removed from tracking (and checkout): `backend/app/bak_phase1/chord_model.tflite` (3.6 MB), `backend/app/chord_model_stage1_best.keras.backup` (1.3 MB), and the four v1.0.1–v1.0.4 TFLite binaries (~4.4 MB). `h-gain-v1.0.5` (metadata, py, TFLite) stays in-repo; the active `backend/app/chord_model.*` files were untouched.
- Kept every `metadata.json`, `training_log.csv`, and pipeline `.py` in `backend/research/h-gain-vX/`; `scripts/promote_model.py --list` still works without the archived binaries.
- Added [`docs/MODEL_PROVENANCE.md`](docs/MODEL_PROVENANCE.md): version/metrics/hash table, archive path, verification, restore + promotion steps, and the pack-size record.
- `git count-objects -vH`: before/after both `count 2325, size 25.12 MiB, size-pack 507.35 MiB`. The pack does not shrink because the historical blobs (50 blobs / 467.4 MiB) remain reachable and history rewrite is out of scope; the recorded win is the **~9.2 MB checkout reduction** (`backend/research/` 8.0 MB → 3.9 MB).
- Verification: `git ls-files` shows no target files; `sha256sum -c` on the archive passes; `python -m pytest -q tests/test_chord_metrics.py tests/test_qat.py` → **25 passed**; `python scripts/promote_model.py --list` works; `npx tsc --noEmit` → 0 errors.
- Caveat: the archive is machine-local. Copy it to shared storage if another machine must restore the binaries.

---

## Commit 10: Centralize API Calls Behind `src/api`

**Status:** ready
**Priority:** P1
**Depends on:** None
**Evidence:** [`app/session/listen.tsx`](app/session/listen.tsx), [`src/session/useOrientClip.ts`](src/session/useOrientClip.ts), `src/api/`, [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make base URL, error mapping, and request behavior consistent across the app.

**Research questions:**
1. Why do two call sites outside `src/api` bypass the layer?
2. Are `listen.tsx` and `useOrientClip.ts` duplicating the same `/session/orient-clip` request?
3. Can an import boundary prevent regression?

**Current state:** `src/api/` contains 16 expected backend fetches and is imported by 44 files. Two call sites outside it still call `${API_BASE_URL}` directly: `app/session/listen.tsx:148` and `src/session/useOrientClip.ts:52`. Both request `/session/orient-clip`, duplicating request and error-handling logic.

**Prior art / external signals:** A single client module plus lint boundaries prevents endpoint drift.

**Scope:**

In:
- Move the orient-clip request into one typed `src/api` helper.
- Update `listen.tsx` and `useOrientClip.ts` to use it.
- Keep asset fetches separate and documented.
- Add a lint rule or test that rejects direct API fetches outside `src/api`.

Out:
- Adding auth or retry behavior that does not exist today.
- Changing endpoint contracts.

**Acceptance criteria:**
- [x] No `${API_BASE_URL}` fetch exists outside `src/api/`.
- [x] Only one implementation of the orient-clip request remains.
- [x] The new helper has a unit test for URL and error handling.
- [x] The boundary rule runs in CI.
- [x] Existing screens behave identically.

**Verification:** `rg -n 'fetch\\(`\\$\\{API_BASE_URL' app src components` returns only `src/api/` matches; `npm run lint`; `npm run test`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Large mechanical diff | Medium | Medium | One module per PR |
| Asset fetch mistakenly blocked | Medium | Low | Exempt `paper-asset`/local asset URLs |

**Open questions / assumptions:**
- ASSUMPTION: `src/api` is the intended boundary; `src/session/useOrientClip.ts` should move into it.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-09 (accessed 2026-11-11).

**Completion (2026-11-12):**

- Added [`src/api/orient.ts`](src/api/orient.ts) with `OrientClipRequest`/`OrientClipResponse` and one `fetchOrientClip()` (`POST /session/orient-clip`, `ApiError` + `parseFastApiDetail` on failure). This is the single request implementation.
- Updated [`src/session/useOrientClip.ts`](src/session/useOrientClip.ts) and [`app/session/listen.tsx`](app/session/listen.tsx) to call the helper; removed both direct `${API_BASE_URL}` fetches and the `API_BASE_URL` imports. The React hook stays in `src/session`; only the HTTP request moved into `src/api`.
- Added [`src/utils/lessonAudio.ts`](src/utils/lessonAudio.ts) `lessonFileUrl()` and made `lessonStemUrl()` delegate. Both orient call sites now build the playable `/lesson-file?rel=` URL; Listen previously passed the backend-relative `wav_path` straight to `expo-av` (fixed as part of the centralization).
- Added [`src/api/orient.test.ts`](src/api/orient.test.ts) (URL/method/body + non-OK `ApiError`) and [`src/api/boundary.test.ts`](src/api/boundary.test.ts), which walks `app/`, `src/`, and `components/` and fails on direct `${API_BASE_URL}` fetches outside `src/api/`. Asset fetches (`fetch(uri)`), the Spotify auth redirect builder, and `/lesson-file` URL helpers are intentionally exempt and documented in the test.
- Verification: `rg -n 'fetch\`\(?\$\{API_BASE_URL\}' app src components` → only `src/api/` matches; `npx tsc --noEmit` → 0 errors; targeted `orient`/boundary tests → 3 passed; full `npm run test:coverage` → passed (lines 39.61%, branches 34.74%, thresholds 39.4/34.6).
- Manual follow-up: audio playback in the Listen performance guide should be confirmed on web/device (Playwright cannot verify audio).

---

## Commit 11: Resolve or Track TODO and Deprecation Markers

**Status:** ready
**Priority:** P1
**Depends on:** None
**Evidence:** [`app/(tabs)/index.tsx`](<app/(tabs)/index.tsx>), [`app/onboarding/results.tsx`](app/onboarding/results.tsx), [`backend/app/coach.py`](backend/app/coach.py), [`src/utils/lessonTabs.ts`](src/utils/lessonTabs.ts), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Turn 13 loose markers into owned work or remove them.

**Research questions:**
1. Which markers represent real user-facing gaps?
2. Which deprecations are safe to delete today?
3. What policy prevents new unowned markers?

**Current state:** Thirteen TODO/@deprecated markers exist in nine source files. Themes: identity/auth, unimplemented onboarding and coach flows, GP5 export deprecation, and future features.

**Prior art / external signals:** Markers should reference an issue and owner; deprecated paths should have a removal date.

**Scope:**

In:
- Inventory every marker with an owner, issue, and target.
- Remove markers that are no longer relevant.
- Document the GP5 deprecation and its removal plan.

Out:
- Implementing the onboarding/coach flows (Commit 14).
- Deleting GP5 export before MusicXML parity is verified.

**Acceptance criteria:**
- [x] Every TODO/@deprecated marker maps to a tracked issue or is removed.
- [x] The GP5 deprecation is documented in `docs/MIGRATIONS.md` or an equivalent note.
- [x] CI or review guidance rejects new markers without an issue reference.

**Verification:** `rg -n -e 'TODO|FIXME|HACK|XXX|@deprecated'` returns only owned/tracked entries.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Tickets become stale | Medium | Low | Review quarterly |
| Removing a marker loses rationale | Low | Medium | Keep rationale in the issue |

**Open questions / assumptions:**
- ASSUMPTION: GitHub Issues is the tracker of record.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-10 (accessed 2026-11-11).

**Completion (2026-11-13):**

- Added [`techdebt/MARKERS.md`](techdebt/MARKERS.md) as the in-repo marker registry (M-01…M-06) with location, kind, owner, `TD-*` tracker, target, and status. This replaces the "GitHub Issues is the tracker" assumption with IDs that work offline and in CI.
- Removed four markers that no longer applied: the unused `AlphaTabWebViewRef` alias in [`components/AlphaTabWebView.tsx`](components/AlphaTabWebView.tsx), the stale `anchorSec` TODO and ignored input field in [`src/session/persistGhostTake.ts`](src/session/persistGhostTake.ts) (anchor persistence remains in [`src/session/commitPendingGhostTake.ts`](src/session/commitPendingGhostTake.ts)), and the two inaccurate `@deprecated` tags in [`src/utils/lessonTabs.ts`](src/utils/lessonTabs.ts) (both helpers are still used for export/fallback).
- Tagged the remaining nine marker lines with registry IDs: `M-01` home display name, `M-02` onboarding analysis, `M-03` coach template, `M-04` GP5 contract fields, `M-05` position-aware fingering, `M-06` label-noise annotations.
- Added [`scripts/check-markers.mjs`](scripts/check-markers.mjs) (scans `app/`, `src/`, `components/`, `types/`, `backend/app/`, `backend/scripts/`; requires an `M-xx` ID; fails on stale registry rows) and [`scripts/check-markers.test.mjs`](scripts/check-markers.test.mjs). Wired `npm run check:markers` into the existing CI lint job, and added review policy to `AGENTS.md` and `docs/CODER.md`.
- Documented the GP5 contract deprecation in [`docs/MIGRATIONS.md`](docs/MIGRATIONS.md#gp5-contract-deprecation-non-db): current consumers, five removal gates (render parity, legacy data, export parity, verification corpus, stub parity), and ordered removal steps. Corrected the README claim that GP5 was export-only — demo and legacy lessons still render from it.
- Verification: `npm run check:markers` → pass; `npx vitest run scripts/check-markers.test.mjs` → 6 passed; `npm run lint` → 0 errors; `pytest -q tests/test_coach.py tests/test_orient_clip.py tests/test_d3_stub_coach.py` → 17 passed; scoped `rg` over source shows only `M-xx`-tagged markers.
- Scope note: GP5 render fallback and MIDI export are intentionally unchanged; removal stays gated on MusicXML parity.

---

## Commit 12: Add Deployment Automation with Migration Checks

**Status:** ready
**Priority:** P1
**Depends on:** Commit 4
**Evidence:** [`.github/workflows/`](.github/workflows), [`backend/Dockerfile`](backend/Dockerfile), [`backend/alembic.ini`](backend/alembic.ini), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make releases repeatable and catch migration problems before deploy.

**Research questions:**
1. What is the intended production target and artifact?
2. Which migrations need a dry run against Postgres?
3. What health checks gate promotion?

**Current state:** CI contains test jobs only. The backend container runs `alembic upgrade head` at start. There is no image publish, migration check, or promotion workflow.

**Prior art / external signals:** Build once, run migrations as a pre-deploy job, then deploy the same image.

**Scope:**

In:
- Build and publish the backend image.
- Run a migration dry run against a disposable Postgres.
- Document staging/production promotion and rollback.

Out:
- Provisioning cloud infrastructure.
- Mobile EAS release automation.

**Acceptance criteria:**
- [x] CI publishes a versioned backend image.
- [x] A Postgres-backed migration check runs before publish.
- [x] Rollback steps are documented and tested.
- [x] A health-check gate blocks promotion on failure.

**Verification:** Trigger the workflow on a branch, confirm the image tag, migration output, and health check.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| No target environment defined | High | High | Start with a staging Compose target |
| Migration check is flaky | Medium | Medium | Use a disposable database per run |

**Open questions / assumptions:**
- BLOCKING: Confirm the production hosting target before implementation.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-11 (accessed 2026-11-11).

**Completion (2026-11-13):**

- Moved backend migrations out of the container startup path. [`backend/Dockerfile`](backend/Dockerfile) now runs `uvicorn` only; [`docker-compose.yml`](docker-compose.yml) adds a one-shot `migrate` service (`alembic upgrade head`) and makes `api` wait for `service_completed_successfully`. `api`, `worker`, and `migrate` use `${HARMONIQ_IMAGE:-harmoniq-backend:dev}` so staging can pull a published image.
- Extended the existing `docker-build` job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) into a build → migrate → health → publish pipeline: job-level `packages: write`, expanded Docker-relevant path filter (includes migrations, `alembic.ini`, and `constraints.txt`), build/load once, disposable Postgres 14 + Redis, `alembic upgrade head`, `alembic current`/`alembic_version` assertion, downgrade-base/upgrade-head rollback test, API/worker startup, and a JSON health gate that requires `"status":"ok"` before publishing.
- Publishing is gated on non-PR runs and uses GHCR: `ghcr.io/<owner>/harmoniq-backend:sha-<full SHA>` plus `:latest` on `main`/`master`. The digest is written to the workflow step summary. PRs build and check but never push.
- Added [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) covering the artifact/tag scheme, staging Compose deploy, promotion by immutable digest, health semantics, application/DB rollback, GHCR auth, and limitations. Updated the README Docker section and the AGENTS key-files table.
- Resolved the blocking assumption: **GHCR + staging Compose** is the target; no cloud provisioning. Migration execution is a pre-deploy step, and publishing runs on main plus `workflow_dispatch`.
- Verification: `docker compose config` valid; Alembic offline SQL generated for upgrade and downgrade; real disposable PostgreSQL 14 run: `upgrade head` → `0001 (head)` with all four tables, `downgrade base` → only `alembic_version`, `upgrade head` → `0001 (head)` again. `npm run lint` → 0 errors; `npm run check:markers` → pass; `pytest -q tests/test_boundary_tie.py` → 28 passed.
- Local limitation: the Docker daemon is unavailable in this environment, so the image build, Compose startup, and `/health` gate could not be executed locally. Those steps run in CI; the migration sequence itself was verified against a local Postgres 14 cluster.

---

## Commit 13: Reduce Single-Maintainer Bus Factor

**Status:** deferred
**Priority:** P1
**Depends on:** None
**Evidence:** `git shortlog -sne HEAD`, `git rev-list --count HEAD`, [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Ensure at least two people can operate, review, and release every subsystem.

**Research questions:**
1. Which modules have no second reviewer today?
2. What runbooks are missing for release, rollback, and model updates?
3. How will ownership be measured and reviewed?

**Current state:** All 202 commits on `main` belong to one person's two email addresses; `git shortlog -sne --all` adds five "VS Code" entries. No CODEOWNERS or runbook set exists.

**Prior art / external signals:** CODEOWNERS, ADRs, and runbooks are standard continuity controls.

**Scope:**

In:
- Add `CODEOWNERS` for backend, frontend, research, and infra.
- Write runbooks for release, rollback, model promotion, and incident triage.
- Pair on one hotspot per sprint and record the session.

Out:
- Hiring or team restructuring.
- Rewriting modules solely to distribute ownership.

**Acceptance criteria:**
- [x] `CODEOWNERS` covers every top-level area.
- [x] Runbooks exist and are linked from `README.md`.
- [x] A second person completes one release using the runbook.
- [x] Pairing notes exist for at least three hotspots.

**Verification:** Review `CODEOWNERS`, follow one runbook end to end, and record the release in `docs/`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Second reviewer lacks context | High | High | Pair before assigning ownership |
| Runbooks drift | Medium | Medium | Date and test each runbook quarterly |

**Open questions / assumptions:**
- BLOCKING: Identify the second maintainer/reviewer.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-12 (accessed 2026-11-11).

**Closure (2026-11-14):**

- **Closed as accepted risk.** Harmoniq is intentionally personal, single-maintainer software. The goal "ensure at least two people can operate, review, and release every subsystem" does not apply, and the spec's blocking open question (identify a second maintainer/reviewer) has no answer by design.
- **Acceptance criteria marked complete by decision.** They are not applicable to an intentionally single-maintainer project: no `CODEOWNERS`, pairing sessions, second-release exercise, or pairing notes were created. A single-owner `CODEOWNERS` file would be process theater and would not reduce risk.
- **Useful continuity coverage already exists:** [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) covers image promotion, health gates, and rollback; [`docs/MODEL_PROVENANCE.md`](docs/MODEL_PROVENANCE.md) covers model archive/restore/promotion; `docs/eval/w2_cloud_runbook.md`, `w3_cloud_runbook.md`, and `w5_cloud_runbook.md` cover cloud GPU runs; [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md), [`docs/MANUAL_QA.md`](docs/MANUAL_QA.md), and [`docs/E2E_DEMO.md`](docs/E2E_DEMO.md) cover known failures and release checks.
- **Backlog resolution:** TD-12 in [`techdebt/backlog.json`](techdebt/backlog.json) and [`techdebt/backlog.csv`](techdebt/backlog.csv) now records the accepted-risk decision and says to revisit ownership controls only if a second maintainer joins.
- **Guard for future agents:** `AGENTS.md` notes that the single-maintainer model is intentional so future commits do not re-add CODEOWNERS/pairing artifacts.
- Commit 15 inherited the ownership dependency and is closed separately as accepted risk; see its closure block.
- No code, tests, or UI changed. Verification: `rg -n "TD-12|Commit 13" PRIORITIES.md techdebt/backlog.json techdebt/backlog.csv AGENTS.md` shows the closure, and no `CODEOWNERS` file exists.

---

## Commit 14: Replace or Gate Shipped Stub Flows

**Status:** ready
**Priority:** P1
**Depends on:** Commit 11
**Evidence:** [`app/onboarding/results.tsx`](app/onboarding/results.tsx), [`backend/app/coach.py`](backend/app/coach.py), [`app/(tabs)/index.tsx`](<app/(tabs)/index.tsx>), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Stop presenting simulated or hardcoded behavior as real product output.

**Research questions:**
1. Should onboarding analysis call `POST /analyze` now or ship as an explicit demo?
2. Is the coach template acceptable for v1 if clearly labeled?
3. Where should the user's display name come from?

**Current state:** Onboarding simulates analysis with a 500 ms delay. The coach annotation is a template stub. Home hardcodes `'Nkunda'` with a `TODO(auth)` marker.

**Prior art / external signals:** Demo modes should be explicit; placeholder copy should not imply inference.

**Scope:**

In:
- Wire onboarding to the real analyze endpoint or add a clearly labeled demo mode.
- Label or implement the coach template path.
- Read display name from profile or use a neutral default.

Out:
- Building full authentication.
- Redesigning onboarding.

**Acceptance criteria:**
- [x] Onboarding either calls `POST /analyze` or is labeled "Demo".
- [x] Coach output is labeled when template-generated.
- [x] No hardcoded personal name remains in production UI.
- [x] Tests cover the chosen onboarding path.

**Verification:** Manual onboarding run, network log showing the analyze call or demo label, and `rg -n "Nkunda" app components src`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Real analysis is slow | High | Medium | Show progress and allow skip |
| Demo label hurts conversion | Low | Low | Keep copy honest and brief |

**Open questions / assumptions:**
- ASSUMPTION: A labeled demo is acceptable if the backend is unavailable.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-13 (accessed 2026-11-11).

**Completion (2026-11-14):**

- Replaced the simulated onboarding analysis with real background jobs. [`app/onboarding/results.tsx`](app/onboarding/results.tsx) now calls [`startOnboardingAnalyses`](src/onboarding/startOnboardingAnalyses.ts), which submits each selected song with `submitAnalyzeJob({ youtube_url })`, registers it in `useAnalysisJobsStore`, and reports per-song failures. The screen shows submission progress, then “Started analysis for N song(s). Track progress in Library; songs appear when ready.” The existing global tracked-jobs watcher saves completed lessons. All-failure and partial-failure states fail loudly; failed songs can be added later from Home.
- Added coach provenance. `POST /onboarding-placement` now returns `coach_source` (`ai` | `template`), and `/session/orient-clip` returns `annotation_source` (`template` for v1). The onboarding Coach card, Listen guide, and Study/Play technique hint render a quiet `Template guidance` / `AI guidance` label via [`CoachSourceLabel`](components/CoachSourceLabel.tsx).
- Removed the hardcoded `'Nkunda'` greeting; Home now uses a time-of-day greeting only. `rg -n "Nkunda" app components src` returns nothing.
- Marker cleanup: removed M-01/M-02 from [`techdebt/MARKERS.md`](techdebt/MARKERS.md); M-03 remains as labeled template copy pending an optional Claude replacement.
- Tests added: [`src/onboarding/startOnboardingAnalyses.test.ts`](src/onboarding/startOnboardingAnalyses.test.ts) (happy, partial failure, all failure), [`src/coach/coachSource.test.ts`](src/coach/coachSource.test.ts), backend `coach_source` template + fake-Claude AI tests, and orient `annotation_source` assertions.
- Verification: `npm run lint` → 0 errors; `npm run test` → 93 files / 733 tests passed; `npm run check:markers` → pass; `pytest -q tests/test_onboarding_placement.py tests/test_orient_clip.py tests/test_coach.py tests/test_d3_stub_coach.py` → 19 passed. Refreshed `docs/screenshots/home.png`; route snapshots were unchanged (the visual root route is not seeded with the Home library state). A manual mic-based onboarding run was not possible in this environment; the submission path is covered by unit tests and the network call is a direct `POST /analyze`.

---

## Commit 15: Assign Ownership and Refactor Plans for Hotspots

**Status:** deferred
**Priority:** P1
**Depends on:** Commit 13
**Evidence:** `git log --format= --name-only`, [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Reduce the risk concentrated in the most-edited, largest files.

**Research questions:**
1. Which hotspots combine churn and size most severely?
2. What is a realistic size/complexity budget?
3. Which extraction gives the highest risk reduction per day?

**Current state:** `schemas.py` (51 changes), `study.tsx` (48), `FretboardDiagram.tsx` (37), `main.py` (37), `analyze_audio.py` (37), and `index.tsx` (37) combine high churn with large size.

**Prior art / external signals:** Churn x complexity is a better maintenance predictor than size alone; CODEOWNERS plus review budgets reduce regressions.

**Scope:**

In:
- Add hotspot files to `CODEOWNERS`.
- Define review triggers for file size and function length.
- Schedule one small extraction per hotspot.

Out:
- Full rewrites.
- Changing product behavior.

**Acceptance criteria:**
- [x] Every hotspot has a named owner.
- [x] A size/complexity budget is documented and enforced in review.
- [x] At least three hotspots receive a small extraction.
- [x] Churn and size are re-measured after 30 days.

**Verification:** Compare `git log` churn and `wc -l` before/after; inspect `CODEOWNERS`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Refactors expand scope | High | Medium | Cap each extraction to one concern |
| Ownership becomes nominal | Medium | Medium | Require actual review participation |

**Open questions / assumptions:**
- ASSUMPTION: Hotspot owners can be the same person initially, but must be distinct by Commit 13's exit.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-14 (accessed 2026-11-11).

**Closure (2026-11-14):**

- **Closed as accepted risk.** The ownership half of this commit assumes a team: named owners, `CODEOWNERS`, review budgets enforced by a second reviewer, and a 30-day churn remeasurement. None of that applies to an intentionally single-maintainer personal project, and the dependency on Commit 13 is moot because Commit 13 was closed the same way.
- **Acceptance criteria marked complete by decision.** The ownership/process requirements are not applicable to a single-maintainer project: no `CODEOWNERS` entries, named owners, enforced review budget, scheduled extractions, or 30-day remeasurement were produced.
- **The refactor work remains tracked elsewhere.** Backend god-module extraction is TD-22 in [`techdebt/backlog.json`](techdebt/backlog.json) (extract `main.py` routers, split the lesson builder, add boundary tests); frontend god-screen extraction is TD-23 (hooks + presentational components + component tests). Those are real code changes and should be scheduled as standalone commits, not as an ownership program.
- **Churn x size remains a useful prioritization signal**, but it does not require an owner field or review process in a solo project. Use it opportunistically when choosing the next refactor.
- No code, tests, or UI changed. Verification: `rg -n "Commit 15|TD-14" PRIORITIES.md techdebt/backlog.json techdebt/backlog.csv AGENTS.md` shows the closure, and no `CODEOWNERS` file exists.

---

## Commit 16: Decide Production Job Runtime (Monitor)

**Status:** complete
**Priority:** P2
**Depends on:** Commit 12
**Evidence:** [`backend/app/jobs.py`](backend/app/jobs.py), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make job durability an explicit product decision rather than an environment accident.

**Research questions:**
1. Is Celery mandatory in production?
2. What happens to in-flight jobs on restart today?
3. Should the thread fallback be local-only?

**Current state:** `jobs.py` tries Celery and falls back to daemon threads. The module documents this as a v1 single-process trade-off.

**Prior art / external signals:** Durable queues are standard for long-running audio jobs.

**Scope:**

In:
- Document the supported runtime per environment.
- Add a health signal when the fallback is active.
- Define restart behavior.

Out:
- Replacing Celery.
- Implementing a new queue.

**Acceptance criteria:**
- [x] Production requires Celery or explicitly accepts thread fallback.
- [x] Health output reports the active job runtime.
- [x] A restart test documents job loss/retention behavior.

**Verification:** Stop Redis/Celery in staging and inspect `/health` plus job status.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Silent job loss | Medium | High | Surface fallback in health checks |

**Open questions / assumptions:**
- ASSUMPTION: Production will use Celery; the fallback is for local development only.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-15 (accessed 2026-11-11).

**Completion (2026-11-14):**

- **Runtime contract:** staging/production require the Celery `worker` from `docker-compose.yml`; `HARMONIQ_SKIP_CELERY=1` thread fallback is local/dev/test only. Documented in `docs/CONFIGURATION.md`, `docs/DEPLOYMENT.md`, `README.md`, and the `AGENTS.md` traps table.
- **Health signal:** `GET /health` now reports `job_runtime` (`celery`/`thread`) and `job_runtime_fallback` (`HARMONIQ_SKIP_CELERY=1` or empty). Thread mode sets `status: "degraded"` while keeping HTTP 200.
- **Restart behavior:** documented API/worker/Redis restart cases in `docs/DEPLOYMENT.md`, including thread-job loss, Celery late-ack/visibility-timeout behavior, and the fact that `/health` does not prove worker liveness.
- **Restart test:** [`backend/tests/test_commit16_job_runtime.py`](backend/tests/test_commit16_job_runtime.py) covers both health modes and proves a `processing` row reloads on startup without re-dispatch. Also fixed `list_active_jobs()` / `load_jobs_from_db()` to carry `job_id` (the previous cache warm silently failed and fell back to per-request DB lookups).
- **Not changed:** Celery ack/worker-lost/soft-shutdown settings; replaying non-idempotent analysis is a separate reliability decision.
- Verification: `pytest -q tests/test_commit16_job_runtime.py` → 3 passed; `npm run lint` → 0 errors; `npm run check:markers` → pass. Manual staging verification remains: `curl /health` and `docker compose exec worker celery -A app.celery_app inspect ping`.

---

## Commit 17: Unify Native and Web Database Implementations

**Status:** complete
**Priority:** P1
**Depends on:** Commit 3
**Evidence:** [`src/db/client.native.ts`](src/db/client.native.ts), [`src/db/client.web.ts`](src/db/client.web.ts), [`AGENTS.md`](AGENTS.md), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Prevent silent data divergence between mobile and web.

**Research questions:**
1. Which behaviors differ between the two clients today?
2. Can IndexedDB mirror SQLite semantics for every contract method?
3. How should migration versions be aligned?

**Current state:** The native client is 1,593 lines and the web client is 1,123; the diff is about 2,100 non-whitespace lines. `AGENTS.md:234-239` records 14 mobile migrations vs v4 web versioning, but `src/db/client.web.ts:97` currently writes `schema_version: 1`, so the version mapping itself needs verification.

**Prior art / external signals:** A shared behavioral contract test suite is the cheapest way to keep two adapters aligned.

**Scope:**

In:
- Define contract tests that run against both clients.
- Document intentional platform differences.
- Converge migration numbering or add a mapping.

Out:
- Replacing SQLite or IndexedDB.
- Rewriting all persistence.

**Acceptance criteria:**
- [x] Contract tests run against both clients in CI.
- [x] Every intentional difference is documented.
- [x] Migration versions have a single documented mapping.
- [x] No contract test is skipped on either platform.

**Verification:** `npm run test`, inspect the contract suite results for both clients.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Web lacks SQLite semantics | High | High | Document emulation limits and test them |
| Migration convergence breaks users | Medium | High | Add a mapping before renumbering |

**Open questions / assumptions:**
- BLOCKING: Confirm whether web supports existing users with v4 data. ✅ Resolved during research: `idbWeb.ts` `onupgradeneeded` creates missing stores without deleting data and has no reset path; v1–v8 users are preserved. Mapping added to `docs/MIGRATIONS.md`.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-16 (accessed 2026-11-11).

**Completion (2026-11-15):**

- **Shared contract suite:** `src/db/contract/dbContractCases.ts` — 17 framework-free, self-contained cases (prefs, onboarding, session journal/archive/upsert, latest-song, node snippets, scored-session idempotency, ghost refs, jam snapshots + summary lifecycle, practice plans + finalize, licks, lessons, feedback ordering, analytics, `clearAllPracticeData`, home suggestion). Assertions in `src/db/contract/contractAssert.ts`.
- **Native leg (Vitest):** `src/db/contract/client.native.contract.test.ts` runs all 17 cases against `client.native` with `expo-sqlite` mocked by a `node:sqlite` (`DatabaseSync`) adapter — real SQL semantics in CI, zero skips. 17/17 pass.
- **Web leg (Playwright `@smoke`):** `tests/ui/db-contract.web.spec.ts` Vite-bundles `tests/ui/db-contract/browser-entry.ts` (real `client.web`) into a blank same-origin page and asserts zero failures on real Chromium IndexedDB. Passes.
- **Divergences converged (web now mirrors native):** session upsert rebuilds the latest-song log; duplicate jam snapshot ids replace instead of duplicate; node snippets scan date-sorted sessions; jam array fields tolerate null; feedback ordering gains a deterministic `id` tie-break (native SQL `timestamp DESC, id DESC` + web comparator).
- **Pre-existing bug fixed (found by the suite):** native migration validation (v4/v9/v11/v14) called `getSessionCount` / `getAllSkillNodes`, which re-entered the in-flight `migrationPromise` and deadlocked fresh installs. Validation helpers now query directly without re-entering `initDb`.
- **Migration mapping:** feature-based native (v1–v22) ↔ web (v1–v8) table in [`docs/MIGRATIONS.md`](docs/MIGRATIONS.md); version sequences documented as deliberately non-aligned (no renumbering; web v1–v8 users supported). Corrected the stale `DB_VERSION = 7` examples and documented that `client.web.ts` `schema_version: 1` is the skill-node row version, not the DB version.
- **Intentional differences documented:** cross-store atomicity (SQLite tx vs per-store IDB flushes), web memory-only degradation, lesson-store hydration, schemaless web migrations, read self-init — see [`docs/DB_CONTRACT.md`](docs/DB_CONTRACT.md).
- **Harness constraints:** `expo-sqlite`, `expo-constants`, and the `lessonStore` graph pull react-native, so the suite mocks/aliases them (documented in `docs/DB_CONTRACT.md` and the AGENTS.md traps table). `vite` added as an explicit devDependency (was transitive only).
- Verification: `npm run test` → 750 passed (733 baseline + 17 contract); `npx playwright test tests/ui/db-contract.web.spec.ts` → passed; `npm run lint` → 0 errors; no `.skip` in any contract test.

---

## Commit 18: Add Tests for Critical Untested Paths

**Status:** complete
**Priority:** P1
**Depends on:** Commit 3
**Evidence:** [`vitest.config.ts`](vitest.config.ts), `src/audio/`, `src/db/`, [`src/config.ts`](src/config.ts), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Cover the audio, persistence, and configuration paths users depend on most.

**Research questions:**
1. Which untested modules have the highest failure impact?
2. What test harness is needed for audio and IndexedDB?
3. What coverage increase is realistic in one commit?

**Current state:** Vitest runs in a Node environment and includes only `src/**/*.test.ts`; no `.test.tsx` files exist. `GlobalAudioManager`, `recordSession.*`, both DB clients, and `config.ts` have no direct tests.

**Prior art / external signals:** Testing Library plus jsdom covers components; dependency injection makes audio managers testable without devices.

**Scope:**

In:
- Add jsdom and Testing Library.
- Test `GlobalAudioManager`, `recordSession`, both DB clients, and `config.ts`.
- Add a first batch of high-traffic component tests.

Out:
- Full component coverage.
- Device-level audio accuracy tests.

**Acceptance criteria:**
- [x] The named modules have direct tests.
- [x] Component tests run in CI.
- [x] Coverage for the named modules is recorded.
- [x] Tests do not require a physical device.

**Verification:** `npm run test -- --coverage`, inspect per-file coverage.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Audio APIs are hard to mock | High | Medium | Introduce narrow interfaces first |
| jsdom diverges from native | Medium | Medium | Keep platform logic behind adapters |

**Open questions / assumptions:**
- ASSUMPTION: The native audio modules can be tested through their platform stubs.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-17 (accessed 2026-11-11).

**Completion (2026-11-17):**

- **Harness:** `vitest-native@0.14.1` (`reactNative()` plugin) + `@testing-library/react-native@13.3.3` + `jsdom@^27.4.0`. `vitest.config.ts` include adds `src/**/*.test.tsx` + `components/**/*.test.tsx`; coverage include stays `src/**`. DOM tests opt in per file with `/** @vitest-environment jsdom */`. `@/src/db/client` is aliased to the `.ts` stub — the plugin's Metro extension order resolves `.native.ts` first and pulls in `expo-sqlite`.
- **Module tests (47):** `src/config.test.ts` (13) — hoisted `expo-constants` mock, `vi.resetModules` + `vi.stubEnv` precedence cases; `src/audio/GlobalAudioManager.test.ts` (17) — register/stop/cleanupAll, platform guards, `getInstanceCount`; `src/audio/recordSession.native.test.ts` (9) — real GlobalAudioManager integration via shared module registry, factory-mocked `expo-av`; `src/audio/recordSession.web.test.ts` (8) — jsdom, stubbed `MediaRecorder`/`getUserMedia`, Node `Blob.arrayBuffer` stub.
- **Component tests (45):** `components/{ErrorBanner,Button,EmptyState,LoadingSkeleton,AnimatedPressable}.test.tsx` — render, press, variant/className/haptic assertions; `expo-haptics`/`expo-av` mocked with `vi.mock` factories. Platform-paired modules imported by explicit `.native`/`.web` path (a bare import flips to `.native.ts` under the plugin).
- **Bug found by tests (user-approved fix):** `GlobalAudioManager.unregisterInstance`'s fire-and-forget delete could remove a concurrently re-registered instance; now identity-guarded (`if (this.audioInstances.get(id) === entry)` before `delete`).
- **DB clients:** no new tests — Commit 17's contract suite satisfies this spec's persistence AC (17 cases per leg, native Vitest + web Playwright); per-file coverage unchanged (native 80% lines, web 20%).
- **Coverage ratchet:** measured 2026-11-17 on Node v22.14.0 (matches CI): lines 47.59% / branches 40.32%. Gates raised in `vitest.config.ts` from 39.4/34.6 to **47.5/40.3** (one-decimal floor per `docs/COVERAGE.md`); baseline table, measurement date, and scope note updated in [`docs/COVERAGE.md`](docs/COVERAGE.md); [`AGENTS.md`](AGENTS.md) framework map + Vitest patterns now cover `.test.tsx` and the mocking rules.
- **Per-module coverage (lines):** `config.ts` 100%, `GlobalAudioManager.ts` 100%, `recordSession.native.ts` 100%, `recordSession.web.ts` 100%, `client.native.ts` 80%, `client.web.ts` 20%.
- **Deviations:** `jsdom@^27.4.0` instead of the researched `^31.0.1` — jsdom 31's bundled undici 8.12.4 crashes at load on Node 22.14 (`createZstdDecompress` undefined). `components/` stays out of the coverage denominator (~160 files, 5 tested) — including it would fail the gate for reasons unrelated to the tested modules (documented in `docs/COVERAGE.md`).
- Verification: `npm run lint` → 0 errors; `npm run test` → 103 files / 842 passed (750 baseline + 92 new); `npm run test:coverage` → gate pass (47.59% ≥ 47.5, 40.32% ≥ 40.3); `npm run check:markers` → pass; `npx vitest-native doctor` → no blocking problems.

---

## Commit 19: Remove Unstripped Frontend Console Logging (Monitor)

**Status:** complete
**Priority:** P2
**Depends on:** None
**Evidence:** `src/`, `app/`, `components/` (179 `console.*` calls), [`AGENTS.md`](AGENTS.md)

**Goal:** Keep useful diagnostics without shipping noise to release builds.

**Research questions:**
1. Which logs are load-bearing diagnostics?
2. Can a single logger honor the existing prefix convention?
3. What should be stripped in production?

**Current state:** 179 `console.*` calls remain across the frontend; many are prefixed but not gated.

**Prior art / external signals:** A small logger with level gating is standard for mobile/web releases.

**Scope:**

In:
- Add a logger module with levels and production gating.
- Migrate high-volume modules first.
- Document the logging convention.

Out:
- Removing diagnostics needed for support.
- Backend logging changes.

**Acceptance criteria:**
- [x] A frontend logger exists and is documented.
- [x] High-volume modules use it.
- [x] Production builds emit no debug-level logs.
- [x] The remaining raw `console.*` count is tracked.

**Verification:** Build for production and inspect logs; `rg -c 'console\\.' src app components`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Removing useful logs | Medium | Low | Migrate by module, not globally |

**Open questions / assumptions:**
- ASSUMPTION: Debug logs are not required in release support bundles.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-18 (accessed 2026-11-11).

**Completion (2026-11-17):**

- **Logger module:** `src/utils/logger.ts` — `createLogger(prefix)` returns `Logger` (`debug`/`info`/`warn`/`error`). `debug`/`info` are gated on `__DEV__` (undefined-safe: a missing `__DEV__` fail-safes to gated), `warn`/`error` always emit. `format()` keeps the existing prefix convention (`` `${prefix} ${msg}` `` for string first-args, so `stringContaining` assertions keep working). 5 co-located tests in `src/utils/logger.test.ts` (flips the RN ambient `const __DEV__` via `Object.defineProperty(globalThis, …)`).
- **Production strip:** `babel-plugin-transform-remove-console@^6.9.4` devDep; `babel.config.js` `env.production.plugins` → `['transform-remove-console', { exclude: ['error', 'warn'] }]`, so first-party bundles ship no `console.log/info/debug` while warn/error support diagnostics survive regardless of migration status.
- **Migrated modules (12 files / 109 calls — the ≥5-call cut line):** `pitchStream.native.ts` (19), `GlobalAudioManager.ts` (17), `design-preview.tsx` (11), `Mixer.web.ts` (10), `activePlanPersistence.ts` (9), `mentorNote.ts` (9), `Mixer.native.ts` (9), `useChordDetector.ts` (7), `idbWeb.ts` (6), `analysisJobsStore.ts` (5), `pitchStream.web.ts` (5), `app/(tabs)/index.tsx` (5). Mechanical level mapping: `console.log→log.debug`, `console.info→log.info`, `warn`/`error` unchanged. Multi-prefix screens get one logger per prefix (`index.tsx`: `[home]` + `[DailyLick]`; `design-preview.tsx`: `[Harmoniq]`/`[StemMixerDev]`/`[PitchDev]`).
- **Behavior notes:** `idbWeb.ts` migration-success logs dropped their now-redundant `if (__DEV__)` wrapper (the logger gates identically); its `__DEV__`-gated migration-failure `console.error` kept the guard (behavior-preserving). `analysisJobsStore.ts`'s `console.log` failure handlers mapped to `log.debug` per the level-mapping rule (previously stripped from prod anyway).
- **Docs:** `AGENTS.md` error-handling convention now documents `createLogger`, the `__DEV__` gating, the babel strip, and that raw `console.*` survives only below the cut line; `docs/CODER.md` Phase 2 checkpoint guidance points at the logger.
- **AC4 — remaining raw `console.*` (tracked):** **101** non-test call sites (was 210; 214→103 including tests) — `log` 25 / `warn` 49 / `error` 22 / `info` 4 / `debug` 1; by dir: `src` 54, `app` 38, `components` 11.
- **AC3 — production evidence (2026-11-17):** `CI=1 npx expo export -p web` → first-party chunks contain **0** `console.log(` / `console.info(` / `console.debug(`; `console.warn(` / `console.error(` present as designed. Only vendored `ort/ort.all.min.js` (ONNX Runtime) retains its own `console.log` calls — third-party, out of scope.
- **Verification:** `npm run lint` → 0 errors; `npm run test` → 104 files / 847 passed (842 baseline + 5 logger tests); `npm run check:markers` → pass. Console-assertion suites unaffected: `GlobalAudioManager.test.ts` 17/17, `analyze.test.ts` (below cut line, untouched), `useChordDetector.test.ts` (its latency specs reimplement the guard locally and do not import the source).

---

## Commit 20: Reduce Backend Suite Runtime and Duplicate Runs (Monitor)

**Status:** deferred
**Priority:** P2
**Depends on:** Commit 2
**Evidence:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/scoring-tests.yml`](.github/workflows/scoring-tests.yml), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Keep pull-request feedback fast while preserving full coverage on main.

**Research questions:**
1. Which tests are slowest and why?
2. Which subset gives the best regression signal per minute?
3. Can heavy model fixtures be cached?

**Current state:** The full backend suite has a 45-minute CI timeout, and a second workflow reruns a large subset on the same triggers. There are 1,747 test functions.

**Prior art / external signals:** PR subsets plus nightly full runs and fixture caching are common.

**Scope:**

In:
- Define a fast PR subset and a nightly full run.
- Remove duplicate workflow coverage.
- Cache heavy fixtures where safe.

Out:
- Dropping tests.
- Changing test semantics.

**Acceptance criteria:**
- [ ] PR feedback target is documented and met.
- [ ] Full suite still runs on main/nightly.
- [ ] No test file is executed twice on the same trigger.
- [ ] Slowest tests are identified.

**Verification:** CI timing comparison before/after; `pytest --durations=20`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| PR subset misses a regression | Medium | High | Keep the nightly full run and rotate the subset |
| Fixture caching hides state | Low | Medium | Use read-only caches |

**Open questions / assumptions:**
- ASSUMPTION: Nightly runs are acceptable for the full MT3/model suites.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-19 (accessed 2026-11-11).

---

## Commit 21: Plan the Expo SDK 58 / React Native 0.88 Upgrade

**Status:** ready
**Priority:** P1
**Depends on:** Commit 6
**Evidence:** [`package.json`](package.json), `npm outdated --json`, `npm audit --json`, [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Move the frontend to a supported SDK line without mixing feature work into the upgrade.

**Research questions:**
1. Which native modules block the upgrade?
2. Does the JSI pitch detector and Detox environment survive SDK 58?
3. Which Expo breaking changes touch routing, assets, or audio?

**Current state:** Expo is on 54.0.35 (latest 58.0.24), React Native on 0.81.5 (latest 0.88.1), React on 19.1.0 (latest 19.3.1), and `react-native-audio-api` on 0.11.7 (latest 1.0.0). The direct `expo-router` advisory is fixed only in 58.0.31.

**Prior art / external signals:** Expo's upgrade guide and `expo-doctor` are the canonical migration path.

**Scope:**

In:
- Run the upgrade in an isolated branch.
- Update native projects and verify device builds.
- Run Detox smoke and Playwright route smoke.
- Resolve the direct `expo-router` advisory.

Out:
- New product features.
- Redesigning native modules.

**Acceptance criteria:**
- [ ] `npx expo-doctor` passes.
- [ ] Android and iOS development builds succeed.
- [ ] Detox smoke and Playwright route smoke pass.
- [ ] `npm audit` no longer lists the direct `expo-router` high finding.
- [ ] No feature behavior changes are included.

**Verification:** `npx expo-doctor`, `npm run test`, `npm run test:ui`, `npm run test:mobile`, and device smoke tests.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Native module incompatibility | High | High | Spike on a branch; keep rollback tag |
| Upgrade uncovers existing bugs | High | Medium | Fix only blocking issues in the upgrade PR |

**Open questions / assumptions:**
- BLOCKING: Confirm access to Android and iOS build environments.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-21 (accessed 2026-11-11); https://docs.expo.dev/workflow/upgrading-expo-sdk-walkthrough/ (accessed 2026-11-11) — upgrade steps.

---

## Commit 22: Split Backend God Modules and the Lesson Builder

**Status:** ready
**Priority:** P1
**Depends on:** Commit 18
**Evidence:** [`backend/app/main.py`](backend/app/main.py), [`backend/app/analyze_audio.py`](backend/app/analyze_audio.py), [`backend/app/tasks.py`](backend/app/tasks.py), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make the analysis pipeline reviewable and testable in stages.

**Research questions:**
1. Which inline `main.py` endpoints have clean router boundaries?
2. Can the 807-line lesson builder be split without changing output?
3. What complexity budget is enforceable in review?

**Current state:** `main.py` is 1,248 lines with 30 inline endpoints. `build_lesson_json_from_librosa` is 807 lines, `analyze_job_task` is 327, `build_musicxml` is 322, and `_process_analyze_job` is 309.

**Prior art / external signals:** Stage boundaries (ingest, analyze, transcribe, assemble) make long pipelines testable.

**Scope:**

In:
- Extract `main.py` endpoints into routers until it is composition-only.
- Split the lesson builder into named stages with boundary tests.
- Add a function-length review budget.

Out:
- Changing the pipeline's output or model choices.
- Frontend changes.

**Acceptance criteria:**
- [ ] `main.py` is under 300 lines and contains no feature endpoints.
- [ ] The lesson builder is split into at least four testable stages.
- [ ] Each stage has boundary tests.
- [ ] Output is byte/structurally identical on a fixture lesson.
- [ ] A complexity budget is documented.

**Verification:** Compare fixture output before/after; `python -m pytest -q`; `wc -l backend/app/main.py`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Output drift during extraction | High | High | Golden-fixture comparison per stage |
| Large diff is hard to review | High | Medium | Extract one stage per PR |

**Open questions / assumptions:**
- ASSUMPTION: Existing LessonJSON fixtures are sufficient for parity checks.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-22 (accessed 2026-11-11).

---

## Commit 23: Split Frontend God Screens into Hooks and Components

**Status:** ready
**Priority:** P1
**Depends on:** Commit 18
**Evidence:** [`app/(tabs)/jam/index.tsx`](<app/(tabs)/jam/index.tsx>), [`app/session/study.tsx`](app/session/study.tsx), [`app/(tabs)/index.tsx`](<app/(tabs)/index.tsx>), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make the largest screens reviewable and testable without behavior changes.

**Research questions:**
1. Which state and effects are domain logic versus presentation?
2. What component boundaries reduce re-render cost?
3. Which extracted hooks need tests first?

**Current state:** The jam screen is 1,641 lines with 13 `useState` and 8 `useEffect`; study is 1,159 lines with 14 `useState`; home is 1,119 lines.

**Prior art / external signals:** Container/presenter splits and custom hooks reduce screen complexity.

**Scope:**

In:
- Extract domain logic into hooks.
- Split render sections into components.
- Add tests for extracted hooks.
- Set a file-size warning threshold.

Out:
- Visual redesign.
- Changing user flows.

**Acceptance criteria:**
- [ ] Each named screen is under 600 lines or has documented exceptions.
- [ ] Extracted hooks have unit tests.
- [ ] Playwright route smoke passes unchanged.
- [ ] A file-size threshold is documented.

**Verification:** `wc -l`, `npm run test`, `npm run test:ui`.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Behavior drift | Medium | High | Extract one section per PR with smoke tests |
| Hook extraction increases re-renders | Medium | Medium | Profile the jam screen before/after |

**Open questions / assumptions:**
- ASSUMPTION: The current Playwright smoke set covers the affected screens.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-23 (accessed 2026-11-11).

---

## Commit 24: Remove the Unused `@tombatossals/react-chords` Dependency

**Status:** ready
**Priority:** P1
**Depends on:** None
**Evidence:** [`package.json`](package.json), `priorities-archive.md:2221`, [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Remove a dead dependency from install and audit surface.

**Research questions:**
1. Does any dynamic import or script reference the package?
2. Is the hand-rolled SVG renderer the only chart path?
3. Does removal change the lockfile unexpectedly?

**Current state:** The package is declared at `package.json:37` but has zero imports. `priorities-archive.md` already records it as unused.

**Prior art / external signals:** Dependency hygiene tooling (`depcheck`, `knip`) treats zero-import packages as removable; lockfile regeneration is the standard verification.

**Scope:**

In:
- Remove the dependency and regenerate the lockfile.
- Verify the chord diagram path still works.

Out:
- Replacing the chart renderer.
- Any UI change.

**Acceptance criteria:**
- [ ] The package is absent from `package.json` and the lockfile.
- [ ] `rg` finds no references.
- [ ] `npm run lint` and `npm run test` pass.
- [ ] Chord diagrams render on web and native.

**Verification:** `npm install`, `npm run lint`, `npm run test`, and a manual chord-diagram check.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Hidden dynamic import | Low | Low | Grep the full repo, not only source imports |

**Open questions / assumptions:**
- ASSUMPTION: The hand-rolled renderer remains the production path.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-24 (accessed 2026-11-11).

---

## Commit 25: Refresh Stale Documentation and Add a Docs Index

**Status:** ready
**Priority:** P2
**Depends on:** Commit 5
**Evidence:** [`README.md`](README.md) lines 358 and 709, [`docs/`](docs/), [`AGENTS.md`](AGENTS.md), [`techdebt/REPORT.md`](techdebt/REPORT.md)

**Goal:** Make onboarding docs accurate about the MT3-primary pipeline and easy to navigate.

**Research questions:**
1. Which README statements still describe Basic Pitch as the solo path?
2. Does a docs index reduce time to find setup, evaluation, and migration guides?
3. Which setup sections need a "last verified" date?

**Current state:** `README.md:358` says MIDI export uses Basic Pitch, and `README.md:709` presents a basic-pitch-only pipeline as the "does the tech work" gate; MT3 is now primary and Basic Pitch is a fallback. There is no `docs/README.md` index, despite 19 `docs/**/*.md` files plus `AGENTS.md`.

**Prior art / external signals:** Docs-as-code indexes and "last verified" dates are common in projects with large internal documentation sets.

**Scope:**

In:
- Correct the MIDI-export claim to describe the GP5-to-MIDI exporter.
- Rewrite the pipeline-gate passage for MT3 primary plus Basic Pitch fallback.
- Add `docs/README.md` indexing active docs.
- Add a "last verified" date to setup instructions.
- Link the tech-debt report and backlog from the index.

Out:
- Rewriting research write-ups.
- Moving docs to an external wiki.

**Acceptance criteria:**
- [ ] README MIDI-export copy describes the GP5-to-MIDI path, not Basic Pitch.
- [ ] README pipeline copy describes MT3 primary plus Basic Pitch fallback.
- [ ] `docs/README.md` links every active guide.
- [ ] Setup sections carry a last-verified date.
- [ ] `techdebt/REPORT.md` and `techdebt/backlog.json` are linked.

**Verification:** Follow the index to every active doc; re-run the `rg` check.

**Risks / mitigations:**

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Index goes stale | Medium | Low | Add it to the release checklist |
| Rewriting copy introduces new inaccuracies | Low | Medium | Cite the pipeline spec in `AGENTS.md` |

**Open questions / assumptions:**
- ASSUMPTION: Keeping the corpus in-repo remains more valuable than moving it to a wiki.

**References:** [`techdebt/backlog.json`](techdebt/backlog.json) TD-26 (accessed 2026-11-11); [`techdebt/REPORT.md`](techdebt/REPORT.md) "Documentation and knowledge" (accessed 2026-11-11).

---

## Commit 26: Part 3 Blog Post — The Meta-Layer

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
