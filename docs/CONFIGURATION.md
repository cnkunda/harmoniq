# Configuration and Environment Variables

Last updated: 2026-11-12. This is the reference for every environment variable the
backend reads. Defaults below are the values used when the variable is unset;
the source of truth is always the code.

## How configuration is loaded

- **Backend:** `backend/app/main.py` calls `load_dotenv(backend/.env)` when the
  uvicorn app is imported. Copy [`backend/.env.example`](../backend/.env.example)
  to `backend/.env` and edit locally.
- **Celery worker caveat:** the worker command is
  `celery -A app.celery_app worker` and does **not** import `app.main`, so it
  does **not** read `backend/.env`. Export the variables in the worker shell or
  run it through Docker Compose, which supplies them as container environment.
- **Frontend:** the root `.env` is read by Expo. Only `EXPO_PUBLIC_*` variables
  are exposed to the bundle. Copy [`.env.example`](../.env.example) to `.env`.
- **Docker Compose:** `docker-compose.yml` sets `DATABASE_URL_SYNC`,
  `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, and
  `HARMONIQ_CORS_ORIGINS` for the `api` and `worker` services; those values win
  over local files.

`Required` legend:

| Value | Meaning |
| --- | --- |
| **No** | Has a safe local default; override only when needed. |
| **Production** | Must be set explicitly in production; the default is a dev-only credential/URL. |
| **For feature** | Only needed to enable that optional integration. |
| **Test-only** | Set by pytest or CI; never set in production. |

Booleans are read as the literal string `"1"` unless noted; unset or any other
value means off.

## Quick local setup

```bash
cp backend/.env.example backend/.env
cp .env.example .env
```

For CPU-only development, `HARMONIQ_SKIP_MT3=1` and `HARMONIQ_SKIP_CELERY=1`
give the fastest pipeline without the MT3 checkpoint or a worker process.

## Backend reference

### Core / API

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `PORT` | `8000` | No | `app/routers/ws.py` | Port used to build the default WebSocket API base. |
| `HARMONIQ_API_BASE` | `http://localhost:$PORT` | No | `app/routers/ws.py` | Public API origin for WebSocket URLs. |
| `HARMONIQ_CORS_ORIGINS` | localhost:8081 and :19006 | No | `app/main.py` | Extra browser origins, comma-separated. Merged with localhost defaults; not needed for loopback. |
| `HARMONIQ_VERSION` | `0.1.0` | No | `app/tracing.py` | Reported as `service.version`. |
| `OTEL_TRACING_ENABLED` | `false` | No | `app/tracing.py` | `1`/`true`/`yes` enables OpenTelemetry. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | For feature | `app/tracing.py` | OTLP collector; only used when tracing is enabled. |

### Database and persistence

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://harmoniq:harmoniq_dev@localhost:5432/harmoniq` | Production | `app/db.py` | Sync SQLAlchemy URL. The fallback uses the dev Compose credentials. |
| `DATA_DIR` | `./data` | No | `app/ingest.py` | Root for uploads, stems, cache, and artifacts. Relative paths anchor to `backend/`. |
| `REDIS_URL` | `redis://localhost:6379/0` | No | `app/job_store.py`, `app/routers/ws.py`, `app/tasks.py` | Job state, SSE pub/sub, and DLQ. |
| `HARMONIQ_JOB_TTL_HOURS` | `24` | No | `app/job_store.py` | Redis job-key expiry. |
| `HARMONIQ_DLQ_MAX_ENTRIES` | `1000` | No | `app/job_store.py` | Dead-letter queue cap. |
| `HARMONIQ_OPERATOR_TOKEN` | unset | No | `app/routers/analyze.py` | Enables `X-Operator-Token` auth for DLQ endpoints. When unset, loopback is allowed. |
| `HARMONIQ_ALLOW_REMOTE_OPERATOR` | off | No | `app/routers/analyze.py` | `1` allows non-loopback DLQ access **only safely when `HARMONIQ_OPERATOR_TOKEN` is set**. |
| `HARMONIQ_SKIP_CLEANUP` | off | No | `app/main.py` | `1` disables the startup job-data cleanup loop. |
| `HARMONIQ_CLEANUP_RETENTION_DAYS` | `7` | No | `app/main.py` | Retention window for cleanup. |

### Queue / Celery

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | No | `app/celery_app.py` | Celery broker. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | No | `app/celery_app.py` | Celery result backend. |
| `HARMONIQ_SKIP_CELERY` | off | No | `app/jobs.py` | `1` runs analysis in-process instead of dispatching to Celery (no worker needed). **Local/dev/test only** — staging/production require the Compose `worker`. `/health` reports `job_runtime=thread` and `status=degraded` when this is set. |

