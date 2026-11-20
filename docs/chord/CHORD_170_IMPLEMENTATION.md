# Chord 170 Program — Implementation

Status: **Phases 0–4 + gate + context + fine-hop iterations complete**
(2026-11-18). Context cropping + fine-hop + inversions: bass and calibration
gates pass; macro-F1/slash remain; production untouched. Spec source: the "Harmoniq 170-Class Chord
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

> **Superseded (2026-11-16):** these numbers were measured before the external
> IDMT/RWC splits existed; the model had seen the now-held-out tracks. See
> “Gate iteration” for the corrected, honest measurement.

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


## Phase 4 — ablations and teacher comparison (complete)

> **Superseded test numbers (2026-11-16):** the Phase 4 test metrics below
> were measured on a test set that overlapped the training corpus (no external
> IDMT/RWC holdout existed yet). The teacher comparison and the relative
> ablation ordering remain informative; the absolute test numbers are leaked.
> See “Gate iteration” for the honest baseline.

Framework: `train_chord_170.py` now supports `--label-space {170,277,mirex25}`,
`--aux-heads` (root 13 + quality 15, weight 0.15), `--bass-loss-weight`,
`--no-augment`, and `--synthetic-epochs`. `eval_chord_170.py` maps every
vocabulary into the shared MIREX-25 space (`evaluate_ablation`) and reports
bootstrap 95% CIs over tracks. `modal_chord_170.py::sweep` runs a suite
sequentially on one A10G; `btc_label_tracks` runs the BTC teacher on a
separate CPU-torch image.

### Ablation table (25 epochs, seed 1, held-out test = GuitarSet p05 + EGSet12)

Exact accuracy and WCSR-MIREX are comparable across spaces; macro-F1 is in
each variant's native space (170-class for 170 rows, 25-class otherwise).

| Variant | Space | Exact | WCSR-MIREX | Macro-F1 (native) | ECE |
| --- | --- | ---: | ---: | ---: | ---: |
| 170 baseline | 170 | 0.285 | 0.300 | 0.172 | 0.075 |
| 170 + aux heads | 170 | 0.332 | 0.353 | 0.244 | 0.069 |
| 170 + bass weight 0.5 | 170 | 0.332 | 0.347 | 0.221 | 0.099 |
| 170 no augmentation | 170 | 0.447 | 0.468 | 0.317 | 0.106 |
| 170 + aux + no augmentation (seed 1, single run)* | 170 | 0.506 | 0.526 | 0.363 | 0.073 |
| MIREX-25 head | mirex25 | 0.335 | 0.341 | 0.292 | 0.036 |
| 277 head | 277 | 0.297 | 0.306 | 0.263 | 0.015 |
| 5 synthetic pretrain epochs | 170 | 0.271 | 0.279 | 0.171 | 0.091 |
| 10 synthetic pretrain epochs | 170 | 0.265 | 0.274 | 0.136 | 0.057 |

Artifacts: `docs/audit/amt/chord170_phase4_ablations.json`,
`docs/audit/amt/chord170_phase4_sweep_core.json`; checkpoints under
`/runs/chord170/sweeps/phase4-{core2,fix,finalists,*-aux}`.

### Winning configuration

**170-class chord + 13-class bass + root/quality auxiliary heads, no
augmentation.** The seed-1 single run reached exact 0.506 / WCSR-MIREX 0.526,
but the 3-seed protocol (below) puts the honest mean at **0.447 ± 0.017 exact
and 0.468 ± 0.016 WCSR-MIREX** — still the best configuration in the sweep and
far above the Phase 3 baseline (0.371 exact / 0.385 MIREX). Ablations show:
- Aux heads help consistently (+0.05–0.06 WCSR at either augmentation setting).
- The configured augmentation (pitch bin-roll ±3, gain, noise, SpecAugment)
  *hurts* at this data scale (−0.16 WCSR when enabled) — documented negative
  result; the augmentation class was fixed (space-aware bin roll) but remains
  off in the winner.
- Bass weight 0.5 is neutral-to-worse than 0.35 for WCSR (though it lifts bass
  accuracy slightly in validation).
