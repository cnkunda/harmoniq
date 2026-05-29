"""Tests for VST synthetic audio pipeline (Commit 105 Phase 2).

Tests: synth_guitar rendering, MIDI generation, CQT extraction,
reverb IR management.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.synth_guitar import (
    render_chord,
    render_melody_note,
    apply_body_resonance,
    apply_random_gain_shift,
    apply_random_eq_shift,
    _midi_to_freq,
    _note_to_string,
    TARGET_SR,
)
from app.reverb_ir import (
    get_available_irs,
    apply_reverb,
)
from scripts.generate_synthetic_midi import (
    _midi_note,
    create_chord_midi,
    create_progression_midi,
    _is_valid_guitar_note,
)
from scripts.render_synthetic_guitar import (
    extract_cqt,
    build_windows,
    render_midi_to_chord_label,
    CHROMA_BINS,
    BASS_BINS,
    FEATURE_DIM,
    WINDOW,
    N_CHORD_IDX,
)


class TestSynthGuitar:
    def test_render_chord_output_shape(self):
        audio = render_chord(48, [0, 4, 7], duration=0.5, style="block")
        expected = int(TARGET_SR * 0.5)
        assert len(audio) == expected
        assert np.max(np.abs(audio)) > 0.001

    def test_render_chord_strum(self):
        audio = render_chord(55, [0, 3, 7], duration=0.5, style="strum")
        assert len(audio) > 0
        assert np.isfinite(audio).all()

    def test_render_melody_note(self):
        audio = render_melody_note(60, duration=0.3)
        expected = int(TARGET_SR * 0.3)
        assert len(audio) == expected
        assert np.max(np.abs(audio)) > 0.001

    def test_apply_body_resonance(self):
        audio = np.sin(2 * np.pi * 440 * np.arange(44100) / 44100).astype(np.float32)
        processed = apply_body_resonance(audio, strength=0.3)
        assert len(processed) == len(audio)
        assert np.isfinite(processed).all()

    def test_apply_random_gain_shift(self):
        audio = np.ones(1000, dtype=np.float32) * 0.5
        shifted = apply_random_gain_shift(audio, (0, 0))  # No change
        assert np.allclose(shifted, audio)

    def test_apply_random_eq_shift(self):
        audio = np.sin(2 * np.pi * 440 * np.arange(4410) / 44100).astype(np.float32)
        processed = apply_random_eq_shift(audio)
        assert len(processed) == len(audio)
        assert np.isfinite(processed).all()

    def test_midi_to_freq(self):
        assert abs(_midi_to_freq(69) - 440.0) < 0.01  # A4 = 440Hz
        assert abs(_midi_to_freq(60) - 261.63) < 0.5  # C4 ~ 261.63Hz

    def test_note_to_string(self):
        string, fret = _note_to_string(40)  # Low E
        assert string == 0
        assert 0 <= fret <= 24

        string, fret = _note_to_string(64)  # High E
        assert string == 5
        assert 0 <= fret <= 24


class TestReverbIR:
    def test_apply_reverb_no_ir(self):
        audio = np.random.randn(44100).astype(np.float32)
        ir = np.array([1.0, 0.5, 0.25], dtype=np.float32)
        processed = apply_reverb(audio, ir, mix=0.5)
        assert len(processed) == len(audio)
        assert np.isfinite(processed).all()

    def test_dry_signal_preserved(self):
        audio = np.sin(2 * np.pi * 440 * np.arange(4410) / 44100).astype(np.float32)
        ir = np.zeros(100, dtype=np.float32)
        ir[0] = 1.0
        processed = apply_reverb(audio, ir, mix=0.0)
        assert np.allclose(processed, audio, atol=1e-6)

    def test_get_available_irs(self):
        irs = get_available_irs()
        assert isinstance(irs, list)


class TestGenerateSyntheticMidi:
    def test_midi_note_C4(self):
        assert _midi_note("C", 4) == 60

    def test_midi_note_A4(self):
        assert _midi_note("A", 4) == 69

    def test_midi_note_C3(self):
        assert _midi_note("C", 3) == 48

    def test_is_valid_guitar_note(self):
        assert _is_valid_guitar_note(40) is True  # Low E
        assert _is_valid_guitar_note(88) is True  # High E
        assert _is_valid_guitar_note(30) is False  # Too low
        assert _is_valid_guitar_note(100) is False  # Too high

    def test_create_chord_midi(self, tmp_path):
        out = tmp_path / "C_maj_posE_oct3.mid"
        create_chord_midi("C", "maj", out, octave=3)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_create_progression_midi(self, tmp_path):
        out = tmp_path / "prog_test.mid"
        create_progression_midi(
            [("C", "maj"), ("G", "7"), ("A", "min"), ("F", "maj")],
            out,
            bpm=100,
        )
        assert out.exists()
        assert out.stat().st_size > 0

    def test_midi_note_C_sharp(self):
        assert _midi_note("C#", 3) == 49  # C#3


class TestRenderSyntheticGuitar:
    def test_render_midi_to_chord_label(self, tmp_path):
        midi_path = tmp_path / "C_maj_posE_oct3.mid"
        midi_path.write_text("dummy")
        result = render_midi_to_chord_label(midi_path)
        assert result is not None
        assert result[0] == "C:maj"
        assert result[1] == "chord"

    def test_render_midi_to_chord_label_progression(self, tmp_path):
        midi_path = tmp_path / "prog_0001_bpm100.mid"
        midi_path.write_text("dummy")
        result = render_midi_to_chord_label(midi_path)
        assert result is None  # Progression has no single label

    def test_render_midi_to_chord_label_melody(self, tmp_path):
        midi_path = tmp_path / "melody_0001_bpm100.mid"
        midi_path.write_text("dummy")
        result = render_midi_to_chord_label(midi_path)
        assert result is None

    def test_extract_cqt_shape(self):
        sr = TARGET_SR
        y = np.random.randn(int(sr * 0.3)).astype(np.float32) * 0.01
        features = extract_cqt(y, sr)
        assert features.shape[1] == FEATURE_DIM

    def test_build_windows_shape(self):
        T = 100
        features = np.random.randn(T, FEATURE_DIM).astype(np.float32)
        labels = np.random.randint(0, 10, size=T).astype(np.int32)
        windows, window_labels = build_windows(features, labels)
        expected = (T + 64 - 1) // 64
        assert windows.shape == (expected, WINDOW, FEATURE_DIM)
        assert window_labels.shape == (expected,)
