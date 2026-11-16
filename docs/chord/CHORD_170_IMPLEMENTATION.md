# Chord 170 Program — Implementation

Status: **Phases 0–3 complete** (2026-11-16). Phase 3 baseline trained and
evaluated; quality gates partially met (see Phase 3 section). Phases 4–6 pending. Spec source: the "Harmoniq 170-Class Chord
Model v2" implementation brief; repo rules in
[`AGENTS.md`](../../AGENTS.md).

## Mission

Replace the failed 25-class/multi-head chord experiment with a 170-class
model (12 roots × 14 qualities + N + X) that predicts bass/inversion via a
separate 13-class head, is trained accuracy-first on GPU (Modal), is
evaluated with WCSR/MIREX and per-quality metrics, can be distilled to a
CPU-friendly student, and closes the user-correction loop. The production
model is NOT swapped until the evaluation gates pass.

## Non-negotiable constraints (from the spec)

- No 25-class labels in the new training path.
- No presence head as a hard gate; no checkpoint selection on any head not
  exported to TFLite/ONNX.
- No synthetic-only 30-epoch pretraining; curriculum ≤ 10 synthetic epochs.
- No frame-accuracy-only evaluation; no production swap until gates pass.

## Vocabulary (Phase 1 — implemented)

`backend/app/chord_vocab_170.py`:

- `CHORD_VOCAB_170`: 12 roots × 14 qualities + `N` (no chord, idx 168) +
  `X` (unknown/ambiguous, idx 169) = **170 exactly**.
- Qualities: `maj, min, dim, aug, min6, maj6, min7, minmaj7, maj7, 7,
  dim7, hdim7, sus2, sus4`. **`minmaj7` and `hdim7` have no 277-class
  source** — labels come only from real datasets / pseudo-labels going
  forward. 9/11/13/alt7 are collapsed (see mapping below); if the product
  later needs them, an extension head is added after the 170 baseline
  passes. The 170 vocabulary does not silently claim 277-class coverage.
- `BASS_VOCAB`: 12 pitch classes + `X` (unknown bass) = **13 classes**.
  `N` is deliberately not a bass class. Bass may be any pitch class —
  non-chord-tone bass (e.g. `C:maj/D#`) is a legal label (decided in spec
  review).
- `compose_label` / `parse_label` / `render_label` / `label_to_indices`:
  slash labels are `root:quality/bass` when bass ≠ root and known
  (`C:maj/E`, `C:maj7/B`); root-position frames carry the root's own pitch
  class in the bass head (not X); N/X never carry bass. The chord head is
  a flat 170-class softmax — the bass head is never a hard override, and
  root-position vs slash accuracy are evaluated separately (Phase 3).

### 277 → 170 mapping table (tested)

| 277 quality | → 170 quality | Rationale |
| --- | --- | --- |
| maj, min, 7, maj7, min7, dim, dim7, aug, sus2, sus4 | identity | |
| 6 / min6 | maj6 / min6 | rename |
| 9, 11, 13 | 7 | dominant-family collapse |
| maj9 | maj7 | |
| min9 | min7 | |
| 7#9, 7b9, 7#5, 7b5, alt7 | 7 | altered-dominant collapse |
| 7sus4 | sus4 | loses the 7th, keeps the suspension |
| N | N | |

Roots are preserved unchanged. `MAP_277_TO_170_TABLE` is a precomputed
277-entry index table for vectorised loaders; every row is unit-tested
(`backend/tests/test_chord_vocab_170.py`). The original 277 label stays
recoverable from `app.chord_vocab.CHORD_VOCAB` for reporting.

### Data loader (Phase 1 — minimal)

`backend/scripts/chord_data_v2.py`:

- `load_dataset_dir_170(data_dir, split=None)` — reads the existing
  `.npz` layout, maps 277→170 via the table, and emits parallel
  `bass_labels`. Sources without bass metadata (GuitarSet CQT extracts)
  emit the unknown-bass class until the Phase 2 pipeline derives bass
  labels from note data (lowest active pitch class).
- `summarize_dataset` — dataset-card counts (N rate must be ≤ 20% before
  pseudo-label training, enforced in Phase 2).
- Splitting is by recording/track only; windows are never split.
- Verified on real data: GuitarSet test split = 60 tracks / 324 windows /
  33 unique 170-classes / N rate 3.7%.

## Baseline (Phase 0 — measured, no production change)

