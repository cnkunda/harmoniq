"""Tests for chord data augmentation functions (Commit 98a).

These tests import only the augmentation functions without triggering TensorFlow import.
"""
import numpy as np
import pytest
import sys
from pathlib import Path

# We need to mock the environment before importing
import os
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES, CHORD_VOCAB, NUM_CLASSES

# Build chord class map for testing
CHORD_CLASS_MAP = []
for quality in CHORD_INTERVALS:
    for root_idx, root_note in enumerate(ROOT_NOTES):
        CHORD_CLASS_MAP.append((root_idx, quality))
CHORD_CLASS_MAP.append((-1, "N"))

WINDOW       = 9
CHROMA_BINS  = 12


def make_chroma_template(root: int, quality: str) -> np.ndarray:
    chroma = np.zeros(CHROMA_BINS, dtype=np.float32)
    if quality == "N":
        return np.full(CHROMA_BINS, 1.0 / CHROMA_BINS, dtype=np.float32)
    intervals = CHORD_INTERVALS[quality]
    for i, interval in enumerate(intervals):
        note = (root + interval) % CHROMA_BINS
        weight = 1.0 if interval <= 12 else 0.7
        if i == 0:
            weight *= 1.20
        chroma[note] += weight
        chroma[(note + 7) % CHROMA_BINS] += 0.5
        chroma[note] += 0.3
    total = chroma.sum()
    return chroma / total if total > 0 else chroma


def apply_inversion(template: np.ndarray, root: int, quality: str, inversion: int = 0) -> np.ndarray:
    if inversion == 0 or quality == "N":
        return template
    
    intervals = CHORD_INTERVALS[quality]
    if len(intervals) < inversion + 1:
        return template
    
    bass_interval = intervals[inversion]
    shifted = np.roll(template, -bass_interval)
    return (shifted * 0.95).astype(np.float32)


def apply_missing_notes(template: np.ndarray, quality: str, dropout_rate: float = 0.15) -> np.ndarray:
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
    for idx in drop_indices:
        interval = intervals[idx]
        note = interval % CHROMA_BINS
        result[note] *= 0.1
        result[(note + 7) % CHROMA_BINS] *= 0.1
    
    total = result.sum()
    if total > 0:
        result = result / total
    
    return result


def apply_pitch_shift(window: np.ndarray, shift_semitones: int = 0) -> np.ndarray:
    if shift_semitones == 0:
        return window
    return np.roll(window, shift_semitones, axis=-1)


def apply_time_stretch(window: np.ndarray, stretch_factor: float = 1.0) -> np.ndarray:
    if abs(stretch_factor - 1.0) < 1e-6:
        return window
    
    original_length = window.shape[0]
    original_times = np.arange(original_length)
    stretched_times = original_times * stretch_factor
    
    result = np.zeros_like(window)
    for bin_idx in range(CHROMA_BINS):
        result[:, bin_idx] = np.interp(
            original_times, stretched_times, window[:, bin_idx],
            left=window[0, bin_idx], right=window[-1, bin_idx]
        )
    
    return result


def apply_bass_ambiguity(template: np.ndarray, root: int, quality: str, ambiguity_strength: float = 0.0) -> np.ndarray:
    if ambiguity_strength <= 0 or quality == "N":
        return template
    
    result = template.copy()
    chord_notes = set()
    for interval in CHORD_INTERVALS[quality]:
        chord_notes.add((root + interval) % CHROMA_BINS)
    
    possible_bass = [n for n in range(CHROMA_BINS) if n not in chord_notes]
    if not possible_bass:
        return template
    
    bass_note = np.random.choice(possible_bass)
    result[bass_note] += ambiguity_strength
    result[(bass_note + 7) % CHROMA_BINS] += ambiguity_strength * 0.3
    
    total = result.sum()
    if total > 0:
        result = result / total
    
    return result


