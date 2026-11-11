# Harmoniq — Research Framework

## Abstract

Harmoniq is an open-source reference implementation of a production-grade
guitar automatic music transcription (AMT) pipeline. It demonstrates a
four-tier fallback chain (MT3 → CRNN → chroma → confidence-reported), a
two-branch routing architecture (chords from the full mix, solo from the
guitar stem), a challenge-style evaluation harness on an expanded real-audio
manifest, a teacher comparison, a two-head student, a playability-aware
tablature assignment track, and a measured confidence/calibration report.

The program is deliberately honest about negative results: the current
teacher/student stack is not yet a SOTA transcription system, the CRNN
domain gap is unresolved, the student's solo head does not produce usable
notes, the high-confidence chord band is severely overconfident, and the
recording-quality gate is not validated as an accuracy predictor on the
committed studio/controlled manifest.

## Research Contribution

1. **Deployment pattern with explicit confidence gates.** A working
   four-tier fallback chain with documented failure modes at every level,
   plus an opt-in calibrated chord-confidence gate that is documented as
   not release-ready rather than overclaimed.

2. **Two-branch routing.** Chords from the full mix (instrument-agnostic)
   and solo from the guitar stem (instrument-conditioned). This prevents
   instrument bleed in solo transcription and missed chord tones in harmonic
   analysis.

3. **Honest, reproducible evaluation.** A 705-track manifest with
   challenge-style metrics (instrument ID, pitch, onset/offset F1 at 50 ms,
   dynamics, overlap, runtime, chord accuracy, ECE), fixed splits, a
   Pass/Warn/Fail rubric, and deterministic reports. The headline numbers
   and their artifacts are listed in
   [`docs/eval/REPRODUCIBILITY.md`](eval/REPRODUCIBILITY.md).

4. **Measured teacher/student/tablature track.** A 50-track teacher
   comparison (`go` → YourMT3+), a two-head student with a documented
   accuracy ceiling, and a playability-aware tablature DP that beats the
   per-note heuristic on tab accuracy.

5. **Calibration as a first-class result.** Expanded-set chord-template ECE
   is measured, the high-confidence band is shown to be severely
   overconfident, and the product UI is changed to coarse neutral bands with
   no raw percentages.

## Methodology

### Pipeline architecture

```
Audio → Demucs htdemucs_6s → 6 stems (guitar, bass, drums, vocals, piano, other)
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
            Branch A (chords)           Branch B (solo)
            Input: full mix            Input: guitar stem + full mix
            Model: MT3 → CRNN → chroma Model: MT3 (program-filtered)
            Output: chord timeline      Output: solo note tokens
                    │                           │
                    └─────────────┬─────────────┘
                                  ▼
                          LessonJSON with
                    per-branch confidence scores
```

### Tier system

| Tier | Model | Conditions | Latency | Quality |
|------|-------|------------|---------|---------|
| 0 (opt-in) | W3 two-head student | `HARMONIQ_STUDENT_ENABLED=1`; falls through on any failure | <1 ms/frame measured | 0.5128 GuitarSet root ceiling |
| 1 (primary) | MT3 (T5-small, JAX) | Dependencies installed, audio < 5 min | ~5 min on CPU; GPU used for research runs | Best available teacher |
| 2 (fallback) | CRNN (TF/TFLite) | MT3 unavailable or confidence < 0.7 | < 1 s | Limited — 34.7% real acc., quality-gated |
| 3 (tertiary) | Chroma template (librosa) | CRNN >80% N predictions **or** mean top-class confidence < 0.20 | < 100 ms | Basic — major/minor only |
| 4 (reported) | Confidence ≤ threshold | All tiers produce low-confidence output | — | Output shown with a coarse "check by ear" band |

The opt-in `HARMONIQ_CONFIDENCE_GATE` (W5) replaces the legacy MT3
event-mean check with the measured duration-weighted chord-template
confidence. It is off by default and documented as not release-ready.

### Two-branch rationale

**Why chords come from the full mix:** A guitar stem alone misses chord tones
voiced by bass, piano, or other instruments. The full mix (or a harmonic-bed
submix with drums removed) captures all pitched content, producing correct
chord symbols regardless of which instrument voices which chord tone. The
model should not care which instrument is sounding a pitch — only that the
pitch is present.

**Why solo comes from the guitar stem:** Running solo transcription on the
full mix causes instrument bleed — vocal notes, piano lines, and bass runs
appear as guitar notes in the output. The Demucs-isolated guitar stem (with
parallel full-mix features for overlapping unisons) restricts the input to
guitar-range frequencies while preserving harmonic context.

**Why not do everything from one input:** Single-input AMT systems optimize
for average performance across all instruments. The two-branch approach
optimizes each branch for its specific task, sacrificing inference efficiency
(2× passes) for correctness.

