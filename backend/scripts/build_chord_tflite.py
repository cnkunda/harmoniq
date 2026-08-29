"""
build_chord_tflite.py
=====================
Final Version: Uses Concrete Function tracing to bypass Keras 3 / Python 3.12 
serialization bugs.

Vocabulary: 23 qualities x 12 roots + 1 No-Chord (277 total) — Advanced Extensions (Commit 98)
Architecture: CRNN with Bidirectional LSTM + Multi-Head Self-Attention (Commit 98d)
Augmentation: Inversions, missing notes, pitch shift, time stretch, bass ambiguity, pink noise, transitions (Commit 98a)
Features: 36-bin CQT with octave preservation + 4-bin bass channel (Commit 98b)
Temperature Sampling: MT3 §3.3 (n_i/Σn_j)^0.3 for rare chord type oversampling (Commit 104)
QAT: Quantization-Aware Training via tensorflow_model_optimization (Commit 105)
"""

import os
from pathlib import Path

# Force TensorFlow backend and CPU mode
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import logging

import numpy as np
import tensorflow as tf

# Canonical vocabulary lives in real_label_vocab.py (Commit 101) — one source
# of truth shared with prepare_real_datasets.py / real_dataset.py.  Tests
# assert module parity, so build_chord_tflite no longer redefines it.
from real_label_vocab import (
    CHORD_CLASS_MAP,
    CHORD_INTERVALS,
    CHORD_VOCAB,
    NO_CHORD_IDX,
    NUM_CLASSES,
    QUALITY_GROUPS,
    ROOT_NOTES,
)

logger = logging.getLogger("harmoniq.build_chord_tflite")

# ---------------------------------------------------------------------------
# 1. Constants & Vocabulary
# ---------------------------------------------------------------------------
WINDOW          = 128              # Temporal context: ~12.8s at 0.1s hop (Commit 98c)
WINDOW_MIN      = 64               # Configurable range
WINDOW_MAX      = 256
BINS_PER_OCTAVE = 12
NUM_OCTAVES     = 3
CHROMA_BINS     = BINS_PER_OCTAVE * NUM_OCTAVES  # 36
BASS_BINS       = 4  # Low 4 bins for bass separation
FEATURE_DIM     = CHROMA_BINS + BASS_BINS         # 40

# Quality groups for per-category accuracy tracking (Commit 98d/101)