- Vocabulary: 170 > MIREX-25 (+0.19 WCSR) and 170 > 277 (+0.22 WCSR) at equal
  budget — the 170-class set is the right size for this corpus.

### Seed protocol (finalists)

| Run | Epochs | Exact | WCSR-MIREX |
| --- | --- | ---: | ---: |
| no-augment seed 1 | 100 | 0.426 | 0.456 |
| no-augment seed 2 | 100 | 0.394 | 0.409 |
| no-augment seed 3 | 100 | 0.424 | 0.450 |
| **mean ± std** | | **0.415 ± 0.015** | **0.438 ± 0.021** |

Aux+no-augment, 3 seeds at 25 epochs (the winner protocol):

| Seed | Exact | 95% CI (exact) | Macro-F1 | WCSR-MIREX | ECE |
| --- | ---: | --- | ---: | ---: | ---: |
| 1 | 0.468 | [0.386, 0.556] | 0.327 | 0.471 | 0.091 |
| 2 | 0.447 | [0.359, 0.540] | 0.301 | 0.485 | 0.120 |
| 3 | 0.426 | [0.344, 0.518] | 0.328 | 0.447 | 0.121 |
| **mean ± std** | **0.447 ± 0.017** | | **0.319 ± 0.012** | **0.468 ± 0.016** | 0.091–0.121 |

Note the 100-epoch schedule underperforms the 25-epoch budget on this corpus
(cosine decay too slow for ~7.3k windows) and single runs vary by ~±0.04
exact — Phase 5 should use the 25-epoch schedule and the seed mean.

### Teacher comparison (MT3-template vs BTC)

Protocol: IDMT dataset4 (solo guitar) audio → BTC 170-class timeline;
MT3-template labels come from the stored W1 pseudo-labels; both scored
against the IDMT CSV annotations at the same window centres. Bootstrap 95%
CIs over tracks.

| Teacher | Tracks | Windows | Exact | 95% CI | Root | Majmin |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| MT3-template (W1) | 37 | 153 | 0.503 | [0.458, 0.612] | 0.549 | 0.549 |
| **BTC 170-class** | 37 | 153 | **0.752** | **[0.693, 0.859]** | **0.843** | **0.843** |

BTC is the clear teacher (+0.25 exact, non-overlapping CIs). The
MT3-template path is a documented negative result and explains the Phase 2
finding that W1 pseudo-labels were unusable. Artifact:
`docs/audit/amt/chord170_phase4_teacher_compare.json`.

### Separation / mix ablation — documented as not applicable here

The annotated corpora are solo-guitar (IDMT dataset4, GuitarSet mixes), so
“full mix vs guitar stem vs chord-oriented mix” collapses to the same signal;
a meaningful comparison needs *unlabeled* mixed tracks with a teacher. The
chord-oriented mix (bass + guitar + piano + other, vocals/drums removed) is
implemented in the plan and is the next relabeling job on GPU (BTC teacher +
Demucs), not measurable on the current annotated sets. Recorded as a
documented limitation, not silently skipped.

### Negative results (kept)

1. Presence gate / gated checkpoint selection (Phase 0).
2. MT3-template pseudo-labels as a teacher (−0.25 exact vs BTC).
3. Synthetic-only pretraining (5/10 epochs): −0.19 WCSR vs baseline; 30
   epochs excluded by the program constraint (not run).
4. Configured augmentation harms at this corpus size.
5. 100-epoch cosine budget underperforms 25 epochs on ~7.3k windows.


## Gate iteration (Stage A–C, 2026-11-16) — leakage correction and verdict

### Stage A: external splits + honest measurement

`scripts/make_external_splits.py` carves track-level, quality-stratified
holdouts from IDMT (103 train / 13 val / 13 test) and RWC (80 / 10 / 10),
keeps the GuitarSet player split, and excludes pseudo-labels that map to a
held-out IDMT track. `data/chord170/splits.json` is applied by the loader.

**Critical finding — earlier numbers were leaked.** The Phase 3/4 models
were trained before the split file existed, so they saw the now-held-out
IDMT/RWC tracks. Re-evaluating the Phase 4 winner on the corrected test gives
macro-F1 0.705 / exact 0.691 / bass 0.688 / slash 0.323 — but it memorized
those tracks. **All Phase 3/4 test numbers are superseded.**

