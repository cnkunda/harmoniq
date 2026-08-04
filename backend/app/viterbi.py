"""Viterbi decoding for chord progression smoothing (Commit 99).

Post-processes frame-wise chord predictions with the Viterbi algorithm to enforce
plausible chord transitions, suppress flicker, and align chord changes to beat
boundaries.  Includes key-constrained transition costs, duration-aware filtering,
half-beat chord-change resolution, and quality metrics (flicker rate,
beat-alignment gate).
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from pathlib import Path

import numpy as np

from app.schemas import BeatGrid, ChordEvent, ChordTimeline

logger = logging.getLogger("harmoniq.inference.viterbi")

# ---------------------------------------------------------------------------
# Vocabulary helpers (mirrors chord_inference.py)
# ---------------------------------------------------------------------------

_ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_CHORD_QUALITIES = [
    "maj", "min",
    "7", "maj7", "min7",
    "9", "min9", "maj9", "11", "13",
    "7#9", "7b9", "7#5", "7b5", "alt7",
    "sus2", "sus4", "7sus4",
    "dim", "dim7", "aug", "6", "min6",
]

CHORD_VOCAB: list[str] = (
    [f"{root}:{qual}" for qual in _CHORD_QUALITIES for root in _ROOTS] + ["N"]
)
VOCAB_SIZE = len(CHORD_VOCAB)  # 277

# Index of the no-chord token
N_CHORD_IDX = VOCAB_SIZE - 1

# Build root-index lookup: chord_idx -> root_idx (0..11), or -1 for N
_ROOT_IDX: list[int] = []
for q in _CHORD_QUALITIES:
    for r in range(12):
        _ROOT_IDX.append(r)
_ROOT_IDX.append(-1)  # N

# Quality-group membership for diatonic penalty
_QUALITY_SETS: dict[str, set[str]] = {
    "triad":           {"maj", "min"},
    "extended":        {"7", "maj7", "min7", "9", "min9", "maj9", "11", "13"},
    "altered":         {"7#9", "7b9", "7#5", "7b5", "alt7"},
    "suspended_other": {"sus2", "sus4", "7sus4", "dim", "dim7", "aug", "6", "min6"},
}

# Semitone distances for key-constrained costs
_SEMITONE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Diatonic intervals (semitones) for major and minor keys
_MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
_MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]

# ---------------------------------------------------------------------------
# Transition matrix
# ---------------------------------------------------------------------------

_transition_cache_path: Path | None = None
_transition_matrix: np.ndarray | None = None


def _default_transition_matrix() -> np.ndarray:
    """Uniform transition matrix (all transitions equally likely).

    Used as fallback when no learned matrix is available.
    """
    mat = np.full((VOCAB_SIZE, VOCAB_SIZE), 1.0 / VOCAB_SIZE, dtype=np.float64)
    return mat


def build_transition_matrix_from_sequences(
    sequences: list[list[int]],
    smoothing: float = 1e-6,
) -> np.ndarray:
    """Build a transition probability matrix from chord index sequences.

    Args:
        sequences: List of chord index sequences (each sequence is a song/segment).
        smoothing: Laplace smoothing factor to avoid zero probabilities.

    Returns:
        Transition matrix of shape (VOCAB_SIZE, VOCAB_SIZE) with
        transition_matrix[i, j] = P(chord_j | chord_i).
    """
    counts = np.full((VOCAB_SIZE, VOCAB_SIZE), smoothing, dtype=np.float64)
    for seq in sequences:
        for k in range(len(seq) - 1):
            i, j = seq[k], seq[k + 1]
            if 0 <= i < VOCAB_SIZE and 0 <= j < VOCAB_SIZE:
                counts[i, j] += 1.0

    # Normalize rows
    row_sums = counts.sum(axis=1, keepdims=True)
    row_sums = np.maximum(row_sums, 1e-12)
    return counts / row_sums


def build_music_theory_transition_matrix() -> np.ndarray:
    """Build a transition matrix from music-theory priors.

    Uses common chord progressions (I-IV-V-I, ii-V-I, vi-IV, etc.) weighted
    by harmonic plausibility.  This is used as a prior when no training-data
    matrix is available.
    """
    mat = np.full((VOCAB_SIZE, VOCAB_SIZE), 1e-4, dtype=np.float64)

    # Major-key diatonic progressions (root offsets from I)
    # I=0, ii=2, iii=4, IV=5, V=7, vi=9, vii=10 (semitone offsets)
    major_diatonic_roots = [0, 2, 4, 5, 7, 9, 10]
    minor_diatonic_roots = [0, 2, 3, 5, 7, 8, 10]

    # Common progressions as root-offset pairs (from/to)
    common_transitions = [
        (0, 5), (0, 7), (0, 9),    # I -> IV, V, vi
        (5, 0), (5, 7), (5, 9),    # IV -> I, V, vi
        (7, 0), (7, 5), (7, 9),    # V -> I, IV, vi
        (9, 5), (9, 7),             # vi -> IV, V
        (2, 5), (2, 7),             # ii -> IV, V
        (4, 5), (4, 7),             # iii -> IV, V
        (10, 0), (10, 5),           # vii -> I, IV
    ]

    for quality in _CHORD_QUALITIES:
        for root_offset in range(12):
            from_idx = root_offset * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index(quality)
            for to_root_offset in range(12):
                to_idx = to_root_offset * len(_CHORD_QUALITIES) + _CHORD_QUALITIES.index(quality)
                semitone_dist = (to_root_offset - root_offset) % 12

                # Prefer diatonic intervals (fourths, fifths, thirds)
                if semitone_dist in (5, 7):  # Fourth, fifth
                    mat[from_idx, to_idx] = 0.08
                elif semitone_dist in (3, 4, 9):  # Minor/major third, major sixth
                    mat[from_idx, to_idx] = 0.05
                elif semitone_dist == 0:  # Same root (pedal/extend)
                    mat[from_idx, to_idx] = 0.06
                else:
                    mat[from_idx, to_idx] = 0.005

    # Common quality transitions (same root, different quality)
    quality_transitions = [
        ("maj", "min"), ("min", "maj"),
        ("maj", "7"), ("7", "maj"),
        ("maj", "maj7"), ("maj7", "maj"),
        ("min", "min7"), ("min7", "min"),
        ("7", "maj"), ("7", "min"),
    ]
    for q_from, q_to in quality_transitions:
        if q_from in _CHORD_QUALITIES and q_to in _CHORD_QUALITIES:
            qi_from = _CHORD_QUALITIES.index(q_from)
            qi_to = _CHORD_QUALITIES.index(q_to)
            for root in range(12):
                from_idx = root * len(_CHORD_QUALITIES) + qi_from
                to_idx = root * len(_CHORD_QUALITIES) + qi_to
                mat[from_idx, to_idx] = max(mat[from_idx, to_idx], 0.04)

    # N transitions: N -> anything with small probability
    for j in range(VOCAB_SIZE):
        mat[N_CHORD_IDX, j] = 0.02
    mat[N_CHORD_IDX, N_CHORD_IDX] = 0.8

    # Normalize rows
    row_sums = mat.sum(axis=1, keepdims=True)
    row_sums = np.maximum(row_sums, 1e-12)
    mat = mat / row_sums

    return mat


def load_transition_matrix(cache_dir: Path | None = None) -> np.ndarray:
    """Load transition matrix from cache or build from music theory.

    Checks for a cached JSON file at ``{cache_dir}/transition_matrix.json``.
    If absent, builds from music-theory priors and caches the result.
    """
    global _transition_matrix, _transition_cache_path

    if _transition_matrix is not None:
        return _transition_matrix

    if cache_dir is not None:
        _transition_cache_path = cache_dir / "transition_matrix.json"
        if _transition_cache_path.exists():
            try:
                data = json.loads(_transition_cache_path.read_text())
                mat = np.array(data, dtype=np.float64)
                if mat.shape == (VOCAB_SIZE, VOCAB_SIZE):
                    _transition_matrix = mat
                    logger.info("Loaded cached transition matrix from %s", _transition_cache_path)
                    return _transition_matrix
            except Exception:
                logger.warning("Failed to load cached transition matrix; rebuilding")

    mat = build_music_theory_transition_matrix()

    if cache_dir is not None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            path = cache_dir / "transition_matrix.json"
            path.write_text(json.dumps(mat.tolist()))
            logger.info("Cached transition matrix to %s", path)
        except Exception:
            logger.warning("Failed to cache transition matrix")

    _transition_matrix = mat
    return _transition_matrix


# ---------------------------------------------------------------------------
# Key-constrained transition costs
# ---------------------------------------------------------------------------

def _key_penalty(from_idx: int, to_idx: int, key_root: int | None, is_minor: bool) -> float:
    """Return a multiplicative penalty for non-diatonic transitions.

    Lower penalty = more preferred.  Returns 1.0 for diatonic transitions,
    higher values for chromatic ones.
    """
    if key_root is None:
        return 1.0

    from_root = _ROOT_IDX[from_idx]
    to_root = _ROOT_IDX[to_idx]

    if from_root < 0 or to_root < 0:
        return 1.0

    scale = _MINOR_SCALE if is_minor else _MAJOR_SCALE
    scale_pitches = set((key_root + s) % 12 for s in scale)

    # Check if both roots are diatonic
    from_diatonic = from_root in scale_pitches
    to_diatonic = to_root in scale_pitches

    if from_diatonic and to_diatonic:
        return 1.0
    elif from_diatonic or to_diatonic:
        return 1.5  # One chromatic note
    else:
        return 2.5  # Both chromatic


def _parse_key(key_signature: str | None) -> tuple[int | None, bool]:
    """Parse a key signature string into (root_pitch_class, is_minor).

    Examples: "C major" -> (0, False), "A minor" -> (9, True), None -> (None, False)
    """
    if not key_signature:
        return None, False

    parts = key_signature.strip().split()
    if len(parts) < 2:
        return None, False

    root_str = parts[0]
    mode = parts[1].lower()

    if root_str not in _SEMITONE_NAMES:
        return None, False

    root = _SEMITONE_NAMES.index(root_str)
    is_minor = mode == "minor"
    return root, is_minor


# ---------------------------------------------------------------------------
# Viterbi decoder
# ---------------------------------------------------------------------------

def viterbi_decode(
    emissions: list[dict],
    transition_matrix: np.ndarray | None = None,
    key_signature: str | None = None,
) -> list[int]:
    """Run Viterbi decoding over frame-wise chord predictions.

    Args:
        emissions: List of dicts with keys ``time``, ``chord``, ``confidence``.
            Each dict represents one frame's prediction from the TFLite model.
        transition_matrix: Pre-computed transition matrix (VOCAB_SIZE x VOCAB_SIZE).
            If None, uses the music-theory prior.
        key_signature: Optional key signature string (e.g., "C major") for
            key-constrained transition costs.

    Returns:
        List of decoded chord indices (one per emission frame).
    """
    T = len(emissions)
    if T == 0:
        return []

    if transition_matrix is None:
        transition_matrix = load_transition_matrix()

    key_root, is_minor = _parse_key(key_signature)

    # Build emission log-probabilities
    chord_to_idx: dict[str, int] = {c: i for i, c in enumerate(CHORD_VOCAB)}

    # Pre-compute key penalties for all transitions
    key_penalties = np.ones((VOCAB_SIZE, VOCAB_SIZE), dtype=np.float64)
    if key_root is not None:
        for i in range(VOCAB_SIZE):
            for j in range(VOCAB_SIZE):
                key_penalties[i, j] = _key_penalty(i, j, key_root, is_minor)

    # Adjusted transition log-probs
    adjusted = transition_matrix * key_penalties
    row_sums = adjusted.sum(axis=1, keepdims=True)
    row_sums = np.maximum(row_sums, 1e-12)
    adjusted = adjusted / row_sums
    log_trans = np.log(np.maximum(adjusted, 1e-12))

    # Viterbi initialization
    log_emit = np.full((T, VOCAB_SIZE), -1e12, dtype=np.float64)
    for t, em in enumerate(emissions):
        idx = chord_to_idx.get(em["chord"], N_CHORD_IDX)
        conf = float(em.get("confidence", 0.5))
        # Map confidence to log-prob: higher confidence -> stronger emission
        log_emit[t, idx] = math.log(max(conf, 1e-6))
        # Also allow nearby chords with lower probability
        # (emission model is sparse: mostly just the top prediction)

    # Viterbi forward pass
    V = np.full((T, VOCAB_SIZE), -1e12, dtype=np.float64)
    backpointer = np.zeros((T, VOCAB_SIZE), dtype=np.int32)

    # Initialize
    V[0] = log_emit[0]

    # Forward pass
    for t in range(1, T):
        for j in range(VOCAB_SIZE):
            # V[t-1, i] + log_trans[i, j] for all i
            scores = V[t - 1] + log_trans[:, j]
            best_i = int(np.argmax(scores))
            V[t, j] = scores[best_i] + log_emit[t, j]
            backpointer[t, j] = best_i

    # Backtracking
    path = np.zeros(T, dtype=np.int32)
    path[T - 1] = int(np.argmax(V[T - 1]))
    for t in range(T - 2, -1, -1):
        path[t] = backpointer[t + 1, path[t + 1]]

    return path.tolist()


# ---------------------------------------------------------------------------
# Beat-aligned Viterbi (beat-level decoding)
# ---------------------------------------------------------------------------

def viterbi_decode_beats(
    beat_predictions: list[list[dict]],
    transition_matrix: np.ndarray | None = None,
    key_signature: str | None = None,
) -> list[int]:
    """Run Viterbi on beat-level aggregated predictions.

    Each element of ``beat_predictions`` is a list of frame-level predictions
    within one beat interval.  We aggregate them into a single emission
    distribution per beat, then run Viterbi over beats.

    Args:
        beat_predictions: Per-beat lists of frame predictions.
        transition_matrix: Pre-computed transition matrix.
        key_signature: Optional key for diatonic constraints.

    Returns:
        List of decoded chord indices, one per beat.
    """
    if not beat_predictions:
        return []

    if transition_matrix is None:
        transition_matrix = load_transition_matrix()

    key_root, is_minor = _parse_key(key_signature)
    chord_to_idx: dict[str, int] = {c: i for i, c in enumerate(CHORD_VOCAB)}

    # Aggregate per-beat emission distributions
    T = len(beat_predictions)
    emit_probs = np.zeros((T, VOCAB_SIZE), dtype=np.float64)

    for t, frames in enumerate(beat_predictions):
        if not frames:
            emit_probs[t, N_CHORD_IDX] = 1.0
            continue
        for f in frames:
            idx = chord_to_idx.get(f["chord"], N_CHORD_IDX)
            emit_probs[t, idx] += f.get("confidence", 0.5)
        row_sum = emit_probs[t].sum()
        if row_sum > 0:
            emit_probs[t] /= row_sum
        else:
            emit_probs[t, N_CHORD_IDX] = 1.0

    # Key penalties
    key_penalties = np.ones((VOCAB_SIZE, VOCAB_SIZE), dtype=np.float64)
    if key_root is not None:
        for i in range(VOCAB_SIZE):
            for j in range(VOCAB_SIZE):
                key_penalties[i, j] = _key_penalty(i, j, key_root, is_minor)

    adjusted = transition_matrix * key_penalties
    row_sums = adjusted.sum(axis=1, keepdims=True)
    row_sums = np.maximum(row_sums, 1e-12)
    adjusted = adjusted / row_sums
    log_trans = np.log(np.maximum(adjusted, 1e-12))
    log_emit = np.log(np.maximum(emit_probs, 1e-12))

    # Viterbi forward pass
    V = np.full((T, VOCAB_SIZE), -1e12, dtype=np.float64)
    backpointer = np.zeros((T, VOCAB_SIZE), dtype=np.int32)

    V[0] = log_emit[0]

    for t in range(1, T):
        for j in range(VOCAB_SIZE):
            scores = V[t - 1] + log_trans[:, j]
            best_i = int(np.argmax(scores))
            V[t, j] = scores[best_i] + log_emit[t, j]
            backpointer[t, j] = best_i

    # Backtracking
    path = np.zeros(T, dtype=np.int32)
    path[T - 1] = int(np.argmax(V[T - 1]))
    for t in range(T - 2, -1, -1):
        path[t] = backpointer[t + 1, path[t + 1]]

    return path.tolist()


# ---------------------------------------------------------------------------
# Duration-aware filtering
# ---------------------------------------------------------------------------

def _filter_short_chords(
    events: list[ChordEvent],
    beats: list[float],
    min_beats: float = 1.0,
) -> list[ChordEvent]:
    """Suppress chord outliers shorter than ``min_beats`` beats.

    A chord shorter than the threshold is replaced with its predecessor
    unless it is a transition chord (surrounded by different chords on
    both sides that match each other — i.e., the flicker pattern).
    """
    if len(events) < 3 or len(beats) < 2:
        return events

    # Compute beat duration (median gap)
    gaps = [beats[i + 1] - beats[i] for i in range(len(beats) - 1)]
    if not gaps:
        return events
    beat_dur = float(np.median(gaps))
    if beat_dur <= 0:
        return events

    min_duration = min_beats * beat_dur
    filtered = list(events)

    for i in range(1, len(filtered) - 1):
        curr = filtered[i]
        prev = filtered[i - 1]
        nxt = filtered[i + 1]

        # Compute duration of current chord
        if i + 1 < len(filtered):
            duration = filtered[i + 1].timestamp - curr.timestamp
        else:
            duration = beat_dur  # Last chord gets one beat

        if duration < min_duration and curr.chord != "N":
            # Replace with predecessor if this is an isolated flicker
            if prev.chord == nxt.chord and prev.chord != curr.chord:
                filtered[i] = ChordEvent(
                    timestamp=curr.timestamp,
                    chord=prev.chord,
                    confidence=round(curr.confidence * 0.8, 3),
                )
            # Otherwise keep it (might be a genuine quick change)

    return filtered


# ---------------------------------------------------------------------------
# Half-beat chord change resolution
# ---------------------------------------------------------------------------

def _resolve_half_beat_changes(
    events: list[ChordEvent],
    beats: list[float],
    frame_predictions: list[dict] | None = None,
    tie_threshold: float = 0.15,
) -> list[ChordEvent]:
    """Emit two ChordEvents per beat when a tie is detected.

    When two competing chords within a single beat window have confidence
    difference < ``tie_threshold``, split the beat into two half-beat events.
    """
    if not events or len(beats) < 2:
        return events

    resolved: list[ChordEvent] = []

    for i, event in enumerate(events):
        # Find frames within this beat
        beat_start = beats[i]
        beat_end = beats[i + 1] if i + 1 < len(beats) else beat_start + 0.5

        if frame_predictions is None:
            resolved.append(event)
            continue

        beat_frames = [
            f for f in frame_predictions
            if beat_start <= f["time"] < beat_end
        ]

        if len(beat_frames) < 2:
            resolved.append(event)
            continue

        # Count chords and their average confidence
        chord_counts: dict[str, list[float]] = {}
        for f in beat_frames:
            chord_counts.setdefault(f["chord"], []).append(f["confidence"])

        if len(chord_counts) < 2:
            resolved.append(event)
            continue

        # Sort by total confidence (sum of confidences)
        sorted_chords = sorted(
            chord_counts.items(),
            key=lambda x: sum(x[1]),
            reverse=True,
        )

        top_chord, top_confs = sorted_chords[0]
        second_chord, second_confs = sorted_chords[1]

        top_total = sum(top_confs)
        second_total = sum(second_confs)
        total = top_total + second_total

        if total <= 0:
            resolved.append(event)
            continue

        diff = abs(top_total - second_total) / total

        if diff < tie_threshold:
            # Split into half-beat
            mid = (beat_start + beat_end) / 2.0
            resolved.append(ChordEvent(
                timestamp=beat_start,
                chord=top_chord,
                confidence=round(top_total / len(top_confs), 3),
            ))
            resolved.append(ChordEvent(
                timestamp=mid,
                chord=second_chord,
                confidence=round(second_total / len(second_confs), 3),
            ))
        else:
            resolved.append(event)

    return resolved


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------

def compute_flicker_rate(events: list[ChordEvent]) -> float:
    """Compute the rate of adjacent-beat chord changes (flicker rate).

    Returns a value between 0.0 (no flickering) and 1.0 (every beat changes).
    Target: <5%.
    """
    if len(events) < 2:
        return 0.0

    changes = 0
    for i in range(1, len(events)):
        if events[i].chord != events[i - 1].chord:
            changes += 1

    return changes / (len(events) - 1)


def compute_beat_alignment(
    events: list[ChordEvent],
    downbeats: list[float],
    tolerance_s: float = 0.05,
) -> float:
    """Measure fraction of chord changes landing on downbeat boundaries.

    Args:
        events: Chord events with timestamps.
        downbeats: Downbeat timestamps from BeatGrid.
        tolerance_s: Time tolerance in seconds for alignment matching.

    Returns:
        Fraction of chord changes aligned to a downbeat (0.0 to 1.0).
        Target: >90%.
    """
    if len(events) < 2 or not downbeats:
        return 0.0

    aligned = 0
    total_changes = 0

    for i in range(1, len(events)):
        if events[i].chord != events[i - 1].chord:
            total_changes += 1
            change_time = events[i].timestamp
            # Check if any downbeat is within tolerance
            for db in downbeats:
                if abs(change_time - db) <= tolerance_s:
                    aligned += 1
                    break

    if total_changes == 0:
        return 1.0  # No changes = trivially aligned

    return aligned / total_changes


def compute_beat_alignment_all_beats(
    events: list[ChordEvent],
    beats: list[float],
    tolerance_s: float = 0.05,
) -> float:
    """Measure fraction of chord changes landing on ANY beat boundary.

    This is a less strict version of compute_beat_alignment that checks
    alignment to all beats, not just downbeats.
    """
    if len(events) < 2 or not beats:
        return 0.0

    aligned = 0
    total_changes = 0

    for i in range(1, len(events)):
        if events[i].chord != events[i - 1].chord:
            total_changes += 1
            change_time = events[i].timestamp
            for b in beats:
                if abs(change_time - b) <= tolerance_s:
                    aligned += 1
                    break

    if total_changes == 0:
        return 1.0

    return aligned / total_changes


def compute_chord_change_histogram(events: list[ChordEvent]) -> dict[str, int]:
    """Compute a histogram of chord-change intervals.

    Returns a dict mapping interval description to count, e.g.
    {"0-1 beats": 5, "1-2 beats": 12, "2-4 beats": 8, "4+ beats": 3}.
    """
    if len(events) < 2:
        return {}

    # Compute median beat duration from event gaps
    gaps = []
    for i in range(1, len(events)):
        gaps.append(events[i].timestamp - events[i - 1].timestamp)

    if not gaps:
        return {}

    median_gap = float(np.median(gaps))
    if median_gap <= 0:
        return {}

    histogram: dict[str, int] = {
        "0-1 beats": 0,
        "1-2 beats": 0,
        "2-4 beats": 0,
        "4+ beats": 0,
    }

    for gap in gaps:
        beats = gap / median_gap
        if beats < 1.0:
            histogram["0-1 beats"] += 1
        elif beats < 2.0:
            histogram["1-2 beats"] += 1
        elif beats < 4.0:
            histogram["2-4 beats"] += 1
        else:
            histogram["4+ beats"] += 1

    return histogram


def compute_flicker_events(events: list[ChordEvent]) -> list[tuple[int, str, str, str]]:
    """Identify specific flicker events (isolated chord changes).

    Returns list of (index, prev_chord, flicker_chord, next_chord) tuples.
    """
    flickers = []
    for i in range(1, len(events) - 1):
        prev = events[i - 1].chord
        curr = events[i].chord
        nxt = events[i + 1].chord
        if curr != prev and curr != nxt and prev == nxt:
            flickers.append((i, prev, curr, nxt))
    return flickers


# ---------------------------------------------------------------------------
# Main post-processing pipeline
# ---------------------------------------------------------------------------

def postprocess_chords(
    events: list[ChordEvent],
    beats: list[float],
    downbeats: list[float],
    transition_matrix: np.ndarray | None = None,
    key_signature: str | None = None,
    frame_predictions: list[dict] | None = None,
    enable_half_beat: bool = True,
    tie_threshold: float = 0.15,
) -> tuple[ChordTimeline, dict]:
    """Full Viterbi post-processing pipeline.

    1. Viterbi decoding on beat-level aggregated predictions
    2. Duration-aware filtering (suppress <1-beat outliers)
    3. Half-beat resolution (split ties)
    4. Quality metrics (flicker rate, beat alignment, histogram)

    Returns:
        Tuple of (smoothed ChordTimeline, metrics dict).
    """
    if not events:
        return ChordTimeline(events=[]), {}

    if transition_matrix is None:
        transition_matrix = load_transition_matrix()

    chord_to_idx: dict[str, int] = {c: i for i, c in enumerate(CHORD_VOCAB)}
    idx_to_chord: dict[int, str] = {i: c for i, c in enumerate(CHORD_VOCAB)}

    # Group frame predictions by beat for beat-level Viterbi
    beat_grouped: list[list[dict]] = []
    if frame_predictions:
        for i in range(len(beats) - 1):
            b_start = beats[i]
            b_end = beats[i + 1]
            beat_frames = [
                f for f in frame_predictions
                if b_start <= f["time"] < b_end
            ]
            beat_grouped.append(beat_frames)
        # Last beat
        if len(beats) > 1:
            b_start = beats[-1]
            beat_frames = [
                f for f in frame_predictions
                if f["time"] >= b_start
            ]
            beat_grouped.append(beat_frames)
    else:
        # Build beat_grouped from events (fallback)
        for i, ev in enumerate(events):
            beat_grouped.append([{"chord": ev.chord, "confidence": ev.confidence, "time": ev.timestamp}])

    # Run beat-level Viterbi
    decoded_indices = viterbi_decode_beats(beat_grouped, transition_matrix, key_signature)

    # Build decoded events
    decoded_events: list[ChordEvent] = []
    for i, idx in enumerate(decoded_indices):
        if i < len(events):
            timestamp = events[i].timestamp
        elif i < len(beats):
            timestamp = beats[i]
        else:
            break

        # Use the confidence from the original event if available
        orig_conf = events[i].confidence if i < len(events) else 0.5
        decoded_events.append(ChordEvent(
            timestamp=timestamp,
            chord=idx_to_chord.get(idx, "N"),
            confidence=round(orig_conf, 3),
        ))

    # Duration-aware filtering
    decoded_events = _filter_short_chords(decoded_events, beats)

    # Half-beat resolution
    if enable_half_beat:
        decoded_events = _resolve_half_beat_changes(
            decoded_events, beats, frame_predictions, tie_threshold
        )

    # Compute quality metrics
    flicker_rate = compute_flicker_rate(decoded_events)
    beat_align_downbeat = compute_beat_alignment(decoded_events, downbeats)
    beat_align_all = compute_beat_alignment_all_beats(decoded_events, beats)
    histogram = compute_chord_change_histogram(decoded_events)
    flicker_events = compute_flicker_events(decoded_events)

    metrics = {
        "flicker_rate": round(flicker_rate, 4),
        "beat_alignment_downbeat": round(beat_align_downbeat, 4),
        "beat_alignment_all_beats": round(beat_align_all, 4),
        "chord_change_histogram": histogram,
        "flicker_event_count": len(flicker_events),
        "total_events": len(decoded_events),
        "non_n_events": len([e for e in decoded_events if e.chord != "N"]),
    }

    logger.info(
        "Viterbi post-processing: flicker=%.2f%%, beat_align_downbeat=%.1f%%, "
        "beat_align_all=%.1f%%, events=%d",
        flicker_rate * 100,
        beat_align_downbeat * 100,
        beat_align_all * 100,
        len(decoded_events),
    )

    return ChordTimeline(events=decoded_events), metrics
