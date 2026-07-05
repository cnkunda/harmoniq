"""
build_chord_tflite.py
=====================
Final Version: Uses Concrete Function tracing to bypass Keras 3 / Python 3.12 
serialization bugs.

Vocabulary: 25-class MIREX (12 maj + 12 min + N) — mapped from 277-class at dataset load (Commit 98)
Architecture: CRNN with Bidirectional LSTM + Multi-Head Self-Attention (Commit 98d)
Augmentation: Inversions, missing notes, pitch shift, time stretch, bass ambiguity, pink noise, transitions (Commit 98a)
Features: 144-bin CQT with octave preservation (Commit 98b)

Roles (Commit A2.2):
  1. CRNN training pipeline for the on-device TFLite model (Live Mic Mode)
  2. Preserved for long-term MT3 distillation — trains student models that
     learn from MT3 pseudo-labels, producing smaller/faster on-device models
"""

import json
import os
from pathlib import Path
from typing import Any, Callable

import sys

# Increase recursion limit to avoid TF 2.20 lazy_loader infinite recursion
# when tensorflow_model_optimization is installed alongside TF 2.20 / Keras 3.
sys.setrecursionlimit(10000)

# Force TensorFlow backend and CPU mode
os.environ["TF_USE_LEGACY_KERAS"] = "0"
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import traceback

import numpy as np
import tensorflow as tf

# Limit TF memory growth to avoid OOM
gpus = tf.config.experimental.list_physical_devices('GPU')
for gpu in gpus:
    tf.config.experimental.set_memory_growth(gpu, True)

# Commit 106: Quantization-Aware Training toolkit
try:
    import tensorflow_model_optimization as tfmot
    _HAS_TFMOT = True
except ImportError:
    tfmot = None  # type: ignore[assignment]
    _HAS_TFMOT = False

from app.chord_vocab import (
    ROOT_NOTES,
    CHORD_INTERVALS,
    CHORD_QUALITIES,
    CHORD_VOCAB,
    CHORD_TO_IDX,
    NUM_CLASSES,
    MIREX_VOCAB,
    MIREX_TO_IDX,
    NUM_CLASSES_MIREX,
    mirex_label,
    MIREX_QUALITY_MAP,
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

# MIREX 25-class class map for per-group accuracy computation
MIREX_CLASS_MAP: list[tuple[int, str]] = (
    [(root, "maj") for root in range(12)]
    + [(root, "min") for root in range(12)]
    + [(-1, "N")]
)


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


from app.cqt_constants import (WINDOW, BINS_PER_OCTAVE, NUM_OCTAVES,
                                CHROMA_BINS, FEATURE_DIM)

WINDOW_MIN      = 64               # Configurable range
WINDOW_MAX      = 256

# Commit 106: Quantization-Aware Training constants
QAT_EPOCHS = 5
QAT_LEARNING_RATE = 1e-4

# Commit 148 Phase 3b: Multi-task head constants
N_ROOTS = 13           # 12 chromatic roots + N (index 12)
CHORD_LOSS_WEIGHT = 1.0
ROOT_LOSS_WEIGHT = 0.2
PRESENCE_LOSS_WEIGHT = 0.1
N_INDEX = NUM_CLASSES_MIREX - 1  # 24 — index of the N (no-chord) class in 25-class vocab

# Commit 148 Phase 2a: Cosine annealing LR schedule
INITIAL_LR = 1e-3          # Cosine start LR (reduced from 3e-3 for multi-task stability)
MIN_LR = 1e-5               # Prevents total stall (was 1e-6 under ReduceLROnPlateau)
FIRST_DECAY_EPOCHS = 20     # Cosine half-period matches Stage 1 duration

# Quality groups for per-category accuracy tracking (Commit A: vocab reduction)
QUALITY_GROUPS = {
    "triad":           {"maj", "min"},
    "no_chord":        {"N"},
}


def compute_grouped_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute per-quality-group accuracy.

    Groups: triad, no_chord, overall.

    Args:
        y_true: Ground truth class indices (25-class MIREX), shape (N,)
        y_pred: Predicted class indices (25-class MIREX), shape (N,)

    Returns:
        Dict mapping group name to accuracy (float in [0, 1]).
    """
    results: dict[str, float] = {}
    for group_name, qualities in QUALITY_GROUPS.items():
        mask = np.array([MIREX_CLASS_MAP[idx][1] in qualities for idx in y_true])
        if mask.sum() == 0:
            results[group_name] = 0.0
            continue
        group_correct = int((y_true[mask] == y_pred[mask]).sum())
        results[group_name] = round(group_correct / int(mask.sum()), 4)
    total_correct = int((y_true == y_pred).sum())
    results["overall"] = round(total_correct / len(y_true), 4)
    return results


# ---------------------------------------------------------------------------
# Phase 6a. Bootstrap confidence intervals
# ---------------------------------------------------------------------------

def bootstrap_ci_accuracies(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_bootstraps: int = 1000,
    ci_level: float = 0.95,
    seed: int = 42,
) -> dict[str, float]:
    """Compute bootstrapped accuracy with confidence intervals.

    Sample with replacement n_bootstraps times, compute accuracy each time,
    and report mean ± 1.96σ as the 95% CI.

    Args:
        y_true: Ground truth class indices, shape (N,).
        y_pred: Predicted class indices, shape (N,).
        n_bootstraps: Number of bootstrap resamples.
        ci_level: Confidence level (default 0.95 → 95% CI).
        seed: Random seed for reproducibility.

    Returns:
        Dict with keys: mean_acc, std_acc, ci_lower, ci_upper.
    """
    rng = np.random.RandomState(seed)
    n = len(y_true)
    boot_accs = np.empty(n_bootstraps, dtype=np.float64)
    for i in range(n_bootstraps):
        idx = rng.randint(0, n, size=n)
        boot_accs[i] = float(np.mean(y_pred[idx] == y_true[idx]))
    mean_acc = float(np.mean(boot_accs))
    std_acc = float(np.std(boot_accs))
    z = 1.96  # for 95% CI
    ci_lower = float(np.percentile(boot_accs, (1 - ci_level) / 2 * 100))
    ci_upper = float(np.percentile(boot_accs, (1 + ci_level) / 2 * 100))
    return {
        "mean_acc": mean_acc,
        "std_acc": std_acc,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
    }


# ---------------------------------------------------------------------------
# Phase 6c. CQT domain visualization (EMD + t-SNE)
# ---------------------------------------------------------------------------

def compute_cqt_emd(
    real_cqt: np.ndarray,
    synth_cqt: np.ndarray,
    n_bins: int = 144,
) -> float:
    """Compute Earth Mover's Distance between real and synthetic CQT distributions.

    Averages per-bin Wasserstein-1 distances across all 144 frequency bins.
    Lower values indicate more similar distributions.

    Args:
        real_cqt: Real CQT windows, shape (N_real, T, n_bins).
        synth_cqt: Synthetic CQT windows, shape (N_synth, T, n_bins).
        n_bins: Number of CQT frequency bins (default 144).

    Returns:
        Mean EMD across all bins (float).
    """
    from scipy.stats import wasserstein_distance

    # Flatten to (samples, features) for each domain
    real_flat = real_cqt.reshape(-1, n_bins)
    synth_flat = synth_cqt.reshape(-1, n_bins)

    emd_per_bin = []
    for b in range(n_bins):
        emd = wasserstein_distance(real_flat[:, b], synth_flat[:, b])
        emd_per_bin.append(emd)
    return float(np.mean(emd_per_bin))


def visualize_cqt_domain(
    real_cqt: np.ndarray,
    synth_cqt: np.ndarray,
    epoch: int,
    emd_value: float,
    output_dir: Path | str,
    max_samples: int = 1000,
    seed: int = 42,
) -> Path | None:
    """Generate t-SNE projection of real vs synthetic CQT windows.

    Saves a scatter plot to output_dir/cqt_domain_plot_epoch{N}.png.
    Real samples in blue, synthetic in red.

    Args:
        real_cqt: Real CQT windows, shape (N_real, T, n_bins).
        synth_cqt: Synthetic CQT windows, shape (N_synth, T, n_bins).
        epoch: Current epoch number (for filename + title).
        emd_value: Current EMD value (for title annotation).
        output_dir: Directory to save the plot.
        max_samples: Max samples per domain to plot (t-SNE is O(N²)).
        seed: Random seed for subsampling.

    Returns:
        Path to saved plot, or None if matplotlib is unavailable.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.manifold import TSNE
    except ImportError:
        print("  [WARN] matplotlib or sklearn not available — skipping CQT domain plot")
        return None

    rng = np.random.RandomState(seed)

    # Flatten to (samples, features)
    real_flat = real_cqt.reshape(real_cqt.shape[0], -1)
    synth_flat = synth_cqt.reshape(synth_cqt.shape[0], -1)

    # Subsample
    n_real = min(max_samples, len(real_flat))
    n_synth = min(max_samples, len(synth_flat))
    idx_real = rng.choice(len(real_flat), size=n_real, replace=False)
    idx_synth = rng.choice(len(synth_flat), size=n_synth, replace=False)
    X_real = real_flat[idx_real]
    X_synth = synth_flat[idx_synth]

    # Combine for t-SNE
    X_all = np.concatenate([X_real, X_synth], axis=0)
    labels = np.array([0] * n_real + [1] * n_synth)

    # t-SNE projection
    perplexity = min(30, len(X_all) - 1)
    tsne = TSNE(n_components=2, random_state=seed, perplexity=perplexity)
    X_2d = tsne.fit_transform(X_all)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 8))
    mask_real = labels == 0
    mask_synth = labels == 1
    ax.scatter(X_2d[mask_real, 0], X_2d[mask_real, 1],
               c="blue", alpha=0.5, s=10, label=f"Real (n={n_real})")
    ax.scatter(X_2d[mask_synth, 0], X_2d[mask_synth, 1],
               c="red", alpha=0.5, s=10, label=f"Synthetic (n={n_synth})")
    ax.set_title(f"CQT Domain Projection — Epoch {epoch}\nEMD: {emd_value:.4f}")
    ax.legend()
    ax.set_xticks([])
    ax.set_yticks([])

    output_path = Path(output_dir) / f"cqt_domain_plot_epoch{epoch}.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# 1b. No-Chord (N) Silence Templates (Phase 1a)
# ---------------------------------------------------------------------------
_N_SILENCE_VARIANTS = [
    "near_silence",   # Near-zero energy everywhere
    "muted_string",   # 1-2 random bins at low energy
    "bg_noise",       # Uniform low energy with random fluctuations
    "single_pluck",   # One bin at moderate energy, rest near zero
]


def collect_real_n_templates(data_dirs: list[Path]) -> list[np.ndarray]:
    """Extract real N (no-chord) windows from real CQT datasets.

    Scans .npz files in processed/cqt/ for frames whose label matches the
    N class. Checks for both the old 277-class N index (276) and the new
    25-class N index (24) to handle stale .npz files from previous extraction.

    Args:
        data_dirs: List of dataset paths containing processed/cqt/*.npz.

    Returns:
        List of (128, 144) arrays, each a real N-cqt feature window.
    """
    n_idx_new = NUM_CLASSES_MIREX - 1  # 24 (new N index)
    n_idx_old = NUM_CLASSES - 1        # 276 (old N index in stale .npz files)
    templates: list[np.ndarray] = []

    for data_dir in data_dirs:
        cqt_dir = data_dir / "processed" / "cqt"
        if not cqt_dir.exists():
            continue
        for npz_path in sorted(cqt_dir.glob("*.npz")):
            try:
                data = np.load(npz_path)
                features = data["features"]
                labels = data["labels"]
                n_mask = (labels == n_idx_new) | (labels == n_idx_old)
                n_windows = features[n_mask]
                templates.extend(n_windows)
            except Exception as e:
                print(f"  [WARN] skipping {npz_path.name}: {e}")

    return templates


def _make_n_silence_template() -> np.ndarray:
    """Generate a no-chord template that resembles real quiet guitar passages.

    Replaces the old flat uniform vector with diverse near-silence profiles
    so the model learns to distinguish silence from low-energy chords.

    Returns:
        144-bin feature vector.
    """
    variant = np.random.choice(_N_SILENCE_VARIANTS)
    cqt = np.zeros(CHROMA_BINS, dtype=np.float32)

    if variant == "near_silence":
        # Very low energy across all bins with pink noise
        cqt = np.random.uniform(0.001, 0.01, CHROMA_BINS).astype(np.float32)
        noise = generate_pink_noise((CHROMA_BINS,), 0.003)
        cqt = np.clip(cqt + noise, 0, 0.02)

    elif variant == "muted_string":
        # 1-2 random bins at low energy, rest near zero
        n_bins = np.random.randint(1, 3)
        active_bins = np.random.choice(CHROMA_BINS, size=n_bins, replace=False)
        cqt[active_bins] = np.random.uniform(0.05, 0.15, size=n_bins)
        noise = generate_pink_noise((CHROMA_BINS,), 0.005)
        cqt = np.clip(cqt + noise, 0, 0.2)

    elif variant == "bg_noise":
        # Uniform low energy with random per-bin fluctuations
        base = np.random.uniform(0.01, 0.03)
        cqt = np.full(CHROMA_BINS, base, dtype=np.float32)
        noise = generate_pink_noise((CHROMA_BINS,), 0.008)
        cqt = np.clip(cqt + noise, 0, 0.05)

    elif variant == "single_pluck":
        # One bin at moderate energy, rest near zero
        active_bin = np.random.randint(CHROMA_BINS)
        cqt[active_bin] = np.random.uniform(0.1, 0.3)
        noise = generate_pink_noise((CHROMA_BINS,), 0.005)
        cqt = np.clip(cqt + noise, 0, 0.35)

    # Normalize
    total = cqt.sum()
    if total > 0:
        cqt = cqt / total

    return cqt.astype(np.float32)


# ---------------------------------------------------------------------------
# 2. Data Generation (Harmonic Overtones with Extension Attenuation)
# ---------------------------------------------------------------------------
def make_cqt_template(root: int, quality: str) -> np.ndarray:
    """Generate 144-bin CQT template with overtone modeling.

    Chord tones placed at 24-bins-per-octave resolution covering
    octaves 2-4 (guitar range E2-E5 + harmonics).

    Args:
        root: Root note index (0-11)
        quality: Chord quality string

    Returns:
        144-bin feature vector (no separate bass channel).
    """
    cqt = np.zeros(CHROMA_BINS, dtype=np.float32)  # 144

    if quality == "N":
        return _make_n_silence_template()

    intervals = CHORD_INTERVALS[quality]

    for i, interval in enumerate(intervals):
        if interval >= 14:
            octave = 3
        else:
            octave = 2

        note_in_octave = (root + interval) % 12
        bin_idx = octave * BINS_PER_OCTAVE + note_in_octave  # 24*octave + note

        weight = 1.0 if interval <= 12 else 0.4
        if i == 0:
            weight *= 1.20

        # Fundamental
        cqt[bin_idx] += weight

        # 2nd harmonic (octave above)
        harmonic2_bin = bin_idx + BINS_PER_OCTAVE
        if harmonic2_bin < CHROMA_BINS:
            cqt[harmonic2_bin] += weight * 0.5

        # 3rd harmonic (octave + fifth)
        harmonic3_bin = bin_idx + BINS_PER_OCTAVE + 7
        if harmonic3_bin < CHROMA_BINS:
            cqt[harmonic3_bin] += weight * 0.3

        # Spectral leakage: spread energy to adjacent bins
        for offset in [-1, 1]:
            neighbor = bin_idx + offset
            if 0 <= neighbor < CHROMA_BINS:
                cqt[neighbor] += weight * 0.15

    # Root note reinforcement in octave 2
    root_bin = 2 * BINS_PER_OCTAVE + root
    cqt[root_bin] += 0.5

    # Min-max normalization (matches real extraction normalization)
    cmin, cmax = cqt.min(), cqt.max()
    if cmax > cmin:
        cqt = (cqt - cmin) / (cmax - cmin + 1e-8)

    return cqt.astype(np.float32)  # No bass concatenation


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
        template: 144-bin CQT template.
        root: Root note index (0-11)
        quality: Chord quality string
        inversion: 0=root position, 1=1st inversion, 2=2nd inversion
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

    return cqt.astype(np.float32)


def apply_missing_notes(template: np.ndarray, quality: str, dropout_rate: float = 0.15) -> np.ndarray:
    """Randomly drop chord tones to model sparse arrangements.
    
    Preserves at least 2 notes to maintain chord identity.
    Works with 144-bin CQT template.
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

    total = cqt.sum()
    if total > 0:
        result[:CHROMA_BINS] = cqt / total

    return result


def apply_pitch_shift(window: np.ndarray, shift_semitones: int = 0) -> np.ndarray:
    """Circular shift CQT bins along pitch axis.
    
    Note: This crosses octave boundaries, which is an approximation
    but effective for augmentation regularization.
    """
    if shift_semitones == 0:
        return window

    return np.roll(window, shift_semitones, axis=-1).astype(np.float32)


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
    """Add energy to low-frequency bins (0-23) of the 144-bin CQT.

    Replaces the old bass-channel ambiguity approach. With BASS_BINS=0,
    the 144-bin CQT covers E2-E5; low bins 0-23 correspond to the lowest
    octave. Injecting energy at non-chord notes in this range simulates
    the ambiguous bass of real recordings.

    Same signature as the old function for backward compatibility.
    """
    if ambiguity_strength <= 0 or quality == "N":
        return template

    result = template.copy()

    chord_notes = set()
    for interval in CHORD_INTERVALS[quality]:
        note = (root + interval) % 12
        chord_notes.add(note)

    possible_bass = [n for n in range(12) if n not in chord_notes]
    if not possible_bass:
        return template

    bass_note = np.random.choice(possible_bass)
    # Place ambiguous bass energy in low-frequency region (bins 0-23)
    bin_0 = bass_note * 2  # spread across 2 bins for realism
    bin_1 = (bass_note * 2 + 1) % 24
    result[bin_0] += ambiguity_strength
    result[bin_1] += ambiguity_strength * 0.5

    # Renormalize
    total = result.sum()
    if total > 0:
        result = result / total

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
    """Create a window mixing two 144-bin CQT templates."""
    window = np.zeros((WINDOW, FEATURE_DIM), dtype=np.float32)
    for i in range(WINDOW):
        t = i / (WINDOW - 1)
        frame_mix = (1 - t) * template_a + t * template_b
        noise = generate_pink_noise((FEATURE_DIM,), 0.12)
        window[i] = np.clip(frame_mix + noise, 0, 1)
    
    return window


def make_window(center_chroma: np.ndarray, noise_std: float = 0.12) -> np.ndarray:
    """Create window with 144-bin CQT features."""
    frames = [np.clip(center_chroma + np.random.randn(FEATURE_DIM).astype(np.float32) * noise_std, 0, 1) 
              for _ in range(WINDOW)]
    return np.stack(frames, axis=0)


def make_window_augmented(center_chroma: np.ndarray, noise_std: float = 0.12,
                          pitch_range: int = 2, stretch_rate: float = 0.3,
                          stretch_range: tuple = (0.9, 1.1)) -> tuple[np.ndarray, int]:
    """Create augmented window with pink noise and temporal variations.

    Returns (window, shift_semitones) so callers can adjust labels
    to match the applied pitch shift.

    Works with 144-bin CQT features.
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
        template: 144-bin CQT template.
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


