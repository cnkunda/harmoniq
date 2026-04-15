# Harmoniq Scoring Benchmark Matrix

Internal reference for aligning Harmoniq scoring behavior with patterns seen in Yousician, Rocksmith, and Melodics while preserving Harmoniq's low-pressure coaching tone.

| Surface | Harmoniq current | Harmoniq v2 target | Yousician pattern | Rocksmith/Rocksmith+ pattern | Melodics pattern |
| --- | --- | --- | --- | --- | --- |
| Onboarding phrases | Mean aggregation over 3 phrases | Winsorized + confidence-weighted aggregation with reliability flags | Placement + lesson adaptation after early attempts | Calibration and setup heavily influence first scoring outcomes | Early calibration and timing bucketing |
| Session review score | Single score payload with core metrics | Add reliability envelope + diagnostics payload | Real-time scoring and post-pass summaries | Real-time note detection, lag correction, and per-note diagnostics | Tight timing categories with transparent windows |
| Jam scoring | Passive map + coach summary | Reliability-tagged map with confidence envelope and sparse-map guardrails | Less jam-centric; more exercise-centric scoring | Sustained tone/fret tracking with latency calibration | Grid-centric diagnostics with groove feedback |
| Progress updates | Scalar session score into SM-2 update | Multi-signal update (accuracy + timing + reliability) with low-confidence damping | Progress affected by repeated clean runs | Progress unlocked by sustained consistency | Progress tied to timing consistency and repetition |
| Explainability | Limited | Explicit confidence notes and reliability tags in UX | Visible pass/fail and stars | Technique-focused reason codes and setup guidance | Timing category feedback and trend emphasis |

## Mapping Summary

- Harmoniq differentiator: keep coaching non-judgmental while making reliability explicit.
- Minimum parity requirement: every scoring surface carries confidence + reliability flags.
- Avoid anti-patterns: opaque score jumps, binary "good/bad" language, and low-signal false progression.

## Immediate Validation Checklist

- Onboarding averages are stable under one outlier phrase.
- Jam responses include reliability tags for short or sparse captures.
- Session score responses include diagnostics and contract version.
- Progress updates dampen low-confidence runs and still reward high-confidence consistency.