Corrected test: 820 windows / 86 tracks (GuitarSet p05 324, RWC 409, IDMT 71,
EGSet12 16), 79 supported classes, zero leakage. Artifacts:
`docs/audit/amt/chord170_gates_{iteration1,splits}.json`; the Phase 2 dataset
card is regenerated from the new splits.

### Stage B–C: ablations (honest splits)

25 epochs (macro-F1 is supported-class on the external test):

| Variant | Macro-F1 | Exact | WCSR-MIREX | Bass (known) | Slash | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bass mask only | 0.152 | 0.316 | 0.412 | 0.349 | 0.045 | 0.170 |
| + inversion ×2 | 0.142 | 0.327 | 0.417 | 0.308 | 0.071 | 0.154 |
| + bass loss 1.0 | 0.150 | 0.326 | 0.401 | 0.336 | 0.026 | 0.154 |
| + rare-class weights | 0.142 | 0.313 | 0.389 | 0.332 | 0.065 | 0.157 |
| full augmentation | 0.087 | 0.257 | 0.334 | 0.363 | 0.039 | 0.043 |

60-epoch generalization variants (patience 6):

| Variant | Macro-F1 | Exact | WCSR-MIREX | Bass | Slash | ECE | RWC exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| early-stop, no aug | 0.127 | 0.274 | 0.365 | 0.336 | 0.039 | 0.173 | 0.115 |
| mild augmentation | 0.105 | 0.257 | 0.340 | 0.334 | 0.045 | 0.145 | 0.152 |
| feature standardization | 0.142 | 0.293 | 0.391 | 0.337 | 0.045 | 0.189 | 0.154 |
| mild aug + standardize | 0.026 | 0.118 | 0.149 | 0.157 | 0.013 | 0.013 | 0.103 |

Calibration (best variant): macro unchanged (0.138 → 0.138), **ECE 0.191 →
0.050**.

### Diagnosis

The dominant blocker is **cross-song generalization on RWC**: RWC *training*
macro-F1 is 0.828, held-out RWC macro-F1 is 0.044–0.050 (exact 0.115–0.174),
and training accuracy reaches 1.0. GuitarSet and IDMT transfer moderately
(0.43–0.52 exact); RWC does not. Bass masking lifts known-bass accuracy only
to ~0.35; slash stays ≤0.07. Calibration fixes confidence but not accuracy.

### Gate status after the cheap levers

| Gate | Target | Best honest result | Status |
| --- | ---: | ---: | --- |
| Macro-F1 (supported) | 0.45 | 0.152 | ❌ |
| Bass accuracy (known) | 0.60 | 0.349 | ❌ |
| Slash accuracy | 0.50 | 0.071 | ❌ |
| ECE | ≤0.15 | 0.050 (calibrated) | ✅ |

**Verdict:** cheap levers are exhausted. Meeting the gates requires the
data-expansion stage — BTC pseudo-labels on chord-oriented mixes of unlabeled
audio plus additional datasets (Slakh, SheetSage-Chord) — and/or a
generalization-focused modelling change. Production is untouched.

### Bugs fixed during the iteration

- `load_split` ignored the external split overrides (trained on leaked data).
- `ChordSequence.__getitem__` dropped the per-sample weight dict, so bass
  masking/inversion weighting/rare-class weighting were silently inert.
- The sweep's evaluation hardcoded the old narrow sources.


## Stage D — BTC pseudo-labels on chord mixes and the generalization ceiling (2026-11-16)

Pipeline built and run end-to-end:
`build_chord_mixes.py` (Demucs htdemucs_6s → bass+guitar+piano+other),
`btc_teacher.predict_frame_probs` (softmax confidences via
`output_projection`), `pseudo_label_btc.py` (confidence ≥0.6, ≥3 salient
chroma classes, bass from the separated bass stem, N cap 20 %, v2 schema).
Reusable Modal GPU entrypoints: `build_mixes`, `btc_pseudo` on a dedicated
audio image; TORCH_HOME cached on the data volume.

