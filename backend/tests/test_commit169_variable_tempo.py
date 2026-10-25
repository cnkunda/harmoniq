"""Tests for Commit 169: variable-tempo beat grid."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from app.beat_grid import (
    BEAT_TRACK_SR,
    BeatGridComputationError,
    _beat_grid_from_tempo_curve,
    _normalize_tempo_curve,
    _uniform_beat_grid,
    estimate_beat_grid,
)
from app.schemas import BeatGrid, BeatGridRecomputeRequest, TempoChange


class _FakeLibrosa:
    """Minimal librosa stand-in: only audio loading is needed on curve paths."""

    def __init__(self, duration_s: float) -> None:
        self.duration_s = duration_s

    def load(self, path: str, sr: int, mono: bool) -> tuple[np.ndarray, int]:
        return np.zeros(int(sr * self.duration_s), dtype=np.float32), sr


def _fake_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duration_s: float) -> Path:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"fake")
    monkeypatch.setattr("app.beat_grid.librosa", _FakeLibrosa(duration_s))
    return audio


class TestUniformGridBackwardCompatibility:
    def test_uniform_grid_matches_static_bpm(self):
        assert _uniform_beat_grid(2.0, 120.0) == [0.0, 0.5, 1.0, 1.5, 2.0]

    def test_static_override_path_unchanged(self, tmp_path, monkeypatch):
        audio = _fake_audio(tmp_path, monkeypatch, duration_s=2.0)

        result = estimate_beat_grid(audio, bpm_override=120.0)

        assert result["beats"] == [0.0, 0.5, 1.0, 1.5, 2.0]
        assert result["pulse_bpm"] == 120.0
        assert result["bpm"] == 120.0
        assert result["downbeats"] == [0.0, 2.0]
        assert result["tempo_changes"] == []

    def test_tempo_curve_and_override_are_mutually_exclusive(self, tmp_path, monkeypatch):
        audio = _fake_audio(tmp_path, monkeypatch, duration_s=4.0)

        with pytest.raises(BeatGridComputationError, match="not both"):
            estimate_beat_grid(
                audio,
                bpm_override=120.0,
                tempo_curve=[(0.0, 60.0), (4.0, 120.0)],
            )


class TestTempoCurveGrid:
    def test_linear_ramp_accelerates(self):
        beats = _beat_grid_from_tempo_curve(8.0, [(0.0, 60.0), (4.0, 120.0)])

        assert beats[0] == 0.0
        assert beats[-1] == 8.0
        first_interval = beats[1] - beats[0]
        last_interval = beats[-1] - beats[-2]
        assert first_interval > last_interval
        assert last_interval == pytest.approx(0.5, abs=1e-6)

    def test_sudden_shift_holds_previous_tempo_until_instant(self):
        beats = _beat_grid_from_tempo_curve(
            8.0,
            [(0.0, 60.0), (4.0, 60.0), (4.0, 120.0)],
        )

        before_shift = [b for b in beats if b < 4.0]
        assert before_shift == [0.0, 1.0, 2.0, 3.0]
        assert 4.0 in beats
        after_shift = [beats[i + 1] - beats[i] for i in range(len(beats) - 1) if beats[i] >= 4.0]
        assert after_shift
        assert all(interval == pytest.approx(0.5, abs=1e-6) for interval in after_shift)

    def test_curve_is_extended_to_track_duration(self):
        points = _normalize_tempo_curve(8.0, [(0.0, 90.0), (2.0, 90.0)])

        assert points == [(0.0, 90.0), (2.0, 90.0), (8.0, 90.0)]

    def test_invalid_curve_fails_loudly(self):
        with pytest.raises(BeatGridComputationError, match="at least one"):
            _beat_grid_from_tempo_curve(4.0, [])
        with pytest.raises(BeatGridComputationError, match="non-negative"):
            _beat_grid_from_tempo_curve(4.0, [(-1.0, 120.0)])
        with pytest.raises(BeatGridComputationError, match="positive"):
            _beat_grid_from_tempo_curve(4.0, [(0.0, 0.0)])
        with pytest.raises(BeatGridComputationError, match="pair"):
            _beat_grid_from_tempo_curve(4.0, [(0.0,)])

    def test_rejects_bpm_outside_schema_range(self, tmp_path, monkeypatch):
        audio = _fake_audio(tmp_path, monkeypatch, duration_s=4.0)

        with pytest.raises(BeatGridComputationError, match="between 20 and 300"):
            estimate_beat_grid(audio, tempo_curve=[(0.0, 10.0)])


class TestEstimateWithTempoCurve:
    def test_returns_tempo_changes_and_schema_accepts_them(self, tmp_path, monkeypatch):
        audio = _fake_audio(tmp_path, monkeypatch, duration_s=8.0)

        result = estimate_beat_grid(
            audio,
            tempo_curve=[(0.0, 60.0), (4.0, 120.0)],
        )

        assert result["tempo_changes"] == [
            {"time": 0.0, "bpm": 60.0},
            {"time": 4.0, "bpm": 120.0},
        ]
        assert result["pulse_bpm"] == pytest.approx(105.0)
        assert result["bpm"] == pytest.approx(105.0)

        grid = BeatGrid.model_validate(result)
        assert grid.tempo_changes == [
            TempoChange(time=0.0, bpm=60.0),
            TempoChange(time=4.0, bpm=120.0),
        ]

    def test_downbeats_follow_transitions_in_4_4(self, tmp_path, monkeypatch):
        audio = _fake_audio(tmp_path, monkeypatch, duration_s=8.0)

        result = estimate_beat_grid(audio, tempo_curve=[(0.0, 60.0), (4.0, 120.0)])
        beats = result["beats"]
        downbeats = result["downbeats"]

        assert downbeats == beats[::4]
        assert downbeats == [0.0, 2.928203, 5.0, 7.0]
        assert downbeats[0] == 0.0
        assert any(2.5 < t < 3.5 for t in downbeats)

    def test_compound_meter_subdivisions_follow_local_tempo(self, tmp_path, monkeypatch):
        audio = _fake_audio(tmp_path, monkeypatch, duration_s=8.0)

        result = estimate_beat_grid(
            audio,
            time_signature="6/8",
            tempo_curve=[(0.0, 120.0), (8.0, 60.0)],
        )
        beats = result["beats"]

        assert result["time_signature"] == {"numerator": 6, "denominator": 8}
        assert result["tick_value"] == 0.125
        assert len(beats) % 3 == 1
        for index in range(0, len(beats) - 3, 3):
            first_gap = beats[index + 1] - beats[index]
            second_gap = beats[index + 2] - beats[index + 1]
            assert first_gap == pytest.approx(second_gap, abs=2e-6)
        early_gap = beats[1] - beats[0]
        late_gap = beats[-1] - beats[-2]
        assert early_gap < late_gap

    def test_variable_grid_generation_under_100ms_for_five_minutes(self):
        curve = [(float(t), 60.0 + (t % 120.0) * 0.5) for t in range(0, 300, 10)]
        start = time.perf_counter()

        beats = _beat_grid_from_tempo_curve(300.0, curve)

        elapsed = time.perf_counter() - start
        assert beats[0] == 0.0
        assert 295.0 < beats[-1] <= 300.0
        assert elapsed < 0.1


class TestRecomputeRequestValidation:
    def test_accepts_tempo_curve_pairs(self):
        req = BeatGridRecomputeRequest(tempo_curve=[(0.0, 90.0), (12.5, 120.0)])

        assert req.tempo_curve == [(0.0, 90.0), (12.5, 120.0)]

    def test_rejects_curve_and_bpm_override_together(self):
        with pytest.raises(ValueError, match="not both"):
            BeatGridRecomputeRequest(
                bpm_override=120.0,
                tempo_curve=[(0.0, 120.0)],
            )
