# AMT evaluation (Commit 1 / W0)

This directory holds the committed, reproducible evaluation inputs for the
guitar-AMT research program. The harness is evaluation-only; it does not run
inside `/analyze`. Exact clean-checkout commands and artifact-to-number
mappings are in [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

## What is here

| File | Purpose |
| --- | --- |
| `amt_manifest.json` | 705-track manifest generated from the datasets present in `backend/data/` |
| `../audit/amt/` | Generated JSON + Markdown reports (created by the harness) |

The manifest references audio/annotations relative to `backend/` through
`data_root`. Audio is gitignored and is not committed.

## Datasets currently included

| Source | Tracks | Ground truth | Split |
| --- | ---: | --- | --- |
| GuitarSet | 360 | JAMS `note_midi` + chord timeline | `split_policy.json` (player 03 = test, 05 = val) |
| EGSet12 | 12 | JAMS `note_midi` + chord timeline | test |
| IDMT-SMT-Guitar | 129 | chord timeline (no note MIDI) | test |
| Guitar-TECHS | 104 | per-string MIDI + chord timeline | test |
| RWC-P | 100 | chord timeline (CC BY-NC 4.0) | test |

The manifest is regenerated with:

```bash
cd backend
python scripts/build_eval_manifest.py
```

## Missing datasets / strata

The committed manifest covers **studio / controlled** recordings (including
RWC-P full mixes with 1–7 instruments) plus jazz/funk (EGSet12). Live, home,
and kora/mbira OOD recordings are user-supplied; use the
[external recording intake](external_recordings.md) to add them without
modifying the committed dataset-only manifest.

RWC-P (CC BY-NC 4.0) is already downloaded locally and parsed into the
manifest. To reproduce:

```bash
cd backend
export HARMONIQ_RWC_LICENSE_ACK=1
python scripts/download_rwc.py --download-audio
python scripts/parse_rwc.py
python scripts/build_eval_manifest.py
```

Only the annotations are downloaded without `--download-audio`. Do not
redistribute RWC-P audio or include it in a public release.

## Running

```bash
cd backend

# One tier
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier mt3 \
  --limit 5 \
  --report ../docs/audit/amt/eval-mt3.json

# All four baselines + comparison
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier all \
  --limit 5 \
  --report ../docs/audit/amt/eval-all.json

# Chroma is fast; use it for a smoke check of the harness
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier chroma --limit 2 --report /tmp/amt-smoke.json
```

Tiers: `mt3`, `crnn` (Keras/TFLite only, no chroma fallthrough), `chroma`,
`full` (the production fallback chain). `all` runs every tier on the same
track selection and writes `<report>-<tier>.json` plus a comparison report.

Predictions are cached under `backend/data/evaluation/predictions/` keyed by
audio hash, so repeated runs and per-tier comparisons are cheap. Use
`--refresh` to ignore the cache.

## Metrics

- onset match: same pitch (and optionally GM program) within ±50 ms;
- offset match: onset plus offset within `max(50 ms, 20% of reference duration)`;
- overlap: interval IoU over offset-matched notes;
- dynamics: velocity MAE over offset-matched notes;
- instrument: exact GM program and GM-family accuracy;
- chords: duration-weighted frame accuracy on the 25-class MIREX vocabulary,
  plus interval P/R/F1;
- calibration: duration-weighted ECE over chord confidences, reusing
  `app/confidence_calibration.py`;
- runtime: wall time per track.

Reports are deterministic (sorted keys, rounded floats, no timestamps or
absolute paths). `schema_version` is bumped when the report shape changes.

## Known caveats

- **MT3 event confidence is currently a placeholder.** `_note_sequence_to_events`
  falls back to `0.9` because the MT3 `NoteSequence` has no confidence field.
  The `mean_confidence=0.90` in reports reflects that placeholder, not a
  measured model probability. W5 must fix this before calibration/gating.
- **GuitarSet split:** `split_policy.json` defines player 03 as test and
  player 05 as validation. Earlier docs called player 05 “test”; the manifest
  follows the policy file.
- CRNN/chroma are chord-only baselines; the verdict rubric does not fail them
  for a missing solo line.
- The bundled GuitarSet / EGSet12 / IDMT / Guitar-TECHS tracks are
  solo-guitar (`instrument_count=1`). RWC-P adds full-mix strata
  (1–7 instruments, derived from `metadata.csv`); live/home/OOD recordings
  remain absent.

## Compute for W1–W4

W0 is CPU-only. For the GPU workstreams, the recommended order is:

1. **Modal** — serverless, auto-scale-to-zero, `$30/mo` free credit with a
   card (`$5` without). Best default for bursty W1/W2 inference.
2. **Lightning AI** — 75–80 free GPU hours; good for a first student training
   run.
3. **vast.ai** — lowest `$/hr` (RTX 4090 from ~`$0.27/hr`) once free credits
   are exhausted or a long run is needed.

Pin the container image, CUDA/JAX versions, dataset checksums, and model
commit hashes in every run record.

## Verdict vs accuracy

The Pass/Warn/Fail verdict encodes the original docs/EVALUATION.md rubric
(presence + confidence + completion). It is **not** an accuracy gate. A track
can be `pass` while its chord frame accuracy is low, because MT3 confidence on
the MT3 path is template coverage, not a calibrated probability. Use the
metric columns for research decisions; use the verdict only for parity with
the historical smoke-test rubric.

## W1 data engine

The W1 scripts live alongside the W0 harness:

```bash
cd backend

python scripts/build_w1_manifest.py          # docs/eval/w1_dataset_manifest.json (2,117 real tracks)
python scripts/pseudo_label_w1.py --limit 5  # MT3 teacher + confidence filtering
# Long CPU runs: add --skip-existing --report-every 25; use --offset N --limit M to shard
python scripts/augment_w1.py --limit 2       # GuitarSet solo + RWC-P background mix
python scripts/merge_w1_reports.py --report /tmp/shard1.json --report /tmp/shard2.json  # sharded CPU runs
```

See `dataset_card.md` for composition, splits, label provenance, and the
MT3 low-yield finding, and `licences.md` for the dataset/model licence audit.
Generated outputs stay under `backend/data/pseudo_label/w1/` (gitignored);
reports go to `docs/audit/amt/`.


## W2 teacher comparison

The W2 harness runs every available teacher over a fixed, committed
50-track sample and emits a go/no-go recommendation for the W3 student's
teacher. Teachers: `mt3` (production JAX/T5X baseline), `mr_mt3`
(MR-MT3 PyTorch via `mt3-infer`), `yourmt3` (YourMT3+ PyTorch via
`mt3-infer`), and `musicfm` (documented placeholder — encoder-only, the
MIROS/YourMT3 decoder and its weight licence are outstanding).

```bash
cd backend

# Regenerate the fixed 50-track sample (committed; deterministic)
python scripts/build_teacher_sample.py

# Full comparison (cached per track; repeat runs stay cheap)
HARMONIQ_MT3_INFER_PATH=/path/to/mt3-infer \
HARMONIQ_MT3_CHECKPOINT_DIR=data/models/mt3infer \
HARMONIQ_TEACHER_DEVICE=cuda \
python scripts/compare_teachers.py --teachers mt3,mr_mt3,yourmt3,musicfm

# Options for long runs: teachers are cached under
# backend/data/evaluation/teacher_outputs/ keyed by audio hash.
#   --offset N --limit M    shard a long CPU/GPU run (cache makes it resumable)
#   --cached-only           score caches only; never run inference
#   --refresh               ignore cached teacher outputs
#   --device cuda           PyTorch teacher worker on GPU
```

Report: `docs/audit/amt/w2_teacher_comparison.{json,md}` — per-teacher
summaries, deltas vs MT3, teacher statuses with reasons, and a go/no-go
decision with per-candidate checks (accuracy tolerance, leakage tolerance,
guitar-retention floor, RTF ratio). Metrics are guitar-filtered MR-MT3 style:
`notes` metrics use guitar-program-filtered predictions; `notes_raw` is the
raw output, so instrument leakage stays visible rather than hidden.

Long CPU/GPU batches should be sharded with `--offset/--limit` and let the
output cache accumulate. The worker flushes its output file after every track,
so an interruption loses at most the in-flight track (not the whole batch).

The MT3 baseline is scored from the uploaded output cache, so a PyTorch-only
GPU box can produce the full report without installing JAX/T5X. To offload a
run to Cerebrium / Modal / Lightning / vast.ai, use
[`w2_cloud_runbook.md`](w2_cloud_runbook.md) and
`backend/scripts/stage_w2_cloud_bundle.py` (stages the 50-track sample audio,
ground truth, and the existing teacher cache into a self-contained bundle).
The repo includes a ready Cerebrium project in `cerebrium_w2/`.


## W3 two-head student

The W3 student shares one convolutional encoder between a 277-class
framewise chord head and an autoregressive guitar-vocabulary solo head.
Artifacts live in `backend/data/models/student/` (gitignored). See
[`w3_cloud_runbook.md`](w3_cloud_runbook.md) for the Modal A10G workflow.

```bash
cd backend

# Train + QAT + export + latency benchmark (local smoke / CPU)
CUDA_VISIBLE_DEVICES=-1 TF_USE_LEGACY_KERAS=1 \
python scripts/build_student_model.py --sources w1 --epochs 40

# Evaluate the student tier (adds root accuracy to the W0 report)
python scripts/eval_amt.py \
  --manifest ../docs/eval/amt_manifest.json \
  --tier student --source guitarset --split test \
  --report ../docs/audit/amt/w3_eval_student.json
```

The student is opt-in at runtime:

```bash
export HARMONIQ_STUDENT_ENABLED=1
export HARMONIQ_STUDENT_MODEL_DIR=/path/to/backend/data/models/student
```

It is tried before MT3 and falls through to the unchanged
MT3 → CRNN → chroma chain on any failure. G3 uses
`chords.root_accuracy` (duration-weighted root match), not the 25-class
frame accuracy.

## W4 tablature assignment

The W4 harness compares the per-note `allCellsForMidi` heuristic with a
playability-aware sequence DP on string/fret ground truth. It is symbolic
(MIDI→tab): reference pitches are assigned, so transcription error is
excluded.

```bash
cd backend
python scripts/eval_tab.py \
  --source guitarset,egset12 --split test \
  --augment-capo --augment-tuning \
  --report ../docs/audit/amt/w4_tab_eval.json
```

Ground truth comes from the per-string `note_midi` annotations in GuitarSet
and EGSet12 (`annotation_metadata.data_source` 0 = low E … 5 = high E);
Guitar-TECHS per-string MIDI is supported when a file has exactly six named
string tracks. DadaGP is not staged (research access on request).

Metrics: pitch accuracy, tab accuracy (exact string/fret), and the
Fretting-Transformer playability difficulty. The report also records group
validity (distinct strings for simultaneous notes). Tuning/capo variants are
augmented, not recorded performances.

Report: `docs/audit/amt/w4_tab_eval.{json,md}`. The DP is evaluation-only;
production tab generation is unchanged.

## W5 calibration & recording-quality evaluation

W5 measures **chord-template confidence** calibration on the expanded
manifest and evaluates the ingest recording-quality gate against measured
chord frame accuracy. MT3 note confidence is still a placeholder (`0.9`)
because the MT3 `NoteSequence` has no confidence field; note-level
calibration is explicitly deferred and must not be claimed.

```bash
cd backend

# Full MT3 calibration on a Modal A10G (see w5_cloud_runbook.md)
modal run --detach scripts/w5_modal.py::evaluate --source guitarset
modal run --detach scripts/w5_modal.py::evaluate --source egset12
modal run --detach scripts/w5_modal.py::evaluate --source idmt_smt_guitar
modal run --detach scripts/w5_modal.py::evaluate --source guitar_techs
modal run --detach scripts/w5_modal.py::evaluate --source rwc_p

# Pool bins + evaluate the quality gate (CPU)
modal run scripts/w5_modal.py::aggregate
```

Or aggregate existing reports locally:

```bash
python scripts/eval_calibration_quality.py \
  --manifest ../docs/eval/amt_manifest.json \
  --eval-report ../docs/audit/amt/w5_eval_mt3-guitarset.json \
  --out-json ../docs/audit/amt/w5_calibration.json \
  --out-md ../docs/audit/amt/w5_calibration.md
```

Report: `docs/audit/amt/w5_calibration.{json,md}`. It contains the pooled
reliability table, ECE, per-source/per-stratum summaries, and the
recording-quality gate confusion matrix + threshold sweep. The committed
per-source reports (`docs/audit/amt/w5_eval_mt3-*.json`) reproduce the
calibration table without audio or GPUs; see
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

**Measured 2026-11-11:** 526 tracks / 15,204 chord events; pooled **ECE
0.7281**, mean confidence 0.9307, accuracy 0.2026. No bin reaches 0.70
accuracy (best 0.544), so the calibrated gate uses the best available
cutoff (0.80) and is documented as **not release-ready**. The remaining 179
Guitar-TECHS/RWC-P tracks were not staged on the Modal volumes; the run
reused the W2/W3 volumes to avoid a 10 GB re-upload. The recording-quality
gate accepted all 513 scored tracks (18 high-accuracy, 495 low-accuracy), so
it is not validated as an accuracy predictor on the studio-only manifest.

### Calibrated fallback gate (opt-in)

```bash
export HARMONIQ_CONFIDENCE_GATE=1
```

When enabled, the MT3 tier decodes first and accepts only when the
duration-weighted chord-template confidence clears
`MT3_GATE_CHORD_CONFIDENCE_MIN` (chosen from the W5 reliability table).
When unset, the legacy event-mean check (`>= 0.7`) is unchanged. Rollback is
unsetting the variable.

### Export band metadata

MusicXML exports from JSON carry `harmoniq-confidence-band` as a
`<miscellaneous-field>` under `<identification>`. GP5→MIDI/MusicXML
responses also return an `X-Harmoniq-Confidence-Band` header when the
request supplies a band. Raw percentages are never exported.

### UI wording

The four learner-facing confidence surfaces render coarse bands only:
`Rough transcription — check by ear`, `Approximate transcription — check by
ear`, `Transcription generated — verify by ear`. The high band deliberately
does not claim an accuracy level.

## External / OOD recordings

Live, home, and kora/mbira recordings are user-supplied and kept out of the
committed manifest. Put them under `backend/data/eval_external/{live,home,ood}`
and run:

```bash
cd backend
python scripts/ingest_eval_recordings.py
python scripts/eval_amt.py --manifest data/eval_external/manifest.json --tier all
```

Optional `.notes.json`, `.chords.json`, `.jams`, or `.mid` files add ground
truth. A recording without annotations is **qualitative**: the report records
completion/runtime/output but leaves the verdict unscored. See
[`external_recordings.md`](external_recordings.md) for the layout and metadata.
