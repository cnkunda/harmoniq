# Harmoniq Pipeline Evaluation

This document records the pipeline smoke test results. Last updated: July 2026.

## Test Set

The current smoke test set consists of 5 recordings:

| # | Song | Artist | Source | Type | Notes |
|---|------|--------|--------|------|-------|
| 1 | *Sunny* | Bobby Hebb | Upload (WAV) | Studio, clean | 3:37, clear guitar |
| 2 | *Sunny* (live) | Bobby Hebb | YouTube | Live, crowd | Audience bleed, room reverb |
| 3 | *Gravity* | John Mayer | YouTube | Studio | Section with talkback/ambient intro (muted) |
| 4 | *Improv blues* | Self-recorded | Upload (WAV) | Home recording | Single track, SM57 on amp |
| 5 | *Stairway to Heaven* | Led Zeppelin | YouTube | Studio, complex | Acoustic + electric sections |

## Evaluation Protocol

1. Submit each song via the analyze endpoint (upload or YouTube URL)
2. Wait for pipeline to complete (MT3 mode, ~5 min per song on CPU)
3. Inspect the LessonJSON output for each section:
   - Chord timeline: any chords produced? confidence?
   - Solo notes: any notes produced? per-note confidence?
   - Tier used: MT3, CRNN, or chroma for each branch
4. Mark pass/fail/warn based on:

| Criterion | Pass | Warn | Fail |
|-----------|------|------|------|
| Chord timeline | All sections have chords with confidence >0.5 | Some sections have chords but confidence <0.5 | No chords produced for any section |
| Solo notes | Notes present for guitar sections | Notes present but low confidence or wrong pitch centers | No notes for guitar sections or obvious instrument leakage |
| Pipeline completion | Complete LessonJSON returned within timeout | Partial result with fallback | No result or crash |

## Test Results

### #1 — Sunny (Bobby Hebb, studio)

| Component | Result | Confidence | Notes |
|-----------|--------|------------|-------|
| Branch A (chords) | MT3 | 0.82 | Correct voicings, 7th chords detected |
| Branch B (solo) | MT3 | 0.73 | Clean melodic line, note durations accurate |
| Pipeline time | 4:12 | — | MT3 decode on CPU |

**Verdict:** ✅ Pass

### #2 — Sunny (Bobby Hebb, live)

| Component | Result | Confidence | Notes |
|-----------|--------|------------|-------|
| Branch A (chords) | MT3 → CRNN | 0.48 | CRNN quality gate triggered for 2 of 5 sections |
| Branch B (solo) | MT3 | 0.51 | Some bleed from crowd noise, notes in vocal range present |
| Pipeline time | 4:35 | — | MT3 decode on CPU |

**Verdict:** ⚠️ Warn — chords present but low confidence in live sections. Expected for live recording.

### #3 — Gravity (John Mayer, studio)

| Component | Result | Confidence | Notes |
|-----------|--------|------------|-------|
| Branch A (chords) | MT3 | 0.88 | G major progression detected correctly |
| Branch B (solo) | MT3 | 0.79 | Solo section well-transcribed, bends approximated |
| Pipeline time | 4:08 | — | MT3 decode on CPU |

**Verdict:** ✅ Pass

### #4 — Improv blues (self-recorded, home)

| Component | Result | Confidence | Notes |
|-----------|--------|------------|-------|
| Branch A (chords) | MT3 → CRNN → Chroma | 0.35 | CRNN qualty gate triggered; chroma got basic I-IV-V |
| Branch B (solo) | MT3 | 0.42 | Notes detected but many pitch errors |
| Pipeline time | 4:40 | — | MT3 decode on CPU + fallback latency |

**Verdict:** ❌ Fail — poor recording quality (room reverb, low input gain) degraded the entire pipeline. The chroma fallback got the blues progression but couldn't capture detail. This is the worst-case demonstration of the domain gap.

### #5 — Stairway to Heaven (Led Zeppelin, studio)

