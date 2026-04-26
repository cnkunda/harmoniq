"""Demucs htdemucs_6s stem separation and routing hints (commit 78)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

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


def _wav_rms(path: Path, chunk_size: int = 65536) -> float:
    """Calculate RMS of a WAV file using chunked reading for memory efficiency.

    Reads audio in chunks (default 64KB) to minimize RAM usage.
    Supports all bit depths and float formats via soundfile.
    """
    try:
        if not path.is_file():
            return 0.0

        total_sum = 0.0
        total_samples = 0

        for block in sf.blocks(str(path), blocksize=chunk_size, dtype="float64"):
            if block.size == 0:
                continue
            # Flatten in case of multi-channel audio
            flat = block.ravel()
            total_sum += np.sum(np.square(flat))
            total_samples += flat.size

        if total_samples == 0:
            return 0.0

        return float(np.sqrt(total_sum / total_samples))
    except Exception:
        return 0.0


def build_stem_routing_hints(stem_abs_paths: dict[str, Path]) -> dict[str, object]:
    """Provide deterministic routing order for commit 79 handoff.

    Pre-calculates RMS values once to minimize disk I/O.
    Raises DemucsEngineError if all stems are silent.
    """
    # Pre-calculate RMS for all stems to minimize disk I/O
    rms_cache: dict[str, float] = {}
    for stem in STEM_KEYS:
        p = stem_abs_paths.get(stem)
        rms_cache[stem] = _wav_rms(p) if p is not None and p.is_file() else 0.0

    # Sort fallback candidates by RMS (loudest first)
    fallback_candidates = [s for s in STEM_KEYS if s not in {"guitar", "vocals"}]
    fallback_candidates.sort(key=lambda name: rms_cache.get(name, 0.0), reverse=True)
    melodic_preference_order = ["guitar", "vocals", *fallback_candidates]

    # Select the first stem with non-zero audio
    selected: str | None = None
    for stem in melodic_preference_order:
        if rms_cache.get(stem, 0.0) > 0.0:
            selected = stem
            break

    # All stems are silent - raise an error instead of silently defaulting
    if selected is None:
        raise DemucsEngineError(
            "No stems contain detectable audio. All stems are silent or missing."
        )

    return {
        "chord_mix_stems": ["bass", "other"],
        "melodic_preference_order": melodic_preference_order,
        "selected_melodic_stem": selected,
    }
