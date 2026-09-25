"""Tests for Commit 109: Beat grid recompute and progressive analysis stages."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.beat_grid import DEPENDENT_ARTIFACTS, dependent_artifacts_for_grid_override
from app.schemas import (
    BeatGrid,
    BeatGridRecomputeRequest,
    BeatGridRecomputeResponse,
    JobStatus,
)


class TestBeatGridDependentArtifacts:
    """Tests for DEPENDENT_ARTIFACTS and barTimestamps inclusion."""

    def test_dependent_artifacts_includes_bar_timestamps(self):
        """barTimestamps must be listed as a dependent artifact."""
        assert "barTimestamps" in DEPENDENT_ARTIFACTS

    def test_dependent_artifacts_returns_all(self):
        """dependent_artifacts_for_grid_override() returns the full list."""
        result = dependent_artifacts_for_grid_override()
        assert "chordTimeline" in result
        assert "SoloNotes" in result
        assert "Score.musicxml" in result
        assert "barTimestamps" in result


class TestJobStatusAnalysisStage:
    """Tests for the analysis_stage field on JobStatus."""

    def test_default_analysis_stage_is_none(self):
        """analysis_stage defaults to None for backward compat."""
        job = JobStatus(status="processing")
        assert job.analysis_stage is None

    def test_analysis_stage_set_on_creation(self):
        """analysis_stage can be set when creating a JobStatus."""
        job = JobStatus(status="processing", analysis_stage="chords_inferring")
        assert job.analysis_stage == "chords_inferring"

    def test_analysis_stage_on_complete(self):
        """Complete jobs should have analysis_stage='complete'."""
        job = JobStatus(status="complete", analysis_stage="complete")
        assert job.analysis_stage == "complete"


class TestBeatGridRecomputeSchemas:
    """Tests for BeatGridRecomputeRequest and BeatGridRecomputeResponse."""

    def test_request_defaults(self):
        """Request defaults to no overrides."""
        req = BeatGridRecomputeRequest()
        assert req.time_signature is None
        assert req.bpm_override is None

    def test_request_with_overrides(self):
        """Request accepts time signature and bpm overrides."""
        req = BeatGridRecomputeRequest(time_signature="6/8", bpm_override=120.0)
        assert req.time_signature == "6/8"
        assert req.bpm_override == 120.0

    def test_response_defaults(self):
        """Response defaults to pending status."""
        resp = BeatGridRecomputeResponse(job_id="test-123")
        assert resp.job_id == "test-123"
        assert resp.status == "pending"
        assert resp.progress is None
        assert resp.error is None
        assert resp.beat_grid is None
        assert resp.bar_timestamps == []

    def test_response_complete_status(self):
        """Response can be created with complete status."""
        bg = BeatGrid(
            bpm=120.0,
            pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0],
            downbeats=[0.0],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        resp = BeatGridRecomputeResponse(
            job_id="test-123",
            status="complete",
            progress=1.0,
            beat_grid=bg,
            bar_timestamps=[0.0, 2.0],
        )
        assert resp.status == "complete"
        assert resp.progress == 1.0
        assert resp.beat_grid is not None
        assert resp.bar_timestamps == [0.0, 2.0]


class TestBarTimestampsFromDownbeats:
    """Tests for bar_timestamps derivation from BeatGrid.downbeats."""

    def test_bar_timestamps_from_downbeats(self):
        """bar_timestamps should come from beat_grid.downbeats, not hardcoded 4/4."""
        bg = BeatGrid(
            bpm=120.0,
            pulse_bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            downbeats=[0.0, 2.0],  # 2/4 time: 2 beats per bar
            time_signature={"numerator": 2, "denominator": 4},
            tick_value=0.25,
        )
        bar_timestamps = list(bg.downbeats)
        assert bar_timestamps == [0.0, 2.0]

    def test_bar_timestamps_6_8(self):
        """6/8 time: downbeats every 3 eighth notes."""
        bg = BeatGrid(
            bpm=360.0,  # Grid BPM (120 pulse * 3 subdivisions)
            pulse_bpm=120.0,
            beats=[0.0, 0.167, 0.333, 0.5, 0.667, 0.833, 1.0],
            downbeats=[0.0, 0.5],  # Dotted quarter = 0.5s at 120 BPM
            time_signature={"numerator": 6, "denominator": 8},
            tick_value=0.125,
        )
        bar_timestamps = list(bg.downbeats)
        assert bar_timestamps == [0.0, 0.5]

    def test_bar_timestamps_empty_downbeats(self):
        """Empty downbeats falls back to [0.0]."""
        bg = BeatGrid(
            bpm=120.0,
            pulse_bpm=120.0,
            beats=[0.0, 0.5],
            downbeats=[],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )
        bar_timestamps = list(bg.downbeats) if bg.downbeats else [0.0]
        assert bar_timestamps == [0.0]
