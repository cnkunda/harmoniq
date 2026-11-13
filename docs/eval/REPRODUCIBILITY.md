# W6 reproducibility package

This page lists the exact commands and committed artifacts behind the
headline numbers in [`docs/RESEARCH.md`](../RESEARCH.md) and
[`docs/EVALUATION.md`](../EVALUATION.md).

**What a clean checkout reproduces without data or GPUs:** the committed
analysis artifacts (manifest, reports, calibration table, tab evaluation).
**What needs the gitignored datasets/models:** fresh inference runs. Audio,
teacher caches, and student/TFLite artifacts are deliberately not committed.

---

## 1. Environment

```bash
# Frontend health
npm ci
npm run lint

# Backend
cd backend
python -m venv .venv-wsl && source .venv-wsl/bin/activate
pip install -e ".[dev]"
# MT3 (teacher) and the W2/W3/W5 cloud runs:
pip install -e ".[mt3]"
```

The MT3 checkpoint lives under `backend/data/models/mt3/` (gitignored,
~190 MB) and is downloaded by `python scripts/download_mt3_checkpoint.py`.

---

## 2. Headline numbers and artifacts

| Workstream | Headline | Committed artifact |
| --- | --- | --- |
| W0 | 705-track manifest; challenge-style metrics + verdict rubric | `docs/eval/amt_manifest.json`, `docs/audit/amt/eval-smoke-all.*` |
| W1 | 1,004 pseudo-labeled tracks; 1,654 / 233 / 230 splits; zero train↔eval overlap | `docs/eval/w1_dataset_manifest.json`, `docs/audit/amt/w1_pseudo_label_full.json`, `docs/eval/dataset_card.md` |
| W2 | 50-track teacher comparison; `go` → YourMT3+ (onset F1 0.5723, leakage 0.5756) | `docs/audit/amt/w2_teacher_comparison.{json,md}`, `docs/eval/w2_teacher_sample.json` |
| W3 | Student ceiling 0.5128 GuitarSet root accuracy; 0.002986 ms/frame; solo F1 0.0 | `docs/audit/amt/w3_eval_student.json`, `docs/audit/amt/w3_latency.json` |
| W4 | Tab accuracy 0.5893 vs 0.5031 baseline; group validity 1.0 vs 0.5076 | `docs/audit/amt/w4_tab_eval.{json,md}` |
| W5 | ECE 0.7281 on 526 tracks; quality gate inconclusive; calibrated gate not release-ready | `docs/audit/amt/w5_calibration.{json,md}`, `docs/audit/amt/w5_eval_mt3-*.json` |

---

## 3. W0 — evaluation harness

```bash
cd backend

# Regenerate the committed manifest from the staged datasets
python scripts/build_eval_manifest.py

# One tier on the committed manifest (needs audio; MT3 needs the checkpoint)
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier mt3 --limit 5 \
  --report /tmp/eval-mt3.json

# All baselines + comparison
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier all --limit 5 \
  --report /tmp/eval-all.json
```

Predictions cache under `backend/data/evaluation/predictions/` keyed by audio
hash; `--refresh` ignores the cache. Reports are deterministic (sorted keys,
rounded floats, no timestamps/absolute paths).

---

## 4. W1 — data engine

```bash
cd backend

python scripts/build_w1_manifest.py        # docs/eval/w1_dataset_manifest.json
python scripts/pseudo_label_w1.py --limit 5 --min-chord-confidence 0.6
python scripts/augment_w1.py --limit 2
```

The full CPU run used `--skip-existing` + `--offset/--limit` shards and
`scripts/merge_w1_reports.py`; the final report is committed at
`docs/audit/amt/w1_pseudo_label_full.json`. See
[`dataset_card.md`](dataset_card.md) for splits, provenance, and the
MT3 low-yield finding.

---

## 5. W2 — teacher comparison

```bash
cd backend

# Fixed 50-track sample (test > val > train within each source)
python scripts/build_teacher_sample.py

# Cached-only reproduction of the cloud decision (no mt3-infer install needed)
python scripts/compare_teachers.py --cached-only
```

