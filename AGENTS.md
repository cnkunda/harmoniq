# AGENTS.md — Harmoniq Factory Floor Manual

AMT research project + demo app. React Native + Expo (iOS, Android, Web) + FastAPI backend.
MT3-primary transcription with confidence-gated CRNN fallback and chroma last resort.

**One rule above all: if anything is unclear, ask. Do not guess.**

---

## TL;DR for agents

| Thing | Rule |
|-------|------|
| **Stack** | React Native + Expo (iOS, Android, Web) + FastAPI backend |
| **Path alias** | `@/*` maps to repo root — no relative imports like `../../foo` |
| **Lint** | `npm run lint` = `tsc --noEmit` (no ESLint) — **must pass 0 errors before commit** |
| **Pascal of camel?** | Component files = PascalCase. Modules, hooks, utils = camelCase. Constants = SCREAMING_SNAKE. |
| **Golden rules** | Never combine two commits. Never future-proof. Never silence an error. Ask when uncertain. |

---

## Setup & key commands

```bash
# Frontend
npm install
npx expo start               # native (iOS/Android)
expo start --web              # browser

# Backend (Python 3.11+, from backend/)
python -m venv .venv-wsl && source .venv-wsl/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# MT3 (primary transcription engine) — downloads ~600MB checkpoint
pip install -e ".[mt3]"
python scripts/download_mt3_checkpoint.py

# MRT2 backing tracks (optional — without this, bundled MP3 loops are used)
pip install -e ".[mrt2]"
mrt models init && mrt models download mrt2_small
```

| Command | What it does |
|---------|-------------|
| `npm run lint` | `tsc --noEmit` — zero errors required before every commit |
| `npm run test` | `vitest run` — unit test files |
| `npm run test:ui` | Playwright structural tests (non-visual) |
| `npm run test:visual` | Playwright visual regression |
| `npm run test:visual:update` | Update Playwright visual snapshots |
| `npm run test:mobile` | Detox E2E on Android emulator |
| `npm run test:mobile:ios` | Detox E2E on iOS simulator |
| `npm run audit:inventory` | Generate screen/component inventory |
| `npm run audit:platform` | Generate platform health audit |
| `npm run audit:ui` | Playwright route capture + vision-tool analysis -> UI/UX gap report |
| `npm run ux:improve` | Full UX improvement loop: capture → analyze → flag gaps |
| `npm run ux:verify` | Re-analyze existing screenshots (skip capture, just re-check) |
| `python -m pytest -q` | All backend tests (from `backend/`) |
| `python -m pytest -q tests/test_cqt_features.py tests/test_chord_augmentation.py tests/test_chord_metrics.py tests/test_inference_logic.py` | Chord model tests |
| `python -m pytest -q tests/test_viterbi_decoder.py tests/test_viterbi_chord_progression.py tests/test_chord_transitions.py` | Viterbi decoding tests |
| `python -m pytest -q tests/test_boundary_tie.py` | Boundary tie tests |
| `python scripts/clear_analysis_cache.py` | Clear cached song analyses |
| `python scripts/version_model.py --version X.Y.Z --weights app/chord_model.weights.h5 --log scripts/training_log.csv` | Archive model version to `research/h-gain-vX.Y.Z/` |
| `python scripts/promote_model.py --list` | Show all model versions and active status |
| `python scripts/promote_model.py --version X.Y.Z` | Promote version if better than active (gatekeeper) |
| `python scripts/promote_model.py --version X.Y.Z --force` | Force promote (skip metric check) |
| `python scripts/download_mt3_checkpoint.py` | Download MT3 T5-small checkpoint for transcription |
| `python scripts/quick_smoke_test.py` | Run quick pipeline validation on bundled test audio |
| `python scripts/pseudo_label_generate.py --audio-dir <dir>` | Generate MT3 pseudo-labels for all audio in a directory |

