# Known Pipeline Failures & Limitations

This document tracks known failure modes in the Harmoniq transcription pipeline.
Last updated: October 2026

## MT3 (Primary)

| Scenario | Symptom | Root Cause | Workaround |
|----------|---------|------------|------------|
| Live recording with crowd noise | Low confidence on both branches | Ambiguous audio — applause/bleed confuses spectrogram | Use studio recording when possible |
| Heavy reverb or delay | Duplicated or smeared note onsets | Reverb tail interpreted as new events | Pre-process with dry/wet reduction |
| Song >5 min | Inference timeout or memory pressure | CPU-only JAX — T5-small decoder O(n²) over 1024 token limit | Split song into sections |
| MT3 dependencies missing | Empty event stream returned, CRNN fallback activated | `mt3`, `note-seq`, `jax`, `t5x` not installed | `pip install -e ".[mt3]"` |
| GPU conflicts | JAX crashes on startup | CuDNN version mismatch or no CUDA jaxlib | Server hardcodes `JAX_PLATFORMS=cpu` |

## CRNN (Fallback — Chord Detection)

| Scenario | Symptom | Root Cause | Workaround |
|----------|---------|------------|------------|
| Non-guitar instrument (piano, synth) | >80% frames predict N (no chord) — quality gate triggers | Model only trained on guitar CQT (GuitarSet, IDMT, etc.) | Correct behavior — falls through to chroma |
| Out-of-distribution mix | Mean top-class confidence < 0.20 — near-uniform CRNN output | Model has no usable signal for this audio | Correct behavior — `_neural_model_too_uncertain()` falls through to chroma |
| Alternate tuning (Drop D, Open G) | Lower confidence on voiced chords | Training data uses standard tuning primarily | Tuning metadata passed to pipeline helps |
| Heavy distortion / overdrive | Chord classification degrades | Harmonic distortion changes chroma profile | Use clean or amp-simulated signal |
| Complex jazz harmony (altered dominants, upper extensions) | Model predicts simpler chord (maj/min) instead of extended | 277-class vocabulary trained with class imbalance | Chroma fallback may be better for extensions |
| Room mic recording | Predictions flicker between adjacent chord classes | Reverberation smears chord boundaries | Viterbi decoder smooths transitions |

## Demucs (Stem Separation)

| Scenario | Symptom | Root Cause | Workaround |
|----------|---------|------------|------------|
| Mono recording | Bleed between stems | `htdemucs_6s` trained on stereo; mono degrades separation | Minimal — best-effort only |
| Heavy compression | Reduced stem separation quality | Dynamic range compression confuses separation model | Seek unmastered recording |
| Non-western instruments (kora, mbira, etc.) | Instrument routed to "other" stem | Only 6 stems: guitar, bass, drums, vocals, piano, other | Full-mix Branch A still produces chords |
| Low bitrate MP3 (<128kbps) | Artifacts in all stems | Compression artifacts confuse separation | Use WAV or FLAC source |
| YouTube with varying audio quality | Stems have bleed between channels | yt-dlp may return variable-bitrate with encoding artifacts | Upload WAV directly when possible |
| Piano bleed into guitar stem | Wrong notes in tab/solo on affected sections | `htdemucs_6s` lets piano/vocal bleed through; stock MT3 lacks MR-MT3 training-time leakage mitigations | App hedges coach copy on high-confusion sections (Commit 156: caution clause ≥ 0.3, approximate-guide framing ≥ 0.6, plus a deterministic appended caveat); check the part by ear against the recording |

## Instrument Confusion (Commit 156)

| Scenario | Symptom | Root Cause | What the app does |
|----------|---------|------------|-------------------|
| Piano-forward mix on CRNN dual-path branch | High per-section `instrument_confusion` (stem-vs-mix chord disagreement) | Piano harmony dominates the full mix while the guitar stem says otherwise | Flags `high_instrument_confusion`, hedges section coach copy, downgrades `/score` confidence above 0.5 |
| MT3-primary job with uncertain chords | Heuristic proxy confusion from low-confidence chord share | Dual-path divergence is unavailable on the MT3 path; proxy measures model uncertainty, not proven interference | Same hedging tiers apply; hedges are approximate by design |
| No confusion data (single-path, empty sections) | `instrument_confusion` null | Nothing computed — unknown | Coach copy unchanged; null is never treated as 0 or high |

## Teacher Comparison (W2)

| Scenario | Symptom | Root Cause | What the program does |
|----------|---------|------------|-----------------------|
| MR-MT3 on guitar mixes | Leakage 0.8251; retention 0.4269; lower onset F1 than MT3 | Program tokens still cross instruments; memory retention not enough without a filter | Not selected as-is; viable only with a mandatory guitar-program filter |
| YourMT3+ on guitar mixes | Best onset F1 (0.5723) and lowest leakage (0.5756), but chord accuracy 0.2164 | Teacher strengths differ by task; chord decoding is not its primary win | W2 `go` teacher for student relabeling; not wired as the production teacher |
| MusicFM | Placeholder only | Encoder-only; MIROS decoder/weights licence outstanding | Not evaluated; documented placeholder |
| MT3 baseline | Event confidence is a `0.9` placeholder | The MT3 `NoteSequence` has no confidence field | Confidence claims use chord-template coverage only |

## Two-Head Student (W3)

