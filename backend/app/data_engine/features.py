"""CQT feature extraction for W1 pseudo-labels and augmentation.

Mirrors the training windowing in ``build_chord_tflite.py`` /
``pseudo_label_pipeline.py``:

- 144-bin CQT at 44.1 kHz, 100 ms hop;
- per-frame L1 normalization;
- 128-frame windows with 64-frame hop (12.8 s context);
- the window label is taken at the centre frame.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.cqt_constants import (
    BINS_PER_OCTAVE,
    CHROMA_BINS,
    FEATURE_DIM,
    HOP_FRAMES,
    HOP_SEC,
    TARGET_SR,
    WINDOW,
)


class FeatureExtractionError(RuntimeError):
    """Raised when audio cannot be loaded or converted to CQT windows."""


def extract_cqt_windows(audio_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(windows, center_times_s)`` for one audio file.

    ``windows`` has shape ``(n_windows, WINDOW, FEATURE_DIM)`` and
    ``center_times_s`` has shape ``(n_windows,)``.
    """
    try:
        import librosa
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise FeatureExtractionError("librosa is required for CQT extraction") from exc

    try:
        y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    except Exception as exc:
        raise FeatureExtractionError(
            f"could not load audio {audio_path}: {exc}"
        ) from exc

    if y.size == 0:
        raise FeatureExtractionError(f"audio is empty: {audio_path}")

    hop = max(1, int(TARGET_SR * HOP_SEC))
    cqt = librosa.cqt(
        y=y,
        sr=sr,
        hop_length=hop,
        n_bins=CHROMA_BINS,
        bins_per_octave=BINS_PER_OCTAVE,
    )
    features = np.abs(cqt).T.astype(np.float32)
    if features.ndim != 2 or features.shape[1] != FEATURE_DIM:
        raise FeatureExtractionError(
            f"unexpected CQT shape for {audio_path}: {features.shape}"
        )

    norms = features.sum(axis=1, keepdims=True).clip(1e-8, None)
    features = features / norms

    half = WINDOW // 2
    pad = np.zeros((half, FEATURE_DIM), dtype=np.float32)
    padded = np.concatenate([pad, features, pad], axis=0)

    n_frames = len(features)
    n_windows = max(1, int(np.ceil(n_frames / HOP_FRAMES)))
    windows = np.zeros((n_windows, WINDOW, FEATURE_DIM), dtype=np.float32)
    for index in range(n_windows):
        start = index * HOP_FRAMES
        windows[index] = padded[start : start + WINDOW]

    # Window index k is centred on original frame k * HOP_FRAMES.
    center_times = (
        np.arange(n_windows, dtype=np.float64) * HOP_FRAMES * HOP_SEC
    )
    return windows, center_times