**Research / evaluation:**
| `python -m pytest -q tests/test_mt3_pipeline.py tests/test_mt3_accuracy.py tests/test_mt3_performance.py` | MT3 inference tests |
| `python -m pytest -q tests/test_guitarset_mt3_accuracy.py tests/test_guitarset_solo_accuracy.py` | GuitarSet vs MT3 accuracy |
| `python -m pytest -q tests/test_inference_logic.py` | Fallback chain logic tests |
| See also [`docs/RESEARCH.md`](docs/RESEARCH.md), [`docs/KNOWN_FAILURES.md`](docs/KNOWN_FAILURES.md), [`docs/EVALUATION.md`](docs/EVALUATION.md), and [`docs/blog/`](docs/blog/) |

## UX Improvement Loop (Playwright + vision-tool MCP)

Two MCPs drive automated UI/UX gap detection and self-healing:

- **Playwright MCP** — browser automation (navigation, screenshot capture)
- **vision-tool MCP** — image analysis via 23 vision backends (Gemini, Azure, Groq, etc.)

**Run from Git Bash** — frontend toolchain (npm, Node, Playwright) lives there.
Python/vision-tool runs in WSL — the scripts auto-detect Windows and call `wsl.exe python3` transparently.

### Workflow

```
npm run ux:improve  →  capture screenshots  →  analyze via vision-tool  →  flag gaps
      ↓
agent reads report → fixes code → re-runs → verify → loop until clean
```

1. **Start Expo web** in one terminal: `npm run web` (or `CI=1 npx expo start --web --port 8081`)
2. **Run loop** in another terminal: `npm run ux:improve` — captures all routes, analyzes via vision-tool, writes `docs/audit/ui-feedback-report.json`
3. Agent reads `allGapsByRoute` — each gap has `severity` (error/warning/info) and `issue` type
4. For each error/warning gap, agent inspects the route's source file and applies a targeted fix
5. Run `npm run ux:verify` to re-analyze existing screenshots (no new capture)
6. Loop up to 5 iterations until `isComplete: true`

### One-shot (no pre-started server)

If you don't have Expo running, Playwright can auto-start it:
```bash
PLAYWRIGHT_USE_WEBSERVER=1 npm run ux:improve
```
First run takes ~3 min (Expo cold start). Subsequent runs reuse the server.

### Agent instructions

Detailed step-by-step workflow in `.opencode/instructions/UX_IMPROVE_LOOP.md`.

**CI** (`.github/workflows/scoring-tests.yml`): runs frontend `vitest run` + backend pytest on 12 specific test files. Triggered on push to `main`/`master` and on all PRs.

---

## Code conventions

### TypeScript / React Native

**Naming**
| What | Convention | Example |
|------|-----------|---------|
| Component files | PascalCase | `AnimatedPressable.tsx` |
| Module / util files | camelCase | `chordFunction.ts`, `sm2.ts` |
| Hook files | camelCase with `use` prefix | `usePitchStream.ts` |
| Functions | camelCase | `getChordFunction()`, `sessionEntryHref()` |
| Types & interfaces | PascalCase | `ChordEvent`, `AnimatedPressableProps` |
| Exported constants | SCREAMING_SNAKE | `SESSION_STEPS`, `CENTS_TOLERANCE` |
| Local constants | camelCase | `const maxRetries = 3` |

**Imports**
- Always use `@/` absolute imports — never `../` or `../../`.
- Group: (1) third-party / Expo, blank line, (2) internal modules.
- Named exports preferred everywhere. Default exports **only** for Expo Router screen files (`app/` directory).
- Type-only imports: `import type { Foo } from '@/src/types'`.

**TypeScript**
- `strict: true` — no `any` unless unavoidable for interop (rare).
- Interfaces preferred for object shapes; unions for discriminated variants.
- `as const` for literal arrays/objects to derive union types.
- Explicit return types on all exported functions.

