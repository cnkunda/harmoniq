"""Modal app: train and evaluate the W3 two-head student on a cloud GPU.

Prerequisites (once)::

    pip install modal && modal token new
    modal volume create harmoniq-w3

    # from backend/: build a self-contained bundle and upload it
    python scripts/stage_w3_cloud_bundle.py --out /tmp/w3_bundle --include-audio
    modal volume put harmoniq-w3 /tmp/w3_bundle /w3

Run (from backend/)::

    modal run scripts/w3_modal.py::status
    modal run scripts/w3_modal.py::train --limit-tracks 300 --epochs 40
    modal run scripts/w3_modal.py::qat --benchmark true
    modal run scripts/w3_modal.py::evaluate --source guitarset --limit 20

The bundle mirrors the repo layout, so the committed manifests resolve
without editing. Long runs should use ``modal run --detach``.
"""

from __future__ import annotations

import os
import subprocess

import modal

app = modal.App("harmoniq-w3")

# The official TensorFlow GPU image already carries the matching CUDA/cuDNN
# stack. Modal's own TF example uses the same pattern:
# https://github.com/modal-labs/modal-examples/blob/main/06_gpu_and_ml/tensorflow/tensorflow_tutorial.py
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
        "tqdm>=4.67",
        "tensorflow-model-optimization>=0.8.1",
    )
    .env(
        {
            "TF_USE_LEGACY_KERAS": "1",
            "TF_CPP_MIN_LOG_LEVEL": "2",
            "PYTHONUNBUFFERED": "1",
        }
    )
)

volume = modal.Volume.from_name("harmoniq-w3", create_if_missing=True)

ROOT = "/w3"
BACKEND = f"{ROOT}/backend"
REPORT_DIR = f"{ROOT}/docs/audit/amt"


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
        if "w3_bundle.tgz" in filenames:
            tarball = os.path.join(dirpath, "w3_bundle.tgz")
            print(f"[setup] extracting {tarball}", flush=True)
            with tarfile.open(tarball) as archive:
                archive.extractall(dirpath)
            volume.commit()
            root = _find_bundle_root()
            if root is not None:
                _apply_root(root)
                return

    raise FileNotFoundError(
        "W3 bundle not found in the Modal volume. Upload it first:\n"
        "  python scripts/stage_w3_cloud_bundle.py --out /tmp/w3_bundle\n"
        "  modal volume put harmoniq-w3 /tmp/w3_bundle /w3"
    )


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "TF_USE_LEGACY_KERAS": "1",
            "HARMONIQ_STUDENT_MODEL_DIR": os.path.join(
                BACKEND, "data", "models", "student"
            ),
        }
    )
    return env


def _run(command: list[str]) -> str:
    print("[run] " + " ".join(command), flush=True)
    process = subprocess.Popen(
        command,
        cwd=BACKEND,
        env=_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
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
            f"command failed ({returncode}): {' '.join(command)}\n"
            f"{output[-4000:]}"
        )
    return output


@app.function(
    image=image,
    cpu=8,
    memory=32768,
    timeout=8 * 60 * 60,
    volumes={ROOT: volume},
    retries=2,
)
def prepare(
    sources: str = "w1",
    limit_tracks: str = "0",
    max_windows_per_track: str = "0",
) -> str:
    """Build and cache the training arrays on CPU (no GPU needed)."""
    _ensure_bundle()
    command = [
        "python",
        "scripts/build_student_model.py",
        "--sources",
        sources,
        "--prepare-only",
    ]
    if int(limit_tracks or 0):
        command += ["--limit-tracks", str(int(limit_tracks))]
    if int(max_windows_per_track or 0):
        command += ["--max-windows-per-track", str(int(max_windows_per_track))]
    if _truthy(force):
        command.append("--force-train")
    output = _run(command)
    volume.commit()
    return output


@app.function(image=image, gpu="A10G", timeout=8 * 60 * 60, volumes={ROOT: volume}, retries=1)
def train(
    sources: str = "w1",
    limit_tracks: str = "0",
    max_windows_per_track: str = "0",
    epochs: str = "40",
    batch_size: str = "16",
    force: str = "true",
) -> str:
    """Train the float32 student and save the checkpoint."""
    _ensure_bundle()
    command = [
        "python",
        "scripts/build_student_model.py",
        "--sources",
        sources,
        "--epochs",
        epochs,
        "--batch-size",
        batch_size,
    ]
    if int(limit_tracks or 0):
        command += ["--limit-tracks", str(int(limit_tracks))]
    if int(max_windows_per_track or 0):
        command += ["--max-windows-per-track", str(int(max_windows_per_track))]
    if _truthy(force):
        command.append("--force-train")
    output = _run(command)
    volume.commit()
    return output