**Yield (264 YouTube 30 s clips):** 179 tracks yielded windows; **283 non-N
windows**, N rate 19.8 %, 247 known bass, 114 inversions, 6 qualities —
~4 % of the 6,405-window training set. Most clips are mostly silence/N, so
BTC confidence filtering removes the rest.

**A/B (external test, 25 epochs):**

| Variant | Macro-F1 | Exact | WCSR-MIREX | Bass | Slash | RWC exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| control | 0.142 | 0.327 | 0.417 | 0.308 | 0.071 | 0.169 |
| + BTC pseudo-labels | 0.131 | 0.302 | 0.391 | 0.332 | 0.039 | 0.154 |

No improvement — the pseudo set is too small.

Additional negative levers tested in the same iteration: **per-track feature
normalization** (exact 0.259, RWC 0.130) and per-track normalization + mild
augmentation (diverged, exact 0.076).

**Verdict:** the dominant blocker is the corpus size/diversity, not loss or
metric tuning. RWC train macro-F1 0.83 vs held-out 0.05 shows the model
memorizes songs. Closing the gates requires an order-of-magnitude increase in
*independent* songs (Slakh2100, SheetSage-Chord, larger unlabeled corpora via
the now-built Demucs+BTC pipeline) and/or a representation/architecture
change. Production remains untouched. Artifact:
`docs/audit/amt/chord170_stageD_report.json`.


## Context-length iteration (2026-11-17) — the generalization fix

Diagnosing the RWC held-out failure (train macro 0.83 vs held-out 0.05) showed
predictions were neighbouring chords from the same progression, not shifted:
the 12.8 s (128-frame) window averages several chords on fast harmonic-rhythm
material. Centre-cropping the existing windows to shorter contexts (no
re-extraction) was tested under the gates config (aux heads, masked bass +
inversion ×2, no augmentation):

| Context | Macro-F1 | Exact | WCSR-MIREX | Bass (known) | Slash | ECE | RWC exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 12.8 s (128, control) | 0.147 | 0.320 | 0.385 | 0.346 | 0.065 | 0.172 | 0.171 |
| 6.4 s (64) | 0.156 | 0.337 | 0.441 | 0.477 | 0.071 | 0.188 | 0.230 |
| 4.8 s (48) | 0.180 | 0.372 | 0.491 | 0.573 | 0.065 | 0.169 | 0.284 |
| 3.2 s (32) | 0.169 | 0.377 | 0.491 | **0.604** | 0.058 | 0.107 | 0.359 |
| 2.4 s (24) | 0.155 | 0.352 | 0.489 | 0.633 | 0.084 | 0.149 | 0.330 |
| **1.6 s (16)** | **0.190** | **0.373** | **0.501** | **0.688** | **0.103** | **0.145** | **0.399** |
| 0.8 s (8) | 0.188 | 0.370 | 0.513 | 0.704 | 0.077 | 0.190 | 0.428 |

**1.6 s + Slakh subset** (15,426 extra windows; 328/40/32 splits, 93 %
bass-known, includes minmaj7/hdim7): exact **0.396**, WCSR-MIREX **0.541**,
RWC exact **0.452**, bass 0.683. Adding rare-class weights (τ=0.3) gives
macro-F1 **0.201**. Calibration on the w16 model: **ECE 0.216 → 0.062**
(macro unchanged).

### Gate status after this iteration

| Gate | Target | Best honest | Status |
| --- | ---: | ---: | --- |
| Macro-F1 (supported) | 0.45 | 0.201 | ❌ |
| Bass accuracy (known) | 0.60 | 0.704 | ✅ |
| Slash accuracy | 0.50 | 0.103 | ❌ |
| ECE | ≤ 0.15 | 0.062 (calibrated) | ✅ |

Remaining blockers: macro-F1 over 79 supported classes (rare qualities still
weak) and slash (requires chord *and* bass exact on inversions). Natural next
levers: fine-hop feature extraction (1.6 s) for train+test, an exported
inversion auxiliary head with inversion-focused sampling, scaling Slakh to the
full redux set, and 3 seeds + 5-fold RWC/IDMT for CIs. Artifact:
`docs/audit/amt/chord170_context_report.json`. Production remains untouched.


## Fine-hop + inversion iteration (2026-11-18)