**Platform-specific files**
- Metro resolves `.native.ts` / `.web.ts` at bundle time.
- A plain `.ts` file acts as a type-only re-export stub (see `src/db/client.ts`, `src/pitch/usePitchStream.ts`).
- Shared interface goes in the `.ts` stub; implementations go in `.native.ts` and `.web.ts`.

**State management (Zustand)**
```typescript
// Store definition — src/stores/useAppStore.ts
import { create } from 'zustand'

interface AppState {
  volume: number
  setVolume: (v: number) => void
}

export const useAppStore = create<AppState>((set) => ({
  volume: 0.8,
  setVolume: (volume) => set({ volume }),
}))

// Subscription — always use selectors to avoid wasted re-renders
const volume = useAppStore((s) => s.volume)
```

**Comments**
- `/** JSDoc */` for all exported APIs, types, and public functions.
- `// Commit N:` reference to trace back to PRIORITIES.md spec.
- Section dividers: `// ---- Section ----`.
- No inline comments explaining *what* the code does (the code should be clear). Inline comments explain *why* a non-obvious choice was made.

**Error handling — fail loudly**
- No bare `catch (e) {}` — never silence errors.
- User-facing errors: `toast.error('Something went wrong: ' + message)`.
- Dev logging: `console.log('[ModuleName]', message)`.
- Backend: raise `HarmoniqAPIError` for known failure modes (caught by global handler).
- Backend feature toggles: `if os.getenv("HARMONIQ_SKIP_FOO", "").strip() == "1": raise HTTPException(503, ...)`.

### Python / FastAPI

| What | Convention | Example |
|------|-----------|---------|
| Files | snake_case | `viterbi_decoder.py` |
| Functions / variables | snake_case | `compute_flicker_rate()` |
| Classes | PascalCase | `ViterbiChordDecoder` |
| Constants | SCREAMING_SNAKE | `TIE_THRESHOLD = 0.3` |

- `from __future__ import annotations` at module top.
- Type hints on all function parameters and return values.
- Pydantic v2 models: `model_config = ConfigDict(extra="ignore")`.
- FastAPI routers in `app/routers/`.
- Imports order: stdlib, blank line, third-party, blank line, local.

---

## Architecture

### Session flow (7 steps, 4 phases + pre-flight)

Pre-flight: `tune` → `musical-tolerance`
Phase 1 (Orient): `listen`
Phase 2 (Isolate): `study`
Phase 3 (Refine): `slow` (`warmup` is a URL alias for `slow`)
Phase 4 (Apply): `play`
Phase 5 (Reflect): `review`

Defined in `src/constants/sessionFlow.ts` and `sessionPhases.ts`. Mood check gates the first daily session (`sessionEntryHrefWithMoodCheck`).

### Dual database

| Platform | Engine | Versions |
|----------|--------|----------|
| Mobile | SQLite via `expo-sqlite` | 14 migration versions |
| Web | IndexedDB + in-memory arrays | v4 (separate versioning) |

Shared contract: `HarmoniqDbClient` interface in `src/db/harmoniqDbClient.ts`. Platform resolution via `client.native.ts` / `client.web.ts`.

### Audio architecture

- `src/audio/GlobalAudioManager.ts` is a singleton — all audio instances go through it.
- Mobile mic: `react-native-audio-api` (dev build required, not Expo Go).
- Web mic: `getUserMedia` + `AudioWorklet` (requires HTTPS or localhost).
- Ghost recordings: on-disk files (native) vs inline base64 strings (web).

### Backend pipeline (MT3-primary)