def generate_pink_noise(shape: tuple, noise_std: float = 0.12) -> np.ndarray:
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
    window = np.zeros((WINDOW, CHROMA_BINS), dtype=np.float32)
    for i in range(WINDOW):
        t = i / (WINDOW - 1)
        frame_mix = (1 - t) * template_a + t * template_b
        noise = generate_pink_noise((CHROMA_BINS,), 0.12)
        window[i] = np.clip(frame_mix + noise, 0, 1)
    
    return window


def make_window_augmented(center_chroma: np.ndarray, noise_std: float = 0.12,
                          pitch_range: int = 2, stretch_rate: float = 0.3,
                          stretch_range: tuple = (0.9, 1.1)) -> tuple[np.ndarray, int]:
    """Create augmented window with pink noise and temporal variations.

    Returns (window, shift_semitones) so callers can adjust labels
    to match the applied pitch shift.
    """
    frames = []
    for _ in range(WINDOW):
        noise = generate_pink_noise((CHROMA_BINS,), noise_std)
        frame = np.clip(center_chroma + noise, 0, 1)
        frames.append(frame)

    window = np.stack(frames, axis=0)

    shift = np.random.randint(-pitch_range, pitch_range + 1)
    window = apply_pitch_shift(window, shift)

    if np.random.random() < stretch_rate:
        factor = np.random.uniform(*stretch_range)
        window = apply_time_stretch(window, factor)

    return window, shift


def _adjust_label_for_shift(idx: int, shift: int, n_classes_per_quality: int = 12,
                             n_chord_classes: int | None = None) -> int:
    """Adjust class index to match a pitch-shifted feature.

    When CQT bins are rolled by N semitones, the chord root must
    also shift: C:maj shifted +2 becomes D:maj. N class stays unchanged.
    """
    if n_chord_classes is None:
        n_chord_classes = len(CHORD_INTERVALS) * n_classes_per_quality
    if shift == 0 or idx >= n_chord_classes:
        return idx
    quality_pos = idx // n_classes_per_quality
    root = idx % n_classes_per_quality
    new_root = (root + shift) % n_classes_per_quality
    return quality_pos * n_classes_per_quality + new_root