Built `extract_fine_windows.py` (1.6 s windows/hop for GuitarSet, EGSet12,
IDMT, RWC) and `prepare_slakh_fine` (Slakh subset at 1.6 s). Added an exported
inversion auxiliary head (root/first/second/third/other, weight 0.25),
inversion-weighted chord loss, head fusion and slash diagnostics.

Fixed external test (3,121 windows at the fine hop):

| Variant | Macro-F1 | Exact | WCSR-MIREX | Bass | Slash | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fine-inv (4 corpora + coarse Slakh) | 0.223 | 0.466 | 0.611 | 0.720 | 0.160 | 0.145 |
| fine-inv + rare weights | 0.209 | 0.455 | 0.606 | 0.712 | 0.140 | 0.142 |
| + Slakh fine + inversion chord weight 2 | 0.213 | 0.450 | 0.606 | 0.719 | 0.129 | 0.159 |
| + rare weights | 0.246 | 0.463 | 0.618 | 0.716 | 0.160 | 0.130 |
| **+ mild augmentation (25 ep)** | **0.266** | 0.440 | **0.629** | **0.761** | **0.168** | **0.065** |
| same config, 60 epochs | 0.264 | 0.440 | 0.610 | 0.745 | **0.184** | 0.110 |

The earlier "slash2" mild-augmentation variants accidentally also passed
`--no-augment` (making the flag inert and both runs identical); a corrected
mild-augmentation run is the best configuration so far, with validation
macro/slash still climbing at epoch 25 — a longer schedule is running.
Slash diagnostic on 642 inversion frames: chord exact 0.315, bass exact
0.530, both 0.151 — slash is gated by chord-quality accuracy on richer
chords, not by bass composition. Composing bass from the inversion head was
worse than the 13-class bass head (0.69 bass, 0.077 slash), and head fusion
reduced macro-F1 (0.246 → 0.222). Fine Slakh (61k windows) did not lift
external 6th/7th quality accuracy, indicating a domain gap between the
synthesized Slakh corpus and RWC/GuitarSet.

**Full Slakh scale-up (1,710 tracks, ~285k windows)** with the same recipe
gives the best honest result: macro-F1 **0.278**, exact 0.451, WCSR-MIREX
0.633, bass **0.773**, slash **0.182**, ECE 0.083 (val, which includes
in-domain Slakh val: 0.337 / 0.369). Selecting checkpoints on the *external* validation split only (excluding
Slakh val) was worse (test macro 0.239, slash 0.170) — the external val is
small and selection is noisy. Combined-val selection remains the better
protocol for now; k-fold/EMA checkpoint averaging is the next step.

**Gates:** bass 0.773 ✅, ECE 0.083 ✅, macro-F1 0.278 ❌, slash 0.182 ❌. Next levers: full Slakh redux (1,710 tracks), a
multi-scale model (local 1.6 s + global 6.4 s), a documented label-ambiguity
policy for 6th vs relative 7th chords, and 3 seeds + 5-fold evaluation.
A larger encoder (conv 96/192, LSTM 192, Dense 384; 40 epochs) raised
validation macro to 0.303 but left the external test unchanged (macro 0.264,
slash 0.159) — capacity is not the bottleneck. Bass-aware disambiguation of
identical pitch-class sets (C6 vs Am7) gained only +0.002 macro. Scaling
Slakh past 400 tracks requires a resumable full-tarball download; a `wget -c`
based `download_slakh_full` job is in place (48.7 GB, all 1,710 tracks).
Artifact: `docs/audit/amt/chord170_fine_inversion_report.json`.

## Frame supervision + real-guitar additions (2026-11-18)

`scripts/add_frame_labels.py` adds per-frame `frame_labels` / `frame_bass`
(N,16) to each fine npz using the stored `center_times` and the extractor
geometry `(k*hop - window//2 + i) * 0.1 s`; no CQT is recomputed. Sources:
timelines (GuitarSet/EGSet12/IDMT-d4/RWC/Guitar-TECHS), Slakh `all_src.mid`,
and IDMT dataset1 XML note events.