- `POST /analyze` + `GET /analyze/{job_id}` run the full pipeline: Demucs → two-branch transcription (full-mix chord branch + guitar-conditioned solo branch with MR-MT3 leakage mitigation) → MusicXML → LessonJSON.
- **Primary transcription engine — two-branch architecture:**
  - **Branch A (chords, instrument-agnostic):** full mix or harmonic-bed submix → aggregate pitch/chroma representation (MT3 Flat granularity or dedicated chroma extractor) → template matching against `CHORD_INTERVALS`. Chord confidence reflects chroma clarity + template match quality, decoupled from guitar-stem separation.
  - **Branch B (solo, leakage-hardened):** guitar stem (Demucs) as soft prior + full mix as parallel feature → MT3-style token decoder conditioned on fixed guitar-program embedding, with MR-MT3 memory retention (previous-segment token context), prior token sampling, and token shuffling → post-hoc guitar-program token filter → melodic line with per-note confidence and per-section `leakage_risk` (0.0–1.0).
- **Fallback chain**: Branch A (chords): MT3 → CRNN TFLite on full mix → Chroma template matching. Branch B (solo): MT3 → Basic Pitch on guitar stem. The quality gate (`_neural_model_too_noisy()`) at line 541 bypasses the CRNN result when >80% of frames predict N (no-chord), falling through to chroma.
- **Basic Pitch caching**: `basic_pitch_predict_events()` in `pipeline_proof.py` caches results by audio path to avoid duplicate 60s+ inference between solo note extraction and tab generation.
- **On-device path**: CRNN TFLite model powers Live Mic Mode (<120ms latency) for chord detection. Long-term targets: (1) framewise chord student — non-autoregressive piano-roll model distilled from Branch A's output; (2) guitar-vocabulary token solo student — autoregressive model distilled from Branch B's program-conditioned output, structurally incapable of leaking non-guitar notes.
- **Custom model training** (`build_chord_tflite.py`): preserved for Phase 3 distillation. MT3 pseudo-labels will train two smaller student models (framewise chord + guitar-vocabulary solo).
- `torch==2.5.1` / `torchaudio==2.5.1` pinned — do not upgrade without testing Demucs.
- MT3 requires JAX; CPU fallback auto-activates CRNN path.

### MRT2 backing track generation

- `POST /jam/backing` generates practice backing tracks via **MRT2 (Magenta RealTime 2)** — open-weights generative audio model (2.4B / 230M params).
- `backend/app/jam_backing.py`: `Mrt2BackingGenerator` singleton, lazy-loaded on first request. Falls back to bundled MP3 loops when MRT2 is unavailable.
- Setup: `pip install "harmoniq-backend[mrt2]"` then `mrt models init && mrt models download mrt2_small`.
- Text prompt built from `style_hint + musical_key + bpm` → MusicCoCa embedding → MRT2 generates 48kHz stereo WAV.
- Offline (non-realtime) inference — generation takes ~2-5 min on CPU, returned as base64 WAV.

### Expo Router routing

- Every file under `app/` is a route. No manual registration.
- Hidden tabs (`design-preview`, `analyze-debug`) set `href: null` in tab config — reachable via `router.push()` only.
- Dynamic routes: `[param]` directories, e.g. `app/onboarding/phrase/[index].tsx`.
- Screen components in `app/` must be `export default` (Expo Router requirement).

### Path alias

`@/*` → repo root. Configured in `tsconfig.json` and `vitest.config.ts`. Any new test files with `@/` imports must match.

---

## Design system

### Colors (`src/constants/colors.ts`, not `constants/Colors.ts`)

| Token | Hex | Usage |
|-------|-----|-------|
| `wood.900` | `#2C1810` | Deepest backgrounds |
| `wood.800` | `#3D2317` | Surface cards |
| `wood.700` | `#3D2B1F` | Card backgrounds |
| `amber.accent` | `#D4A574` | Primary accent |
| `amber.light` | `#E8B86D` | Active tint / secondary accent |
| `cream` | `#F5E6D0` | Primary text |
| `danger` | `#C17B5F` | Missed notes (terracotta) |
| `success` | `#7A9B6D` | Hit notes (sage) |

### Typography