| Component | Result | Confidence | Notes |
|-----------|--------|------------|-------|
| Branch A (chords) | MT3 | 0.76 | Acoustic section chords correct; electric section harmony complex |
| Branch B (solo) | MT3 | 0.68 | Solo section transcribed but ornamentation (hammer-ons, bends) approximated |
| Pipeline time | 4:55 | — | Longest decode, 8-minute track |

**Verdict:** ✅ Pass

## Summary

| Result | Count |
|--------|-------|
| ✅ Pass | 3 |
| ⚠️ Warn | 1 |
| ❌ Fail | 1 |

## Conclusions

1. **Studio recordings with clear guitar produce reliable output.** MT3 handles these well on both branches.
2. **Home/live recordings are the failure mode.** The CRNN quality gate catches these and chroma provides basic coverage, but the pipeline can't produce detailed transcription in this range.
3. **The fallback chain works as designed.** When MT3 confidence is low, CRNN fires. When CRNN is uncertain, chroma fires. Each tier handles the cases the previous tier can't.
4. **CPU latency is the practical bottleneck.** ~5 min per song is acceptable for research but not for a real-time demo.

## Next Steps for Re-evaluation

When re-running this evaluation after pipeline changes:

1. Re-record test #4 with proper gain staging and minimal room reverb
2. Add a clean kora/mbira recording to test out-of-distribution behavior
3. Add a song with extended jazz harmony to stress-test the chord vocabulary
4. Capture pipeline timing with GPU to document speedup factor

## Transcription Confidence (Commit 156)

**What the score is:** a hand-tuned heuristic, **not** a calibrated probability.
Never describe it as "% likely correct" in code, schemas, or docs.

- Song level — `LessonJSON.transcription_confidence` =
  `composite_transcription_confidence(chord, vocals)` (`backend/app/transcription_confidence.py`):
  chord signal alone when instrumental; vocals discounted ×0.85 when chords
  failed; 60/40 chord/vocals blend when both present; capped at 0.25 when the
  guitar stem is unusable; floored at 0.05–0.1. Chord input =
  duration-weighted mean event confidence (`chord_section_confidence`, N
  events excluded); vocals input = beat-grid coverage steps
  (`vocals_coverage_confidence`: 0.92/0.82/0.7/0.55/0.35).
- Per section — `sections[].chord_confidence` from `chord_section_confidence()`
  over the section's time range (also mirrored onto `sections[].confidence`,
  capped at 0.25 when tabs were skipped).
- **Consumers of the song score (Commit 156 wiring):** the same composite
  value now feeds tab generation — `generate_tab_artifacts_for_guitar_stem`
  and `apply_tab_artifacts_to_sections` (alt-position GP5 gate,
  `TAB_ALT_CONFIDENCE_THRESHOLD = 0.6`), `derive_section_confidence`, and
  `low_snr_warning` (`< 0.5`). Practical effect: instrumentals no longer sit
  at the ~0.1 vocals floor — they score chord-level and therefore clear the
  alt-tab gate and stop raising the low-SNR warning. This is the intended
  consequence of the replace decision, not a regression.
- Band — `confidence_band`: low < 0.5, medium < 0.75, high ≥ 0.75
  (`backend/app/confidence_thresholds.py`). Coarse by design so the UI avoids
  false precision. `null` = unknown.
- Tier-aware gap (known follow-up): the score does not take
  `transcription_source` (mt3/crnn/chroma) as an input, so CRNN/chroma-tier
  results can score as high as MT3 results.

**Calibration measurement (Commit 184):** the heuristic is **severely
overconfident** on a small GuitarSet test subset. Measured with:

```bash
cd backend && source .venv-wsl/bin/activate
python scripts/measure_confidence_ece.py --limit 3 --out data/evaluation/ece_mt3.json
```

Tracks: `05_BN1-129-Eb_comp`, `05_BN1-147-Gb_comp`, `05_BN2-131-B_comp`
(player 05 test split). 134 decoded events covering 70.8 s. Overall chord
accuracy **0.090**, mean confidence **0.834**, **ECE 0.7441** (10 equal-width
bins, duration-weighted). Non-empty bins:

