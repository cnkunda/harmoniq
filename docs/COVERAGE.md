# Test Coverage Baseline

Last updated: 2026-11-17 (Commit 18). Coverage is a **regression gate only**:
the numbers below are the floor, not a product target. Raising them further is
tracked separately from the gate.

## Commands

```bash
# Frontend (Vitest v8)
npm run test:coverage
# equivalently: npm run test -- --coverage

# Backend (pytest-cov)
cd backend
python -m pytest --cov=app --cov-branch --cov-report=term-missing:skip-covered
```

CI runs the backend gate on the curated PR subset from
`.github/workflows/ci.yml`, using the same flags plus
`--cov-report=xml:coverage.xml` and `--cov-report=html:htmlcov`. Full-suite
coverage on pushes is always greater than or equal to the subset baseline, so
the same `fail_under` applies to both.

## Baseline

Measured 2026-11-17 on Node v22.14.0 (matches the CI runner) with Vitest
4.1.12 and the vitest-native component harness; backend measured with
coverage.py 7.17.2. Gates use the one-decimal floor of the measurement.

| Layer | Metric | Baseline | Gate |
| --- | --- | ---: | ---: |
| Frontend (`src/**`) | Lines | 47.59% | 47.50% |
| Frontend (`src/**`) | Branches | 40.32% | 40.30% |
| Frontend (`src/**`) | Statements | 45.98% | not gated |
| Frontend (`src/**`) | Functions | 45.77% | not gated |
| Backend (`app/**`, lines + branches) | Total | 34.71% | 34.50% |
| Backend (`app/**`) | Lines | 38.29% | included in total |
| Backend (`app/**`) | Branches | 24.01% | included in total |

The backend gate uses coverage.py's combined line+branch total with
`precision = 2`; the frontend gate compares raw percentages. Threshold values
live in `vitest.config.ts` and `backend/pyproject.toml` — those are the source
of truth, this table is documentation.

## Scope and exclusions

- Frontend coverage is scoped to `src/**/*.{ts,tsx}`. Component tests
  (`components/**/*.test.tsx`, Commit 18) run in the suite but `components/`
  and `app/` stay out of the coverage denominator: they hold ~160 files of
  which only a handful are tested, so including them would fail the gate for
  reasons unrelated to the tested modules.
- Backend coverage is scoped to the `app` package. Subprocesses spawned by
  tests are not measured.
- Uncovered files are included in the denominator (`coverage.include` /
  `--cov=app`), so adding an untested module lowers coverage and fails the
  gate.

## Updating the baseline

After a deliberate coverage improvement:

1. Run both commands above and capture the totals.
2. Lower the buffer to the new one-decimal floor
   (`floor(measured * 10) / 10`) in `vitest.config.ts` and
   `backend/pyproject.toml`.
3. Update the table and the measurement date here.

Do not use `coverage.thresholds.autoUpdate` — thresholds are updated manually
so a coverage change is always reviewed.