| Use | Font | Class |
|-----|------|-------|
| Display / headings | Playfair Display | `font-serif`, `font-serif-bold` |
| Body / UI labels | DM Sans | `font-sans`, `font-sans-medium` |
| Tab / monospace | JetBrains Mono | `font-mono` |

### Component rules

| Do | Don't |
|----|-------|
| Use `AnimatedPressable` from `components/AnimatedPressable.tsx` | Use bare `Pressable` |
| Use `toast.success()` / `toast.error()` helpers | Use `Toast.show()` directly |
| Use `lucide-react-native` icons | Use Phosphor or Material icons |
| Use `react-native-reanimated` for animations | Use `Animated` from React Native core |
| Use NativeWind `className` + Tailwind classes | Use `StyleSheet.create()` |
| Use `NoiseOverlay` for background texture | Use solid color backgrounds |
| Use `WoodGradient` (`expo-linear-gradient`) | Use CSS gradients |

### Animation philosophy

Slow and intentional — "jazz club lighting, not mobile game." Shared spring/timing presets in `src/constants/animations.ts`. Opacity modifiers: `bg-wood-800/40`, `border-wood-600/50`.

---

## Testing

### Framework map

| Framework | What for | Where | Run command |
|-----------|----------|-------|-------------|
| Vitest | Unit tests | `src/` (co-located `*.test.ts`) | `npm run test` |
| Playwright | E2E + visual regression | `tests/ui/` | `npm run test:ui` / `npm run test:visual` |
| Detox | Mobile E2E | `tests/mobile/` | `npm run test:mobile` |
| pytest | Backend tests | `backend/tests/` | `python -m pytest -q` |

### Vitest patterns

```typescript
import { describe, it, expect } from 'vitest'
import { getChordFunction } from './chordFunction'

describe('getChordFunction', () => {
  it('returns tonic function for I chord in C major', () => {
    const result = getChordFunction('C major', 'C:maj')
    expect(result).toEqual({ roman: 'I', label: 'Tonic — Home base' })
  })
})
```

- Tests co-located next to their source module.
- All test files run in CI (`vitest run`).

### Playwright patterns

- Chromium only (config in `playwright.config.ts`).
- Visual regression uses `maxDiffPixelRatio: 0.02`, `threshold: 0.2`.
- Tag visual tests with `@visual` in test name.

### pytest patterns

```python
"""Tests for Commit 99: Viterbi chord decoder."""
from __future__ import annotations
import numpy as np
import pytest
from app.viterbi_decoder import ViterbiChordDecoder

class TestViterbiDecoder:
    def test_basic_decoding(self):
        decoder = ViterbiChordDecoder(...)
        result = decoder.decode(...)
        assert len(result) > 0
```

- Fixtures defined as `@pytest.fixture` in test files.
- 10 specific test files run in CI (scoring + chord model + Viterbi + boundary tie).

### Pre-submit checklist

Before every commit:
- [ ] `npm run lint` passes (0 errors) — **mandatory even for backend-only changes**
- [ ] `python -m pytest -q` passes from `backend/` (if backend changed)
- [ ] New code has co-located unit tests (if adding logic)
- [ ] No `console.log` / `print` left in production code (debug logging with prefixes is fine)

---

## Commit conventions

### Message format

Descriptive subject line. No strict conventional commits. Reference PRIORITIES.md commit numbers when applicable.

```
feat: Commit 99 — Viterbi Decoding for Chord Progressions
Fix button padding regression: revert AnimatedPressable migration in 3 files
Backend API modularization — feature-specific routers
```

### Scope discipline

- One commit = one spec from PRIORITIES.md. Never combine two.
- No refactoring of unrelated code — the diff must be minimal.
- No future-proofing abstractions ("we might need this later").

### Workflow

