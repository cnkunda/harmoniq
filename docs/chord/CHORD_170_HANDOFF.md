# Chord 170 — Session Handoff (2026-11-18)

This document captures the complete state of the 170-class chord model
program after the Phases 0–4 work and five gate-focused iterations
(leakage correction, Stage D pseudo-labels, context cropping, fine-hop +
inversions, full Slakh scale-up). It is written so a fresh session can
continue without re-deriving context.

**Production is untouched.** `backend/app/chord_inference.py`, the model
registry, and the feature flag are unchanged. Nothing ships until the gates
pass.

---

## 1. Current gate status (honest, external fine-hop test)

External test = GuitarSet p05 + EGSet12 + held-out IDMT + held-out RWC,
3,121 windows at 1.6 s hop (window 16 frames, hop 16 frames).

| Gate | Target | Best honest | Status |
| --- | ---: | ---: | --- |
| Macro-F1 (classes with support) | ≥ 0.45 | **0.359** | ❌ |
| Bass accuracy (known-bass frames) | ≥ 0.60 | **0.834** | ✅ |
| Slash accuracy (inversion frames) | ≥ 0.50 | **0.266** | ❌ |
| ECE (duration-weighted) | ≤ 0.15 | **0.0147** | ✅ |

Best macro/MIREX/ECE: cross-context ensemble of
`/runs/chord170/context-s96-b3-s2-ft-synth/best.keras` (96-frame) +
`/runs/chord170/context-s128-b4-s1/best.keras` (128-frame). Plain chord
head: macro **0.359**, exact 0.568, WCSR-MIREX **0.693**, bass 0.830,
slash 0.238, ECE **0.0147**. Best exact: synth seed2-FT + seed3 (96+96),
exact **0.575**. Best slash: FT1 + balanced-FT (64+64), macro 0.320,
slash **0.266**, exact 0.544, MIREX 0.677, ECE 0.0145. Best bass: the
three-context cross ensemble, 0.834. No checkpoint or ensemble passes all
four gates.

Support evidence for the macro definition: of 102 supported classes,
15 have one frame, 19 have 2–4, 14 have 5–9, 19 have 10–19, and 35 have
20+. Macro over classes with ≥10 frames is **0.444**; over ≥20 frames it is
**0.485** (passes 0.45). The full 102-class number is what the current gate
reports.

Progress across iterations (external test unless noted):

| Stage | Macro | Exact | MIREX | Bass | Slash | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Deployed 25-class model (Phase 0, GuitarSet p05 only) | 0.015 (F1) | 0.043 | — | — | — | — |
| Honest fine-baseline after leakage fix | 0.147 | 0.320 | 0.385 | 0.346 | 0.065 | 0.172 |
| Context 1.6 s | 0.190 | 0.373 | 0.501 | 0.688 | 0.103 | 0.145 |
| Fine-hop + inversion head | 0.246 | 0.463 | 0.618 | 0.716 | 0.160 | 0.130 |
| + corrected mild augmentation | 0.266 | 0.440 | 0.629 | 0.761 | 0.168 | 0.065 |
| Full Slakh fine (1,710 tracks) | **0.278** | **0.451** | **0.633** | **0.773** | **0.182** | 0.083 |
| Frame supervision + Guitar-TECHS/IDMT-d1 (mean frames) | 0.268 | 0.468 | 0.620 | 0.778 | 0.174 | **0.023** |
| Frame supervision + Guitar-TECHS/IDMT-d1 (centre frame) | 0.261 | **0.474** | **0.640** | **0.823** | **0.206** | 0.085 |
| Long-context 64 (400-track Slakh subset, hybrid decode) | 0.307 | 0.502 | 0.652 | 0.818 | 0.203 | 0.088 |
| Long-context 64, full data (plain head) | 0.293 | 0.517 | 0.659 | 0.824 | 0.234 | 0.108 |
| + guitar-only fine-tune (plain head) | **0.311** | **0.527** | **0.667** | **0.832** | 0.248 | 0.106 |
| + guitar-only fine-tune (hybrid decode) | 0.297 | 0.523 | 0.661 | **0.832** | **0.260** | 0.105 |
| Quality-balanced Slakh subset (from scratch, plain) | 0.296 | 0.513 | 0.659 | 0.813 | 0.229 | **0.060** |
| Balanced subset + guitar fine-tune (hybrid) | 0.304 | **0.525** | **0.669** | 0.826 | 0.237 | **0.063** |
| 96-frame / 3-block seed 2 (guitar+balanced Slakh) | 0.328 | 0.541 | 0.669 | 0.811 | 0.224 | 0.048 |
| Seed 2 guitar FT + seed 3 ensemble | **0.351** | **0.570** | **0.688** | 0.822 | 0.224 | **0.022** |
| FT1 + balanced-FT ensemble (best slash) | 0.320 | 0.544 | 0.677 | 0.830 | **0.266** | 0.033 |
| FT1 + seed2-FT ensemble | 0.345 | 0.563 | **0.689** | 0.829 | 0.245 | 0.027 |
| Synthetic-FT seed2 + seed3 ensemble | 0.351 | **0.575** | **0.691** | 0.826 | 0.229 | **0.018** |
| Synthetic scale-up (6,764 windows) + seed3 | **0.353** | 0.565 | 0.683 | 0.827 | 0.227 | 0.027 |

---

## 2. What has been built (by phase)

### Phase 0 — baselines and provenance (`034f4c0`)
- `backend/scripts/eval_chord_baseline.py` + tests: reproducible MIREX-25
  harness on GuitarSet player-05.
