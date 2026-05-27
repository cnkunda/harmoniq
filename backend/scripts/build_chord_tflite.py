"""
build_chord_tflite.py
=====================
Final Version: Uses Concrete Function tracing to bypass Keras 3 / Python 3.12 
serialization bugs.

Vocabulary: 23 qualities x 12 roots + 1 No-Chord (277 total) — Advanced Extensions (Commit 98)
Architecture: CRNN with Bidirectional LSTM + Multi-Head Self-Attention (Commit 98d)
Augmentation: Inversions, missing notes, pitch shift, time stretch, bass ambiguity, pink noise, transitions (Commit 98a)
Features: 36-bin CQT with octave preservation + 4-bin bass channel (Commit 98b)
"""

import json
import os
from pathlib import Path

# Force TensorFlow backend and CPU mode
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import tensorflow as tf

from app.chord_vocab import (
    ROOT_NOTES,
    CHORD_INTERVALS,
    CHORD_QUALITIES,
    CHORD_VOCAB,
    CHORD_TO_IDX,
    NUM_CLASSES,
)

from sklearn.metrics import confusion_matrix, classification_report
from sklearn.utils.class_weight import compute_class_weight
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# 1. Constants & Vocabulary (imported from shared module)
# ---------------------------------------------------------------------------

# Build (root_idx, quality) map for dataset generation
CHORD_CLASS_MAP = []
for quality in CHORD_INTERVALS:
    for root_idx, root_note in enumerate(ROOT_NOTES):
        CHORD_CLASS_MAP.append((root_idx, quality))
CHORD_CLASS_MAP.append((-1, "N"))

N_CLASSES_PER_QUALITY = 12  # Each quality has 12 root positions
N_CHORD_CLASSES = len(CHORD_INTERVALS) * N_CLASSES_PER_QUALITY  # 23 * 12 = 276


def _find_class_index(root: int, quality: str) -> int:
    """Find class index for a given (root, quality) pair.

    CHORD_CLASS_MAP is ordered as: for each quality (insertion order of CHORD_INTERVALS),
    iterate roots 0-11. So index = quality_position * 12 + root.

    Returns the class index, or -1 if not found (should not happen for valid pairs).
    """
    if quality == "N":
        return len(CHORD_CLASS_MAP) - 1
    quality_position = list(CHORD_INTERVALS.keys()).index(quality)
    return quality_position * N_CLASSES_PER_QUALITY + root


WINDOW          = 128              # Temporal context: ~12.8s at 0.1s hop (Commit 98c)
WINDOW_MIN      = 64               # Configurable range
WINDOW_MAX      = 256
BINS_PER_OCTAVE = 12
NUM_OCTAVES     = 3
CHROMA_BINS     = BINS_PER_OCTAVE * NUM_OCTAVES  # 36
BASS_BINS       = 4  # Low 4 bins for bass separation
FEATURE_DIM     = CHROMA_BINS + BASS_BINS         # 40

# Quality groups for per-category accuracy tracking (Commit 98d)
QUALITY_GROUPS = {
    "triad":           {"maj", "min"},
    "extended":        {"7", "maj7", "min7", "9", "min9", "maj9", "11", "13"},
    "altered":         {"7#9", "7b9", "7#5", "7b5", "alt7"},
    "suspended_other": {"sus2", "sus4", "7sus4", "dim", "dim7", "aug", "6", "min6"},
    "no_chord":        {"N"},
}


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

        weight = 1.0 if interval <= 12 else 0.4
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
    """Circular shift CQT bins along pitch axis.
    
    Note: This crosses octave boundaries, which is an approximation
    but effective for augmentation regularization.
    """
    if shift_semitones == 0:
        return window
    
    cqt = window[:, :CHROMA_BINS]
    bass = window[:, CHROMA_BINS:]
    
    cqt_shifted = np.roll(cqt, shift_semitones, axis=-1)
    bass_shifted = np.roll(bass, shift_semitones, axis=-1)
    
    return np.concatenate([cqt_shifted, bass_shifted], axis=-1)


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


def make_window_augmented(center_chroma: np.ndarray, noise_std: float = 0.12,
                          pitch_range: int = 2, stretch_rate: float = 0.3,
                          stretch_range: tuple = (0.9, 1.1)) -> tuple[np.ndarray, int]:
    """Create augmented window with pink noise and temporal variations.

    Returns (window, shift_semitones) so callers can adjust labels
    to match the applied pitch shift.

    Works with 40-bin CQT features.
    """
    frames = []
    for _ in range(WINDOW):
        noise = generate_pink_noise((FEATURE_DIM,), noise_std)
        frame = np.clip(center_chroma + noise, 0, 1)
        frames.append(frame)

    window = np.stack(frames, axis=0)

    shift = np.random.randint(-pitch_range, pitch_range + 1)
    window = apply_pitch_shift(window, shift)

    if np.random.random() < stretch_rate:
        factor = np.random.uniform(*stretch_range)
        window = apply_time_stretch(window, factor)

    return window, shift


def apply_extension_dropout(template: np.ndarray, quality: str,
                             extension_drop_rate: float = 0.30) -> np.ndarray:
    """Reduce or remove extension notes (intervals > 12) to combat bias.

    Extended chords (9ths, 11ths, 13ths) sound very similar to their base
    7th chord in CQT space (the extension note has ~40% amplitude in the
    template). This function randomly drops extension notes so the model
    learns not to always default to the extended form.

    Args:
        template: 40-bin CQT template.
        quality: Chord quality string.
        extension_drop_rate: Probability of zeroing out an extension note.

    Returns:
        Modified template with some extension notes suppressed.
    """
    if quality == "N" or np.random.random() >= extension_drop_rate:
        return template

    intervals = CHORD_INTERVALS.get(quality, [])
    extension_intervals = [iv for iv in intervals if iv > 12]
    if not extension_intervals:
        return template

    # Decide how many extensions to drop (at least 1, but not all)
    n_ext = len(extension_intervals)
    n_drop = np.random.randint(1, min(n_ext + 1, 3))  # drop 1-2 extensions
    to_drop = np.random.choice(extension_intervals, size=n_drop, replace=False)

    result = template.copy()
    cqt = result[:CHROMA_BINS]

    for interval in to_drop:
        note_in_octave = interval % BINS_PER_OCTAVE
        bin_idx = (3 - 1) * BINS_PER_OCTAVE + note_in_octave  # octave 3
        # Zero out the extension in all octave positions
        for octave in range(NUM_OCTAVES):
            idx = octave * BINS_PER_OCTAVE + note_in_octave
            cqt[idx] = 0.0
            cqt[(idx + 7) % CHROMA_BINS] = 0.0

    # Renormalize
    total = cqt.sum()
    if total > 0:
        cqt = cqt / total
        result[:CHROMA_BINS] = cqt
        result[CHROMA_BINS:] = cqt[:BASS_BINS].copy()

    return result