### Analysis pipeline

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `HARMONIQ_SKIP_MT3` | off | No | `app/analyze_audio.py`, `app/main.py` | `1` skips the MT3 tier and uses CRNN/chroma. Recommended on CPU. |
| `HARMONIQ_SKIP_DEMUCS` | off | No | `app/separate.py`, `app/demucs_engine.py` | `1` skips stem separation. |
| `HARMONIQ_SKIP_STEMS` | off | No | `app/separate.py` | `1` skips stem separation (production override). |
| `HARMONIQ_FAST_STEMS` | off | No | `app/separate.py` | `1` uses `htdemucs_ft` instead of `htdemucs_6s` (faster, lower quality). |
| `HARMONIQ_DEMUCS_MODEL` | `htdemucs_6s` | No | `app/pipeline_proof.py` | Demucs model name. |
| `HARMONIQ_DEMUCS_DEVICE` | auto | No | `app/pipeline_proof.py` | Force a Demucs device (`cpu`, `cuda`, ...). |
| `HARMONIQ_SKIP_AUDIO_QUALITY_GATE` | off | No | `app/audio_quality.py` | `1` bypasses ingest quality rejection (metrics still recorded). |
| `HARMONIQ_SKIP_BASIC_PITCH` | off | No | `app/tabgen.py` | `1` skips Basic Pitch solo fallback. |
| `HARMONIQ_SKIP_WHISPER` | off | No | `app/transcribe.py` | `1` skips lyric transcription. |
| `HARMONIQ_WHISPER_MODEL` | `base` | No | `app/transcribe.py` | Whisper model size/name. |
| `HARMONIQ_SKIP_EXPORT` | off | No | `app/exporter.py` | `1` skips MusicXML/GP5 export. |
| `HARMONIQ_SKIP_TRANSCRIPTION_VERIFY` | off | No | `app/routers/analyze.py` | `1` skips the post-transcription verification step. |
| `HARMONIQ_SKIP_THEORY_ANNOTATE` | off | No | `app/coach.py` | `1` skips theory annotation. |

### MT3 teacher

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `HARMONIQ_MT3_CHECKPOINT_DIR` | backend checkpoint dir | No | `app/teachers/mt3_infer.py` | Override the MT3 checkpoint root. |
| `HARMONIQ_MT3_INFER_PATH` | unset | No | `app/teachers/mt3_infer.py` | Path to a local `mt3_infer` package checkout. |
| `HARMONIQ_TEACHER_PYTHON` | current interpreter | No | `app/teachers/mt3_infer.py` | Python used for the MT3 subprocess. |
| `HARMONIQ_TEACHER_TIMEOUT_S` | `1800` | No | `app/teachers/mt3_infer.py` | MT3 subprocess timeout in seconds. |
| `HARMONIQ_TEACHER_DEVICE` | `cpu` | No | `app/teachers/mt3_infer.py` | MT3 subprocess device. |
| `HARMONIQ_TEACHER_CUDA_VISIBLE_DEVICES` | `0` | No | `app/teachers/mt3_infer.py` | Re-enables GPUs for the PyTorch worker when `HARMONIQ_TEACHER_DEVICE` starts with `cuda`. |
| `HARMONIQ_TEACHER_AUTO_DOWNLOAD` | off | No | `app/teachers/mt3_infer.py` | `1` allows automatic checkpoint download. |

### Student / chord model

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `HARMONIQ_STUDENT_ENABLED` | off | No | `app/student/inference.py` | `1` enables the student model path. |
| `HARMONIQ_STUDENT_MODEL_DIR` | `backend/data/models/student` | No | `app/student/inference.py` | Student artifact directory. |
| `HARMONIQ_STUDENT_SOLO` | `1` | No | `app/student/inference.py` | `0` disables solo inference on the student path. |
| `CHORD_MODEL_PATH` | `models/chord_model.tflite` | No | `app/model_server.py` | CRNN TFLite model path. |
| `HARMONIQ_TFLITE_FLEX` | `0` | No | `app/model_server.py` | `1` enables TFLite Flex delegate. |
| `HARMONIQ_CONFIDENCE_GATE` | off | No | `app/confidence_thresholds.py` | `1` enables the W5 calibrated MT3 gate. **Not release-ready** (see code comment). |
| `HARMONIQ_DRIFT_BASELINE` | `models/drift_baseline.npy` | No | `app/drift_detection.py` | Drift baseline artifact path. |

