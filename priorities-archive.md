# Harmoniq — Engineering Roadmap Archive

This file contains completed work from Phase 0 and all Phase 1 commits (1-97), archived during the Phase 1 → Phase 2 transition.

**Phase 1 Archive Date:** May 14, 2026

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

## Commits 86-97 — Phase 1 Completion

### Commit 86: Placement Session Logic

**Goal:** SQLite logic to initialize skill_nodes (e.g., bend_accuracy) based on onboarding performance.

**Scope:**
- Onboarding placement session scoring
- SQLite schema for initial skill node population
- Radial skill graph driven by real scores (not mock data)

**Acceptance Criteria:**
- [x] 3 AlphaTab snippets load real GP5 data
- [x] Mic → pitch stream → score path populates initial skill nodes
- [x] Radial skill graph displays real scores from placement session

**Completed:** 2026-04-22

---

### Commit 87: Global Audio Manager

**Goal:** Implement centralized audio architecture to prevent context bloat and handle hot-swapping between screens.

**Scope:**
- Global Audio Manager singleton for all expo-av and react-native-audio-api instances
- Hot swap logic for deep-linking scenarios (e.g., Single File → Full Practice)
- Audio buffer clearing without app crashes
- Support for 6+ parallel audio streams (Demucs stems) + mic input

**Acceptance Criteria:**
- [x] Global Audio Manager singleton controls all audio instances
- [x] Hot swap clears audio buffers without crashes
- [x] No "Audio Stutter" or "Ghost Tracks" after session exit
- [x] Deep-linking from Single File to Full Practice works seamlessly
- [x] 6-stem isolation + mic input managed without bloat

**Completed:** 2026-04-22

---

### Commit 88: Versioned Database Migration Strategy

**Goal:** Implement schema migration system to prevent data loss during app updates as LessonJSON structure evolves.

**Scope:**
- Versioned migration strategy for SQLite (mobile) and IndexedDB (web)
- Migration path for skill_nodes table changes (e.g., Jazz Extensions support)
- Backward compatibility for early beta testers' practice history
- Mastery percentage preservation across schema updates

**Acceptance Criteria:**
- [x] expo-sqlite migrations implemented with version tracking
- [x] IndexedDB migration system for web parity
- [x] skill_nodes schema changes have migration path
- [x] Beta testers retain practice history after app updates
- [x] Mastery percentages preserved across schema migrations
- [x] Rollback mechanism for failed migrations

---

### Commit 89: Predictive UI Rendering

**Goal:** Eliminate visual lag perception by scrolling 50ms before audio reaches timestamp using look-ahead buffer.

**Scope:**
- Look-ahead buffer in usePitchStream hook
- Predictive scrolling for SmartScroll and AlphaTab cursor
- 50ms advance rendering for playback cursor
- Cross-platform implementation (web + native)

**Acceptance Criteria:**
- [x] Predictive scrolling implemented with 50ms look-ahead
- [x] SmartScroll scrolls 50ms before audio timestamp
- [x] AlphaTab cursor highlights notes 50ms early
- [x] Visual sync feels "intelligent" and "pro"
- [x] No perceived lag during playback

---

### Commit 90: AI Coach Variation Agents

**Goal:** Prevent feedback redundancy by varying AI coach focus areas across sessions.

**Scope:**
- Focus area parameter for Claude coach prompts
- Coach "Moods" or "Foci" system (Timing, Vibrato, Dynamics, etc.)
- Session-to-session variation in feedback emphasis
- Avoid repetitive template feedback

**Acceptance Criteria:**
- [x] Claude coach accepts focus_area parameter
- [x] 7 focus areas implemented (Timing, Vibrato, Dynamics, Phrasing, Bending, Rhythm, Expression)
- [x] Focus area varies between sessions
- [x] Feedback doesn't feel like repeated template
- [x] User feedback collection infrastructure in place

---

