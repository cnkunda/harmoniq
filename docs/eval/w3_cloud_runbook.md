# W3 two-head student — cloud GPU runbook

Commit 1 / W3 trains one shared-encoder student with two heads:

- **Chord head:** 277-class framewise chords at the 100 ms CQT hop.
- **Solo head:** frame-synchronous, autoregressive **guitar-vocabulary**
  event tokens (`ONSET(pitch) + VELOCITY(bin)`, `OFFSET(pitch)`,
  `TIME_SHIFT`). Pitches are restricted to E2–C7 (MIDI 40–96), so the model
  cannot emit non-guitar notes.

Training, QAT, export, and evaluation run on a **Modal A10G**.

---

## 1. What the code provides

| Path | Purpose |
| --- | --- |
| `backend/app/student/vocab.py` | Guitar event vocabulary + decode |
| `backend/app/student/targets.py` | Framewise chord + token targets |
| `backend/app/student/model.py` | Shared conv encoder + two heads, QAT, TFLite |
| `backend/app/student/inference.py` | TFLite/Keras loader + chord/solo decode |
| `backend/scripts/build_student_model.py` | Train / QAT / export / benchmark CLI |
| `backend/scripts/w3_modal.py` | Modal app (`train`, `qat`, `evaluate`, `status`) |
| `backend/scripts/stage_w3_cloud_bundle.py` | Self-contained bundle builder |

The deployable artifact is `backend/data/models/student/student_model.tflite`.
The Keras checkpoints (`student_model.keras`, `student_model_qat.keras`) are
kept for reproducibility.

---

## 2. Local smoke (CPU)

```bash
cd backend
CUDA_VISIBLE_DEVICES=-1 TF_USE_LEGACY_KERAS=1 \
python scripts/build_student_model.py \
  --sources amt --limit-tracks 1 --max-windows-per-track 4 \
  --epochs 1 --qat-epochs 1 --batch-size 2 \
  --output-dir /tmp/w3_student --benchmark \
  --report /tmp/w3_student/latency.json
```

Useful flags:

- `--sources w1,amt` — W1 human/weak + pseudo labels, plus W0 non-test tracks.
- `--max-windows-per-track N` — cap CQT windows per track.
- `--qat-only` — reuse an existing `student_model.keras` and only run QAT/export.
- `--benchmark` — write per-frame TFLite latency.

The script never trains on a `test` track. GuitarSet follows
`split_policy.json` (player 03 = test), **not** the stale `split` field in
`backend/data/guitarset/processed/cqt/*.npz`.

---

## 3. Modal (A10G)

```bash
cd backend

# 1. Build the bundle and upload it
python scripts/stage_w3_cloud_bundle.py --out /tmp/w3_bundle --include-audio
modal volume create harmoniq-w3
modal volume put harmoniq-w3 /tmp/w3_bundle /w3

# 2. Sanity check (TF/tfmot/GPU/pseudo-label counts)
modal run scripts/w3_modal.py::status

# 3. Cache the feature arrays on the volume (CPU, no GPU cost)
modal run --detach scripts/w3_modal.py::prepare --sources w1

# 4. Train + QAT + TFLite export (loads the cache; fast on A10G)
modal run --detach scripts/w3_modal.py::train --sources w1 --epochs 40 --force true

# 5. Latency benchmark (reuses the checkpoint)
modal run scripts/w3_modal.py::qat

# 6. GuitarSet test evaluation with the student tier
#    (pass --refresh true after retraining to bypass stale predictions)
modal run scripts/w3_modal.py::evaluate --source guitarset --split test --refresh true

```

Fetch artifacts:

```bash
modal volume get harmoniq-w3 /w3/backend/data/models/student ./student
modal volume get harmoniq-w3 /w3/docs/audit/amt ./amt
```

`--include-audio` copies several GB. A box that already has the datasets can
omit it and upload only the labels/manifests.

---

## 4. Evaluation and the W3 gate

Add the student artifact to `backend/data/models/student/`, then:

```bash
cd backend
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier student --source guitarset --split test \
  --report ../docs/audit/amt/w3_eval_student.json
```

The report includes:

- `chords.frame_accuracy` — 25-class MIREX frame accuracy (existing).
- `chords.root_accuracy` — **the G3 metric**: duration-weighted root match.
- `aggregates.chord_root_accuracy` — mean across tracks.
- note metrics when `HARMONIQ_STUDENT_SOLO` is not `0`.

Gate G3: `chord_root_accuracy >= 0.70` on GuitarSet test (player 03), or a
documented ceiling.

### Rollout flag

The student is **off by default**. Enable it with:

```bash
export HARMONIQ_STUDENT_ENABLED=1
export HARMONIQ_STUDENT_MODEL_DIR=/absolute/path/to/models/student
# optional: disable the (slower) autoregressive solo decode
export HARMONIQ_STUDENT_SOLO=0
```

When enabled, `transcribe_with_fallback` tries the student first and falls
through to the unchanged MT3 → CRNN → chroma chain on any error, missing
artifact, or `< 3` chord events.

---

## 5. Measured baseline (2026-11-10)

- Corpus: 1,244 available W1 tracks (GuitarSet + EGSet12 + IDMT human and
  pseudo-labels).
- GuitarSet test (60 tracks, player 03): **root accuracy 0.5128**, 25-class
  frame accuracy 0.4756. This is below the 0.70 gate and is recorded as the
  documented ceiling.
- Solo note F1: **0.0** — the solo head trains but does not yet produce
  usable matched notes.
- Latency: **0.382 ms/window, 0.002986 ms/frame** (128-frame window).
- Artifacts: `docs/audit/amt/w3_eval_student.json`,
  `docs/audit/amt/w3_latency.json`.

## 6. Known deviations

- **INT8 export currently falls back to FP16.** TF 2.20's INT8 converter
  fails on the Conv1D reshape (`CONV_2D input dims 3 != 4`). QAT is applied
  and `student_model_qat.keras` is retained; the shipped TFLite is FP16 from
  the float checkpoint. Revisit when the converter or the encoder changes.
- **Solo targets come from the existing W1 MT3 pseudo-labels** (plus
  GuitarSet/EGSet12 human notes). The W2 `go` teacher was YourMT3+; a full
  YourMT3+ re-label of the 1,004 W1 tracks is a separate GPU pass.
- **The historical 5-song set is not in the repo.** Per the owner decision,
  the regression check uses the W0 `full`-tier manifest baseline.
- **The student reads 128-frame CQT windows**; chord events are emitted by
  aggregating all 128 per-frame predictions across overlapping windows.