def generate_dataset(samples_per_class: int = 120, config: dict = None,
                      transition_probs: np.ndarray | None = None,
                      cqt_stats: dict | None = None,
                      real_n_templates: list[np.ndarray] | None = None):
    """Generate augmented chord dataset with realistic variability.

    Includes chord transition windows sampled from the empirical chord
    distribution (via transition_probs) to teach the model temporal
    chord-to-chord boundary patterns.

    IMPORTANT: When make_window_augmented applies a pitch shift (±1-2 semitones),
    the label is adjusted to match (e.g., C:maj shifted +2 becomes D:maj).
    This fixes the critical bug where 80% of pre-generated samples had
    pitch-shifted features but original-chord labels.

    When cqt_stats is provided (from cqt_distribution_analyzer), synthetic
    windows are post-processed with distribution matching to bridge the
    synthetic-to-real domain gap (Commit 148 Phase 1b).

    When real_n_templates is provided, N (no-chord) frames use real extracted
    CQT features from GuitarSet gaps instead of purely synthetic silence
    (Commit 148 Phase 1c).

    Args:
        samples_per_class: Base samples per chord class (80 → 277×80 = 22,160 total).
                           Reduced from 260 to balance real/synthetic ratio.
        config: Augmentation configuration dict
        transition_probs: Optional (NUM_CLASSES,) marginal chord distribution from
            empirical transition matrix. Used to sample chord pairs for transition
            windows. If None, samples uniform.
        cqt_stats: Optional CQT statistics for distribution matching. If None,
            no distribution matching is applied.
        real_n_templates: Optional list of real (128, 144) N-CQT windows. If
            provided, replaces ~50% of synthetic N samples with real ones.
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
    _total_classes = len(CHORD_CLASS_MAP)
    _progress_interval = max(1, _total_classes // 20)

    for idx, (root_idx, quality) in enumerate(CHORD_CLASS_MAP):
        if idx % _progress_interval == 0:
            print(f"  [synth] Generating class {idx}/{_total_classes} ({quality}:{ROOT_NOTES[root_idx] if root_idx >= 0 else 'N'})...")
        # Commit 148 Phase 1c: use real N templates from GuitarSet gaps
        if quality == "N" and real_n_templates and np.random.random() < 0.5:
            template = real_n_templates[np.random.randint(len(real_n_templates))]
            template = template.copy()
            # Add mild augmentation to increase diversity of real N frames
            if np.random.random() < 0.4:
                noise = generate_pink_noise(template.shape, 0.005)
                template = np.clip(template + noise, 0, 1)
        else:
            template = make_cqt_template(root_idx, quality)

        for _ in range(samples_per_class):
            if template.ndim == 1 or template.shape[0] != WINDOW:
                inversion = np.random.choice([0, 1, 2], p=inversion_rates)
                augmented = apply_inversion(template, root_idx, quality, inversion)
                augmented = apply_missing_notes(augmented, quality, dropout_rate)
                augmented = apply_extension_dropout(augmented, quality, extension_drop_rate)

                if np.random.random() < bass_rate:
                    strength = np.random.uniform(0.1, 0.3)
                    augmented = apply_bass_ambiguity(augmented, root_idx, quality, strength)

                if np.random.random() < guitar_body_rate:
                    augmented = apply_guitar_body_resonance(augmented, strength=0.3)

                std = 0.08 + np.random.uniform(0, 0.12)
                window, shift = make_window_augmented(
                    augmented, std,
                    pitch_range=pitch_range,
                    stretch_rate=stretch_rate,
                    stretch_range=stretch_range
                )
            else:
                window = template.copy()
                shift = 0

            # Apply strumming onset after window creation (temporal)
            if np.random.random() < strumming_rate:
                window = apply_strumming_onset(window, quality)

            # Apply CQT leakage after window creation (spectral)
            if np.random.random() < cqt_leakage_rate:
                window = apply_cqt_leakage(window, leakage_strength=0.2)

            # Apply domain gap augmentations to bridge synthetic-real gap
            if quality != "N":
                if np.random.random() < 0.4:
                    window = apply_cqt_reverb(window, strength=0.3)
                if np.random.random() < 0.3:
                    window = apply_fine_detune(window, max_cents=30.0)
                if np.random.random() < 0.5:
                    window = apply_spectral_tilt(window)
                if np.random.random() < 0.5:
                    window = apply_random_gain(window)

            # N-specific augmentations for diverse silence profiles
            if quality == "N":
                if np.random.random() < 0.6:
                    window = apply_n_augmentation(window)

            # Commit 148 Phase 1b: distribution matching for domain gap
            window = _apply_distribution_matching(window, cqt_stats, strength=0.8)

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
    n_transitions = int(n_classes * max(5, samples_per_class // 3) * transition_rate)
    # Expand 25-class MIREX marginal distribution to 277-class for CPCC sampling
    if transition_probs is not None and transition_probs.sum() > 0:
        expanded = np.zeros(n_classes, dtype=np.float64)
        for i in range(276):
            quality = CHORD_QUALITIES[i // 12]
            root = i % 12
            target_q = MIREX_QUALITY_MAP.get(quality, "maj")
            m_idx = MIREX_TO_IDX.get(f"{ROOT_NOTES[root]}:{target_q}", 24)
            expanded[i] = transition_probs[m_idx]
        expanded[276] = transition_probs[-1]  # N
        expanded /= expanded.sum()
    else:
        expanded = None
    print(f"  [synth] Generating {n_transitions} transition windows...")
    _trans_interval = max(1, n_transitions // 10)
    for t_idx in range(n_transitions):
        if t_idx % _trans_interval == 0:
            print(f"  [synth] Transition {t_idx}/{n_transitions}...")
        if expanded is not None:
            idx_a = np.random.choice(n_classes, p=expanded)
            idx_b = np.random.choice(n_classes, p=expanded)
        else:
            idx_a, idx_b = np.random.choice(n_classes, 2, replace=False)
        root_a, qual_a = CHORD_CLASS_MAP[idx_a]
        root_b, qual_b = CHORD_CLASS_MAP[idx_b]
        template_a = make_cqt_template(root_a, qual_a)
        template_b = make_cqt_template(root_b, qual_b)
        mix_ratio = np.random.uniform(0.3, 0.7)
        window = make_transition_window(template_a, template_b, mix_ratio)
        window = _apply_distribution_matching(window, cqt_stats, strength=0.3)
        X.append(window)
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
        template: 144-bin CQT template.
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

    return cqt.astype(np.float32)


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

    return result


# ---------------------------------------------------------------------------
# 2b1. Domain Gap Augmentations (Phase 3 — heavier synthetic augmentation)
# ---------------------------------------------------------------------------


def apply_cqt_reverb(
    window: np.ndarray, strength: float = 0.3
) -> np.ndarray:
    """Simulate reverb effects in the CQT domain.

    Reverb causes temporal smearing (energy spreads forward in time) and
    spectral spread (energy spreads to adjacent frequency bins). This
    function approximates both effects on CQT features.

    Args:
        window: Feature window of shape (WINDOW, FEATURE_DIM).
        strength: Reverb intensity (0 = dry, 1 = fully wet).

    Returns:
        Window with simulated reverb.
    """
    if strength <= 0:
        return window

    result = window.copy()

    # Temporal smearing: exponential decay kernel convolved along time axis
    decay_len = max(1, int(strength * 8))  # 1-8 frames (~100-800ms)
    decay_kernel = np.exp(-np.linspace(0, 3, decay_len)).astype(np.float32)
    decay_kernel /= decay_kernel.sum()

    for bin_idx in range(FEATURE_DIM):
        channel = result[:, bin_idx].copy()
        smeared = np.convolve(channel, decay_kernel, mode="same")
        result[:, bin_idx] = (1.0 - strength) * channel + strength * smeared

    # Spectral spread: widen each bin's energy to neighbors
    spectral_kernel = np.array([0.15, 0.7, 0.15], dtype=np.float32)
    for t in range(len(result)):
        cqt_row = result[t, :CHROMA_BINS].copy()
        spread = np.convolve(cqt_row, spectral_kernel, mode="same")
        result[t, :CHROMA_BINS] = (
            (1.0 - strength * 0.5) * cqt_row + strength * 0.5 * spread
        )

    return result


def apply_fine_detune(
    window: np.ndarray, max_cents: float = 30.0
) -> np.ndarray:
    """Apply fractional semitone shift to simulate real guitar detuning.

    Real guitars are never perfectly in tune. This applies a fine pitch
    shift (0-30 cents) by interpolating between adjacent CQT bins.

    Args:
        window: Feature window of shape (WINDOW, FEATURE_DIM).
        max_cents: Maximum detuning in cents (100 cents = 1 semitone).

    Returns:
        Detuned window.
    """
    cents = np.random.uniform(-max_cents, max_cents)
    if abs(cents) < 1.0:
        return window

    # Convert cents to fractional bin shift
    bin_shift = cents / 100.0  # fractional bins

    result = window.copy()
    cqt = result[:, :CHROMA_BINS].copy()

    # Shift each frame's CQT by fractional bin amount
    for t in range(len(cqt)):
        shifted = np.roll(cqt[t], int(np.sign(bin_shift)))
        # Interpolate between original and shifted
        alpha = abs(bin_shift) % 1.0
        cqt[t] = (1.0 - alpha) * cqt[t] + alpha * shifted

    result[:, :CHROMA_BINS] = cqt
    return result


def apply_spectral_tilt(
    window: np.ndarray, tilt_range: tuple[float, float] = (-0.3, 0.3)
) -> np.ndarray:
    """Apply linear spectral tilt to simulate different mic positions.

    Mic placement dramatically changes the spectral balance. This applies
    a linear gain ramp across frequency bins (boost low + cut high, or
    vice versa).

    Args:
        window: Feature window of shape (WINDOW, FEATURE_DIM).
        tilt_range: (min_tilt, max_tilt) where positive = bright, negative = dark.

    Returns:
        Spectrally tilted window.
    """
    tilt = np.random.uniform(*tilt_range)
    if abs(tilt) < 0.05:
        return window

    # Linear ramp from low to high frequencies: tilt > 0 boosts highs
    ramp = np.linspace(1.0 - tilt, 1.0 + tilt, CHROMA_BINS).astype(np.float32)
    # Ensure no negative gains
    ramp = np.clip(ramp, 0.3, 2.0)
    # Normalize to preserve average energy
    ramp = ramp / ramp.mean()

    result = window.copy()
    result[:, :CHROMA_BINS] *= ramp[np.newaxis, :]
    return result


def apply_random_gain(
    window: np.ndarray, db_range: tuple[float, float] = (-4.0, 4.0)
) -> np.ndarray:
    """Apply random gain normalization to simulate different recording levels.

    Args:
        window: Feature window of shape (WINDOW, FEATURE_DIM).
        db_range: Gain range in dB.

    Returns:
        Gain-normalized window.
    """
    db = np.random.uniform(*db_range)
    gain = 10.0 ** (db / 20.0)
    result = window * gain
    # Clip to valid range
    result = np.clip(result, 0.0, 1.0)
    return result


def apply_n_augmentation(window: np.ndarray) -> np.ndarray:
    """Apply no-chord-specific augmentations to make N windows more diverse.

    Randomly applies sparse masking and noise injection to model real
    quiet guitar passages (muted strings, finger noise, room tone).

    Args:
        window: Feature window of shape (WINDOW, FEATURE_DIM).

    Returns:
        Augmented N window.
    """
    result = window.copy()
    variant = np.random.choice(["sparse_mask", "low_noise", "fade_out"])

    if variant == "sparse_mask":
        # Zero out 50-80% of random bins across all frames
        mask_frac = np.random.uniform(0.5, 0.8)
        n_mask = int(CHROMA_BINS * mask_frac)
        mask_bins = np.random.choice(CHROMA_BINS, size=n_mask, replace=False)
        result[:, mask_bins] = 0.0

    elif variant == "low_noise":
        # Add very low amplitude noise
        noise = generate_pink_noise(result.shape, 0.005)
        result = np.clip(result + noise, 0, 1)

    elif variant == "fade_out":
        # Gradual fade to silence over the window
        fade = np.linspace(1.0, 0.0, WINDOW).astype(np.float32)
        result *= fade[:, np.newaxis]

    return result


# Mixup is now applied inline in AugmentedDataGenerator.__getitem__
# (Commit 148 Phase 2b)


def _apply_distribution_matching(
    window: np.ndarray, cqt_stats: dict | None = None,
    strength: float = 0.8,
) -> np.ndarray:
    """Bridge synthetic-to-real domain gap via CQT distribution matching.

    Three complementary operations (applied in sequence):
      1. Per-bin energy scaling: scales each of the 144 bins toward real
         energy distribution using per_bin_mean / per_bin_std.
      2. Structured noise injection: noise sampled from real covariance
         structure (Cholesky), preserving inter-bin correlations.
      3. PCA-mode perturbation: projects window onto top-10 real PCA
         components and perturbs them with variance-scaled noise.

    Each operation has a probability < 1.0 so the model sees both
    matched and unmatched synthetic data.

    Args:
        window: (128, 144) synthetic CQT feature window.
        cqt_stats: Output from cqt_distribution_analyzer.compute_cqt_statistics().
            If None, this is a no-op.
        strength: Overall scaling of distribution matching (0 = none, 1 = full).

    Returns:
        Modified window with same shape.
    """
    if cqt_stats is None:
        return window

    rng = np.random.default_rng()

    # 1. Per-bin energy scaling (90% probability — nearly always match)
    if rng.random() < 0.9:
        real_mean = cqt_stats["per_bin_mean"]
        real_std = cqt_stats["per_bin_std"]
        window_mean = window.mean(axis=0)
        # Scale each bin toward real distribution
        scale = 1.0 + strength * ((real_mean / (window_mean + 1e-10)) - 1.0)
        scale = np.clip(scale, 0.5, 2.0)
        window = window * scale
        # Then add noise to match real variance
        noise_scale = strength * 0.3 * real_std
        window = window + rng.normal(0, noise_scale, size=window.shape)
        window = np.clip(window, 0.0, None)

    # 2. Structured noise from real covariance (80% probability)
    if rng.random() < 0.8:
        cov = cqt_stats["covariance"]
        try:
            L = np.linalg.cholesky(
                cov + 1e-6 * np.eye(FEATURE_DIM, dtype=np.float32)
            )
            structured_noise = rng.normal(0, strength * 0.15, size=(WINDOW, FEATURE_DIM))
            structured_noise = structured_noise @ L.T
            window = window + structured_noise
        except np.linalg.LinAlgError:
            pass

    # 3. PCA-mode perturbation (80% probability)
    if rng.random() < 0.8 and len(cqt_stats.get("pca_components", [])) >= 3:
        components = cqt_stats["pca_components"]  # (K, 5120)
        flat = window.reshape(1, -1)  # (1, 5120)
        proj = flat @ components.T  # (1, K)
        var = cqt_stats["pca_explained_variance"]
        # Perturb higher-variance modes more (they capture real structure)
        perturb = rng.normal(0, 1, size=proj.shape) * np.sqrt(var) * strength * 0.2
        reconstructed = flat + (perturb @ components)  # (1, 5120)
        window = reconstructed.reshape(WINDOW, FEATURE_DIM)

    # Final safety clip — CQT features are non-negative
    window = np.clip(window, 0.0, None)
    return window


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
    - ``transition_real_ratio``: target real-data fraction in batches
      for gradual curriculum transition. Starts at 0.0 (no override)
      and can be adjusted via callback to smoothly shift data mix.
    """

    def __init__(
        self,
        X: np.ndarray,
        y: np.ndarray,
        w: np.ndarray | None = None,
        batch_size: int = 64,
        p_pitch_shift: float = 0.5,
        pitch_range: int = 2,
        p_time_stretch: float = 0.3,
        stretch_range: tuple[float, float] = (0.9, 1.1),
        noise_std: float = 0.05,
        shuffle: bool = True,
        temperature: float = 0.5,
        p_mixup: float = 0.15,
        mixup_alpha: float = 0.2,
        p_specaug_freq: float = 0.3,
        specaug_freq_mask: int = 8,
        p_specaug_time: float = 0.3,
        specaug_time_mask: int = 16,
        real_mask: np.ndarray | None = None,
        transition_real_ratio: float | None = None,
        **kwargs,
    ):
        super().__init__()
        self.X = X
        self.y = y
        self.w = w
        self.batch_size = batch_size
        self.p_pitch_shift = p_pitch_shift
        self.pitch_range = pitch_range
        self.p_time_stretch = p_time_stretch
        self.stretch_range = stretch_range
        self.noise_std = noise_std
        self.shuffle = shuffle
        self.temperature = float(temperature)
        self.p_mixup = p_mixup
        self.mixup_alpha = mixup_alpha
        self.p_specaug_freq = p_specaug_freq
        self.specaug_freq_mask = specaug_freq_mask
        self.p_specaug_time = p_specaug_time
        self.specaug_time_mask = specaug_time_mask
        self.real_mask = real_mask  # bool mask: True for real samples
        self.transition_real_ratio = transition_real_ratio
        self.multi_task = kwargs.get("multi_task", False)
        self.indices = np.arange(len(X))
        if shuffle:
            if self.transition_real_ratio is not None and self.real_mask is not None:
                self._resample_indices_transition()
            elif self.temperature < 1.0:
                self._resample_indices_temperature()
            else:
                np.random.shuffle(self.indices)

    def __len__(self) -> int:
        return int(np.ceil(len(self.X) / self.batch_size))

    def __getitem__(self, idx: int):
        if idx < 0:
            idx += len(self)
        batch_indices = self.indices[
            idx * self.batch_size : (idx + 1) * self.batch_size
        ]
        batch_X = self.X[batch_indices].copy()
        batch_y = self.y[batch_indices].copy()

        batch_X, batch_y = self._apply_on_the_fly_augmentations(batch_X, batch_y, batch_indices)

        # Save integer labels before one-hot conversion (needed for multi-task heads)
        chord_labels_int = batch_y.copy()

        # Convert chord labels to one-hot
        chord_onehot = tf.keras.utils.to_categorical(chord_labels_int, NUM_CLASSES_MIREX).astype(np.float32)

        if self.multi_task:
            # Derive root + presence labels from augmented integer labels
            root_labels = derive_root_labels(chord_labels_int.astype(np.int32))
            presence_labels = derive_presence_labels(chord_labels_int.astype(np.int32))
            root_onehot = tf.keras.utils.to_categorical(root_labels, N_ROOTS).astype(np.float32)

            # Apply mixup to all label sets with the same lambda + permutation
            if np.random.random() < self.p_mixup:
                lam = np.random.beta(self.mixup_alpha, self.mixup_alpha)
                perm = np.random.permutation(len(batch_X))
                batch_X = lam * batch_X + (1.0 - lam) * batch_X[perm]
                chord_onehot = lam * chord_onehot + (1.0 - lam) * chord_onehot[perm]
                root_onehot = lam * root_onehot + (1.0 - lam) * root_onehot[perm]
                presence_labels = lam * presence_labels + (1.0 - lam) * presence_labels[perm]

            target_dict = {
                "chord_probs": chord_onehot,
                "root_probs": root_onehot,
                "presence": presence_labels.reshape(-1, 1),
            }
            if self.w is not None:
                w_batch = self.w[batch_indices].copy()
                weight_dict = {
                    "chord_probs": w_batch,
                    "root_probs": w_batch,
                    "presence": w_batch,
                }
                return batch_X, target_dict, weight_dict
            return batch_X, target_dict

        # Single-task path (unchanged)
        if np.random.random() < self.p_mixup:
            lam = np.random.beta(self.mixup_alpha, self.mixup_alpha)
            perm = np.random.permutation(len(batch_X))
            batch_X = lam * batch_X + (1.0 - lam) * batch_X[perm]
            chord_onehot = lam * chord_onehot + (1.0 - lam) * chord_onehot[perm]

        if self.w is not None:
            return batch_X, chord_onehot, self.w[batch_indices].copy()
        return batch_X, chord_onehot

    def on_epoch_end(self):
        if self.transition_real_ratio is not None and self.real_mask is not None:
            self._resample_indices_transition()
        elif self.shuffle:
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

    def _resample_indices_transition(self):
        """Resample indices to match the target real/synthetic ratio.

        Used during the gradual curriculum transition in Stage 2 to smoothly
        shift from synthetic-heavy to real-heavy data distribution over
        several epochs, avoiding the instant curriculum shock.
        """
        total = len(self.X)
        real_idx = np.where(self.real_mask)[0]
        synth_idx = np.where(~self.real_mask)[0]
        n_real = len(real_idx)
        n_synth = len(synth_idx)
        target_real = int(round(total * self.transition_real_ratio))
        target_real = max(1, min(target_real, n_real))
        target_synth = total - target_real
        if target_synth > n_synth:
            target_synth = n_synth
            target_real = total - target_synth
        chosen_real = np.random.choice(real_idx, size=target_real, replace=True)
        chosen_synth = np.random.choice(synth_idx, size=target_synth, replace=True)
        self.indices = np.concatenate([chosen_real, chosen_synth])
        np.random.shuffle(self.indices)

    def _apply_on_the_fly_augmentations(
        self, batch_X: np.ndarray, batch_y: np.ndarray,
        batch_indices: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        for i in range(len(batch_X)):
            is_real = self.real_mask is not None and batch_indices is not None and self.real_mask[batch_indices[i]]
            sample = batch_X[i]

            # --- Pitch shift with label adjustment ---
            # Real data gets higher pitch-shift probability and range
            p_shift = self.p_pitch_shift * (1.5 if is_real else 1.0)
            if np.random.random() < p_shift:
                p_range = self.pitch_range + (1 if is_real else 0)
                shift = np.random.randint(-p_range, p_range + 1)
                if shift != 0:
                    sample = apply_pitch_shift(sample, shift)
                    batch_y[i] = self._label_after_pitch_shift(batch_y[i], shift)

            # --- Time stretch ---
            # Real data gets higher time-stretch probability
            p_stretch = self.p_time_stretch * (1.5 if is_real else 1.0)
            if np.random.random() < p_stretch:
                s_range = self.stretch_range
                if is_real:
                    # Wider stretch range for real data (0.85-1.15x)
                    s_range = (max(0.85, s_range[0]), min(1.15, s_range[1]))
                factor = np.random.uniform(*s_range)
                sample = apply_time_stretch(sample, factor)

            # --- SpecAugment: Frequency masking ---
            # Masks random contiguous frequency bins to improve cross-recording
            # generalization (different mics/EQ affect different frequency ranges)
            if np.random.random() < self.p_specaug_freq:
                n_bins = sample.shape[-1]
                mask_size = min(self.specaug_freq_mask, n_bins // 4)
                f_start = np.random.randint(0, max(1, n_bins - mask_size))
                sample[:, f_start:f_start + mask_size] = 0.0

            # --- SpecAugment: Time masking ---
            # Masks random contiguous time steps to improve robustness to
            # transient noise and temporal occlusions
            if np.random.random() < self.p_specaug_time:
                n_frames = sample.shape[0]
                mask_size = min(self.specaug_time_mask, n_frames // 4)
                t_start = np.random.randint(0, max(1, n_frames - mask_size))
                sample[t_start:t_start + mask_size, :] = 0.0

            # --- Pink noise ---
            # Real data gets more noise
            n_std = self.noise_std * (2.0 if is_real else 1.0)
            noise = generate_pink_noise(sample.shape, n_std)
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
        if label_idx >= N_INDEX:
            return label_idx  # N class — no shift
        quality_pos = label_idx // N_CLASSES_PER_QUALITY
        root = label_idx % N_CLASSES_PER_QUALITY
        new_root = (root + shift) % N_CLASSES_PER_QUALITY
        return quality_pos * N_CLASSES_PER_QUALITY + new_root

    def get_all_labels(self) -> np.ndarray:
        """Return the original (un-augmented) labels for class-weight computation."""
        return self.y.copy()


# ---------------------------------------------------------------------------
# 2d. Multi-Task Label Derivation (Commit 148 Phase 3b)
# ---------------------------------------------------------------------------


def derive_root_labels(chord_labels: np.ndarray) -> np.ndarray:
    """Derive root classifier labels from chord class indices.

    Root = chord_idx % 12 for chord classes (0-275), or 12 for N class.

    Args:
        chord_labels: (N,) integer chord class indices.

    Returns:
        (N,) integer root labels in range [0, 12].
    """
    root_labels = np.where(
        chord_labels >= N_INDEX, N_ROOTS - 1, chord_labels % N_CLASSES_PER_QUALITY
    ).astype(np.int32)
    return root_labels


def derive_presence_labels(chord_labels: np.ndarray) -> np.ndarray:
    """Derive binary chord-presence labels from chord class indices.

    Presence = 1 for any chord class, 0 for N (no-chord).

    Args:
        chord_labels: (N,) integer chord class indices.

    Returns:
        (N,) float32 binary labels.
    """
    return np.where(chord_labels < N_INDEX, 1.0, 0.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 3. Architecture
# ---------------------------------------------------------------------------


@tf.keras.saving.register_keras_serializable()
class CircularCqtPad(tf.keras.layers.Layer):
    """Circular padding on 144-bin CQT (no bass channel).

    Custom layer (not Lambda) so TFMOT can serialize/clone it for QAT.
    """

    def call(self, x):
        # x shape: (batch, time, 144)
        return tf.concat([x[:, :, -1:], x, x[:, :, :1]], axis=-1)

    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[1], input_shape[2] + 2)

    def get_config(self):
        return super().get_config()


def _circular_cqt_pad(x):
    """Legacy Lambda wrapper — kept for backward compat with Keras 3 saved models."""
    return CircularCqtPad()(x)


def build_model(window: int = WINDOW, return_attention_scores: bool = False,
                qat_compatible: bool = False) -> tf.keras.Model:
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
        qat_compatible: If True, uses ``Add`` for residual instead of Python ``+``
                        — required for TFMOT weight-transfer.

    Returns:
        Single-output model (chord_probs) when return_attention_scores=False.
        Dual-output model (chord_probs, attention_weights) when True.
    """
    inputs = tf.keras.Input(shape=(window, FEATURE_DIM), name="cqt_window")

    padded = CircularCqtPad(name="circular_cqt_pad")(inputs)

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
    # Use Add layer instead of Python + to avoid TFOpLambda serialization issues with TFMOT
    if qat_compatible:
        residual = tf.keras.layers.Add(name="residual_add")([x, mha_output])
    else:
        residual = x + mha_output
    x = tf.keras.layers.LayerNormalization(epsilon=1e-6, name="attention_layernorm")(residual)

    # Bidirectional LSTM layers
    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(128, return_sequences=True), name="bilstm_1"
    )(x)
    x = tf.keras.layers.Dropout(0.45, name="dropout_1")(x)

    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(128, return_sequences=False), name="bilstm_2"
    )(x)
    x = tf.keras.layers.Dropout(0.45, name="dropout_2")(x)

    # Classifier head
    x = tf.keras.layers.Dense(256, activation="relu", name="dense_256")(x)
    x = tf.keras.layers.Dropout(0.45, name="dropout_3")(x)
    outputs = tf.keras.layers.Dense(NUM_CLASSES_MIREX, activation="softmax", name="chord_probs")(x)

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


def build_multi_task_model(
    window: int = WINDOW,
    qat_compatible: bool = False,
) -> tf.keras.Model:
    """Build multi-task CRNN: shared backbone + chord/root/presence heads.

    Reduced architecture for data-scarce setting (~3,800 real windows).
    Removed MultiHeadAttention, single BiLSTM layer, compact dense layers.

    Args:
        window: Temporal window size (default WINDOW=128).
        qat_compatible: If True, uses ``Add`` for residual instead of ``+``.

    Returns:
        Multi-output Keras model with dict outputs:
        ``{'chord_probs': (B, 25), 'root_probs': (B, 13), 'presence': (B, 1)}``
    """
    inputs = tf.keras.Input(shape=(window, FEATURE_DIM), name="cqt_window")
    padded = CircularCqtPad(name="circular_cqt_pad")(inputs)

    # ---- Compact shared backbone with L2 regularization ----

    _l2 = tf.keras.regularizers.l2(1e-4)

    # CNN frontend (reduced width)
    x = tf.keras.layers.Conv1D(32, kernel_size=3, padding="same", activation="relu",
                                kernel_regularizer=_l2,
                                name="conv1d_32")(padded)
    x = tf.keras.layers.MaxPooling1D(pool_size=2, name="maxpool_1")(x)

    x = tf.keras.layers.Conv1D(64, kernel_size=3, padding="same", activation="relu",
                                kernel_regularizer=_l2,
                                name="conv1d_64")(x)
    x = tf.keras.layers.MaxPooling1D(pool_size=2, name="maxpool_2")(x)

    x = tf.keras.layers.BatchNormalization(name="bn_cnn")(x)

    # Single Bidirectional LSTM with L2
    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(64, return_sequences=False,
                             kernel_regularizer=_l2), name="bilstm"
    )(x)
    x = tf.keras.layers.Dropout(0.5, name="dropout_1")(x)

    # Compact embedding with L2
    x = tf.keras.layers.Dense(64, activation="relu", kernel_regularizer=_l2,
                              name="dense_64")(x)
    x = tf.keras.layers.Dropout(0.5, name="dropout_2")(x)

    # ---- Output heads (Phase 3b) ----

    # Head 1: Chord classifier (25-way MIREX)
    chord_probs = tf.keras.layers.Dense(
        NUM_CLASSES_MIREX, activation="softmax", name="chord_probs"
    )(x)

    # Head 2: Root classifier (13-way: 12 roots + N)
    root_probs = tf.keras.layers.Dense(
        N_ROOTS, activation="softmax", name="root_probs"
    )(x)

    # Head 3: Binary chord presence (0 = N, 1 = chord present)
    presence = tf.keras.layers.Dense(
        1, activation="sigmoid", name="presence"
    )(x)

    model = tf.keras.Model(
        inputs=inputs,
        outputs={"chord_probs": chord_probs, "root_probs": root_probs, "presence": presence},
        name="chord_multi_task",
    )
    return model


def extract_chord_predictions(model_output, use_n_rejection: bool = True) -> np.ndarray:
    """Extract chord predictions from multi-task model output with N-rejection.

    For multi-task models, the output is a dict with 'chord_probs', 'root_probs',
    and 'presence' keys.  For single-output models, it is a plain numpy array.

    When ``use_n_rejection=True`` and a binary presence head is available:
    if ``presence < 0.5``, the prediction is forced to N regardless of the
    chord head output.

    Args:
        model_output: dict (multi-task) or np.ndarray (single-output).
        use_n_rejection: If True and presence head is available, force N when
            chord presence is below 0.5.

    Returns:
        (batch_size,) integer predictions.
    """
    if isinstance(model_output, dict):
        chord_probs = model_output["chord_probs"]
        preds = np.argmax(chord_probs, axis=1).astype(np.int32)
        if use_n_rejection and "presence" in model_output:
            presence = model_output["presence"].flatten()
            low_confidence = presence < 0.5
            preds[low_confidence] = N_INDEX
        return preds
    # Single-output model — use N-override as before
    return _apply_n_override(model_output)


# ---------------------------------------------------------------------------
# 3c. Quantization-Aware Training — Commit 106
# ---------------------------------------------------------------------------


def _safe_remove(path: str | Path) -> None:
    """Remove a file, ignoring errors."""
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


def _build_chord_crnn_tfkeras(
    weights_source: tf.keras.Model | None = None,
) -> tf.keras.Model:
    """Build the chord CRNN architecture using pure tf_keras (Keras 2) layers.

    Each quantizable layer (Conv1D, Dense) is wrapped with
    ``tfmot.quantization.keras.quantize_annotate_layer`` so the returned model
    is ready for ``quantize_apply()`` without any cloning.

    Must be called with ``TF_USE_LEGACY_KERAS=1`` so that ``tf.keras`` routes
    to ``tf_keras`` (Keras 2), which TFMOT expects.

    Uses a ``Lambda`` layer for CQT padding instead of a custom class to avoid
    serialization/deserialisation issues when ``tfmot`` rebuilds the model
    graph during ``quantize_apply()``.

    Builds a multi-task model with three output heads:
    - chord_probs: 277-way softmax (main head)
    - root_probs: 13-way softmax
    - presence: 1-way sigmoid

    Note: Does NOT annotate individual layers with ``qal()`` — that approach
    fails because ``quantize_apply`` clones the model and unwraps per-layer
    annotations. Instead, the model is built plain and
    ``quantize_annotate_model()`` is applied in ``apply_qat()``.

    Args:
        weights_source: Optional Keras 3 model whose weights are copied into
            the fresh tf_keras model by layer name.

    Returns:
        Plain tf_keras model (no per-layer annotations) ready for
        ``quantize_annotate_model()`` + ``quantize_apply()``.
    """

    inputs = tf.keras.Input(shape=(WINDOW, FEATURE_DIM), name="cqt_window")
    padded = CircularCqtPad(name="circular_cqt_pad")(inputs)

    _l2 = tf.keras.regularizers.l2(1e-4)

    x = tf.keras.layers.Conv1D(32, 3, padding="same", activation="relu",
                                kernel_regularizer=_l2,
                                name="conv1d_32")(padded)
    x = tf.keras.layers.MaxPooling1D(pool_size=2, name="maxpool_1")(x)

    x = tf.keras.layers.Conv1D(64, 3, padding="same", activation="relu",
                                kernel_regularizer=_l2,
                                name="conv1d_64")(x)
    x = tf.keras.layers.MaxPooling1D(pool_size=2, name="maxpool_2")(x)

    x = tf.keras.layers.BatchNormalization(name="bn_cnn")(x)

    x = tf.keras.layers.Bidirectional(
        tf.keras.layers.LSTM(64, return_sequences=False,
                             kernel_regularizer=_l2), name="bilstm"
    )(x)
    x = tf.keras.layers.Dropout(0.5, name="dropout_1")(x)

    x = tf.keras.layers.Dense(64, activation="relu", kernel_regularizer=_l2,
                              name="dense_64")(x)
    x = tf.keras.layers.Dropout(0.5, name="dropout_2")(x)

    # Multi-task heads
    chord_head = tf.keras.layers.Dense(NUM_CLASSES_MIREX, activation="softmax", name="chord_probs")(x)
    root_head = tf.keras.layers.Dense(N_ROOTS, activation="softmax", name="root_probs")(x)
    presence_head = tf.keras.layers.Dense(1, activation="sigmoid", name="presence")(x)

    tf_keras_model = tf.keras.Model(
        inputs=inputs,
        outputs={"chord_probs": chord_head, "root_probs": root_head, "presence": presence_head},
        name="chord_crnn_attention",
    )

    # Copy weights from the source Keras 3 model by layer name.
    if weights_source is not None:
        for layer in tf_keras_model.layers:
            try:
                src = weights_source.get_layer(layer.name)
            except ValueError:
                continue
            if src.get_weights():
                try:
                    layer.set_weights(src.get_weights())
                except Exception as e:
                    print(f"  [WARN] could not set weights for '{layer.name}': {e}")

    return tf_keras_model


def apply_qat(model: tf.keras.Model) -> tf.keras.Model:
    """Apply Quantization-Aware Training wrapper to a trained float32 model.

    Builds a fresh tf_keras (Keras 2) copy of the chord CRNN with all
    quantizable layers (Conv1D, Dense) wrapped by
    ``tfmot.quantization.keras.quantize_annotate_layer``, copies weights
    from the Keras 3 *model*, and then calls ``quantize_apply()`` to
    insert fake-quantization nodes.

    This approach avoids ``quantize_model()`` (which internally clones the
    model and fails on Keras 3 layers) and ``clone_model`` (which has
    serialisation issues with TFMOT wrappers).

    Args:
        model: Trained float32 Keras model (output of :func:`build_model`).

    Returns:
        QAT-wrapped model ready for fine-tuning with simulated quantization.

    Raises:
        ImportError: If ``tensorflow_model_optimization`` is not installed.
    """
    if not _HAS_TFMOT:
        raise ImportError(
            "tensorflow_model_optimization is required for QAT. "
            "Install with: pip install tensorflow-model-optimization"
        )

    _old_legacy = os.environ.get("TF_USE_LEGACY_KERAS")
    try:
        os.environ["TF_USE_LEGACY_KERAS"] = "1"
        plain_model = _build_chord_crnn_tfkeras(weights_source=model)

        # Patch keras.models.clone_model used inside quantize_apply so that
        # _quantize passes through unsupported layers (CircularCqtPad, etc.)
        # instead of raising RuntimeError.
        from tensorflow_model_optimization.python.core.keras.compat import keras as _tfmot_keras
        _orig_clone = _tfmot_keras.models.clone_model

        def _safe_clone_model(model, input_tensors=None, clone_function=None):
            if clone_function is not None:
                _orig_qf = clone_function
                def _safe_quantize(layer):
                    try:
                        return _orig_qf(layer)
                    except (RuntimeError, ValueError):
                        return layer
                clone_function = _safe_quantize
            return _orig_clone(model, input_tensors=input_tensors,
                               clone_function=clone_function)

        _tfmot_keras.models.clone_model = _safe_clone_model
        try:
            annotated_model = tfmot.quantization.keras.quantize_annotate_model(plain_model)
            qat_model = tfmot.quantization.keras.quantize_apply(annotated_model)
        finally:
            _tfmot_keras.models.clone_model = _orig_clone
    finally:
        if _old_legacy is None:
            os.environ.pop("TF_USE_LEGACY_KERAS", None)
        else:
            os.environ["TF_USE_LEGACY_KERAS"] = _old_legacy

    print(
        "  Applied QAT via direct tf_keras annotation "
        "— Conv1D and Dense layers quantized"
    )
    return qat_model


def convert_to_int8_tflite(
    model: tf.keras.Model,
    representative_data: np.ndarray,
    output_path: str | Path,
) -> bytes | None:
    """Convert a QAT-wrapped model to INT8-quantized TFLite.

    Tries multiple strategies in order: INT8 with calibration, INT8 without
    calibration, FP16, and finally Float32. The BiLSTM layer uses TensorList
    ops that require SELECT_TF_OPS, which the calibrator cannot handle, so
    fallback strategies are essential.

    Args:
        model: QAT-wrapped Keras model (output of :func:`apply_qat`).
        representative_data: Validation-data subset for calibration,
            shape ``(N, WINDOW, FEATURE_DIM)``.
        output_path: Destination path for the ``.tflite`` file.

    Returns:
        Raw TFLite model bytes, or None if all strategies failed.
    """
    # For multi-output models, export only chord_probs head for TFLite
    is_multi = hasattr(model, 'output_names') and isinstance(model.output, dict)
    if is_multi:
        export_m = tf.keras.Model(inputs=model.input, outputs=model.output["chord_probs"])
    else:
        export_m = model

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    strategies = []

    # Strategy 1: INT8 with calibration (requires Flex delegate at calibration time)
    n_samples = min(100, len(representative_data))

    def _representative():
        for i in range(n_samples):
            yield [representative_data[i : i + 1].astype(np.float32)]

    strategies.append(("INT8 (calibrated)", lambda: _build_converter(
        export_m,
        optimizations=[tf.lite.Optimize.DEFAULT],
        representative_dataset=_representative,
        supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8, tf.lite.OpsSet.SELECT_TF_OPS],
        inference_input_type=tf.int8,
        inference_output_type=tf.int8,
    )))

    # Strategy 2: INT8 without calibration (static ranges, may be less accurate)
    strategies.append(("INT8 (no calibration)", lambda: _build_converter(
        export_m,
        optimizations=[tf.lite.Optimize.DEFAULT],
        supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8, tf.lite.OpsSet.SELECT_TF_OPS],
        inference_input_type=tf.int8,
        inference_output_type=tf.int8,
    )))

    # Strategy 3: FP16 dynamic range (no calibration needed)
    strategies.append(("FP16", lambda: _build_converter(
        export_m,
        optimizations=[tf.lite.Optimize.DEFAULT],
        supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS, tf.lite.OpsSet.SELECT_TF_OPS],
    )))

    # Strategy 4: Float32 (no optimization, just SELECT_TF_OPS compatibility)
    strategies.append(("Float32", lambda: _build_converter(
        export_m,
        supported_ops=[tf.lite.OpsSet.SELECT_TF_OPS],
    )))

    for name, build_fn in strategies:
        try:
            print(f"  Trying {name} conversion...")
            converter = build_fn()
            tflite_model = converter.convert()
            with open(output_path, "wb") as f:
                f.write(tflite_model)
            print(f"  {name} TFLite saved to {output_path} ({len(tflite_model) / 1024:.1f} KB)")
            return tflite_model
        except Exception as exc:
            print(f"  [SKIP] {name} conversion failed: {exc}")
            continue

    print("  [FAIL] All TFLite conversion strategies failed")
    return None


def convert_to_onnx(
    model: tf.keras.Model,
    output_path: str | Path,
) -> str | None:
    """Convert a Keras model to ONNX format for web inference.

    Uses tf2onnx to produce an ONNX model that can be loaded by
    onnxruntime-web in the browser.

    Args:
        model: Trained Keras model (single-output chord_probs head).
        output_path: Destination path for the ``.onnx`` file.

    Returns:
        The output path string on success, or None on failure.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import tf2onnx
        import tf2onnx.convert
    except ImportError:
        print("  [SKIP] ONNX conversion — tf2onnx not installed. "
              "Install with: pip install tf2onnx")
        return None

    try:
        spec = (tf.TensorSpec(model.input_shape, tf.float32, name="input"),)
        model_proto, _ = tf2onnx.convert.from_keras(
            model,
            input_signature=spec,
            output_path=str(output_path),
        )
        size_kb = output_path.stat().st_size / 1024
        print(f"  Saved ONNX -> {output_path}  ({size_kb:.1f} KB)")
        return str(output_path)
    except Exception as exc:
        print(f"  [WARN] ONNX conversion failed: {exc}")
        return None


def _build_converter(
    model: tf.keras.Model,
    optimizations: list | None = None,
    representative_dataset: Callable | None = None,
    supported_ops: list | None = None,
    inference_input_type: Any = None,
    inference_output_type: Any = None,
) -> tf.lite.TFLiteConverter:
    """Build a TFLiteConverter with the given options."""
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    if optimizations is not None:
        converter.optimizations = optimizations
    if representative_dataset is not None:
        converter.representative_dataset = representative_dataset
    if supported_ops is not None:
        converter.target_spec.supported_ops = supported_ops
    if inference_input_type is not None:
        converter.inference_input_type = inference_input_type
    if inference_output_type is not None:
        converter.inference_output_type = inference_output_type
    return converter


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
    cm = confusion_matrix(y_true, y_pred, labels=range(NUM_CLASSES_MIREX))

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
        true_chord = MIREX_VOCAB[i]
        pred_chord = MIREX_VOCAB[j]
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
        labels=range(NUM_CLASSES_MIREX),
        target_names=MIREX_VOCAB,
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
    weight_dict = dict(zip(classes, weights))

    # Cap N (no-chord) class weight to prevent over-penalization.
    # N has only 1 class vs 276 chord classes, so sklearn balanced gives it
    # an extremely high weight. Capping at 3.0 keeps it reasonable.
    n_idx = NUM_CLASSES_MIREX - 1  # N is the last class (index 24)
    if n_idx in weight_dict:
        weight_dict[n_idx] = min(weight_dict[n_idx], 3.0)

    return weight_dict


# ---------------------------------------------------------------------------
# 4a. Multi-source dataset loading (Commit 105)
# ---------------------------------------------------------------------------

def _build_recording_id(data: np.lib.npyio.NpzFile, source_name: str, npz_path: Path) -> str:
    """Build a recording-level identifier from available metadata.

    Uses player_id (session-level) if available, otherwise track_id.
    The identifier is prefixed with the source name to ensure uniqueness
    across datasets (e.g., 'guitarset_player_00' vs 'guitar_techs_player_P1').
    """
    player_id = str(data.get("player_id", b"")).strip()
    if player_id:
        return f"{source_name}_player_{player_id}"
    track_id = str(data.get("track_id", b"")).strip()
    if track_id:
        return f"{source_name}_{track_id}"
    # Fallback: use filename stem as a unique recording ID
    return f"{source_name}_{npz_path.stem}"


def load_dataset_dir(data_path: Path) -> tuple[np.ndarray, np.ndarray, float | None, np.ndarray]:
    """Load CQT features, labels, and loss weight from a dataset .npz directory.

    Reads all .npz files from <data_path>/processed/cqt/.
    Filters out files with split='test' (e.g., GuitarSet player_05).

    Returns:
        (features, labels, loss_weight, recording_ids) where:
        - features: (N, 128, 144) float32 CQT windows
        - labels: (N,) int32 277-class chord labels
        - loss_weight: per-source loss weight from .npz metadata or None
        - recording_ids: (N,) object array of recording-level identifiers
          for leave-recording-out validation. Derived from player_id or track_id.
    """
    cqt_dir = data_path / "processed" / "cqt"
    if not cqt_dir.exists():
        raise FileNotFoundError(f"CQT directory not found: {cqt_dir}")

    npz_files = sorted(cqt_dir.glob("*.npz"))
    if not npz_files:
        raise FileNotFoundError(f"No .npz files found in {cqt_dir}")

    all_features: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []
    all_recording_ids: list[np.ndarray] = []
    loss_weight: float | None = None
    source_name = data_path.name

    for npz_path in npz_files:
        data = np.load(npz_path)
        split = str(data.get("split", b""))
        # GuitarSet test split (player_05) is excluded from training
        if split == "test":
            continue
        # Read loss_weight from the first file (all files from same source
        # should have the same loss_weight)
        if "loss_weight" in data and loss_weight is None:
            loss_weight = float(data["loss_weight"])
        # Build recording-level ID for this file (player or track level)
        rec_id = _build_recording_id(data, source_name, npz_path)
        n_windows = len(data["features"])
        all_features.append(data["features"])
        all_labels.append(data["labels"])
        all_recording_ids.append(np.full(n_windows, rec_id, dtype=object))

    if not all_features:
        raise ValueError(f"No training files found in {cqt_dir}")

    X = np.concatenate(all_features, axis=0).astype(np.float32)
    y = np.concatenate(all_labels, axis=0).astype(np.int32)
    recording_ids = np.concatenate(all_recording_ids, axis=0)

    n_recordings = len(set(recording_ids))
    print(f"  Loaded {len(X)} windows from {n_recordings} recordings, "
          f"{len(npz_files)} files ({source_name}, loss_weight={loss_weight})")
    return X, y, loss_weight, recording_ids


def load_datasets(sources: list[tuple[Path, str, float]]) -> tuple[
    list[np.ndarray], list[np.ndarray], list[np.ndarray], list[np.ndarray],
]:
    """Load multiple datasets with per-source loss weights.

    Args:
        sources: List of (data_dir, source_name, default_loss_weight) tuples.
                 source_name is used for logging only.
                 default_loss_weight is used if not present in .npz metadata.

    Returns:
        (features_list, labels_list, weights_list, recording_ids_list)
        where each element is a list of arrays, one per source.
        recording_ids_list contains recording-level identifiers for
        leave-recording-out validation.
    """
    features_list: list[np.ndarray] = []
    labels_list: list[np.ndarray] = []
    weights_list: list[np.ndarray] = []
    recording_ids_list: list[np.ndarray] = []

    for data_dir, source_name, default_weight in sources:
        try:
            X, y, lw, rec_ids = load_dataset_dir(data_dir)
            lw = lw if lw is not None else default_weight
            features_list.append(X)
            labels_list.append(y)
            weights_list.append(np.full(len(X), lw, dtype=np.float32))
            recording_ids_list.append(rec_ids)
        except Exception as e:
            print(f"  [SKIP] {source_name}: {e}")
            continue

    return features_list, labels_list, weights_list, recording_ids_list


def load_guitarset_test(data_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load GuitarSet test split (player 05) for evaluation."""
    cqt_dir = data_dir / "processed" / "cqt"
    if not cqt_dir.exists():
        raise FileNotFoundError(f"GuitarSet CQT directory not found: {cqt_dir}")

    npz_files = sorted(cqt_dir.glob("*.npz"))
    all_features: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []

    for npz_path in npz_files:
        data = np.load(npz_path)
        split = str(data.get("split", b""))
        if split == "test":
            all_features.append(data["features"])
            all_labels.append(data["labels"])

    if not all_features:
        raise ValueError("No GuitarSet test data found (player 05)")

    X = np.concatenate(all_features, axis=0).astype(np.float32)
    y = np.concatenate(all_labels, axis=0).astype(np.int32)
    print(f"  Loaded {len(X)} test windows from GuitarSet player-05")
    return X, y


# ---------------------------------------------------------------------------
# 4c. GuitarSet 5-fold Leave-One-Player-Out CV (Commit 122 Phase 4c)
# ---------------------------------------------------------------------------

# Players used for CV (00-04). Player 05 is held out for final test.
_CV_PLAYERS = ["00", "01", "02", "03", "04"]


def load_guitarset_by_player(
    data_dir: Path,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Load GuitarSet data grouped by player ID.

    Returns a dict mapping player_id -> (features, labels) for all 6 players.
    Each value contains the concatenated windows from all tracks by that player.
    """
    cqt_dir = data_dir / "processed" / "cqt"
    if not cqt_dir.exists():
        raise FileNotFoundError(f"GuitarSet CQT directory not found: {cqt_dir}")

    player_data: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        p: [] for p in ["00", "01", "02", "03", "04", "05"]
    }

    for npz_path in sorted(cqt_dir.glob("*.npz")):
        data = np.load(npz_path)
        player_id = str(data.get("player_id", b""))[:2]
        if player_id not in player_data:
            continue
        player_data[player_id].append((data["features"], data["labels"]))

    result: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for pid, files in sorted(player_data.items()):
        if not files:
            continue
        X = np.concatenate([f[0] for f in files], axis=0).astype(np.float32)
        y = np.concatenate([f[1] for f in files], axis=0).astype(np.int32)
        result[pid] = (X, y)

    return result


def run_guitarset_cv(
    guitarset_data_dir: str | Path,
    build_model_fn=None,
    train_kwargs: dict | None = None,
    epochs: int = 30,
    batch_size: int = 64,
    verbose: int = 1,
) -> dict[str, object]:
    """Run 5-fold leave-one-player-out cross-validation on GuitarSet.

    Each fold holds out one player (00-04) for validation and trains on
    the remaining 4 players. Player 05 is never used (held out for final test).

    Args:
        guitarset_data_dir: Path to GuitarSet data directory.
        build_model_fn: Callable that returns a compiled Keras model.
            If None, uses build_multi_task_model().
        train_kwargs: Extra kwargs passed to model.fit() (callbacks, etc.).
        epochs: Number of training epochs per fold.
        batch_size: Batch size for training.
        verbose: Verbosity level.

    Returns:
        Dict with keys:
            fold_accuracies: list of per-fold validation accuracies
            mean_accuracy: mean across folds
            std_accuracy: std across folds
            per_fold_details: list of dicts with per-fold metrics
    """
    from sklearn.model_selection import train_test_split as _ts

    data_dir = Path(guitarset_data_dir)
    player_data = load_guitarset_by_player(data_dir)

    missing = [p for p in _CV_PLAYERS if p not in player_data]
    if missing:
        raise ValueError(f"Missing GuitarSet players for CV: {missing}")

    print(f"\n{'=' * 60}")
    print(f"  GuitarSet 5-Fold Leave-One-Player-Out CV")
    print(f"  Players: {_CV_PLAYERS} (player 05 held out for final test)")
    print(f"{'=' * 60}")

    fold_accuracies: list[float] = []
    fold_details: list[dict] = []

    for fold_idx, val_player in enumerate(_CV_PLAYERS):
        train_players = [p for p in _CV_PLAYERS if p != val_player]

        # Combine training players
        X_train = np.concatenate([player_data[p][0] for p in train_players])
        y_train = np.concatenate([player_data[p][1] for p in train_players])
        X_val = player_data[val_player][0]
        y_val = player_data[val_player][1]

        print(f"\n--- Fold {fold_idx + 1}/5: val=player {val_player}, "
              f"train=players {train_players} ---")
        print(f"  Train: {len(X_train)} windows, Val: {len(X_val)} windows")

        # Build and compile model
        if build_model_fn is not None:
            model = build_model_fn()
        else:
            model = build_multi_task_model()

        # Default compilation for multi-task
        if not hasattr(model, 'optimizer') or model.optimizer is None:
            model.compile(
                optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3, weight_decay=1e-4, clipnorm=1.0),
                loss={
                    "chord_probs": tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.0),
                    "root_probs": tf.keras.losses.CategoricalCrossentropy(),
                    "presence": tf.keras.losses.BinaryCrossentropy(),
                },
                loss_weights={"chord_probs": 1.0, "root_probs": 0.1, "presence": 0.05},
                metrics={"chord_probs": "accuracy"},
            )

        # Prepare validation dict
        y_val_root = tf.keras.utils.to_categorical(
            derive_root_labels(y_val), N_ROOTS
        ).astype(np.float32)
        y_val_presence = derive_presence_labels(y_val).reshape(-1, 1)
        y_val_dict = {
            "chord_probs": tf.keras.utils.to_categorical(y_val, NUM_CLASSES_MIREX).astype(np.float32),
            "root_probs": y_val_root,
            "presence": y_val_presence,
        }

        # Prepare training dict
        y_train_dict = {
            "chord_probs": tf.keras.utils.to_categorical(y_train, NUM_CLASSES_MIREX).astype(np.float32),
            "root_probs": tf.keras.utils.to_categorical(derive_root_labels(y_train), N_ROOTS).astype(np.float32),
            "presence": derive_presence_labels(y_train).reshape(-1, 1).astype(np.float32),
        }

        # Train
        model.fit(
            X_train,
            y_train_dict,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=(X_val, y_val_dict),
            verbose=verbose,
        )

        # Evaluate
        output = model.predict(X_val, verbose=0)
        y_pred = extract_chord_predictions(output)
        acc = float(np.mean(y_pred == y_val))
        fold_accuracies.append(acc)

        # Per-group accuracy
        grouped = compute_grouped_accuracy(y_val, y_pred)
        detail = {
            "fold": fold_idx + 1,
            "val_player": val_player,
            "train_players": train_players,
            "accuracy": acc,
            "n_val": len(X_val),
            "grouped": grouped,
        }
        fold_details.append(detail)

        print(f"  Fold {fold_idx + 1} accuracy: {acc:.1%}")
        for group, gacc in sorted(grouped.items()):
            print(f"    {group:20s}: {gacc * 100:.1f}%")

        del model
        tf.keras.backend.clear_session()

    mean_acc = float(np.mean(fold_accuracies))
    std_acc = float(np.std(fold_accuracies))

    # Phase 6b: Bootstrap CI on the CV mean
    rng = np.random.RandomState(42)
    n_bootstraps = 1000
    boot_means = np.empty(n_bootstraps, dtype=np.float64)
    for i in range(n_bootstraps):
        idx = rng.randint(0, len(fold_accuracies), size=len(fold_accuracies))
        boot_means[i] = np.mean(np.array(fold_accuracies)[idx])
    cv_ci_lower = float(np.percentile(boot_means, 2.5))
    cv_ci_upper = float(np.percentile(boot_means, 97.5))

    print(f"\n{'=' * 60}")
    print(f"  GuitarSet 5-Fold CV Results")
    print(f"{'=' * 60}")
    for i, (acc, detail) in enumerate(zip(fold_accuracies, fold_details)):
        print(f"  Fold {i + 1} (player {detail['val_player']}): {acc:.1%}")
    print(f"  ─────────────────────────────────")
    print(f"  Mean ± std: {mean_acc:.1%} ± {std_acc:.1%}")
    print(f"  95% CI: [{cv_ci_lower:.1%}, {cv_ci_upper:.1%}]")
    print(f"  Range: {min(fold_accuracies):.1%} – {max(fold_accuracies):.1%}")
    print(f"{'=' * 60}")

    return {
        "fold_accuracies": fold_accuracies,
        "mean_accuracy": mean_acc,
        "std_accuracy": std_acc,
        "ci_lower": cv_ci_lower,
        "ci_upper": cv_ci_upper,
        "per_fold_details": fold_details,
    }


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
    dataset_sources: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Mix multiple datasets by concatenation with per-source sample weights.

    Each source provides (X, y, sample_weights, recording_ids). The arrays
    are concatenated and shuffled consistently.

    Args:
        dataset_sources: List of (features, labels, sample_weights, recording_ids)
                         tuples, one per data source.

    Returns:
        (X, y, sample_weights, source_ids, recording_ids) concatenated and
        shuffled arrays. source_ids tracks which source each sample came from.
        recording_ids tracks recording-level groups for honest cross-recording
        train/val splitting.
    """
    if len(dataset_sources) == 0:
        raise ValueError("At least one dataset source is required")

    X_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    w_parts: list[np.ndarray] = []
    source_parts: list[np.ndarray] = []
    rec_id_parts: list[np.ndarray] = []

    for i, (X_src, y_src, w_src, rec_ids_src) in enumerate(dataset_sources):
        X_parts.append(X_src)
        y_parts.append(y_src)
        w_parts.append(w_src)
        source_parts.append(np.full(len(X_src), i, dtype=np.int32))
        rec_id_parts.append(rec_ids_src)

    X = np.concatenate(X_parts, axis=0).astype(np.float32)
    y = np.concatenate(y_parts, axis=0).astype(np.int32)
    w = np.concatenate(w_parts, axis=0).astype(np.float32)
    source_ids = np.concatenate(source_parts, axis=0).astype(np.int32)
    recording_ids = np.concatenate(rec_id_parts, axis=0)

    # Shuffle consistently
    p = np.random.permutation(len(X))
    X, y, w, source_ids, recording_ids = X[p], y[p], w[p], source_ids[p], recording_ids[p]

    total = len(X)
    n_recordings = len(set(recording_ids))
    print(f"  Mixed {len(dataset_sources)} sources: {total} total samples "
          f"from {n_recordings} recordings")
    for i, (X_src, _, _, _) in enumerate(dataset_sources):
        print(f"    Source {i}: {len(X_src)} samples")

    return X, y, w, source_ids, recording_ids


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

        test_output = self.model.predict(self.test_X, verbose=0)
        test_pred = extract_chord_predictions(test_output)
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


class EGSet12TestCallback(tf.keras.callbacks.Callback):
    """Evaluate on EGSet12 held-out set after each epoch (Phase 6a).

    EGSet12 provides 12 real solo electric guitar recordings with diverse
    playing styles — useful as a second real-world eval axis alongside
    GuitarSet's player_05 test split.

    Reports bootstrapped 95% confidence intervals since 61 eval windows
    is too small for stable point estimates.
    """

    def __init__(
        self,
        test_X: np.ndarray,
        test_y: np.ndarray,
        log_freq: int = 1,
        n_bootstraps: int = 1000,
    ):
        super().__init__()
        self.test_X = test_X
        self.test_y = test_y
        self.log_freq = log_freq
        self.n_bootstraps = n_bootstraps
        self.history: list[float] = []
        self.ci_history: list[dict] = []
        self.best_test_acc: float = 0.0
        self.best_epoch: int = -1

    def on_epoch_end(self, epoch: int, logs: dict | None = None):
        if (epoch + 1) % self.log_freq != 0:
            return
        if len(self.test_X) == 0:
            return

        test_output = self.model.predict(self.test_X, verbose=0)
        test_pred = extract_chord_predictions(test_output)
        test_acc = float(np.mean(test_pred == self.test_y))
        self.history.append(test_acc)

        ci = bootstrap_ci_accuracies(self.test_y, test_pred, n_bootstraps=self.n_bootstraps)
        self.ci_history.append(ci)

        if test_acc > self.best_test_acc:
            self.best_test_acc = test_acc
            self.best_epoch = epoch

        print(f"\n  [EGSet12] Epoch {epoch + 1}: "
              f"accuracy={test_acc:.2%} ± {ci['std_acc']:.2%} "
              f"(95% CI: [{ci['ci_lower']:.2%}, {ci['ci_upper']:.2%}]) "
              f"(best={self.best_test_acc:.2%} @ epoch {self.best_epoch + 1})")


class TwoPhaseCallback(tf.keras.callbacks.Callback):
    """Manages two-phase training curriculum (Commit 148 Phase 2d).

    Prints a visual separator at the end of Phase A (epoch ``switch_epoch``)
    and logs the transition. The actual data/LR switch is handled externally
    by ``run_pipeline()`` which starts a second ``model.fit()`` call.
    """

    def __init__(self, switch_epoch: int = 30):
        super().__init__()
        self.switch_epoch = switch_epoch

    def on_epoch_end(self, epoch: int, logs: dict | None = None):
        if (epoch + 1) == self.switch_epoch:
            print(f"\n{'=' * 60}")
            print(f"  Phase A complete (epoch {epoch + 1}). Switching to Phase B...")
            print(f"{'=' * 60}\n")


class GradualTransitionCallback(tf.keras.callbacks.Callback):
    """Gradually transitions the real-data ratio in the data generator.

    Smoothly ramps ``generator.transition_real_ratio`` from ``start_ratio``
    to ``target_ratio`` over ``transition_epochs``, preventing the instant
    curriculum shock that occurs when switching from synthetic-heavy to
    real-heavy data.

    The generator responds to this ratio at each ``on_epoch_end`` via
    ``_resample_indices_transition()``.
    """

    def __init__(
        self,
        generator: AugmentedDataGenerator,
        start_ratio: float = 0.5,
        target_ratio: float = 0.8,
        transition_epochs: int = 10,
        start_epoch: int = 0,
    ):
        super().__init__()
        self.generator = generator
        self.start_ratio = start_ratio
        self.target_ratio = target_ratio
        self.transition_epochs = transition_epochs
        self.start_epoch = start_epoch

    def on_epoch_begin(self, epoch: int, logs: dict | None = None):
        phase_epoch = epoch - self.start_epoch
        if 0 <= phase_epoch < self.transition_epochs:
            progress = (phase_epoch + 1) / self.transition_epochs
            ratio = self.start_ratio + progress * (self.target_ratio - self.start_ratio)
            self.generator.transition_real_ratio = ratio


def _apply_n_override(
    probs: np.ndarray,
    n_class_idx: int | None = None,
    prob_threshold: float = 0.3,
    entropy_threshold: float | None = None,
) -> np.ndarray:
    """Override N predictions: only allow N when model is genuinely uncertain.

    When the model has reasonable confidence (>threshold) in any chord class,
    force the prediction to that chord instead of allowing N as a default escape
    hatch. This breaks the "always predict N for real audio" equilibrium by
    removing the safe default and forcing the model to commit to a chord guess.

    N is only predicted when BOTH conditions hold:
      1. The best non-N chord probability is below ``prob_threshold``.
      2. Entropy across all classes is high (model is genuinely confused).

    If either condition is false, the prediction is forced to the best non-N
    chord class, creating gradient pressure for the model to learn real audio
    patterns.

    Args:
        probs: (batch_size, num_classes) softmax probability array.
        n_class_idx: Index of the N (no-chord) class. Defaults to
            ``NUM_CLASSES - 1`` (the last entry, per ``CHORD_CLASS_MAP``).
        prob_threshold: Minimum probability for a chord prediction to be kept.
        entropy_threshold: Entropy threshold. If ``None``, computed as
            0.7 * log(num_classes). With 25 classes this is ~2.25.

    Returns:
        (batch_size,) argmax predictions with N-override applied.
    """
    if n_class_idx is None:
        n_class_idx = NUM_CLASSES_MIREX - 1

    if entropy_threshold is None:
        entropy_threshold = 0.7 * np.log(float(probs.shape[1]))

    eps = 1e-10
    entropy = -np.sum(probs * np.log(np.clip(probs, eps, 1.0)), axis=1)

    chord_probs = probs.copy()
    chord_probs[:, n_class_idx] = -1.0
    best_chord_idx = np.argmax(chord_probs, axis=1).astype(np.int32)
    best_chord_prob = np.max(chord_probs, axis=1)

    # Default: plain argmax (may pick N)
    preds = np.argmax(probs, axis=1).astype(np.int32)

    # Allow N only when BOTH: best chord prob is low AND entropy is high
    allow_n = (best_chord_prob < prob_threshold) & (entropy > entropy_threshold)

    # Force chord prediction when N is used as an uncertainty escape hatch
    n_mask = (preds == n_class_idx) & (~allow_n)
    preds[n_mask] = best_chord_idx[n_mask]

    return preds


class DualValidationLogger(tf.keras.callbacks.Callback):
    """Per-epoch dual validation logging (Commit 148 Phase 1e, Phase 6c).

    Evaluates the model on both real and synthetic validation sets at
    each epoch end and logs ``val_accuracy_real``, ``val_accuracy_synthetic``,
    and ``domain_gap`` to a CSV file alongside the standard metrics.

    Phase 6c: Also computes Earth Mover's Distance (EMD) between real and
    synthetic CQT distributions every epoch, and saves t-SNE projection
    plots periodically.
    """

    def __init__(
        self,
        X_real_val: np.ndarray,
        y_real_val: np.ndarray,
        X_synth_val: np.ndarray,
        y_synth_val: np.ndarray,
        filename: str = "training_log.csv",
        separator: str = ",",
        append: bool = False,
        plot_output_dir: Path | str | None = None,
        plot_every_n: int = 5,
    ):
        super().__init__()
        self.X_real_val = X_real_val
        self.y_real_val = y_real_val
        self.X_synth_val = X_synth_val
        self.y_synth_val = y_synth_val
        self.sep = separator
        self.filename = filename
        self.append = append
        self.writer = None
        self.keys: list[str] | None = None
        self.plot_output_dir = Path(plot_output_dir) if plot_output_dir else _SCRIPTS_DIR
        self.plot_every_n = plot_every_n
        self.emd_history: list[float] = []

    def on_epoch_end(self, epoch: int, logs: dict | None = None):
        logs = logs or {}

        # Evaluate on real validation set (with N-rejection via extract_chord_predictions)
        has_real = len(self.X_real_val) > 0 and len(self.y_real_val) > 0
        if has_real:
            real_output = self.model.predict(self.X_real_val, verbose=0)
            real_pred = extract_chord_predictions(real_output)
            real_acc = float(np.mean(real_pred == self.y_real_val))
            logs["val_accuracy_real"] = real_acc
        else:
            logs["val_accuracy_real"] = 0.0

        # Evaluate on synthetic validation set (no N-override — synthetic N is clean)
        has_synth = len(self.X_synth_val) > 0 and len(self.y_synth_val) > 0
        if has_synth:
            synth_output = self.model.predict(self.X_synth_val, verbose=0)
            if isinstance(synth_output, dict):
                synth_pred = np.argmax(synth_output["chord_probs"], axis=1)
            else:
                synth_pred = np.argmax(synth_output, axis=1)
            synth_acc = float(np.mean(synth_pred == self.y_synth_val))
            logs["val_accuracy_synthetic"] = synth_acc
        else:
            synth_acc = 0.0
            logs["val_accuracy_synthetic"] = 0.0

        # Domain gap = synthetic - real
        logs["domain_gap"] = synth_acc - logs["val_accuracy_real"]

        # Phase 6c: Compute CQT domain EMD (every epoch)
        has_real_cqt = len(self.X_real_val) > 0
        has_synth_cqt = len(self.X_synth_val) > 0
        if has_real_cqt and has_synth_cqt:
            emd = compute_cqt_emd(self.X_real_val, self.X_synth_val)
            logs["cqt_emd"] = emd
            self.emd_history.append(emd)
            print(f"    CQT EMD: {emd:.4f}")
            # Phase 6c: Save t-SNE projection periodically
            if (epoch + 1) % self.plot_every_n == 0:
                plot_path = visualize_cqt_domain(
                    self.X_real_val, self.X_synth_val,
                    epoch=epoch + 1, emd_value=emd,
                    output_dir=self.plot_output_dir,
                )
                if plot_path:
                    print(f"    Saved CQT domain plot -> {plot_path}")
        else:
            logs["cqt_emd"] = 0.0

        # CSV writing (same logic as CSVLogger)
        if self.keys is None:
            self.keys = sorted(logs.keys())
        import csv
        file_exists = False
        has_header_mismatch = False
        try:
            with open(self.filename, "r") as f:
                first_line = f.readline()
                file_exists = bool(first_line)
                if file_exists:
                    existing_headers = [h.strip() for h in first_line.strip().split(",")]
                    if set(existing_headers) != set(self.keys):
                        has_header_mismatch = True
        except FileNotFoundError:
            pass
        # If header mismatch, truncate and start fresh
        mode = "w" if (not file_exists or has_header_mismatch) else ("a" if self.append else "w")
        with open(self.filename, mode, newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.keys)
            if mode == "w" or has_header_mismatch:
                writer.writeheader()
            row = {k: logs.get(k, "") for k in self.keys}
            writer.writerow(row)


# ---------------------------------------------------------------------------
# 4e. TFLite smoke test helper (Commit 106)
# ---------------------------------------------------------------------------


def _run_tflite_smoke_test(
    label: str,
    model_path: Path,
    is_int8: bool,
    float32_keras_model: tf.keras.Model | None = None,
    cqt_stats: dict | None = None,
) -> bool:
    """Run top-1 chord accuracy smoke tests on a TFLite model.

    Tries three paths in order of preference:
    1. ``tflite_runtime.Interpreter`` (Flex delegate)
    2. ``tf.lite.Interpreter`` (Flex delegate)
    3. Fallback to Keras ``predict()`` for float32 model (if provided)

    Args:
        label: Human-readable model label for logging.
        model_path: Path to the ``.tflite`` file.
        is_int8: Whether the model expects INT8 input.
        float32_keras_model: Optional float32 Keras model to use as
            fallback when TFLite interpreter is unavailable.
        cqt_stats: Optional CQT distribution statistics for matching
            synthetic test inputs to training distribution.

    Returns:
        True if all test cases pass or test was skipped gracefully.
    """
    print(f"\n--- {label} Smoke Tests ---")

    interp = None
    tried_fallback = False

    try:
        from tflite_runtime.interpreter import Interpreter

        interp = Interpreter(
            model_path=str(model_path),
            experimental_delegates=[
                Interpreter.load_delegate("libtensorflowlite_flex.so")
            ],
        )
    except (ImportError, ValueError, OSError):
        try:
            interp = tf.lite.Interpreter(
                model_path=str(model_path),
                experimental_delegates=[
                    tf.lite.experimental.load_delegate(
                        "libtensorflowlite_flex.so"
                    )
                ],
            )
        except (ValueError, OSError, RuntimeError):
            tried_fallback = True

    smoke_cases = [
        ("C:maj", 0, "maj"),
        ("A:min", 9, "min"),
        ("D#:7", 3, "7"),
        ("D:7", 2, "7"),
    ]

    # ---- Keras fallback (float32 only) ----
    if tried_fallback:
        if not is_int8 and float32_keras_model is not None:
            print(
                "  Flex delegate unavailable — "
                "falling back to Keras model predict()"
            )
            all_ok = True
            for expected, root_idx, quality in smoke_cases:
                test_input = make_window(
                    make_cqt_template(root_idx, quality), 0.05
                )
                test_input = _apply_distribution_matching(test_input, cqt_stats, strength=0.8)
                test_input = test_input[np.newaxis]
                raw_output = float32_keras_model.predict(test_input, verbose=0)
                pred_idx = extract_chord_predictions(raw_output)[0]
                predicted = CHORD_VOCAB[pred_idx]
                if isinstance(raw_output, dict):
                    confidence = float(raw_output["chord_probs"][0, pred_idx])
                else:
                    confidence = float(raw_output[0, pred_idx])
                passed = predicted == expected
                if not passed:
                    all_ok = False
                print(
                    f"  {expected:<8} -> {predicted:<8} "
                    f"({confidence:.1%}) [{'PASS' if passed else 'FAIL'}]"
                )
            if all_ok:
                print(f"  All {label} smoke tests PASSED")
            else:
                print(f"  Some {label} smoke tests FAILED")
            return all_ok

        # INT8 or no float32 fallback — skip gracefully
        print(
            "  Flex delegate unavailable — "
            "skipping TFLite smoke test "
            "(will work on mobile with tensorflow-lite-select-tf-ops)"
        )
        return True

    if interp is None:
        return True

    # ---- TFLite interpreter path ----
    interp.allocate_tensors()
    input_details = interp.get_input_details()[0]
    output_details = interp.get_output_details()[0]

    if is_int8:
        in_scale, in_zp = input_details["quantization"]
        if in_scale == 0.0:
            in_scale = 1.0

    all_ok = True
    for expected, root_idx, quality in smoke_cases:
        test_float = make_window(
            make_cqt_template(root_idx, quality), 0.05
        )
        test_float = _apply_distribution_matching(test_float, cqt_stats, strength=0.8)
        test_float = test_float[np.newaxis].astype(np.float32)

        if is_int8:
            test_input = np.clip(
                np.round(test_float / in_scale + in_zp),
                -128, 127,
            ).astype(np.int8)
        else:
            test_input = test_float

        interp.set_tensor(input_details["index"], test_input)
        interp.invoke()
        raw = interp.get_tensor(output_details["index"])[0]

        if is_int8:
            out_scale, out_zp = output_details["quantization"]
            if out_scale != 0.0:
                raw = (raw.astype(np.float32) - out_zp) * out_scale
            else:
                raw = raw.astype(np.float32)

        top_idx = int(np.argmax(raw))
        predicted = CHORD_VOCAB[top_idx]
        confidence = float(raw[top_idx])
        passed = predicted == expected
        if not passed:
            all_ok = False
        print(
            f"  {expected:<8} -> {predicted:<8} "
            f"({confidence:.1%}) [{'PASS' if passed else 'FAIL'}]"
        )

    if all_ok:
        print(f"  All {label} smoke tests PASSED")
    else:
        print(f"  Some {label} smoke tests FAILED")
    return all_ok


def run_pipeline(
    guitarset_data_dir: str | Path | None = None,
    idmt_data_dir: str | Path | None = None,
    vst_data_dir: str | Path | None = None,
    youtube_data_dir: str | Path | None = None,
    damp_data_dir: str | Path | None = None,
    pseudo_data_dir: str | Path | None = None,
    jaah_data_dir: str | Path | None = None,
    guitar_techs_data_dir: str | Path | None = None,
    egset12_data_dir: str | Path | None = None,
    guitarset_loss_weight: float = 1.0,
    vst_loss_weight: float = 0.3,
    damp_loss_weight: float = 0.15,
    jaah_loss_weight: float = 1.0,
    guitar_techs_loss_weight: float = 1.0,
    egset12_loss_weight: float = 1.0,
    empirical_matrix_path: str | Path | None = None,
    temperature: float = 0.3,
    cqt_stats_path: str | Path | None = None,
    export_onnx: bool = False,
):
    """Run the full training pipeline with multi-source weighted data mixing.

    All available data from all configured sources is loaded, mixed, and
    trained with per-source loss weighting (sample_weight in Keras).

    Source weights (from PRIORITIES.md Commit 105):
      - GuitarSet (real):       1.0  (highest confidence, real recordings)
      - IDMT-SMT-Guitar:        1.0  (real recordings, good labels)
      - VST synthetic:          0.3  (lower confidence, synthetic audio)
      - DAMP-VPB:               0.15 (lowest confidence, heuristic labels — UNAVAILABLE)
      - YouTube crawl:          1.0  (real recordings, TFLite-filtered)
      - Pseudo-label:           same as vst_loss_weight (model-generated labels)
      - JAAH:                   1.0  (real recordings, expert annotations — audio separate)
      - Guitar-TECHS:           1.0  (real multi-player chords + techniques, MIDI ground truth)
      - EGSet12:                1.0  (real solo electric guitar, diverse styles)

    Args:
        guitarset_data_dir: Path to GuitarSet CQT data directory.
        idmt_data_dir: Path to IDMT-SMT-Guitar CQT data directory.
        vst_data_dir: Path to VST synthetic CQT data directory.
        youtube_data_dir: Path to YouTube crawl CQT data directory.
        damp_data_dir: Path to DAMP-VPB CQT data directory.
        pseudo_data_dir: Path to pseudo-labeled CQT data directory.
        jaah_data_dir: Path to JAAH CQT data directory (requires user-supplied audio).
        guitar_techs_data_dir: Path to Guitar-TECHS CQT data directory.
        egset12_data_dir: Path to EGSet12 CQT data directory.
        guitarset_loss_weight: Per-sample loss weight for GuitarSet (default 1.0).
        vst_loss_weight: Per-sample loss weight for VST synthetic (default 0.3).
        damp_loss_weight: Per-sample loss weight for DAMP-VPB (default 0.15).
        jaah_loss_weight: Per-sample loss weight for JAAH (default 1.0).
        guitar_techs_loss_weight: Per-sample loss weight for Guitar-TECHS (default 1.0).
        egset12_loss_weight: Per-sample loss weight for EGSet12 (default 1.0).
        empirical_matrix_path: Path to empirical transition matrix .npy (or None).
        temperature: Temperature τ for quality re-sampling (default 0.5).
                     τ < 1.0 boosts rare chord quality sampling via MT3 formula.
                     τ = 1.0 uses uniform sampling (neutral).
        cqt_stats_path: Path to .npz with CQT distribution statistics for
            synthetic-to-real domain gap matching (Commit 148 Phase 1b).
            If None, no distribution matching is applied.
    """
    _APP_DIR = Path(__file__).resolve().parent.parent / "app"
    _SCRIPTS_DIR = Path(__file__).resolve().parent

    # --- Load CQT statistics for distribution matching (Commit 148 Phase 1b) ---
    cqt_stats: dict | None = None
    if cqt_stats_path is not None:
        cqt_path = Path(cqt_stats_path)
        if cqt_path.exists():
            cqt_stats = dict(np.load(str(cqt_path)))
            print(f"  Loaded CQT distribution stats from {cqt_path} ({cqt_stats['n_samples']} real windows)")
        else:
            print(f"  [WARN] CQT stats not found: {cqt_path} — distribution matching disabled")

    # --- Load all dataset sources ---
    source_configs: list[tuple[Path, str, float]] = []
    real_data_dirs: list[Path] = []
    has_any_real_data = False

    if guitarset_data_dir is not None:
        gs_path = Path(guitarset_data_dir)
        if gs_path.exists():
            source_configs.append((gs_path, "GuitarSet", guitarset_loss_weight))
            real_data_dirs.append(gs_path)
            has_any_real_data = True
        else:
            print(f"  [WARN] GuitarSet data dir not found: {gs_path}")

    if idmt_data_dir is not None:
        idmt_path = Path(idmt_data_dir)
        if idmt_path.exists():
            source_configs.append((idmt_path, "IDMT-SMT-Guitar", 1.0))
            real_data_dirs.append(idmt_path)
            has_any_real_data = True
        else:
            print(f"  [WARN] IDMT-SMT-Guitar data dir not found: {idmt_path}")

    if vst_data_dir is not None:
        vst_path = Path(vst_data_dir)
        if vst_path.exists():
            source_configs.append((vst_path, "VST-Synthetic", vst_loss_weight))
        else:
            print(f"  [WARN] VST synthetic data dir not found: {vst_path}")

    if youtube_data_dir is not None:
        yt_path = Path(youtube_data_dir)
        if yt_path.exists():
            # YouTube crawl is 100% no-chord (N) — skip for training
            print(f"  [SKIP] YouTube-Crawl at {yt_path} — 100% N windows, skipping")
        else:
            print(f"  [WARN] YouTube crawl data dir not found: {yt_path}")

    if damp_data_dir is not None:
        damp_path = Path(damp_data_dir)
        if damp_path.exists():
            source_configs.append((damp_path, "DAMP-VPB", damp_loss_weight))
        else:
            print(f"  [WARN] DAMP-VPB data dir not found: {damp_path}")

    if pseudo_data_dir is not None:
        pseudo_path = Path(pseudo_data_dir)
        if pseudo_path.exists():
            source_configs.append((pseudo_path, "Pseudo-Label", vst_loss_weight))
        else:
            print(f"  [WARN] Pseudo-label data dir not found: {pseudo_path}")

    if jaah_data_dir is not None:
        jaah_path = Path(jaah_data_dir)
        if jaah_path.exists():
            source_configs.append((jaah_path, "JAAH", jaah_loss_weight))
            real_data_dirs.append(jaah_path)
            has_any_real_data = True
        else:
            print(f"  [WARN] JAAH data dir not found: {jaah_path}")

    if guitar_techs_data_dir is not None:
        gt_path = Path(guitar_techs_data_dir)
        if gt_path.exists():
            source_configs.append((gt_path, "Guitar-TECHS", guitar_techs_loss_weight))
            real_data_dirs.append(gt_path)
            has_any_real_data = True
        else:
            print(f"  [WARN] Guitar-TECHS data dir not found: {gt_path}")

    if egset12_data_dir is not None:
        eg_path = Path(egset12_data_dir)
        if eg_path.exists():
            source_configs.append((eg_path, "EGSet12", egset12_loss_weight))
            real_data_dirs.append(eg_path)
            has_any_real_data = True
        else:
            print(f"  [WARN] EGSet12 data dir not found: {eg_path}")

    # Load user-contributed data (if available)
    _data_dir = Path(__file__).resolve().parent.parent / "data"
    user_contributed_dir = _data_dir / "user_contributed"
    if user_contributed_dir.exists() and (user_contributed_dir / "processed" / "cqt").exists():
        source_configs.append((user_contributed_dir, "User-Contributed", 1.0))
        real_data_dirs.append(user_contributed_dir)
        has_any_real_data = True

    print(f"Loading {len(source_configs)} data source(s)...")
    features_list, labels_list, weights_list = load_datasets(source_configs)

    # Track which loaded sources are synthetic (data_dir not in real_data_dirs)
    _loaded_synth_flags: list[bool] = [
        config[0] not in real_data_dirs for config in source_configs
    ]
    # Find the VST source index (used later to include VST in Stage 1)
    _vst_loaded_idx: int | None = None
    for i, (_, name, _) in enumerate(source_configs):
        if "VST" in name.upper():
            _vst_loaded_idx = i
            break

    # --- Load GuitarSet test data (if available) ---
    test_X, test_y = np.array([]), np.array([])
    if guitarset_data_dir is not None:
        gs_path = Path(guitarset_data_dir)
        if gs_path.exists():
            try:
                test_X, test_y = load_guitarset_test(gs_path)
                test_y = np.array([mirex_label(int(y)) for y in test_y], dtype=np.int32)
            except (FileNotFoundError, ValueError) as e:
                print(f"  [WARN] Could not load GuitarSet test data: {e}")

    # --- Load EGSet12 eval data (if available) ---
    egset12_test_X, egset12_test_y = np.array([]), np.array([])
    if egset12_data_dir is not None:
        eg_path = Path(egset12_data_dir)
        if eg_path.exists():
            try:
                gs_test_path = Path(egset12_data_dir) / "processed" / "cqt"
                if gs_test_path.exists():
                    loaded_chunks = []
                    for npz_path in sorted(gs_test_path.glob("*.npz")):
                        data = np.load(npz_path)
                        split = str(data.get("split", b""))
                        if split != "test":
                            continue
                        if "features" in data and "labels" in data:
                            loaded_chunks.append((data["features"], data["labels"]))
                    if loaded_chunks:
                        egset12_test_X = np.concatenate([c[0] for c in loaded_chunks], axis=0)
                        egset12_test_y = np.concatenate([c[1] for c in loaded_chunks], axis=0)
                        egset12_test_y = np.array([mirex_label(int(y)) for y in egset12_test_y], dtype=np.int32)
                        print(f"  Loaded EGSet12 eval set: {len(egset12_test_X)} windows")
            except (FileNotFoundError, ValueError) as e:
                print(f"  [WARN] Could not load EGSet12 eval data: {e}")

    # --- Load empirical transition matrix ---
    transition_probs = None
    if empirical_matrix_path is not None:
        emp_path = Path(empirical_matrix_path)
        if emp_path.exists():
            matrix = np.load(str(emp_path))
            if matrix.shape == (NUM_CLASSES_MIREX, NUM_CLASSES_MIREX):
                transition_probs = matrix.sum(axis=1)
                if transition_probs.sum() > 0:
                    transition_probs = transition_probs / transition_probs.sum()
                print(f"  Loaded empirical transition matrix ({emp_path})")
            else:
                print(f"  [WARN] Matrix shape {matrix.shape} != ({NUM_CLASSES_MIREX},{NUM_CLASSES_MIREX}), ignored")
        else:
            print(f"  [WARN] Empirical matrix not found: {emp_path}")

    # --- Commit 148 Phase 1c: collect real N templates for escape hatch fix ---
    real_n_templates: list[np.ndarray] = []
    if real_data_dirs:
        real_n_templates = collect_real_n_templates(real_data_dirs)
        print(f"  Collected {len(real_n_templates)} real N-CQT templates for escape hatch fix")

    # --- Generate synthetic data ---
    # Estimate required samples BEFORE generation to avoid massive waste
    total_real = sum(len(f) for f in features_list)
    max_synthetic = total_real * 1 if total_real > 0 else 5000
    n_classes_277 = len(CHORD_INTERVALS) * N_CLASSES_PER_QUALITY + 1
    # Reserve ~20% for transition windows, rest for per-class generation
    target_per_class = max(10, int((max_synthetic * 0.8) / n_classes_277))
    target_transitions = min(max_synthetic * 2, n_classes_277 * 50)
    print(f"Generating synthetic dataset ({target_per_class} per class, {int(target_transitions)} transitions)...")
    synth_X, synth_y = generate_dataset(
        samples_per_class=target_per_class,
        transition_probs=transition_probs,
        cqt_stats=cqt_stats,
        real_n_templates=real_n_templates if real_n_templates else None,
    )
    p = np.random.permutation(len(synth_X))
    synth_X, synth_y = synth_X[p], synth_y[p]

    # --- Commit 148 Phase 1a: cap synthetic volume & reduce weight ---
    if len(synth_X) > max_synthetic:
        synth_X = synth_X[:max_synthetic]
        synth_y = synth_y[:max_synthetic]
        print(f"  Capped synthetic to {len(synth_X)} samples (weight=0.15)")
    else:
        print(f"  Generated {len(synth_X)} synthetic samples (weight=0.15)")

    # Generate synthetic recording IDs (one unique ID per sample — synthetic
    # windows are independent, no recording-level grouping needed)
    synth_rec_ids = np.array(
        [f"synthetic_{i}" for i in range(len(synth_X))], dtype=object
    )
    synth_weight = np.full(len(synth_X), 0.15, dtype=np.float32)
    features_list.append(synth_X)
    labels_list.append(synth_y)
    weights_list.append(synth_weight)
    recording_ids_list.append(synth_rec_ids)

    # Build synthetic-source flag for each entry in features_list.
    # VST / DAMP / Pseudo-Label are loaded but not in real_data_dirs → synthetic.
    # The generate_dataset output (last entry) is always synthetic.
    _synth_source_flags = _loaded_synth_flags + [True]

    # --- Mix all sources ---
    print("Mixing all dataset sources with per-source loss weighting...")
    dataset_sources = list(zip(features_list, labels_list, weights_list, recording_ids_list))
    X_all, y_all, sample_weights, source_ids, recording_ids = mix_datasets(dataset_sources)

    # Commit A: Map all labels from 277-class to 25-class MIREX vocabulary
    # Real .npz files still have 277-class labels, synthetic labels from
    # generate_dataset are generated as 277-class. Both must be mapped.
    y_all = np.array([mirex_label(int(y)) for y in y_all], dtype=np.int32)

    # --- Source-aware train / validation split (Phase 2a) ---
    # Separate by synthetic vs real using the source index flags.
    _synth_src_indices = {i for i, is_synth in enumerate(_synth_source_flags) if is_synth}
    synth_mask = np.array([sid in _synth_src_indices for sid in source_ids])
    real_mask = ~synth_mask

    # Further separate synthetic into VST, generated, and other (DAMP, Pseudo)
    _generated_idx = len(features_list) - 1
    _generated_mask = source_ids == _generated_idx
    if _vst_loaded_idx is not None:
        _vst_mask = source_ids == _vst_loaded_idx
    else:
        _vst_mask = np.zeros(len(source_ids), dtype=bool)
    _other_synth_mask = synth_mask & ~_vst_mask & ~_generated_mask

    X_real, y_real, w_real, rec_ids_real = (
        X_all[real_mask], y_all[real_mask], sample_weights[real_mask], recording_ids[real_mask]
    )
    X_vst, y_vst, w_vst, rec_ids_vst = (
        X_all[_vst_mask], y_all[_vst_mask], sample_weights[_vst_mask], recording_ids[_vst_mask]
    )
    X_generated, y_generated, w_generated, rec_ids_generated = (
        X_all[_generated_mask], y_all[_generated_mask], sample_weights[_generated_mask], recording_ids[_generated_mask]
    )

    _other_synth_count = _other_synth_mask.sum()
    if _other_synth_count > 0:
        print(f"  Other synthetic samples (ignored): {_other_synth_count}")

    print(f"  Real samples: {len(X_real)}, VST synthetic: {len(X_vst)}, Generated synthetic: {len(X_generated)}")

    # Real: 70/30 RECORDING-LEVEL split (honest cross-recording validation)
    # All windows from the same recording stay in the same split.
    from sklearn.model_selection import GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=42)
    # Use unique recording groups to split at recording level
    train_idx, val_idx = next(gss.split(X_real, y_real, groups=rec_ids_real))
    X_real_tr, X_real_val = X_real[train_idx], X_real[val_idx]
    y_real_tr, y_real_val = y_real[train_idx], y_real[val_idx]
    w_real_tr, w_real_val = w_real[train_idx], w_real[val_idx]
    # Log the recording-level split
    train_recs = set(rec_ids_real[train_idx])
    val_recs = set(rec_ids_real[val_idx])
    print(f"  Recording-level 70/30 split: {len(train_recs)} train recordings, "
          f"{len(val_recs)} val recordings")

    # VST: use entirely for training with domain-bridge weight 0.3
    if len(X_vst) > 0:
        w_vst = np.full(len(X_vst), 0.3, dtype=np.float32)

    # Commit 148 Phase 2d: Stash real train for two-phase curriculum
    X_real_tr_s1, y_real_tr_s1, w_real_tr_s1 = X_real_tr.copy(), y_real_tr.copy(), w_real_tr.copy()

    # Stage 1: real + VST training (no generated synthetic)
    X_train = X_real_tr.copy()
    y_train = y_real_tr.copy()
    w_train = w_real_tr.copy()
    train_real_mask = np.ones(len(X_real_tr), dtype=bool)
    if len(X_vst) > 0:
        X_train = np.concatenate([X_train, X_vst])
        y_train = np.concatenate([y_train, y_vst])
        w_train = np.concatenate([w_train, w_vst])
        train_real_mask = np.concatenate([
            np.ones(len(X_real_tr), dtype=bool),
            np.zeros(len(X_vst), dtype=bool),
        ])
    X_val = X_real_val.copy()
    y_val = y_real_val.copy()
    w_val = w_real_val.copy()
    val_source_tags = np.ones(len(X_val), dtype=np.int32)  # 1 = real (all val is real)

    # Shuffle validation set
    val_perm = np.random.permutation(len(X_val))
    X_val, y_val, w_val, val_source_tags = X_val[val_perm], y_val[val_perm], w_val[val_perm], val_source_tags[val_perm]

    # Commit 148 Phase 2b/2c: Convert validation labels to one-hot
    y_val_onehot = tf.keras.utils.to_categorical(y_val, NUM_CLASSES_MIREX).astype(np.float32)

    # Commit 148 Phase 3b: Multi-task validation labels (dict format)
    y_val_root = tf.keras.utils.to_categorical(
        derive_root_labels(y_val), N_ROOTS
    ).astype(np.float32)
    y_val_presence = derive_presence_labels(y_val).reshape(-1, 1)
    y_val_dict = {
        "chord_probs": y_val_onehot,
        "root_probs": y_val_root,
        "presence": y_val_presence,
    }

    print(f"  Stage 1 real+VST: {len(X_real_tr)} real + {len(X_vst)} VST "
          f"= {len(X_train)} total ({100 * len(X_real_tr) / max(len(X_train), 1):.0f}% real)")
    print(f"  Validation (real only): {len(X_val)} samples")

    # Commit 148 Phase 2d: Build Stage 2 training data (real + generated supplement)
    _s2_synth_cap = max(1, int(len(X_real_tr_s1) * 0.30))
    if len(X_generated) > _s2_synth_cap:
        _s2_perm = np.random.RandomState(42).permutation(len(X_generated))
        X_generated_s2 = X_generated[_s2_perm[:_s2_synth_cap]]
        y_generated_s2 = y_generated[_s2_perm[:_s2_synth_cap]]
        w_generated_s2 = w_generated[_s2_perm[:_s2_synth_cap]]
    else:
        X_generated_s2, y_generated_s2, w_generated_s2 = X_generated, y_generated, w_generated
    X_train_s2 = np.concatenate([X_real_tr_s1, X_generated_s2])
    y_train_s2 = np.concatenate([y_real_tr_s1, y_generated_s2])
    w_train_s2 = np.concatenate([w_real_tr_s1, w_generated_s2])
    train_real_mask_s2 = np.concatenate([
        np.ones(len(X_real_tr_s1), dtype=bool),
        np.zeros(len(X_generated_s2), dtype=bool),
    ])
    print(f"  Stage 2 real-supplement: {len(X_real_tr_s1)} real + {len(X_generated_s2)} generated "
          f"= {len(X_train_s2)} total ({100 * len(X_real_tr_s1) / max(len(X_train_s2), 1):.0f}% real)")

    # Compute inverse-frequency class weights and fold into sample weights.
    print("\nComputing & applying balanced class weights...")
    _class_counts = np.bincount(y_real_tr.astype(int), minlength=NUM_CLASSES_MIREX)
    _class_counts = np.maximum(_class_counts, 1)
    _median_count = np.median(_class_counts[_class_counts > 0])
    _class_weight_arr = _median_count / _class_counts.astype(np.float32)
    _class_weight_arr = np.clip(_class_weight_arr, 0.5, 5.0)
    print(f"  Class weight range: [{_class_weight_arr.min():.2f}, {_class_weight_arr.max():.2f}]")
    for ci in np.argsort(_class_counts)[:5]:
        print(f"    {MIREX_VOCAB[ci]:25s}: count={_class_counts[ci]:4d}, weight={_class_weight_arr[ci]:.2f}")
    for ci in np.argsort(-_class_counts)[:3]:
        print(f"    {MIREX_VOCAB[ci]:25s}: count={_class_counts[ci]:4d}, weight={_class_weight_arr[ci]:.2f}")
    # Fold into existing sample weights (Stage 1 + Stage 2)
    w_real_tr *= _class_weight_arr[y_real_tr.astype(int)]
    # Note: w_real_tr_s1 was already copied before this — need to re-build
    # Stage 2 data with weighted sample weights.
    w_real_tr_s1 = w_real_tr.copy()
    # Rebuild Stage 2 training data with updated weights
    w_train_s2 = np.concatenate([w_real_tr_s1, w_generated_s2])

    # --- Build model ---
    model = build_multi_task_model()

    # --- Build shared test callbacks (appended to all stages) ---
    test_callbacks: list[tf.keras.callbacks.Callback] = []
    if has_any_real_data and len(test_X) > 0:
        test_callbacks.append(GuitarSetTestCallback(test_X, test_y))
    if len(egset12_test_X) > 0:
        test_callbacks.append(EGSet12TestCallback(egset12_test_X, egset12_test_y))

    # ===== Stage 0: Synthetic pre-training (epochs 1-30) =====
    # Pre-train on abundant synthetic data (VST + generated) to learn CQT→chord
    # mapping from clean templates, then adapt to real audio in later stages.
    PRETRAIN_EPOCHS = 30
    _has_any_synth = len(X_vst) + len(X_generated) > 0
    if _has_any_synth:
        _synth_X_all = np.concatenate([X_vst, X_generated]) if len(X_vst) > 0 else X_generated
        _synth_y_all = np.concatenate([y_vst, y_generated]) if len(X_vst) > 0 else y_generated
        _synth_w_all = np.concatenate([
            np.full(len(X_vst), 1.0, dtype=np.float32),
            np.full(len(X_generated), 1.0, dtype=np.float32),
        ]) if len(X_vst) > 0 else np.full(len(X_generated), 1.0, dtype=np.float32)
        _synth_perm = np.random.permutation(len(_synth_X_all))
        _synth_X_all, _synth_y_all, _synth_w_all = (
            _synth_X_all[_synth_perm], _synth_y_all[_synth_perm], _synth_w_all[_synth_perm]
        )
        print(f"\n{'=' * 60}")
        print(f"  Stage 0: Synthetic pre-training ({PRETRAIN_EPOCHS} epochs)")
        print(f"  Data: {len(_synth_X_all)} synthetic windows (VST + generated)")
        print(f"  Cosine LR: 3e-3 -> 1e-5 over {PRETRAIN_EPOCHS} epochs")
        print(f"{'=' * 60}")
        _steps_pretrain = int(np.ceil(len(_synth_X_all) / 64))
        _lr_pretrain = tf.keras.optimizers.schedules.CosineDecay(
            initial_learning_rate=3e-3,
            decay_steps=PRETRAIN_EPOCHS * _steps_pretrain,
            alpha=1e-5 / 3e-3,
        )
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=_lr_pretrain, weight_decay=1e-4, clipnorm=1.0),
            loss={
                "chord_probs": tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.0),
                "root_probs": tf.keras.losses.CategoricalCrossentropy(),
                "presence": tf.keras.losses.BinaryCrossentropy(),
            },
            loss_weights={
                "chord_probs": CHORD_LOSS_WEIGHT,
                "root_probs": ROOT_LOSS_WEIGHT * 0.5,
                "presence": PRESENCE_LOSS_WEIGHT * 0.5,
            },
            metrics={
                "chord_probs": tf.keras.metrics.CategoricalAccuracy(name="accuracy"),
                "root_probs": tf.keras.metrics.CategoricalAccuracy(name="root_accuracy"),
                "presence": tf.keras.metrics.BinaryAccuracy(name="presence_acc"),
            },
        )
        _synth_generator = AugmentedDataGenerator(
            _synth_X_all, _synth_y_all, _synth_w_all,
            batch_size=64,
            p_pitch_shift=0.3, pitch_range=1,
            p_time_stretch=0.1, stretch_range=(0.95, 1.05),
            noise_std=0.03, shuffle=True, temperature=1.0,
            real_mask=np.ones(len(_synth_X_all), dtype=bool),
            multi_task=True,
        )
        model.fit(
            x=_synth_generator,
            epochs=PRETRAIN_EPOCHS,
            callbacks=test_callbacks,
            verbose=1,
        )
    else:
        print("  [SKIP] No synthetic data — skipping Stage 0 pre-training")

    # ===== Stage 1: Real+VST training =====
    _s1_start = 0 if not _has_any_synth else PRETRAIN_EPOCHS
    _s1_end = PRETRAIN_EPOCHS + 20
    print(f"\n{'=' * 60}")
    print(f"  Stage 1: Real+VST training (epochs {_s1_start+1}-{_s1_end})")
    print(f"  Cosine LR: {INITIAL_LR} -> {MIN_LR} over {FIRST_DECAY_EPOCHS} epochs")
    print(f"  Mixup: p=0.3, alpha=0.2, label_smoothing=0.0")
    print(f"  Multi-task: chord(λ={CHORD_LOSS_WEIGHT}) + root(λ={ROOT_LOSS_WEIGHT}) + presence(λ={PRESENCE_LOSS_WEIGHT})")
    print(f"{'=' * 60}")

    steps_per_epoch_s1 = int(np.ceil(len(X_train) / 64))
    lr_schedule_s1 = tf.keras.optimizers.schedules.CosineDecayRestarts(
        initial_learning_rate=INITIAL_LR,
        first_decay_steps=FIRST_DECAY_EPOCHS * steps_per_epoch_s1,
        t_mul=2.0,
        m_mul=0.5,
        alpha=MIN_LR / INITIAL_LR,
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=lr_schedule_s1, weight_decay=1e-4, clipnorm=1.0),
        loss={
            "chord_probs": tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.0),
            "root_probs": tf.keras.losses.CategoricalCrossentropy(),
            "presence": tf.keras.losses.BinaryCrossentropy(),
        },
        loss_weights={
            "chord_probs": CHORD_LOSS_WEIGHT,
            "root_probs": ROOT_LOSS_WEIGHT * 0.5,
            "presence": PRESENCE_LOSS_WEIGHT * 0.5,
        },
        metrics={
            "chord_probs": tf.keras.metrics.CategoricalAccuracy(name="accuracy"),
            "root_probs": tf.keras.metrics.CategoricalAccuracy(name="root_accuracy"),
            "presence": tf.keras.metrics.BinaryAccuracy(name="presence_acc"),
        },
    )

    # No synthetic validation data — val is purely real (Phase 2 fix)
    X_synth_val = np.zeros((0, WINDOW, FEATURE_DIM), dtype=np.float32)
    y_synth_val = np.zeros(0, dtype=np.int32)

    callbacks_s1: list[tf.keras.callbacks.Callback] = [
        DualValidationLogger(
            X_real_val=X_real_val, y_real_val=y_real_val,
            X_synth_val=X_synth_val, y_synth_val=y_synth_val,
            filename=str(_SCRIPTS_DIR / "training_log.csv"),
            plot_output_dir=_SCRIPTS_DIR,
            plot_every_n=5,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_accuracy_real",
            patience=10,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(_APP_DIR / "chord_model_best.keras"),
            monitor="val_accuracy_real",
            save_best_only=True,
            verbose=1,
        ),
        TwoPhaseCallback(switch_epoch=_s1_end),
    ]
    callbacks_s1.extend(test_callbacks)

    train_generator_s1 = AugmentedDataGenerator(
        X_train, y_train, w_train,
        batch_size=64,
        p_pitch_shift=0.5, pitch_range=2,
        p_time_stretch=0.3, stretch_range=(0.9, 1.1),
        noise_std=0.05, shuffle=True, temperature=temperature,
        real_mask=train_real_mask, multi_task=True,
    )

    fit_kwargs_s1 = dict(
        x=train_generator_s1,
        epochs=_s1_end,
        initial_epoch=_s1_start,
        validation_data=(X_val, y_val_dict),
        callbacks=callbacks_s1,
        verbose=1,
    )
    # Class weights are already folded into sample weights; no separate class_weight dict needed.

    history_s1 = model.fit(**fit_kwargs_s1)

    # ===== Stage 2: Real-heavy fine-tuning =====
    _s2_start = _s1_end
    _s2_end = _s1_end + 40
    print(f"\n{'=' * 60}")
    print(f"  Stage 2: Real-heavy fine-tuning (epochs {_s2_start+1}-{_s2_end})")
    print(f"  Cosine LR: 1e-4 -> 1e-5 over 10 epochs, no restart")
    print(f"{'=' * 60}")

    # model is reused from Stage 1 (no need to reload — avoids stale checkpoint / Keras 3 compat issues)
    print(f"  Reusing model from Stage 1 (epoch {_s1_end}). Architecture: {model.input_shape} -> 25-class multi-task")

    steps_per_epoch_s2 = int(np.ceil(len(X_train_s2) / 64))
    total_steps_s2 = (_s2_end - _s2_start) * steps_per_epoch_s2  # 40 epochs
    lr_schedule_s2 = tf.keras.optimizers.schedules.CosineDecay(
        initial_learning_rate=1e-4,
        decay_steps=total_steps_s2,
        alpha=1e-5 / 1e-4,
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=lr_schedule_s2, weight_decay=1e-4, clipnorm=1.0),
        loss={
            "chord_probs": tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.0),
            "root_probs": tf.keras.losses.CategoricalCrossentropy(),
            "presence": tf.keras.losses.BinaryCrossentropy(),
        },
        loss_weights={
            "chord_probs": CHORD_LOSS_WEIGHT,
            "root_probs": ROOT_LOSS_WEIGHT * 0.5,
            "presence": PRESENCE_LOSS_WEIGHT * 0.5,
        },
        metrics={
            "chord_probs": tf.keras.metrics.CategoricalAccuracy(name="accuracy"),
            "root_probs": tf.keras.metrics.CategoricalAccuracy(name="root_accuracy"),
            "presence": tf.keras.metrics.BinaryAccuracy(name="presence_acc"),
        },
    )

    callbacks_s2: list[tf.keras.callbacks.Callback] = [
        DualValidationLogger(
            X_real_val=X_real_val, y_real_val=y_real_val,
            X_synth_val=X_synth_val, y_synth_val=y_synth_val,
            filename=str(_SCRIPTS_DIR / "training_log.csv"),
            append=True,
            plot_output_dir=_SCRIPTS_DIR,
            plot_every_n=5,
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_accuracy_real",
            patience=10,
            restore_best_weights=True,
            verbose=1,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(_APP_DIR / "chord_model_stage2_best.keras"),
            monitor="val_accuracy_real",
            save_best_only=True,
            verbose=1,
        ),
    ]
    callbacks_s2.extend(test_callbacks)

    train_generator_s2 = AugmentedDataGenerator(
        X_train_s2, y_train_s2, w_train_s2,
        batch_size=64,
        p_pitch_shift=0.5, pitch_range=2,
        p_time_stretch=0.3, stretch_range=(0.9, 1.1),
        noise_std=0.05, shuffle=True, temperature=temperature,
        real_mask=train_real_mask_s2, multi_task=True,
    )

    # Gradual curriculum transition: smooth from 100% real (S1 end) to 92% real (S2) over 10 epochs
    _s1_real_pct = len(X_real_tr_s1) / max(len(X_train), 1)
    callbacks_s2.append(GradualTransitionCallback(
        generator=train_generator_s2,
        start_ratio=_s1_real_pct,
        target_ratio=0.92,
        transition_epochs=10,
        start_epoch=_s1_end,
    ))

    fit_kwargs_s2 = dict(
        x=train_generator_s2,
        epochs=_s2_end,
        initial_epoch=_s2_start,
        validation_data=(X_val, y_val_dict),
        callbacks=callbacks_s2,
        verbose=1,
    )
    # Class weights are already folded into sample weights; no separate class_weight dict needed.

    history_s2 = model.fit(**fit_kwargs_s2)

    # Merge histories for post-training evaluation
    merged_history: dict[str, list[float]] = {}
    for k in history_s1.history:
        merged_history[k] = history_s1.history[k] + history_s2.history.get(k, [])
    # Add keys unique to s2
    for k in history_s2.history:
        if k not in merged_history:
            merged_history[k] = [None] * len(history_s1.history[k]) + history_s2.history[k]
    history = type("History", (), {"history": merged_history})()

    # Try chord_probs accuracy first (multi-task), fall back to accuracy (single-task)
    best_val_acc = max(
        merged_history.get("val_chord_probs_accuracy", []),
        default=max(merged_history.get("val_accuracy", [0.0])),
    )
    print(f"\nTraining completed. Best val_accuracy: {best_val_acc:.1%}")

    # --- Per-group validation accuracy (Commit 98d) ---
    print("\n--- Per-Group Validation Accuracy ---")
    y_output = model.predict(X_val, verbose=0)
    y_pred = extract_chord_predictions(y_output)
    y_pred_raw = np.argmax(y_output["chord_probs"], axis=1) if isinstance(y_output, dict) else np.argmax(y_output, axis=1)
    grouped_acc = compute_grouped_accuracy(y_val, y_pred)
    for group, acc in sorted(grouped_acc.items()):
        pct = acc * 100
        arrow = ""
        if group == "overall":
            arrow = f"  (best val: {best_val_acc:.1%})"
        elif group == "extended":
            arrow = "  ← target +3% improvement"
        print(f"  {group:20s}: {pct:5.1f}%{arrow}")

    # --- Per-source validation accuracy (Phase 2b) ---
    print("\n--- Per-Source Validation Accuracy ---")
    real_val_mask = val_source_tags == 1
    synth_val_mask = val_source_tags == 0
    synth_acc = 0.0
    if real_val_mask.sum() > 0:
        real_acc = float(np.mean(y_pred[real_val_mask] == y_val[real_val_mask]))
        print(f"  Real-world val:   {real_acc:.1%}  ({real_val_mask.sum()} samples)")
    if synth_val_mask.sum() > 0:
        # Synthetic val uses raw argmax (no N-override — synthetic N is clean)
        synth_acc = float(np.mean(y_pred_raw[synth_val_mask] == y_val[synth_val_mask]))
        print(f"  Synthetic val:    {synth_acc:.1%}  ({synth_val_mask.sum()} samples)")
    real_acc_val = float(np.mean(y_pred[real_val_mask] == y_val[real_val_mask])) if real_val_mask.sum() > 0 else 0.0
    domain_gap = synth_acc - real_acc_val
    print(f"  Domain gap:       {domain_gap:.1%}  (synthetic - real)")

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
    if has_any_real_data and len(test_X) > 0:
        print("\n--- GuitarSet Test Set (Player 05) ---")
        test_probs = model.predict(test_X, verbose=0)
        test_pred = extract_chord_predictions(test_probs)
        test_acc = np.mean(test_pred == test_y)
        print(f"  Root accuracy on GuitarSet test: {test_acc:.1%}")
        test_grouped = compute_grouped_accuracy(test_y, test_pred)
        for group, acc in sorted(test_grouped.items()):
            print(f"  {group:20s}: {acc*100:5.1f}%")

    # ---- Record float32 baseline metrics for QAT comparison ----
    float32_model = model
    float32_val_pred = y_pred  # already computed from per-group validation
    float32_val_acc = float(np.mean(float32_val_pred == y_val))
    float32_test_acc = float(test_acc) if has_any_real_data and len(test_X) > 0 else None

    # =================================================================
    # QAT Phase (Commit 106): Quantization-Aware Training
    # =================================================================
    qat_model: tf.keras.Model | None = None
    qat_val_acc: float | None = None
    qat_test_acc: float | None = None

    if _HAS_TFMOT:
        print("\n" + "=" * 60)
        print("  QAT Phase (Commit 106): Quantization-Aware Training")
        print("=" * 60)
        try:
            # Create a fresh data generator for QAT fine-tuning
            # using milder augmentation since the model has already converged.
            qat_generator = AugmentedDataGenerator(
                X_train, y_train, w_train,
                batch_size=64,
                p_pitch_shift=0.3,
                pitch_range=1,
                p_time_stretch=0.1,
                stretch_range=(0.95, 1.05),
                noise_std=0.03,
                shuffle=True,
                temperature=temperature,
                real_mask=train_real_mask,
                multi_task=True,
            )

            print(
                f"  Applying QAT wrapper to float32 model "
                f"({QAT_EPOCHS} epochs, LR={QAT_LEARNING_RATE})..."
            )
            qat_model = apply_qat(float32_model)

            qat_model.compile(
                optimizer=tf.keras.optimizers.Adam(learning_rate=QAT_LEARNING_RATE),
                loss={
                    "chord_probs": tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.0),
                    "root_probs": tf.keras.losses.CategoricalCrossentropy(),
                    "presence": tf.keras.losses.BinaryCrossentropy(),
                },
                loss_weights={"chord_probs": 1.0, "root_probs": 0.1, "presence": 0.05},
                metrics={"chord_probs": "accuracy", "root_probs": "accuracy", "presence": "accuracy"},
            )

            qat_callbacks = [
                tf.keras.callbacks.CSVLogger(
                    filename=str(
                        Path(__file__).resolve().parent / "training_log_qat.csv"
                    ),
                ),
            ]

            qat_history = qat_model.fit(
                x=qat_generator,
                epochs=QAT_EPOCHS,
                validation_data=(X_val, y_val_dict),
                callbacks=qat_callbacks,
                verbose=1,
            )

            # Evaluate QAT model on validation set
            qat_output = qat_model.predict(X_val, verbose=0)
            qat_val_pred = extract_chord_predictions(qat_output)
            qat_val_acc = float(np.mean(qat_val_pred == y_val))
            print(
                f"\n  QAT val accuracy: {qat_val_acc:.2%}  "
                f"(float32 baseline: {float32_val_acc:.2%})"
            )

            # Evaluate QAT model on GuitarSet test (if available)
            if has_any_real_data and len(test_X) > 0:
                qat_test_output = qat_model.predict(test_X, verbose=0)
                qat_test_pred = extract_chord_predictions(qat_test_output)
                qat_test_acc = float(np.mean(qat_test_pred == test_y))
                qat_deg = float32_test_acc - qat_test_acc if float32_test_acc is not None else 0.0
                print(
                    f"  QAT GuitarSet test: {qat_test_acc:.2%}  "
                    f"(float32 baseline: {float32_test_acc:.2%}, "
                    f"degradation: {qat_deg:.2%})"
                )

            # Save QAT Keras model (requires quantize_scope for reloading)
            qat_keras_path = _APP_DIR / "chord_model_qat.keras"
            with tfmot.quantization.keras.quantize_scope():
                qat_model.save(str(qat_keras_path))
            print(
                f"  Saved QAT Keras model to {qat_keras_path} "
                f"({qat_keras_path.stat().st_size / 1024 / 1024:.1f} MB)"
            )

        except Exception as exc:
            print(f"  [WARN] QAT phase failed: {exc}")
            print("  [WARN] INT8 QAT unavailable — using FP16 dynamic quantization instead")
            print("  Continuing with float32-only TFLite conversion...")
            traceback.print_exc()
            qat_model = None
    else:
        print(
            "\n  [SKIP] QAT phase: tensorflow_model_optimization not available. "
            "Install with:  pip install tensorflow-model-optimization"
        )

    # =================================================================
    # Save float32 model assets
    # =================================================================
    print("\nSaving float32 model assets...")

    weights_path = _APP_DIR / "chord_model.weights.h5"
    float32_model.save_weights(str(weights_path))
    print(f"  Keras weights -> {weights_path}  (for attention visualization)")

    keras_path = _APP_DIR / "chord_model.keras"
    float32_model.save(str(keras_path))
    print(
        f"  Keras model   -> {keras_path}  "
        f"({keras_path.stat().st_size / 1024 / 1024:.1f} MB)"
    )

    # =================================================================
    # 1.  Float32 model -> Dynamic Range TFLite  (baseline, Commit 99)
    # =================================================================
    print("\nConverting float32 model to TFLite (dynamic range quantization)...")

    # For multi-output models, TFLite only supports tensor outputs.
    # Create a wrapper that extracts chord_probs head only.
    is_multi_output = hasattr(float32_model, 'output_names') and isinstance(float32_model.output, dict)

    if is_multi_output:
        print("  Multi-output model: exporting chord_probs head only for TFLite")
        chord_probs_tensor = float32_model.output["chord_probs"]
        export_model = tf.keras.Model(inputs=float32_model.input, outputs=chord_probs_tensor)
    else:
        export_model = float32_model

    @tf.function(
        input_signature=[
            tf.TensorSpec(shape=[None, WINDOW, FEATURE_DIM], dtype=tf.float32)
        ]
    )
    def run_model_fn(input_tensor):
        return export_model(input_tensor, training=False)

    concrete_func = run_model_fn.get_concrete_function()

    converter = tf.lite.TFLiteConverter.from_concrete_functions([concrete_func])
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.target_spec.supported_ops = [
        tf.lite.OpsSet.TFLITE_BUILTINS,
        tf.lite.OpsSet.SELECT_TF_OPS,
    ]

    float32_tflite_size: float | None = None
    try:
        tflite_float32 = converter.convert()
        tflite_float32_path = _APP_DIR / "chord_model.tflite"
        with open(tflite_float32_path, "wb") as f:
            f.write(tflite_float32)
        float32_tflite_size = len(tflite_float32) / 1024
        print(
            f"  Saved -> {tflite_float32_path}  "
            f"({float32_tflite_size:.1f} KB)"
        )
    except Exception as e:
        print(f"  [WARN] Float32 TFLite conversion failed: {e}")

    # =================================================================
    # 2.  QAT model -> INT8 TFLite  (Commit 106)
    # =================================================================
    qat_int8_size: float | None = None
    if qat_model is not None and len(X_val) > 0:
        print(
            "\nConverting QAT model to INT8 TFLite "
            "(full integer quantization with representative dataset)..."
        )
        try:
            qat_tflite_path = _APP_DIR / "chord_model_qat_int8.tflite"
            qat_int8_bytes = convert_to_int8_tflite(
                qat_model,
                X_val,
                qat_tflite_path,
            )
            qat_int8_size = len(qat_int8_bytes) / 1024
            if float32_tflite_size and float32_tflite_size > 0:
                reduction_pct = (
                    (1 - qat_int8_size / float32_tflite_size) * 100
                )
                print(
                    f"  INT8 is {qat_int8_size:.1f} KB  "
                    f"({reduction_pct:.0f}% smaller than float32 TFLite)"
                )
        except Exception as e:
            print(f"  [WARN] INT8 TFLite conversion failed: {e}")
            print("  [WARN] INT8 QAT unavailable — using FP16 dynamic quantization instead")
    else:
        print(
            "\n  [SKIP] INT8 TFLite conversion "
            "(no QAT model or no validation data)"
        )

    # =================================================================
    # 2b. ONNX export for web inference (Commit A3.1)
    # =================================================================
    if export_onnx:
        print("\nExporting ONNX model for web inference...")
        onnx_path = _APP_DIR / "chord_model.onnx"
        convert_to_onnx(export_model, onnx_path)

    # =================================================================
    # 3.  Accuracy & size comparison
    # =================================================================
    if qat_val_acc is not None:
        print("\n" + "-" * 60)
        print("  Quantization Accuracy & Size Comparison")
        print("-" * 60)

        val_deg = float32_val_acc - qat_val_acc
        val_pass = val_deg < 0.03
        print(
            f"  Validation accuracy:  "
            f"float32={float32_val_acc:.2%}, "
            f"QAT={qat_val_acc:.2%}  "
            f"degradation={val_deg:.2%}  "
            f"{'✓' if val_pass else '✗'} (target <3%)"
        )

        if float32_test_acc is not None and qat_test_acc is not None:
            test_deg = float32_test_acc - qat_test_acc
            test_pass = test_deg < 0.03
            print(
                f"  GuitarSet test:       "
                f"float32={float32_test_acc:.2%}, "
                f"QAT={qat_test_acc:.2%}  "
                f"degradation={test_deg:.2%}  "
                f"{'✓' if test_pass else '✗'} (target <3%)"
            )

        if float32_tflite_size is not None and qat_int8_size is not None:
            print(
                f"  TFLite model size:    "
                f"float32={float32_tflite_size:.1f} KB, "
                f"INT8={qat_int8_size:.1f} KB"
            )
            size_pass = qat_int8_size < 500
            print(
                f"  INT8 < 500 KB:         "
                f"{'✓' if size_pass else '✗'}"
            )
        print("-" * 60)

    # =================================================================
    # 4.  Smoke Tests on both TFLite models
    # =================================================================
    tflite_models_for_test = []
    float32_path = _APP_DIR / "chord_model.tflite"
    if float32_path.exists():
        tflite_models_for_test.append(
            ("Float32 TFLite", float32_path, False)
        )
    qat_int8_path = _APP_DIR / "chord_model_qat_int8.tflite"
    if qat_int8_path.exists():
        tflite_models_for_test.append(
            ("INT8 TFLite", qat_int8_path, True)
        )

    all_smoke_passed = all(
        _run_tflite_smoke_test(
            label=label,
            model_path=path,
            is_int8=is_int8,
            float32_keras_model=float32_model if not is_int8 else None,
            cqt_stats=cqt_stats,
        )
        for label, path, is_int8 in tflite_models_for_test
    )

    if all_smoke_passed:
        print("\nAll TFLite smoke tests PASSED")
    else:
        print("\nSome TFLite smoke tests FAILED")


def run_qat_only(
    guitarset_data_dir: str | Path | None = None,
    idmt_data_dir: str | Path | None = None,
    vst_data_dir: str | Path | None = None,
    youtube_data_dir: str | Path | None = None,
    damp_data_dir: str | Path | None = None,
    pseudo_data_dir: str | Path | None = None,
    jaah_data_dir: str | Path | None = None,
    guitar_techs_data_dir: str | Path | None = None,
    egset12_data_dir: str | Path | None = None,
    guitarset_loss_weight: float = 1.0,
    vst_loss_weight: float = 0.3,
    damp_loss_weight: float = 0.15,
    jaah_loss_weight: float = 1.0,
    guitar_techs_loss_weight: float = 1.0,
    egset12_loss_weight: float = 1.0,
    empirical_matrix_path: str | Path | None = None,
    temperature: float = 0.3,
    cqt_stats_path: str | Path | None = None,
):
    """QAT-only: load data + best model, apply QAT, fine-tune, convert to INT8."""
    _APP_DIR = Path(__file__).resolve().parent.parent / "app"
    _SCRIPTS_DIR = Path(__file__).resolve().parent

    print("=" * 60)
    print("  QAT-Only Pipeline (Commit 106)")
    print("=" * 60)

    # ---- Load data sources ----
    source_configs: list[tuple[Path, str, float]] = []
    has_any_real_data = False

    for name, path, weight in [
        ("GuitarSet", guitarset_data_dir, guitarset_loss_weight),
        ("IDMT-SMT-Guitar", idmt_data_dir, 1.0),
        ("VST-Synthetic", vst_data_dir, vst_loss_weight),
        ("YouTube-Crawl", youtube_data_dir, 1.0),
        ("DAMP-VPB", damp_data_dir, damp_loss_weight),
        ("Pseudo-Label", pseudo_data_dir, vst_loss_weight),
        ("JAAH", jaah_data_dir, jaah_loss_weight),
        ("Guitar-TECHS", guitar_techs_data_dir, guitar_techs_loss_weight),
        ("EGSet12", egset12_data_dir, egset12_loss_weight),
    ]:
        if path is not None:
            p = Path(path)
            if p.exists():
                source_configs.append((p, name, weight))
                if name != "VST-Synthetic":
                    has_any_real_data = True
            else:
                print(f"  [WARN] {name} data dir not found: {p}")

    print(f"Loading {len(source_configs)} data source(s)...")
    features_list, labels_list, weights_list, _ = load_datasets(source_configs)

    # GuitarSet test data
    test_X, test_y = np.array([]), np.array([])
    if guitarset_data_dir is not None:
        gs_path = Path(guitarset_data_dir)
        if gs_path.exists():
            try:
                test_X, test_y = load_guitarset_test(gs_path)
                test_y = np.array([mirex_label(int(y)) for y in test_y], dtype=np.int32)
            except (FileNotFoundError, ValueError) as e:
                print(f"  [WARN] GuitarSet test: {e}")

    egset12_test_X, egset12_test_y = np.array([]), np.array([])
    if egset12_data_dir is not None:
        try:
            eg_path = Path(egset12_data_dir) / "processed" / "cqt"
            if eg_path.exists():
                loaded_chunks = []
                for npz_path in sorted(eg_path.glob("*.npz")):
                    data = np.load(npz_path)
                    split = str(data.get("split", b""))
                    if split != "test":
                        continue
                    if "features" in data and "labels" in data:
                        loaded_chunks.append((data["features"], data["labels"]))
                if loaded_chunks:
                    egset12_test_X = np.concatenate([c[0] for c in loaded_chunks], axis=0)
                    egset12_test_y = np.concatenate([c[1] for c in loaded_chunks], axis=0)
                    egset12_test_y = np.array([mirex_label(int(y)) for y in egset12_test_y], dtype=np.int32)
                    print(f"  Loaded EGSet12 eval set: {len(egset12_test_X)} windows (test split only)")
        except (FileNotFoundError, ValueError) as e:
            print(f"  [WARN] EGSet12 eval: {e}")

    # Empirical transition matrix
    transition_probs = None
    if empirical_matrix_path is not None:
        emp_path = Path(empirical_matrix_path)
        if emp_path.exists():
            matrix = np.load(str(emp_path))
            if matrix.shape == (NUM_CLASSES_MIREX, NUM_CLASSES_MIREX):
                transition_probs = matrix.sum(axis=1)
                if transition_probs.sum() > 0:
                    transition_probs = transition_probs / transition_probs.sum()
                print(f"  Loaded empirical matrix ({emp_path})")
            else:
                print(f"  [WARN] Matrix shape {matrix.shape}, ignored")

    # Skip synthetic generation for QAT-only — real data is sufficient for
    # INT8 calibration fine-tuning. Mix and split only real data sources.
    print("Skipping synthetic generation (QAT-only mode)...")
    qat_rec_ids = [np.array([f"{i}_{j}" for j in range(len(f))], dtype=object)
                   for i, f in enumerate(features_list)]
    dataset_sources = list(zip(features_list, labels_list, weights_list, qat_rec_ids))
    X_all, y_all, sample_weights, source_ids, _ = mix_datasets(dataset_sources)

    # Map 277-class labels to 25-class MIREX (same as full pipeline)
    y_all = np.array([mirex_label(int(y)) for y in y_all], dtype=np.int32)

    X_train, X_val, y_train, y_val, w_train, _ = train_test_split(
        X_all, y_all, sample_weights, test_size=0.15, random_state=42, stratify=y_all,
    )

    print(f"  Train: {len(X_train)} samples, Val: {len(X_val)} samples (no synthetic)")

    # ---- Load best float32 model ----
    # Model was saved with TF Keras (Keras 2). Since TFMOT sets
    # TF_USE_LEGACY_KERAS=True, tf.keras routes to tf_keras (Keras 2),
    # which is what we need to load the saved model.
    best_path = _APP_DIR / "chord_model_best.keras"
    if not best_path.exists():
        best_path = _APP_DIR / "chord_model_stage2_best.keras"
    if not best_path.exists():
        best_path = _APP_DIR / "chord_model.keras"
    print(f"\nLoading best model from: {best_path}")
    float32_model = tf.keras.models.load_model(
        str(best_path),
        custom_objects={"_circular_cqt_pad": _circular_cqt_pad, "CircularCqtPad": CircularCqtPad},
    )

    # Float32 baseline eval
    float32_output = float32_model.predict(X_val, verbose=0)
    float32_val_pred = extract_chord_predictions(float32_output)
    float32_val_acc = float(np.mean(float32_val_pred == y_val))
    float32_test_acc = None
    if len(test_X) > 0:
        float32_test_output = float32_model.predict(test_X, verbose=0)
        float32_test_pred = extract_chord_predictions(float32_test_output)
        float32_test_acc = float(np.mean(float32_test_pred == test_y))
    print(f"  Float32 baseline: val={float32_val_acc:.2%}, test={float32_test_acc or 'N/A'}")

    # ---- QAT Phase ----
    print("\n" + "=" * 60)
    print("  QAT Phase: Quantization-Aware Training")
    print("=" * 60)

    qat_model: tf.keras.Model | None = None
    qat_val_acc: float | None = None

    if not _HAS_TFMOT:
        print("  [SKIP] tensorflow_model_optimization not available")
        return

    qat_generator = AugmentedDataGenerator(
        X_train, y_train, w_train,
        batch_size=64,
        p_pitch_shift=0.3,
        pitch_range=1,
        p_time_stretch=0.1,
        stretch_range=(0.95, 1.05),
        noise_std=0.03,
        shuffle=True,
        temperature=temperature,
        multi_task=True,
    )

    print(f"  Applying QAT wrapper ({QAT_EPOCHS} epochs, LR={QAT_LEARNING_RATE})...")

    qat_val_acc: float | None = None
    qat_keras_path: Path | None = None
    int8_path: Path | None = None

    try:
        qat_model = apply_qat(float32_model)

        # Build multi-task validation dict
        y_val_root_qat = tf.keras.utils.to_categorical(
            derive_root_labels(y_val), N_ROOTS
        ).astype(np.float32)
        y_val_presence_qat = derive_presence_labels(y_val).reshape(-1, 1)
        y_val_dict_qat = {
            "chord_probs": tf.keras.utils.to_categorical(y_val, NUM_CLASSES_MIREX).astype(np.float32),
            "root_probs": y_val_root_qat,
            "presence": y_val_presence_qat,
        }

        qat_model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=QAT_LEARNING_RATE),
            loss={
                "chord_probs": tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.0),
                "root_probs": tf.keras.losses.CategoricalCrossentropy(),
                "presence": tf.keras.losses.BinaryCrossentropy(),
            },
            loss_weights={"chord_probs": 1.0, "root_probs": 0.1, "presence": 0.05},
            metrics={"chord_probs": "accuracy", "root_probs": "accuracy", "presence": "accuracy"},
        )

        qat_callbacks = [
            tf.keras.callbacks.CSVLogger(
                filename=str(_SCRIPTS_DIR / "training_log_qat.csv"),
            ),
        ]

        qat_model.fit(
            x=qat_generator,
            epochs=QAT_EPOCHS,
            validation_data=(X_val, y_val_dict_qat),
            callbacks=qat_callbacks,
            verbose=1,
        )

        qat_output = qat_model.predict(X_val, verbose=0)
        qat_val_pred = extract_chord_predictions(qat_output)
        qat_val_acc = float(np.mean(qat_val_pred == y_val))
        print(f"\n  QAT val accuracy: {qat_val_acc:.2%}  (float32: {float32_val_acc:.2%})")

        if len(test_X) > 0:
            qat_test_output = qat_model.predict(test_X, verbose=0)
            qat_test_pred = extract_chord_predictions(qat_test_output)
            qat_test_acc = float(np.mean(qat_test_pred == test_y))
            qat_deg = float32_test_acc - qat_test_acc if float32_test_acc is not None else 0.0
            print(f"  QAT GuitarSet test: {qat_test_acc:.2%}  (float32: {float32_test_acc:.2%}, deg: {qat_deg:.2%})")

        # Save QAT Keras model
        qat_keras_path = _APP_DIR / "chord_model_qat.keras"
        with tfmot.quantization.keras.quantize_scope():
            qat_model.save(str(qat_keras_path))
        print(f"  Saved QAT model -> {qat_keras_path} ({qat_keras_path.stat().st_size / 1024 / 1024:.1f} MB)")

        # ---- TFLite Conversion ----
        print("\nConverting QAT model to TFLite...")
        int8_path = _APP_DIR / "chord_model_qat_int8.tflite"
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X_val), size=min(100, len(X_val)), replace=False)
        rep_data = X_val[idx]
        tflite_bytes = convert_to_int8_tflite(qat_model, rep_data, str(int8_path))

        if tflite_bytes is not None:
            # ---- TFLite Smoke Tests ----
            print("\n--- TFLite Smoke Tests ---")
            test_cases = [
                (MIREX_TO_IDX["C:maj"], "C:maj"),
                (MIREX_TO_IDX["A:min"], "A:min"),
                (MIREX_TO_IDX["D#:maj"], "D#:maj"),
                (MIREX_TO_IDX["D:maj"], "D:maj"),
            ]

            try:
                # Load Flex delegate for SELECT_TF_OPS (needed for BiLSTM TensorList ops)
                flex_delegate = tf.lite.experimental.load_delegate("libtensorflowlite_flex.so")
                interpreter = tf.lite.Interpreter(
                    model_path=str(int8_path),
                    experimental_delegates=[flex_delegate],
                )
            except (ValueError, OSError, RuntimeError):
                # Flex delegate not available — run without it
                interpreter = tf.lite.Interpreter(model_path=str(int8_path))

            try:
                interpreter.allocate_tensors()
                input_details = interpreter.get_input_details()
                output_details = interpreter.get_output_details()
                input_scale, input_zero = input_details[0]["quantization"]

                all_passed = True
                for label_idx, label_name in test_cases:
                    class_mask = y_train == label_idx
                    if class_mask.sum() > 0:
                        sample = X_train[class_mask][0:1]
                    else:
                        sample = np.zeros((1, WINDOW, FEATURE_DIM), dtype=np.float32)

                    # Handle both quantized (INT8) and float input
                    if input_details[0]["dtype"] == np.int8:
                        q_sample = (sample / input_scale + input_zero).astype(np.int8)
                    else:
                        q_sample = sample.astype(np.float32)
                    interpreter.set_tensor(input_details[0]["index"], q_sample)
                    interpreter.invoke()
                    output = interpreter.get_tensor(output_details[0]["index"])
                    out_scale, out_zero = output_details[0]["quantization"]
                    if out_scale != 0:
                        output_float = (output.astype(np.float32) - out_zero) * out_scale
                    else:
                        output_float = output.astype(np.float32)
                    pred_idx = np.argmax(output_float[0])

                    pred_label = MIREX_VOCAB[pred_idx]
                    expected_label = MIREX_VOCAB[label_idx]
                    match = "PASS" if pred_idx == label_idx else "FAIL"
                    if match == "FAIL":
                        all_passed = False
                    confidence = output_float[0][pred_idx] * 100
                    print(f"  {label_name:<10} -> {pred_label:<10} ({confidence:.1f}%) [{match}]")

                print(f"\n  All TFLite smoke tests {'PASSED' if all_passed else 'FAILED'}")
            except RuntimeError as e:
                print(f"  [SKIP] TFLite smoke tests (SELECT_TF_OPS not available in Python runtime): {e}")
                print("  [SKIP] Test on-device with the tensorflow-lite-select-tf-ops dependency.")
        else:
            print("  [SKIP] TFLite smoke tests (conversion failed)")

    except Exception as exc:
        print(f"\n  [WARN] QAT pipeline failed: {exc}")
        import traceback
        traceback.print_exc()
        qat_model = None

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("  QAT-Only Pipeline Complete")
    print("=" * 60)
    if qat_keras_path is not None:
        print(f"  QAT model:     {qat_keras_path}")
    else:
        print(f"  QAT model:     (not saved)")
    if int8_path is not None and int8_path.exists():
        print(f"  INT8 TFLite:   {int8_path}")
        size_kb = int8_path.stat().st_size / 1024
        print(f"  INT8 TFLite size: {size_kb:.1f} KB")
    else:
        print(f"  INT8 TFLite:   (not available)")
    print(f"  Float32 val acc: {float32_val_acc:.2%}")
    if qat_val_acc is not None:
        print(f"  QAT val acc:      {qat_val_acc:.2%}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build chord recognition model with multi-source weighted data mixing (Commit 105)"
    )
    parser.add_argument(
        "--guitarset-data-dir", type=str, default=None,
        help="Path to GuitarSet CQT data directory (contains guitarset/processed/cqt/)"
    )
    parser.add_argument(
        "--idmt-data-dir", type=str, default=None,
        help="Path to IDMT-SMT-Guitar CQT data directory"
    )
    parser.add_argument(
        "--vst-data-dir", type=str, default=None,
        help="Path to VST synthetic CQT data directory"
    )
    parser.add_argument(
        "--youtube-data-dir", type=str, default=None,
        help="Path to YouTube crawl CQT data directory"
    )
    parser.add_argument(
        "--damp-data-dir", type=str, default=None,
        help="Path to DAMP-VPB CQT data directory"
    )
    parser.add_argument(
        "--pseudo-data-dir", type=str, default=None,
        help="Path to pseudo-labeled CQT data directory (uses vst-loss-weight)"
    )
    parser.add_argument(
        "--jaah-data-dir", type=str, default=None,
        help="Path to JAAH CQT data directory (requires user-supplied audio)"
    )
    parser.add_argument(
        "--guitarset-loss-weight", type=float, default=1.0,
        help="Per-sample loss weight for GuitarSet (default 1.0)"
    )
    parser.add_argument(
        "--vst-loss-weight", type=float, default=0.3,
        help="Per-sample loss weight for VST synthetic (default 0.3, per Commit 105)"
    )
    parser.add_argument(
        "--damp-loss-weight", type=float, default=0.15,
        help="Per-sample loss weight for DAMP-VPB (default 0.15, per Commit 105)"
    )
    parser.add_argument(
        "--jaah-loss-weight", type=float, default=1.0,
        help="Per-sample loss weight for JAAH (default 1.0)"
    )
    parser.add_argument(
        "--guitar-techs-data-dir", type=str, default=None,
        help="Path to Guitar-TECHS CQT data directory (contains guitar_techs/processed/cqt/)"
    )
    parser.add_argument(
        "--guitar-techs-loss-weight", type=float, default=1.0,
        help="Per-sample loss weight for Guitar-TECHS (default 1.0)"
    )
    parser.add_argument(
        "--egset12-data-dir", type=str, default=None,
        help="Path to EGSet12 CQT data directory (contains egset12/processed/cqt/)"
    )
    parser.add_argument(
        "--egset12-loss-weight", type=float, default=1.0,
        help="Per-sample loss weight for EGSet12 (default 1.0)"
    )
    parser.add_argument(
        "--empirical-matrix", type=str, default=None,
        help="Path to empirical transition matrix .npy file"
    )
    parser.add_argument(
        "--temperature", type=float, default=0.5,
        help="Temperature τ for quality re-sampling (default 1.0 = uniform). "
             "τ<1.0 boosts rare chord quality sampling via MT3 formula. "
             "τ=1.0 = uniform sampling. Range [0, 1]."
    )
    parser.add_argument(
        "--rare-boost", action="store_true",
        help="Rare chord boost mode: sets temperature=0.1 for aggressive "
             "oversampling of rare chord types (7#9, alt7, dim7, aug). "
             "Use during fine-tuning after initial convergence."
    )
    parser.add_argument(
        "--cqt-stats-path", type=str, default=None,
        help="Path to .npz with CQT distribution statistics for synthetic-to-real "
             "domain gap matching (Commit 148 Phase 1b). Generated by "
             "cqt_distribution_analyzer.py. If omitted, no distribution matching."
    )
    parser.add_argument(
        "--qat-only", action="store_true",
        help="QAT-only mode: skip main training, load best model, run QAT fine-tuning and INT8 conversion. "
             "Requires a previously trained model (chord_model_best.keras)."
    )
    parser.add_argument(
        "--guitarset-cv", action="store_true",
        help="GuitarSet 5-fold cross-validation mode: run leave-one-player-out CV "
             "(players 00-04) and report mean ± std. Player 05 held out for final test."
    )
    parser.add_argument(
        "--cv-epochs", type=int, default=30,
        help="Epochs per fold for --guitarset-cv (default: 30)"
    )
    parser.add_argument(
        "--onnx", action="store_true",
        help="Export ONNX model (chord_model.onnx) for web inference after training. "
             "Requires tf2onnx: pip install tf2onnx"
    )
    args = parser.parse_args()

    if args.temperature < 0:
        parser.error("temperature must be >= 0")

    if args.rare_boost:
        if args.temperature != 1.0:
            print("  [WARN] --rare-boost overrides --temperature; setting τ=0.1")
        args.temperature = 0.1
        print("  Rare chord boost mode: τ=0.1 — aggressive oversampling of rare types")

    if args.qat_only:
        run_qat_only(
            guitarset_data_dir=args.guitarset_data_dir,
            idmt_data_dir=args.idmt_data_dir,
            vst_data_dir=args.vst_data_dir,
            youtube_data_dir=args.youtube_data_dir,
            damp_data_dir=args.damp_data_dir,
            pseudo_data_dir=args.pseudo_data_dir,
            jaah_data_dir=args.jaah_data_dir,
            guitar_techs_data_dir=args.guitar_techs_data_dir,
            egset12_data_dir=args.egset12_data_dir,
            guitarset_loss_weight=args.guitarset_loss_weight,
            vst_loss_weight=args.vst_loss_weight,
            damp_loss_weight=args.damp_loss_weight,
            jaah_loss_weight=args.jaah_loss_weight,
            guitar_techs_loss_weight=args.guitar_techs_loss_weight,
            egset12_loss_weight=args.egset12_loss_weight,
            empirical_matrix_path=args.empirical_matrix,
            temperature=args.temperature,
            cqt_stats_path=args.cqt_stats_path,
            export_onnx=args.onnx,
        )
    elif args.guitarset_cv:
        if not args.guitarset_data_dir:
            parser.error("--guitarset-cv requires --guitarset-data-dir")
        cv_result = run_guitarset_cv(
            guitarset_data_dir=args.guitarset_data_dir,
            epochs=args.cv_epochs,
        )
        # Save CV results
        import json as _json
        cv_output = Path(args.guitarset_data_dir) / "cv_results.json"
        with open(cv_output, "w") as f:
            _json.dump(cv_result, f, indent=2, default=str)
        print(f"\nCV results saved to {cv_output}")
    else:
        run_pipeline(
            guitarset_data_dir=args.guitarset_data_dir,
            idmt_data_dir=args.idmt_data_dir,
            vst_data_dir=args.vst_data_dir,
            youtube_data_dir=args.youtube_data_dir,
            damp_data_dir=args.damp_data_dir,
            pseudo_data_dir=args.pseudo_data_dir,
            jaah_data_dir=args.jaah_data_dir,
            guitar_techs_data_dir=args.guitar_techs_data_dir,
            egset12_data_dir=args.egset12_data_dir,
            guitarset_loss_weight=args.guitarset_loss_weight,
            vst_loss_weight=args.vst_loss_weight,
            damp_loss_weight=args.damp_loss_weight,
            jaah_loss_weight=args.jaah_loss_weight,
            guitar_techs_loss_weight=args.guitar_techs_loss_weight,
            egset12_loss_weight=args.egset12_loss_weight,
            empirical_matrix_path=args.empirical_matrix,
            temperature=args.temperature,
            cqt_stats_path=args.cqt_stats_path,
            export_onnx=args.onnx,
        )