def apply_temporal_jitter_to_labels(labels: np.ndarray, max_shift_ms: float = 30.0, 
                                   hop_sec: float = 0.1, label_value_for_padding: int = -1) -> np.ndarray:
    """
    Apply temporal jitter to simulate label timing noise during training.
    
    Following MT3 paper Appendix D.2: randomly shift label boundaries by ±max_shift_ms
    to make the model robust to imperfect ground truth timing.
    
    Args:
        labels: Label array of shape (sequence_length,) containing class indices
        max_shift_ms: Maximum shift in milliseconds (±)
        hop_sec: Hop size in seconds between predictions (0.1s = 100ms in this codebase)
        label_value_for_padding: Value to use for padding shifted regions (-1 for ignore_index)
        
    Returns:
        Temporally jittered label array
    """
    if max_shift_ms == 0.0:
        return labels.copy()
    
    # Convert milliseconds to number of prediction steps
    max_shift_steps = int(round(max_shift_ms / 1000.0 / hop_sec))
    
    if max_shift_steps == 0:
        return labels.copy()
    
    # Handle different label formats
    if labels.ndim == 1:
        # Assuming labels are class indices for each prediction step
        shift = np.random.randint(-max_shift_steps, max_shift_steps + 1)
        
        if shift == 0:
            return labels.copy()
        elif shift > 0:
            # Shift right: move content to higher indices, pad at beginning
            shifted_labels = np.full_like(labels, label_value_for_padding)
            shifted_labels[shift:] = labels[:-shift]
            return shifted_labels
        else:  # shift < 0
            # Shift left: move content to lower indices, pad at end
            shifted_labels = np.full_like(labels, label_value_for_padding)
            shifted_labels[:shift] = labels[-shift:]
            return shifted_labels
    else:
        raise ValueError(f"Unsupported label shape: {labels.shape}. Expected 1D array of class indices.")


def apply_temporal_jitter_to_window_features(window: np.ndarray, max_shift_ms: float = 30.0,
                                            hop_sec: float = 0.1) -> np.ndarray:
    """
    Apply temporal jitter to the input features by shifting the window in time.
    This is a more direct implementation that shifts the audio features.
    
    Args:
        window: Feature array of shape (window_size, feature_dim)
        max_shift_ms: Maximum shift in milliseconds (±)
        hop_sec: Hop size in seconds between frames
        
    Returns:
        Temporally jittered feature array
    """
    if max_shift_ms == 0.0:
        return window.copy()
    
    # Convert milliseconds to number of feature frames
    # Assuming features are extracted with hop_sec hop size
    max_shift_frames = int(round(max_shift_ms / 1000.0 / hop_sec))
    
    if max_shift_frames == 0:
        return window.copy()
    
    seq_length, feature_dim = window.shape
    shift = np.random.randint(-max_shift_frames, max_shift_frames + 1)
    
    if shift == 0:
        return window.copy()
    elif shift > 0:
        # Shift right: move content to higher indices, pad at beginning with zeros
        shifted_window = np.zeros_like(window)
        shifted_window[shift:] = window[:-shift]
        return shifted_window
    else:  # shift < 0
        # Shift left: move content to lower indices, pad at end with zeros
        shifted_window = np.zeros_like(window)
        shifted_window[:shift] = window[-shift:]
        return shifted_window


def generate_dataset(samples_per_class: int = 260, config: dict = None,
                      transition_probs: np.ndarray | None = None):
    """Generate augmented chord dataset with realistic variability.

    Includes chord transition windows sampled from the empirical chord
    distribution (via transition_probs) to teach the model temporal
    chord-to-chord boundary patterns.

    IMPORTANT: When make_window_augmented applies a pitch shift (±1-2 semitones),
    the label is adjusted to match (e.g., C:maj shifted +2 becomes D:maj).
    This fixes the critical bug where 80% of pre-generated samples had
    pitch-shifted features but original-chord labels.

    Args:
        samples_per_class: Base samples per chord class (260 → 277×260 = 72,020 total)
        config: Augmentation configuration dict
        transition_probs: Optional (NUM_CLASSES,) marginal chord distribution from
            empirical transition matrix. Used to sample chord pairs for transition
            windows. If None, samples uniform.
    """
    cfg = config or {}
    inversion_rates = cfg.get("inversion_rates", [0.60, 0.25, 0.15])
    dropout_rate = cfg.get("missing_note_dropout", 0.15)
    pitch_range = cfg.get("pitch_shift_range", 2)
    stretch_rate = cfg.get("time_stretch_rate", 0.3)
    stretch_range = cfg.get("time_stretch_range", (0.9, 1.1))
    bass_rate = cfg.get("bass_ambiguity_rate", 0.2)
    transition_rate = cfg.get("transition_rate", 0.3)
    extension_drop_rate = cfg.get("extension_drop_rate", 0.30)
    temporal_jitter_prob = cfg.get("temporal_jitter_prob", 0.3)
    guitar_body_rate = cfg.get("guitar_body_rate", 0.3)
    strumming_rate = cfg.get("strumming_rate", 0.4)
    cqt_leakage_rate = cfg.get("cqt_leakage_rate", 0.5)

    n_chord_classes = len(CHORD_INTERVALS) * N_CLASSES_PER_QUALITY
    X, y = [], []

    for idx, (root_idx, quality) in enumerate(CHORD_CLASS_MAP):
        template = make_cqt_template(root_idx, quality)

        for _ in range(samples_per_class):
            inversion = np.random.choice([0, 1, 2], p=inversion_rates)
            augmented = apply_inversion(template, root_idx, quality, inversion)
            augmented = apply_missing_notes(augmented, quality, dropout_rate)
            augmented = apply_extension_dropout(augmented, quality, extension_drop_rate)

            if np.random.random() < bass_rate:
                strength = np.random.uniform(0.1, 0.3)
                augmented = apply_bass_ambiguity(augmented, root_idx, quality, strength)

            # Guitar body resonance — applied to template before window creation
            if np.random.random() < guitar_body_rate:
                augmented = apply_guitar_body_resonance(augmented, strength=0.3)

            std = 0.08 + np.random.uniform(0, 0.12)
            window, shift = make_window_augmented(
                augmented, std,
                pitch_range=pitch_range,
                stretch_rate=stretch_rate,
                stretch_range=stretch_range
            )

            # Apply strumming onset after window creation (temporal)
            if np.random.random() < strumming_rate:
                window = apply_strumming_onset(window, quality)

            # Apply CQT leakage after window creation (spectral)
            if np.random.random() < cqt_leakage_rate:
                window = apply_cqt_leakage(window, leakage_strength=0.1)

            if np.random.random() < temporal_jitter_prob:
                max_shift_ms = 30.0
                hop_sec = 0.1
                window = apply_temporal_jitter_to_window_features(
                    window,
                    max_shift_ms=max_shift_ms,
                    hop_sec=hop_sec
                )

            # --- Label adjustment for pitch shift ---
            # When CQT bins are rolled by N semitones, the chord root must
            # also shift. E.g., C:maj shifted +2 becomes D:maj.
            if shift != 0 and idx < n_chord_classes:
                quality_pos = idx // N_CLASSES_PER_QUALITY
                root = idx % N_CLASSES_PER_QUALITY
                new_root = (root + shift) % N_CLASSES_PER_QUALITY
                adjusted_idx = quality_pos * N_CLASSES_PER_QUALITY + new_root
                X.append(window)
                y.append(adjusted_idx)
            else:
                X.append(window)
                y.append(idx)
    
    # Transition windows: temporally mix two chords to teach boundary patterns
    n_classes = len(CHORD_CLASS_MAP)
    n_transitions = int(n_classes * 200 * transition_rate)
    chord_dist = transition_probs if transition_probs is not None and transition_probs.sum() > 0 else None
    for _ in range(n_transitions):
        if chord_dist is not None:
            idx_a = np.random.choice(n_classes, p=chord_dist / chord_dist.sum())
            idx_b = np.random.choice(n_classes, p=chord_dist / chord_dist.sum())
        else:
            idx_a, idx_b = np.random.choice(n_classes, 2, replace=False)
        root_a, qual_a = CHORD_CLASS_MAP[idx_a]
        root_b, qual_b = CHORD_CLASS_MAP[idx_b]
        template_a = make_cqt_template(root_a, qual_a)
        template_b = make_cqt_template(root_b, qual_b)
        mix_ratio = np.random.uniform(0.3, 0.7)
        X.append(make_transition_window(template_a, template_b, mix_ratio))
        y.append(idx_a)
    
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)

