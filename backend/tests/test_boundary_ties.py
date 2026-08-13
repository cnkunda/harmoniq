"""Tests for Commit 100: Segment Boundary Tie Mechanism (MT3 Paper Insight).

Covers:
  - Overlap-and-blend window layout: every frame covered, overlap zones blend
    predictions weighted toward the nearer window center, and a chord held
    across a window boundary resolves to the nearer window's chord without
    flicker (single event, not two).
  - Boundary confidence penalty: confidence scaled down for frames within the
    edge zone of the track, unchanged in the interior.
  - Edge flicker counting: chord changes inside boundary zones are counted
    (the metric the penalty suppresses).
  - Active-note tie mechanism for solo notes: notes held across a segment
    boundary merge into a single event; forgotten notes survive; distinct
    attacks are never merged.
  - Boundary onset damping for fresh (untied) onsets near segment starts.
  - Segment range geometry.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.chord_inference import (
    _BOUNDARY_CONFIDENCE_FACTOR,
    _BOUNDARY_PENALTY_FRAMES,
    _apply_boundary_penalty,
    _boundary_metrics_for_frames,
    _edge_flicker_events,
    _window_layout,
    _WINDOW_STRIDE,
)
from app.schemas import BeatGrid
from app.solo_inference import (
    _dampen_boundary_onsets,
    _segment_ranges,
    merge_segments_with_ties,
    SEGMENT_OVERLAP_S,
)


@pytest.fixture
def fake_basic_pitch(monkeypatch):
    """Provide a lightweight basic_pitch fake for ML-free integration tests.

    Importing real basic-pitch triggers the multi-minute TensorFlow
    initialization on this machine; the fake supplies a path-like
    ICASSP_2022_MODEL_PATH and an injectable ``predict``. The fake is removed
    from ``sys.modules`` afterward so other test files that need the real
    (or missing) module are unaffected.
    """
    if "basic_pitch" in sys.modules:
        yield sys.modules["basic_pitch"].inference
        return
    model_path = MagicMock(spec=Path)
    model_path.is_dir.return_value = True
    model_path.suffix = ""
    model_path.exists.return_value = True
    model_path.name = "nmp"

    bp_mod = SimpleNamespace(ICASSP_2022_MODEL_PATH=model_path)
    inf_mod = SimpleNamespace(predict=None)
    sys.modules["basic_pitch"] = bp_mod
    sys.modules["basic_pitch.inference"] = inf_mod
    yield inf_mod
    del sys.modules["basic_pitch"]
    del sys.modules["basic_pitch.inference"]


# ---------------------------------------------------------------------------
# Chord: overlap-and-blend window layout
# ---------------------------------------------------------------------------


class TestOverlapBlendLayout:
    def test_every_frame_covered(self):
        for T in (1, 2, 10, 128, 200, 513):
            _centers, weights = _window_layout(T)
            coverage = weights.sum(axis=0)
            assert np.all(coverage > 0), f"frame left uncovered for T={T}"

    def test_overlap_zone_gets_two_windows(self):
        T = 200
        centers, weights = _window_layout(T)
        coverage = weights.sum(axis=0)
        # Between centers 64 and 128 the frame 96 is 32 frames from each center
        assert coverage[96] == pytest.approx(1.0, abs=1e-9)
        # Deep overlap zone: frame exactly between two centers sees both
        assert weights[1, 96] == pytest.approx(0.5, abs=1e-9)  # window centered at 64
        assert weights[2, 96] == pytest.approx(0.5, abs=1e-9)  # window centered at 128
        # Edge frame sits at the center of the first window
        assert weights[0, 0] == pytest.approx(1.0, abs=1e-9)

    def test_centers_are_strided_at_50_percent_overlap(self):
        T = 500
        centers, _ = _window_layout(T)
        assert centers == list(range(0, T, _WINDOW_STRIDE))

    def test_predict_overlap_blend_interpreter_contract(self, monkeypatch):
        """The blend loop respects the TFLite contract: one invoke per
        window, per-frame triangular accumulation, valid vocab predictions."""
        from app.chord_inference import _predict_overlap_blend, CHORD_VOCAB

        class FakeInterp:
            def get_input_details(self):
                return [{"index": 0}]

            def get_output_details(self):
                return [{"index": 1}]

            def set_tensor(self, _idx, _arr):
                self._tensor = _arr

            def invoke(self):
                pass

            def get_tensor(self, _idx):
                window = self._tensor[0]
                peak_bin = float(window[:, 0].max())
                cls = int(round(peak_bin * 100)) % (len(CHORD_VOCAB) - 1)
                probs = np.zeros((1, len(CHORD_VOCAB)), dtype=np.float32)
                probs[0, cls] = 1.0
                return probs

        monkeypatch.setattr("app.chord_inference._get_interpreter", lambda: FakeInterp())

        T = 260
        features = np.zeros((T, 40), dtype=np.float32)
        features[20:100, 0] = 0.05   # "chord A" region: class 5
        features[140:230, 0] = 0.5   # "chord B" region: class 50

        results, n_windows = _predict_overlap_blend(features)

        assert n_windows == len(list(range(0, T, _WINDOW_STRIDE)))
        assert len(results) == T
        for r in results:
            assert r["chord"] in CHORD_VOCAB
            assert 0.0 <= r["confidence"] <= 1.0
        # Frames deep inside a region keep that region's chord — the blend
        # must not oscillate between the two classes anywhere.
        assert results[60]["chord"] == CHORD_VOCAB[5]
        assert results[190]["chord"] == CHORD_VOCAB[50]

    def test_blend_resolves_boundary_disagreement_without_flicker(self):
        """A chord held across a window boundary is one stable event.

        Simulates two adjacent windows disagreeing on the chord; the per-frame
        blend must follow the nearer window center (weight > 0.5), so the held
        chord never flickers back and forth and stays a single run per region.
        """
        T = 200
        centers, weights = _window_layout(T)
        vocab = 277
        window_preds = {c: (5 if (c // _WINDOW_STRIDE) % 2 == 0 else 9) for c in centers}

        probs = np.zeros((len(centers), vocab), dtype=np.float64)
        for k, c in enumerate(centers):
            probs[k, window_preds[c]] = 1.0

        acc = weights.T @ probs
        blended = acc / np.maximum(weights.sum(axis=0)[:, None], 1e-8)
        preds = blended.argmax(axis=1)

        # Frames within 30 frames of a center are dominated by that center's
        # window (weight >= 1 - 30/64 > 0.5): no disagreement can flicker there.
        for c in centers:
            zone = slice(max(0, c - 30), min(T, c + 30))
            assert np.all(preds[zone] == window_preds[c]), f"flicker near center {c}"
        # The full run structure: exactly one change per pair of adjacent
        # windows, located in the overlap zone, never at a window center.
        changes = [i for i in range(1, T) if preds[i] != preds[i - 1]]
        assert len(changes) == len(centers) - 1
        for i in changes:
            assert i % _WINDOW_STRIDE != 0  # not at a window center
            assert abs(i % _WINDOW_STRIDE) > _WINDOW_STRIDE // 4  # inside overlap zone


# ---------------------------------------------------------------------------
# Chord: boundary confidence penalty
# ---------------------------------------------------------------------------


def _frames(n: int, chord: str = "C:maj", confidence: float = 0.9) -> list[dict]:
    return [{"time": i * 0.1, "chord": chord, "confidence": confidence} for i in range(n)]


class TestBoundaryPenalty:
    def test_penalty_applied_only_at_track_edges(self):
        frames = _frames(20)
        penalized = _apply_boundary_penalty(frames)
        assert penalized == 2 * _BOUNDARY_PENALTY_FRAMES
        for i in range(_BOUNDARY_PENALTY_FRAMES):
            assert frames[i]["confidence"] == pytest.approx(0.9 * _BOUNDARY_CONFIDENCE_FACTOR)
            assert frames[19 - i]["confidence"] == pytest.approx(0.9 * _BOUNDARY_CONFIDENCE_FACTOR)
        for i in range(_BOUNDARY_PENALTY_FRAMES, 20 - _BOUNDARY_PENALTY_FRAMES):
            assert frames[i]["confidence"] == pytest.approx(0.9)

    def test_penalty_never_exceeds_bounds(self):
        for T in (1, 2, 3, 5, 7):
            frames = _frames(T, confidence=0.4)
            penalized = _apply_boundary_penalty(frames)
            assert 0 < penalized <= T
            assert all(f["confidence"] >= 0.0 for f in frames)

    def test_edge_flicker_events_only_in_boundary_zones(self):
        # A stray chord change AT frame 0 (deep in the boundary zone): the
        # change edge (0 -> 1) touches the zone and is counted.
        frames = [{"time": i * 0.1, "chord": "G:maj" if i == 0 else "C:maj", "confidence": 0.9}
                  for i in range(20)]
        assert _edge_flicker_events(frames) == 1
        # The same change deep in the interior (frame 10) is NOT counted.
        frames = [{"time": i * 0.1, "chord": "G:maj" if i == 10 else "C:maj", "confidence": 0.9}
                  for i in range(20)]
        assert _edge_flicker_events(frames) == 0

    def test_boundary_metrics_dict_surfaces_tie_telemetry(self):
        metrics = _boundary_metrics_for_frames(_frames(200))
        assert metrics["blend_windows"] == len(list(range(0, 200, _WINDOW_STRIDE)))
        assert metrics["boundary_frames_penalized"] == 2 * _BOUNDARY_PENALTY_FRAMES
        assert "edge_flicker_events" in metrics


# ---------------------------------------------------------------------------
# Solo: MT3-style active-note tie mechanism
# ---------------------------------------------------------------------------


class TestActiveNoteTies:
    def test_chord_held_across_boundary_is_single_event(self):
        """Acceptance test: a note held across a segment boundary is emitted
        as ONE continuous event, not two."""
        seg0 = [(12.0, 18.0, 60, 0.8)]   # starts before boundary (15s), held across
        seg1 = [(15.05, 18.1, 60, 0.7)]  # re-declared shortly after the boundary
        merged = merge_segments_with_ties([seg0, seg1])
        assert len(merged) == 1
        start, end, pitch, velocity = merged[0]
        assert start == pytest.approx(12.0)
        assert end == pytest.approx(18.1)   # extended by the re-declaration
        assert velocity == pytest.approx(0.8)  # max amplitude kept

    def test_forgotten_note_survives_boundary(self):
        """If the next segment omits the active note (model failure), the note
        is not dropped and not shortened: it survives from its first
        detection."""
        seg0 = [(12.0, 18.0, 60, 0.8)]
        seg1 = []  # model "forgot" the note in the next segment
        merged = merge_segments_with_ties([seg0, seg1])
        assert len(merged) == 1
        assert merged[0] == (12.0, 18.0, 60, 0.8)

    def test_distinct_attacks_never_merged(self):
        """A real re-attack of the same pitch after the tie window stays a
        separate event."""
        seg0 = [(12.0, 15.0, 60, 0.8)]
        seg1 = [(16.0, 18.0, 60, 0.8)]  # gap of 1s > TIE_WINDOW_S
        merged = merge_segments_with_ties([seg0, seg1])
        assert len(merged) == 2

    def test_same_segment_overlapping_detections_merge(self):
        merged = merge_segments_with_ties([[(1.0, 3.0, 60, 0.8), (2.98, 5.0, 60, 0.9)]])
        assert len(merged) == 1
        assert merged[0][1] == pytest.approx(5.0)

    def test_unrelated_pitches_never_tied(self):
        seg0 = [(12.0, 18.0, 60, 0.8)]
        seg1 = [(15.05, 18.0, 64, 0.8)]  # different pitch, same time — not a tie
        merged = merge_segments_with_ties([seg0, seg1])
        assert len(merged) == 2

    def test_dampen_boundary_onsets(self):
        boundary = 15.0
        notes = [
            (12.0, 18.0, 60, 0.8),   # continuation started before boundary — untouched
            (15.1, 16.0, 62, 0.6),   # fresh onset right after boundary — dampened
            (16.0, 17.0, 64, 0.6),   # onset outside the window — untouched
        ]
        dampened, count = _dampen_boundary_onsets(notes, [boundary])
        assert count == 1
        assert dampened[0] == (12.0, 18.0, 60, 0.8)
        assert dampened[1][3] == pytest.approx(0.6 * 0.85)
        assert dampened[2][3] == pytest.approx(0.6)

    def test_segment_ranges_geometry(self):
        assert _segment_ranges(60) == [(0.0, 60.0)]                  # short track: single pass
        assert _segment_ranges(0.0) == []
        assert _segment_ranges(0.5) == [(0.0, 0.5)]
        ranges = _segment_ranges(210.0)
        assert ranges[0] == (0.0, 60.0)
        # 50% overlap: consecutive segments start `length - overlap` apart
        assert ranges[1] == (60.0 - SEGMENT_OVERLAP_S, 105.0)
        assert ranges[-1] == (180.0, 210.0)
        assert all(a < b for a, b in ranges)


# ---------------------------------------------------------------------------
# Solo: segmented inference end-to-end (mocked basic-pitch)
# ---------------------------------------------------------------------------


def _write_test_wav(path, duration_s: float, sr: int = 44100) -> None:
    t = np.arange(int(sr * duration_s)) / sr
    y = 0.1 * np.sin(2 * np.pi * 220.0 * t).astype(np.float32)
    pcm16 = (np.clip(y, -1.0, 1.0) * 32767.0).astype(np.int16)
    import wave

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def _grid_spanning(duration_s: float) -> BeatGrid:
    beats = [i * 0.5 for i in range(int(duration_s * 2) + 1)]
    return BeatGrid(
        bpm=120.0,
        beats=beats,
        downbeats=[0.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    )


def test_infer_solo_segmented_ties_boundary_note(monkeypatch, tmp_path, fake_basic_pitch):
    """End-to-end: a note held across a segment boundary detected in BOTH
    segments is emitted exactly once with the combined duration."""
    from app.solo_inference import infer_solo

    wav = tmp_path / "song.wav"
    _write_test_wav(wav, 12.0)

    def mock_predict(audio_path, **kwargs):
        # Note detected in every segment with identical absolute-ish timing:
        # segment 0 reports [2.0, 6.0), segment 1 reports (offset +4) [6.0,
        # 10.0) — a single note held across the boundary at 8.0s.
        return (None, None, [(2.0, 6.0, 60, 0.8, None)])

    monkeypatch.setattr(fake_basic_pitch, "predict", mock_predict)

    solo = infer_solo(wav, _grid_spanning(12.0), segment_length_s=8.0, overlap_s=4.0)

    # One tied note [2.0, 10.0): segment 0's detection extended by segment
    # 1's re-declaration — single event, not two.
    assert len(solo.notes) == 1
    assert solo.notes[0].pitch == 60
    assert solo.notes[0].start_time == pytest.approx(2.0)
    assert solo.notes[0].duration == pytest.approx(8.0)


def test_infer_solo_segmented_forgotten_note_survives(monkeypatch, tmp_path, fake_basic_pitch):
    """End-to-end: the next segment omits the active note; it still survives
    as one complete event instead of being dropped at the boundary."""
    from app.solo_inference import infer_solo

    wav = tmp_path / "song.wav"
    _write_test_wav(wav, 12.0)

    calls = {"n": 0}

    def mock_predict(audio_path, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return (None, None, [(3.0, 9.0, 60, 0.8, None)])
        return (None, None, [])  # second segment "forgets" the note

    monkeypatch.setattr(fake_basic_pitch, "predict", mock_predict)

    solo = infer_solo(wav, _grid_spanning(12.0), segment_length_s=8.0, overlap_s=4.0)

    assert calls["n"] == 2  # both segments processed
    assert len(solo.notes) == 1
    assert solo.notes[0].start_time == pytest.approx(3.0)
    assert solo.notes[0].duration == pytest.approx(6.0)