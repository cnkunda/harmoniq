"""Modal app: Chord 170 data preparation (Phase 2).

Phase 2 delivers the reproducible data pipeline; CQT caches and the derived
label/bass sidecars live on a Modal Volume so training runs (Phase 3) never
recompute features.

Prerequisites (once)::

    pip install modal && modal token new
    modal volume create harmoniq-chord170-data
    modal volume create harmoniq-chord170-runs

    # Upload the repo bundle (code + data/) the same way the W3 app expects it:
    tar -czf /tmp/chord170_bundle.tgz -C <repo-root> backend docs manifest.json
    modal volume put harmoniq-chord170-data /tmp/chord170_bundle.tgz /chord170

Run (from backend/)::

    modal run scripts/modal_chord_170.py::status
    modal run --detach scripts/modal_chord_170.py::prepare
    modal run --detach scripts/modal_chord_170.py::prepare --extract-rwc true
    modal volume get harmoniq-chord170-data /chord170/docs/audit/amt/chord170_phase2_dataset.json ./

Later phases extend this app with ``train``/``eval``/``sweep``/``export``
(GPU A10G/A100); Phase 2 intentionally ships only prepare + introspection.
"""

from __future__ import annotations

import os
import subprocess

import modal

app = modal.App("harmoniq-chord170")

# TensorFlow GPU image carries the CUDA/cuDNN stack; BTC inference needs torch
# (CPU is fine for labeling on this image) and chord-mix extraction needs
# demucs. Phase 3 training uses tensorflow (200-class CRNN student).
image = (
    modal.Image.from_registry("tensorflow/tensorflow:2.20.0-gpu")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "pydantic>=2.0",
        "numpy>=1.26",
        "scipy>=1.11",
        "librosa>=0.10.2",
        "soundfile>=0.13",
        "scikit-learn>=1.3",
        "pretty_midi>=0.2.10",
        "mir_eval>=0.8",
        "tqdm>=4.67",
        "torch==2.5.1",
        "huggingface_hub>=0.20",
    )
    .env(
        {
            "TF_USE_LEGACY_KERAS": "1",
            "TF_CPP_MIN_LOG_LEVEL": "2",
            "PYTHONUNBUFFERED": "1",
        }
    )
)

data_volume = modal.Volume.from_name("harmoniq-chord170-data", create_if_missing=True)
runs_volume = modal.Volume.from_name("harmoniq-chord170-runs", create_if_missing=True)

ROOT = "/chord170"
BACKEND = f"{ROOT}/backend"
REPORT_DIR = f"{ROOT}/docs/audit/amt"
RUNS = "/runs"


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def _find_bundle_root() -> str | None:
    if os.path.isdir(os.path.join(ROOT, "backend")):
        return ROOT
    try:
        entries = sorted(os.listdir(ROOT))
    except FileNotFoundError:
        return None
    for name in entries:
        candidate = os.path.join(ROOT, name)
        if os.path.isdir(os.path.join(candidate, "backend")):
            return candidate
    return None


def _apply_root(root: str) -> None:
    global BACKEND, REPORT_DIR
    BACKEND = os.path.join(root, "backend")
    REPORT_DIR = os.path.join(root, "docs", "audit", "amt")


def _ensure_bundle() -> None:
    root = _find_bundle_root()
    if root is not None:
        _apply_root(root)
        return

    import tarfile

    for dirpath, dirnames, filenames in os.walk(ROOT):
        depth = dirpath[len(ROOT):].count(os.sep)
        if depth > 1:
            dirnames[:] = []
            continue
        if "chord170_bundle.tgz" in filenames:
            tarball = os.path.join(dirpath, "chord170_bundle.tgz")
            print(f"[setup] extracting {tarball}", flush=True)
            with tarfile.open(tarball) as archive:
                archive.extractall(dirpath)
            data_volume.commit()
            root = _find_bundle_root()
            if root is not None:
                _apply_root(root)
                return

    raise FileNotFoundError(
        "Chord 170 bundle not found on the Modal volume. Upload it first:\n"
        "  tar -czf /tmp/chord170_bundle.tgz -C <repo-root> backend docs\n"
        "  modal volume put harmoniq-chord170-data /tmp/chord170_bundle.tgz /chord170"
    )


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update({"PYTHONUNBUFFERED": "1", "TF_USE_LEGACY_KERAS": "1"})
    return env