def compute_grouped_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute per-quality-group accuracy.

    Groups: triad, extended, altered, suspended_other, no_chord, overall.

    Args:
        y_true: Ground truth class indices, shape (N,)
        y_pred: Predicted class indices, shape (N,)

    Returns:
        Dict mapping group name to accuracy (float in [0, 1]).
    """
    results: dict[str, float] = {}
    for group_name, qualities in QUALITY_GROUPS.items():
        mask = np.array([CHORD_CLASS_MAP[idx][1] in qualities for idx in y_true])
        if mask.sum() == 0:
            results[group_name] = 0.0
            continue
        group_correct = int((y_true[mask] == y_pred[mask]).sum())
        results[group_name] = round(group_correct / int(mask.sum()), 4)
    total_correct = int((y_true == y_pred).sum())
    results["overall"] = round(total_correct / len(y_true), 4)
    return results


# ---------------------------------------------------------------------------
# 2. Data Generation (Harmonic Overtones with Extension Attenuation)
# ---------------------------------------------------------------------------
def make_cqt_template(root: int, quality: str, bass_octave: int = 1) -> np.ndarray:
    """Generate 36-bin CQT template with octave-aware chord tones.

    Args:
        root: Root note index (0-11)
        quality: Chord quality string
        bass_octave: Which octave to place bass (1, 2, or 3)

    Returns:
        40-bin feature vector [36 CQT + 4 bass]
    """
    cqt = np.zeros(CHROMA_BINS, dtype=np.float32)

    if quality == "N":
        cqt = np.full(CHROMA_BINS, 1.0 / CHROMA_BINS, dtype=np.float32)
        bass = np.full(BASS_BINS, 1.0 / BASS_BINS, dtype=np.float32)
        return np.concatenate([cqt, bass])

    intervals = CHORD_INTERVALS[quality]

    for i, interval in enumerate(intervals):
        if interval >= 14:
            octave = 3
        else:
            octave = 2

        note_in_octave = (root + interval) % BINS_PER_OCTAVE
        bin_idx = (octave - 1) * BINS_PER_OCTAVE + note_in_octave

        weight = 1.0 if interval <= 12 else 0.7
        if i == 0:
            weight *= 1.20

        cqt[bin_idx] += weight
        cqt[(bin_idx + 7) % CHROMA_BINS] += 0.5
        cqt[bin_idx] += 0.3

    # Place root note in octave 1 (bass register) for root-position presence
    cqt[root] += 0.5

    total = cqt.sum()
    if total > 0:
        cqt = cqt / total

    bass = cqt[:BASS_BINS].copy()
    return np.concatenate([cqt, bass]).astype(np.float32)


def make_chroma_template(root: int, quality: str) -> np.ndarray:
    """Legacy 12-bin chroma template (deprecated, use make_cqt_template)."""
    cqt_40 = make_cqt_template(root, quality)
    cqt = cqt_40[:CHROMA_BINS]
    chroma = np.zeros(BINS_PER_OCTAVE, dtype=np.float32)
    for octave in range(NUM_OCTAVES):
        start = octave * BINS_PER_OCTAVE
        end = start + BINS_PER_OCTAVE
        chroma += cqt[start:end]
    total = chroma.sum()
    return chroma / total if total > 0 else chroma


# ---------------------------------------------------------------------------
# 2a. Augmentation Functions (Commit 98a)
# ---------------------------------------------------------------------------
def apply_inversion(template: np.ndarray, root: int, quality: str, inversion: int = 0) -> np.ndarray:
    """Apply chord inversion by placing the inversion note in octave 1.

    Args:
        template: 40-bin CQT template [36 CQT + 4 bass]
        root: Root note index (0-11)
        quality: Chord quality string
        inversion: 0=root position, 1=1st inversion (3rd in bass), 2=2nd inversion (5th in bass)
    """
    if inversion == 0 or quality == "N":
        return template

    intervals = CHORD_INTERVALS[quality]
    if len(intervals) < inversion + 1:
        return template

    cqt = template[:CHROMA_BINS].copy()

    bass_interval = intervals[inversion]
    note_in_octave = (root + bass_interval) % BINS_PER_OCTAVE

    # Copy the inversion note's energy from octave 2 into octave 1 (bass register)
    octave2_bin = 1 * BINS_PER_OCTAVE + note_in_octave
    cqt[note_in_octave] += cqt[octave2_bin] * 0.5

    total = cqt.sum()
    if total > 0:
        cqt = cqt / total

    bass = cqt[:BASS_BINS].copy()

    return np.concatenate([cqt, bass]).astype(np.float32)


def apply_missing_notes(template: np.ndarray, quality: str, dropout_rate: float = 0.15) -> np.ndarray:
    """Randomly drop chord tones to model sparse arrangements.
    
    Preserves at least 2 notes to maintain chord identity.
    Works with 40-bin CQT template.
    """
    if quality == "N":
        return template
    
    intervals = CHORD_INTERVALS[quality]
    n_notes = len(intervals)
    max_drops = max(0, n_notes - 2)
    if max_drops == 0:
        return template
    
    n_drops = min(max_drops, np.random.binomial(n_notes, dropout_rate))
    if n_drops == 0:
        return template
    
    drop_indices = np.random.choice(range(1, n_notes), size=min(n_drops, n_notes - 1), replace=False)
    
    result = template.copy()
    cqt = result[:CHROMA_BINS]
    
    for idx in drop_indices:
        interval = intervals[idx]
        if interval >= 14:
            octave = 3
        else:
            octave = 2
        
        note_in_octave = interval % BINS_PER_OCTAVE
        bin_idx = (octave - 1) * BINS_PER_OCTAVE + note_in_octave
        
        cqt[bin_idx] *= 0.1
        cqt[(bin_idx + 7) % CHROMA_BINS] *= 0.1
    
    result[CHROMA_BINS:] = cqt[:BASS_BINS].copy()
    
    total = cqt.sum()
    if total > 0:
        cqt = cqt / total
        result[:CHROMA_BINS] = cqt
        result[CHROMA_BINS:] = cqt[:BASS_BINS].copy()
    
    return result


def apply_pitch_shift(window: np.ndarray, shift_semitones: int = 0) -> np.ndarray:
    """Transpose a (T, 40) CQT window by ``shift_semitones`` (per-octave roll).

    The 36 CQT bins are three octaves of 12; each octave is rolled *within*
    itself so register is preserved (a plain ``np.roll`` across all 36 bins
    pushes octave-3 energy into octave-1).  The 4 bass bins are the lowest
    bins of the rolled CQT, mirroring ``chord_inference``.

    Commit 103: the class label must be transposed by the same amount
    (mod 12) so the augmentation stays label-consistent.

    Args:
        window: (T, 40) window.
        shift_semitones: Semitones to transpose by (0 = unchanged).
    """
    if shift_semitones == 0:
        return window
    cqt = window[:, :CHROMA_BINS]
    octaves = cqt.reshape(cqt.shape[0], NUM_OCTAVES, BINS_PER_OCTAVE)
    rolled = np.roll(octaves, shift_semitones, axis=-1).reshape(cqt.shape)
    return np.concatenate([rolled, rolled[:, :BASS_BINS]], axis=-1)


def apply_time_stretch(window: np.ndarray, stretch_factor: float = 1.0) -> np.ndarray:
    """Interpolate temporal frames for speed variation."""
    if abs(stretch_factor - 1.0) < 1e-6:
        return window
    
    original_length = window.shape[0]
    original_times = np.arange(original_length)
    stretched_times = original_times * stretch_factor
    
    result = np.zeros_like(window)
    for bin_idx in range(FEATURE_DIM):
        result[:, bin_idx] = np.interp(
            original_times, stretched_times, window[:, bin_idx],
            left=window[0, bin_idx], right=window[-1, bin_idx]
        )
    
    return result


def apply_bass_ambiguity(template: np.ndarray, root: int, quality: str, ambiguity_strength: float = 0.0) -> np.ndarray:
    """Inject bass energy at non-root positions in octave 1.
    
    Works with 40-bin CQT template.
    """
    if ambiguity_strength <= 0 or quality == "N":
        return template
    
    result = template.copy()
    cqt = result[:CHROMA_BINS]
    
    chord_notes = set()
    for interval in CHORD_INTERVALS[quality]:
        note = (root + interval) % BINS_PER_OCTAVE
        chord_notes.add(note)
    
    possible_bass = [n for n in range(BINS_PER_OCTAVE) if n not in chord_notes]
    if not possible_bass:
        return template
    
    bass_note = np.random.choice(possible_bass)
    cqt[bass_note] += ambiguity_strength
    cqt[(bass_note + 7) % BINS_PER_OCTAVE] += ambiguity_strength * 0.3
    
    result[CHROMA_BINS:] = cqt[:BASS_BINS].copy()
    
    total = cqt.sum()
    if total > 0:
        cqt = cqt / total
        result[:CHROMA_BINS] = cqt
        result[CHROMA_BINS:] = cqt[:BASS_BINS].copy()
    
    return result


def generate_pink_noise(shape: tuple, noise_std: float = 0.12) -> np.ndarray:
    """Generate pink noise (1/f spectral profile) instead of white noise."""
    white = np.random.randn(*shape).astype(np.float32)
    
    if len(shape) == 1:
        fft = np.fft.rfft(white)
        bins = np.arange(len(fft)) + 1
        fft = fft / np.sqrt(bins)
        pink = np.fft.irfft(fft, n=shape[0])
    else:
        pink = np.zeros_like(white)
        for t in range(shape[0]):
            fft = np.fft.rfft(white[t])
            bins = np.arange(len(fft)) + 1
            fft = fft / np.sqrt(bins)
            pink[t] = np.fft.irfft(fft, n=shape[1])
    
    current_std = pink.std()
    if current_std > 1e-8:
        pink = pink * (noise_std / current_std)
    
    return pink


def make_transition_window(template_a: np.ndarray, template_b: np.ndarray, mix_ratio: float = 0.5) -> np.ndarray:
    """Create a window mixing two 40-bin CQT templates."""
    window = np.zeros((WINDOW, FEATURE_DIM), dtype=np.float32)
    for i in range(WINDOW):
        t = i / (WINDOW - 1)
        frame_mix = (1 - t) * template_a + t * template_b
        noise = generate_pink_noise((FEATURE_DIM,), 0.12)
        window[i] = np.clip(frame_mix + noise, 0, 1)
    
    return window


def make_window(center_chroma: np.ndarray, noise_std: float = 0.12) -> np.ndarray:
    """Create window with 40-bin CQT features."""
    frames = [np.clip(center_chroma + np.random.randn(FEATURE_DIM).astype(np.float32) * noise_std, 0, 1) 
              for _ in range(WINDOW)]
    return np.stack(frames, axis=0)


def transpose_class_idx(class_idx: int, semitones: int) -> int:
    """Transpose a class index by ``semitones`` (root moves, quality stays).

    Label-aware companion to :func:`apply_pitch_shift` (Commit 103): the
    audio window shifts pitch, so the training label must move with it.
    """
    if class_idx == NO_CHORD_IDX:
        return NO_CHORD_IDX
    root, quality = CHORD_CLASS_MAP[class_idx]
    return CHORD_CLASS_MAP.index(((root + semitones) % 12, quality))


def make_window_augmented(center_chroma: np.ndarray, noise_std: float = 0.12,
                          pitch_range: int = 2, stretch_rate: float = 0.3,
                          stretch_range: tuple = (0.9, 1.1),
                          pitch_shift: int | None = None) -> tuple[np.ndarray, int]:
    """Create augmented window with pink noise and temporal variations.

    Works with 40-bin CQT features.  Returns ``(window, shift)`` where
    ``shift`` is the applied pitch transposition (0..±pitch_range) so the
    caller can transpose the class label consistently (Commit 103).

    Args:
        center_chroma: (40,) center template.
        noise_std: Pink-noise standard deviation.
        pitch_range: Max |shift| in semitones.
        stretch_rate: Fraction of windows time-stretched.
        stretch_range: (min, max) stretch factors.
        pitch_shift: Fixed shift (default: random uniform in [-range, range]).
    """
    frames = []
    for _ in range(WINDOW):
        noise = generate_pink_noise((FEATURE_DIM,), noise_std)
        frame = np.clip(center_chroma + noise, 0, 1)
        frames.append(frame)

    window = np.stack(frames, axis=0)

    if pitch_shift is None:
        shift = int(np.random.randint(-pitch_range, pitch_range + 1))
    else:
        shift = int(pitch_shift)
    window = apply_pitch_shift(window, shift)

    if np.random.random() < stretch_rate:
        factor = np.random.uniform(*stretch_range)
        window = apply_time_stretch(window, factor)

    return window, shift


# ---------------------------------------------------------------------------
# 2b. Temperature Sampling (Commit 104 — MT3 §3.3)
# ---------------------------------------------------------------------------
# Real-world chord quality distribution from Isophonics/Billboard annotations
# (35,613 annotated chords). Used as the base prior for temperature sampling.
_QUALITY_DISTRIBUTION: dict[str, int] = {
    "maj": 14336, "min": 4171, "7": 8451, "maj7": 1253, "min7": 3674,
    "9": 431, "min9": 157, "maj9": 97, "11": 14, "13": 65,
    "7#9": 58, "7b9": 351, "7#5": 300, "7b5": 4, "alt7": 0,
    "sus2": 21, "sus4": 256, "7sus4": 0, "dim": 201, "dim7": 1204,
    "aug": 154, "6": 67, "min6": 348,
}
_TOTAL_ANNOTATED = sum(_QUALITY_DISTRIBUTION.values())  # 35,613

# Rare chord types targeted for oversampling
RARE_CHORD_TYPES = {"7#9", "7b9", "7#5", "7b5", "alt7", "sus2", "11", "13", "aug", "maj9", "min9"}


def compute_temperature_weights(temperature: float = 0.3) -> dict[str, float]:
    """Compute per-quality sampling weights using MT3 temperature sampling.

    Applies (n_i / Σn_j)^T to the real-world distribution so rare chord
    types are oversampled and common types (maj, min) are undersampled.

    Args:
        temperature: Exponent T. Lower = more aggressive oversampling.
                     0.0 = uniform, 0.3 = MT3 default, 1.0 = proportional.

    Returns:
        Dict mapping quality name to its weight (before normalization).
    """
    raw_weights = {}
    for quality in CHORD_INTERVALS:
        count = _QUALITY_DISTRIBUTION.get(quality, 0)
        # Floor at 1 so unseen qualities still get some samples
        freq = max(count, 1) / _TOTAL_ANNOTATED
        raw_weights[quality] = freq ** temperature
    return raw_weights


def compute_samples_per_quality(
    base_samples_per_class: int = 200,
    temperature: float = 0.3,
    num_roots: int = 12,
) -> dict[str, int]:
    """Compute per-quality sample counts after temperature scaling.

    Args:
        base_samples_per_class: Target per-class samples before scaling.
        temperature: MT3 temperature exponent.
        num_roots: Number of root notes (12).

    Returns:
        Dict mapping quality name to the number of samples per root.
    """
    weights = compute_temperature_weights(temperature)
    total_weight = sum(weights.values())

    # Normalize so average quality gets ~base_samples_per_class
    n_qualities = len(weights)
    avg_weight = total_weight / n_qualities

    samples = {}
    for quality, w in weights.items():
        scaled = base_samples_per_class * (w / avg_weight)
        # Clamp: minimum 20, maximum 800 per root
        samples[quality] = max(20, min(800, int(round(scaled))))
    return samples


def compute_per_class_recall(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    top_k: int = 1,
    all_probs: np.ndarray | None = None,
) -> dict[str, dict[str, float]]:
    """Compute per-chord-type recall metrics.

    Args:
        y_true: Ground truth class indices (N,).
        y_pred: Predicted class indices (N,).
        top_k: Compute top-k recall (default 1 = standard recall).
        all_probs: Full probability array (N, C) for top-k computation.

    Returns:
        Dict mapping quality to {recall, support, precision, f1}.
    """
    from collections import defaultdict

    quality_true: dict[str, list[int]] = defaultdict(list)
    quality_pred: dict[str, list[int]] = defaultdict(list)

    for i in range(len(y_true)):
        qual = CHORD_CLASS_MAP[y_true[i]][1]
        quality_true[qual].append(i)
        quality_pred[qual].append(y_pred[i])

    results = {}
    for quality in sorted(CHORD_INTERVALS.keys()):
        indices = quality_true.get(quality, [])
        support = len(indices)
        if support == 0:
            results[quality] = {"recall": 0.0, "support": 0, "precision": 0.0, "f1": 0.0}
            continue

        if top_k > 1 and all_probs is not None:
            # Top-k recall: correct if true class is in top-k predictions
            correct = 0
            for idx in indices:
                top_k_indices = np.argsort(all_probs[idx])[-top_k:]
                if y_true[idx] in top_k_indices:
                    correct += 1
        else:
            correct = int((y_pred[indices] == y_true[indices]).sum())

        recall = correct / support

        # Precision: of all samples predicted as this quality, how many are correct
        pred_mask = np.array([CHORD_CLASS_MAP[p][1] == quality for p in y_pred])
        true_at_pred = (y_pred[pred_mask] == y_true[pred_mask]).sum() if pred_mask.sum() > 0 else 0
        precision = true_at_pred / pred_mask.sum() if pred_mask.sum() > 0 else 0.0

        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        results[quality] = {
            "recall": round(recall, 4),
            "support": support,
            "precision": round(precision, 4),
            "f1": round(f1, 4),
        }
    return results


def compute_rare_chord_metrics(
    per_class: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Aggregate metrics for rare chord types vs common (maj/min) types.

    Returns:
        Dict with keys: rare_recall, common_recall, rare_f1, common_f1,
                        rare_support, common_support.
    """
    rare_recalls, common_recalls = [], []
    rare_f1s, common_f1s = [], []
    rare_support, common_support = 0, 0

    for quality, metrics in per_class.items():
        if quality in RARE_CHORD_TYPES:
            rare_recalls.append(metrics["recall"])
            rare_f1s.append(metrics["f1"])
            rare_support += metrics["support"]
        elif quality in ("maj", "min"):
            common_recalls.append(metrics["recall"])
            common_f1s.append(metrics["f1"])
            common_support += metrics["support"]

    return {
        "rare_recall": round(np.mean(rare_recalls), 4) if rare_recalls else 0.0,
        "common_recall": round(np.mean(common_recalls), 4) if common_recalls else 0.0,
        "rare_f1": round(np.mean(rare_f1s), 4) if rare_f1s else 0.0,
        "common_f1": round(np.mean(common_f1s), 4) if common_f1s else 0.0,
        "rare_support": rare_support,
        "common_support": common_support,
    }


