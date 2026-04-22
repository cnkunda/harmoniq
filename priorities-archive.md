# Harmoniq — Engineering Roadmap Archive

This file contains completed work from Phase 0 and commits 1-85, archived during the Phase 1 → Phase 2 transition.

**Archive Date:** April 22, 2026

---

## Phase 0 — Foundation (Complete)

| Commit | Summary |
|--------|---------|
| 0.1 | Expo + Router + NativeWind + fonts + tooling |
| 0.2 | FastAPI scaffold, health, stub analyze routes, Pydantic shapes |
| 0.3 | Noise overlay, WoodGradient, component stubs, design-preview |
| 0.4 | AlphaTab harness HTML + `tabMessage` types |
| 0.5 | `.env` / `API_BASE_URL`, backing tracks, `docs/` placeholders |
| 0.6 | `AnimatedPressable`, `LoadingSkeleton`, `EmptyState`, `ErrorBanner`, Toast, `src/api/analyze.ts`, animation presets |

---

## Commits 1-85 — Complete

### Phase 1: Product Discovery & Core Loop (Foundational)

| # | Title | Phase |
|---|--------|--------|
| 1 | Notebook proof pipeline | 1 |
| 2 | Stem separation quality gate | 1 |
| 3 | FastAPI skeleton analyze | 1 |
| 4 | Async job runner | 1 |
| 5 | Upload + YouTube → WAV | 1 |
| 6 | Demucs in job | 1 |
| 7 | librosa analysis | 1 |
| 8 | Whisper lyrics | 1 |
| 9 | basic-pitch → GP5 + confidence | 1 |
| 10 | Analysis cache | 1 |
| 11 | Claude coach strings | 1 |
| 12 | Expo audio scaffold | 2 |
| 13 | Playback matrix doc | 2 |
| 14 | Multi-stem mixer | 2 |
| 15 | Mic + pitch web | 2 |
| 16 | Mic + pitch native | 2 |
| 17 | Pitch QA protocol | 2 |
| 18 | API client + lesson store | 2 |
| 19 | Session router 5 steps | 2 |
| 20 | Listen step | 2 |
| 21 | AlphaTab WebView | 2 |
| 22 | AlphaTab web DOM | 2 |
| 23 | SmartScroll | 2 |
| 24 | Study step | 2 |
| 25 | Slow & loop | 2 |
| 26 | Play step | 2 |
| 27 | Review step | 2 |
| 28 | POST /score | 3 |
| 29 | SQLite schema | 3 |
| 30 | SM-2 scheduler | 3 |
| 31 | Home suggestion | 3 |
| 32 | Onboarding placement | 3 |
| 33 | Add Song | 4 |
| 34 | Transpose lick + filters | 4 |
| 35 | Progress screen | 4 |
| 36 | Jam mode | 4 |
| 37 | Settings | 4 |
| 38 | IndexedDB web + cache | 4 |
| 39 | Error copy + mic blocked | 4 |
| 40 | E2E demo + release checklist | 4 |
| 41 | Library + drill | 4 |
| 45 | AlphaTab external media sync | 5 |
| 46 | AlphaTab MIDI note events -> pitch ladder | 5 |
| 47 | SoundFont upgrade + real backing tracks | 5 |
| 48 | AI-adaptive lesson plan (player profile -> coach) | 5 |
| 49 | Play step real-time per-note accuracy | 5 |
| 50 | Metronome - lookahead scheduling + beat flash | 5 |
| 51 | Slow step frame-accurate loop + region UI | 5 |
| 52 | Study step interactive fretboard + NoteDetailCard | 5 |
| 53 | Study tab-aligned note payload + alternate fingerings | 5 |
| 54 | Jam scale overlay on fretboard + AlphaTab | 5 |
| 55 | Feel Real QA checklist | 5 |
| 56 | AlphaTab formatting templates + styling presets | 5 |
| 57 | AlphaTab song details + section metadata panel | 5 |
| 58 | AlphaTab exporter path (PDF/PNG/MusicXML/MIDI) | 5 |
| 59 | Node-side AlphaTab pre-render service | 5 |
| 60 | Multiple SoundFonts + auto profile selection | 5 |
| 61 | AlphaTab runtime telemetry kill switch | 5 |
| 62 | Pre-session tuner + mic noise calibration | 6 |
| 63 | Skill node mutation from session accuracy | 6 |
| 64 | Left-handed mode fretboard parity *(skipped)* | 6 |
| 65 | Adaptive curriculum routing (ZPD suggestion) | 6 |
| 66 | Coach async streaming + retry architecture *(complete)* | 7 |
| 67 | Spotify OAuth + listening history ingestion *(complete)* | 7 |
| 68 | Taste graph → style profile + song candidates *(complete)* | 7 |
| 69 | Cold-start taste quiz *(complete)* | 7 |
| 70 | Ordered drill sequencer — structured practice plan | 7 |
| 71 | Guided path home — practice queue UX | 7 |
| 72 | Voice coach — TTS narration | 7 |
| 73 | Session warm-up generator *(complete)* | 7 |
| 74 | Riff DNA — personal playing fingerprint *(complete)* | 7 |
| 75 | Ghost player — play alongside past self *(complete)* | 7 |
| 76 | Mood-adaptive session intensity | 7 |
| 77 | Listening mode — Spotify playback + tab follow | 7 |
| 78 | Audio Pipeline: Demucs Stems & Beat Grid Engine | 8 |
| 79 | ML Inference: TFLite Chords & Basic Pitch Solo | 8 |
| 80 | Score Assembly: MusicXML Generation | 8 |
| 81 | Frontend Rendering: alphaTab & Fretboard Sync | 8 |
| 82 | Transcription Confidence & Collaborative Verification | 8 |
| 83 | Session flow restructure: Orient → Isolate → Apply → Reflect | 8 |
| 84 | Orient phase: Lyria 3 Clip technique examples | 8 |
| 85 | Theory layer in Study step *(complete)* | 8 |