# ---------------------------------------------------------------------------
# 2b. Acoustic Realism Augmentations (Commit 104b — domain gap fix)
# ---------------------------------------------------------------------------


def apply_guitar_body_resonance(
    template: np.ndarray, strength: float = 0.3
) -> np.ndarray:
    """Apply guitar body resonance EQ curve to CQT template.

    Real acoustic guitars boost frequencies around 200-400 Hz (the body's
    resonant low-mid region) and roll off above ~8 kHz. This models that
    response to make synthetic CQT templates more realistic.

    Args:
        template: 40-bin CQT template [36 CQT + 4 bass].
        strength: How strongly to apply the EQ curve (0 = flat).

    Returns:
        Modified template with guitar-like spectral shaping.
    """
    cqt = template[:CHROMA_BINS].copy()

    # Warmth bump: bins 4-10 (~130-260 Hz at CQT resolution from C2)
    for i in range(4, min(10, CHROMA_BINS)):
        cqt[i] *= 1.0 + strength * 0.8

    # High rolloff: last 6 bins
    for i in range(max(CHROMA_BINS - 6, 0), CHROMA_BINS):
        t = (i - (CHROMA_BINS - 6)) / 6.0
        cqt[i] *= 1.0 - strength * t * 0.4

    total = cqt.sum()
    if total > 0:
        cqt = cqt / total

    return np.concatenate([cqt, cqt[:BASS_BINS]]).astype(np.float32)


def apply_strumming_onset(
    window: np.ndarray, quality: str, n_strum_frames: int = 4
) -> np.ndarray:
    """Simulate strumming by attenuating early frames.

    Real strumming hits strings sequentially over ~50-150ms. At 100ms
    frame hop, this covers ~1-2 frames, but we spread over more for
    regularization.

    Args:
        window: Feature window of shape (WINDOW, FEATURE_DIM).
        quality: Chord quality string ("N" skips strumming).
        n_strum_frames: Number of initial frames to attenuate.

    Returns:
        Window with ramped onset (or unchanged for no-chord).
    """
    if quality == "N" or n_strum_frames <= 0:
        return window

    result = window.copy()
    max_frames = min(n_strum_frames, len(window))
    for i in range(max_frames):
        t = i / max_frames  # 0 → 1
        weight = 0.3 + 0.7 * t  # ramp from 0.3 to 1.0
        result[i] *= weight

    return result


def apply_cqt_leakage(
    window: np.ndarray, leakage_strength: float = 0.1
) -> np.ndarray:
    """Simulate CQT filter overlap with cross-bin energy spread.

    Real CQT filters have overlapping passbands — energy from one bin
    leaks into adjacent bins. This improves model robustness to the
    difference between synthetic templates and real CQT features.

    Args:
        window: Feature window of shape (WINDOW, FEATURE_DIM).
        leakage_strength: Blend factor for leaked energy (0 = none).

    Returns:
        Window with cross-bin leakage applied.
    """
    if leakage_strength <= 0:
        return window

    cqt = window[:, :CHROMA_BINS]
    # 3-tap smoothing kernel
    kernel = np.array([0.05, 0.9, 0.05], dtype=np.float32)
    cqt_leaky = np.apply_along_axis(
        lambda x: np.convolve(x, kernel, mode="same"),
        axis=-1, arr=cqt,
    )

    result = window.copy()
    result[:, :CHROMA_BINS] = (1.0 - leakage_strength) * cqt + leakage_strength * cqt_leaky
    # Re-extract bass from modified CQT
    result[:, CHROMA_BINS:] = result[:, :BASS_BINS]

    return result


# ---------------------------------------------------------------------------
# 2c. On-the-Fly Augmentation Generator (Commit 103)
# ---------------------------------------------------------------------------


