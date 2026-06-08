"""
Commit 118: Repetition-Aware Section Detection via Self-Similarity Matrix.

Uses chroma-based recurrence matrix analysis to detect repeated sections
(e.g., Chorus 1 = Chorus 2 = Chorus 3) and assign consistent labels
with repeat group metadata.

The algorithm projects the frame-level recurrence matrix onto segment pairs,
thresholds to find similar segments, then uses connected-component analysis
to group repeated sections.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("harmoniq.repeat_detection")
logger.setLevel(logging.INFO)

# ---- Tunable constants -------------------------------------------------------

SIMILARITY_THRESHOLD: float = 0.6
MIN_SEGMENT_FRAMES: int = 5


# ---- Helpers -----------------------------------------------------------------


def _segment_frame_ranges(
    boundaries: list[float],
    times: np.ndarray,
) -> list[tuple[int, int]]:
    """Convert time-based boundaries to (start_frame, end_frame) ranges.

    boundaries must include 0.0 as the first element and song duration
    (or the last segment end) as the final element.  *times* is the
    frame-time axis from librosa (one entry per hop).
    """
    ranges: list[tuple[int, int]] = []
    for i in range(len(boundaries) - 1):
        start_t = boundaries[i]
        end_t = boundaries[i + 1]
        start_frame = int(np.searchsorted(times, start_t, side="left"))
        end_frame = int(np.searchsorted(times, end_t, side="left"))
        # Ensure at least one frame
        if end_frame <= start_frame:
            end_frame = min(start_frame + 1, len(times))
        ranges.append((start_frame, end_frame))
    return ranges


def _segment_similarity_matrix(
    recurrence: np.ndarray,
    frame_ranges: list[tuple[int, int]],
) -> np.ndarray:
    """Project frame-level recurrence matrix onto segment pairs.

    For each pair (i, j), computes the mean affinity over the block
    ``recurrence[fi:fj, fi:fj]`` — this captures how similar two segments'
    internal chroma patterns are.

    Returns an (n_segments, n_segments) symmetric matrix with values in [0, 1].
    """
    n = len(frame_ranges)
    sim = np.zeros((n, n), dtype=float)

    for i in range(n):
        si, ei = frame_ranges[i]
        for j in range(i, n):
            sj, ej = frame_ranges[j]
            block = recurrence[si:ei, sj:ej]
            if block.size == 0:
                val = 0.0
            else:
                val = float(block.mean())
            sim[i, j] = val
            sim[j, i] = val

    return sim


def _group_by_connected_components(
    sim_matrix: np.ndarray,
    threshold: float,
) -> list[list[int]]:
    """Threshold the similarity matrix and find connected components.

    Returns a list of groups, each group being a list of section indices
    that belong together (i.e., they are repetitions of the same material).
    """
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components

    adjacency = (sim_matrix >= threshold).astype(int)
    np.fill_diagonal(adjacency, 0)

    n_components, labels = connected_components(
        csr_matrix(adjacency), directed=False
    )

    groups: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        groups.setdefault(int(label), []).append(idx)

    return list(groups.values())


def _assign_consistent_labels(
    existing_labels: list[str],
    groups: list[list[int]],
) -> list[dict[str, Any]]:
    """Assign repeat-group metadata and consistent labels.

    For each group with >1 member, labels are suffixed:
      first occurrence  → "Chorus"
      second occurrence → "Chorus (2 of 3)"
      third occurrence  → "Chorus (3 of 3)"

    Single-occurrence groups retain their original label unchanged.
    """
    n = len(existing_labels)
    # Build index→group lookup
    section_to_group: dict[int, int] = {}
    for gid, group in enumerate(groups):
        for idx in group:
            section_to_group[idx] = gid

    results: list[dict[str, Any]] = []
    for i in range(n):
        gid = section_to_group[i]
        group = groups[gid]
        repeat_count = len(group)
        is_repeated = repeat_count > 1
        # Position within group (sorted by original section order)
        sorted_group = sorted(group)
        repeat_index = sorted_group.index(i) + 1  # 1-based

        label = existing_labels[i]
        if is_repeated and repeat_index > 1:
            label = f"{label} ({repeat_index} of {repeat_count})"

        results.append({
            "repeat_group_id": gid,
            "is_repeated": is_repeated,
            "repeat_count": repeat_count,
            "repeat_index": repeat_index,
            "label": label,
        })

    return results


# ---- Public entry point ------------------------------------------------------


def detect_repeated_sections(
    chroma: np.ndarray,
    times: np.ndarray,
    boundaries: list[float],
    existing_labels: list[str],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]] | None:
    """Detect repeated sections using chroma self-similarity.

    Parameters
    ----------
    chroma : np.ndarray
        (12, n_frames) chroma CQT from librosa.
    times : np.ndarray
        Frame time axis, shape (n_frames,).
    boundaries : list[float]
        Section boundary times in seconds.  Must start with 0.0 and end
        with the song duration (or last segment end).
    existing_labels : list[str]
        Current section labels (from ``_infer_section_labels`` or cyclic).
    similarity_threshold : float
        Minimum segment-pair affinity to consider sections as repetitions.

    Returns
    -------
    list[dict] | None
        One dict per section with keys ``repeat_group_id``, ``is_repeated``,
        ``repeat_count``, ``repeat_index``, ``label`` (updated with suffix).
        Returns ``None`` if chroma is invalid or there are < 2 sections.
    """
    n_segments = len(boundaries) - 1
    if n_segments < 2:
        logger.info("detect_repeated_sections: fewer than 2 sections, skipping")
        return None

    if chroma is None or chroma.ndim != 2 or chroma.shape[0] != 12:
        logger.warning("detect_repeated_sections: invalid chroma shape, skipping")
        return None

    if len(times) < 2:
        logger.warning("detect_repeated_sections: insufficient time frames, skipping")
        return None

    # 1. Build frame-level recurrence matrix
    recurrence = librosa_segment_recurrence(chroma)

    # 2. Convert boundaries to frame ranges
    frame_ranges = _segment_frame_ranges(boundaries, times)

    # 3. Project onto segment-pair similarity matrix
    seg_sim = _segment_similarity_matrix(recurrence, frame_ranges)

    # 4. Find repeat groups via connected components
    groups = _group_by_connected_components(seg_sim, similarity_threshold)

    # 5. Assign labels and metadata
    results = _assign_consistent_labels(existing_labels, groups)

    logger.info(
        "detect_repeated_sections: %d sections, %d groups, groups=%s",
        n_segments,
        len(groups),
        [sorted(g) for g in groups],
    )

    return results


def _cosine_recurrence_fallback(chroma: np.ndarray) -> np.ndarray:
    """Fallback recurrence matrix using pairwise cosine similarity between frames.

    Used when ``librosa.segment`` is unavailable (e.g. in test environments).
    """
    # Normalize each column (frame) to unit length
    norms = np.linalg.norm(chroma, axis=0, keepdims=True)
    norms = np.clip(norms, 1e-10, None)
    chroma_normed = chroma / norms
    # Cosine similarity = dot product of unit vectors
    R = chroma_normed.T @ chroma_normed
    # Clip to [0, 1] for affinity interpretation
    R = np.clip(R, 0.0, 1.0)
    return R


def librosa_segment_recurrence(chroma: np.ndarray) -> np.ndarray:
    """Compute recurrence matrix from chroma features.

    Wraps ``librosa.segment.recurrence_matrix`` with affinity mode and
    symmetric output. Falls back to cosine similarity if librosa.segment
    is unavailable or if the recurrence matrix computation fails (e.g.
    on synthetic data with sparse k-NN graphs).
    """
    try:
        import librosa.segment
        return librosa.segment.recurrence_matrix(chroma, mode="affinity", sym=True)
    except Exception:
        return _cosine_recurrence_fallback(chroma)