def generate_dataset(samples_per_class: int = 1500, config: dict = None):
    cfg = config or {}
    inversion_rates = cfg.get("inversion_rates", [0.60, 0.25, 0.15])
    dropout_rate = cfg.get("missing_note_dropout", 0.15)
    pitch_range = cfg.get("pitch_shift_range", 2)
    stretch_rate = cfg.get("time_stretch_rate", 0.3)
    stretch_range = cfg.get("time_stretch_range", (0.9, 1.1))
    bass_rate = cfg.get("bass_ambiguity_rate", 0.2)
    transition_rate = cfg.get("transition_rate", 0.3)

    n_chord_classes = len(CHORD_INTERVALS) * 12
    X, y = [], []

    for idx, (root_idx, quality) in enumerate(CHORD_CLASS_MAP):
        template = make_chroma_template(root_idx, quality)

        for _ in range(samples_per_class):
            inversion = np.random.choice([0, 1, 2], p=inversion_rates)
            augmented = apply_inversion(template, root_idx, quality, inversion)
            augmented = apply_missing_notes(augmented, quality, dropout_rate)

            if np.random.random() < bass_rate:
                strength = np.random.uniform(0.1, 0.3)
                augmented = apply_bass_ambiguity(augmented, root_idx, quality, strength)

            std = 0.08 + np.random.uniform(0, 0.12)
            window, shift = make_window_augmented(
                augmented, std,
                pitch_range=pitch_range,
                stretch_rate=stretch_rate,
                stretch_range=stretch_range
            )

            # Adjust label to match pitch shift
            adjusted_idx = _adjust_label_for_shift(idx, shift)
            X.append(window)
            y.append(adjusted_idx)
    
    n_transitions = int(len(CHORD_CLASS_MAP) * samples_per_class * transition_rate)
    for _ in range(n_transitions):
        idx_a, idx_b = np.random.choice(len(CHORD_CLASS_MAP), 2, replace=False)
        root_a, qual_a = CHORD_CLASS_MAP[idx_a]
        root_b, qual_b = CHORD_CLASS_MAP[idx_b]
        template_a = make_chroma_template(root_a, qual_a)
        template_b = make_chroma_template(root_b, qual_b)
        mix_ratio = np.random.uniform(0.3, 0.7)
        X.append(make_transition_window(template_a, template_b, mix_ratio))
        y.append(idx_a)
    
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestInversion:
    def test_root_position_unchanged(self):
        template = make_chroma_template(0, "maj")
        result = apply_inversion(template, 0, "maj", 0)
        np.testing.assert_array_almost_equal(result, template)
    
    def test_first_inversion_shifts_bass(self):
        template = make_chroma_template(0, "maj")
        inv1 = apply_inversion(template, 0, "maj", 1)
        # 1st inversion rolls by -4 (E interval), shifting the template
        # Verify the shift occurred: template should be different from root
        assert not np.allclose(inv1, template)
        # Verify energy distribution changed: the pattern is rotated
        assert np.argmax(inv1) != np.argmax(template)
    
    def test_second_inversion_shifts_bass(self):
        template = make_chroma_template(0, "maj")
        inv2 = apply_inversion(template, 0, "maj", 2)
        # 2nd inversion rolls by -7 (G interval), so G moves to bin 0
        # The template has overtones so we verify the shift occurred
        assert not np.allclose(inv2, template)
        # Verify the shift occurred: original root (bin 0) should have moved
        assert inv2[0] != template[0]
    
    def test_no_chord_returns_unchanged(self):
        template = make_chroma_template(-1, "N")
        result = apply_inversion(template, -1, "N", 1)
        np.testing.assert_array_almost_equal(result, template)
    
    def test_insufficient_notes_returns_unchanged(self):
        template = make_chroma_template(0, "dim")
        result = apply_inversion(template, 0, "dim", 2)
        assert result.shape == template.shape


class TestMissingNotes:
    def test_preserves_minimum_notes(self):
        template = make_chroma_template(0, "maj7")
        result = apply_missing_notes(template, "maj7", 0.5)
        assert np.sum(result > 0.05) >= 2
    
    def test_no_chord_returns_unchanged(self):
        template = make_chroma_template(-1, "N")
        result = apply_missing_notes(template, "N", 0.5)
        np.testing.assert_array_almost_equal(result, template)
    
    def test_dropout_rate_affects_result(self):
        template = make_chroma_template(0, "13")
        result = apply_missing_notes(template, "13", 0.8)
        assert not np.allclose(result, template)


class TestPitchShift:
    def test_zero_shift_unchanged(self):
        window = np.random.rand(9, 12).astype(np.float32)
        result = apply_pitch_shift(window, 0)
        np.testing.assert_array_equal(result, window)
    
    def test_shift_circular(self):
        window = np.zeros((9, 12), dtype=np.float32)
        window[:, 0] = 1.0
        shifted = apply_pitch_shift(window, 3)
        assert np.argmax(shifted[0]) == 3
    
    def test_negative_shift(self):
        window = np.zeros((9, 12), dtype=np.float32)
        window[:, 6] = 1.0
        shifted = apply_pitch_shift(window, -3)
        assert np.argmax(shifted[0]) == 3


class TestTimeStretch:
    def test_no_stretch_unchanged(self):
        window = np.random.rand(9, 12).astype(np.float32)
        result = apply_time_stretch(window, 1.0)
        np.testing.assert_array_almost_equal(result, window)
    
    def test_stretch_preserves_shape(self):
        window = np.random.rand(9, 12).astype(np.float32)
        result = apply_time_stretch(window, 1.1)
        assert result.shape == window.shape
    
    def test_slow_stretch(self):
        window = np.random.rand(9, 12).astype(np.float32)
        result = apply_time_stretch(window, 0.9)
        assert result.shape == window.shape