def _run(command: list[str]) -> str:
    print("[run] " + " ".join(command), flush=True)
    process = subprocess.Popen(
        command, cwd=BACKEND, env=_env(), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
    )
    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    returncode = process.wait()
    output = "".join(lines)
    if returncode != 0:
        raise RuntimeError(
            f"command failed ({returncode}): {' '.join(command)}\n{output[-4000:]}"
        )
    return output


@app.function(
    image=image,
    cpu=8,
    memory=32768,
    timeout=8 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def prepare(extract_rwc: str = "false", datasets: str = "all") -> str:
    """Build CQT caches + label/bass sidecars + dataset card on the volume."""
    _ensure_bundle()
    output = ""
    if _truthy(extract_rwc):
        # RWC-P audio is opt-in (CC BY-NC 4.0); extraction runs on the volume.
        # Timelines (from the annotation CSVs) must exist before CQT extraction.
        output += _run(["python", "scripts/parse_rwc.py"])
        output += _run(["python", "scripts/extract_rwc_cqt.py"])
    output += _run(["python", "scripts/chord_data_v2.py", "build-real",
                    "--dataset", datasets])
    output += _run(["python", "scripts/chord_data_v2.py", "build-pseudo",
                    "--report", os.path.join(REPORT_DIR, "chord170_phase2_pseudo_report.json")])
    output += _run(["python", "scripts/chord_data_v2.py", "card",
                    "--out", os.path.join(REPORT_DIR, "chord170_phase2_dataset.json")])
    data_volume.commit()
    for name in ("chord170_phase2_dataset.json", "chord170_phase2_pseudo_report.json"):
        path = os.path.join(REPORT_DIR, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                print(f"===== {name} =====", flush=True)
                print(handle.read(), flush=True)
    return output


@app.function(image=image, timeout=600, volumes={ROOT: data_volume, RUNS: runs_volume})
def status() -> str:
    """Cheap availability check: code bundle, datasets, and cached windows."""
    _ensure_bundle()
    script = (
        "import glob, json, os\n"
        "report = {}\n"
        "report['bundle'] = os.path.isdir(%r)\n" % BACKEND
        + "report['datasets'] = {}\n"
        "for name in ['guitarset', 'egset12', 'guitar_techs', 'idmt_smt_guitar', 'rwc']:\n"
        f"    cqt = glob.glob(os.path.join({BACKEND!r}, 'data', name, 'processed', 'cqt', '*.npz'))\n"
        f"    side = glob.glob(os.path.join({BACKEND!r}, 'data', name, 'processed', 'chord170', '*.npz'))\n"
        "    report['datasets'][name] = {'cqt': len(cqt), 'sidecars': len(side)}\n"
        f"pseudo = glob.glob(os.path.join({BACKEND!r}, 'data', 'chord170', 'pseudo_v2', 'processed', 'cqt', '*.npz'))\n"
        "report['pseudo_v2'] = len(pseudo)\n"
        "print(json.dumps(report, indent=1))\n"
    )
    completed = subprocess.run(
        ["python", "-c", script], cwd=BACKEND, env=_env(), capture_output=True, text=True,
    )
    text = completed.stdout + completed.stderr
    print(text, flush=True)
    return text


@app.function(image=image, timeout=300, volumes={ROOT: data_volume, RUNS: runs_volume})
def ls(path: str = ROOT) -> str:
    """List the volume contents (debug helper)."""
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(path):
        depth = dirpath[len(path):].count(os.sep)
        if depth >= 2:
            dirnames[:] = []
            continue
        for name in sorted(dirnames):
            lines.append(os.path.join(dirpath, name) + "/")
        for name in sorted(filenames):
            lines.append(os.path.join(dirpath, name))
    text = "\n".join(lines) or f"({path} is empty)"
    print(text, flush=True)
    return text


@app.local_entrypoint()
def main() -> None:
    print(status.remote())
