# Resources

This document lists key external resources used in the Harmoniq platform.

## AlphaTab Documentation

- **URL**: https://alphatab.net/docs/introduction
- **Description**: Official documentation for AlphaTab, the library used for rendering guitar tablature and sheet music in the app.
- **Utilization**: Referenced in AlphaTab components (`components/AlphaTab*.tsx`) and backend tab processing.

## MT3: Multi-Task Multitrack Music Transcription

- **Paper**: https://openreview.net/pdf?id=iMSjopcOn0p (ICLR 2022 Spotlight)
- **Code**: https://github.com/magenta/mt3
- **Description**: Google Magenta's Transformer-based model for multi-instrument automatic music transcription. Demonstrates that a single general-purpose Transformer can jointly transcribe arbitrary combinations of instruments across multiple datasets, with strong results for low-resource instruments like guitar.
- **Utilization**: The TieRegistry active-note tracking mechanism in `backend/app/solo_inference.py` (commit 100) follows the MT3-style approach for merging notes across segment boundaries. Informs the boundary tie and overlap-and-blend design for solo transcription.

## Nicolas Slonimsky - Thesaurus of Scales and Melodic Patterns

- **URL**: https://www.lapetitedistribution.org/archive/Nicolas_Slonimsky.pdf
- **Description**: Classic reference work on scales, patterns, and finger exercises by Nicolas Slonimsky, used as inspiration for warmup exercises.
- **Utilization**: Basis for Slonimsky-inspired exercises in `backend/app/exercises/warmup_pool.json` and warmup screens.