`extract_fine_windows.py` gained two real-guitar sources: Guitar-TECHS
(directinput condition, 68 split-assigned tracks / 6,056 windows) and IDMT
dataset1 chord recordings (88 tracks / 176 windows, deterministic hash
splits; dataset2/3 are technique/monophonic corpora and were not added).

`train_chord_170.py --frame-supervision` keeps the time axis through the
second BiLSTM, crops back to 16 frames after the circular pad, and applies
per-frame chord/bass/root/quality/inversion heads with masked per-frame
weights. Validation and evaluation reduce frame probabilities to window
level (mean by default, `--frame-aggregation center` optional).

Run `frame-fine` (40 epochs, best epoch 30 on combined val) external test:

| Aggregation | Macro-F1 | Exact | MIREX | Bass | Slash | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mean frames | 0.268 | 0.468 | 0.620 | 0.778 | 0.174 | 0.023 |
| Centre frame | 0.261 | 0.474 | 0.640 | 0.823 | 0.206 | 0.085 |

Across the 3,121-window external test, supported macro-F1 is 0.268/0.261,
below the window model's 0.278; centre-frame aggregation gives the best
exact/MIREX/bass/slash companions. Bass and ECE gates pass; macro-F1 and
slash do not. This is a documented negative result for frame supervision as
a route to the macro gate. Artifact:
`docs/audit/amt/chord170_frame_supervision.json`.

## Long-context transformer + structured heads (2026-11-19)

The fine cache (window = hop = 16) tiles CQT frames exactly, so
`scripts/chord_context.py` reconstructs 64-frame (6.4 s) contexts per
training window and per external-test window without re-extracting audio.
`train_chord_170.py` gains a BTC-style transformer (2 blocks, d_model 192,
per-frame heads) and a 12-class pitch head; `eval_chord_170.py` gains
context inference, centre-frame selection, `none/fuse/hybrid` structured
decoding, per-class support, and macro-F1 at minimum-support thresholds.

External fine test (3,121 windows, 86 tracks):

| Run / decode | Macro (supported) | Exact | MIREX | Bass | Slash | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 400-track Slakh subset, hybrid | 0.307 | 0.502 | 0.652 | 0.818 | 0.203 | 0.088 |
| Full data, plain head | 0.293 | 0.517 | 0.659 | 0.824 | 0.234 | 0.108 |
| Full data + guitar-only fine-tune, plain | **0.311** | **0.527** | **0.667** | **0.832** | 0.248 | 0.106 |
| Full data + guitar-only fine-tune, hybrid | 0.297 | 0.523 | 0.661 | **0.832** | **0.260** | 0.105 |
| Balanced Slakh subset, from scratch | 0.296 | 0.513 | 0.659 | 0.813 | 0.229 | **0.060** |
| Balanced subset + guitar fine-tune, hybrid | 0.304 | **0.525** | **0.669** | 0.826 | 0.237 | 0.063 |

This is the strongest iteration so far: +0.033 supported macro, +0.066 slash,
+0.076 exact, +0.034 WCSR-MIREX, and +0.059 bass versus `slakh-full-fine`.
Macro-F1 and slash still miss their gates; production remains untouched.

The macro gate is also a measurement problem: the 102 supported test classes
include 15 with one frame, 19 with 2–4, and 14 with 5–9. Macro over classes
with ≥10 frames is 0.444; over ≥20 frames it is 0.485 (passes 0.45).
Changing the reported gate to a minimum-support definition is a metric
decision and has not been made silently.

`scripts/build_slakh_subset.py` builds a deterministic 400-track Slakh subset
by greedy coverage of the 170 classes and inversion classes (320/40/40
splits, 62,835 windows, 115/170 classes) using hardlinks, no CQT recompute.
A from-scratch context model on guitar sources + this subset did not beat the
full-data + guitar-fine-tune recipe on macro/slash (0.296/0.229), but after
guitar fine-tuning it gave the best MIREX (0.669) and ECE (0.063), and macro
over classes with ≥20 frames reached 0.497. Artifact:
`docs/audit/amt/chord170_context_structured.json`.

## Phases 1–3: structured objective, seeds/SWA, ensembles (2026-11-20)