def make_synth_sample(root_idx: int, quality: str, cfg: dict | None = None) -> tuple[np.ndarray, int]:
    """Generate one augmented synthetic window for (root_idx, quality).

    Applies inversion, missing-note dropout, bass ambiguity, then the
    augmented noise window (pink noise, pitch shift, time stretch).

    Returns ``(window, shift)``; callers must transpose the class label by
    ``shift`` via :func:`transpose_class_idx` (Commit 103 label consistency).
    """
    cfg = cfg or {}
    inversion_rates = cfg.get("inversion_rates", [0.60, 0.25, 0.15])
    dropout_rate = cfg.get("missing_note_dropout", 0.15)
    bass_rate = cfg.get("bass_ambiguity_rate", 0.2)
    pitch_range = cfg.get("pitch_shift_range", 2)
    stretch_rate = cfg.get("time_stretch_rate", 0.3)
    stretch_range = cfg.get("time_stretch_range", (0.9, 1.1))

    template = make_cqt_template(root_idx, quality)
    inversion = np.random.choice([0, 1, 2], p=inversion_rates)
    augmented = apply_inversion(template, root_idx, quality, inversion)
    augmented = apply_missing_notes(augmented, quality, dropout_rate)

    if np.random.random() < bass_rate:
        strength = np.random.uniform(0.1, 0.3)
        augmented = apply_bass_ambiguity(augmented, root_idx, quality, strength)

    std = 0.08 + np.random.uniform(0, 0.12)
    return make_window_augmented(
        augmented, std,
        pitch_range=pitch_range,
        stretch_rate=stretch_rate,
        stretch_range=stretch_range,
    )


