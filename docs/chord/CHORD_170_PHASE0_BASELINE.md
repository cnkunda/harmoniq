# Chord 170 — Phase 0 Baseline Report

Phase 0 of the Harmoniq 170-class chord model program. Deliverables: a
reproducible evaluation harness, this report (fair v1.0.3 baseline, v1.0.5
gate regression, deployed-head mismatch), and fixed training-log/metadata
provenance. **No production model changes.**

## Method

- Harness: `backend/scripts/eval_chord_baseline.py` (unit-tested in
  `backend/tests/test_chord_eval_baseline.py`).
- Data: GuitarSet `.npz` windows (`backend/data/guitarset/processed/cqt/`),
  player-level split by construction — **test = player 05 held out**
  (60 tracks / 324 windows), val = player 04 (60 tracks). No window leakage.
- Comparison space: **MIREX-25** (`app.chord_vocab.MIREX_VOCAB`) — the
  deployed model's native space — via the shared `mirex_label()` mapping,
  so every baseline is scored against the same truth.
- Metrics: exact accuracy, root accuracy (maj/min merged), macro-F1,
  top-3 accuracy, N rates — reported separately for chord-head vs gated
  vs TFLite outputs.
- Runtime: local CPU (WSL, `.venv-wsl`), `CUDA_VISIBLE_DEVICES=-1`.

Reproduce:

```bash
cd backend && source .venv-wsl/bin/activate
python scripts/eval_chord_baseline.py --split test --models deployed
# artifact: docs/audit/amt/chord170_phase0_baseline.json
```

## Finding 1 — deployed head is not what the registry says (provenance)

`backend/app/model_registry.json` declares `active_version: "1.0.3"` — the
277-class/40-bin CRNN (Conv1D 64/128 + MHA + BiLSTM + Dense 256, val 83.8%).

**The shipped binary is not that model.** Inspecting
`backend/app/chord_model.keras`:

| Property | v1.0.3 (registry claim) | shipped `app/chord_model.keras` |
| --- | --- | --- |
| Chord head | 277-class | **25-class MIREX** |
| Heads | single output | multi-task: `chord_probs` 25, `root_probs` 13, `presence` 1 |
| Frontend | Conv1D 64/128 + MHA | Conv1D 32/64 (Commit 148 Phase A architecture) |
| Input | 128 × 40 | 128 × 144 |

`app/chord_inference.py` additionally loads it through the 25-class
MIREX vocabulary with 144-bin CQT features. The deployed production path is
the **25-class multi-task Commit 148 model**, and `model_registry.json` is
wrong. Registry updates are deferred to Phase 5 (post-validation) per the
program constraints; this document is the authoritative interim record.

## Finding 2 — the deployed 25-class model is near-useless on honest splits

Evaluated on the held-out GuitarSet player 05 test split (324 windows;
MIREX truth N rate 3.7%):

| Metric | chord-head-only | presence-gated |
| --- | ---: | ---: |
| Exact accuracy | **0.0432** | 0.0432 |
| Root accuracy | 0.0556 | 0.0556 |
| Macro-F1 | 0.0155 | 0.0155 |
| Top-3 accuracy | 0.1698 | — |
| Predicted-N rate | 0.5926 | 0.5926 |

Val split (player 04) reproduces the pattern: exact 0.0401 / root 0.0525.
This confirms the earlier observation in
[`docs/EVALUATION.md`](../EVALUATION.md) ("local Keras checkpoint scored
~4% on precomputed test windows") with a reproducible harness and adds the
root cause: the model predicts N on 59% of frames against a 3.7% true N
rate — it is N-biased out of distribution, exactly the failure mode
`_neural_model_too_noisy()` (backend/app/chord_inference.py:819) was built
to catch before routing to chroma.

## Finding 3 — presence gate: selection-time regression, no-op at test time

- **Mechanism confirmed:** `extract_chord_predictions`
  (backend/scripts/build_chord_tflite.py:1895) forces N whenever
  `presence < 0.5`, and checkpoint selection + validation metrics were
  computed on this gated output while the exported TFLite dropped the
  presence head and shipped `chord_probs` only. That is the v1.0.5
  regression path (chord head 0.4854 real → gated 0.3468, GuitarSet test
  0.111), as recorded in `backend/research/h-gain-v1.0.5/metadata.json`.
- **Live measurement:** on the deployed model, the presence gate changed
  **zero** predictions on this split (`presence_low_rate` 0.494 — the
  chord head already predicts N wherever presence is low). The gate's
  historical damage came from **selection on the training-distribution
  val set**, not from test-time behavior. Both effects argue for the same
  program rule: **no checkpoint selection on any head that is not
  exported.**

## Finding 4 — v1.0.3 / v1.0.5 TFLite baselines cannot run locally

- v1.0.3 (277-class, 40-bin) binary restored to
  `backend/research/h-gain-v1.0.3/chord_model.tflite` from the machine-local
  archive per [`docs/MODEL_PROVENANCE.md`](../MODEL_PROVENANCE.md)
  (SHA-256 prefix `4ab3e423…33ac7`, manifest-verified).
- Both v1.0.x TFLite models contain BiLSTM ops and require the SELECT_TF_OPS
  Flex delegate; `libtensorflowlite_flex.so` is **absent** from
  `.venv-wsl` (matches the note in `docs/EVALUATION.md`). The harness
  reports these rows as `status: "unavailable"` with the reason rather
  than skipping silently — see the `baselines` block in
  [`chord170_phase0_baseline.json`](../audit/amt/chord170_phase0_baseline.json).
- Cited (not reproduced locally) historical numbers: v1.0.3 val 0.8375 /
  GuitarSet test 0.287 (commit d57b6ff); v1.0.5 chord head 0.4854 real,
  0.3468 gated. Reproduction on a Flex-enabled runtime (e.g. Modal CPU
  function) is queued for Phase 2/3 infrastructure; the harness runs them
  unchanged there.

## Provenance fixes applied

1. **`DualValidationLogger` no longer destroys rows.** Previously, any
   header change (e.g. a metric key appearing once both val sets are
   non-empty, or stage-to-stage key differences such as scheduler `lr`)
   triggered `mode="w"` and truncated the CSV — the mechanism behind the
   8-row training log for a 37-epoch v1.0.5 run. Now a header mismatch
   rotates the existing file to `<name>-<timestamp>.csv` and starts a new
   one, preserving every row (verified with a two-header simulation).
2. **Latent `NameError` fixed** in the same callback: the default
   `plot_output_dir` referenced `_SCRIPTS_DIR`, a function-local in
   `run_pipeline` (backend/scripts/build_chord_tflite.py:3537), which made
   `DualValidationLogger(...)` without an explicit `plot_output_dir`
   crash. It now defaults to the script's own directory.
3. **Metadata/code mismatch documented, not rewritten:** v1.0.5
   `metadata.json` claims patience 25 / 80% real-data ramp; the committed
   code has patience 10 (build_chord_tflite.py:4009) and a 92% ramp
   target. The metadata is a historical artifact and is left untouched;
   the discrepancy is recorded here and the harness + rotation fix ensure
   future runs log their true configuration.

## Acceptance criteria status

| Criterion | Status |
| --- | --- |
| Same splits and metrics for all baselines | ✅ MIREX-25 space, player-level test split, shared harness |
| Chord-head vs gated vs TFLite metrics reported separately | ✅ chord-head and gated measured; TFLite rows honestly `unavailable` (Flex) with a ready path |
| No production model changes | ✅ `backend/app/` untouched (report + harness + provenance fix only) |