**Phase 1 — structured composition + CRF: negative.** Added a trainable
`StructuredChordComposition` head (presence × root × quality) and per-track
Viterbi smoothing. The composed decoder reaches exact 0.154 / MIREX 0.210;
the flat head after the same fine-tune remains at exact 0.527 / MIREX 0.667.
Viterbi over window predictions is neutral-to-negative (best exact 0.525 at
self-transition 0.05 versus 0.527 unsmoothed). Keep the flat chord head.

**Phase 2 — 96-frame / 3-block, 3 seeds + SWA.** Trained on guitar sources +
the quality-balanced Slakh subset. Seeds 1/2/3 reach macro 0.311/0.328/0.327,
exact 0.518/0.541/0.546, MIREX 0.657/0.669/0.675. Seed variance is ≈0.018
macro. Last-5 epoch weight averaging (SWA) is neutral.

**Phase 3 — ensembles: positive.** Averaging model probabilities is the most
reliable lever:

| Ensemble | Macro | Exact | MIREX | Bass | Slash | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Seed2-FT + seed3 | **0.351** | **0.570** | 0.688 | 0.822 | 0.224 | **0.022** |
| FT1 + seed2-FT | 0.345 | 0.563 | **0.689** | 0.829 | 0.245 | 0.027 |
| FT1 + balanced-FT | 0.320 | 0.544 | 0.677 | 0.830 | **0.266** | 0.033 |

Best macro/exact/MIREX/ECE: seed2-FT + seed3. Best slash: FT1 +
balanced-FT. Gates still fail for full 102-class macro (0.351 vs 0.45) and
slash (0.266 vs 0.50); bass and ECE pass. Minimum-support macro reaches
0.496 (≥10 frames) and 0.521 (≥20 frames).

**Phase 4 — synthetic rare-chord/inversion data.** `build_synthetic_chords.py`
renders 3,091 balanced guitar windows (110/170 classes, all 12 bass classes)
from Isophonics/Billboard/JAAH `.lab` annotations using additive synthesis and
the annotated bass for inversions. Fine-tuning seed2-FT with synthetic +
guitar data gives val macro 0.285 (0.272 without), external alone macro 0.325
/ exact 0.554 / MIREX 0.680. Ensembled with seed3: macro 0.351, exact
**0.575**, MIREX **0.691**, bass 0.826, slash 0.229, ECE **0.018**, macro
≥20 0.526. The gain is small but consistent; scale up synthetic windows and
class coverage before another gate run. JAAH is NC, so this corpus is
research-only. Artifact: `docs/audit/amt/chord170_phases_1_3.json`.

## Phase plan (remaining)

| Phase | Scope | Gate |
| --- | --- | --- |
| 2 | **Done** — see Phase 2 section above | Pseudo-label report (N ≤ 20% ✓), zero track overlap ✓, Modal cache ✓ |
| 3 | **Done** — see Phase 3 section. Pipeline + baseline trained/evaluated | ECE ✅; macro-F1/bass/slash ❌ (Phase 4 targets) |
| 4 | **Done** — see Phase 4 section. Winner: 170+aux+no-augment (0.526 WCSR-MIREX); BTC teacher 0.752 vs MT3 0.503 | Winning config + CIs; negative results documented |
| 5 | Distill + TFLite/ONNX export, FP16/INT8, latency, feature flag `HARMONIQ_CHORD_MODEL_V2=1`, registry/docs | Exported heads match evaluated heads; teacher drop ≤ 3pp |
| 6 | Correction loop (`backend/app/corrections_dataset.py` schema) | Corrections improve rare-class recall without degrading common classes |

## Verification

```bash
cd backend
.venv-wsl/bin/python -m pytest -q tests/test_chord_vocab_170.py tests/test_chord_labels_170.py
.venv-wsl/bin/python -m pytest -q tests/test_chord_eval_baseline.py
.venv-wsl/bin/python -m pytest -q tests/test_chord_frame_labels.py
.venv-wsl/bin/python -m pytest -q tests/test_chord_context.py
.venv-wsl/bin/python scripts/chord_data_v2.py data/guitarset --split test
```

Existing 277/25-class tests still pass (`test_chord_vocab.py`,
`test_real_label_vocab.py`, `test_student_vocab.py` re-run in Phase 1).
