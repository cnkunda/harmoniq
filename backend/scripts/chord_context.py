"""Long-context helpers for the 170-class chord model.

The fine feature cache stores 16-frame windows with a 16-frame hop, so
consecutive windows tile the underlying CQT frames exactly. This module
reconstructs arbitrary-length contexts from those windows without touching
audio or recomputing CQT, and provides the structured (root / quality /
pitch) helpers used by the long-context model and decoder.

Geometry: window ``k`` frame ``i`` is ``(k*hop - window//2 + i) * 0.1 s``.
With ``window == hop == 16``, global frame ``g = k*16 + i`` is centred at
``(g - 8) * 0.1 s``; the centre frame of a window is index 8.
"""

from __future__ import annotations

import numpy as np

from app.chord_vocab_170 import (
    BASS_X_IDX,
    N_IDX_170,
    NUM_CLASSES_170,
    QUALITIES_14,
    QUALITY_INTERVALS_170,
)

FRAME_HOP_SEC = 0.1


def pitch_target_table() -> np.ndarray:
    """Binary ``(170, 12)`` pitch-class table (N/X rows are all zeros)."""
    table = np.zeros((NUM_CLASSES_170, 12), dtype=np.float32)
    for index in range(168):
        root = index % 12
        quality = QUALITIES_14[index // 12]
        for interval in QUALITY_INTERVALS_170[quality]:
            table[index, (root + interval) % 12] = 1.0
    return table


PITCH_TARGET_TABLE = pitch_target_table()


def pitch_targets_from_chords(chords: np.ndarray) -> np.ndarray:
    """Map ``(...,)`` 170-class chord indices to ``(..., 12)`` pitch targets."""
    chords = np.asarray(chords, dtype=np.int64)
    return PITCH_TARGET_TABLE[chords]


def build_segment_index(offsets: list[tuple[int, int, str]], n_windows: int) -> np.ndarray:
    """Map each global window index to its track segment index."""
    segment = np.full(n_windows, -1, dtype=np.int64)
    for index, (start, n_tracks, _track_id) in enumerate(offsets):
        segment[start:start + n_tracks] = index
    return segment


def context_for_window(
    features: np.ndarray,
    frame_labels: np.ndarray | None,
    frame_bass: np.ndarray | None,
    offsets: list[tuple[int, int, str]],
    segment_index: np.ndarray,
    window_index: int,
    context_frames: int,
) -> dict:
    """Build one long context centred on ``window_index``.

    Returns dict with ``features`` ``(context, C)``, ``frame_labels`` and
    ``frame_bass`` ``(context,)`` (or ``None``), ``valid`` ``(context,)``,
    ``center_index`` (frame in the context corresponding to the window
    centre), and ``track_id``.
    """
    window_index = int(window_index)
    segment = int(segment_index[window_index])
    if segment < 0:
        raise IndexError(f"window {window_index} has no track segment")
    start, n_windows, track_id = offsets[segment]
    n_frames = int(n_windows) * features.shape[1]
    local_window = window_index - start
    center_global = local_window * features.shape[1] + features.shape[1] // 2
    length = int(context_frames)

    if n_frames <= length:
        flat = features[start:start + n_windows].reshape(-1, features.shape[2])
        context = np.zeros((length, features.shape[2]), dtype=np.float32)
        context[:n_frames] = flat
        labels = np.full(length, N_IDX_170, dtype=np.int64)
        bass = np.full(length, BASS_X_IDX, dtype=np.int64)
        if frame_labels is not None:
            labels[:n_frames] = frame_labels[start:start + n_windows].reshape(-1)
        if frame_bass is not None:
            bass[:n_frames] = frame_bass[start:start + n_windows].reshape(-1)
        valid = np.zeros(length, dtype=np.float32)
        valid[:n_frames] = 1.0
        center_index = center_global
    else:
        start_frame = int(np.clip(center_global - length // 2, 0, n_frames - length))
        start_window = start_frame // features.shape[1]
        start_offset = start_frame % features.shape[1]
        n_span = (start_offset + length + features.shape[1] - 1) // features.shape[1]
        first_window = start + start_window
        flat = features[first_window:first_window + n_span].reshape(
            -1, features.shape[2])
        context = flat[start_offset:start_offset + length]
        labels = None
        bass = None
        if frame_labels is not None:
            labels = (frame_labels[first_window:first_window + n_span]
                      .reshape(-1)[start_offset:start_offset + length])
        if frame_bass is not None:
            bass = (frame_bass[first_window:first_window + n_span]
                    .reshape(-1)[start_offset:start_offset + length])
        valid = np.ones(length, dtype=np.float32)
        center_index = center_global - start_frame

    return {
        "features": np.asarray(context, dtype=np.float32),
        "frame_labels": labels,
        "frame_bass": bass,
        "valid": valid,
        "center_index": int(center_index),
        "track_id": track_id,
    }


def context_batch(
    features: np.ndarray,
    frame_labels: np.ndarray | None,
    frame_bass: np.ndarray | None,
    offsets: list[tuple[int, int, str]],
    segment_index: np.ndarray,
    window_indices: np.ndarray,
    context_frames: int,
) -> dict:
    """Build a batch of contexts; stacks features and returns centre indices."""
    contexts = [
        context_for_window(features, frame_labels, frame_bass, offsets,
                           segment_index, int(index), context_frames)
        for index in window_indices
    ]
    labels = (np.stack([item["frame_labels"] for item in contexts])
              if contexts[0]["frame_labels"] is not None else None)
    bass = (np.stack([item["frame_bass"] for item in contexts])
            if contexts[0]["frame_bass"] is not None else None)
    return {
        "features": np.stack([item["features"] for item in contexts]),
        "frame_labels": labels,
        "frame_bass": bass,
        "valid": np.stack([item["valid"] for item in contexts]),
        "center_index": np.array([item["center_index"] for item in contexts],
                                 dtype=np.int64),
        "track_ids": [item["track_id"] for item in contexts],
    }


def _log_probs(probs: np.ndarray) -> np.ndarray:
    return np.log(np.clip(np.asarray(probs, dtype=np.float64), 1e-8, 1.0))


def structured_scores(
    chord_probs: np.ndarray,
    root_probs: np.ndarray | None = None,
    quality_probs: np.ndarray | None = None,
    pitch_probs: np.ndarray | None = None,
    *,
    chord_weight: float = 1.0,
    root_weight: float = 1.0,
    quality_weight: float = 1.0,
    pitch_weight: float = 0.0,
) -> np.ndarray:
    """Score every 170-class chord from per-frame structured heads.

    ``fuse`` = chord + root + quality. ``hybrid`` additionally adds the
    pitch-class template similarity. N/X rows have no pitch template, so
    the chord head remains the only source for them.
    """
    scores = chord_weight * _log_probs(chord_probs)
    if root_probs is not None and root_weight:
        root_map = np.array([12 if i >= N_IDX_170 else i % 12
                             for i in range(NUM_CLASSES_170)])
        scores += root_weight * _log_probs(root_probs)[:, root_map]
    if quality_probs is not None and quality_weight:
        quality_map = np.array([14 if i >= N_IDX_170 else i // 12
                                for i in range(NUM_CLASSES_170)])
        scores += quality_weight * _log_probs(quality_probs)[:, quality_map]
    if pitch_probs is not None and pitch_weight:
        template_size = np.maximum(PITCH_TARGET_TABLE.sum(axis=1), 1.0)
        similarity = (np.asarray(pitch_probs, dtype=np.float64)
                      @ PITCH_TARGET_TABLE.T) / template_size[None, :]
        scores += pitch_weight * np.log(np.clip(similarity, 1e-8, 1.0))
    return scores


def structured_decode(
    chord_probs: np.ndarray,
    root_probs: np.ndarray | None = None,
    quality_probs: np.ndarray | None = None,
    pitch_probs: np.ndarray | None = None,
    *,
    mode: str = "none",
    chord_weight: float = 1.0,
    root_weight: float = 1.0,
    quality_weight: float = 1.0,
    pitch_weight: float = 0.25,
) -> np.ndarray:
    """Decode chord indices from the structured heads (identity for none)."""
    chord_probs = np.asarray(chord_probs)
    if mode == "none":
        return chord_probs.argmax(axis=1)
    if mode not in ("fuse", "hybrid"):
        raise ValueError(f"unknown structured decode mode: {mode}")
    scores = structured_scores(
        chord_probs, root_probs, quality_probs,
        pitch_probs if mode == "hybrid" else None,
        chord_weight=chord_weight,
        root_weight=root_weight,
        quality_weight=quality_weight,
        pitch_weight=pitch_weight,
    )
    return scores.argmax(axis=1)


def viterbi_smooth_sequence(
    probs: np.ndarray,
    *,
    self_transition: float = 0.9,
) -> np.ndarray:
    """Viterbi path over a sequence of class probabilities (persistence prior)."""
    probs = np.asarray(probs, dtype=np.float64)
    if len(probs) == 0:
        return np.zeros(0, dtype=np.int64)
    n_states = probs.shape[1]
    if n_states == 1:
        return np.zeros(len(probs), dtype=np.int64)
    self_transition = float(np.clip(self_transition, 0.0, 1.0 - 1e-6))
    off = (1.0 - self_transition) / (n_states - 1)
    transition = np.full((n_states, n_states), off, dtype=np.float64)
    np.fill_diagonal(transition, self_transition)
    log_transition = np.log(np.clip(transition, 1e-12, 1.0))
    log_emission = np.log(np.clip(probs, 1e-12, 1.0))
    delta = log_emission[0]
    back = np.zeros((len(probs), n_states), dtype=np.int64)
    states = np.arange(n_states)
    for t in range(1, len(probs)):
        scores = delta[:, None] + log_transition
        back[t] = scores.argmax(axis=0)
        delta = scores[back[t], states] + log_emission[t]
    path = np.zeros(len(probs), dtype=np.int64)
    path[-1] = int(delta.argmax())
    for t in range(len(probs) - 2, -1, -1):
        path[t] = back[t + 1, path[t + 1]]
    return path


def viterbi_smooth_tracks(
    probs: np.ndarray,
    track_ids: list[str],
    centres: np.ndarray,
    *,
    self_transition: float = 0.9,
) -> np.ndarray:
    """Apply Viterbi independently per track, ordered by window centre."""
    probs = np.asarray(probs)
    centres = np.asarray(centres)
    predictions = probs.argmax(axis=1).astype(np.int64)
    grouped: dict[str, list[int]] = {}
    for index, track in enumerate(track_ids):
        grouped.setdefault(track, []).append(index)
    for indices in grouped.values():
        order = np.asarray(indices)[np.argsort(centres[indices], kind="stable")]
        predictions[order] = viterbi_smooth_sequence(
            probs[order], self_transition=self_transition)
    return predictions


def centre_window_predictions(
    probs: np.ndarray,
    center_indices: np.ndarray,
    *,
    span: int = 1,
) -> np.ndarray:
    """Select (or average) the central frame predictions of each context."""
    probs = np.asarray(probs)
    if probs.ndim == 2:
        return probs
    if span <= 1:
        return probs[np.arange(len(probs)), np.asarray(center_indices)]
    half = span // 2
    gathered = []
    for index, center in enumerate(center_indices):
        lo = max(0, int(center) - half)
        hi = min(probs.shape[1], int(center) + half + 1)
        gathered.append(probs[index, lo:hi].mean(axis=0))
    return np.stack(gathered)


def root_quality_from_chords(chords: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Derive root/quality auxiliary labels from 170-class chords."""
    chords = np.asarray(chords, dtype=np.int64)
    roots = np.full(chords.shape, 12, dtype=np.int64)
    qualities = np.full(chords.shape, 14, dtype=np.int64)
    mask = chords < N_IDX_170
    roots[mask] = chords[mask] % 12
    qualities[mask] = chords[mask] // 12
    return roots, qualities


def inversion_from_chord_bass(chord: np.ndarray, bass: np.ndarray) -> np.ndarray:
    """Inversion labels ``(...,)``; unknown/N frames map to class 4."""
    from app.chord_labels import inversion_class

    chord = np.asarray(chord, dtype=np.int64)
    bass = np.asarray(bass, dtype=np.int64)
    flat = np.array([inversion_class(int(c), int(b))
                     for c, b in zip(chord.reshape(-1), bass.reshape(-1))],
                    dtype=np.int64)
    return flat.reshape(chord.shape)


__all__ = [
    "FRAME_HOP_SEC",
    "PITCH_TARGET_TABLE",
    "build_segment_index",
    "centre_window_predictions",
    "context_batch",
    "context_for_window",
    "inversion_from_chord_bass",
    "pitch_targets_from_chords",
    "root_quality_from_chords",
    "structured_decode",
    "structured_scores",
    "viterbi_smooth_sequence",
    "viterbi_smooth_tracks",
]