### Tablature assignment

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `HARMONIQ_SKIP_TAB_ASSIGNMENT` | off | No | `app/tab_assignment.py` | `1` keeps pitch-only solo notes without string/fret. |
| `HARMONIQ_TAB_ASSIGNMENT_MODE` | `dp` | No | `app/tab_assignment.py` | `dp` (playability-aware) or `baseline`. |
| `HARMONIQ_TAB_TUNING` | `standard` | No | `app/tab_assignment.py` | Tuning name from `app.fretting.tuning`. |
| `HARMONIQ_TAB_CATALOG` | `stub` | No | `app/tab_catalog/provider.py` | `stub` or `none`. |

### Coach / LLM

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | unset | For feature | `app/coach.py`, `app/jobs.py`, `app/main.py`, `app/routers/mentor.py`, `app/tasks.py` | Coach, enrichment, mentor. Missing/rejected keys degrade to skipped, not failed. |
| `HARMONIQ_MODEL_ID` | `claude-haiku-4-5-20251001` | No | `app/coach.py`, `app/mentor.py` | Claude model for coach/mentor. |
| `HARMONIQ_COACH_TIMEOUT_MS` | `8000` | No | `app/coach.py` | Coach request timeout. |
| `HARMONIQ_CHORD_ENRICHMENT_MODEL` | `claude-haiku-4-5-20251001` | No | `app/chord_enrichment.py` | Chord-enrichment model. |
| `HARMONIQ_CHORD_ENRICHMENT_TIMEOUT_MS` | `12000` | No | `app/chord_enrichment.py` | Enrichment request timeout. |
| `HARMONIQ_SKIP_CHORD_ENRICHMENT` | off | No | `app/chord_enrichment.py` | `1` skips chord enrichment. |
| `HARMONIQ_SKIP_MENTOR` | off | No | `app/routers/mentor.py` | `1` disables `POST /mentor/trajectory`. |
| `HARMONIQ_MENTOR_TIMEOUT_MS` | `20000` | No | `app/mentor.py` | Mentor request timeout. |
| `HARMONIQ_SKIP_PRACTICE_PLAN` | off | No | `app/routers/curriculum.py` | `1` uses template intros instead of a Claude batch call. |
| `HARMONIQ_SKIP_CURRICULUM` | off | No | `app/routers/curriculum.py` | `1` disables curriculum ranking. |
| `HARMONIQ_SKIP_STYLE_DETECT` | off | No | `app/style_detect.py` | `1` forces style label `general` with no technique hints. |
| `HARMONIQ_SKIP_LYRIA_CLIP` | off | No | `app/lyria_clip.py` | `1` skips Lyria orient clips. |

### Spotify / taste

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `HARMONIQ_SKIP_SPOTIFY` | off | No | `app/spotify.py` | `1` disables Spotify integration. |
| `HARMONIQ_SKIP_SPOTIFY_PLAYBACK` | off | No | `app/main.py` | `1` skips playback polling (static tab mode). |
| `HARMONIQ_SKIP_TASTE_DERIVE` | off | No | `app/routers/taste.py` | `1` skips `POST /taste/derive`. |
| `SPOTIFY_CLIENT_ID` | unset | For feature | `app/spotify.py` | Spotify OAuth client id. |
| `HARMONIQ_SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8000/auth/spotify/callback` | For feature | `app/spotify.py` | Must match the Spotify dashboard. |
| `HARMONIQ_SPOTIFY_WEB_RETURN` | `http://127.0.0.1:8081` | No | `app/spotify.py` | Post-OAuth web return URL. |
| `HARMONIQ_SPOTIFY_APP_SCHEME` | `harmoniq` | No | `app/spotify.py` | Deep-link scheme for native return. |

### Jam backing providers

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `HARMONIQ_BACKING_PROVIDERS` | `ace_step_modal,lyria,mrt2,bundled` | No | `app/music_generation/registry.py` | Ordered provider chain; `synth` is always appended last. |
| `HARMONIQ_BACKING_TIMEOUT_S` | `45` | No | `app/music_generation/service.py`, `app/music_generation/providers.py` | Per-attempt deadline. The provider module's own fallback is `60` when the service value is absent; the effective chain deadline is `45`. |
| `HARMONIQ_ACE_STEP_BACKING_URL` | unset | For feature | `app/music_generation/registry.py` | Warm ACE-Step endpoint. |
| `HARMONIQ_MODAL_TOKEN` | unset | For feature | `app/music_generation/registry.py` | Bearer token for the ACE-Step endpoint. |
| `HARMONIQ_LYRIA_BACKING_URL` | unset | For feature | `app/music_generation/registry.py` | Warm Lyria endpoint. |
| `GEMINI_API_KEY` | unset | For feature | `app/music_generation/registry.py` | Bearer token for the Lyria endpoint. |