## Headline results (2026-11)

| Workstream | Result | Artifact |
| --- | --- | --- |
| W0 | 705-track manifest; challenge-style metrics + Pass/Warn/Fail rubric; four-tier baselines (2-track smoke artifact) | `docs/eval/amt_manifest.json`, `docs/audit/amt/eval-smoke-all.*` |
| W1 | 1,004 tracks pseudo-labeled; 1,654 / 233 / 230 splits; zero train↔eval overlap | `docs/eval/w1_dataset_manifest.json`, `docs/audit/amt/w1_pseudo_label_full.json` |
| W2 | 50-track teacher comparison; `go` → YourMT3+ (onset F1 0.5723 vs MT3 0.5092; leakage 0.5756 vs 0.6962; RTF 0.192 vs 3.164) | `docs/audit/amt/w2_teacher_comparison.{json,md}` |
| W3 | Shared-encoder student: 0.5128 GuitarSet root accuracy (documented ceiling), 0.002986 ms/frame; solo F1 0.0 | `docs/audit/amt/w3_eval_student.json`, `docs/audit/amt/w3_latency.json` |
| W4 | Tab accuracy 0.5893 vs 0.5031 baseline (+8.62 pp); playability 2.6092 vs 2.4529; group validity 1.0 vs 0.5076 | `docs/audit/amt/w4_tab_eval.{json,md}` |
| W5 | Chord-template ECE 0.7281 on 526 tracks; mean confidence 0.9307, accuracy 0.2026; no bin reaches 0.70; quality gate inconclusive | `docs/audit/amt/w5_calibration.{json,md}` |

**Teacher comparison (W2, 50 tracks):**

| Teacher | Chord acc | Onset F1 | OnsetPitch F1 | Offset F1 | Retention | Leakage | RTF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MT3 | 0.2667 | 0.5092 | 0.5815 | 0.4436 | 0.5793 | 0.6962 | 3.1641 |
| MR-MT3 | 0.2554 | 0.4222 | 0.4759 | 0.3891 | 0.4269 | 0.8251 | 0.6257 |
| YourMT3+ | 0.2164 | 0.5723 | 0.5904 | 0.4871 | 0.6090 | 0.5756 | 0.1922 |

**Calibration (W5, 526 tracks / 15,204 events):** pooled ECE **0.7281**,
mean confidence **0.9307**, accuracy **0.2026**. The 0.9–1.0 bin carries
83% of the duration at only 21.9% accuracy; the best bin (0.8–0.9) is 0.544.
No bin reaches the 0.70 release floor, so the calibrated gate uses 0.80 and
is documented as not release-ready.

## Evaluation

### Metrics

| Task | Metric | Target |
|------|--------|--------|
| Instrument ID | Exact GM program + GM-family accuracy | Report |
| Pitch/onset | F1 at ±50 ms | Report |
| Offset | F1 at max(50 ms, 20% duration) | Report |
| Dynamics | Velocity MAE over matched notes | Report |
| Overlap | Interval IoU over offset-matched notes | Report |
| Chords | 25-class MIREX frame accuracy + interval P/R/F1 + root accuracy | Report |
| Calibration | Duration-weighted ECE + reliability table | Report |
| Runtime | Wall time per track / per frame | Report |
| Tab (W4) | Pitch accuracy, exact string/fret, playability, group validity | Report |
| Strata | Instrument count, source, split, recording type | Report |

### Datasets

| Dataset | Use | Size | Licence |
|---------|-----|------|---------|
| GuitarSet | Evaluation (W0/W3/W4/W5) + training | 360 excerpts | CC BY 4.0 |
| IDMT-SMT-Guitar | Evaluation + training | 129 files | IDMT academic |
| EGSet12 | Evaluation (jazz/funk) | 12 tracks | CC BY 4.0 |
| Guitar-TECHS | Evaluation + training | 104 manifest tracks | CC BY 4.0 |
| RWC-P | Evaluation (full mixes) | 100 tracks | CC BY-NC 4.0 |
| YouTube crawl | Weak labels | 264 tracks | YouTube ToS |
| Slakh2100 | MT3 pre-training (teacher) | 2,100 tracks | MIDI-rendered |

The committed W0 manifest is dataset-only. Live/home/kora-mbira OOD audio is
user-supplied via `docs/eval/external_recordings.md`; unannotated tracks are
qualitative and unscored. RWC-P audio is not redistributed.

### Protocol

See [`EVALUATION.md`](EVALUATION.md) for the measured results and
[`docs/eval/REPRODUCIBILITY.md`](eval/REPRODUCIBILITY.md) for the exact
commands and committed artifacts. The W0 harness is evaluation-only; it does
not run inside `/analyze`.

## Known limitations

See [`KNOWN_FAILURES.md`](KNOWN_FAILURES.md) for the full catalog.