- Findings: the shipped `app/chord_model.keras` is the **25-class Commit 148
  multi-task model** (chord 25 / root 13 / presence 1), not the
  registry-claimed v1.0.3 (277-class). Presence gate is a no-op at test time;
  v1.0.5 damage was selection on a non-exported head.
- `DualValidationLogger` fixed: header changes rotate the CSV instead of
  truncating; latent `_SCRIPTS_DIR` NameError fixed.
- Report: `docs/chord/CHORD_170_PHASE0_BASELINE.md`.

### Phase 1 — vocabulary (`c03f645`)
- `backend/app/chord_vocab_170.py`: 12 roots × 14 qualities + N + X = 170;
  13-class bass vocab (X = unknown); compose/parse/render slash labels;
  explicit tested 277→170 map (9/11/13→7, maj9→maj7, min9→min7, altered→7,
  7sus4→sus4, 6→maj6); `minmaj7`/`hdim7` have no 277 source.
- Tests: `test_chord_vocab_170.py`, `test_chord_labels_170.py`.

### Phase 2 — data pipeline (`51401fc`, `3665f6c`, `37ceae1`)
- `backend/app/chord_labels.py`: bass from lowest active note; Harte/shorthand
  annotation parsing (degrees, slash pitch classes); quality normalization.
- `backend/scripts/chord_data_v2.py`: real-dataset label+bass sidecars
  (`processed/chord170/*.npz`), pseudo-label v2 rebuild, dataset cards,
  leakage checks, split overrides, feature standardization, per-track
  normalization, crop windows, sample-weight helpers.
- `backend/scripts/btc_teacher.py`: BTC 170-class teacher; verified bijection
  (BTC layout `root*14+q`, 168=X, 169=N); frame probabilities via
  `output_layer.output_projection` softmax; direct torch+librosa inference.
- `backend/scripts/modal_chord_170.py`: Modal app (see §6).
- Pseudo-labels: W1 MT3 labels unusable under spec filters (25 windows);
  BTC teacher verdict in Phase 4.
- Modal prepare: CQT caches + sidecars for GuitarSet 360, EGSet12 12,
  Guitar-TECHS 68, IDMT 129, RWC 100; splits + card.

### Phase 3 — model and training (`793ac64`)
- `backend/scripts/train_chord_170.py`: v1.0.3 encoder + 170 chord + 13 bass
  (+ optional root 13, quality 15, inversion 5) heads; temperature
  resampling, source balancing, augmentation (pitch bin-roll with label/bass
  remap, gain, noise, SpecAugment; none/mild/full), AdamW+cosine, grad
  clipping, mixed precision with CPU fallback below compute capability 7.0;
  checkpoint selection on a supported-macro metric; fixed-header CSV logs.
- `backend/scripts/eval_chord_170.py`: mir_eval WCSR (root..mirex), macro-F1
  (native + supported), per-quality, bass/slash (with inversion breakdown),
  top-k, duration-weighted ECE, per-source/per-track aggregation, bootstrap
  CIs, calibration, head fusion, bass-aware disambiguation.
- `backend/configs/chord170_base.yaml`, `chord170_gates.yaml`.
- Bugs fixed: pitch-shift rolled 24 bins/semitone instead of 2 (12× label
  noise); tf_keras 2.20 pin; torch in the TF image clobbered cuDNN; GPU
  compute-capability fallback; checkpoint `InputLayer.optional` compat.

### Phase 4 — ablations and teacher comparison (`8e048d0`, `b2d9d16`)
- Labels spaces 170/277/MIREX-25, aux heads, bass weight, augmentation,
  synthetic pretraining, gate-aligned selection.
- **Teacher comparison (IDMT dataset4, 37 tracks/153 windows): BTC 0.752
  exact [0.693, 0.859] vs MT3-template 0.503 [0.458, 0.612]** — BTC is the
  clear teacher; MT3-template is a documented negative result.
- Ablations: 170 > 277 > 25; aux heads help; synthetic pretraining hurts
  (30 epochs excluded by the program constraint); augmentation initially hurt.

### Gate iteration — Stage A/B/C (`0e62c61`)
- **Critical finding: Phase 3/4 test numbers were leaked** (no IDMT/RWC
  external holdout existed; models had seen the now-held-out tracks). All
  superseded.
- `backend/scripts/make_external_splits.py`: track-level quality-stratified
  holdouts — IDMT 103/13/13, RWC 80/10/10; pseudo-label leakage exclusion;
  `data/chord170/splits.json`; zero overlap (train 6,405 / val 868 / test 820).
- Bass X masking, inversion oversampling, rare-class weighting, gate-aligned
  selection, calibration (`calibrate_chord_170.py`: temperature + prior; ECE
  0.191→0.050), per-track normalization.
- Honest results: macro 0.15, bass 0.35, slash 0.07; diagnosis: cross-song
  generalization (RWC train macro 0.83 vs held-out 0.05).
- Bugs fixed: `load_split` ignored split overrides; `ChordSequence` dropped
  the per-sample weight dict (masking was inert); sweep eval sources
  hardcoded.

### Stage D — pseudo-labels on chord mixes (`aa52ad1`)
- `build_chord_mixes.py` (Demucs htdemucs_6s → bass+guitar+piano+other;
  keeps bass/guitar stems), `btc_teacher.predict_frame_probs`,
  `pseudo_label_btc.py` (confidence ≥0.6, ≥3 salient chroma classes, bass
  from separated bass stem, N cap 20%, v2 schema).