### AlphaTab prerender

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `HARMONIQ_ENABLE_PRERENDER` | off | No | `app/alphatab_prerender.py` | `1` enables Node-based AlphaTab prerender. |
| `HARMONIQ_SKIP_PRERENDER` | off | No | `app/alphatab_prerender.py` | `1` overrides the enable flag (CI/fast paths). |

### Test-only

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `PYTEST_CURRENT_TEST` | unset | Test-only | Multiple modules | Set automatically by pytest. Routes skip heavy ML/external calls and allow loopback operator access. |
| `HARMONIQ_ENABLE_COACH_IN_TESTS` | off | Test-only | `app/coach.py`, `app/routers/mentor.py` | `1` lets tests exercise real coach calls despite `PYTEST_CURRENT_TEST`. |
| `HARMONIQ_ENABLE_ENRICHMENT_IN_TESTS` | off | Test-only | `app/chord_enrichment.py` | `1` lets tests exercise real enrichment despite `PYTEST_CURRENT_TEST`. |

## Deprecated or ignored names

These appear in older examples or local `.env` files but are not read by the
backend. Do not add new uses.

| Variable | Status | Reason |
| --- | --- | --- |
| `DATABASE_URL` | Deprecated | The app only reads `DATABASE_URL_SYNC` (`app/db.py`); removed from Compose in Commit 4. |
| `PIPELINE_VERSION` | Not an env var | Cache version is the module constant `app.cache.PIPELINE_VERSION`. |
| `LYRIA_MODEL` | Unused | Not read anywhere in the backend. |
| `GEMINI_API_BASE` | Unused | Not read anywhere in the backend. |
| `MINIMAX_API_KEY` | Unused | Not read anywhere in the backend. |
| `HARMONIQ_ENRICHMENT_MODEL` | Unused | Use `HARMONIQ_CHORD_ENRICHMENT_MODEL`. |

## Frontend (Expo) reference

These live in the root `.env` and are read by the client. Non-`EXPO_PUBLIC_*`
values are not exposed to the bundle.

| Variable | Default | Required | Owner area | Notes |
| --- | --- | --- | --- | --- |
| `EXPO_PUBLIC_API_URL` | `http://localhost:8000` | No | `src/config.ts` | Backend origin; use a LAN IP for physical devices. |
| `EXPO_PUBLIC_HARMONIQ_SKIP_TTS` | off | No | Coach voice | `1` skips all client TTS (CI/headless). |
| `EXPO_PUBLIC_HARMONIQ_SKIP_SPOTIFY_PLAYBACK` | off | No | Listening mode | `1` renders static tab mode without playback polling. |
| `EXPO_PUBLIC_HARMONIQ_PITCH_JSI` | off | No | `src/config.ts` | `1` uses the native C++/JSI YIN detector; requires a development build. |
| `EXPO_PUBLIC_HARMONIQ_SKIP_SKILL_MUTATION` | off | No | `src/config.ts` | `1` skips technique EMA persistence after Review. |
| `HARMONIQ_SKIP_SKILL_MUTATION` | off | No | `src/config.ts` | Unprefixed alias accepted by the client for the same flag. |
| `EXPO_PUBLIC_ALPHATAB_RUNTIME_DIAG` | off | No | `docs/MANUAL_QA.md` | `0` forces AlphaTab runtime diagnostics off. |

## Verification

The guard test compares this file against literal `os.getenv(...)` and
`os.environ.get(...)` reads under `backend/app/`:

```bash
cd backend
python -m pytest -q tests/test_configuration_docs.py
```

The equivalent manual check (does not catch single-quoted or multi-line calls):

```bash
rg --no-filename -o 'os\.getenv\("[A-Z0-9_]+"' backend/app | sort -u
```

Seven names are read through variables and cannot be found by a literal scan;
they are documented above: `HARMONIQ_CONFIDENCE_GATE`,
`HARMONIQ_ENABLE_PRERENDER`, `HARMONIQ_SKIP_PRERENDER`,
`HARMONIQ_ACE_STEP_BACKING_URL`, `HARMONIQ_MODAL_TOKEN`,
`HARMONIQ_LYRIA_BACKING_URL`, and `GEMINI_API_KEY`.
