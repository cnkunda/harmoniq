# Known Pipeline Failures & Limitations

This document tracks known failure modes in the Harmoniq transcription pipeline.
Last updated: July 2026

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

## Frontend

| Scenario | Symptom | Root Cause | Workaround |
|----------|---------|------------|------------|
| Web mic requires HTTPS | `getUserMedia` blocked on HTTP | Browser security requirement | Use `http://localhost` for development |
| AlphaTab WebView on older Android | Tab rendering crashes | Underlying Chromium WebView version | Update WebView via Play Store |
| Large lesson files (>10MB) | Slow initial render | Full MusicXML + audio stems loaded at once | Lazy-load sections |

## Known Not-Bugs

These behaviors are intentional but may look like bugs:

- **CRNN predicts N on unfamiliar audio.** The quality gate checks this and routes to chroma. It is correct, not broken.
- **MT3 returns empty for guitar-less songs.** Branch A still gives chords (from full mix). Branch B is empty. This is correct — no guitar was detected.
- **Pipeline is slow on first run.** Downloads model checkpoints on first invocation. Subsequent runs use cached models.
- **Chromat.chord() may not match MT3 results for the same song.** They use different methods and may disagree. The system reports which method produced each result.