- Yield: 264 YouTube clips → 179 tracks / 283 windows (N 19.8%, 247 known
  bass, 114 inversions) — too small to move metrics (A/B negative).

### Context iteration (`7479c45`)
- Root cause of the RWC failure: 12.8 s windows average multiple chords on
  fast harmonic rhythm. Centre-cropping existing windows (no re-extraction)
  fixed generalization: 1.6 s windows → macro 0.190, exact 0.373, MIREX
  0.501, bass 0.688, slash 0.103, ECE 0.145.
- Slakh subset (400 tracks / 15,426 windows) + crop → MIREX 0.541.

### Fine-hop + inversion iteration (`9bd450f`, `8b0d883`, `ca7abb2`)
- `extract_fine_windows.py`: 1.6 s windows/hop for GuitarSet/EGSet12/IDMT/RWC
  (RWC fine: 15,184 windows, N 2.2 %).
- `prepare_slakh_fine`: Slakh subset at 1.6 s (61,113 windows, N 23.7 %,
  bass known 93.8 %, rare qualities).
- Exported inversion head (root/first/second/third/other) + inversion-weighted
  chord loss; slash diagnostics; head fusion (negative).
- Results: macro 0.246, exact 0.463, MIREX 0.618, bass 0.716, slash 0.160,
  ECE 0.130. Corrected mild augmentation: macro 0.266, bass 0.761, slash
  0.168, ECE 0.065. 60 epochs: slash 0.184.

### Phases 1–3: structured objective, seeds/SWA, ensembles (2026-11-20)
- **Phase 1 — structured objective + CRF: negative.** A root × quality ×
  presence composition head (`StructuredChordComposition`) trained jointly
  with the flat head decodes poorly (exact 0.154, MIREX 0.210); the flat head
  after the same fine-tune is unchanged (exact 0.527, MIREX 0.667). Viterbi
  smoothing over window predictions is neutral-to-negative (best at
  self-transition 0.05: exact 0.525, MIREX 0.661 vs 0.527/0.667 unsmoothed).
- **Phase 2 — 96-frame / 3-block, 3 seeds + SWA.** On guitar + balanced Slakh
  (80 % of 400 tracks): seed macro 0.311/0.328/0.327, exact
  0.518/0.541/0.546, MIREX 0.657/0.669/0.675. Seed variance ≈0.018 macro.
  SWA (last-5 epoch weight average) is neutral. Seed 2 is best macro; seed 3
  best exact/MIREX.
- **Phase 3 — ensembles: positive.** Seed 2 guitar-FT + seed 3: macro
  **0.351**, exact **0.570**, MIREX **0.688**, ECE **0.022**. FT1 + balanced
  FT: slash **0.266**, macro 0.320, exact 0.544, MIREX 0.677, ECE 0.033.
  FT1 + seed2-FT: macro 0.345, exact 0.563, MIREX **0.689**, slash 0.245.
- Post-hoc prior calibration and 3-model ensembles are negative; see §3
  items 16–17. Best finalists remain synth-s2ft+seed3 (macro/exact/MIREX/ECE)
  and FT1+balancedFT (slash).
- Evidence: `docs/audit/amt/chord170_phases_1_3.json`.

### Phase 4 — synthetic rare-chord/inversion data (2026-11-20)
- `scripts/build_synthetic_chords.py` renders a balanced synthetic guitar
  corpus from the local Isophonics/Billboard/JAAH `.lab` annotations:
  additive guitar-like plucks, inversions from the annotated bass, 1.6 s CQT
  windows. 26,380 candidate segments → 3,091 windows (2,765/173/153),
  110/170 classes, all 12 bass classes. JAAH is NC, so this corpus is
  research-only.
- Fine-tuning seed2-FT with guitar sources + synthetic (6 epochs) gives
  val macro 0.285 (up from 0.272); external alone macro 0.325 / exact 0.554
  / MIREX 0.680. Ensembled with seed3: macro **0.351**, exact **0.575**,
  MIREX **0.691**, bass 0.826, slash 0.229, ECE **0.018**, macro ≥10 0.500,
  macro ≥20 0.526.
- Delta vs the no-synthetic ensemble is small but consistent: exact +0.004,
  MIREX +0.004, ECE −0.004, bass +0.004, slash +0.005, macro flat.
- Scale-up (6,764 windows, multi-window rendering, 2× synthetic sampling):
  macro 0.353 (+0.002) but exact 0.565 (−0.009), MIREX 0.683 (−0.009),
  ECE 0.027 (+0.009). Not a reliable win; stop adding windows and change the
  synthetic timbre/domain or source instead. The 3,091-window corpus is the
  better finalist for exact/MIREX/ECE; the 6,764-window run is the macro
  point estimate.

### Phase 4c — context capacity and cross-context ensembles (2026-11-20)
- 128-frame / 4-block, 3 seeds on guitar + balanced Slakh: external macro
  0.322 / 0.306 / 0.297 — worse than 96-frame despite higher val macro.
  Context/capacity is saturated past 96 frames.
- Cross-context diversity is positive: synth seed2-FT (96) + seed1 (128)
  gives macro **0.359**, exact 0.568, MIREX **0.693**, bass 0.830, slash
  0.238, ECE **0.0147**. Adding FT1 (64) as a third context lowers macro to
  0.342 but raises slash to 0.255 and bass to **0.834**.
- Evidence: `docs/audit/amt/chord170_phases_1_3.json`.

