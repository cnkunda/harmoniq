"""W1 data-engine tests: splits, manifest validation, confidence, features."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.data_engine.confidence import (
    NO_CHORD_INDEX,
    PseudoLabelConfig,
    chord_intervals,
    has_confident_chord,
    label_windows,
)
from app.data_engine.manifest import W1Manifest, W1Track
from app.data_engine.splits import deterministic_split


class TestDeterministicSplit:
    def test_is_stable(self):
        assert deterministic_split("idmt:abc") == deterministic_split("idmt:abc")

    def test_changes_with_salt(self):
        values = {
            deterministic_split("idmt:abc", salt=f"salt-{index}")
            for index in range(10)
        }
        assert len(values) > 1

    def test_invalid_ratios_fail(self):
        with pytest.raises(ValueError):
            deterministic_split("x", train_ratio=1.2)
        with pytest.raises(ValueError):
            deterministic_split("x", train_ratio=0.8, val_ratio=0.3)

    def test_roughly_respects_ratios(self):
        counts = {"train": 0, "val": 0, "test": 0}
        for index in range(2000):
            counts[deterministic_split(f"track-{index}")] += 1
        assert counts["train"] > counts["val"]
        assert counts["train"] > counts["test"]
        assert 0.75 < counts["train"] / 2000 < 0.85


class TestW1Manifest:
    def _track(self, **overrides):
        payload = {
            "id": "t1",
            "audio_path": "audio.wav",
            "source": "unit",
            "licence_id": "CC-BY-4.0",
            "split": "train",
            "label_status": "none",
            "label_channels": ["chord", "solo"],
        }
        payload.update(overrides)
        return payload

    def test_none_labels_cannot_have_paths(self):
        with pytest.raises(ValueError, match="must not set label paths"):
            W1Track(**self._track(chord_label_path="timeline.json"))

    def test_labeled_track_requires_a_path(self):
        with pytest.raises(ValueError, match="requires chord_label_path"):
            W1Track(**self._track(label_status="human"))

    def test_duplicate_ids_rejected(self):
        with pytest.raises(ValueError, match="duplicate track ids"):
            W1Manifest(
                manifest_id="m",
                tracks=[W1Track(**self._track()), W1Track(**self._track())],
            )

    def test_valid_manifest(self):
        manifest = W1Manifest(
            manifest_id="m",
            tracks=[
                W1Track(**self._track()),
                W1Track(**self._track(id="t2", label_status="human", chord_label_path="c.json")),
            ],
        )
        assert len(manifest.tracks) == 2


class TestConfidenceFiltering:
    def _intervals(self):
        from dataclasses import dataclass

        @dataclass
        class Event:
            timestamp: float
            chord: str
            confidence: float

        events = [
            Event(0.0, "C:maj", 0.9),
            Event(2.0, "G:maj", 0.4),
            Event(4.0, "N", 1.0),
        ]
        return chord_intervals(events, audio_duration=6.0)

    def test_intervals_use_next_timestamp(self):
        intervals = self._intervals()
        assert intervals[0].start == 0.0
        assert intervals[0].end == 2.0
        assert intervals[-1].end == 6.0

    def test_threshold_drops_low_confidence_windows(self):
        config = PseudoLabelConfig(min_chord_confidence=0.6)
        labels, confidences, keep = label_windows(
            self._intervals(), [0.5, 2.5, 4.5], config
        )
        assert keep == [True, False, True]
        assert labels[0] != NO_CHORD_INDEX
        assert labels[1] != NO_CHORD_INDEX
        assert labels[2] == NO_CHORD_INDEX

    def test_no_covering_interval_is_dropped(self):
        labels, confidences, keep = label_windows(
            self._intervals(), [99.0], PseudoLabelConfig()
        )
        assert labels == [NO_CHORD_INDEX]
        assert confidences == [0.0]
        assert keep == [False]

    def test_has_confident_chord(self):
        assert has_confident_chord([1, NO_CHORD_INDEX], [True, True])
        assert not has_confident_chord([NO_CHORD_INDEX], [True])


class TestCqtFeatures:
    def test_extracts_training_window_shape(self, tmp_path):
        import soundfile as sf

        sample_rate = 44100
        t = np.linspace(0, 1.0, sample_rate, endpoint=False)
        audio = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        path = tmp_path / "tone.wav"
        sf.write(str(path), audio, sample_rate)

        from app.data_engine.features import extract_cqt_windows

        windows, centers = extract_cqt_windows(path)
        assert windows.shape[1:] == (128, 144)
        assert len(windows) == len(centers)
        assert np.all(np.isfinite(windows))
        # Real frames are L1-normalized; padded frames are zeros.
        real_frames = windows.sum(axis=2) > 0
        assert np.allclose(windows[real_frames].sum(axis=1), 1.0, atol=1e-5)


class TestCommittedW1Manifest:
    def test_manifest_has_a_thousand_plus_tracks_and_no_holdout_leak(self):
        from pathlib import Path

        from app.data_engine.manifest import load_w1_manifest
        from app.evaluation.manifest import load_manifest as load_eval

        repo = Path(__file__).resolve().parents[2]
        w1 = load_w1_manifest(repo / "docs" / "eval" / "w1_dataset_manifest.json")
        eval_manifest = load_eval(repo / "docs" / "eval" / "amt_manifest.json")

        assert len(w1.tracks) >= 1000
        assert len({track.id for track in w1.tracks}) == len(w1.tracks)

        holdout = {
            track.audio_path
            for track in eval_manifest.tracks
            if track.split in ("test", "val")
        }
        train = {track.audio_path for track in w1.tracks if track.split == "train"}
        assert holdout & train == set()
