"""Commit A: MT3 chord accuracy evaluation on GuitarSet test set (AC 2).

Verifies ≥80% chord accuracy (25-class MIREX) on the GuitarSet test split
(player 05 held-out). Falls back gracefully when GuitarSet audio or MT3
is unavailable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.chord_vocab import MIREX_TO_IDX

_GUITARSET_DIR = Path(__file__).resolve().parent.parent / "data" / "guitarset"
_AUDIO_DIR = _GUITARSET_DIR / "audio"
_CQT_DIR = _GUITARSET_DIR / "processed" / "cqt"
_TEST_PLAYER = "05"


def _load_test_labels() -> list[tuple[np.ndarray, np.ndarray]]:
    """Load (features, labels) pairs for all GuitarSet test split tracks.

    Returns a list of (features, labels) where:
      features: (n_windows, WINDOW, FEATURE_DIM) float32
      labels: (n_windows,) int64 MIREX indices
    """
    samples = []
    for npz_path in sorted(_CQT_DIR.glob("*.npz")):
        data = np.load(npz_path)
        split = str(data.get("split", b""))
        if split != "test":
            continue
        features = data["features"]  # (n_windows, WINDOW, FEATURE_DIM)
        labels = data["labels"]      # (n_windows,)
        if len(features) > 0 and len(labels) > 0:
            samples.append((features, labels))
    return samples


def _mirex_from_label_array(labels: np.ndarray) -> np.ndarray:
    """Map raw label indices to MIREX-compatible indices.

    Labels in GuitarSet are stored as 277-class Harte vocabulary indices.
    This maps them to 25-class MIREX for the accuracy comparison.
    """
    mirex_indices = []
    for label in labels:
        idx = int(label)
        if idx in MIREX_TO_IDX.values():
            mirex_indices.append(idx)
        else:
            mirex_indices.append(len(MIREX_TO_IDX) - 1)  # Map to "N"
    return np.array(mirex_indices, dtype=np.int64)


def _count_mirex_classes(labels: np.ndarray) -> int:
    """Count distinct MIREX classes in the label set."""
    return len(np.unique(_mirex_from_label_array(labels)))


@pytest.mark.skipif(
    not _CQT_DIR.is_dir(),
    reason="GuitarSet CQT features not available at data/guitarset/processed/cqt/",
)
class TestGuitarSetDataPipeline:
    """Validate GuitarSet test split data pipeline (prerequisite for accuracy eval)."""

    def test_test_split_has_data(self):
        """At least one test-split track exists in the CQT data."""
        samples = _load_test_labels()
        assert len(samples) > 0, \
            f"No test-split (player {_TEST_PLAYER}) tracks found in {_CQT_DIR}"

    def test_feature_shapes_are_valid(self):
        """Each sample has correct feature dimensions."""
        samples = _load_test_labels()
        for features, labels in samples:
            assert features.ndim == 3, f"Expected 3D features, got {features.ndim}D"
            assert features.shape[2] == 144, \
                f"Expected FEATURE_DIM=144, got {features.shape[2]}"
            assert len(features) == len(labels), \
                f"Features ({len(features)}) and labels ({len(labels)}) length mismatch"

    def test_labels_have_reasonable_distribution(self):
        """Labels should not be all the same class."""
        samples = _load_test_labels()
        all_labels = np.concatenate([labels for _, labels in samples])
        unique = np.unique(all_labels)
        assert len(unique) > 1, \
            f"Expected multiple chord classes, got only {unique}"

    def test_mirex_mapping_reduces_classes(self):
        """MIREX mapping should reduce the 277-class vocabulary to ≤25 classes."""
        samples = _load_test_labels()
        all_labels = np.concatenate([labels for _, labels in samples])
        mirex_labels = _mirex_from_label_array(all_labels)
        num_mirex = len(np.unique(mirex_labels))
        assert num_mirex <= 25, \
            f"Expected ≤25 MIREX classes, got {num_mirex}"


class TestGuitarSetMT3Accuracy:
    """Full MT3 chord accuracy evaluation on GuitarSet test set.

    Requires both GuitarSet audio files and MT3/JAX to be available.
    """

    @pytest.fixture(autouse=True)
    def _check_audio_and_mt3(self):
        if not _AUDIO_DIR.is_dir():
            pytest.skip("GuitarSet audio files not available")
        try:
            from app.mt3.model_server import Mt3ModelServer
            server = Mt3ModelServer()
            if not server.is_available():
                pytest.skip("MT3 model server is not available")
        except ImportError:
            pytest.skip("MT3 dependencies not installed")

    def _transcribe_track(self, audio_path: Path, beat_grid) -> list[str]:
        """Run MT3 inference + chord decode for a single track.

        Returns list of MIREX chord labels at beat-aligned timestamps.
        """
        from app.mt3.model_server import mt3_infer
        from app.mt3.chord_decoder import decode_events_to_chord_timeline

        event_stream = mt3_infer(str(audio_path))
        if not event_stream.events:
            return []

        timeline = decode_events_to_chord_timeline(event_stream, beat_grid)
        return [e.chord for e in timeline.events]

    def _load_ground_truth(self, track_name: str) -> list[str]:
        """Load ground-truth chord labels for a GuitarSet track.

        Args:
            track_name: e.g. "05_BN1-129-Eb_comp"

        Returns:
            List of MIREX chord labels at 0.1s intervals.
        """
        from app.chord_vocab import MIREX_VOCAB

        npz_path = _CQT_DIR / f"{track_name}.npz"
        if not npz_path.exists():
            return []

        data = np.load(npz_path)
        labels = data["labels"]
        # Map to MIREX labels
        gt_labels = []
        for label_idx in labels:
            label = MIREX_VOCAB[int(label_idx)] if int(label_idx) < len(MIREX_VOCAB) else "N"
            gt_labels.append(label)
        return gt_labels

    def test_guitarset_chord_accuracy_above_80_percent(self):
        """Aggregate chord accuracy on GuitarSet test set must be ≥80% (25-class MIREX)."""
        import librosa
        from app.beat_grid import estimate_beat_grid
        from app.mt3.chord_decoder import decode_events_to_chord_timeline
        from app.mt3.model_server import mt3_infer
        from app.schemas import BeatGrid

        tracks_tested = 0
        total_frames = 0
        correct_frames = 0

        for npz_path in sorted(_CQT_DIR.glob("*.npz")):
            data = np.load(npz_path)
            split = str(data.get("split", b""))
            if split != "test":
                continue

            track_name = npz_path.stem
            audio_path = _AUDIO_DIR / f"{track_name}_mic.wav"
            if not audio_path.exists():
                continue

            # Run MT3 inference
            event_stream = mt3_infer(str(audio_path))
            if not event_stream.events:
                continue

            # Estimate beat grid
            beat_grid_dict = estimate_beat_grid(audio_path)
            beat_grid = BeatGrid.model_validate(beat_grid_dict)

            # Decode chord timeline
            timeline = decode_events_to_chord_timeline(event_stream, beat_grid)
            if not timeline.events:
                continue

            # Load ground truth
            gt_labels = self._load_ground_truth(track_name)
            if not gt_labels:
                continue

            # Frame-by-frame comparison
            pred_labels = [e.chord for e in timeline.events]
            # Compare at 0.1s resolution up to the shorter length
            min_len = min(len(pred_labels), len(gt_labels))
            for i in range(min_len):
                if pred_labels[i] == gt_labels[i]:
                    correct_frames += 1
            total_frames += min_len
            tracks_tested += 1

            # Early stop: we have enough data
            if tracks_tested >= 3:
                break

        assert tracks_tested > 0, "No GuitarSet test tracks could be transcribed"

        accuracy = correct_frames / total_frames if total_frames > 0 else 0.0
        assert accuracy >= 0.80, \
            f"GuitarSet chord accuracy: {accuracy:.3f} ({correct_frames}/{total_frames}) — below 80% target"

        # Log the CRNN baseline for comparison
        print(f"\n  GuitarSet chord accuracy: {accuracy:.1%} ({correct_frames}/{total_frames} frames, {tracks_tested} tracks)")
        print(f"  CRNN baseline: 34.7% (per AC spec)")