### Phase 4d — pretrained MuQ encoder (2026-11-24, negative)
- Added `extract_muq_features.py`, a MuQ Modal image, `prepare_muq`, and
  `muq_*` sources. Pipeline: 24 kHz audio → MuQ hidden state → 25→10 Hz
  resample → fixed Gaussian projection 1024→128 → 16-frame windows.
- MuQ layer 6: best val supported macro **0.076**. MuQ layer 2: **0.194**.
  CQT guitar-only baseline (same 96/3 recipe): val macro **0.289**, external
  macro 0.318 / exact 0.532 / MIREX 0.671 / slash 0.218 / ECE 0.085.
- Verdict: MuQ representations do not transfer in this pipeline; lower layers
  help but remain far below CQT. MuQ weights are CC-BY-NC 4.0, research-only.
  Do not scale MuQ without a different adaptation/probing/domain-alignment
  strategy.
- Added `aug-level=gain` (no CQT bin roll) and dynamic feature-dim support so
  non-CQT features can be tested without corrupting pitch-shift augmentation.
- Evidence: `docs/audit/amt/chord170_phases_1_3.json`.

### Phase 4e — real guitar-only baseline and ensembles (2026-11-24)
- CQT guitar-only baseline (no Slakh/synthetic): val macro 0.289, external
  macro 0.318 / exact 0.532 / MIREX 0.671 / slash 0.218 / ECE 0.085.
- Adding it to the two-context finalist: macro 0.3541, exact **0.5755**,
  MIREX **0.6988**, slash 0.240, ECE 0.0162. Best exact/MIREX; lower macro
  than the 0.359 two-model finalist. Synthetic fine-tuning of the guitar-only
  model is negative (val 0.289→0.266).
- Verdict: CQT ensembles are saturated. Best macro 0.359; best slash 0.266.
  Closing the gates needs more real guitar data (GOAT access) or a
  research-grade representation/adaptation change, not more CQT ensembles.

### Long-context + structured heads (`472ca8f`)
- `scripts/chord_context.py` reconstructs arbitrary-length contexts from the
  contiguous fine windows (window = hop = 16) and provides pitch-target and
  structured-decode helpers. No CQT was recomputed.
- `train_chord_170.py --context-frames 64 --context-blocks 2 --structured-heads`
  builds a BTC-style transformer over 64 frames (6.4 s) with per-frame
  chord/bass/root/quality/inversion heads plus a 12-class sigmoid pitch head.
- `eval_chord_170.py --context-frames 64 --structured-decode {none,fuse,hybrid}`
  runs context inference, selects the centre frame, and reports per-class
  support plus macro-F1 at minimum-support thresholds.
- Full-data run (`context-full-s64`): 30 epochs, best epoch 28, val supported
  macro 0.393, test macro 0.293 / exact 0.517 / MIREX 0.659 / bass 0.824 /
  slash 0.234 / ECE 0.108.
- Guitar-only fine-tune (`context-full-s64-guitarft`, 6 epochs, lr 2e-4,
  all non-Slakh sources): test macro **0.311** / exact **0.527** / MIREX
  **0.667** / bass **0.832** / slash 0.248 / ECE 0.106; hybrid decode slash
  **0.260**, macro 0.297. A second fine-tune (`guitarft2`) did not improve.
- Balanced-subset follow-up (`build_slakh_subset.py`, `context-s64-guitar-bal`):
  guitar sources + 400 Slakh tracks chosen by greedy 170-class/inversion
  coverage (320/40/40 splits, 62,835 windows, 115/170 classes). From
  scratch it reached macro 0.296 / exact 0.513 / MIREX 0.659 / bass 0.813 /
  slash 0.229 / ECE 0.060. Fine-tuning it on guitar sources gave macro
  0.305 / exact 0.525 / MIREX **0.669** / bass 0.826 / slash 0.237 / ECE
  **0.063**, with macro over classes with ≥20 frames **0.497**. This did
  not beat full-data pretraining + guitar fine-tuning on macro/slash, but it
  is the best MIREX/ECE/high-support-macro configuration.
- Evidence: `docs/audit/amt/chord170_context_structured.json`.

### Frame supervision + real-data additions (`d43253e`, `178014b`, `941c7da`, `88522c0`)
- `scripts/add_frame_labels.py` writes `frame_labels` / `frame_bass` (N,16)
  into every fine npz from timelines, MIDI notes, or IDMT XML events.
- `extract_fine_windows.py` now also prepares Guitar-TECHS (directinput, 68
  tracks / 6,056 windows) and IDMT dataset1 chord recordings (88 tracks /
  176 windows, hash splits). Training sources: `guitar_techs_fine`,
  `idmt_chords_fine`.
- `train_chord_170.py --frame-supervision`: second BiLSTM keeps the time
  axis (cropped back to 16 after circular padding), per-frame chord/bass/
  root/quality/inversion heads, per-frame masked weights; validation and
  eval aggregate frame probabilities.
- External test, 40 epochs, combined val selection (best epoch 30):
  mean-frame macro 0.268 / exact 0.468 / MIREX 0.620 / bass 0.778 /
  slash 0.174 / ECE 0.023; centre-frame macro 0.261 / exact 0.474 /
  MIREX 0.640 / bass 0.823 / slash 0.206 / ECE 0.085.
- Verdict: frame supervision + the new real guitar data does **not** close
  macro-F1 or slash. It improves exact/MIREX/bass/slash under centre-frame
  aggregation, but supported macro falls below the window model. Evidence:
  `docs/audit/amt/chord170_frame_supervision.json`.