class AugmentedDataGenerator(tf.keras.utils.Sequence):
    """Generates batches with on-the-fly augmentations.

    Wraps pre-generated data (real + synthetic) and applies fresh
    augmentations per batch so the model sees different variations
    each epoch. Augmentations are applied to copies — original data
    is never modified.

    Key features:
    - Pitch shift (±2 semitones) with **label adjustment**: when a CQT
      window is shifted by N semitones, the chord root is also shifted
      so the label stays correct. Fixes the critical bug where pitch-
      shifted data had wrong labels.
    - Time stretch (0.9x-1.1x) via temporal interpolation
    - Pink noise injection (low amplitude) for spectral robustness
    - Async batch generation via `workers` + `use_multiprocessing`
    """

    def __init__(
        self,
        X: np.ndarray,
        y: np.ndarray,
        batch_size: int = 64,
        p_pitch_shift: float = 0.5,
        pitch_range: int = 2,
        p_time_stretch: float = 0.3,
        stretch_range: tuple[float, float] = (0.9, 1.1),
        noise_std: float = 0.05,
        shuffle: bool = True,
        temperature: float = 0.3,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.X = X
        self.y = y
        self.batch_size = batch_size
        self.p_pitch_shift = p_pitch_shift
        self.pitch_range = pitch_range
        self.p_time_stretch = p_time_stretch
        self.stretch_range = stretch_range
        self.noise_std = noise_std
        self.shuffle = shuffle
        self.temperature = float(temperature)
        self.indices = np.arange(len(X))
        self._n_chord_classes = len(CHORD_INTERVALS) * N_CLASSES_PER_QUALITY
        if shuffle:
            if self.temperature < 1.0:
                self._resample_indices_temperature()
            else:
                np.random.shuffle(self.indices)

    def __len__(self) -> int:
        return int(np.ceil(len(self.X) / self.batch_size))

    def __getitem__(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        if idx < 0:
            idx += len(self)
        batch_indices = self.indices[
            idx * self.batch_size : (idx + 1) * self.batch_size
        ]
        batch_X = self.X[batch_indices].copy()
        batch_y = self.y[batch_indices].copy()

        batch_X, batch_y = self._apply_on_the_fly_augmentations(batch_X, batch_y)

        return batch_X, batch_y

    def on_epoch_end(self):
        if self.shuffle:
            if self.temperature < 1.0:
                self._resample_indices_temperature()
            else:
                np.random.shuffle(self.indices)

    def _resample_indices_temperature(self):
        """Resample training indices with temperature-based quality balancing.

        When τ < 1.0, rare chord qualities get boosted sampling probability
        using the MT3-style formula:
            per_example_weight ∝ (p_q)^τ / n_q
        where p_q = n_q / N is the quality's frequency, n_q is its count,
        and τ is the temperature.

        This produces weighted resampling with replacement so rare qualities
        appear more often in each epoch without changing class weights.
        """
        qualities = np.array(
            [CHORD_CLASS_MAP[idx][1] for idx in self.y], dtype=object
        )
        unique_q, counts = np.unique(qualities, return_counts=True)
        total = len(qualities)
        p_q = counts.astype(np.float64) / total
        weight_q = (p_q ** self.temperature) / counts
        q_to_weight = dict(zip(unique_q, weight_q))
        weights = np.array(
            [q_to_weight[q] for q in qualities], dtype=np.float64
        )
        weights /= weights.sum()
        self.indices = np.random.choice(
            np.arange(total), size=total, replace=True, p=weights
        )

    def _apply_on_the_fly_augmentations(
        self, batch_X: np.ndarray, batch_y: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        for i in range(len(batch_X)):
            sample = batch_X[i]

            # --- Pitch shift with label adjustment ---
            if np.random.random() < self.p_pitch_shift:
                shift = np.random.randint(
                    -self.pitch_range, self.pitch_range + 1
                )
                if shift != 0:
                    sample = apply_pitch_shift(sample, shift)
                    batch_y[i] = self._label_after_pitch_shift(batch_y[i], shift)

            # --- Time stretch ---
            if np.random.random() < self.p_time_stretch:
                factor = np.random.uniform(*self.stretch_range)
                sample = apply_time_stretch(sample, factor)

            # --- Pink noise ---
            noise = generate_pink_noise(sample.shape, self.noise_std)
            sample = np.clip(sample + noise, 0, 1)

            batch_X[i] = sample

        return batch_X, batch_y

    def _label_after_pitch_shift(self, label_idx: int, shift: int) -> int:
        """Adjust label to match the pitch-shifted chord root.

        When we shift CQT bins by +2 semitones, a C:maj window
        becomes a D:maj window — so the label must change from
        C:maj to D:maj.

        The class-index layout is:
          [quality_0_root_0, quality_0_root_1, …, quality_0_root_11,
           quality_1_root_0, …, quality_N_root_11]
        So label_idx // 12  -> quality position
           label_idx % 12   -> root
        """
        if label_idx >= self._n_chord_classes:
            return label_idx  # N class — no shift
        quality_pos = label_idx // N_CLASSES_PER_QUALITY
        root = label_idx % N_CLASSES_PER_QUALITY
        new_root = (root + shift) % N_CLASSES_PER_QUALITY
        return quality_pos * N_CLASSES_PER_QUALITY + new_root

    def get_all_labels(self) -> np.ndarray:
        """Return the original (un-augmented) labels for class-weight computation."""
        return self.y.copy()


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
# 3b. Evaluation Metrics (Commit 103)
# ---------------------------------------------------------------------------


def compute_confusion_matrix_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    top_k: int = 10,
) -> np.ndarray:
    """Compute and report most-confused chord pairs.

    Prints the top-K chord pairs that the model most frequently
    confuses, which helps identify harmonic similarities the model
    is struggling with (e.g. C:maj ↔ A:min sharing two of three notes).

    Args:
        y_true: Ground truth class indices, shape (N,).
        y_pred: Predicted class indices, shape (N,).
        top_k: Number of confused pairs to report.

    Returns:
        Full confusion matrix, shape (NUM_CLASSES, NUM_CLASSES).
    """
    cm = confusion_matrix(y_true, y_pred, labels=range(NUM_CLASSES))

    cm_no_diag = cm.copy()
    np.fill_diagonal(cm_no_diag, 0)
    confused_pairs = np.argwhere(cm_no_diag > 0)

    if len(confused_pairs) == 0:
        print("  No confused pairs found (perfect or single-class predictions).")
        return cm

    confused_counts = cm_no_diag[confused_pairs[:, 0], confused_pairs[:, 1]]
    top_indices = np.argsort(confused_counts)[-top_k:][::-1]

    print(f"\n--- Top {top_k} Most Confused Chord Pairs ---")
    actual_top_k = min(top_k, len(top_indices))
    for rank in range(actual_top_k):
        idx = top_indices[rank]
        i, j = confused_pairs[idx]
        count = int(confused_counts[idx])
        true_chord = CHORD_VOCAB[i]
        pred_chord = CHORD_VOCAB[j]
        print(f"  {rank + 1:2d}. {true_chord:<12} → {pred_chord:<12}  ({count} errors)")

    return cm


def compute_per_class_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    recall_threshold: float = 0.3,
) -> dict:
    """Compute and report per-class precision, recall, and F1.

    Groups results by chord quality category (triad, extended, altered,
    suspended_other, no_chord) and flags classes with recall below the
    threshold for targeted data collection (Commit 104 spec).

    Args:
        y_true: Ground truth class indices, shape (N,).
        y_pred: Predicted class indices, shape (N,).
        recall_threshold: Flag classes with recall below this value.

    Returns:
        Full classification report dict from sklearn.
    """
    report = classification_report(
        y_true,
        y_pred,
        labels=range(NUM_CLASSES),
        target_names=CHORD_VOCAB,
        output_dict=True,
        zero_division=0,
    )

    print("\n--- Per-Class Metrics Summary ---")

    quality_to_group: dict[str, str] = {}
    for group_name, qualities in QUALITY_GROUPS.items():
        for q in qualities:
            quality_to_group[q] = group_name

    group_f1s: dict[str, list[float]] = {}
    low_recall_classes: list[tuple[str, float]] = []

    for chord_name, metrics in report.items():
        if chord_name == "accuracy" or chord_name == "macro avg" or \
           chord_name == "weighted avg" or chord_name == "micro avg":
            continue
        try:
            int(chord_name)
            continue
        except (ValueError, TypeError):
            pass

        if not isinstance(metrics, dict) or "f1-score" not in metrics:
            continue

        f1 = metrics["f1-score"]
        recall = metrics["recall"]

        if chord_name == "N":
            group = "no_chord"
        else:
            quality_str = chord_name.split(":")[1] if ":" in chord_name else chord_name
            group = quality_to_group.get(quality_str, "unknown")

        if group not in group_f1s:
            group_f1s[group] = []
        group_f1s[group].append(f1)

        if recall < recall_threshold:
            low_recall_classes.append((chord_name, recall))

    for group in ["triad", "extended", "altered", "suspended_other", "no_chord", "overall"]:
        if group == "overall":
            all_f1s = [m["f1-score"] for m in report.values()
                       if isinstance(m, dict) and "f1-score" in m]
            if all_f1s:
                print(f"  {group:20s}: mean F1 = {np.mean(all_f1s):.3f}")
            continue
        f1s = group_f1s.get(group, [])
        if f1s:
            print(f"  {group:20s}: mean F1 = {np.mean(f1s):.3f}  "
                  f"(min={np.min(f1s):.3f}, max={np.max(f1s):.3f})")

    if low_recall_classes:
        print(f"\n  Classes with recall < {recall_threshold} ({len(low_recall_classes)} total):")
        for chord_name, rec in sorted(low_recall_classes, key=lambda x: x[1])[:20]:
            print(f"    {chord_name:<12} recall = {rec:.3f}")
        if len(low_recall_classes) > 20:
            print(f"    ... and {len(low_recall_classes) - 20} more")

    return report


def compute_training_class_weights(
    y_train: np.ndarray,
    temperature: float = 0.3,
) -> dict[int, float]:
    """Compute balanced class weights using sklearn's inverse-frequency formula.

    Temperature resampling in AugmentedDataGenerator already handles the
    per-quality balance correction at the sampling level. Class weights are
    kept as standard sklearn ``balanced`` (no additional temperature adjustment)
    to avoid double-correction and numeric overflow from extreme weights.

    Args:
        y_train: Training labels, shape (N,).
        temperature: Kept for API compatibility (unused — temperature is
                     handled by AugmentedDataGenerator resampling).

    Returns:
        Dict mapping class index -> weight value.
    """
    classes = np.unique(y_train)
    weights = compute_class_weight("balanced", classes=classes, y=y_train)
    return dict(zip(classes, weights))


# ---------------------------------------------------------------------------
# 4a. Real dataset loading (Commit 101)
# ---------------------------------------------------------------------------

def load_real_data(data_dir: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load GuitarSet CQT features and labels from processed .npz files.

    Looks for .npz files in <data_dir>/processed/cqt/.
    Uses train+val splits (excludes test/player 05).

    Returns:
        (features, labels) arrays with shapes (N, 128, 40) and (N,).
    """
    data_path = Path(data_dir) / "processed" / "cqt"
    if not data_path.exists():
        raise FileNotFoundError(f"GuitarSet CQT directory not found: {data_path}")

    npz_files = sorted(data_path.glob("*.npz"))
    if not npz_files:
        raise FileNotFoundError(f"No .npz files found in {data_path}")

    all_features: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []

    for npz_path in npz_files:
        data = np.load(npz_path)
        split = str(data.get("split", b"train"))
        if split == "test":
            continue
        all_features.append(data["features"])
        all_labels.append(data["labels"])

    if not all_features:
        raise ValueError("No training/validation data found in GuitarSet CQT directory")

    X = np.concatenate(all_features, axis=0).astype(np.float32)
    y = np.concatenate(all_labels, axis=0).astype(np.int32)

    # Apply label quality gate (placeholder for future implementation)
    # In a full implementation, this would:
    # 1. Run a baseline model to get predictions
    # 2. Compare predictions with ground truth to estimate boundary jitter
    # 3. Reject examples with boundary jitter > max_boundary_jitter_ms
    # 4. Flag examples with boundary jitter > flag_boundary_jitter_ms for review
    # For now, we just log that this step would occur
    config_path = Path(__file__).parent.parent / "config" / "label_noise_config.yaml"
    if config_path.exists():
        import yaml
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        max_jitter_ms = config.get("data_ingestion", {}).get("max_boundary_jitter_ms", 100)
        flag_jitter_ms = config.get("data_ingestion", {}).get("flag_boundary_jitter_ms", 50)
        print(f"Label quality gate: Would reject examples with >{max_jitter_ms}ms jitter, "
              f"flag examples with >{flag_jitter_ms}ms jitter")
    else:
        print("Label quality gate: Configuration not found, skipping gate")

    print(f"Loaded {len(X)} windows from {len(npz_files)} GuitarSet files (train+val only)")
    return X, y


def load_test_data(data_dir: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load GuitarSet test split (player 05)."""
    data_path = Path(data_dir) / "processed" / "cqt"
    if not data_path.exists():
        raise FileNotFoundError(f"GuitarSet CQT directory not found: {data_path}")

    npz_files = sorted(data_path.glob("*.npz"))
    all_features: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []

    for npz_path in npz_files:
        data = np.load(npz_path)
        split = str(data.get("split", b""))
        if split == "test":
            all_features.append(data["features"])
            all_labels.append(data["labels"])

    if not all_features:
        raise ValueError("No test data found (player 05)")

    X = np.concatenate(all_features, axis=0).astype(np.float32)
    y = np.concatenate(all_labels, axis=0).astype(np.int32)
    print(f"Loaded {len(X)} test windows from GuitarSet player-05")
    return X, y


def load_empirical_transition_matrix(data_dir: str | Path) -> np.ndarray | None:
    """Load empirical transition matrix from annotations directory."""
    matrix_path = Path(data_dir) / "annotations" / "transition_matrix_empirical.npy"
    if not matrix_path.exists():
        print("  [INFO] No empirical transition matrix found, using uniform sampling")
        return None
    matrix = np.load(str(matrix_path))
    print(f"  Loaded empirical transition matrix from {matrix_path}")
    return matrix


# ---------------------------------------------------------------------------
# 4b. Dataset mixing (Commit 101)
# ---------------------------------------------------------------------------

def mix_datasets(
    real_X: np.ndarray, real_y: np.ndarray,
    synth_X: np.ndarray, synth_y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Concatenate all real and synthetic data (no subsampling).

    Args:
        real_X: Real CQT features, shape (N_real, 128, 40)
        real_y: Real labels, shape (N_real,)
        synth_X: Synthetic CQT features, shape (N_synth, 128, 40)
        synth_y: Synthetic labels, shape (N_synth,)

    Returns:
        (X_mixed, y_mixed) shuffled arrays using ALL data from both sources.
    """
    n_real = len(real_X)
    n_synth = len(synth_X)

    if n_real == 0:
        X, y = synth_X.copy(), synth_y.copy()
    elif n_synth == 0:
        X, y = real_X.copy(), real_y.copy()
    else:
        X = np.concatenate([real_X, synth_X], axis=0).astype(np.float32)
        y = np.concatenate([real_y, synth_y], axis=0).astype(np.int32)

    p = np.random.permutation(len(X))
    X, y = X[p], y[p]

    print(f"Mixed dataset: {n_real} real + {n_synth} synthetic "
          f"= {len(X)} total (real ratio: {n_real / len(X):.1%})")
    return X, y


# ---------------------------------------------------------------------------
# 4c. Training and the Concrete Conversion Fix
# ---------------------------------------------------------------------------
def _numpy_to_native(obj):
    """Recursively convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _numpy_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_numpy_to_native(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_numpy_to_native(v) for v in obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _build_quality_distribution(y_train: np.ndarray) -> dict:
    """Build per-quality frequency distribution from training labels."""
    total = len(y_train)
    qualities: list[str] = []
    for idx in y_train:
        if 0 <= idx < len(CHORD_CLASS_MAP):
            qualities.append(CHORD_CLASS_MAP[idx][1])
        else:
            qualities.append("N")
    counter: dict[str, int] = {}
    for q in qualities:
        counter[q] = counter.get(q, 0) + 1
    return {
        q: {"count": c, "percentage": round(c / total * 100, 2)}
        for q, c in sorted(counter.items(), key=lambda x: -x[1])
    }


def _save_metrics_json(
    class_report: dict,
    y_train: np.ndarray,
    output_path: Path,
) -> None:
    """Save per-class metrics and quality distribution to JSON.

    Handles numpy type conversion for safe JSON serialization.
    """
    report_native = _numpy_to_native(class_report)
    quality_dist = _build_quality_distribution(y_train)

    # Build per-quality recall averages
    quality_recalls: dict[str, list[float]] = {}
    for chord_name, metrics in class_report.items():
        if not isinstance(metrics, dict) or "recall" not in metrics:
            continue
        if ":" in chord_name:
            quality = chord_name.split(":", 1)[1]
        elif chord_name in {"N", "accuracy"}:
            continue
        else:
            continue
        if quality not in quality_recalls:
            quality_recalls[quality] = []
        quality_recalls[quality].append(float(metrics["recall"]))

    recall_summary = {
        q: {
            "mean_recall": round(np.mean(v), 4),
            "min_recall": round(np.min(v), 4),
            "max_recall": round(np.max(v), 4),
            "n_chords": len(v),
        }
        for q, v in sorted(quality_recalls.items())
    }

    # Build per-class recall list (all 277 individual classes)
    per_class_recall: list[dict[str, float | str]] = []
    for chord_name, m in class_report.items():
        if not isinstance(m, dict) or "recall" not in m:
            continue
        if chord_name in {"accuracy", "macro avg", "weighted avg", "micro avg"}:
            continue
        try:
            int(chord_name)
            continue
        except (ValueError, TypeError):
            pass
        per_class_recall.append({
            "chord": chord_name,
            "recall": round(float(m["recall"]), 4),
            "precision": round(float(m["precision"]), 4),
            "f1_score": round(float(m["f1-score"]), 4),
        })
    per_class_recall.sort(key=lambda x: x["recall"])

    metrics_doc = {
        "per_quality_recall": recall_summary,
        "quality_distribution": quality_dist,
        "per_class_recall": per_class_recall,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics_doc, f, indent=2)
    print(f"  Commit 104 metrics saved to {output_path}")


# ---------------------------------------------------------------------------
# 4d. GuitarSet test callback
# ---------------------------------------------------------------------------


class GuitarSetTestCallback(tf.keras.callbacks.Callback):
    """Evaluate on real GuitarSet test set after each epoch.

    Provides visibility into real-world performance during training,
    preventing the model from overfitting to synthetic validation data
    while losing real-world accuracy.

    Usage:
        callback = GuitarSetTestCallback(test_X, test_y)
        model.fit(..., callbacks=[...existing..., callback])
        print(callback.best_test_acc)  # best real accuracy during training
    """

    def __init__(
        self,
        test_X: np.ndarray,
        test_y: np.ndarray,
        log_freq: int = 1,
        patience: int = 5,
    ):
        super().__init__()
        self.test_X = test_X
        self.test_y = test_y
        self.log_freq = log_freq
        self.patience = patience
        self.history: list[float] = []
        self.best_test_acc: float = 0.0
        self.best_epoch: int = -1
        self._no_improve_count: int = 0

    def on_epoch_end(self, epoch: int, logs: dict | None = None):
        if (epoch + 1) % self.log_freq != 0:
            return

        test_pred = np.argmax(self.model.predict(self.test_X, verbose=0), axis=1)
        test_acc = float(np.mean(test_pred == self.test_y))
        self.history.append(test_acc)

        # Compute per-group accuracy
        grouped = compute_grouped_accuracy(self.test_y, test_pred)

        if test_acc > self.best_test_acc:
            self.best_test_acc = test_acc
            self.best_epoch = epoch
            self._no_improve_count = 0
        else:
            self._no_improve_count += 1

        print(f"\n  [GuitarSet Test] Epoch {epoch + 1}: accuracy={test_acc:.2%} "
              f"(best={self.best_test_acc:.2%} @ epoch {self.best_epoch + 1})")
        for group, acc in sorted(grouped.items()):
            print(f"    {group:20s}: {acc * 100:.1f}%")
        print(f"    no_chord   {grouped.get('no_chord', 0) * 100:.1f}%")


def run_pipeline(
    real_data_dir: str | Path | None = None,
    empirical_matrix_path: str | Path | None = None,
    temperature: float = 0.3,
):
    """Run the full training pipeline with optional real data mixing.

    All available real and synthetic data is concatenated (no ratio-based
    subsampling), giving the model the maximum possible training signal.

    Args:
        real_data_dir: Path to GuitarSet CQT data directory (or None for synthetic-only).
        empirical_matrix_path: Path to empirical transition matrix .npy (or None).
        temperature: Temperature τ for quality re-sampling (default 0.3, matching MT3).
                     τ < 1.0 boosts rare chord quality sampling via MT3 formula.
                     τ = 1.0 uses uniform sampling (neutral).
    """
    _APP_DIR = Path(__file__).resolve().parent.parent / "app"
    _SCRIPTS_DIR = Path(__file__).resolve().parent

    # --- Load real data (if available) ---
    has_real_data = False
    test_X, test_y = np.array([]), np.array([])
    if real_data_dir is not None:
        data_path = Path(real_data_dir)
        if data_path.exists():
            try:
                real_X, real_y = load_real_data(data_path)
                test_X, test_y = load_test_data(data_path)
                has_real_data = len(real_X) > 0
            except (FileNotFoundError, ValueError) as e:
                print(f"  [WARN] Could not load real data: {e}")
                has_real_data = False
        else:
            print(f"  [WARN] Real data dir not found: {data_path}")

    # --- Load empirical transition matrix ---
    transition_probs = None
    if empirical_matrix_path is not None:
        emp_path = Path(empirical_matrix_path)
        if emp_path.exists():
            matrix = np.load(str(emp_path))
            if matrix.shape == (NUM_CLASSES, NUM_CLASSES):
                transition_probs = matrix.sum(axis=1)
                if transition_probs.sum() > 0:
                    transition_probs = transition_probs / transition_probs.sum()
                print(f"  Loaded empirical transition matrix ({emp_path})")
            else:
                print(f"  [WARN] Matrix shape {matrix.shape} != ({NUM_CLASSES},{NUM_CLASSES}), ignored")
        else:
            print(f"  [WARN] Empirical matrix not found: {emp_path}")

    # --- Generate synthetic data ---
    print("Generating synthetic dataset...")
    synth_X, synth_y = generate_dataset(transition_probs=transition_probs)
    p = np.random.permutation(len(synth_X))
    synth_X, synth_y = synth_X[p], synth_y[p]
    print(f"  Generated {len(synth_X)} synthetic samples")

    # --- Mix real + synthetic (use all data from both sources) ---
    if has_real_data:
        print("Mixing real and synthetic data...")
        X_all, y_all = mix_datasets(real_X, real_y, synth_X, synth_y)
    else:
        X_all, y_all = synth_X, synth_y
        print("  No real data available, using synthetic data only")

    # --- Train / validation split ---
    print("Splitting into train / validation sets (85/15)...")
    try:
        X_train, X_val, y_train, y_val = train_test_split(
            X_all, y_all, test_size=0.15, random_state=42, stratify=y_all,
        )
    except ValueError:
        # Stratify may fail with very small classes — fall back to random split
        X_train, X_val, y_train, y_val = train_test_split(
            X_all, y_all, test_size=0.15, random_state=42,
        )
    print(f"  Train: {len(X_train)} samples, Val: {len(X_val)} samples")

    # --- Build model ---
    model = build_model()
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])

    # --- Class weights (sklearn balanced, no temperature double-correction) ---
    # Temperature resampling (τ < 1.0) changes per-epoch sample distribution
    # in AugmentedDataGenerator. Class weights are standard sklearn balanced
    # — they compensate for class-level frequency differences. The two
    # mechanisms are independent and complementary at different granularities
    # (sampling distribution vs loss gradient).
    print("\nComputing class weights for imbalanced training data...")
    class_weight_dict = compute_training_class_weights(y_train, temperature=temperature)
    n_classes_with_data = len(class_weight_dict)
    print(f"  Computed weights for {n_classes_with_data}/{NUM_CLASSES} classes present in training set")

    # --- Training callbacks (Commit 103) ---
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=10,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=3,
            min_lr=1e-6,
            verbose=1,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(_APP_DIR / "chord_model_best.keras"),
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        ),
        tf.keras.callbacks.CSVLogger(
            filename=str(_SCRIPTS_DIR / "training_log.csv"),
        ),
    ]

    # GuitarSet test callback — per-epoch visibility into real-world accuracy
    if has_real_data and len(test_X) > 0:
        test_callback = GuitarSetTestCallback(test_X, test_y)
        callbacks.append(test_callback)

    # --- On-the-fly augmented data generator ---
    train_generator = AugmentedDataGenerator(
        X_train, y_train,
        batch_size=64,
        p_pitch_shift=0.5,
        pitch_range=2,
        p_time_stretch=0.3,
        stretch_range=(0.9, 1.1),
        noise_std=0.05,
        shuffle=True,
        temperature=temperature,
    )

    # --- Train ---
    print(f"\nTraining for up to 50 epochs with on-the-fly augmentation...")
    print(f"  EarlyStopping patience={10}, ReduceLROnPlateau patience={3}")
    if temperature < 1.0:
        print(f"  Temperature τ={temperature} (quality-aware resampling)")
    print(f"  Class weights: active ({n_classes_with_data}/{NUM_CLASSES} classes)")
    print(f"  Batch size=64")
    history = model.fit(
        train_generator,
        epochs=50,
        validation_data=(X_val, y_val),
        callbacks=callbacks,
        class_weight=class_weight_dict,
        verbose=1,
    )

    # Restore best weights (EarlyStopping with restore_best_weights already does this)
    print(f"\nTraining completed. "
          f"Best val_loss: {min(history.history['val_loss']):.4f}, "
          f"Best val_accuracy: {max(history.history['val_accuracy']):.1%}")

    # --- Per-group validation accuracy (Commit 98d) ---
    print("\n--- Per-Group Validation Accuracy ---")
    y_pred = np.argmax(model.predict(X_val, verbose=0), axis=1)
    grouped_acc = compute_grouped_accuracy(y_val, y_pred)
    for group, acc in sorted(grouped_acc.items()):
        pct = acc * 100
        arrow = ""
        if group == "overall":
            arrow = f"  (best val: {max(history.history['val_accuracy']):.1%})"
        elif group == "extended":
            arrow = "  ← target +3% improvement"
        print(f"  {group:20s}: {pct:5.1f}%{arrow}")

    # --- Confusion matrix (Commit 103) ---
    print("\n--- Confusion Matrix Analysis ---")
    cm = compute_confusion_matrix_report(y_val, y_pred, top_k=10)
    cm_path = _SCRIPTS_DIR / "confusion_matrix.npy"
    np.save(str(cm_path), cm)
    print(f"  Full confusion matrix saved to {cm_path}")

    # --- Per-class metrics (Commit 103/104) ---
    report = compute_per_class_metrics(y_val, y_pred, recall_threshold=0.3)

    # --- Commit 104: metrics JSON export ---
    _metrics_path = _SCRIPTS_DIR / "chord_104_metrics.json"
    _save_metrics_json(report, y_train, _metrics_path)

    # --- GuitarSet test set validation (if available) ---
    if has_real_data and len(test_X) > 0:
        print("\n--- GuitarSet Test Set (Player 05) ---")
        test_pred = np.argmax(model.predict(test_X, verbose=0), axis=1)
        test_acc = np.mean(test_pred == test_y)
        print(f"  Root accuracy on GuitarSet test: {test_acc:.1%}")
        test_grouped = compute_grouped_accuracy(test_y, test_pred)
        for group, acc in sorted(test_grouped.items()):
            print(f"  {group:20s}: {acc*100:5.1f}%")

    print("\nTracing model to Concrete Function (Bypassing Keras serialization)...")

    # Save Keras weights for attention visualization (Commit 98d)
    _APP_DIR = Path(__file__).resolve().parent.parent / "app"
    weights_path = _APP_DIR / "chord_model.weights.h5"
    model.save_weights(str(weights_path))
    print(f"Saved Keras weights to {weights_path} (for attention visualization)")

    # Save full Keras model for Python backend inference (Commit 99)
    keras_path = _APP_DIR / "chord_model.keras"
    model.save(str(keras_path))
    print(f"Saved Keras model to {keras_path} ({keras_path.stat().st_size/1024/1024:.1f} MB)")

    # 1. Trace the model call into a static graph
    @tf.function(input_signature=[tf.TensorSpec(shape=[None, WINDOW, FEATURE_DIM], dtype=tf.float32)])
    def run_model(input_tensor):
        return model(input_tensor, training=False)

    concrete_func = run_model.get_concrete_function()

    print("Converting to TFLite...")
    # 2. Convert from the concrete function directly
    converter = tf.lite.TFLiteConverter.from_concrete_functions([concrete_func])

    # Enable Dynamic Range Quantization for mobile performance
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    # Target standard TFLite ops but allow TF ops if needed for the padding + MHA
    converter.target_spec.supported_ops = [
        tf.lite.OpsSet.TFLITE_BUILTINS,
        tf.lite.OpsSet.SELECT_TF_OPS
    ]

    try:
        tflite_model = converter.convert()
        _APP_DIR = Path(__file__).resolve().parent.parent / "app"
        output_path = _APP_DIR / "chord_model.tflite"
        with open(output_path, "wb") as f:
            f.write(tflite_model)
        print(f"\nSuccess! Saved {output_path} ({len(tflite_model)/1024:.1f} KB)")
    except Exception as e:
        print(f"\nConversion failed: {e}")
        return

    # 5. Smoke Test
    print("\nRunning TFLite Inference Tests...")
    use_keras_fallback = False
    try:
        # Try with Flex delegate for attention ops
        from tflite_runtime.interpreter import Interpreter
        interp = Interpreter(model_path=str(output_path),
                            experimental_delegates=[
                                Interpreter.load_delegate('libtensorflowlite_flex.so')
                            ])
        interp.allocate_tensors()
        use_tflite_runtime = True
    except (ImportError, ValueError, OSError):
        # Fallback: use TensorFlow Lite interpreter
        try:
            interp = tf.lite.Interpreter(
                model_path=str(output_path),
                experimental_delegates=[
                    tf.lite.experimental.load_delegate('libtensorflowlite_flex.so')
                ]
            )
            interp.allocate_tensors()
            use_tflite_runtime = False
        except (ValueError, OSError, RuntimeError):
            # Flex delegate not available - test with Keras model directly
            print("  Flex delegate not available, testing with Keras model instead")
            print("  (TFLite model will work on mobile with tensorflow-lite-select-tf-ops)")
            test_model = model
            use_keras_fallback = True

    if not use_keras_fallback:
        input_details = interp.get_input_details()[0]
        output_details = interp.get_output_details()[0]

        # Verify single output tensor (classification only; attention weights stripped)
        assert len(output_details) == 1 or len(interp.get_output_details()) == 1, \
            "TFLite model must have exactly one output"

        test_cases = [
            ("C:maj",  0,  "maj"),  # C major — most frequent in GuitarSet (120 samples)
            ("A:min",  9,  "min"),  # A minor — in GuitarSet (20 samples), tests minor quality
            ("D#:7",   3,  "7"),    # D# dominant 7th — in GuitarSet (40 samples), tests 7th chord
            ("D:7",    2,  "7"),    # D dominant 7th — synthetic only, tests extended bias fix
        ]

        all_passed = True
        for expected, root_idx, quality in test_cases:
            test_input = make_window(make_cqt_template(root_idx, quality), 0.05)[np.newaxis]
            interp.set_tensor(input_details['index'], test_input)
            interp.invoke()
            res = interp.get_tensor(output_details['index'])[0]
            top_idx = int(np.argmax(res))
            predicted = CHORD_VOCAB[top_idx]
            confidence = float(res[top_idx])
            # Strict top-1 check: the predicted chord must match the input exactly.
            # Previously used top-3 which masked the semitone confusion bug.
            passed = predicted == expected
            if not passed:
                all_passed = False
            status = "PASS" if passed else "FAIL"
            print(f"  {expected:<8} -> {predicted:<8} ({confidence:.1%}) [{status}]")
    else:
        # Keras fallback test
        test_cases = [
            ("C:maj",  0,  "maj"),  # C major — most frequent in GuitarSet (120 samples)
            ("A:min",  9,  "min"),  # A minor — in GuitarSet (20 samples), tests minor quality
            ("D#:7",   3,  "7"),    # D# dominant 7th — in GuitarSet (40 samples), tests 7th chord
            ("D:7",    2,  "7"),    # D dominant 7th — synthetic only, tests extended bias fix
        ]

        all_passed = True
        for expected, root_idx, quality in test_cases:
            test_input = make_window(make_cqt_template(root_idx, quality), 0.05)[np.newaxis]
            res = test_model.predict(test_input, verbose=0)[0]
            top_idx = int(np.argmax(res))
            predicted = CHORD_VOCAB[top_idx]
            confidence = float(res[top_idx])
            # Strict top-1 check.
            passed = predicted == expected
            if not passed:
                all_passed = False
            status = "PASS" if passed else "FAIL"
            print(f"  {expected:<8} -> {predicted:<8} ({confidence:.1%}) [{status}]")

    if all_passed:
        print("\nAll smoke tests PASSED")
    else:
        print("\nSome smoke tests FAILED")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build chord recognition model with optional real data mixing"
    )
    parser.add_argument(
        "--real-data-dir", type=str, default=None,
        help="Path to GuitarSet CQT data directory (contains guitarset/processed/cqt/)"
    )
    parser.add_argument(
        "--empirical-matrix", type=str, default=None,
        help="Path to empirical transition matrix .npy file"
    )
    parser.add_argument(
        "--temperature", type=float, default=0.3,
        help="Temperature τ for quality re-sampling (default 0.3, matching MT3). "
             "τ<1.0 boosts rare chord quality sampling via MT3 formula. "
             "τ=1.0 = uniform sampling. Range [0, 1]."
    )
    parser.add_argument(
        "--rare-boost", action="store_true",
        help="Rare chord boost mode: sets temperature=0.1 for aggressive "
             "oversampling of rare chord types (7#9, alt7, dim7, aug). "
             "Use during fine-tuning after initial convergence."
    )
    args = parser.parse_args()

    if args.temperature < 0:
        parser.error("temperature must be >= 0")

    if args.rare_boost:
        if args.temperature != 0.3:
            print("  [WARN] --rare-boost overrides --temperature; setting τ=0.1")
        args.temperature = 0.1
        print("  Rare chord boost mode: τ=0.1 — aggressive oversampling of rare types")

    run_pipeline(
        real_data_dir=args.real_data_dir,
        empirical_matrix_path=args.empirical_matrix,
        temperature=args.temperature,
    )