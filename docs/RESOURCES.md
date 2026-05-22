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

## ChordMiniApp

- **URL**: https://chordmini.me
- **GitHub**: https://github.com/ptnghia-j/ChordMiniApp
- **Paper**: https://arxiv.org/abs/2602.19778 (Enhancing Automatic Chord Recognition via Pseudo-Labeling and Knowledge Distillation)
- **Description**: Open-source music analysis tool from UCLA research program. Features chord recognition (Chord-CNN-LSTM, BTC-SL, BTC-PL models), beat tracking (Beat-Transformer, madmom), song segmentation (SongFormer), guitar diagrams (@tombatossals/chords-db), piano visualizer, and synchronized lyrics. Built with Next.js + Flask.
- **Utilization**: Reference for section detection improvements (Commit 115b/115c), chord diagram integration (Commit 115d), and chord model benchmarking. Their BTC-PL and BTC-SL models are candidates for accuracy comparison against Harmoniq's CRNN.

## BTC-ISMIR19 (Bidirectional Transformer for Chord Recognition)

- **GitHub**: https://github.com/jayg996/BTC-ISMIR19
- **Description**: Bidirectional Transformer model for automatic chord recognition, presented at ISMIR 2019. Uses pseudo-labeling and knowledge distillation to improve chord recognition accuracy over traditional CNN-LSTM approaches.
- **Utilization**: Candidate model for chord recognition benchmarking against Harmoniq's CRNN (Commit 98 series). The BTC architecture with pseudo-labeling may offer improved accuracy on extended chord types (7ths, 9ths, altered dominants).