The full A10G run is documented in
[`w2_cloud_runbook.md`](w2_cloud_runbook.md). It requires the teacher cache
under `backend/data/evaluation/teacher_outputs/` (gitignored) or the W2
Modal volume. The committed report is the source of truth for the decision.

---

## 6. W3 — two-head student

```bash
cd backend

# Train / QAT / export / benchmark (local smoke; GPU recommended)
CUDA_VISIBLE_DEVICES=-1 TF_USE_LEGACY_KERAS=1 \
python scripts/build_student_model.py \
  --sources w1 --epochs 40 --benchmark

# Evaluate the student tier (requires the exported artifact)
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier student --source guitarset --split test \
  --report ../docs/audit/amt/w3_eval_student.json
```

The cloud workflow is in [`w3_cloud_runbook.md`](w3_cloud_runbook.md).
The committed artifacts record the 0.5128 ceiling and 0.002986 ms/frame.

---

## 7. W4 — tablature assignment

```bash
cd backend

python scripts/eval_tab.py \
  --source guitarset,egset12 --split test \
  --augment-capo --augment-tuning \
  --report ../docs/audit/amt/w4_tab_eval.json
```

This is symbolic (MIDI→tab) and requires GuitarSet/EGSet12 audio + JAMS
annotations. The committed report records tab accuracy 0.5893 vs 0.5031,
playability 2.6092 vs 2.4529, and group validity 1.0 vs 0.5076.

---

## 8. W5 — calibration and recording quality

**Calibration is reproducible from the committed per-source reports without
audio or GPUs:**

```bash
cd backend
python scripts/eval_calibration_quality.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier mt3 \
  --eval-report ../docs/audit/amt/w5_eval_mt3-guitarset.json \
  --eval-report ../docs/audit/amt/w5_eval_mt3-idmt_smt_guitar.json \
  --eval-report ../docs/audit/amt/w5_eval_mt3-egset12.json \
  --eval-report ../docs/audit/amt/w5_eval_mt3-guitar_techs.json \
  --eval-report ../docs/audit/amt/w5_eval_mt3-rwc_p.json \
  --skip-quality \
  --out-json /tmp/w5_calibration.json \
  --out-md /tmp/w5_calibration.md
```

The pooled ECE must match **0.7281** and the reliability bins must match
`docs/audit/amt/w5_calibration.json` exactly. The committed per-source
reports cover 526 tracks (GuitarSet 360, IDMT 129, EGSet12 12,
Guitar-TECHS 10, RWC-P 15); the remaining 179 Guitar-TECHS/RWC-P tracks
were not staged on the Modal volumes (documented coverage gap).

The recording-quality section additionally decodes the local audio:

```bash
# Omit --skip-quality to recompute the gate confusion matrix + threshold sweep
python scripts/eval_calibration_quality.py ... --out-json /tmp/w5_full.json
```

The Modal workflow (fresh MT3 inference + aggregation) is in
[`w5_cloud_runbook.md`](w5_cloud_runbook.md).

---

## 9. Verification commands

```bash
# Frontend
npm run lint
npx vitest run src --exclude src/constants/designTokenConformance.test.ts

# Backend (touched areas)
cd backend
.venv-wsl/bin/python -m pytest -q \
  tests/test_confidence_gate.py \
  tests/test_eval_calibration_quality.py \
  tests/test_musicxml_export_confidence.py \
  tests/test_confidence_ece.py \
  tests/test_mt3_pipeline.py \
  tests/test_student_fallback.py \
  tests/test_audio_quality.py \
  tests/test_analyze_confidence.py \
  tests/test_transcription_confidence.py \
  tests/test_musicxml_slash.py \
  tests/test_exporter.py \
  tests/test_musicxml_builder.py
```

The full `npm run test` now passes (88 files / 719 tests). The earlier
`designTokenConformance` repo-scan timeout no longer reproduces; the narrowed
command above remains useful when iterating on AMT-related source only.
