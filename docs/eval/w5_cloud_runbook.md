# W5 calibration & recording-quality — cloud GPU runbook

Commit 1 / W5 measures chord-template confidence calibration and evaluates
the ingest recording-quality gate on the committed 705-track manifest.

Only **chord-template confidence** is calibrated. MT3 note confidence is a
placeholder (`0.9`) because the MT3 `NoteSequence` has no confidence field;
note-level calibration is explicitly deferred.

---

## 1. What the code provides

| Path | Purpose |
| --- | --- |
| `backend/scripts/eval_calibration_quality.py` | Pool per-track calibration bins, compute ECE, join audio quality, sweep gate thresholds |
| `backend/scripts/stage_w5_cloud_bundle.py` | Copy only manifest-resolved audio/GT + checkpoint + code |
| `backend/scripts/w5_modal.py` | Modal A10G app (`smoke`, `evaluate`, `aggregate`, `status`) |
| `docs/audit/amt/w5_calibration.{json,md}` | Committed result artifact |

---

## 2. Stage the bundle

```bash
cd backend
python scripts/stage_w5_cloud_bundle.py --out /tmp/w5_bundle
tar -C /tmp/w5_bundle -czf w5_bundle.tgz .
modal volume create harmoniq-w5
modal volume put harmoniq-w5 w5_bundle.tgz /w5_bundle.tgz
```

The bundle contains only manifest-referenced audio/ground truth, the MT3
checkpoint, and backend code. RWC-P audio is CC BY-NC 4.0 — keep the volume
private and never commit audio.

On a slow link a multi-GB single-file upload can stall. Split the tarball
and upload `chunks/w5_bundle.tgz.part-*`; `_ensure_bundle` joins the parts
before extracting. The harness can also reuse the datasets already on the
`harmoniq-w2` / `harmoniq-w3` volumes: `evaluate` and `aggregate` rewrite
the committed manifest against those mounted volumes and skip tracks that
are not present.

---

## 3. Smoke the GPU path

```bash
modal run scripts/w5_modal.py::status
modal run scripts/w5_modal.py::smoke
```

`smoke` runs the MT3 tier on one EGSet12 track. If JAX/T5X cannot initialize
on the A10G, stop and use the documented fallback (50-track W2 MT3 cache +
full-manifest chroma) rather than silently changing the calibration target.

---

## 4. Run the full calibration

```bash
modal run --detach scripts/w5_modal.py::evaluate --source guitarset
modal run --detach scripts/w5_modal.py::evaluate --source egset12
modal run --detach scripts/w5_modal.py::evaluate --source idmt_smt_guitar
modal run --detach scripts/w5_modal.py::evaluate --source guitar_techs
modal run --detach scripts/w5_modal.py::evaluate --source rwc_p
```

Each run writes `w5_eval_mt3-<source>.json` under `/w5/docs/audit/amt` and
commits the prediction cache. Preemption restarts resume from the cache.

Optional production-chain check (runs MT3 again through the fallback chain):

```bash
modal run --detach scripts/w5_modal.py::evaluate --source guitarset --tier full
```

---

## 5. Aggregate

```bash
modal run scripts/w5_modal.py::aggregate
modal volume get harmoniq-w5 /w5/docs/audit/amt ./amt
```

Copy `w5_calibration.json` and `w5_calibration.md` into
`docs/audit/amt/`.

---

## 6. Choose and wire the gate

The calibrated fallback gate is **off by default**. Choose
`MT3_GATE_CHORD_CONFIDENCE_MIN` in
`backend/app/confidence_thresholds.py` from the pooled reliability table:

1. Find the lowest raw-confidence bin whose measured accuracy is `>= 0.70`.
2. Use that bin's lower edge as the floor.
3. If no bin reaches `0.70`, use the highest-accuracy bin, record the ceiling
   in `docs/EVALUATION.md`, and mark the gate *not release-ready*.

Enable it with:

```bash
export HARMONIQ_CONFIDENCE_GATE=1
```

Rollback is unsetting the variable. The student tier
(`HARMONIQ_STUDENT_ENABLED`) and the ingest quality gate
(`HARMONIQ_SKIP_AUDIO_QUALITY_GATE=1`) keep their existing rollbacks.

---

## 7. Measured result (2026-11-11)

The committed run resolved 526 tracks from the W2/W3 volumes (GuitarSet 360,
IDMT 129, EGSet12 12, Guitar-TECHS 10, RWC-P 15) and produced:

- pooled ECE **0.7281**; mean confidence **0.9307**; accuracy **0.2026**;
- no bin reaches 0.70 accuracy (best: 0.8–0.9 at 0.544);
- `MT3_GATE_CHORD_CONFIDENCE_MIN = 0.80`, documented as **not
  release-ready**;
- recording-quality gate accepted all 513 scored tracks (no rejected
  group), so it is not validated as an accuracy predictor on this
  studio/controlled manifest.

The 179 Guitar-TECHS/RWC-P tracks not present on the volumes are a
documented coverage gap.

## 8. Local / CPU use

The aggregator is CPU-only and can run on any machine that has the audio:

```bash
cd backend
backend/.venv-wsl/bin/python scripts/eval_calibration_quality.py \
  --manifest ../docs/eval/amt_manifest.json \
  --eval-report ../docs/audit/amt/w5_eval_mt3-guitarset.json \
  --out-json ../docs/audit/amt/w5_calibration.json \
  --out-md ../docs/audit/amt/w5_calibration.md
```

Use `--skip-quality` to skip audio decoding.
