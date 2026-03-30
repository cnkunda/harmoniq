# Harmoniq backend (FastAPI)

Local Python API for the Harmoniq analysis pipeline (YouTube / upload → stems → transcription → lesson JSON). **§3 (current):** `POST /analyze` and `GET /analyze/{job_id}` return an in-memory stub `LessonJSON` (no real pipeline). Earlier roadmap commit **0.2** added the runnable app shell.

## Requirements

- **Python 3.11+** (3.12 works; type hints and tooling assume ≥ 3.11)
- **ffmpeg** on your `PATH` (required by `yt-dlp`, `openai-whisper`, and typical audio normalization). Verify with `ffmpeg -version`.
- **Git** (some dependencies resolve VCS or large wheels; standard on macOS/Linux dev machines)

### PyPI note: Guitar Pro library

The roadmap names **`py-guitarpro`**; the installable distribution on PyPI is **`pyguitarpro`**. It is already listed under `[project] dependencies` in `pyproject.toml`.

## CPU vs GPU (PyTorch + Demucs)

- **Demucs** pulls **PyTorch**. On Linux/macOS/Windows, pip usually installs a **CPU** wheel by default — enough for development and smaller jobs.
- For **CUDA** acceleration, install a torch build that matches your driver **before** or **after** installing this package, following [PyTorch’s install matrix](https://pytorch.org/get-started/locally/), then install `harmoniq-backend` so `demucs` reuses that torch. Example (Linux, CUDA 12.x — adjust for your platform):

  ```bash
  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
  pip install -e .
  ```

- First demucs run downloads model weights; allow disk space and a warm network.

## Research notebook (PRIORITIES commit 1)

End-to-end feasibility proof: **ingest → ffmpeg (44.1 kHz mono) → Demucs `htdemucs_6s` → Librosa → Basic Pitch → `.gp5`**.

| Path | Role |
|------|------|
| `app/pipeline_proof.py` | Shared functions used by the notebook and future API code |
| `research/pipeline_proof.ipynb` | Jupyter walkthrough + CLI equivalents |
| `tests/test_pipeline_proof.py` | Fast unit tests (no Demucs run in CI by default) |

**Run the notebook**

```bash
pip install -e ".[notebook]"   # optional: JupyterLab + kernel
cd backend
jupyter lab research/pipeline_proof.ipynb
```

Set **`LOCAL_AUDIO`** or **`YOUTUBE_URL`** in the first code cell. Outputs go under `data/research_notebook/` (gitignored via `data/`).

**Tests**

```bash
pip install -e ".[dev]"
pytest
```

## Setup

From the **`backend/`** directory:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e .
# or: pip install -r requirements.txt
```

Copy environment template and edit:

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY when you implement coach calls; DATA_DIR defaults to ./data
```

The `data/` folder is gitignored except `.gitkeep`; stems and caches should land there in later commits.

## Run the dev server

**Makefile** (macOS/Linux, or Windows with GNU Make):

```bash
make dev
```

**Shell script** (Unix):

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

**Manual** (any OS):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Verify

- Health: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`
- Stub analyze: `curl.exe -s -X POST http://127.0.0.1:8000/analyze -H "Content-Type: application/json" -d '{"url":null}'` → `{"job_id":"…"}`; then `curl.exe -s http://127.0.0.1:8000/analyze/<job_id>` → `status":"complete"` and a stub `result` (JSON `LessonJSON` shape). Unknown id → **404** with `{"detail":"…"}`.
- Forced failure (smoke-test hook): POST `{"url":"force_error"}`; GET should transition to `status:"failed"` with a user-safe `error` string.
- Docs: open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — **Analyze** routes and schemas **`AnalyzeJobCreated`**, **`AnalyzeRequest`**, **`JobStatus`**, **`LessonJSON`**.

## Project layout

| Path | Role |
|------|------|
| `app/main.py` | `FastAPI` app, `/health`, stub `/analyze` routes |
| `app/schemas.py` | Pydantic models shared with OpenAPI |
| `app/pipeline_proof.py` | Notebook / feasibility audio → stems → Librosa → Basic Pitch → GP5 |
| `research/pipeline_proof.ipynb` | Commit 1 pipeline walkthrough |
| `tests/` | `pytest` targets (e.g. `test_pipeline_proof.py`) |
| `pyproject.toml` | Package metadata + pinned dependency set |
| `data/` | Local runtime output (stems, etc.) — ignored by git |
| `.env.example` | Template for API keys and `PIPELINE_VERSION` |

## Heavy dependencies

A full `pip install -e .` pulls **audio/ML** stacks (`librosa`, `openai-whisper`, `pyguitarpro`, `demucs`, …) and can take several minutes and **multiple GB** (especially PyTorch). That matches the roadmap’s default backend environment for stems, transcription, and Guitar Pro I/O.

### Optional: `basic-pitch`

**`basic-pitch`** is required for the eventual MIDI / pitch pipeline but declares TensorFlow constraints that **do not resolve with `pip` on Windows or Linux under Python 3.11+** (the resolver looks for `tensorflow<2.15.1`, which is unavailable for those platforms). It remains **pinned in this repo** under the optional extra `basicpitch`:

```bash
pip install -e ".[basicpitch]"
```

On **macOS**, that extra usually installs cleanly. If you are on Windows or Linux, track [basic-pitch](https://pypi.org/project/basic-pitch/) / TensorFlow updates, use a **conda** environment the project documents later, or install pitch tooling in a separate venv until upstream relaxes the pin.

## License / stack

Same as the parent Harmoniq repository. Not all upstream models (e.g. demucs checkpoints, whisper weights) are redistributed here — they download on first use.