Full 6-phase process in `docs/CODER.md` (read before implementing a commit):
1. Extract & restate the spec
2. Plan (TODO list — no code yet)
3. Build (lint after every file)
4. Test (happy path + complex + failure)
5. Audit (scope, quality, correctness, acceptance criteria)
6. Complete (verify, update PRIORITIES.md)

### Anti-patterns — never do these

- Write code before planning
- Swallow exceptions silently
- Add "it might be useful later" abstractions
- Combine two commits into one
- Refactor unrelated code while implementing
- Guess when the spec is ambiguous — ask instead

---

## Key files to read first

| File | Why |
|------|-----|
| `PRIORITIES.md` | Full engineering roadmap with commit-level specs |
| `docs/CODER.md` | Commit implementation workflow (6-phase process) |
| `docs/E2E_DEMO.md` | End-to-end walkthrough with checkpoints |
| `docs/MIGRATIONS.md` | Database migration strategy and version history |
| `README.md` | Product spec, backend pipeline, DB schema, 5-step loop |
| `.github/copilot-instructions.md` | Legacy copilot context (partially stale) |
| `src/config.ts` | API URL resolution and feature flags |
| `src/constants/sessionFlow.ts` | Session step ordering and entry logic |
| `src/constants/sessionPhases.ts` | 4-phase pedagogical model |
| `src/constants/colors.ts` | Real color palette (not `constants/Colors.ts`) |
| `src/db/harmoniqDbClient.ts` | DB interface contract |

---

---

## Dataset Pipeline (Chord Model Training)

### Data sources

| Dataset | Scripts | Status | Path | CQT windows |
|---------|---------|--------|------|-------------|
| **GuitarSet** | `download_guitarset.py` → `parse_guitarset.py` → `extract_guitarset_cqt.py` | ✅ Ready | `data/guitarset` | 360 |
| **IDMT-SMT-Guitar** | `download_idmt_smt_guitar.py` → `parse_idmt_smt_guitar.py` → `extract_idmt_cqt.py` | ✅ Ready | `data/idmt_smt_guitar` | 129 |
| **VST Synthetic** | `generate_synthetic_midi.py` → `render_synthetic_guitar.py` | ✅ Ready | `data/vst_synthetic` | 5,640 |
| **YouTube Crawl** | `crawl_chord_videos.py` → `extract` inline | ✅ Ready | `data/youtube_crawl` | 264 |
| **Guitar-TECHS** | `download_guitar_techs.py` → `parse_guitar_techs.py` → `extract_guitar_techs_cqt.py` | ✅ Ready | `data/guitar_techs` | 68 |
| **EGSet12** | `download_egset12.py` → `parse_egset12.py` → `extract_egset12_cqt.py` | ✅ Ready | `data/egset12` | 12 |
| **JAAH** (annotations only) | `download_jaah.py` | ⚠️ No audio | `data/annotations/jaah` | — |
| **DAMP-VPB** | (withdrawn) | ❌ Unavailable | — | — |
| **EGDB-PG** | `download_egdb_pg.py` (135 GB) | ⏸️ Skipped | — | — |
| **Pseudo-label** | `pseudo_label_pipeline.py` | ✅ Ready | `data/pseudo_label` | 1 file |

### Pipeline commands

```bash
# From backend/

# --- GuitarSet — already complete ---
python scripts/download_guitarset.py && python scripts/parse_guitarset.py && python scripts/extract_guitarset_cqt.py

# --- IDMT-SMT-Guitar — already complete ---
python scripts/download_idmt_smt_guitar.py && python scripts/parse_idmt_smt_guitar.py && python scripts/extract_idmt_cqt.py

# --- VST Synthetic — already complete ---
python scripts/generate_synthetic_midi.py && python scripts/render_synthetic_guitar.py

# --- YouTube Crawl — already complete ---
python scripts/crawl_chord_videos.py

# --- Guitar-TECHS (4.1 GB) ---
python scripts/download_guitar_techs.py
python scripts/parse_guitar_techs.py
python scripts/extract_guitar_techs_cqt.py

# --- EGSet12 (110 MB) ---
python scripts/download_egset12.py
python scripts/parse_egset12.py
python scripts/extract_egset12_cqt.py

# --- JAAH (annotations only; requires Smithsonian audio for CQT) ---
python scripts/download_jaah.py
python scripts/extract_jaah_cqt.py --audio-dir /path/to/smithsonian/audio   # optional

# --- EGDB-PG (135 GB, optional) ---
python scripts/download_egdb_pg.py   # Not yet extracted
```

