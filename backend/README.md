# Harmoniq backend (FastAPI)

Local Python API for the Harmoniq analysis pipeline (YouTube / upload → stems → transcription → lesson JSON). This package is introduced in roadmap commit **0.2**: runnable app, health check, OpenAPI stubs only — no real jobs yet.

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
- Docs: open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — you should see **`AnalyzeRequest`**, **`JobStatus`**, and **`LessonJSON`** under *Schemas*, plus **Stubs** operations that return **501** until the pipeline is implemented.

## Project layout

| Path | Role |
|------|------|
| `app/main.py` | `FastAPI` app, `/health`, stub `/analyze` routes |
| `app/schemas.py` | Pydantic models shared with OpenAPI |
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