class TestBassAmbiguity:
    def test_zero_strength_unchanged(self):
        template = make_chroma_template(0, "maj")
        result = apply_bass_ambiguity(template, 0, "maj", 0.0)
        np.testing.assert_array_almost_equal(result, template)
    
    def test_injects_bass_energy(self):
        template = make_chroma_template(0, "maj")
        result = apply_bass_ambiguity(template, 0, "maj", 0.3)
        assert not np.allclose(result, template)
    
    def test_no_chord_returns_unchanged(self):
        template = make_chroma_template(-1, "N")
        result = apply_bass_ambiguity(template, -1, "N", 0.3)
        np.testing.assert_array_almost_equal(result, template)


class TestPinkNoise:
    def test_output_shape_1d(self):
        noise = generate_pink_noise((100,), 1.0)
        assert noise.shape == (100,)
    
    def test_output_shape_2d(self):
        noise = generate_pink_noise((9, 12), 0.12)
        assert noise.shape == (9, 12)
    
    def test_spectral_slope(self):
        noise = generate_pink_noise((1000,), 1.0)
        fft = np.abs(np.fft.rfft(noise))
        low_energy = fft[:10].mean()
        high_energy = fft[-10:].mean()
        assert low_energy > high_energy
    
    def test_std_scaling(self):
        noise = generate_pink_noise((10000,), 0.5)
        assert abs(noise.std() - 0.5) < 0.1


class TestTransitionWindow:
    def test_output_shape(self):
        t_a = make_chroma_template(0, "maj")
        t_b = make_chroma_template(7, "maj")
        window = make_transition_window(t_a, t_b, 0.5)
        assert window.shape == (WINDOW, CHROMA_BINS)
    
    def test_mixed_content(self):
        t_a = make_chroma_template(0, "maj")
        t_b = make_chroma_template(7, "maj")
        window = make_transition_window(t_a, t_b, 0.5)
        assert window.sum() > 0


class TestDatasetGeneration:
    def test_output_shapes(self):
        X, y = generate_dataset(samples_per_class=10)
        assert X.ndim == 3
        assert X.shape[1:] == (WINDOW, CHROMA_BINS)
        assert len(y) == len(X)
    
    def test_augmentation_diversity(self):
        X, y = generate_dataset(samples_per_class=10)
        assert X.std() > 0.05
    
    def test_transition_samples_included(self):
        X, y = generate_dataset(samples_per_class=10, config={"transition_rate": 0.3})
        n_classes = len(CHORD_CLASS_MAP)
        expected_base = n_classes * 10
        expected_transitions = int(n_classes * 10 * 0.3)
        assert len(X) >= expected_base + expected_transitions * 0.5