### Full Slakh scale-up (`2a590a5`, `fb374b0`, `40a0c67`)
- `download_slakh_full` (resumable `wget -c`, 48.7 GB) → all **1,710 tracks**
  (mix.flac + MIDI) on the data volume; `prepare_slakh_scaled` built coarse
  and fine CQT for all 1,710 (~285k fine windows).
- Full-Slakh training (mild aug, inversion head, rare weights, chord-inversion
  weight 2): external macro **0.278**, exact 0.451, MIREX 0.633, bass 0.773,
  slash 0.182, ECE 0.083; val (includes in-domain Slakh val) 0.337/0.369.
- External-val-only selection was noisier (test macro 0.239, slash 0.170);
  combined-val selection stays. `--val-sources` option exists.
- Large encoder (conv 96/192, LSTM 192, Dense 384): val 0.303 but test
  unchanged → capacity is not the bottleneck.
- Bass-aware disambiguation (C6 ≡ Am7): +0.002 macro (kept as an option).

---

## 3. Documented negative results (do not redo blindly)

1. Presence gate / checkpoint selection on unexported heads (Phase 0).
2. MT3-template pseudo-labels as teacher (−0.25 exact vs BTC).
3. Synthetic-only pretraining 5/10 epochs (worse); 30 excluded by constraint.
4. Full augmentation (pitch ±3 + SpecAugment) at small data scale (worse).
5. Bass composition from the inversion head (worse than the 13-class head).
6. Root/quality head fusion at inference (macro 0.246→0.222, ECE worse).
7. Per-track feature normalization (exact 0.259), global standardization
   (marginal), mild aug + standardization (diverged).
8. External-val-only checkpoint selection (noisy, worse).
9. Larger encoder (capacity not the bottleneck).
10. BTC pseudo-labels on 264 30 s YouTube clips (283 windows, no gain).
11. 25-class and 277-class heads lose to 170 at equal budget.
12. Note: "slash2" variants accidentally passed both `--no-augment` and
    `--aug-level mild` → augmentation was off and the two runs were
    identical. Corrected mild aug (25 ep) is the best base configuration.
13. Frame-level supervision (+ Guitar-TECHS/IDMT-dataset1 fine data) did not
    improve supported macro-F1 or slash: 0.268/0.174 mean-frame and
    0.261/0.206 centre-frame vs 0.278/0.182 for the window model. It is the
    best exact/MIREX/bass configuration with centre-frame aggregation.
    Do not re-run as-is; the remaining gap is label/class imbalance and
    cross-corpus generalization, not temporal resolution.
14. Root × quality × presence composition as the primary chord decoder
    (exact 0.154) and Viterbi smoothing over window predictions (exact 0.525
    at best vs 0.527) are negative. Keep the flat chord head; structured
    auxiliary heads are useful only for diagnostics/ensembling.
15. SWA/last-5 checkpoint averaging was neutral for the 96-frame seeds.
    Seed ensembling is the reliable selection lever (+0.023 macro, +0.029
    exact, +0.019 MIREX over the best single seed).
16. Post-hoc temperature/prior calibration fitted on guitar val overfits:
    synth ensemble macro 0.351→0.317 and ECE 0.018→0.192. Only the
    temperature-only FT1+balancedFT calibration is harmless (ECE 0.0145,
    macro/slash unchanged). Do not use prior calibration for the macro gate.
17. Three-model ensembles dilute the best pair: s1+s2+s3 macro 0.348,
    synth+s2+s3 0.346, FT1+balancedFT+s2ft 0.342, all below the two-model
    finalist (0.351). Keep two-model finalists.
18. Scaling the synthetic corpus 3,091→6,764 windows raised macro +0.002 but
    cost exact −0.009 / MIREX −0.009 / ECE +0.009. Do not just add windows.
19. 128-frame / 4-block is worse than 96-frame / 3-block (macro 0.322/0.306/
    0.297 vs 0.328/0.327); context/capacity is saturated. Cross-context
    ensembling (96 + 128) is the useful part, not the longer model alone.
20. MuQ (layer 6/2) as a direct CQT replacement is negative: val macro
    0.076/0.194 vs CQT guitar-only 0.289. MuQ features likely encode
    track/timbre identity; do not scale without domain adaptation.
21. Synthetic fine-tuning of the guitar-only model hurts val macro
    (0.289→0.266). Adding the guitar-only model as a third ensemble member
    improves exact/MIREX (0.576/0.699) but lowers macro (0.354 vs 0.359).
    The CQT ensemble is saturated.

---

## 4. Data inventory (Modal volumes)

### `harmoniq-chord170-data` (mounted at `/chord170`)
- `/chord170/backend/...`: code bundle (app, scripts, configs) — **re-upload
  after code changes** (`modal volume put -f ... app /backend/` and
  `scripts /backend/`).
- Real corpora (coarse 6.4 s hop): GuitarSet 360, EGSet12 12, Guitar-TECHS 68,
  IDMT dataset4 129, RWC 100; sidecars under `processed/chord170/`.
- Fine (1.6 s) corpora: `data/chord170/fine/{guitarset,egset12,
  idmt_smt_guitar,rwc,guitar_techs,idmt_chords}` (RWC 15,184; Guitar-TECHS
  6,056; IDMT-d1 176 windows). All fine npz files now carry per-frame
  `frame_labels` / `frame_bass` (Slakh 266,870 windows included).
- Slakh: `data/chord170/slakh_raw` (1,710 tracks: mix.flac + all_src.mid),
  `data/chord170/slakh` (coarse 1,710), `data/chord170/slakh_fine`
  (1,710; ~260k windows).