See [`CHORD_170_PHASE0_BASELINE.md`](CHORD_170_PHASE0_BASELINE.md).
Headline: the shipped `app/chord_model.keras` is the 25-class Commit 148
multi-task model (not registry-claimed v1.0.3) and scores **0.0432 exact
accuracy** on the held-out GuitarSet player-05 split; the presence gate is
a no-op at test time (selection-time regression confirmed as the v1.0.5
failure mode). v1.0.3/v1.0.5 TFLite rows are honestly `unavailable`
locally (Flex delegate absent) with a ready harness path for Modal.

## Provenance fixes (Phase 0)

- `DualValidationLogger` (backend/scripts/build_chord_tflite.py) rotates
  the CSV on header change instead of truncating (v1.0.5's 8-row log root
  cause) and no longer references the function-local `_SCRIPTS_DIR`.
- v1.0.5 metadata/code mismatch (patience 25 vs 10; ramp 80% vs 92%) is
  documented, not rewritten.


## Phase 2 — data pipeline (complete)

Modules: `backend/app/chord_labels.py` (bass/annotation logic) and
`backend/scripts/chord_data_v2.py` (builders + dataset card), with the
Modal prepare entrypoint in `backend/scripts/modal_chord_170.py`.

### Real datasets (bass derived from annotations)

| Source | Bass method | Train (tracks/windows) | Val | Test | Bass known |
| --- | --- | ---: | ---: | ---: | ---: |
| GuitarSet | JAMS `note_midi`, lowest active note | 240 / 1,296 | 60 / 324 | 60 / 324 | 63% train, 52% test |
| Guitar-TECHS | per-string MIDI, lowest active note | 56 / 1,452 | 12 / 82 | — | 83% |
| IDMT-SMT-Guitar (dataset4) | CSV slash bass (root position = root) | 129 / 696 | — | — | 40% |
| EGSet12 | JAMS `note_midi`, lowest active note | 9 / 45 | — | 3 / 16 | 29% |
| RWC-P | CSV Harte degree bass (`/3`, `/b7`) | 100 / 3,833 | — | — | 93% |

Bass labels are written as sidecars (`processed/chord170/<track>.npz`) so the
existing 144-bin feature cache is not duplicated. Unknown bass (X) is
reported honestly: silent/count-in windows and annotation gaps are X.

### Pseudo-labels (v2 rebuild)

`build-pseudo` re-derives labels from the W1 teacher outputs with the spec's
filters: ≥ 3 active pitches, confidence ≥ 0.6, N capped at ≤ 20 % (highest
confidence N kept).

**Finding — W1 pseudo-labels are not usable as training data.** All 1,004
W1 tracks align and load, but only **25 windows survive** (11 IDMT tracks;
N rate 20.0 %, 5 unique classes). The YouTube-crawl labels are N-dominated
(87 % in W1) and the teacher detected ≤ 1 note at most window centres, so
the ≥ 3-pitch rule correctly rejects them. This is why the spec mandates a
BTC teacher: BTC labels chords directly from audio (no note prerequisite)
and a note model (MT3/YourMT3+) supplies the pitch count, agreement check,
and bass. That relabeling is a GPU/Modal job; Phase 2 ships the pipeline,
filters, cache format, and teacher module.

Artifacts: `docs/audit/amt/chord170_phase2_dataset.json` (dataset card),
`docs/audit/amt/chord170_phase2_pseudo_report.json` (filter report).

### Splits

Track-level only; zero cross-split track overlap across **all** pairs
(train↔val, train↔test, val↔test) — verified by the card
(`cross_split_overlap_count: 0`). GuitarSet remains player-level
(00–03 train, 04 val, 05 test). IDMT/YouTube have no split metadata and are
treated as train.

### Teacher availability (checked)

| Teacher | Status |
| --- | --- |
| MT3 T5-small | local checkpoint present (`data/models/mt3/mt3_t5_small`, 186 MB) — W1 teacher |
| YourMT3+ | local checkpoint present (`data/models/mt3infer/yourmt3`) — W2 winner, usable for the agreement/pitch filter |
| MR-MT3 | local checkpoint present (`data/models/mt3infer/mr_mt3`) |
| BTC 170-class | **downloaded and verified** (`data/models/btc/btc_model_large_voca.pt`, 12 MB) |