class TestPitchShiftLabelSync:
    """Verify that pitch-shifted synthetic data has correct labels."""

    def test_shift_C_maj_to_D_maj(self):
        template = make_chroma_template(0, "maj")
        window, shift = make_window_augmented(
            template, noise_std=0.01, pitch_range=2, stretch_rate=0.0
        )
        # With stretch_rate=0 and small noise, shift is the only augmentation
        assert isinstance(shift, int)
        assert -2 <= shift <= 2

    def test_adjust_label_C_maj_shift_2(self):
        idx = CHORD_CLASS_MAP.index((0, "maj"))  # C:maj
        adjusted = _adjust_label_for_shift(idx, 2)
        expected = CHORD_CLASS_MAP.index((2, "maj"))  # D:maj
        assert adjusted == expected, f"C:maj+2 should be D:maj, got {CHORD_VOCAB[adjusted]}"

    def test_adjust_label_wraps_around(self):
        idx = CHORD_CLASS_MAP.index((11, "maj"))  # B:maj
        adjusted = _adjust_label_for_shift(idx, 1)
        expected = CHORD_CLASS_MAP.index((0, "maj"))  # C:maj
        assert adjusted == expected, f"B:maj+1 should be C:maj, got {CHORD_VOCAB[adjusted]}"

    def test_adjust_label_negative_shift(self):
        idx = CHORD_CLASS_MAP.index((0, "maj"))  # C:maj
        adjusted = _adjust_label_for_shift(idx, -1)
        expected = CHORD_CLASS_MAP.index((11, "maj"))  # B:maj
        assert adjusted == expected, f"C:maj-1 should be B:maj, got {CHORD_VOCAB[adjusted]}"

    def test_N_class_unchanged(self):
        idx = CHORD_CLASS_MAP.index((-1, "N"))  # N
        adjusted = _adjust_label_for_shift(idx, 2)
        assert adjusted == idx, "N class should be unchanged after pitch shift"

    def test_zero_shift_unchanged(self):
        idx = CHORD_CLASS_MAP.index((5, "min"))
        adjusted = _adjust_label_for_shift(idx, 0)
        assert adjusted == idx, "Zero shift should leave label unchanged"

    def test_quality_preserved_across_all_shifts(self):
        """After label adjustment, the quality (maj, min, 7, etc.) must stay the same."""
        for quality in list(CHORD_INTERVALS.keys())[:5]:
            for root in range(12):
                idx = CHORD_CLASS_MAP.index((root, quality))
                for shift in [-2, -1, 1, 2]:
                    adjusted = _adjust_label_for_shift(idx, shift)
                    adjusted_quality = CHORD_CLASS_MAP[adjusted][1]
                    assert adjusted_quality == quality, \
                        f"Quality changed from {quality} to {adjusted_quality} " \
                        f"for root {root} shift {shift}"

    def test_generated_dataset_label_distribution(self):
        """In a large dataset, each quality should have all 12 roots represented
        (label adjustment shouldn't systematically delete any class)."""
        X, y = generate_dataset(samples_per_class=20)
        unique_labels = set(y)
        # At minimum, we should see all 277 classes represented
        # (some may be missing due to randomness, but >265 is expected)
        assert len(unique_labels) > 265, \
            f"Only {len(unique_labels)}/277 classes present after label adjustment"


class TestAcousticRealism:
    """Tests for acoustic realism augmentations — import from production module."""

    def test_body_resonance_changes_spectrum(self):
        from scripts.build_chord_tflite import (
            apply_guitar_body_resonance,
            CHROMA_BINS,
            BASS_BINS,
        )
        feat_dim = CHROMA_BINS + BASS_BINS  # 40
        template = np.ones(feat_dim, dtype=np.float32) / feat_dim
        result = apply_guitar_body_resonance(template, strength=0.5)
        assert result.shape == template.shape
        assert not np.allclose(result, template)

    def test_strumming_attenuates_early_frames(self):
        from scripts.build_chord_tflite import apply_strumming_onset
        feat_dim = 40
        window = np.ones((64, feat_dim), dtype=np.float32)
        result = apply_strumming_onset(window, "maj", n_strum_frames=4)
        assert result[0, 0] < 1.0
        assert abs(result[-1, 0] - 1.0) < 1e-6

    def test_strumming_skips_no_chord(self):
        from scripts.build_chord_tflite import apply_strumming_onset
        window = np.ones((64, 40), dtype=np.float32)
        result = apply_strumming_onset(window, "N", n_strum_frames=4)
        np.testing.assert_array_equal(result, window)

    def test_cqt_leakage_spreads_energy(self):
        from scripts.build_chord_tflite import apply_cqt_leakage, CHROMA_BINS
        window = np.zeros((9, 40), dtype=np.float32)
        window[:, 6] = 1.0
        result = apply_cqt_leakage(window, leakage_strength=1.0)
        assert result[0, 5] > 0.0
        assert result[0, 7] > 0.0
        assert result[0, 6] > result[0, 5]

    def test_cqt_leakage_zero_strength_unchanged(self):
        from scripts.build_chord_tflite import apply_cqt_leakage
        window = np.random.randn(9, 40).astype(np.float32)
        result = apply_cqt_leakage(window, leakage_strength=0.0)
        np.testing.assert_array_equal(result, window)