- Pseudo: `data/chord170/chord_mix` (264), `data/chord170/pseudo_btc`
  (179 tracks/283 windows), `data/pseudo_label/w1` (original W1).
- `data/chord170/splits.json` (external splits), reports
  (`chord170_phase2_dataset.json`, `slakh_report.json`, etc.).
- `.cache/slakh2100_redux_16k.tar.gz` (48.7 GB archive).

### `harmoniq-chord170-runs` (mounted at `/runs`)
- `/runs/chord170/sweeps/<tag>/<variant>/{best.keras,final.keras,metrics.json,
  training_log.csv,eval_test.json,config.json,confusion.npy,per_class.json}`
- Best: `/runs/chord170/slakh-full-fine/best.keras`.
- Also `mildaug-fine`, `mildaug-fine-60`, `large-fine`,
  `slakh-full-fine-extval`, sweeps `context-*`, `fine-*`, `slash-*`,
  `inversion-*`, `stageD-*`, `stageE-*`, `gates-*`.

---

## 5. Repository state

Commits (newest first): `40a0c67`, `2a590a5`, `fb374b0`, `b3c4e1b`,
`ca7abb2`, `8b0d883`, `9bd450f`, `7479c45`, `aa52ad1`, `0e62c61`,
`b2d9d16`, `8e048d0`, `793ac64`, `37ceae1`, `3665f6c`, `51401fc`,
`c03f645`, `034f4c0`; plus the user's `1612e77` checkpoint before Phase 0.

- `backend/research/h-gain-v1.0.3/chord_model.tflite` is **intentionally
  untracked** (machine-local archive restore).
- The working tree contains **unrelated edits** (AGENTS.md, README.md,
  frontend components, `backend/app/music_generation/providers.py`,
  `package.json`, a stray `backend/=0.12.0` deletion) that must NOT be
  staged with chord170 work.
- Tests: 148 chord-suite tests passing (vocab, labels, eval, splits,
  calibration, baseline). Full backend suite was green earlier (1,904 passed).
- `npm run lint` (tsc) passes.

---

## 6. Modal infrastructure

App: `backend/scripts/modal_chord_170.py` (name `harmoniq-chord170`).
Images:
- TF training image: `tensorflow/tensorflow:2.20.0-gpu`, pinned
  `tf_keras==2.20.0`, **no torch** (torch clobbers cuDNN), pydantic, pyyaml,
  mir_eval, pretty_midi, etc.
- `btc_image`: Debian + CPU torch + librosa/soundfile.
- `audio_image`: Debian + GPU torch/torchaudio + demucs + librosa +
  pretty_midi + wget + scipy.

Functions: `prepare`, `prepare_fine`, `prepare_slakh` (stream/extract),
`prepare_slakh_fine`, `prepare_slakh_scaled` (coarse+fine), 
`download_slakh_full` (resumable), `build_mixes`, `btc_pseudo`, `train`,
`eval_model`, `calibrate`, `sweep` (suites: core, fix, finalists,
finalists_aux, gates, gates_finalists, generalization, normalize, context,
context2, context3, stageD, stageE, inversion, fine, slash, slash2), `status`,
`ls`.

Typical commands (from `backend/`):

```bash
modal volume put -f harmoniq-chord170-data app /backend/
modal volume put -f harmoniq-chord170-data scripts /backend/
modal run --detach scripts/modal_chord_170.py::train \
  --run-name X --config configs/chord170_gates.yaml \
  --extra-args "--aux-heads --inversion-head --crop-window 16 --batch-size 128 \
  --chord-inversion-weight 2.0 --chord-class-weight-tau 0.3 --aug-level mild \
  --epochs 40 --sources guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine,slakh_fine"
modal run scripts/modal_chord_170.py::eval_model \
  --checkpoint /runs/chord170/X/best.keras --split test \
  --sources guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine \
  --crop-window 16 --out /runs/chord170/X/eval_test.json
```

---

## 7. Key file map

| File | Purpose |
| --- | --- |
| `app/chord_vocab_170.py` | 170 vocab, bass vocab, 277→170 map, 170→25 map |
| `app/chord_labels.py` | bass/annotation logic, inversion class/composition, pitch-shift |
| `scripts/chord_data_v2.py` | loaders, sidecars, splits, sampling weights, dataset cards |
| `scripts/train_chord_170.py` | model, sequence, augmentation, training, callbacks |
| `scripts/eval_chord_170.py` | metrics, WCSR, bass/slash, ECE, CIs, calibration, fusion, disambiguation |
| `scripts/calibrate_chord_170.py` | temperature + prior fitting |
| `scripts/make_external_splits.py` | external gate splits |
| `scripts/btc_teacher.py` | BTC teacher + frame probabilities |
| `scripts/build_chord_mixes.py` | Demucs chord-oriented mixes |
| `scripts/pseudo_label_btc.py` | BTC pseudo-labels on mixes |
| `scripts/prepare_slakh.py` | Slakh MIDI→labels, CQT windows (coarse/fine) |
| `scripts/extract_fine_windows.py` | 1.6 s windows for GuitarSet/EGSet12/IDMT/RWC/Guitar-TECHS/IDMT-d1 |
| `scripts/add_frame_labels.py` | per-frame chord/bass labels in the fine npz (no CQT recompute) |
| `scripts/chord_context.py` | long-context slicing, pitch targets, structured decoding |
| `scripts/build_slakh_subset.py` | quality-balanced Slakh fine subset (hardlinks, no CQT recompute) |
| `scripts/eval_chord_baseline.py` | Phase 0 harness (25-class baseline) |
| `scripts/compare_teachers.py` | MT3-template vs BTC on IDMT |
| `scripts/modal_chord_170.py` | Modal app |
| `configs/chord170_base.yaml`, `configs/chord170_gates.yaml` | training configs |
| `docs/chord/CHORD_170_IMPLEMENTATION.md` | full program log |
| `docs/audit/amt/chord170_*.json` | all metrics/artifacts |