---

## Detailed Commit Specifications

The detailed specifications for commits 75-85 are preserved in the main PRIORITIES.md file under their respective sections for reference during Phase 2 planning.

---

## Technology Resolution Notes (Archived)

`DESIGN_SYSTEM.md` has been **fully rewritten** for the React Native + Expo stack — it is now the canonical UI reference. The original web-prototype libraries are replaced as follows:

| Concern | Was (web prototype) | **Is (production)** |
|---|---|---|
| Routing | `react-router-dom` | **Expo Router** — file-based, `app/` directory (SDK 54) |
| Icons | `lucide-react` | **`lucide-react-native`** on native; `lucide-react` on web via `.web.tsx` platform split |
| Animations | `framer-motion` | **`react-native-reanimated` v4** — iOS, Android, and Web |
| Interaction feedback | none | **`AnimatedPressable`** (see DESIGN_SYSTEM Interaction Patterns) + **`expo-haptics`** |
| Skill graph | `recharts` RadarChart | **`react-native-svg`** custom radar — or `victory-native` (decide at commit 35) |
| Styling | Tailwind `className` (web only) | **NativeWind v4** — same `className` API, now cross-platform |
| State | mock `useAppStore` | **Zustand** slices backed by `expo-sqlite` (from commit 18) |
| Tab display | `<pre>` ASCII art | **AlphaTab** — themed harness in `assets/alphatab-harness/index.html` (Phase 0) |
| Toast | none | **`react-native-toast-message`** with wood-themed config (Phase 0) |
| API client | fetch ad-hoc | **`src/api/analyze.ts`** typed client with polling (Phase 0) |
| Loading states | none | **`LoadingSkeleton`** Reanimated pulse component (Phase 0) |
| Empty states | none | **`EmptyState`** component (Phase 0) |
| Error feedback | none | **`ErrorBanner`** inline component (Phase 0) |