### Full training command

```bash
# First, generate CQT distribution statistics for synthetic-to-real domain bridging
python scripts/cqt_distribution_analyzer.py \
  --guitarset-data-dir data/guitarset \
  --idmt-data-dir data/idmt_smt_guitar \
  --output data/cqt_stats.npz

# Main training with domain gap matching + pseudo-labels
python scripts/build_chord_tflite.py \
  --guitarset-data-dir data/guitarset \
  --idmt-data-dir data/idmt_smt_guitar \
  --vst-data-dir data/vst_synthetic \
  --youtube-data-dir data/youtube_crawl \
  --guitar-techs-data-dir data/guitar_techs \
  --egset12-data-dir data/egset12 \
  --pseudo-data-dir data/pseudo_label \
  --empirical-matrix data/annotations/transition_matrix_empirical.npy \
  --cqt-stats-path data/cqt_stats.npz \
  --temperature 0.3
```

Two-stage fine-tuning:
```bash
# Stage 1: main training
python scripts/build_chord_tflite.py ...(args above)...

# Stage 2: rare-chord boost
python scripts/build_chord_tflite.py ...(args above)... --temperature 0.1 --rare-boost

# Stage 3: QAT → INT8 TFLite
python scripts/build_chord_tflite.py ...(args above)... --qat-only
```

### Chord matching algorithm (Guitar-TECHS & EGSet12)

Both datasets derive chord labels from MIDI note data rather than explicit chord annotations:
- **Guitar-TECHS**: Parses per-string `.mid` files via `pretty_midi` → aggregate pitch sets per 0.1s frame → match against `CHORD_INTERVALS` template set (Jaccard score, >0.66 coverage threshold)
- **EGSet12**: Extracts MIDI note events from JAMS `note_midi` namespace → same pitch-set-to-chord matching

### Data flow per source

1. Audio → `librosa.cqt()` → 40-bin features (36 chroma + 4 bass) at 0.1s hop
2. Labels → 128-frame overlapping windows (12.8s context, 50% hop) with center-frame label
3. `.npz` output at `<data_dir>/processed/cqt/<track_id>.npz`
4. `build_chord_tflite.py::load_dataset_dir()` reads all `.npz` files, filters out `split="test"` rows

---

## Appendix: Common traps

- **Expo Router default exports**: Screen files under `app/` must use `export default`. Everything else uses named exports.
- **Env var prefixes**: Frontend uses `EXPO_PUBLIC_HARMONIQ_SKIP_*`, backend uses `HARMONIQ_SKIP_*`. Mixing them up = silent no-op.
- **Ghost recording paths**: Native stores recordings on disk; web stores inline base64. Test assertions must account for both.
- **MT3 / JAX**: MT3 requires JAX for GPU inference. The CRNN TFLite fallback activates automatically when JAX/TPU is unavailable. basic-pitch / TensorFlow is no longer a primary pipeline dependency (was the solo inference engine before MT3).
- **CSS grid**: Not available in React Native. Use `flex-row flex-wrap` instead.
- **WSL networking**: Use LAN IP (`192.168.x.x`) in both `EXPO_PUBLIC_API_URL` and `HARMONIQ_CORS_ORIGINS` so physical devices can reach the backend.
- **Starter song**: "Gravity" by John Mayer (G major pentatonic) — the default if no song is added.