@app.function(image=image, gpu="A10G", timeout=4 * 60 * 60, volumes={ROOT: volume}, retries=1)
def qat(
    sources: str = "w1",
    benchmark: str = "true",
) -> str:
    """Apply QAT, export INT8 TFLite, and benchmark per-frame latency."""
    _ensure_bundle()
    command = [
        "python",
        "scripts/build_student_model.py",
        "--sources",
        sources,
        "--qat-only",
        "--report",
        os.path.join(REPORT_DIR, "w3_latency.json"),
    ]
    if _truthy(benchmark):
        command.append("--benchmark")
    output = _run(command)
    volume.commit()
    if os.path.isfile(os.path.join(REPORT_DIR, "w3_latency.json")):
        with open(
            os.path.join(REPORT_DIR, "w3_latency.json"), encoding="utf-8"
        ) as handle:
            print(handle.read(), flush=True)
    return output


@app.function(image=image, gpu="A10G", timeout=6 * 60 * 60, volumes={ROOT: volume})
def evaluate(
    source: str = "guitarset",
    split: str = "test",
    limit: str = "0",
    refresh: str = "false",
) -> str:
    """Run the `student` eval tier and write the W0 report."""
    _ensure_bundle()
    root = os.path.dirname(BACKEND)
    manifest_path = os.path.join(root, "docs", "eval", "amt_manifest.json")
    report_dir = os.path.join(root, "docs", "audit", "amt")
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(
            f"eval manifest not found: {manifest_path} (bundle root={root})"
        )
    os.makedirs(report_dir, exist_ok=True)
    command = [
        "python",
        "scripts/eval_amt.py",
        "--manifest",
        manifest_path,
        "--tier",
        "student",
        "--source",
        source,
        "--split",
        split,
        "--report",
        os.path.join(report_dir, "w3_eval_student.json"),
        "--fail-on-track-error",
    ]
    if int(limit or 0):
        command += ["--limit", str(int(limit))]
    if _truthy(refresh):
        command.append("--refresh")
    output = _run(command)
    volume.commit()
    return output


@app.function(image=image, timeout=600, volumes={ROOT: volume})
def status() -> str:
    """Cheap availability check: imports, GPU, and data presence."""
    _ensure_bundle()
    script = (
        "import json, os, sys\n"
        "report = {}\n"
        "try:\n"
        "    import tensorflow as tf\n"
        "    report['tensorflow'] = tf.__version__\n"
        "    report['cuda'] = bool(tf.config.list_physical_devices('GPU'))\n"
        "except Exception as exc:\n"
        "    report['tensorflow_error'] = f'{type(exc).__name__}: {exc}'\n"
        "try:\n"
        "    import tensorflow_model_optimization as tfmot\n"
        "    report['tfmot'] = tfmot.__version__\n"
        "except Exception as exc:\n"
        "    report['tfmot_error'] = f'{type(exc).__name__}: {exc}'\n"
        f"report['pseudo_labels'] = len(__import__('glob').glob("
        f"'{BACKEND}/data/pseudo_label/w1/labels/*.json'))\n"
        f"report['student_dir'] = os.path.isdir("
        f"'{BACKEND}/data/models/student')\n"
        "print(json.dumps(report, indent=1))\n"
    )
    completed = subprocess.run(
        ["python", "-c", script], cwd=BACKEND, env=_env(),
        capture_output=True, text=True,
    )
    text = completed.stdout + completed.stderr
    print(text, flush=True)
    return text


@app.function(image=image, timeout=300, volumes={ROOT: volume})
def ls() -> str:
    """List the volume contents under /w3 (debug helper)."""
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        depth = dirpath[len(ROOT):].count(os.sep)
        if depth >= 2:
            dirnames[:] = []
            continue
        for name in sorted(dirnames):
            lines.append(os.path.join(dirpath, name) + "/")
        for name in sorted(filenames):
            lines.append(os.path.join(dirpath, name))
    text = "\n".join(lines) or "(volume /w3 is empty)"
    print(text, flush=True)
    return text


@app.local_entrypoint()
def main() -> None:
    print(status.remote())
