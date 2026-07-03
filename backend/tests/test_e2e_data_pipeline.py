"""End-to-end data pipeline test: MIDI → render → CQT → windows.

Verifies the full synthetic data pipeline produces valid .npz output
with correct shapes and metadata.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX
from app.cqt_constants import WINDOW, HOP_FRAMES, FEATURE_DIM


class TestSyntheticPipelineE2E:
    """Full pipeline test with scipy-based guitar tone synthesizer."""

    def test_cqt_extraction_shape(self, sine_wave_audio):
        """Verify CQT feature shape from the render_synthetic_guitar pipeline."""
        from scripts.render_synthetic_guitar import extract_cqt, build_windows

        y, sr = sine_wave_audio
        features = extract_cqt(y, sr)
        assert features.ndim == 2
        assert features.shape[1] == FEATURE_DIM
        assert features.shape[0] > 0

        labels = np.full(features.shape[0], CHORD_TO_IDX["C:maj"], dtype=np.int32)
        windows, window_labels = build_windows(features, labels)

        assert windows.ndim == 3
        assert windows.shape[1] == WINDOW
        assert windows.shape[2] == FEATURE_DIM
        assert window_labels.ndim == 1
        assert len(window_labels) == len(windows)

    def test_synthetic_chord_render_and_cqt(self, sine_wave_audio):
        """Render a chord through the synth and verify CQT."""
        from app.synth_guitar import render_chord
        from scripts.render_synthetic_guitar import extract_cqt, build_windows

        # C:maj → root=60 (MIDI C4), intervals=[0, 4, 7]
        y = render_chord(root_midi=60, intervals=[0, 4, 7], duration=1.0)
        assert len(y) > 0

        sr = 44100
        features = extract_cqt(y, sr)
        assert features.shape[1] == FEATURE_DIM

        labels = np.full(features.shape[0], CHORD_TO_IDX["C:maj"], dtype=np.int32)
        windows, window_labels = build_windows(features, labels)

        assert len(window_labels) == len(windows)
        assert window_labels[0] == CHORD_TO_IDX["C:maj"]

    def test_extract_cqt_from_wav(self, tmp_path):
        """Test extract_cqt_from_wav produces valid .npz from a WAV file."""
        import soundfile as sf

        from scripts.render_synthetic_guitar import extract_cqt_from_wav

        sr = 44100
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        y = (np.sin(2 * np.pi * 440 * t) * 0.1).astype(np.float32)

        wav_path = tmp_path / "test_chord.wav"
        sf.write(str(wav_path), y, sr)

        result = extract_cqt_from_wav(wav_path, "C:maj", "chord", tmp_path / "cqt", force=True)
        assert result is not None
        assert result["track_id"] == "test_chord"

        npz_path = tmp_path / "cqt" / "test_chord.npz"
        assert npz_path.exists()
        data = np.load(npz_path)
        assert data["features"].shape[1] == WINDOW
        assert data["features"].shape[2] == FEATURE_DIM
        assert data["source"] == "vst"

    def test_guitarset_extraction_pipeline(self, sine_wave_audio):
        """Run the GuitarSet extraction pipeline with synthetic data."""
        from scripts.extract_guitarset_cqt import _extract_cqt, _build_windows

        y, sr = sine_wave_audio
        features = _extract_cqt(y, sr)
        assert features.shape[1] == FEATURE_DIM

        labels = np.full(features.shape[0], CHORD_TO_IDX["C:maj"], dtype=np.int32)
        windows, window_labels = _build_windows(features, labels)

        T = len(windows)
        assert T > 0
        assert window_labels.shape == (T,)
        assert np.all(window_labels == CHORD_TO_IDX["C:maj"])

    def test_idmt_extraction_pipeline(self, sine_wave_audio):
        """Run the IDMT extraction pipeline with synthetic data."""
        from scripts.extract_idmt_cqt import extract_cqt, build_windows

        y, sr = sine_wave_audio
        features = extract_cqt(y, sr)
        assert features.shape[1] == FEATURE_DIM

        labels = np.full(features.shape[0], CHORD_TO_IDX["C:maj"], dtype=np.int32)
        windows, window_labels = build_windows(features, labels)

        assert len(windows) > 0
        assert window_labels.dtype == np.int32

    def test_process_song_roundtrip(self, tmp_path):
        """Song-level processing: write WAV + timeline → process_song."""
        import soundfile as sf

        from scripts.extract_guitarset_cqt import process_song

        sr = 44100
        y = np.sin(2 * np.pi * 440 * np.linspace(0, 2.0, int(sr * 2.0))) * 0.1
        y = y.astype(np.float32)

        song_id = "00_BN1-129-Eb_comp"
        audio_path = tmp_path / f"{song_id}.wav"
        sf.write(str(audio_path), y, sr)

        timeline = [
            {"start": 0.0, "end": 1.0, "chord": "C:maj"},
            {"start": 1.0, "end": 2.0, "chord": "G:7"},
        ]
        tl_dir = tmp_path / "timelines"
        tl_dir.mkdir()
        tl_path = tl_dir / f"{song_id}.json"
        with open(tl_path, "w") as f:
            json.dump(timeline, f)

        cqt_dir = tmp_path / "cqt"
        result = process_song(audio_path, tl_path, cqt_dir, force=True)

        assert result is not None
        assert result["track_id"] == song_id
        assert result["split"] == "train"

        npz_path = cqt_dir / f"{song_id}.npz"
        assert npz_path.exists()
        data = np.load(npz_path)
        assert data["features"].shape[1] == WINDOW
        assert data["features"].shape[2] == FEATURE_DIM
        assert str(data["player_id"]) == "00"
        assert str(data["split"]) == "train"
