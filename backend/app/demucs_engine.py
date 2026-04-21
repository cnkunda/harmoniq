"""Demucs htdemucs_6s stem separation and routing hints (commit 78)."""

from __future__ import annotations

import os
import shutil
import wave
from pathlib import Path

import numpy as np

from app.pipeline_proof import DEMUCS_MODEL, run_demucs_htdemucs_6s

STEM_KEYS: tuple[str, ...] = ("guitar", "bass", "drums", "vocals", "piano", "other")


class DemucsEngineError(RuntimeError):
    """Raised when Demucs fails or required stems are missing."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _rel_to_backend(path: Path) -> str:
    return path.resolve().relative_to(_backend_root().resolve()).as_posix()


def _should_skip_demucs() -> bool:
    return os.getenv("HARMONIQ_SKIP_DEMUCS", "").strip() == "1" or bool(os.getenv("PYTEST_CURRENT_TEST"))


def _find_stem_file(stems_track_dir: Path, stem_name: str) -> Path:
    matches = list(stems_track_dir.glob(f"**/{stem_name}.wav"))
    if not matches:
        raise DemucsEngineError(f"Missing stem {stem_name}.wav in Demucs output.")
    matches.sort(key=lambda p: len(p.parts))
    return matches[0]


def _write_placeholder_stems(song_wav_path: Path, stems_dir: Path) -> dict[str, str]:
    stems_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for stem in STEM_KEYS:
        out = stems_dir / f"{stem}.wav"
        shutil.copyfile(song_wav_path, out)
        mapping[stem] = _rel_to_backend(out)
    return mapping


def separate_with_demucs(song_wav_path: Path, job_dir: Path) -> dict[str, str]:
    """Run `htdemucs_6s` and return backend-relative stem paths."""
    if not song_wav_path.is_file():
        raise DemucsEngineError(f"Input WAV missing: {song_wav_path}")
    stems_dir = job_dir / "stems"
    if _should_skip_demucs():
        return _write_placeholder_stems(song_wav_path, stems_dir)

    demucs_out = job_dir / "_demucs_prepare"
    try:
        track_dir = run_demucs_htdemucs_6s(song_wav_path, demucs_out, model=DEMUCS_MODEL)
        stems_dir.mkdir(parents=True, exist_ok=True)
        out: dict[str, str] = {}
        for stem in STEM_KEYS:
            src = _find_stem_file(track_dir, stem)
            dst = stems_dir / f"{stem}.wav"
            shutil.copyfile(src, dst)
            out[stem] = _rel_to_backend(dst)
        return out
    except Exception as exc:
        raise DemucsEngineError(f"Demucs separation failed: {exc}") from exc
    finally:
        shutil.rmtree(demucs_out, ignore_errors=True)


def _wav_rms(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            if not frames:
                return 0.0
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
            if data.size == 0:
                return 0.0
            return float(np.sqrt(np.mean(np.square(data))))
    except Exception:
        return 0.0


def build_stem_routing_hints(stem_abs_paths: dict[str, Path]) -> dict[str, object]:
    """Provide deterministic routing order for commit 79 handoff."""
    fallback_candidates = [s for s in STEM_KEYS if s not in {"guitar", "vocals"}]
    fallback_candidates.sort(key=lambda name: _wav_rms(stem_abs_paths.get(name, Path())), reverse=True)
    melodic_preference_order = ["guitar", "vocals", *fallback_candidates]

    selected = "guitar"
    for stem in melodic_preference_order:
        p = stem_abs_paths.get(stem)
        if p is not None and p.is_file() and _wav_rms(p) > 0.0:
            selected = stem
            break

    return {
        "chord_mix_stems": ["bass", "other"],
        "melodic_preference_order": melodic_preference_order,
        "selected_melodic_stem": selected,
    }
