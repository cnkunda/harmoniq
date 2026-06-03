"""Stem mixing utilities for the Commit 111 stem-routing pipeline.

Provides:

* ``wav_rms(path)`` — chunked RMS calculation reused by Demucs and audio_mix helpers.
* ``mix_stems(stem_paths, output_path)`` — sum 2+ stem WAVs into a normalized mix.
* ``resolve_chord_stems(stem_abs_paths, chord_mix_keys)`` — keep only audible stems.
* ``resolve_solo_stem(stem_abs_paths, selected)`` — cascade through selected → guitar → vocals.

All operations are deterministic and side-effect-light; callers (analyze pipeline,
recompute worker, transcription/analyze endpoint) decide what to do with results.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger("harmoniq.audio_mix")
logger.setLevel(logging.INFO)

# Headroom target after peak normalization. Prevents clipping when downstream
# librosa / smoothing operations push peaks slightly above the raw sum.
PEAK_HEADROOM = 0.9


def wav_rms(path: Path, chunk_size: int = 65536) -> float:
    """Calculate RMS of a WAV file using chunked reading for memory efficiency.

    Reads audio in chunks (default 64KB) to minimize RAM usage. Supports all
    bit depths and float formats via soundfile. Returns 0.0 on missing file
    or read error — never raises, so callers can use it as a silence probe.
    """
    try:
        if path is None or not path.is_file():
            return 0.0

        total_sum = 0.0
        total_samples = 0

        for block in sf.blocks(str(path), blocksize=chunk_size, dtype="float64"):
            if block.size == 0:
                continue
            flat = block.ravel()
            total_sum += np.sum(np.square(flat))
            total_samples += flat.size

        if total_samples == 0:
            return 0.0

        return float(np.sqrt(total_sum / total_samples))
    except Exception:
        return 0.0


def mix_stems(stem_paths: list[Path], output_path: Path) -> Path:
    """Sum 2+ stem WAVs into a single normalized WAV at ``output_path``.

    - Filters to existing files only; raises ``FileNotFoundError`` if none valid.
    - All stems must share the same sample rate (Demucs invariant). A mismatch
      raises ``ValueError`` rather than silently producing time-warped audio.
    - Multi-channel stems are averaged to mono (defensive — Demucs outputs mono).
    - Shorter stems are zero-padded to match the longest; longer stems keep full length.
    - Output is peak-normalized to ``PEAK_HEADROOM`` (0.9) to leave headroom for
      downstream operations that may push peaks slightly above the raw sum.
    - Silent mix (peak == 0) is written as zeros with a warning.
    """
    valid_paths = [p for p in stem_paths if p is not None and p.is_file()]
    if not valid_paths:
        raise FileNotFoundError("No valid existing stem paths provided for mixing.")

    target_sr: int | None = None
    mono_signals: list[np.ndarray] = []

    for p in valid_paths:
        data, sr = sf.read(str(p), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1).astype(np.float32, copy=False)
        if target_sr is None:
            target_sr = sr
        elif sr != target_sr:
            raise ValueError(
                f"Sample rate mismatch in mix_stems: expected {target_sr} Hz, "
                f"got {sr} Hz from {p}"
            )
        mono_signals.append(data.astype(np.float32, copy=False))

    max_length = max(len(s) for s in mono_signals)
    mixed_signal = np.zeros(max_length, dtype=np.float32)
    for s in mono_signals:
        mixed_signal[: len(s)] += s

    peak_amplitude = float(np.max(np.abs(mixed_signal)))
    if peak_amplitude > 0.0:
        mixed_signal = (mixed_signal / peak_amplitude) * PEAK_HEADROOM
    else:
        logger.warning("mix_stems: all input stems are silent; writing zeros")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    assert target_sr is not None
    sf.write(str(output_path), mixed_signal, target_sr)
    return output_path


def resolve_chord_stems(
    stem_abs_paths: dict[str, Path],
    chord_mix_keys: list[str],
) -> list[Path]:
    """Return the subset of ``chord_mix_keys`` whose paths exist and have non-zero RMS.

    Caller decides what to do with the result: mix via ``mix_stems`` when ≥2 stems
    remain, fall back to a single-stem or full-mix path otherwise. Silent / missing
    stems are excluded so the mix has actual harmonic content.
    """
    resolved: list[Path] = []
    for key in chord_mix_keys:
        p = stem_abs_paths.get(key)
        if p is None:
            continue
        if not p.is_file():
            continue
        if wav_rms(p) <= 0.0:
            continue
        resolved.append(p)
    return resolved


def resolve_solo_stem(
    stem_abs_paths: dict[str, Path],
    selected: str,
) -> tuple[Path, str]:
    """Cascade through ``[selected, "guitar", "vocals"]`` and return the first audible stem.

    Returns a tuple of ``(path, chosen_stem_name)``. The chosen name lets callers
    log whether a fallback was activated (e.g., for telemetry: "selected was silent,
    fell back to guitar"). If all three candidates are silent / missing, falls back
    to the guitar path (may be silent but exists) with ``"default_guitar"``.
    """
    for candidate in (selected, "guitar", "vocals"):
        p = stem_abs_paths.get(candidate)
        if p is None or not p.is_file():
            continue
        if wav_rms(p) > 0.0:
            return p, candidate

    guitar_path = stem_abs_paths.get("guitar")
    if guitar_path is not None and guitar_path.is_file():
        return guitar_path, "default_guitar"

    vocals_path = stem_abs_paths.get("vocals")
    if vocals_path is not None and vocals_path.is_file():
        return vocals_path, "default_vocals"

    raise KeyError(
        f"resolve_solo_stem: no usable stem path for selected={selected!r} "
        f"(guitar and vocals also missing)"
    )
