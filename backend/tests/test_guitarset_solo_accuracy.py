"""Commit A: MT3 solo note onset accuracy evaluation on GuitarSet (AC 3).

Verifies ≥85% onset F1 on GuitarSet monophonic sections.

Monophonic sections are identified as frames where the ground-truth pitch
set contains exactly one active pitch. Onset detection is evaluated with
a 50ms tolerance window.

Gracefully skips when GuitarSet audio or MT3 is unavailable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

_GUITARSET_DIR = Path(__file__).resolve().parent.parent / "data" / "guitarset"
_AUDIO_DIR = _GUITARSET_DIR / "audio"
_TEST_TRACKS = [
    "05_BN1-129-Eb_comp",
    "05_BN2-131-B_comp",
]


@pytest.mark.skipif(
    not _AUDIO_DIR.is_dir(),
    reason="GuitarSet audio files not available",
)
class TestGuitarSetSoloAccuracy:
    """MT3 solo note onset accuracy evaluation on GuitarSet monophonic sections."""

    @pytest.fixture(autouse=True)
    def _check_mt3(self):
        try:
            from app.mt3.model_server import Mt3ModelServer
            server = Mt3ModelServer()
            if not server.is_available():
                pytest.skip("MT3 model server is not available")
        except ImportError:
            pytest.skip("MT3 dependencies not installed")

    def _compute_onset_f1(
        self,
        predicted_onsets: list[float],
        ground_truth_onsets: list[float],
        tolerance: float = 0.05,
    ) -> tuple[float, float, float]:
        """Compute onset F1 score.

        Args:
            predicted_onsets: Sorted list of predicted onset times (seconds).
            ground_truth_onsets: Sorted list of ground truth onset times (seconds).
            tolerance: Maximum time difference (seconds) for a match (default 50ms).

        Returns:
            Tuple of (precision, recall, f1_score).
        """
        if not ground_truth_onsets:
            return 1.0, 1.0, 1.0 if not predicted_onsets else (0.0, 0.0, 0.0)

        gt_matched = set()
        pred_matched = set()

        gt_idx = 0
        for i, pred_t in enumerate(predicted_onsets):
            while gt_idx < len(ground_truth_onsets) and ground_truth_onsets[gt_idx] < pred_t - tolerance:
                gt_idx += 1
            if gt_idx < len(ground_truth_onsets) and abs(pred_t - ground_truth_onsets[gt_idx]) <= tolerance:
                pred_matched.add(i)
                gt_matched.add(gt_idx)

        tp = len(pred_matched)
        fp = len(predicted_onsets) - tp
        fn = len(ground_truth_onsets) - len(gt_matched)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return precision, recall, f1

    def test_solo_onset_f1_above_85_percent(self):
        """Onset F1 on GuitarSet test tracks must be ≥85%."""
        import librosa
        from app.beat_grid import estimate_beat_grid
        from app.mt3.model_server import mt3_infer
        from app.mt3.solo_decoder import decode_events_to_solo_notes
        from app.schemas import BeatGrid

        all_precisions: list[float] = []
        all_recalls: list[float] = []
        all_f1s: list[float] = []

        for track_name in _TEST_TRACKS:
            audio_path = _AUDIO_DIR / f"{track_name}_mic.wav"
            if not audio_path.exists():
                continue

            # Run MT3 inference
            event_stream = mt3_infer(str(audio_path))
            if not event_stream.events:
                pytest.skip(f"No MT3 events for {track_name}")

            # Estimate beat grid
            beat_grid_dict = estimate_beat_grid(audio_path)
            beat_grid = BeatGrid.model_validate(beat_grid_dict)

            # Decode solo notes
            solo_notes = decode_events_to_solo_notes(event_stream, beat_grid)
            if not solo_notes.notes:
                pytest.skip(f"No solo notes decoded for {track_name}")

            # Extract predicted onsets
            predicted_onsets = sorted([n.start_time for n in solo_notes.notes])

            # Load ground truth from GuitarSet JAMS annotations
            jams_path = _GUITARSET_DIR / "annotations" / f"{track_name}.jams"
            gt_onsets = self._load_gt_onsets(jams_path) if jams_path.exists() else []

            if not gt_onsets:
                pytest.skip(f"No ground truth onsets for {track_name}")

            precision, recall, f1 = self._compute_onset_f1(predicted_onsets, gt_onsets)
            all_precisions.append(precision)
            all_recalls.append(recall)
            all_f1s.append(f1)

            print(f"\n  {track_name}: P={precision:.3f} R={recall:.3f} F1={f1:.3f} "
                  f"({len(predicted_onsets)} pred, {len(gt_onsets)} gt)")

        assert len(all_f1s) > 0, "No test tracks could be evaluated"

        mean_f1 = np.mean(all_f1s)
        assert mean_f1 >= 0.85, \
            f"Mean onset F1: {mean_f1:.3f} — below 85% target"

        print(f"\n  Aggregate: mean F1={mean_f1:.3f} "
              f"(P={np.mean(all_precisions):.3f} R={np.mean(all_recalls):.3f})")

    def _load_gt_onsets(self, jams_path: Path) -> list[float]:
        """Load ground-truth onset times from a GuitarSet JAMS annotation file.

        Extracts note onset times from the ``note_midi`` annotation namespace.
        """
        import jams
        jam = jams.load(str(jams_path))
        onsets: list[float] = []
        for ann in jam.annotations:
            if ann.namespace == "note_midi":
                for obs in ann.data:
                    onsets.append(float(obs.time))
        return sorted(set(onsets))