### Commit 91: Harmonic Similarity Discovery Agent

**Goal:** Implement song discovery based on harmonic similarity to keep users engaged in the Harmoniq ecosystem.

**Scope:**
- Harmonic similarity analysis between songs
- Discovery agent suggesting next songs based on mastered content
- Context-aware recommendations
- Integration with dynamic session engine

**Acceptance Criteria:**
- [x] Harmonic similarity algorithm implemented
- [x] Discovery agent generates song recommendations
- [x] Recommendations based on user's mastered skills/progress
- [x] UI displays discovery suggestions with context
- [x] One-tap deep-link to analyze recommended songs

---

### Commit 92: Musical Tolerance Scoring Modes

**Goal:** Implement "Musical Tolerance" setting to balance accuracy with expressive playing in scoring engine.

**Scope:**
- Expressive mode (lenient timing for musical feel)
- Technique mode (strict timing for precision practice)
- Musical tolerance configuration in scoring algorithm
- User-selectable scoring modes

**Acceptance Criteria:**
- [x] Scoring engine supports musical tolerance parameter
- [x] Expressive mode allows timing drag/push (±50-100ms tolerance)
- [x] Technique mode enforces strict timing (±20ms tolerance)
- [x] User can select scoring mode per session
- [x] Mode preference saved to user profile
- [x] Scoring feedback reflects selected mode's philosophy

---

### Commit 93: Backend API Modularization

**Goal:** Refactor the monolithic `main.py` into feature-specific routers.

**Scope:**
- `backend/app/routers/` (analyze, export, discovery, taste, curriculum)
- Centralized error handling and dependency injection
- Health checks and CORS isolation

**Acceptance Criteria:**
- [x] Backend integration tests pass after migration
- [x] No circular dependencies in router imports
- [x] Clear separation of concerns

---

### Commit 94: Automated Job Data Cleanup

**Goal:** Lifecycle management for backend temporary data to prevent storage bloat.

**Scope:**
- `backend/scripts/cleanup_data.py`
- Pruning logic for `.tmp_test_data_*` and old `data/jobs/` artifacts
- Background task or cron job for periodic execution

**Acceptance Criteria:**
- [x] Cleanup script safely removes orphaned temp folders
- [x] Configurable retention period (e.g., 7 days)
- [x] Dry-run mode for safe verification

---

### Commit 95: ML Inference Stability & Diagnostics

**Goal:** Resolve TensorFlow loading warnings and optimize inference fallback performance.

**Scope:**
- Fix `AttributeError: '_UserObject'` in `solo_inference.py`
- Improve ONNX fallback logging and performance
- Standardize model loading across chord and solo engines

**Acceptance Criteria:**
- [x] Backend logs are free of model loading warnings
- [x] Cold-start inference time reduced
- [x] Detailed diagnostics for model mismatch errors

---

### Commit 96: Unified Player UX Parity

**Goal:** Standardize the "Rich Player" card layout across all session practice screens.

**Scope:**
- Update `app/session/play.tsx` and `app/session/slow.tsx` to match `study.tsx`
- Refine `TabViewport.tsx` card padding and header alignment
- Unified "Lyrics Strip" visibility logic

**Acceptance Criteria:**
- [x] Consistent header/controls/lyrics layout across all 3 practice steps
- [x] No layout shifting when toggling lyrics or variants

---

### Commit 97: Functional Gap Closures

**Goal:** Complete pending functional requirements for orientation clips and UI state persistence.

**Scope:**
- Implement `backend/app/lyria_clip.py` for orientation hints
- Add `AsyncStorage` persistence for user preferences (`tabVariant`, `showLyrics`)
- Refine "Seek to Start" to ensure perfect audio/cursor sync

**Acceptance Criteria:**
- [x] Orient-as-hint clips generated correctly for all songs
- [x] User preferences survive app restarts
- [x] Seek-to-start resolves within 50ms transport sync

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
