# Harmoniq

**Practice less. Sound more like yourself.**

Harmoniq is an AI-powered guitar practice companion for intermediate players who already know their way around the fretboard but want to solo more expressively. Upload a song (YouTube URL or audio file), and the app isolates the guitar, builds a tab with chord timeline, then walks you through a 7-step session — Tune, Musical Tolerance, Listen, Study, Slow, Play, Review — with real-time fretboard highlighting and AI coaching feedback that sounds like a patient musician, not a robot.

Built for iOS, Android, and Web from a single React Native codebase.

---

## Screenshots

> _Add screenshots to `docs/screenshots/` and reference them here._

| Session loop | Fretboard sync | Jam mode |
|---|---|---|
| <!-- `docs/screenshots/session.png` --> | <!-- `docs/screenshots/fretboard.png` --> | <!-- `docs/screenshots/jam.png` --> |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      React Native + Expo                     │
│    iOS / Android / Web  •  Expo Router (file-based routes)   │
│    Zustand state  •  AlphaTab tab rendering  •  Reanimated   │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP + SSE
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Python)                  │
│  POST /analyze  →  GET /analyze/{id}  →  SSE job stream     │
│  POST /score    •  POST /jam-score    •  POST /export        │
│  POST /exercises/generate  •  Coach hydration (Anthropic)    │
└──────────────────────────────┬───────────────────────────────┘
                               │
                  ┌────────────┼────────────┐
                  ▼            ▼            ▼
           ┌──────────┐ ┌──────────┐ ┌──────────────┐
           │ Demucs   │ │ TFLite   │ │ basic-pitch  │
           │ 6-stem   │ │ chord    │ │ note events  │
           │ separation│ │ inference│ │              │
           └──────────┘ └──────────┘ └──────────────┘
```

### ML Pipeline (per analysis job)

1. **Ingest** — `yt-dlp` (YouTube) or audio upload → normalized WAV (44.1 kHz mono)
2. **Stem separation** — Demucs `htdemucs_6s` → guitar, bass, drums, vocals, piano, other
3. **Beat grid + key** — Librosa tempo/beat tracking, Krumhansl–Schmuckler key estimation
4. **Chord inference** — TFLite CRNN (277 classes, attention + BiLSTM, 128-frame window)
5. **Solo transcription** — basic-pitch MIDI note events → quantized to beat grid
6. **Lyrics** — Whisper on vocals stem, word-level timestamps snapped to beats
7. **MusicXML** — Beat grid + chord timeline + solo notes → MusicXML score
8. **Coach** — Anthropic Claude generates study explanations and session reviews

---

## Tech Stack

| Layer | Tools |
|-------|-------|
| **Frontend** | React Native, Expo SDK 54, Expo Router, Zustand, Reanimated, NativeWind, AlphaTab |
| **Backend** | Python 3.11+, FastAPI, Uvicorn |
| **ML / Audio** | Demucs, TFLite (custom CRNN model), basic-pitch, Whisper, librosa |
| **AI Coach** | Anthropic Claude API |
| **DB** | SQLite (mobile), IndexedDB (web) |
| **Testing** | Vitest, Playwright, Detox, Pytest |
| **Infra** | Docker (in progress) |

---

## Quick Start

### Prerequisites

- Node.js 20+, npm
- Python 3.11+ (WSL recommended on Windows)
- ffmpeg, yt-dlp

### Frontend

```bash
npm install
npx expo start        # native
expo start --web      # browser
```

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set ANTHROPIC_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Windows note:** Demucs and some ML deps work best in WSL. See `backend/README.md` for the WSL setup path.

---

## Testing

```bash
npm run lint              # tsc --noEmit (TypeScript)
npm run test              # vitest run (unit tests)
npm run test:ui           # Playwright structural tests
npm run test:visual       # Playwright visual regression
cd backend && python -m pytest -q
```

CI runs on push/PR via `.github/workflows/ci.yml`.

---

## Session Flow

The practice loop is 7 steps across 5 pedagogical phases:

```
Pre-flight         Orient        Isolate       Refine       Apply        Reflect
───────────   ──────────────   ──────────   ──────────   ──────────   ──────────
  tune          listen          study         slow         play         review