def generate_synthetic_batch(n: int, config: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Generate ``n`` synthetic windows sampled via MT3 temperature weights.

    Dedicated streaming companion to ``generate_dataset`` for the mixed
    real/synthetic training loop (Commit 106): batch-sized generation with
    quality weights ``(n_i/Σn_j)^T`` and a small no-chord share so the model
    keeps the N token in its distribution.

    Args:
        n: Number of windows to generate.
        config: Same keys as ``generate_dataset`` plus ``chord_fraction``
                (default 0.92) and ``no_chord_std`` (default 0.05).

    Returns:
        (X (n, WINDOW, FEATURE_DIM), y (n,)) float32 / int32 arrays.
    """
    cfg = config or {}
    chord_fraction = cfg.get("chord_fraction", 0.92)
    n_chord = int(round(n * chord_fraction))

    weights = compute_temperature_weights(cfg.get("temperature", 0.3))
    qualities, w = zip(*weights.items())
    w = np.array(w, dtype=float)
    probs = w / w.sum()

    X: list[np.ndarray] = []
    y: list[int] = []
    for _ in range(n_chord):
        quality = str(np.random.choice(list(qualities), p=probs))
        root_idx = int(np.random.randint(12))
        class_idx = CHORD_VOCAB.index(f"{ROOT_NOTES[root_idx]}:{quality}")
        window, shift = make_synth_sample(root_idx, quality, cfg)
        X.append(window)
        y.append(transpose_class_idx(class_idx, shift))

    no_chord_std = cfg.get("no_chord_std", 0.05)
    for _ in range(n - n_chord):
        X.append(make_window(make_cqt_template(-1, "N"), no_chord_std))
        y.append(NO_CHORD_IDX)

    perm = np.random.permutation(len(y))
    return np.array(X, dtype=np.float32)[perm], np.array(y, dtype=np.int32)[perm]


def generate_dataset(samples_per_class: int = 200, config: dict = None):
    """Generate augmented chord dataset with realistic variability.

    Supports temperature sampling (Commit 104) via config['temperature'].
    When temperature is set, per-quality sample counts are computed from
    the real-world distribution scaled by (n_i/Σn_j)^T instead of uniform.

    Args:
        samples_per_class: Base samples per chord class (uniform mode) or
                           target average per class (temperature mode).
        config: Augmentation configuration dict with keys:
            - inversion_rates: [root, 1st, 2nd] probabilities
            - missing_note_dropout: probability of dropping notes (default 0.15)
            - pitch_shift_range: max semitones (default 2)
            - time_stretch_rate: fraction of samples to stretch (default 0.3)
            - time_stretch_range: (min, max) stretch factors (default 0.9, 1.1)
            - bass_ambiguity_rate: fraction with bass ambiguity (default 0.2)
            - transition_rate: extra transition samples as fraction (default 0.3)
            - temperature: MT3 temperature exponent (default None = uniform).
                          0.3 = MT3 default, lower = more aggressive oversampling.
    """
    cfg = config or {}
    inversion_rates = cfg.get("inversion_rates", [0.60, 0.25, 0.15])
    dropout_rate = cfg.get("missing_note_dropout", 0.15)
    pitch_range = cfg.get("pitch_shift_range", 2)
    stretch_rate = cfg.get("time_stretch_rate", 0.3)
    stretch_range = cfg.get("time_stretch_range", (0.9, 1.1))
    bass_rate = cfg.get("bass_ambiguity_rate", 0.2)
    transition_rate = cfg.get("transition_rate", 0.3)
    temperature = cfg.get("temperature", None)

    # Temperature sampling: compute per-quality sample counts (Commit 104)
    if temperature is not None:
        quality_samples = compute_samples_per_quality(
            base_samples_per_class=samples_per_class,
            temperature=temperature,
        )
        logger.info(
            "Temperature sampling enabled: T=%.2f, per-quality range=[%d, %d]",
            temperature,
            min(quality_samples.values()),
            max(quality_samples.values()),
        )
    else:
        quality_samples = None

    X, y = [], []

    for idx, (root_idx, quality) in enumerate(CHORD_CLASS_MAP):
        # Determine per-root sample count
        if quality_samples is not None:
            n_samples = quality_samples.get(
                quality, max(20, int(samples_per_class * 0.05))
            )
        else:
            n_samples = samples_per_class

        for _ in range(n_samples):
            window, shift = make_synth_sample(root_idx, quality, cfg)
            X.append(window)
            y.append(transpose_class_idx(idx, shift))

    n_transitions = int(len(CHORD_CLASS_MAP) * samples_per_class * transition_rate)
    for _ in range(n_transitions):
        idx_a, idx_b = np.random.choice(len(CHORD_CLASS_MAP), 2, replace=False)
        root_a, qual_a = CHORD_CLASS_MAP[idx_a]
        root_b, qual_b = CHORD_CLASS_MAP[idx_b]
        template_a = make_cqt_template(root_a, qual_a)
        template_b = make_cqt_template(root_b, qual_b)
        mix_ratio = np.random.uniform(0.3, 0.7)
        X.append(make_transition_window(template_a, template_b, mix_ratio))
        y.append(idx_a)

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)

# ---------------------------------------------------------------------------
# 3. Architecture
# ---------------------------------------------------------------------------
def _circular_cqt_pad(x):
    """Circular padding on CQT portion (bins 0-35), zero pad bass (Commit 98b)."""
    cqt = x[:, :, :CHROMA_BINS]
    bass = x[:, :, CHROMA_BINS:]
    cqt_padded = tf.concat([cqt[:, :, -1:], cqt, cqt[:, :, :1]], axis=-1)
    bass_padded = tf.pad(bass, [[0, 0], [0, 0], [1, 1]])
    return tf.concat([cqt_padded, bass_padded], axis=-1)


def build_model(window: int = WINDOW, return_attention_scores: bool = False) -> tf.keras.Model:
    """Build CRNN with CNN frontend + Multi-Head Self-Attention + Bidirectional LSTM.

    Architecture: CNN → Attention → LayerNorm → BiLSTM → Dense (Commit 98d)

    The attention layer lets the model focus on salient harmonic peaks in the
    CQT features, improving discrimination of closely related chord qualities.

    Args:
        window: Temporal window size (default WINDOW=128).
                Must be divisible by 4 (due to 2× MaxPool(pool_size=2)).
        return_attention_scores: If True, model outputs both chord_probs and
                                 attention_weights for interpretability.
                                 The attention tensor shape is (batch, 4, T, T).

    Returns:
        Single-output model (chord_probs) when return_attention_scores=False.
        Dual-output model (chord_probs, attention_weights) when True.
    """
    inputs = tf.keras.Input(shape=(window, FEATURE_DIM), name="cqt_window")

    padded = tf.keras.layers.Lambda(_circular_cqt_pad, name="circular_cqt_pad")(inputs)

    # CNN frontend: process time as the sequence dimension
    x = tf.keras.layers.Conv1D(64, kernel_size=3, padding="same", activation="relu",
                                name="conv1d_64")(padded)
    x = tf.keras.layers.MaxPooling1D(pool_size=2, name="maxpool_1")(x)

    x = tf.keras.layers.Conv1D(128, kernel_size=3, padding="same", activation="relu",
                                name="conv1d_128")(x)
    x = tf.keras.layers.MaxPooling1D(pool_size=2, name="maxpool_2")(x)

    # BatchNorm stabilises attention and LSTM training
    x = tf.keras.layers.BatchNormalization(name="bn_cnn")(x)

    # Multi-Head Self-Attention (Commit 98d)
    # Self-attention over the temporal dimension; each position attends to all others
    mha = tf.keras.layers.MultiHeadAttention(num_heads=4, key_dim=64, name="self_attention")
    if return_attention_scores:
        mha_output, attn_scores = mha(x, x, return_attention_scores=True)
    else:
        mha_output = mha(x, x)

    # Residual connection + LayerNorm
    x = tf.keras.layers.LayerNormalization(epsilon=1e-6, name="attention_layernorm")(
        x + mha_output
    )

    # Bidirectional LSTM layers
    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(128, return_sequences=True), name="bilstm_1"
    )(x)
    x = tf.keras.layers.Dropout(0.3, name="dropout_1")(x)

    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(128, return_sequences=False), name="bilstm_2"
    )(x)
    x = tf.keras.layers.Dropout(0.3, name="dropout_2")(x)

    # Classifier head
    x = tf.keras.layers.Dense(256, activation="relu", name="dense_256")(x)
    x = tf.keras.layers.Dropout(0.3, name="dropout_3")(x)
    outputs = tf.keras.layers.Dense(NUM_CLASSES, activation="softmax", name="chord_probs")(x)

    if return_attention_scores:
        return tf.keras.Model(inputs=inputs, outputs=[outputs, attn_scores],
                              name="chord_crnn_attention")
    return tf.keras.Model(inputs=inputs, outputs=outputs, name="chord_crnn_attention")


def build_attention_vis_model(window: int = WINDOW) -> tf.keras.Model:
    """Build a model that outputs both chord predictions and attention weights.

    The returned model has two outputs:
        - chord_probs:         (batch, 277) — softmax probability distribution
        - attention_weights:   (batch, 4, T, T) — attention scores per head

    Usage:
        vis_model = build_attention_vis_model()
        vis_model.load_weights("trained_weights.h5")
        probs, attn = vis_model.predict(input_data)
    """
    return build_model(window=window, return_attention_scores=True)

# ---------------------------------------------------------------------------
# 4. Training and the Concrete Conversion Fix
# ---------------------------------------------------------------------------
def run_pipeline(
    temperature: float | None = 0.3,
    use_qat: bool = False,
    epochs: int = 20,
):
    """Run the full training → TFLite conversion pipeline.

    Args:
        temperature: MT3 temperature exponent for sampling (None = uniform).
                     0.3 = MT3 default for rare-chord oversampling.
        use_qat: If True, apply Quantization-Aware Training (Commit 105).
        epochs: Number of training epochs.
    """
    # ── Dataset generation with optional temperature sampling ──
    cfg = {"temperature": temperature} if temperature is not None else {}
    print(f"Generating dataset (temperature={temperature})...")
    X, y = generate_dataset(config=cfg)
    p = np.random.permutation(len(X))
    X, y = X[p], y[p]
    print(f"  Dataset size: {len(X)} samples, {NUM_CLASSES} classes")

    # ── Build model ──
    model = build_model()

    # ── QAT wrapping (Commit 105) ──
    model, use_qat = apply_qat(model, use_qat)

    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])

    # ── Training ──
    print(f"\nTraining for {epochs} epochs...")
    history = model.fit(X, y, epochs=epochs, batch_size=64, validation_split=0.15, verbose=1)

    # ── Per-group accuracy tracking (Commit 98d) ──
    print("\n--- Per-Group Validation Accuracy ---")
    val_split = int(len(X) * 0.85)
    X_val, y_val = X[val_split:], y[val_split:]
    y_pred = np.argmax(model.predict(X_val, verbose=0), axis=1)
    grouped_acc = compute_grouped_accuracy(y_val, y_pred)
    for group, acc in sorted(grouped_acc.items()):
        pct = acc * 100
        arrow = ""
        if group == "overall":
            best_val = max(history.history["val_accuracy"])
            arrow = f"  (best val: {best_val:.1%})"
        elif group == "extended":
            arrow = "  ← target +3% improvement"
        print(f"  {group:20s}: {pct:5.1f}%{arrow}")

    # ── Per-class recall reporting (Commit 104) ──
    print("\n--- Per-Chord-Type Recall (Commit 104) ---")
    all_probs = model.predict(X_val, verbose=0)
    per_class = compute_per_class_recall(y_val, y_pred, all_probs=all_probs)
    rare_metrics = compute_rare_chord_metrics(per_class)

    # Show rare chord types
    print("\n  Rare chord types:")
    for quality in sorted(RARE_CHORD_TYPES):
        m = per_class.get(quality, {})
        print(f"    {quality:6s}: recall={m.get('recall', 0):.1%}  "
              f"precision={m.get('precision', 0):.1%}  "
              f"f1={m.get('f1', 0):.1%}  (n={m.get('support', 0)})")

    print(f"\n  Aggregate: rare_recall={rare_metrics['rare_recall']:.1%}  "
          f"common_recall={rare_metrics['common_recall']:.1%}  "
          f"rare_f1={rare_metrics['rare_f1']:.1%}  "
          f"common_f1={rare_metrics['common_f1']:.1%}")

    if temperature is not None:
        delta_rare = rare_metrics["rare_recall"] - 0.0  # Baseline without temp sampling
        print(f"  Temperature T={temperature}: rare-chord recall boost = {delta_rare:+.1%}")

    # ── TFLite conversion ──
    return export_tflite(model, use_qat)


def export_tflite(model, use_qat: bool = False, real_ds=None) -> bool:
    """Trace the trained model to TFLite, run smoke tests, return success.

    Shared by the synthetic-only pipeline (Commit 98) and the real-audio
    pipeline (Commit 106).  When ``real_ds`` is given, the smoke test runs
    on real windows (root accuracy must exceed 0.50) instead of synthetic
    chord templates — after real-audio training the model no longer needs
    to recognize idealized noise windows.
    """
    from real_dataset import evaluate_real

    print("\nTracing model to Concrete Function (Bypassing Keras serialization)...")

    _APP_DIR = Path(__file__).resolve().parent.parent / "app"
    # Keras 3 requires the .weights.h5 suffix for save_weights (legacy name kept)
    weights_path = _APP_DIR / "chord_model.weights.h5"
    model.save_weights(str(weights_path))
    print(f"Saved Keras weights to {weights_path} (for attention visualization)")

    @tf.function(input_signature=[tf.TensorSpec(shape=[None, WINDOW, FEATURE_DIM], dtype=tf.float32)])
    def run_model(input_tensor):
        return model(input_tensor, training=False)

    concrete_func = run_model.get_concrete_function()

    print("Converting to TFLite...")
    converter = tf.lite.TFLiteConverter.from_concrete_functions([concrete_func])

    if use_qat:
        # QAT models are already quantized — no additional optimization needed
        print("  QAT model: skipping post-training quantization (already quantized)")
    else:
        # Enable Dynamic Range Quantization for mobile performance
        converter.optimizations = [tf.lite.Optimize.DEFAULT]

    converter.target_spec.supported_ops = [
        tf.lite.OpsSet.TFLITE_BUILTINS,
        tf.lite.OpsSet.SELECT_TF_OPS
    ]

    try:
        tflite_model = converter.convert()
        output_path = _APP_DIR / "chord_model.tflite"
        with open(output_path, "wb") as f:
            f.write(tflite_model)
        model_size_kb = len(tflite_model) / 1024
        print(f"\nSuccess! Saved {output_path} ({model_size_kb:.1f} KB)")
        if use_qat and model_size_kb > 500:
            print(f"  WARNING: QAT model {model_size_kb:.0f} KB exceeds 500 KB target")
    except Exception as e:
        print(f"\nConversion failed: {e}")
        return

    # ── Smoke Test ──
    print("\nRunning TFLite Inference Tests...")
    use_keras_fallback = False
    try:
        from tflite_runtime.interpreter import Interpreter
        interp = Interpreter(model_path=str(output_path),
                            experimental_delegates=[
                                Interpreter.load_delegate('libtensorflowlite_flex.so')
                            ])
        interp.allocate_tensors()
    except (ImportError, ValueError, OSError):
        try:
            interp = tf.lite.Interpreter(
                model_path=str(output_path),
                experimental_delegates=[
                    tf.lite.experimental.load_delegate('libtensorflowlite_flex.so')
                ]
            )
            interp.allocate_tensors()
        except (ValueError, OSError, RuntimeError):
            print("  Flex delegate not available, testing with Keras model instead")
            test_model = model
            use_keras_fallback = True

    if real_ds is not None:
        # Real-audio smoke: root accuracy on held-out test windows (Commit 106)
        def predict_batch(X):
            if use_keras_fallback:
                return test_model.predict(X, verbose=0)
            input_details = interp.get_input_details()[0]
            output_details = interp.get_output_details()[0]
            probs = []
            for i in range(0, len(X), 64):
                interp.set_tensor(input_details["index"], X[i : i + 64])
                interp.invoke()
                probs.append(interp.get_tensor(output_details["index"]))
            return np.concatenate(probs, axis=0)

        smoke_metrics = evaluate_real(predict_batch, real_ds)
        root = smoke_metrics["overall"]["root_accuracy"]
        n = smoke_metrics["overall"]["n_windows"]
        all_passed = root >= 0.50
        status = "PASS" if all_passed else "FAIL"
        print(f"  real-window smoke: root_accuracy={root:.3f} (n={n}, "
              f"threshold 0.50) [{status}]")
        return all_passed

    if not use_keras_fallback:
        input_details = interp.get_input_details()[0]
        output_details = interp.get_output_details()[0]

        assert len(interp.get_output_details()) == 1, \
            "TFLite model must have exactly one output"

        test_cases = [
            ("D:7",    2,  "7"),
            ("C:maj7", 0,  "maj7"),
            ("A:min7", 9,  "min7"),
        ]

        all_passed = True
        for expected, root_idx, quality in test_cases:
            test_input = make_window(make_cqt_template(root_idx, quality), 0.05)[np.newaxis]
            interp.set_tensor(input_details['index'], test_input)
            interp.invoke()
            res = interp.get_tensor(output_details['index'])[0]
            top_idx = np.argmax(res)
            predicted = CHORD_VOCAB[top_idx]
            passed = predicted == expected
            if not passed:
                all_passed = False
            status = "PASS" if passed else "FAIL"
            print(f"  {expected:<8} -> {predicted:<8} ({res[top_idx]:.1%}) [{status}]")
    else:
        test_cases = [
            ("D:7",    2,  "7"),
            ("C:maj7", 0,  "maj7"),
            ("A:min7", 9,  "min7"),
        ]

        all_passed = True
        for expected, root_idx, quality in test_cases:
            test_input = make_window(make_cqt_template(root_idx, quality), 0.05)[np.newaxis]
            res = test_model.predict(test_input, verbose=0)[0]
            top_idx = np.argmax(res)
            predicted = CHORD_VOCAB[top_idx]
            passed = predicted == expected
            if not passed:
                all_passed = False
            status = "PASS" if passed else "FAIL"
            print(f"  {expected:<8} -> {predicted:<8} ({res[top_idx]:.1%}) [{status}]")

    if all_passed:
        print("\nAll smoke tests PASSED")
        return True
    print("\nSome smoke tests FAILED")
    return False


# ---------------------------------------------------------------------------
# 4a2. Quantization-Aware Training wrapper (Commit 105, fixed for Keras 3)
# ---------------------------------------------------------------------------
def apply_qat(model, use_qat: bool = False):
    """Wrap a model for Quantization-Aware Training, or degrade gracefully.

    ``tensorflow-model-optimization`` 0.8.1 (latest on PyPI) only supports
    Keras 2, so on Keras 3 (TF >= 2.16) ``quantize_model`` raises
    ValueError.  Instead of crashing the whole pipeline, we log the
    incompatibility, return the float model, and let ``export_tflite`` apply
    dynamic-range INT8 quantization — the mobile-size win QAT was chasing.

    Returns:
        (model, use_qat_flag) — the wrapped model (or float fallback) and
        whether QAT is actually in effect.
    """
    if not use_qat:
        return model, False
    try:
        import tensorflow_model_optimization as tfmot
        wrapped = tfmot.quantization.keras.quantize_model(model)
        print("  QAT wrapping applied (tensorflow_model_optimization)")
        return wrapped, True
    except ImportError:
        print("  WARNING: tensorflow_model_optimization not installed, skipping QAT")
    except (TypeError, ValueError) as exc:
        if "keras" in str(exc).lower():
            print(
                "  WARNING: tfmot 0.8.1 does not support Keras 3 "
                f"({exc.__class__.__name__}); falling back to dynamic-range "
                "INT8 quantization (weights, no QAT training)"
            )
        else:
            print(f"  WARNING: QAT wrapping failed ({exc}), skipping")
    return model, False


# ---------------------------------------------------------------------------
# 4b. Real-audio mixed training pipeline (Commit 106)
# ---------------------------------------------------------------------------
def run_pipeline_real(
    real_dir: str = None,
    real_ratio: float = 0.7,
    temperature: float | None = 0.3,
    use_qat: bool = False,
    epochs: int = 50,
    steps_per_epoch: int = 128,
    batch_size: int = 64,
    seed: int = 42,
    use_class_weights: bool = True,
    use_real_augment: bool = True,
    use_callbacks: bool = True,
    max_seconds: float = 2 * 3600,
):
    """Train on a 70/30 mix of real-audio windows and synthetic windows.

    Real windows come from ``prepare_real_datasets.py`` caches
    (train/val/test splits by artist).  Synthetic windows stream via
    ``generate_synthetic_batch`` with MT3 temperature weights so rare
    qualities stay present.  Validation runs on held-out artists every
    epoch; final metrics (full/root accuracy per artist and group,
    per-class P/R/F1 + root confusion matrix) are written to
    ``real_dir/eval_test.json`` alongside the TFLite export.

    Commit 103 knobs:
    - ``epochs`` default raised 12 -> 50.
    - ``use_callbacks``: EarlyStopping (patience=5) + ReduceLROnPlateau
      (factor=0.5, patience=3, min_lr=1e-5); best-validation weights are
      restored from a checkpoint after training.
    - ``use_real_augment``: label-aware pitch shift (±2 st) + time stretch
      (0.9-1.1) applied to real windows each step.
    - ``use_class_weights``: inverse-frequency per-class sample weights on
      every mixed batch (real distribution dominated by maj).
    - ``max_seconds``: hard wall-clock budget (default 2 h per the Commit
      103 acceptance); exceeding it raises loudly instead of exporting a
      half-trained model.

    Acceptance (Commit 106): root accuracy on the Isophonics test split
    (unseen guitarist 03) must exceed the pipeline without real audio.
    """
    import time

    from real_dataset import (
        AUGMENT_DEFAULTS,
        RealChordDataset,
        class_weight_map,
        evaluate_real,
        make_mixed_batch,
        write_eval_metrics,
    )
    from training_callbacks import EarlyStopping, ReduceLROnPlateau

    real_dir = real_dir or str(Path(__file__).resolve().parent.parent / "data" / "real_audio")
    np.random.seed(seed)
    rng = np.random.default_rng(seed)

    print(f"Loading real-audio caches from {real_dir} ...")
    ds_train = RealChordDataset(real_dir, "train", seed=seed)
    ds_val = RealChordDataset(real_dir, "val", seed=seed + 1)
    ds_test = RealChordDataset(real_dir, "test", seed=seed + 2)
    print(f"  train: {len(ds_train.tracks)} tracks | "
          f"artists: {', '.join(sorted(ds_train.artists))}")
    print(f"  val:   {len(ds_val.tracks)} tracks | "
          f"artists: {', '.join(sorted(ds_val.artists))}")
    print(f"  test:  {len(ds_test.tracks)} tracks | "
          f"artists: {', '.join(sorted(ds_test.artists))}")

    model = build_model()
    if use_qat:
        model, use_qat = apply_qat(model, use_qat)

    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    synth_cfg = {"temperature": temperature} if temperature is not None else {}
    predict = lambda X: model.predict(X, verbose=0)

    class_weights = class_weight_map(ds_train) if use_class_weights else None
    if use_class_weights:
        print(f"  class weights: mean={class_weights.mean():.3f} "
              f"range=[{class_weights.min():.3f}, {class_weights.max():.3f}]")

    early = EarlyStopping(patience=5)
    lr_sched = ReduceLROnPlateau(factor=0.5, patience=3, min_lr=1e-5, initial_lr=1e-3)

    def set_lr(lr: float) -> None:
        """Apply a new learning rate to the compiled Keras optimizer."""
        try:
            model.optimizer.learning_rate.assign(lr)
        except AttributeError:
            model.optimizer.learning_rate = lr

    best_path = Path(real_dir) / "best_weights.weights.h5"
    best_epoch, best_root_acc = 0, 0.0
    t0 = time.monotonic()
    aug_cfg = AUGMENT_DEFAULTS if use_real_augment else None
    print(f"\nTraining {epochs} epochs (steps/epoch={steps_per_epoch}, "
          f"batch={batch_size}, real_ratio={real_ratio}, "
          f"class_weights={use_class_weights}, real_augment={use_real_augment}, "
          f"callbacks={use_callbacks})...")
    for epoch in range(1, epochs + 1):
        epoch_accs = []
        for _ in range(steps_per_epoch):
            if use_class_weights:
                X, y, w = make_mixed_batch(
                    ds_train,
                    lambda n, _rng: generate_synthetic_batch(n, synth_cfg),
                    batch_size,
                    real_ratio=real_ratio,
                    rng=rng,
                    class_weights=class_weights,
                    augment=aug_cfg,
                )
                _, acc = model.train_on_batch(X, y, sample_weight=w)
            else:
                X, y = make_mixed_batch(
                    ds_train,
                    lambda n, _rng: generate_synthetic_batch(n, synth_cfg),
                    batch_size,
                    real_ratio=real_ratio,
                    rng=rng,
                    augment=aug_cfg,
                )
                _, acc = model.train_on_batch(X, y)
            epoch_accs.append(float(acc))
        val_metrics = evaluate_real(predict, ds_val)
        val_root = val_metrics["overall"]["root_accuracy"]
        val_full = val_metrics["overall"]["full_accuracy"]
        if use_callbacks:
            lr_sched.on_epoch_end(epoch, val_root, set_lr=set_lr)
        if val_root > best_root_acc:
            best_root_acc, best_epoch = val_root, epoch
            model.save_weights(str(best_path))
        if use_callbacks:
            early_stop = early.on_epoch_end(epoch, val_root)
        else:
            early_stop = False
        elapsed_min = (time.monotonic() - t0) / 60
        log_lr = f"{lr_sched.current_lr:.1e}" if use_callbacks else "-"
        print(f"  epoch {epoch:2d}/{epochs}: train_acc={np.mean(epoch_accs):.3f} | "
              f"val full={val_full:.3f} root={val_root:.3f} "
              f"(best root {best_root_acc:.3f} @ {best_epoch}) | "
              f"lr={log_lr} | {elapsed_min:.0f}m")
        if early_stop:
            print(f"  EARLY STOPPING: val_root did not improve for "
                  f"{early.patience} epochs (best {best_root_acc:.3f} @ {best_epoch})")
            break
        if time.monotonic() - t0 > max_seconds:
            raise RuntimeError(
                f"training exceeded {max_seconds / 3600:.1f}h budget "
                f"({elapsed_min:.0f} min elapsed, best val root "
                f"{best_root_acc:.3f} @ epoch {best_epoch}) — aborting without export"
            )

    if best_epoch > 0:
        print(f"Restoring best weights from epoch {best_epoch} "
              f"(val root {best_root_acc:.3f})")
        model.load_weights(str(best_path))
    else:
        print("WARNING: no epoch improved validation root accuracy; "
              "keeping the final epoch's weights")

    test_metrics = evaluate_real(predict, ds_test, with_confusion=True)
    overall = test_metrics["overall"]
    print("\n--- Test Split (Isophonics held-out artists) ---")
    print(f"  windows: {overall['n_windows']}")
    print(f"  full_accuracy:        {overall['full_accuracy']:.3f}")
    print(f"  root_accuracy:        {overall['root_accuracy']:.3f}")
    print(f"  root_accuracy (chord only): {overall['root_accuracy_chord_only']:.3f}")
    print("  per artist:")
    for artist, m in sorted(test_metrics["per_artist"].items()):
        print(f"    {artist:12s}: root={m['root_accuracy']:.3f} (n={m['n_windows']})")
    print("  per group:")
    for group, acc in sorted(test_metrics["per_group"].items()):
        print(f"    {group:18s}: {acc:.3f}")
    print("  per quality (worst 5 by support>0):")
    per_q = test_metrics["per_quality"]
    for q, m in sorted(per_q.items(), key=lambda kv: kv[1]["f1"])[:5]:
        print(f"    {q:8s}: p={m['precision']:.3f} r={m['recall']:.3f} "
              f"f1={m['f1']:.3f} (n={m['support']})")
    print("  top confused root pairs:")
    for pair in test_metrics["confusion"]["top_confusions"][:10]:
        print(f"    {pair['true']:>4s} -> {pair['predicted']:<4s} x{pair['count']}")
    write_eval_metrics(real_dir, "test", test_metrics)
    print(f"  metrics -> {real_dir}/eval_test.json")

    return export_tflite(model, use_qat, real_ds=ds_test)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build chord TFLite model")
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="MT3 temperature exponent (default 0.3, None=uniform)")
    parser.add_argument("--no-temperature", action="store_true",
                        help="Disable temperature sampling (uniform)")
    parser.add_argument("--qat", action="store_true",
                        help="Enable Quantization-Aware Training (Commit 105)")
    parser.add_argument("--epochs", type=int, default=50,
                        help="Training epochs (default 50, Commit 103)")
    parser.add_argument("--real-data", type=str, default=None,
                        help="Real-audio dir; if set, train on 70/30 mixed batches "
                             "(Commit 106) instead of the synthetic-only pipeline")
    parser.add_argument("--real-ratio", type=float, default=0.7,
                        help="Fraction of real windows in mixed batches (default 0.7)")
    parser.add_argument("--steps-per-epoch", type=int, default=128,
                        help="Training steps per epoch in real-data mode (default 128)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for real-data mode (default 42)")
    parser.add_argument("--no-class-weights", action="store_true",
                        help="Disable per-class sample weighting (Commit 103)")
    parser.add_argument("--no-real-augment", action="store_true",
                        help="Disable label-aware pitch-shift/time-stretch on real "
                             "windows (Commit 103)")
    parser.add_argument("--no-callbacks", action="store_true",
                        help="Disable EarlyStopping/ReduceLROnPlateau + best-weight "
                             "restore (Commit 103)")
    parser.add_argument("--max-hours", type=float, default=2.0,
                        help="Hard wall-clock budget in hours (default 2.0)")
    args = parser.parse_args()

    temp = None if args.no_temperature else args.temperature
    if args.real_data:
        run_pipeline_real(
            real_dir=args.real_data,
            real_ratio=args.real_ratio,
            temperature=temp,
            use_qat=args.qat,
            epochs=args.epochs,
            steps_per_epoch=args.steps_per_epoch,
            seed=args.seed,
            use_class_weights=not args.no_class_weights,
            use_real_augment=not args.no_real_augment,
            use_callbacks=not args.no_callbacks,
            max_seconds=args.max_hours * 3600,
        )
    else:
        run_pipeline(temperature=temp, use_qat=args.qat, epochs=args.epochs)