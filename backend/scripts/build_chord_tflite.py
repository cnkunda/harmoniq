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

import os
from pathlib import Path

# Force TensorFlow backend and CPU mode
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np
import tensorflow as tf

# ---------------------------------------------------------------------------
# 1. Constants & Vocabulary
# ---------------------------------------------------------------------------
ROOT_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CHORD_INTERVALS = {
    # Core triads
    "maj":  [0, 4, 7],
    "min":  [0, 3, 7],
    # 7th chords
    "7":    [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    # Extended
    "9":    [0, 4, 7, 10, 14],
    "min9": [0, 3, 7, 10, 14],
    "maj9": [0, 4, 7, 11, 14],
    "11":   [0, 4, 7, 10, 14, 17],
    "13":   [0, 4, 7, 10, 14, 17, 21],
    # Altered dominants
    "7#9":  [0, 4, 7, 10, 15],
    "7b9":  [0, 4, 7, 10, 13],
    "7#5":  [0, 4, 8, 10],
    "7b5":  [0, 4, 6, 10],
    "alt7": [0, 4, 6, 8, 10, 13, 15],
    # Suspended
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "7sus4": [0, 5, 7, 10],
    # Other
    "dim":   [0, 3, 6],
    "dim7":  [0, 3, 6, 9],
    "aug":   [0, 4, 8],
    "6":     [0, 4, 7, 9],
    "min6":  [0, 3, 7, 9],
}

# Build vocabulary as root:quality pairs, e.g. "C:maj", "D:7", "A:min7"
CHORD_VOCAB = []
CHORD_CLASS_MAP = []
for quality in CHORD_INTERVALS:
    for root_idx, root_note in enumerate(ROOT_NOTES):
        CHORD_VOCAB.append(f"{root_note}:{quality}")
        CHORD_CLASS_MAP.append((root_idx, quality))

# No-chord token
CHORD_VOCAB.append("N")
CHORD_CLASS_MAP.append((-1, "N"))

NUM_CLASSES     = len(CHORD_VOCAB)
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
                          stretch_range: tuple = (0.9, 1.1)) -> np.ndarray:
    """Create augmented window with pink noise and temporal variations.
    
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
    
    return window


def generate_dataset(samples_per_class: int = 200, config: dict = None):
    """Generate augmented chord dataset with realistic variability.
    
    Args:
        samples_per_class: Base samples per chord class
        config: Augmentation configuration dict with keys:
            - inversion_rates: [root, 1st, 2nd] probabilities
            - missing_note_dropout: probability of dropping notes (default 0.15)
            - pitch_shift_range: max semitones (default 2)
            - time_stretch_rate: fraction of samples to stretch (default 0.3)
            - time_stretch_range: (min, max) stretch factors (default 0.9, 1.1)
            - bass_ambiguity_rate: fraction with bass ambiguity (default 0.2)
            - transition_rate: extra transition samples as fraction (default 0.3)
    """
    cfg = config or {}
    inversion_rates = cfg.get("inversion_rates", [0.60, 0.25, 0.15])
    dropout_rate = cfg.get("missing_note_dropout", 0.15)
    pitch_range = cfg.get("pitch_shift_range", 2)
    stretch_rate = cfg.get("time_stretch_rate", 0.3)
    stretch_range = cfg.get("time_stretch_range", (0.9, 1.1))
    bass_rate = cfg.get("bass_ambiguity_rate", 0.2)
    transition_rate = cfg.get("transition_rate", 0.3)
    
    X, y = [], []
    
    for idx, (root_idx, quality) in enumerate(CHORD_CLASS_MAP):
        template = make_cqt_template(root_idx, quality)
        
        for _ in range(samples_per_class):
            inversion = np.random.choice([0, 1, 2], p=inversion_rates)
            augmented = apply_inversion(template, root_idx, quality, inversion)
            augmented = apply_missing_notes(augmented, quality, dropout_rate)
            
            if np.random.random() < bass_rate:
                strength = np.random.uniform(0.1, 0.3)
                augmented = apply_bass_ambiguity(augmented, root_idx, quality, strength)
            
            std = 0.08 + np.random.uniform(0, 0.12)
            window = make_window_augmented(
                augmented, std,
                pitch_range=pitch_range,
                stretch_rate=stretch_rate,
                stretch_range=stretch_range
            )
            
            X.append(window)
            y.append(idx)
    
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
def run_pipeline():
    print("Generating dataset...")
    X, y = generate_dataset()
    p = np.random.permutation(len(X))
    X, y = X[p], y[p]
    
    model = build_model()
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    
    print("\nTraining...")
    history = model.fit(X, y, epochs=20, batch_size=64, validation_split=0.15, verbose=1)

    # Per-group accuracy tracking (Commit 98d)
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

    print("\nTracing model to Concrete Function (Bypassing Keras serialization)...")
    
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
    interp = tf.lite.Interpreter(model_path=str(output_path))
    interp.allocate_tensors()
    input_details = interp.get_input_details()[0]
    output_details = interp.get_output_details()[0]
    
    # Verify single output tensor (classification only; attention weights stripped)
    assert len(output_details) == 1 or len(interp.get_output_details()) == 1, \
        "TFLite model must have exactly one output"
    
    test_cases = [
        ("D:7",    2,  "7"),     # D dominant 7th
        ("C:maj7", 0,  "maj7"), # C major 7th
        ("A:min7", 9,  "min7"), # A minor 7th
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
    
    if all_passed:
        print("\nAll smoke tests PASSED")
    else:
        print("\nSome smoke tests FAILED")

if __name__ == "__main__":
    run_pipeline()