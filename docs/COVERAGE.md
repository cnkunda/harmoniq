# Test Coverage Baseline

Last updated: 2026-11-12. Coverage is a **regression gate only** for the first
90 days: the numbers below are the floor, not a product target. Raising them is
tracked separately (Commit 18).

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

Measured 2026-11-12 on Node v24.15.0 / Python 3.12.1 with Vitest 4.1.9 and
coverage.py 7.17.2. CI runs Node 22 / Python 3.11; the threshold leaves a small
buffer for that difference.

| Layer | Metric | Baseline | Gate |
| --- | --- | ---: | ---: |
| Frontend (`src/**`) | Lines | 39.50% | 39.40% |
| Frontend (`src/**`) | Branches | 34.68% | 34.60% |
| Frontend (`src/**`) | Statements | 38.52% | not gated |
| Frontend (`src/**`) | Functions | 38.14% | not gated |
| Backend (`app/**`, lines + branches) | Total | 34.71% | 34.50% |
| Backend (`app/**`) | Lines | 38.29% | included in total |
| Backend (`app/**`) | Branches | 24.01% | included in total |

The backend gate uses coverage.py's combined line+branch total with
`precision = 2`; the frontend gate compares raw percentages. Threshold values
live in `vitest.config.ts` and `backend/pyproject.toml` — those are the source
of truth, this table is documentation.

## Scope and exclusions

- Frontend coverage is scoped to `src/**/*.{ts,tsx}`. `components/`, `app/`,
  and `scripts/` are excluded because no component/screen test infrastructure
  exists yet (Commit 18).
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