| Scenario | Symptom | Root Cause | What the program does |
|----------|---------|------------|-----------------------|
| GuitarSet test root accuracy | 0.5128 vs the 0.70 G3 gate | Pseudo-label majority/overfitting; stock MT3 labels; limited corpus | Documented ceiling; student stays off by default |
| Solo head | 0.0 matched-note onset/pitch F1 | Autoregressive token decode does not yet produce usable notes | Chord head is the latency-gated path; `HARMONIQ_STUDENT_SOLO=0` disables solo |
| INT8 export | Falls back to FP16 | TF 2.20 converter fails on the Conv1D reshape (`CONV_2D input dims 3 != 4`) | QAT checkpoint retained; FP16 TFLite ships |
| Autoregressive decode | Slow (one model invoke per token) | Frame-synchronous token generation | Disable solo for fast evaluation; chord head is the target path |

## Tablature Assignment (W4)

| Scenario | Symptom | Root Cause | What the program does |
|----------|---------|------------|-----------------------|
| Playability vs tab accuracy | DP tab accuracy +8.62 pp but difficulty 2.6092 vs 2.4529 | DP minimises transition cost subject to physical validity; the per-note baseline collapses multi-note groups onto one string | Reports both metrics honestly; no single "better" claim |
| Learned Fretting-Transformer | Not trained | DadaGP not staged; local GTX 1050 below a practical training budget | DP uses the paper's sequence cost; learned model is a documented follow-up |
| String-activity audio head | Deferred | Needs a student retrain | Target construction is implemented/tested; no audio head yet |
| Technique labels | Heuristic and unscored | Reuses bend/vibrato patterns + same-string legato heuristics | Prototype only; no ground-truth technique metric is claimed |
| Evaluation scope | Symbolic (MIDI→tab) | Reference pitches are the input | End-to-end audio→tab error is not part of G4 |
| Tuning/capo evidence | Augmented, not recorded | All staged data is standard/capo 0 | Variants transpose the reference performance; documented as augmentation |

## Confidence Calibration (W5)

| Scenario | Symptom | Root Cause | What the app does |
|----------|---------|------------|-------------------|
| MT3 note confidence | Every note reports `0.9`; note-level ECE is undefined | The MT3 `NoteSequence` has no confidence field | Note confidence is documented as a placeholder; W5 calibrates chord-template confidence only |
| Chord-template confidence | High bin (0.9–1.0) is only ~22% accurate; pooled ECE 0.7281 | Template coverage ignores extra pitches and non-chord tones; severe overconfidence | UI shows coarse neutral bands, never percentages; the calibrated gate is opt-in and not release-ready |
| Calibrated fallback gate | `HARMONIQ_CONFIDENCE_GATE=1` can reject MT3 at the best measured bin | No bin reaches the 0.70 accuracy floor (best is 0.544) | Gate is off by default; enabling it documents the ceiling rather than claiming calibration |
| Recording-quality gate | All 513 evaluated studio tracks are accepted; no rejected group | The committed manifest is studio/controlled; the gate was designed for home/live failures | Gate remains a conservative ingest guard; external live/home/OOD recordings are needed to validate it |
| W5 coverage | Calibration uses 526 of 705 tracks | The remaining 179 Guitar-TECHS/RWC-P tracks were not staged on the Modal volumes (10 GB upload stalled) | Documented coverage gap; the committed per-source reports reproduce the 526-track ECE exactly |

## Frontend

| Scenario | Symptom | Root Cause | Workaround |
|----------|---------|------------|------------|
| Web mic requires HTTPS | `getUserMedia` blocked on HTTP | Browser security requirement | Use `http://localhost` for development |
| Headless Chromium has no microphone | Uncaught error overlay: `[PitchStream.web] Unable to access microphone: Not supported` on `/session/tune` | Headless browser exposes no mic device; `usePitchStream().start()` rejection is uncaught | Run the tune step in a real browser with microphone permission; functional follow-up |
| AlphaTab WebView on older Android | Tab rendering crashes | Underlying Chromium WebView version | Update WebView via Play Store |
| Large lesson files (>10MB) | Slow initial render | Full MusicXML + audio stems loaded at once | Lazy-load sections |

## Known Not-Bugs

These behaviors are intentional but may look like bugs:

- **CRNN predicts N or near-uniform probabilities on unfamiliar audio.** The quality gates check both the N ratio and mean top-class confidence and route to chroma. It is correct, not broken.
- **MT3 returns empty for guitar-less songs.** Branch A still gives chords (from full mix). Branch B is empty. This is correct — no guitar was detected.
- **Pipeline is slow on first run.** Downloads model checkpoints on first invocation. Subsequent runs use cached models.
- **Chromat.chord() may not match MT3 results for the same song.** They use different methods and may disagree. The system reports which method produced each result.

- **Two-pass MT3 doubles analysis time.** Chords decode from the chord mix while
  solo decodes a second MT3 pass on the guitar stem. This is the correct trade
  for guitar-truthful solos; use async jobs/progress UI rather than expecting a
  single-pass runtime.
- **AI phrase practice regenerates the bed.** Jam snapshots store the backing
  prompt/key/BPM/progression but not the exact audio, so "practice this phrase"
  requests a new bed and clamps the loop to its duration.
- **Generated beds can be rejected.** If key/BPM verification fails confidently,
  the provider falls through to the next one (eventually bundled loops); the UI
  reports `provider` and `used_fallback` instead of pretending otherwise.
