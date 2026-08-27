"""Audio stem mixing utility (commit 110).

Sums 2+ stem WAVs into a single normalized WAV for chord inference
(bass + other). Handles different lengths via truncate-to-shortest and
prevents clipping via peak normalization.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger("harmoniq.audio_mix")
logger.setLevel(logging.INFO)


def mix_stems(stem_paths: list[Path], output_path: Path) -> Path:
    """Sum 2+ stem WAVs into a single normalized WAV.

    - Loads stems as float32 mono/stereo, sums waveforms.
    - Truncates to shortest stem length when lengths differ.
    - Normalizes to prevent clipping: if peak > 0.89, scale to 0.89.

    Args:
        stem_paths: List of absolute paths to stem WAV files (2+ required).
        output_path: Destination path for mixed WAV.

    Returns:
        The output_path on success.

    Raises:
        ValueError: if fewer than 2 paths provided.
        FileNotFoundError: if any stem file missing.
        RuntimeError: on read/write failure or sample-rate mismatch.
    """
    if len(stem_paths) < 2:
        raise ValueError(f"mix_stems requires 2+ stem paths, got {len(stem_paths)}")
    for p in stem_paths:
        if not p.is_file():
            raise FileNotFoundError(f"Stem file missing: {p}")

    waveforms: list[np.ndarray] = []
    sample_rates: list[int] = []
    for p in stem_paths:
        try:
            data, sr = sf.read(str(p), dtype="float32", always_2d=False)
        except Exception as exc:
            raise RuntimeError(f"Failed to read stem {p}: {exc}") from exc
        # Ensure 2-D shape (samples, channels) for uniform handling; soundfile
        # returns 1-D for mono when always_2d=False.
        if data.ndim == 1:
            data = data[:, np.newaxis]
        waveforms.append(data)
        sample_rates.append(int(sr))

    # Validate sample rates match
    if len(set(sample_rates)) != 1:
        raise RuntimeError(f"Sample rate mismatch across stems: {sample_rates}")
    sr = sample_rates[0]

    # Truncate to shortest length
    min_len = min(w.shape[0] for w in waveforms)
    if min_len == 0:
        raise RuntimeError("One or more stems have zero samples")

    truncated = [w[:min_len] for w in waveforms]

    # Ensure channel counts match — broadcast mono to stereo if needed
    # All stems should be mono (Demucs pipeline), but handle mixed case.
    max_channels = max(w.shape[1] for w in truncated)
    normalized_channels: list[np.ndarray] = []
    for w in truncated:
        if w.shape[1] == 1 and max_channels > 1:
            w = np.repeat(w, max_channels, axis=1)
        elif w.shape[1] != max_channels:
            # If stem has different channel count and not mono, truncate/pad channels
            if w.shape[1] < max_channels:
                pad = np.zeros((min_len, max_channels - w.shape[1]), dtype=np.float32)
                w = np.concatenate([w, pad], axis=1)
            else:
                w = w[:, :max_channels]
        normalized_channels.append(w)

    # Sum waveforms
    mixed = np.zeros_like(normalized_channels[0], dtype=np.float64)
    for w in normalized_channels:
        mixed += w.astype(np.float64)

    # Normalize to prevent clipping
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    target_peak = 0.89
    if peak > target_peak and peak > 1e-9:
        mixed = mixed * (target_peak / peak)
        logger.info("mix_stems normalized peak %.4f -> %.4f (scale %.4f)", peak, target_peak, target_peak / peak)

    # Squeeze mono back to 1-D for writing if single channel
    if mixed.shape[1] == 1:
        mixed_out = mixed[:, 0].astype(np.float32)
    else:
        mixed_out = mixed.astype(np.float32)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sf.write(str(output_path), mixed_out, sr)
    except Exception as exc:
        raise RuntimeError(f"Failed to write mixed WAV {output_path}: {exc}") from exc

    logger.info(
        "mix_stems mixed %d stems -> %s (sr=%d samples=%d channels=%d peak=%.4f)",
        len(stem_paths),
        output_path,
        sr,
        min_len,
        mixed_out.shape[1] if mixed_out.ndim > 1 else 1,
        float(np.max(np.abs(mixed_out))) if mixed_out.size else 0.0,
    )
    return output_path