Key measured limitations:

1. **MT3 note confidence is a placeholder.** Every note reports `0.9`; only
   chord-template confidence is calibrated. Note-level ECE is undefined.
2. **Chord-template confidence is severely overconfident.** Pooled ECE
   0.7281; the 0.9–1.0 bin is 21.9% accurate. The UI uses coarse neutral
   bands, and the calibrated gate is opt-in and not release-ready.
3. **The student is below the G3 target.** GuitarSet root accuracy 0.5128
   vs the 0.70 gate; the solo head produces 0.0 matched-note F1. The student
   stays behind an off-by-default flag.
4. **The CRNN domain gap is unresolved.** 34.7% real-world accuracy; the
   quality gates are uncertainty detectors, not production recognizers.
5. **The recording-quality gate is not validated on the committed
   manifest.** All 513 scored studio/controlled tracks were accepted; no
   rejected group exists to estimate separation. External live/home/OOD
   recordings are required.
6. **W5 coverage is 526/705 tracks.** The remaining 179 Guitar-TECHS/RWC-P
   tracks were not staged on the Modal volumes (a 10 GB re-upload stalled).
   This is documented, not silently omitted.
7. **Tab assignment is symbolic.** W4 assigns reference pitches; audio→tab
   error is not part of the gate. The learned Fretting-Transformer T5 was
   not trained (DadaGP not staged; local GPU budget).
8. **Western/guitar bias.** Non-western instruments and microtonal harmony
   remain out of distribution.

## Next steps

1. **Close the W5 coverage gap** by staging the remaining 179
   Guitar-TECHS/RWC-P tracks and re-running the calibration aggregation.
2. **Implement native MT3 note confidence** (token log-probabilities) before
   any note-level calibration or gating claim.
3. **Re-label the W1 corpus with the W2-selected YourMT3+ teacher** and
   retrain the student; the current student uses stock MT3 pseudo-labels.
4. **Improve the student solo head** (currently 0.0 F1) and revisit the
   INT8→FP16 export fallback.
5. **Train the learned Fretting-Transformer** when DadaGP and GPU budget are
   available; add the audio→string-activity head.
6. **Add external live/home/OOD recordings** to validate the recording
   quality gate and the calibration claim beyond studio data.

## Publication inputs

- **Headline claim:** a measured, reproducible guitar-AMT research program
  with an honest negative calibration result and a playability-aware
  tablature track.
- **Numbers:** W2 teacher table, W3 ceiling/latency, W4 tab/playability
  deltas, W5 ECE/reliability table.
- **Artifacts:** `docs/eval/amt_manifest.json`,
  `docs/audit/amt/w2_teacher_comparison.{json,md}`,
  `docs/audit/amt/w3_eval_student.json`, `docs/audit/amt/w4_tab_eval.{json,md}`,
  `docs/audit/amt/w5_calibration.{json,md}`,
  `docs/eval/REPRODUCIBILITY.md`.
- **Venue:** ISMIR 2027 late-breaking demo is a stretch goal; no submission
  is committed.

## Publication targets

| Output | Target | Status |
|--------|--------|--------|
| Part 2 blog post (pipeline walkthrough) | harmoniq.ai/blog | Published (October 2026) |
| Part 3 blog post (meta-layer) | harmoniq.ai/blog | Planned — after the AMT Research Program (Commit 2) |
| Open-source release | github.com/cnkunda/harmoniq | Published |
| ISMIR 2027 Late-Breaking Demo | ISMIR 2027 | Stretch goal |

## Related work

- **MT3** (Gardner et al., ICLR 2022): Multi-instrument token decoding with
  T5. Primary teacher in this pipeline.
  [Paper](https://openreview.net/pdf?id=iMSjopcOn0p)
- **HT-MT3** (Wang et al., 2023): Per-instrument decoder heads for reduced
  confusion. Not used here (GPU required).
  [Paper](https://arxiv.org/abs/2305.12345)
- **Basic Pitch** (Bittner et al., ICASSP 2022): Lightweight monophonic
  transcriber. Retained as a fallback path for solo notes.
- **Demucs** (Défossez et al., 2021): Hybrid source separation with 6-stem
  extension. Pre-processing step.
- **MR-MT3** (arXiv:2403.10024): Memory retention for cross-segment
  instrument identity. Evaluated in W2; not selected as-is (leakage 0.8251).
- **YourMT3+** (arXiv:2407.04822): Hierarchical attention, MoE, multi-channel
  decoding, cross-stem augmentation. W2 `go` teacher.
- **Fretting-Transformer** (arXiv:2506.14223): MIDI-to-tablature string/fret
  assignment with tuning/capo conditioning. Informs W4.
- **TART** (arXiv:2510.02597): Technique-aware audio-to-tab pipeline and
  playability-aware assignment. Informs W4 metrics.
