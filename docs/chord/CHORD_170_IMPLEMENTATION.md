# Chord 170 Program — Implementation

Status: **Phase 0 + Phase 1 complete** (2026-11-15). Phases 2–6 pending
review before GPU training. Spec source: the "Harmoniq 170-Class Chord
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

## Phase plan (remaining)

| Phase | Scope | Gate |
| --- | --- | --- |
| 2 | Real + pseudo-label pipeline, chord-oriented mix, bass derivation, Modal CQT cache, track-level splits, dataset cards | Pseudo-label report: N ≤ 20%, no track overlap |
| 3 | `train_chord_170.py` + Modal entrypoint; 170 + bass model | ≥ v1.0.3 WCSR MIREX +5pp, ≥ v1.0.5 chord-head +8pp; macro-F1 ≥ 0.45; bass ≥ 0.60; slash ≥ 0.50; ECE ≤ 0.15 |
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