mood-check
musical-tol
```

- **Orient** — Hear the isolated guitar stem, key, and scale context
- **Isolate** — Study the tab with chord symbols and fretboard overlay
- **Refine** — Slow practice at 65% with pitch-corrected playback and SmartScroll
- **Apply** — Play along with the backing track (mic active, real-time pitch indicator)
- **Reflect** — AI review: waveform comparison, specific feedback, next-step suggestion

---

## Project Structure

```
harmoniq/
├── app/                  # Expo Router pages (file-based routes)
│   ├── session/          # 7-step practice loop screens
│   ├── onboarding/       # Placement session & skill assessment
│   └── (tabs)/           # Home, library, jam, progress, settings
├── components/           # Reusable UI (FretboardDiagram, WaveformVisualizer, etc.)
├── src/
│   ├── audio/            # GlobalAudioManager, pitch detection
│   ├── context/          # MusicContext (chord events, playback position)
│   ├── db/               # SQLite (mobile) / IndexedDB (web) — dual DB layer
│   ├── music/            # Chord function, scale matching, progression analysis
│   └── session/          # Session state, scoring, smart scroll
├── backend/
│   ├── app/              # FastAPI routes, ML pipeline, coaches, exporters
│   │   ├── routers/      # analyze, export, discovery, taste, curriculum
│   │   ├── chord_model.tflite   # 277-class CRNN (1.1 MB)
│   │   └── musicxml_builder.py  # Score generation (MusicXML 3.1, DTD-validated)
│   ├── scripts/          # build_chord_tflite.py, smoke_stems.py, alphatab_prerender.mjs
│   └── tests/            # 36 test files (incl. musicxml corpus + DTD fixtures)
├── docs/                 # CODER.md, E2E_DEMO.md, MIGRATIONS.md, audit, AlphaTab limitations
└── PRIORITIES.md         # Engineering roadmap with commit-level specs
```

---

## Roadmap

Phase 0 + Phase 1 are complete. Phase 2 (ML refinement + production infrastructure) is active. Full roadmap: [`PRIORITIES.md`](PRIORITIES.md).

**Current status:** 277-class chord model (CRNN + attention, val_acc ~82%), Viterbi post-processing planned. Backend uses in-memory job queue (pending Redis/Celery upgrade). MusicXML is the canonical score format: the analyzer emits a DTD-valid MusicXML 3.1 score (beat grid + chord timeline + solo notes + tab staff), it is persisted as `score.musicxml` on the analysis, and AlphaTab renders it directly on web and native (GP5 as fallback for legacy lessons). Known AlphaTab importer gaps: [`docs/ALPHATAB_MUSICXML_LIMITATIONS.md`](docs/ALPHATAB_MUSICXML_LIMITATIONS.md).

---

## Known Limitations

- **Synthetic training data only** — the chord model is trained on synthetically generated chroma templates, not real audio. Real-data training is planned (PRIORITIES Commit 101).
- **Tab catalog is a stub** — `GET /tabs/search` returns placeholder data; swap `app/tab_catalog/provider.py` for a licensed catalog API.
- **AlphaTab MusicXML importer is experimental upstream** — 24-case corpus (DTD-valid, no-crash rendered) gates regressions; visual fidelity of chord diagrams and non-standard tunings is not baselined. See [`docs/ALPHATAB_MUSICXML_LIMITATIONS.md`](docs/ALPHATAB_MUSICXML_LIMITATIONS.md).
- **basic-pitch requires TensorFlow** — does not install cleanly on Windows/Linux Python 3.11+; tests stub this via `HARMONIQ_SKIP_BASIC_PITCH`.
- **TFLite model uses Flex ops** — requires `tensorflow-lite-select-tf-ops` on mobile for inference.
- **No user accounts** — local-first, no cloud sync.
- **Web mic requires HTTPS** — `getUserMedia` is blocked on non-localhost HTTP.

---

## License

MIT
