# Scoring Reliability Rollout Plan

Phased rollout plan for scoring v2 contract and confidence-aware progress updates.

## Phase 1 - Jam First (feature flag: `scoring_reliability_v2_jam`)

- Enable jam reliability envelope + tags in backend response.
- Persist reliability tags/confidence in jam snapshots (native + web).
- QA checkpoints:
  - `backend/tests/test_jam_score.py` passes.
  - Manual Jam run shows "Last jam diagnostics" card after save.
  - No regressions in existing map persistence.

## Phase 2 - Session Score Contract (feature flag: `scoring_reliability_v2_score`)

- Ship diagnostics and reliability envelope in `/score` response.
- Thread reliability into review-to-progress update path.
- QA checkpoints:
  - `backend/tests/test_score.py` passes.
  - Review flow still saves snapshots and updates targeted nodes.
  - Low-signal sessions produce reliability flags.

## Phase 3 - Onboarding Robustness (feature flag: `onboarding_confidence_weighting_v1`)

- Replace plain mean with confidence-aware robust aggregation.
- Send placement confidence + reliability flags to coach endpoint.
- QA checkpoints:
  - `src/onboarding/aggregatePlacementScores.test.ts` passes.
  - Onboarding results renders confidence note when applicable.

## Phase 4 - Progress Explainability (feature flag: `progress_multisignal_updates_v1`)

- Use confidence-aware policy in SM-2 session updates.
- Display policy description in Progress screen.
- QA checkpoints:
  - `src/spaced/sm2.test.ts` passes.
  - No negative jumps on low-confidence high-score outliers.

## Calibration + Drift Guardrails

- Add weekly metric review for:
  - reliability confidence distribution,
  - low-signal rate (`signal_low`, `voiced_sparse`),
  - jam sparse-map rate (`map_sparse`).
- Trigger threshold review when any KPI drifts by >20% week-over-week.