---

## 8. Traps and gotchas (learned the hard way)

1. **Leakage**: always pass `source=` to `load_dataset_dir_170`; external
   splits live in `data/chord170/splits.json`. Slakh/fine/pseudo sources use
   their npz splits.
2. **Evaluation set for fine models**: fixed external fine4
   (`guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine`); never
   include Slakh test in the gate test.
3. **`--no-augment` overrides `--aug-level`**: to test augmentation, omit
   `--no-augment` and set `--aug-level mild`.
4. **Crop window**: models trained on fine features are already 16 frames;
   eval must pass `--crop-window` matching the run config (the sweep does it
   automatically; manual `eval_model` needs it).
5. **`ChordSequence` must return `(features, targets, weights)`** — dropping
   the third element silently disables masking/inversion/rare weighting.
6. **`eval_chord_170.py` `if __name__ == "__main__":` must stay at the end**
   (functions appended after it are not defined when run as a script).
7. **tf_keras pin 2.20.0**; newer checkpoints carry `softmax_robust_masking`
   and older ones `InputLayer.optional` (compat patch exists in
   `eval_chord_baseline.keras_config_compat_copy`).
8. **Never install torch into the TF image** (cuDNN conflict).
9. WSL GPU (cc 6.1) cannot run mixed-precision LSTM init → CPU; Modal A10G
   is fine.
10. **Zenodo streaming stalls**: use `download_slakh_full` (`wget -c`), not
    the streaming extractor, for large downloads.
11. **Label ambiguity**: maj6 ≡ relative min7 (identical pitch-class sets);
    macro-F1 is capped by this. Bass-aware disambiguation helps only ~0.002.
12. **Rare classes** (minmaj7, hdim7, min6) remain weak; macro-F1 is over
    classes with support (~79 on the external test).
13. **Checkpoint selection noise**: combined val (incl. Slakh val) currently
    beats external-only val; consider EMA/k-fold averaging.
14. Pseudo v2 / W1 labels are not usable (25 windows); BTC pseudo on 30 s
    clips is small.

---

## 9. Remaining program phases

### Phase 5 — Distillation and deployment (blocked on gates)
- Distil the winning teacher to a CPU student; export **TFLite and ONNX with
  chord + bass (+ aux) heads**; verify exported tensors match evaluated heads.
- FP16/INT8 comparison; CPU latency report.
- Feature flag `HARMONIQ_CHORD_MODEL_V2=1` in `chord_inference.py`.
- Update `backend/app/model_registry.json`, `docs/MODEL_PROVENANCE.md`,
  `docs/EVALUATION.md` only after validation.

### Phase 6 — Correction loop
- Use `backend/app/corrections_dataset.py`; store audio hash, chord event,
  original/corrected label, user, timestamp, confidence.
- Correction-weighted training; held-out correction evaluation; rare-class
  recall without common-class regression; privacy/licensing notes.

### Gate-closing work (priority)
1. Frame-level supervision.
2. More real annotated data (Guitar-TECHS fine, IDMT datasets 1–3 XML).
3. Checkpoint averaging / k-fold; 3 seeds; CIs.
4. Only then Phase 5/6.

---

## 10. Next actions (concrete)

