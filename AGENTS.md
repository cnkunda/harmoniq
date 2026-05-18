# AGENTS.md — Harmoniq

> AI-powered adaptive guitar learning app. React Native + Expo (iOS, Android, Web).

---

## Dev setup

```bash
# 1. Frontend deps (macOS / Linux)
npm install

# 2. Backend (requires WSL on Windows; Python 3.11+)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Copy env files
cp .env.example .env            # root: set EXPO_PUBLIC_API_URL
cp backend/.env.example backend/.env
```

```bash
# 4. Start backend (hot-reload)
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Start frontend
npx expo start        # native (iOS/Android)
expo start --web      # browser
```

- **Backend must be running before the app starts** — the app pings `EXPO_PUBLIC_API_URL` on launch.
- Default API URL is `http://localhost:8000`. Change in `.env` or `app.config.ts` → `extra.apiBaseUrl`.
- For WSL: use your LAN IP (`192.168.x.x`) in both `.env` and `backend/.env` (`HARMONIQ_CORS_ORIGINS`) so a physical phone can reach it.

## Typical development workflow

For optimal development experience, run each component in its own terminal:

1. **Frontend (Git Bash)**: Run `npx expo start` for native or `expo start --web` for browser
2. **Backend (WSL)**: Activate `.venv-wsl` and run `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. **Agent**: Use opencode in a separate terminal for code modifications

---

## Key commands

| Command | What it does |
|---------|-------------|
| `npm run lint` | `tsc --noEmit` — no ESLint in this repo |
| `npm run test` | `vitest run` — unit tests only |
| `npm run test:ui` | Playwright structural tests (non-visual) |
| `npm run test:visual` | Playwright visual regression |
| `npm run test:visual:update` | Update visual snapshots |
| `npm run test:mobile` | Detox E2E on Android emulator |
| `npm run test:mobile:ios` | Detox E2E on iOS simulator |
| `npm run audit:inventory` | Generate screen/component inventory |
| `npm run audit:platform` | Generate platform health audit |
| `python -m pytest -q` | Backend tests (from `backend/`) |
| `python scripts/clear_analysis_cache.py` | Clear cached song analyses |

**CI workflow** (`scoring-tests.yml`): runs `pytest tests/test_jam_score.py tests/test_score.py` (backend) + `vitest run` on 3 specific test files (frontend).

---

## Architecture traps an agent will miss

### Platform-specific file resolution
- `.native.ts` / `.web.ts` suffixes are resolved by Metro at bundle time.
- `src/db/client.ts` is a **type-only re-export** — it does not contain logic. Metro swaps in `client.native.ts` or `client.web.ts`.
- Shared hooks (e.g. `usePitchStream.ts`) follow the same pattern: shared file for types, `.native.ts` and `.web.ts` for implementations, with a stub `.ts` for TypeScript-only.

### Path alias
- `@/*` maps to `./*` (the repo root). Used ubiquitously as `@/src/...`, `@/components/...`.
- Vitest config has a matching alias — if you add new test files, the alias must resolve.

### Expo Router file-based routing
- Every file under `app/` becomes a route. No manual route registration.
- Hidden tabs (`design-preview`, `analyze-debug`) have `href: null` — reachable via `router.push()` only.
- Dynamic routes use `[param]` directories, e.g. `app/onboarding/phrase/[index].tsx`.

### Session flow (7 steps, 4 phases)
Pre-flight steps (**not** in any phase): `tune` → `musical-tolerance`
Phases: **orient** (`listen`) → **isolate** (`study`, `slow`) → **apply** (`play`) → **reflect** (`review`)
- Defined in `src/constants/sessionFlow.ts` (`SESSION_STEPS`) and `src/constants/sessionPhases.ts`.
- Mood check gates the first daily session (see `sessionEntryHrefWithMoodCheck`).
- `warmup` URL maps to the `slow` step index (alias, not a real step).

### Dual database
- **Mobile**: SQLite via `expo-sqlite`, full migration system with rollback (14 versions).
- **Web**: IndexedDB + in-memory arrays, simpler persistence, separate versioning (v4).
- Migrations: `src/db/schema.ts` (SQL constants), `src/db/client.native.ts` (runner), `src/db/migrations.ts` (validation).
- DB interface: `src/db/harmoniqDbClient.ts`.

### Audio architecture
- `src/audio/GlobalAudioManager.ts` is a **singleton** — all audio instances go through it.
- Mic recording uses `react-native-audio-api` on mobile (requires **dev build or release build**, not Expo Go).
- Web mic uses `getUserMedia` + `AudioWorklet` — requires HTTPS or `localhost`.
- Ghost recordings: on-disk (native) vs inline base64 (web).

### Backend pipeline (stub state)
- `POST /analyze` and `GET /analyze/{job_id}` return **in-memory stub** `LessonJSON` — no real ML pipeline yet.
- Full pipeline (Demucs, librosa, whisper, basic-pitch, pyguitarpro) is scaffolded but gated on ML infra.
- `basic-pitch` requires TensorFlow — **does not install on Windows/Linux** with Python 3.11+. See `backend/README.md` workaround.
- `torch==2.5.1` / `torchaudio==2.5.1` are pinned to avoid TorchCodec issues. Do not upgrade without testing Demucs.

---

## Design system notes

- **Real color palette** lives in `src/constants/colors.ts` (not `constants/Colors.ts`, which has the Expo template palette).
- Wood/amber/cream theme throughout. Animations should be slow and intentional — "jazz club lighting, not mobile game."
- Icons: `lucide-react-native` (native + web). Do not use Phosphor or Material icons.
- Toast config: `components/ToastConfig.tsx` — use `toast.success()` / `toast.error()` helpers.
- Pressables: use `AnimatedPressable` from `components/AnimatedPressable.tsx`, not bare `Pressable`.

---

## Testing quirks

- **Vitest**: only 3 test files run in CI (`aggregatePlacementScores`, `sm2`, `scoreProgressSignals`). Other test files exist but are not in CI.
- **Playwright**: Chromium only. Visual regression uses `maxDiffPixelRatio: 0.02`, `threshold: 0.2`.
- **Detox**: Android emulator (`Pixel_7_API_34`), iOS simulator (`iPhone 15`). Jest config at `tests/mobile/jest.config.js`.
- **Starter song**: "Gravity" by John Mayer (G major pentatonic) — the default if no song is added.

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
| `src/db/harmoniqDbClient.ts` | DB interface contract |