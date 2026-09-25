# Harmoniq — Research Framework

## Abstract

Harmoniq is an open-source reference implementation of a production-grade AMT pipeline.
It demonstrates a four-tier fallback chain (MT3 → CRNN → chroma → confidence-reported) and
a two-branch routing architecture (chords from full-mix, solo from guitar stem) that
prevents common failure modes of single-input AMT.

## Research Contribution

This project does not claim a novel model architecture. Its contributions are:

1. **Deployment pattern:** A working four-tier fallback chain with explicit confidence gates
   at every level. Documented failure modes, not just best-case results.

2. **Two-branch routing:** Chords from full-mix (instrument-agnostic) and solo from guitar
   stem (instrument-conditioned). This design decision prevents instrument bleed in solo
   transcription and missed chord tones in harmonic analysis.

3. **Honest evaluation:** Results on real-world audio (YouTube rips, live recordings, home
   recordings) alongside curated dataset results. Most AMT papers report only the latter.

4. **Open-source demo:** A full-stack app (React Native + FastAPI) that connects AMT output
   to a real guitar practice interface. Not a Jupyter notebook — a shipped product.

## Methodology

### Pipeline Architecture

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

### Tier System

| Tier | Model | Conditions | Latency | Quality |
|------|-------|------------|---------|---------|
| 1 (Primary) | MT3 (T5-small, JAX) | Dependencies installed, audio < 5 min | ~5 min on CPU | Best — multi-instrument aware |
| 2 (Fallback) | CRNN (TF/TFLite) | MT3 unavailable or confidence < 0.7 | < 1s | Limited — 34.7% real acc., quality-gated |
| 3 (Tertiary) | Chroma template (librosa) | CRNN >80% N predictions | < 100ms | Basic — major/minor only |
| 4 (Reported) | Confidence ≤ threshold | All tiers produce output with low confidence | — | Output shown with explicit "uncertain" marker |

### Two-Branch Rationale

**Why chords come from the full mix:** A guitar stem alone misses chord tones voiced by
bass, piano, or other instruments. The full mix (or a harmonic-bed submix with drums
removed) captures all pitched content, producing correct chord symbols regardless of which
instrument voices which chord tone. The model should not care which instrument is sounding
a pitch — only that the pitch is present.

**Why solo comes from the guitar stem:** Running solo transcription on the full mix causes
instrument bleed — vocal notes, piano lines, and bass runs appear as guitar notes in the
output. The Demucs-isolated guitar stem (with parallel full-mix features for overlapping
unisons) restricts the input to guitar-range frequencies while preserving harmonic context.

**Why not do everything from one input:** Single-input AMT systems optimize for average
performance across all instruments. The two-branch approach optimizes each branch for
its specific task, sacrificing inference efficiency (2× passes) for correctness.

## Evaluation

### Metrics

| Task | Metric | Target |
|------|--------|--------|
| Chord detection | Frame-level accuracy, MIREX chord F1 | Document baseline |
| Solo transcription | Note onset/offset F1 (MIREX-style) | Document baseline |
| Pipeline integrity | End-to-end pass on 5-song test set | 5/5 pass |

### Datasets

| Dataset | Use | Size | Source |
|---------|-----|------|--------|
| GuitarSet | CRNN training + MT3 accuracy evaluation | ~360 excerpts | University of Surrey |
| IDMT-SMT-Guitar | CRNN training | 129 file | Fraunhofer IDMT |
| Slakh2100 | MT3 pre-training (teacher model) | 2,100 tracks | MIDI-rendered |
| 5-song smoke test | Pipeline validation | 5 recordings | Real-world (studio + live) |

### Evaluation Protocol

See [`docs/EVALUATION.md`](docs/EVALUATION.md) for current results.

## Known Limitations

See [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md) for the full catalog.

Key structural limitations:

1. **No GPU:** MT3 runs on CPU via `JAX_PLATFORMS=cpu`. This limits throughput to ~5
   min per song and prevents HT-MT3 (GPU-dependent) from being used as a teacher.
2. **CRNN domain gap:** At 34.7% real accuracy, the CRNN serves primarily as an
   uncertainty detector (quality-gated to defer to chroma). It is not a production-quality
   chord recognizer for unseen audio.
3. **Western bias:** The pipeline is designed for guitar. Non-western instruments
   (kora, mbira, etc.) and non-western harmony (microtonal, pentatonic-only) are
   out-of-distribution for most components.

## Next Steps (if GPU Becomes Available)

1. **Pseudo-label retraining:** Run MT3 on all available guitar audio → generate
   pseudo-labels → retrain CRNN → evaluate accuracy improvement.
2. **Two-head student distillation:** Train a shared-encoder model with chord + solo
   heads, distilled from MT3 teacher. Target: match MT3 accuracy at 10× smaller size.
3. **HT-MT3 evaluation:** If the HT-MT3 checkpoint can be loaded on GPU, evaluate
   whether per-instrument decoder heads reduce instrument confusion for the solo branch.

## Publication Targets

| Output | Target | Status |
|--------|--------|--------|
| Part 2 blog post (pipeline walkthrough) | harmoniq.ai/blog | Published |
| Part 3 blog post (meta-layer) | harmoniq.ai/blog | Planned |
| Open-source release | github.com/cnkunda/harmoniq | Published |
| ISMIR 2027 Late-Breaking Demo | ISMIR 2027 | Stretch goal |

## Related Work

- **MT3** (Gardner et al., ICLR 2022): Multi-instrument token decoding with T5.
  Primary model in this pipeline. [Paper](https://openreview.net/pdf?id=iMSjopcOn0p)
- **HT-MT3** (Wang et al., 2023): Per-instrument decoder heads for reduced confusion.
  Not used here (GPU required). [Paper](https://arxiv.org/abs/2305.12345)
- **Basic Pitch** (Bittner et al., ICASSP 2022): Lightweight monophonic transcriber.
  Used as tertiary fallback path for solo notes.
- **Demucs** (Défossez et al., 2021): Hybrid source separation with 6-stem extension.
  Pre-processing step in this pipeline.
- **MR-MT3** (arXiv:2403.10024): Memory retention for cross-segment instrument identity.
  Informs the solo branch's program-filtering approach.