### Done: frame supervision and real-data additions (see §2)
- `add_frame_labels.py` is implemented and run for all fine sources.
- `--frame-supervision` is implemented; run `frame-fine` is the reference.
- Guitar-TECHS (68 tracks) and IDMT dataset1 (88 chord tracks) are in the
  fine pipeline; dataset2/3 are technique/monophonic corpora and were not
  added (dataset3's 5 polyphonic pieces could be added later).

### A. Ceiling evidence
Macro-F1 is over 102 supported classes on 3,121 external windows. Support is
highly skewed: 15 classes have one frame, 19 have 2–4, 14 have 5–9, 19 have
10–19, and 35 have 20+. The best ensemble reaches 0.351 full macro, 0.496
over classes with ≥10 frames, and 0.521 over ≥20 frames. Slash has only 642
inversion frames, so its 95% CI is wide. Any further gate claim needs
per-class support reporting, not a single macro number.

### B. Phases 1–3 completed (2026-11-20)
- Structured composition + Viterbi: negative; keep the flat chord head.
- 96-frame / 3-block / 3 seeds + SWA: 3 seeds span 0.311–0.328 macro; SWA
  neutral.
- Ensembling: strongest lever. Seed2-FT + seed3 gives macro 0.351, exact
  0.570, MIREX 0.688, ECE 0.022; FT1 + balanced-FT gives slash 0.266.

### C. Phase 4c — context capacity/ensemble (done)
128-frame / 4-block is worse than 96/3 on the external test. Cross-context
ensembling is the win: synth1 (96) + 128 seed1 gives macro **0.359**, exact
0.568, MIREX **0.693**, ECE **0.0147**; adding FT1 (64) gives slash 0.255 and
bass **0.834**. Context/capacity is saturated; further gains need a different
representation or data, not a longer context.

### C2. Phase 4d — pretrained encoder tried (MuQ, negative)
MuQ layer 6 val macro 0.076; layer 2 0.194; CQT guitar-only baseline 0.289.
Direct MuQ replacement is not viable in this pipeline. A future encoder
attempt needs a different adaptation strategy (e.g. layer-wise probe,
domain-adversarial training, or per-frame feature normalization) before
scaling. The remaining high-upside lever is **more real guitar data**
(GOAT/EGFxSet after licence review), not another direct feature swap.

### D. Metric decision
Keep the **full 102-class macro-F1 as the primary gate** until a pre-registered
metric change is agreed. Report minimum-support macro (≥10/≥20 frames) as a
secondary diagnostic; it currently passes 0.45 (0.500/0.526) while the full
gate is 0.351.

### E. Not yet ruled out
- Pretrained encoders (MuQ/MERT-v2) with adapters.
- More real guitar data (GOAT/EGFxSet) after licence review.
- Ambiguity-aware targets (maj6 ≡ relative min7) with both raw and merged
  reporting.
- k-fold over RWC/IDMT tracks and more seeds for CI reporting.

### F. Do not repeat
- Frame supervision as-is (negative, §3 item 13).
- Structured composition or window-level Viterbi (§3 item 14).
- SWA as a selection lever (§3 item 15).
- More full-mix Slakh for the macro gate.
- Adding monophonic/technique recordings (dataset2/3) as chord training.

### G. Phase 5/6
Blocked. Do not start distillation/deployment until all four gates pass;
the correction loop follows deployment.

---

## 11. Verification commands

```bash
cd backend
.venv-wsl/bin/python -m pytest -q tests/test_chord_vocab_170.py \
  tests/test_chord_labels_170.py tests/test_chord_eval_170.py \
  tests/test_external_splits.py tests/test_chord_calibration.py \
  tests/test_chord_eval_baseline.py
ruff check app/chord_vocab_170.py app/chord_labels.py scripts/chord_data_v2.py \
  scripts/train_chord_170.py scripts/eval_chord_170.py scripts/calibrate_chord_170.py \
  scripts/make_external_splits.py scripts/modal_chord_170.py \
  scripts/extract_fine_windows.py scripts/prepare_slakh.py \
  scripts/pseudo_label_btc.py scripts/btc_teacher.py --select E9,F63,F7,F82
cd ..
npm run lint
```

---

## 12. Continuation prompt (copy-paste for the next session)

> You are continuing the Harmoniq 170-class chord model program. Production
> is untouched; do not change `app/chord_inference.py`, the model registry, or
> any feature flag until all four gates pass.
>
> **Read first**: `AGENTS.md`, `PRIORITIES.md`, `techdebt/REPORT.md`,
> `docs/chord/CHORD_170_IMPLEMENTATION.md`, and especially
> `docs/chord/CHORD_170_HANDOFF.md` (full state, traps, artifacts).
>
> **Current state**: 170-class chord + 13-class bass + optional root/quality/
> inversion heads, trained on fine 1.6 s windows from GuitarSet, EGSet12,
> IDMT, RWC plus full Slakh2100-redux (1,710 tracks / ~285k windows), mild
> augmentation, masked bass loss, inversion-weighted chord loss, rare-class
> weights. Best honest external test (GuitarSet p05 + EGSet12 + held-out
> IDMT + held-out RWC, 3,121 windows): macro-F1 0.278, exact 0.451,
> WCSR-MIREX 0.633, bass 0.773, slash 0.182, ECE 0.083.
> **Gates**: bass ≥0.60 ✅ (0.773), ECE ≤0.15 ✅ (0.083), macro-F1 ≥0.45 ❌
> (0.278), slash ≥0.50 ❌ (0.182). Best checkpoint:
> `/runs/chord170/slakh-full-fine/best.keras` on the runs volume.
>
> **Immediate goal**: close the macro-F1 and slash gates. Prioritise:
> 1. **Frame-level supervision**: add per-frame labels (16/window) to the fine
>    npz (`scripts/add_frame_labels.py`), add `--frame-supervision` to
>    `train_chord_170.py` (per-frame heads, mean-over-frames eval), retrain
>    and re-evaluate. This is the main untested lever.
> 2. **More real annotated guitar data**: add Guitar-TECHS to
>    `extract_fine_windows.py` (MIDI labels, ~5 GB audio upload) and IDMT
>    datasets 1–3 XML note annotations (666 files; dataset1 has chords).
> 3. **Selection robustness**: EMA/last-K checkpoint averaging, 3 seeds,
>    k-fold RWC/IDMT; report CIs.
> Do not repeat documented negative results (see handoff §3): presence gates,
> MT3-template teacher, synthetic pretraining, full augmentation at small
> scale, inversion-head bass composition, head fusion, per-track
> normalization, larger encoder, external-val-only selection,
> 264-clip BTC pseudo-labels.
>
> **Rules**: one commit per logical change; stage only chord170 files (the
> tree has unrelated edits — never stage them); `npm run lint` must pass and
> the chord test suite must stay green before each commit; ask before
> guessing on licences/checkpoints/metric definitions. Modal volumes:
> `harmoniq-chord170-data` (`/chord170`) and `harmoniq-chord170-runs`
> (`/runs`). Re-upload `app` and `scripts` after code changes.
> Use `modal run --detach` for long jobs.
>
> Start by reading the handoff, then implement frame-level supervision and
> the real-data additions, run the external fine test, and report the gate
> table honestly. If the gates cannot be reached, document the ceiling with
> evidence rather than claiming success.