BTC is a drop-in teacher: its 170-class vocabulary is the *same set* as ours
(12 roots × the same 14 qualities), ordered `root*14 + quality`, 168 = X,
169 = N. `scripts/btc_teacher.py` provides the verified bijection
(`BTC_INDEX_TO_170`, unit-tested) and a direct torch+librosa inference path
(the HF wrapper's `transformers` import costs minutes on this mount).
Smoke-tested on a GuitarSet track: correct-looking timeline
(`A#:maj`, `D#:maj7`, …) at ~3m50s/track on WSL CPU — bulk labeling belongs
on Modal (prepare/train functions already run there).

**Licence note:** BTC source code is MIT, but the released 170-class weights
are trained on Isophonics / Robbie Williams / UsPop2002 and distributed as
**CC-BY-NC-SA 4.0 (non-commercial)**. Project owner confirmed acceptance for
this research program; the weights are git-ignored and must not ship in a
commercial build.

### Chord-oriented mix (Deferred to GPU)

`bass + guitar + piano + other` (vocals/drums removed) is the intended
pseudo-label input. Demucs on 1,004 tracks is a GPU job; the pipeline
(`prepare` on Modal + BTC teacher) is ready for it. Locally the
teacher outputs that exist (W1) were produced from the shipped audio.

### Modal

```bash
modal volume create harmoniq-chord170-data
tar -czf /tmp/chord170_bundle.tgz -C <repo-root> backend docs
modal volume put harmoniq-chord170-data /tmp/chord170_bundle.tgz /chord170
modal run scripts/modal_chord_170.py::status
modal run --detach scripts/modal_chord_170.py::prepare
modal run --detach scripts/modal_chord_170.py::prepare --extract-rwc true
```

Phase 3 adds `train`/`eval` to the same app (A10G) — not stubbed here.

**Verified 2026-11-16** (`modal run --detach ...::prepare --extract-rwc true`):
bundle uploaded to the `harmoniq-chord170-data` volume and extracted; RWC-P
audio (4.0 GB, 100 tracks) uploaded; sidecars built for GuitarSet 360/360,
EGSet12 12/12, Guitar-TECHS 68/68, IDMT 129/129 and **RWC 100/100 after CQT
extraction**; 11 pseudo v2 tracks. The committed dataset card is the
Modal-generated one: **train 7,347 / val 406 / test 340 windows**,
`cross_split_overlap_count: 0`. Two image/pipeline fixes were found by
running it: the image needs `pydantic` (`app.data_engine` imports the
manifest models), and RWC extraction requires `parse_rwc.py` to run before
`extract_rwc_cqt.py` (both now in `prepare`).

### Known gaps

- EGSet12 train windows are 69 % N and IDMT 38 % N — both are small; the
  training recipe handles N via sampling/loss weighting, and the card records
  the rates.
- YouTube-crawl pseudo-labels are unusable until BTC + note-model relabeling
  runs on Modal.


## Phase 3 — model and training (complete; gates partially met)

Modules: `backend/scripts/train_chord_170.py` (architecture, resampling,
augmentation, training), `backend/scripts/eval_chord_170.py` (WCSR/macro-F1/
bass/slash/ECE), `backend/configs/chord170_base.yaml`, Modal `train`/`eval_model`
functions. Tests: `backend/tests/test_chord_eval_170.py` (26) plus label/
augmentation/sampling tests.

### Baseline run (Modal A10G, seed 1)

Command:

```bash
modal run --detach scripts/modal_chord_170.py::train \
  --run-name baseline-seed1-v2 --config configs/chord170_base.yaml
modal run scripts/modal_chord_170.py::eval_model \
  --checkpoint /runs/chord170/baseline-seed1-v2/best.keras \
  --split test --sources guitarset,egset12
```

100-epoch budget, patience 15; **early-stopped at epoch 60, best epoch 45**
(checkpoint selected on validation WCSR-MIREX, the deployment metric).

Held-out test (GuitarSet player 05 + EGSet12, 340 windows / 63 tracks):

| Metric | Value |
| --- | ---: |
| WCSR root / majmin / thirds / triads / sevenths / tetrads | 0.412 / 0.353 / 0.382 / 0.335 / 0.320 / 0.300 |
| **WCSR MIREX** | **0.385** |
| Macro-F1 (170) | 0.241 |
| Exact accuracy | 0.371 |
| Top-3 accuracy | 0.624 |
| **ECE (duration-weighted)** | **0.087** |
| Bass accuracy (chord frames) | 0.377 |
| Slash accuracy | 0.070 |
| Per-quality F1 | maj 0.72, min 0.45, dim7 0.50, 7 0.27, N 0.37 |
| Per-source exact | GuitarSet 0.370, EGSet12 0.375 |

Validation (used for selection): WCSR-MIREX 0.394, macro-F1 0.136,
ECE 0.044.

### Gate status (spec acceptance)

| Gate | Target | Result | Status |
| --- | --- | --- | --- |
| v1.0.3 GuitarSet WCSR-MIREX +5 pts | — | root WCSR 0.412 vs published v1.0.3 GuitarSet test 0.287 (metric differs: root vs published accuracy; v1.0.3 binary not runnable — Flex) | ✅ directionally, metric caveat |
| v1.0.5 chord-head +8 pts | — | v1.0.5's 0.485 val-exact is on its own val distribution; our test exact 0.371 — **not directly comparable** | ⚠️ not established |
| Macro-F1 ≥ 0.45 | 0.45 | 0.241 | ❌ |
| Bass accuracy ≥ 0.60 | 0.60 | 0.377 | ❌ |
| Slash accuracy ≥ 0.50 | 0.50 | 0.070 | ❌ |
| ECE ≤ 0.15 | 0.15 | 0.087 | ✅ |
| No EGSet12 regression | — | exact 0.375 (no prior harness number for EGSet12 on the old model) | ⚠️ recorded, not comparative |

**No production change** (`HARMONIQ_CHORD_MODEL_V2` not wired; Phase 5).

### What blocks the remaining gates

- Macro-F1 is dominated by rare qualities the corpus barely contains
  (minmaj7/hdim7/min6 get few examples); per-quality F1 for maj min is already
  0.72/0.45 at exact 0.37. Phase 4 ablations (aux root/quality heads, more
  pseudo-labels via BTC, source weighting) target this.
- Bass/slash are weak (0.38/0.07). The bass head shares the encoder and
  weighted only 0.35; slash accuracy requires *both* heads correct on
  inversion windows. Raising `bass_loss_weight`, adding an aux head, and
  training on more bass-labelled data are Phase 4/5 candidates.
- Train accuracy 0.47 vs val macro-F1 0.14 indicates underfitting at this
  budget/model size — the spec allows a larger teacher distilled later.

### Defects found and fixed while running Phase 3

1. **Pitch-shift augmentation transposed features 12× more than labels**
   (rolled 24 bins per semitone; the CQT has 2 bins/semitone). This poisoned
   training (val WCSR-MIREX stuck at 0.19). Fixed to `shift * 2` bins; the
   same probe then reached 0.30 by epoch 15 and 0.39 at convergence.
2. `tf_keras` version skew: Modal-installed 2.21 wrote checkpoints that local
   2.20 could not load (`InputLayer.optional`, MHA
   `softmax_robust_masking`). Pinned `tf_keras==2.20.0` in the Modal image and
   added the config-compat loader (shared with the Phase 0 harness).
3. Installing `torch` (cu124) in the TF image clobbered cuDNN (“No DNN in
   stream executor”); removed torch from the training image (BTC teacher will
   get its own image when needed).
4. WSL GPU (GTX 1050, cc 6.1) cannot run mixed-precision LSTM init; the
   trainer now auto-falls back to CPU below cc 7.0.

Artifacts: `docs/audit/amt/chord170_phase3_baseline_{val,test}.json`,
`docs/audit/amt/chord170_phase3_training_log.csv`; checkpoint on the
`harmoniq-chord170-runs` volume at `/chord170/baseline-seed1-v2/`.

## Phase plan (remaining)

| Phase | Scope | Gate |
| --- | --- | --- |
| 2 | **Done** — see Phase 2 section above | Pseudo-label report (N ≤ 20% ✓), zero track overlap ✓, Modal cache ✓ |
| 3 | **Done** — see Phase 3 section. Pipeline + baseline trained/evaluated | ECE ✅; macro-F1/bass/slash ❌ (Phase 4 targets) |
| 4 | Ablations (25/170/277, aux heads, teachers, mixes, pretrain epochs) | Winning config with CIs; negative results documented |
| 5 | Distill + TFLite/ONNX export, FP16/INT8, latency, feature flag `HARMONIQ_CHORD_MODEL_V2=1`, registry/docs | Exported heads match evaluated heads; teacher drop ≤ 3pp |
| 6 | Correction loop (`backend/app/corrections_dataset.py` schema) | Corrections improve rare-class recall without degrading common classes |

## Verification

```bash
cd backend
.venv-wsl/bin/python -m pytest -q tests/test_chord_vocab_170.py tests/test_chord_labels_170.py
.venv-wsl/bin/python -m pytest -q tests/test_chord_eval_baseline.py
.venv-wsl/bin/python scripts/chord_data_v2.py data/guitarset --split test
```

Existing 277/25-class tests still pass (`test_chord_vocab.py`,
`test_real_label_vocab.py`, `test_student_vocab.py` re-run in Phase 1).
