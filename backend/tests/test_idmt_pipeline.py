"""Tests for IDMT-SMT-Guitar dataset pipeline (Commit 105 Phase 1).

Tests: filename parsing, chord label mapping, CQT extraction,
instrument/style metadata handling.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX, ROOT_NOTES
from scripts.parse_idmt_smt_guitar import (
    _extract_chord_info,
    _normalize_root,
    _build_chord_label,
    scan_idmt_clips,
    save_timelines,
)
from scripts.extract_idmt_cqt import (
    extract_cqt,
    frame_labels_from_timeline,
    build_windows,
    process_clip,
    FEATURE_DIM,
    WINDOW,
    N_CHORD_IDX,
    CHROMA_BINS,
    BASS_BINS,
)


class TestNormalizeRoot:
    def test_C(self):
        assert _normalize_root("C") == "C"

    def test_G(self):
        assert _normalize_root("G") == "G"

    def test_C_sharp(self):
        assert _normalize_root("C#") == "C#"

    def test_D_flat_becomes_C_sharp(self):
        assert _normalize_root("Db") == "C#"

    def test_G_flat(self):
        assert _normalize_root("Gb") == "F#"

    def test_invalid(self):
        assert _normalize_root("X") is None


class TestExtractChordInfo:
    def test_major_arpeggio(self):
        info = _extract_chord_info("C_major_arpeggio_acoustic.wav")
        assert info is not None
        assert info["root"] == "C"
        assert info["quality"] == "maj"
        assert info["style"] == "arpeggio"
        assert info["instrument"] == "acoustic"

    def test_minor_strum_electric(self):
        info = _extract_chord_info("A_minor_strum_electric.wav")
        assert info["root"] == "A"
        assert info["quality"] == "min"
        assert info["style"] == "strum"
        assert info["instrument"] == "electric_clean"

    def test_seventh_chord(self):
        info = _extract_chord_info("G7_arpeggio_distortion.wav")
        assert info["root"] == "G"
        assert info["quality"] == "7"
        assert info["style"] == "arpeggio"

    def test_maj7_chord(self):
        info = _extract_chord_info("F#_maj7_picked_acoustic.wav")
        assert info["root"] == "F#"
        assert info["quality"] == "maj7"
        assert info["style"] == "picked"

    def test_dim_chord(self):
        info = _extract_chord_info("B_dim_strum_electric.wav")
        assert info["root"] == "B"
        assert info["quality"] == "dim"

    def test_aug_chord(self):
        info = _extract_chord_info("D_aug_arpeggio.wav")
        assert info["root"] == "D"
        assert info["quality"] == "aug"

    def test_single_note(self):
        info = _extract_chord_info("single_C4_picked.wav")
        assert info is not None
        assert info["is_single_note"] is True

    def test_flat_root(self):
        info = _extract_chord_info("Bb_major_strum_acoustic.wav")
        assert info["root"] == "A#"

    def test_unknown_style(self):
        info = _extract_chord_info("E_major_bowing_acoustic.wav")
        assert info["style"] == "strum"  # default
        assert info["root"] == "E"
        assert info["quality"] == "maj"


class TestBuildChordLabel:
    def test_C_maj(self):
        assert _build_chord_label("C", "maj") == "C:maj"

    def test_F_sharp_min7(self):
        assert _build_chord_label("F#", "min7") == "F#:min7"

    def test_G_flat_is_same_as_F_sharp(self):
        from app.chord_vocab import CHORD_TO_IDX
        assert "F#:maj" in CHORD_TO_IDX


class TestScanIdmtClips:
    def test_no_audio_dir(self, tmp_path):
        clips = scan_idmt_clips(tmp_path / "nonexistent")
        assert clips == {}

    def test_empty_audio_dir(self, tmp_path):
        clips = scan_idmt_clips(tmp_path)
        assert clips == {}

    def test_scans_wav_files(self, tmp_path):
        # Create a synthetic WAV file
        import soundfile as sf
        sr = 44100
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 440 * t) * 0.1

        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        wav_path = audio_dir / "C_major_arpeggio_acoustic.wav"
        sf.write(str(wav_path), y, sr)

        clips = scan_idmt_clips(audio_dir)
        assert "C_major_arpeggio_acoustic" in clips
        entry = clips["C_major_arpeggio_acoustic"][0]
        assert entry["chord"] == "C:maj"
        assert entry["instrument"] == "acoustic"
        assert entry["style"] == "arpeggio"
        assert entry["end"] > 0

    def test_save_timelines(self, tmp_path):
        clips = {
            "test_clip": [{"start": 0.0, "end": 1.0, "chord": "C:maj",
                          "instrument": "acoustic", "style": "strum",
                          "path": "/fake/path.wav"}],
        }
        out_dir = tmp_path / "timelines"
        save_timelines(clips, out_dir)
        saved = json.loads((out_dir / "test_clip.json").read_text())
        assert saved[0]["chord"] == "C:maj"
        assert saved[0]["instrument"] == "acoustic"
        assert saved[0]["style"] == "strum"


class TestFrameLabelsFromTimeline:
    def test_single_segment(self):
        timeline = [{"start": 0.0, "end": 1.0, "chord": "C:maj"}]
        labels = frame_labels_from_timeline(timeline, 15)
        assert labels[0] == CHORD_TO_IDX["C:maj"]
        assert labels[14] == N_CHORD_IDX  # past the end

    def test_no_chord_segment(self):
        timeline = [{"start": 0.0, "end": 1.0, "chord": None}]
        labels = frame_labels_from_timeline(timeline, 10)
        assert np.all(labels == N_CHORD_IDX)


class TestBuildWindows:
    def test_window_shape(self):
        T = 200
        features = np.random.randn(T, FEATURE_DIM).astype(np.float32)
        labels = np.random.randint(0, 10, size=T).astype(np.int32)
        windows, window_labels = build_windows(features, labels)
        expected = (T + 64 - 1) // 64
        assert windows.shape == (expected, WINDOW, FEATURE_DIM)
        assert window_labels.shape == (expected,)

    def test_center_frame_label(self):
        features = np.zeros((200, FEATURE_DIM), dtype=np.float32)
        labels = np.full(200, N_CHORD_IDX, dtype=np.int32)
        labels[0] = 5
        _, window_labels = build_windows(features, labels)
        assert window_labels[0] == 5


class TestExtractCqt:
    def test_output_shape(self):
        sr = 44100
        y = np.random.randn(sr * 2) * 0.01
        features = extract_cqt(y, sr)
        assert features.shape[1] == FEATURE_DIM

    def test_normalization(self):
        sr = 44100
        y = np.random.randn(sr * 1) * 0.01
        features = extract_cqt(y, sr)
        cqt_part = features[:, :CHROMA_BINS]
        row_sums = cqt_part.sum(axis=1)
        assert np.allclose(row_sums, 1.0, atol=0.15)

    def test_bass_channel(self):
        sr = 44100
        y = np.random.randn(sr * 1) * 0.01
        features = extract_cqt(y, sr)
        bass_part = features[:, CHROMA_BINS:]
        assert bass_part.shape[1] == BASS_BINS
        assert bass_part.min() >= 0


class TestProcessClip:
    def test_process_clip_with_metadata(self, tmp_path):
        import soundfile as sf

        sr = 44100
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 440 * t) * 0.1

        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        audio_path = audio_dir / "C_major_strum_acoustic.wav"
        sf.write(str(audio_path), y, sr)

        timeline_dir = tmp_path / "timelines"
        timeline_dir.mkdir()
        timeline_path = timeline_dir / "C_major_strum_acoustic.json"
        with open(timeline_path, "w") as f:
            json.dump([{"start": 0.0, "end": 2.0, "chord": "C:maj",
                       "instrument": "acoustic", "style": "strum",
                       "path": str(audio_path)}], f)

        output_dir = tmp_path / "cqt"
        result = process_clip(audio_path, timeline_path, output_dir, force=True)
        assert result is not None
        assert result["track_id"] == "C_major_strum_acoustic"

        npz_path = output_dir / "C_major_strum_acoustic.npz"
        assert npz_path.exists()
        data = np.load(npz_path)
        assert "features" in data
        assert "labels" in data
        assert "source" in data
        assert str(data["source"]) == "idmt"
        assert "instrument" in data
        assert "loss_weight" in data
        assert float(data["loss_weight"]) == 1.0
