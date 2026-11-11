"""Subprocess adapter for the PyTorch MT3 family (MR-MT3 / YourMT3).

The PyTorch teachers are run in a worker process so a slow import or a
runaway generation cannot hang the comparison harness. The worker uses the
``mt3-infer`` toolkit (MIT wrapper) which vendored MR-MT3/YourMT3 inference.

Configuration (environment):
    HARMONIQ_MT3_INFER_PATH     Path to the mt3-infer checkout (or installed)
    HARMONIQ_TEACHER_PYTHON     Python executable for the worker (default: this)
    HARMONIQ_MT3_CHECKPOINT_DIR Checkpoint cache (default: backend/data/models/mt3infer)
    HARMONIQ_TEACHER_TIMEOUT_S  Per-teacher batch timeout (default: 1800)
    HARMONIQ_TEACHER_AUTO_DOWNLOAD=1  Allow the worker to download checkpoints
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.teachers.events import (
    TeacherError,
    TeacherOutput,
    TeacherTimeout,
    TeacherUnavailable,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_WORKER = _BACKEND_DIR / "scripts" / "teacher_workers" / "mt3_infer_worker.py"
_DEFAULT_CHECKPOINT_DIR = _BACKEND_DIR / "data" / "models" / "mt3infer"

_MODEL_LABELS = {
    "mr_mt3": "MR-MT3 (PyTorch, MIT)",
    "yourmt3": "YourMT3+ YPTF.MoE+Multi (PyTorch)",
    "mt3_pytorch": "MT3-PyTorch (PyTorch port)",
}

_KNOWN_CHECKPOINTS = {
    "mr_mt3": "mr_mt3/mt3.pth",
    "yourmt3": (
        "yourmt3/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_"
        "rp_b36_nops/last.ckpt"
    ),
    "mt3_pytorch": "mt3_pytorch/pretrained",
}


def _checkpoint_dir() -> Path:
    raw = os.getenv("HARMONIQ_MT3_CHECKPOINT_DIR")
    return Path(raw) if raw else _DEFAULT_CHECKPOINT_DIR


def _repo_path() -> Path | None:
    raw = os.getenv("HARMONIQ_MT3_INFER_PATH")
    return Path(raw) if raw else None


def _package_available() -> bool:
    if importlib.util.find_spec("mt3_infer") is not None:
        return True
    repo = _repo_path()
    return bool(repo and (repo / "mt3_infer" / "__init__.py").is_file())


def _checkpoint_ready(model_name: str) -> bool:
    rel = _KNOWN_CHECKPOINTS.get(model_name)
    if rel is None:
        return False
    path = _checkpoint_dir() / rel
    if model_name == "mt3_pytorch":
        return path.is_dir()
    return path.is_file()


class Mt3InferTeacher:
    """A PyTorch MT3-family teacher executed in a subprocess worker."""

    def __init__(self, model_name: str = "mr_mt3") -> None:
        if model_name not in _MODEL_LABELS:
            raise ValueError(f"unsupported mt3-infer model: {model_name!r}")
        self.model_name = model_name
        self.name = model_name
        self.display_name = _MODEL_LABELS[model_name]

    def is_available(self) -> bool:
        if not _package_available() or not _WORKER.is_file():
            return False
        auto_download = os.getenv("HARMONIQ_TEACHER_AUTO_DOWNLOAD", "").strip() == "1"
        return _checkpoint_ready(self.model_name) or auto_download

    def unavailable_reason(self) -> str | None:
        if not _package_available():
            return (
                "mt3-infer is not importable; clone openmirlab/mt3-infer and set "
                "HARMONIQ_MT3_INFER_PATH (or pip install it)"
            )
        if not _WORKER.is_file():
            return f"teacher worker missing: {_WORKER}"
        if not _checkpoint_ready(self.model_name):
            return (
                f"{self.model_name} checkpoint missing under {_checkpoint_dir()}; "
                "set HARMONIQ_TEACHER_AUTO_DOWNLOAD=1 or run the mt3-infer downloader"
            )
        return None

    def _python(self) -> str:
        return os.getenv("HARMONIQ_TEACHER_PYTHON", sys.executable)

    def _timeout(self) -> float:
        raw = os.getenv("HARMONIQ_TEACHER_TIMEOUT_S", "1800")
        try:
            return max(30.0, float(raw))
        except ValueError:
            return 1800.0

    def _worker_env(self) -> dict[str, str]:
        env = os.environ.copy()
        repo = _repo_path()
        if repo is not None:
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                f"{repo}{os.pathsep}{existing}" if existing else str(repo)
            )
        # app.mt3.model_server pins the parent process to CPU via
        # CUDA_VISIBLE_DEVICES=""; the PyTorch worker must opt back in when a
        # CUDA device is requested or torch will report no GPU.
        device = os.getenv("HARMONIQ_TEACHER_DEVICE", "cpu").strip().lower()
        if device.startswith("cuda"):
            env["CUDA_VISIBLE_DEVICES"] = os.getenv(
                "HARMONIQ_TEACHER_CUDA_VISIBLE_DEVICES", "0"
            )
        env.setdefault("MT3_CHECKPOINT_DIR", str(_checkpoint_dir()))
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("JAX_PLATFORMS", "cpu")
        return env

    def transcribe_many(self, audio_paths: list[Path]) -> dict[Path, TeacherOutput]:
        if not self.is_available():
            raise TeacherUnavailable(self.unavailable_reason() or "teacher unavailable")
        if not audio_paths:
            return {}

        with tempfile.TemporaryDirectory(prefix="harmoniq_teacher_") as tmp:
            tmp_dir = Path(tmp)
            input_json = tmp_dir / "inputs.json"
            output_json = tmp_dir / "outputs.json"
            input_json.write_text(
                json.dumps([str(path) for path in audio_paths]), encoding="utf-8"
            )
            command = [
                self._python(),
                str(_WORKER),
                "--model",
                self.model_name,
                "--input-json",
                str(input_json),
                "--output",
                str(output_json),
                "--device",
                os.getenv("HARMONIQ_TEACHER_DEVICE", "cpu"),
                "--auto-download",
                "1"
                if os.getenv("HARMONIQ_TEACHER_AUTO_DOWNLOAD", "").strip() == "1"
                else "0",
            ]
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(_BACKEND_DIR),
                    env=self._worker_env(),
                    capture_output=True,
                    text=True,
                    timeout=self._timeout(),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise TeacherTimeout(
                    f"{self.model_name} worker exceeded {self._timeout():.0f}s"
                ) from exc

            if completed.returncode != 0 and not output_json.is_file():
                stderr = (completed.stderr or "").strip().splitlines()[-12:]
                raise TeacherError(
                    f"{self.model_name} worker failed (exit {completed.returncode}): "
                    + " | ".join(stderr)
                )
            if completed.returncode != 0:
                logger = logging.getLogger("harmoniq.w2.compare")
                logger.warning(
                    "%s worker exited %d with per-track errors; salvaging outputs",
                    self.model_name,
                    completed.returncode,
                )
            if not output_json.is_file():
                raise TeacherError(
                    f"{self.model_name} worker produced no output: {output_json}"
                )
            payload = json.loads(output_json.read_text(encoding="utf-8"))
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            outputs: dict[Path, TeacherOutput] = {}
            for path in audio_paths:
                entry = payload.get(str(path))
                if entry is None:
                    raise TeacherError(
                        f"{self.model_name} worker omitted {path}"
                    )
                output = TeacherOutput.from_dict(entry)
                output.metadata.setdefault("worker_elapsed_ms", round(elapsed_ms, 3))
                outputs[path] = output
            return outputs

    def transcribe(self, audio_path: Path) -> TeacherOutput:
        return self.transcribe_many([audio_path])[audio_path]