| Bin | Events | Duration (s) | Avg confidence | Accuracy | Gap |
|-----|--------|--------------|----------------|----------|-----|
| 0.4–0.5 | 2 | 0.95 | 0.400 | 0.000 | 0.400 |
| 0.5–0.6 | 35 | 19.18 | 0.549 | 0.000 | 0.549 |
| 0.7–0.8 | 12 | 5.36 | 0.750 | 0.000 | 0.750 |
| 0.8–0.9 | 12 | 5.90 | 0.800 | 0.378 | 0.422 |
| 0.9–1.0 | 73 | 39.45 | 1.000 | 0.105 | 0.895 |

**Caveats and follow-ups:**

- `ChordEvent.confidence` on the MT3 path is template **coverage**, not a
  calibrated model probability. Coverage ignores extra pitches, so a wrong
  chord with a complete template still scores high.
- The local MT3 + chord-decoder result is far below the ≥80% GuitarSet target
  in `tests/test_guitarset_mt3_accuracy.py`. That test currently skips because
  it looks for `data/guitarset/audio/` (the audio lives under
  `raw/audio_mono-mix/`) and maps 277-class labels through the 25-class vocab;
  it has not been validating the claim. Treat the model/decoder accuracy as a
  separate blocker before interpreting ECE as a pure calibration problem.
- Three tracks are a directional sample, not a precise estimate. The CRNN
  fallback was not used here: the local Keras checkpoint scored ~4% accuracy
  on the precomputed test windows, and the TFLite file needs a Flex delegate
  that is not installed.
- **No scaling was applied.** Raw confidence fields and the 0.5/0.75 band
  thresholds are unchanged; the UI renders wording only. Isotonic/Platt
  scaling needs a larger, trustworthy calibration set (isotonic is prone to
  overfitting on small samples).
- Reproduce with `backend/scripts/measure_confidence_ece.py`; the binning/ECE
  math is in `backend/app/confidence_calibration.py` and covered by
  `backend/tests/test_confidence_ece.py`. Do not describe the score as a
  probability or a percentage.

## Instrument Confusion & Coach Hedging (Commit 156)

- **How computed:** on the CRNN dual-path branch, per-section stem-vs-mix
  chord disagreement rate (`compute_per_section_confusion`,
  `backend/app/instrument_confusion.py`); song level from dual-path fusion.
  On MT3-primary jobs the dual path never runs, so a heuristic proxy is
  used instead: per-section share of chord events below 0.5 confidence
  (`heuristic_mt3_section_confusion`) — model uncertainty, not measured
  divergence. `leakage_risk` on sections is currently an alias of
  `instrument_confusion` until a true solo-branch leakage signal exists.
- **Thresholds** (`backend/app/confidence_thresholds.py`, single source):
  hedge at ≥ 0.3 (soft: note possible cross-instrument notes, check by ear),
  strong hedge at ≥ 0.6 (no specific technique claims, approximate guide,
  listen to the original). Missing (`None`)/NaN = unchanged copy, never 0.
- **How hedging reaches the coach:** per-section values are copied onto
  `LessonSectionStub.instrument_confusion` at aggregation; `jobs.py` hydration
  passes the typed field into `build_coach_user_prompt`, which adds a
  tiered caution block. A deterministic backstop (`apply_hedge_backstop` in
  `backend/app/coach.py`) appends one templated caveat whenever the copy
  (model output **or** the fallback copy used when no model ran — missing key,
  timeout, parse/API error) contains no hedge marker — hedging never depends
  on LLM compliance or availability alone. Hedge copy blames the
  transcription, never the player.
- **Limitations:** stock MT3 lacks MR-MT3's training-time leakage
  mitigations; `htdemucs_6s` guitar stems can contain piano/vocal bleed, which
  surfaces as wrong notes in tab on high-confusion sections.
