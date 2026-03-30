"""Stem separation step for PRIORITIES §6 (Demucs htdemucs_6s).

Goal:
  - Produce six stems: guitar, bass, drums, vocals, piano, other
  - Write them under: data/jobs/{job_id}/stems/
  - Return a mapping suitable for LessonJSON.stems

Smoke-test / CI note:
  Demucs downloads model weights and can be slow. Unit tests should remain fast,
  so this module supports a default "skip demucs" mode when running under pytest.
"""

from __future__ import annotations

import logging
import os
import shutil
import wave
from pathlib import Path

from app.pipeline_proof import TARGET_SR, run_demucs_htdemucs_6s

logger = logging.getLogger("harmoniq.separate")
logger.setLevel(logging.INFO)

STEM_KEYS: tuple[str, ...] = ("guitar", "bass", "drums", "vocals", "piano", "other")


class SeparationError(RuntimeError):
    """Raised when demucs separation fails or outputs are missing/unusable."""


def _backend_root() -> Path:
    # backend/app/separate.py -> backend/
    return Path(__file__).resolve().parents[1]


def _rel_to_backend_root(path: Path) -> str:
    """Return `data/...`-style paths (forward slashes) for JSON payloads."""
    p = path.resolve()
    rel = p.relative_to(_backend_root().resolve())
    return rel.as_posix()


def _should_skip_demucs() -> bool:
    # Explicit override for devs / CI.
    if os.getenv("HARMONIQ_SKIP_DEMUCS") == "1":
        return True

    # Pytest sets this env var during tests. Keep unit tests fast and deterministic.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True

    return False


def _is_readable_nonempty_wav(path: Path) -> bool:
    """Return True if `path` is a non-empty readable WAV file."""
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        with wave.open(str(path), "rb") as wf:
            _ = wf.getnframes()
            return True
    except wave.Error:
        return False


def _find_stem_file(stems_track_dir: Path, stem_name: str) -> Path:
    matches = list(stems_track_dir.glob(f"**/{stem_name}.wav"))
    if not matches:
        raise FileNotFoundError(
            f"Missing demucs stem {stem_name}.wav under {stems_track_dir} (htdemucs_6s expected)."
        )
    # Prefer the shallowest match for stability across demucs versions.
    matches.sort(key=lambda p: len(p.parts))
    return matches[0]


def _write_placeholder_stems(song_wav_path: Path, stems_dir: Path) -> dict[str, str]:
    stems_dir.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    for key in STEM_KEYS:
        dest = stems_dir / f"{key}.wav"
        shutil.copyfile(song_wav_path, dest)
        # Placeholders are derived from ingest's normalized contract; enforce
        # sr/channels so downstream steps don't silently inherit bad audio.
        if not _is_readable_nonempty_wav(dest):
            raise SeparationError(f"Placeholder stem {dest} is not a valid {TARGET_SR}Hz mono WAV.")
        with wave.open(str(dest), "rb") as wf:
            if wf.getframerate() != TARGET_SR or wf.getnchannels() != 1:
                raise SeparationError(f"Placeholder stem {dest} must be {TARGET_SR}Hz mono.")
        mapping[key] = _rel_to_backend_root(dest)
    return mapping


def separate_song_to_stems(
    song_wav_path: Path,
    job_dir: Path,
    *,
    cleanup_demucs_outputs: bool = True,
) -> dict[str, str]:
    """Separate `song_wav_path` into six stems and return JSON-ready relative paths."""
    if not song_wav_path.exists():
        raise SeparationError(f"Input song.wav missing: {song_wav_path}")

    stems_dir = job_dir / "stems"

    if _should_skip_demucs():
        logger.info("Skipping demucs (fast test mode) for job_dir=%s", job_dir)
        return _write_placeholder_stems(song_wav_path, stems_dir)

    demucs_out_dir = job_dir / "_demucs"
    try:
        stems_track_dir = run_demucs_htdemucs_6s(song_wav_path, demucs_out_dir)

        stems_dir.mkdir(parents=True, exist_ok=True)
        mapping: dict[str, str] = {}
        for key in STEM_KEYS:
            src = _find_stem_file(stems_track_dir, key)
            dest = stems_dir / f"{key}.wav"
            shutil.copyfile(src, dest)
            if not _is_readable_nonempty_wav(dest):
                raise SeparationError(f"Demucs output {dest} is missing or not a readable WAV.")
            mapping[key] = _rel_to_backend_root(dest)
        return mapping
    except Exception as e:
        # Provide an actionable error for end users.
        msg = (
            "Demucs stem separation failed. Try a studio recording or a different upload. "
            "If this keeps happening, check that demucs model weights are available."
        )
        raise SeparationError(msg) from e
    finally:
        if cleanup_demucs_outputs:
            shutil.rmtree(demucs_out_dir, ignore_errors=True)

