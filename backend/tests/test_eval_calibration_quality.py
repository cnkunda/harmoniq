"""W5: calibration pooling and recording-quality gate evaluation."""

from __future__ import annotations

import pytest

from scripts.eval_calibration_quality import (
    TrackCalibration,
    _calibration_summary,
    _gate_sweep,
    _pool_bins,
    _quality_distribution,
    _track_rows,
)


def _bins(*, low_weight: float, high_weight: float) -> list[dict]:
    bins = [
        {
            "lower": index / 10,
            "upper": (index + 1) / 10,
            "count": 0,
            "weight": 0.0,
            "avg_confidence": 0.0,
            "accuracy": 0.0,
            "gap": 0.0,
        }
        for index in range(10)
    ]
    bins[0].update(
        {
            "count": 1,
            "weight": low_weight,
            "avg_confidence": 0.05,
            "accuracy": 0.0,
            "gap": 0.05,
        }
    )
    bins[9].update(
        {
            "count": 2,
            "weight": high_weight,
            "avg_confidence": 0.95,
            "accuracy": 0.5,
            "gap": 0.45,
        }
    )
    return bins


def _row(track_id: str, *, low_weight: float, high_weight: float) -> TrackCalibration:
    return TrackCalibration(
        id=track_id,
        source="guitarset",
        split="test",
        instrument_count=1,
        tier="mt3",
        frame_accuracy=0.5,
        bins=_bins(low_weight=low_weight, high_weight=high_weight),
    )


def test_pooling_weights_bins_by_duration():
    pooled = _pool_bins(
        [
            _row("a", low_weight=1.0, high_weight=2.0),
            _row("b", low_weight=1.0, high_weight=2.0),
        ]
    )

    high = pooled[9]
    assert high["count"] == 4
    assert high["weight"] == pytest.approx(4.0)
    assert high["avg_confidence"] == pytest.approx(0.95)
    assert high["accuracy"] == pytest.approx(0.5)
    assert high["gap"] == pytest.approx(0.45)


def test_calibration_summary_reports_duration_weighted_ece():
    summary = _calibration_summary(
        [
            _row("a", low_weight=1.0, high_weight=2.0),
            _row("b", low_weight=1.0, high_weight=2.0),
        ]
    )

    assert summary["total_weight_s"] == pytest.approx(6.0)
    assert summary["samples"] == 6
    assert summary["ece"] == pytest.approx(
        (2 / 6) * 0.05 + (4 / 6) * 0.45, abs=1e-6
    )
    assert summary["overall_accuracy"] == pytest.approx(4 / 6 * 0.5)
    assert summary["mean_confidence"] == pytest.approx(
        (2 / 6) * 0.05 + (4 / 6) * 0.95
    )


def test_track_rows_are_deduplicated_and_sorted():
    report = {
        "tracks": [
            {
                "id": "b",
                "source": "rwc_p",
                "split": "test",
                "instrument_count": 4,
                "tier": "mt3",
                "metrics": {"chords": {"frame_accuracy": 0.25}},
            },
            {
                "id": "a",
                "source": "guitarset",
                "split": "test",
                "instrument_count": 1,
                "tier": "mt3",
                "metrics": {"chords": {"frame_accuracy": None}},
            },
        ]
    }
    rows = _track_rows([report, report])

    assert [row.id for row in rows] == ["a", "b"]
    assert rows[0].frame_accuracy is None
    assert rows[1].frame_accuracy == 0.25


def test_gate_sweep_separates_high_and_low_quality_tracks():
    samples = [
        {
            "id": "clean-1",
            "accuracy": 0.9,
            "quality": {"score": 0.9},
        },
        {
            "id": "clean-2",
            "accuracy": 0.8,
            "quality": {"score": 0.8},
        },
        {
            "id": "noisy-1",
            "accuracy": 0.1,
            "quality": {"score": 0.2},
        },
        {
            "id": "noisy-2",
            "accuracy": 0.2,
            "quality": {"score": 0.3},
        },
    ]

    item = _gate_sweep(
        samples,
        "score",
        higher_is_better=True,
        threshold=0.5,
        accuracy_threshold=0.5,
    )

    assert item is not None
    assert item["accepted"] == 2
    assert item["rejected"] == 2
    assert item["accepted_mean_accuracy"] == pytest.approx(0.85)
    assert item["rejected_mean_accuracy"] == pytest.approx(0.15)
    assert item["separation"] == pytest.approx(0.7)


def test_gate_sweep_returns_none_when_one_side_is_empty():
    samples = [{"id": "a", "accuracy": 0.9, "quality": {"score": 0.9}}]
    assert (
        _gate_sweep(
            samples,
            "score",
            higher_is_better=True,
            threshold=0.5,
            accuracy_threshold=0.5,
        )
        is None
    )


def test_quality_distribution_reports_median():
    result = _quality_distribution([0.1, 0.2, 0.3, 0.4])
    assert result is not None
    assert result["median"] == pytest.approx(0.25)
    assert result["mean"] == pytest.approx(0.25)
    assert result["n"] == 4
    assert _quality_distribution([]) is None


def test_quality_evaluation_joins_accuracy_and_gate(tmp_path):
    import json

    import numpy as np
    import soundfile as sf

    from app.evaluation.manifest import EvalManifest
    from scripts.eval_calibration_quality import _quality_evaluation

    sr = 22050
    t = np.arange(int(sr * 4.0)) / sr
    envelope = 0.15 + 0.85 * np.abs(np.sin(2 * np.pi * 0.7 * t)) ** 2
    clean = envelope * (
        0.25 * np.sin(2 * np.pi * 220.0 * t)
        + 0.125 * np.sin(2 * np.pi * 440.0 * t)
    )
    sf.write(str(tmp_path / "clean.wav"), clean.astype(np.float32), sr, subtype="PCM_16")
    sf.write(
        str(tmp_path / "silent.wav"),
        np.zeros(int(sr * 4.0), dtype=np.float32),
        sr,
        subtype="PCM_16",
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_id": "quality-test",
                "data_root": str(tmp_path),
                "tracks": [
                    {
                        "id": "clean",
                        "audio_path": "clean.wav",
                        "gt_format": "none",
                        "chord_gt_path": "clean.json",
                        "source": "guitarset",
                        "split": "test",
                        "instrument_count": 1,
                    },
                    {
                        "id": "silent",
                        "audio_path": "silent.wav",
                        "gt_format": "none",
                        "chord_gt_path": "silent.json",
                        "source": "guitarset",
                        "split": "test",
                        "instrument_count": 1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    # Ground-truth paths are not read by the quality evaluation, but the
    # manifest resolves them; create placeholders.
    (tmp_path / "clean.json").write_text("[]", encoding="utf-8")
    (tmp_path / "silent.json").write_text("[]", encoding="utf-8")
    manifest = EvalManifest.model_validate(json.loads(manifest_path.read_text()))

    rows = [
        TrackCalibration(
            id="clean",
            source="guitarset",
            split="test",
            instrument_count=1,
            tier="mt3",
            frame_accuracy=0.9,
            bins=[],
        ),
        TrackCalibration(
            id="silent",
            source="guitarset",
            split="test",
            instrument_count=1,
            tier="mt3",
            frame_accuracy=0.1,
            bins=[],
        ),
    ]

    result = _quality_evaluation(rows, manifest, manifest_path, None, 0.5)

    assert result["tracks"] == 2
    assert result["gate"]["true_accept"] == 1
    assert result["gate"]["true_reject"] == 1
    assert result["gate"]["false_accept"] == 0
    assert result["gate"]["false_reject"] == 0
    assert result["distributions"]["score"] is not None
