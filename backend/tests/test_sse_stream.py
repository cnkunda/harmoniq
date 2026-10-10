"""Tests for Commit 151: SSE progress stream — BUG-01 root-cause fix.

Covers `app.sse.job_progress_stream`: connect frame, status-on-change,
analysis_stage passthrough, terminal complete/failed + stream close, and
silence between state changes (heartbeat-only keep-alive).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.jobs import _set_job_partial_result, jobs
from app.schemas import ChordEvent, ChordTimeline, JobStatus, LessonJSON, PartialAnalysisResult
from app.sse import job_progress_stream, sse_response

_NEXT_FRAME_TIMEOUT = 5.0
# Short tick so the tests observe state changes fast (monkeypatched per test).
_FAST_TICK = 0.01


@pytest.fixture(autouse=True)
def clear_jobs():
    jobs.clear()
    yield
    jobs.clear()


@pytest.fixture(autouse=True)
def fast_tick(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.sse.POLL_INTERVAL_SECONDS", _FAST_TICK)


def _parse(frame: str) -> tuple[str | None, dict[str, Any] | None]:
    event: str | None = None
    data: dict[str, Any] | None = None
    for line in frame.strip().split("\n"):
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = json.loads(line.split(":", 1)[1].strip())
    assert event is not None, f"frame missing event line: {frame!r}"
    return event, data


async def _next_frame(gen) -> tuple[str | None, dict[str, Any] | None]:
    frame = await asyncio.wait_for(gen.__anext__(), timeout=_NEXT_FRAME_TIMEOUT)
    return _parse(frame)


async def _expect_closed(gen) -> None:
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=_NEXT_FRAME_TIMEOUT)


def test_connect_then_initial_status() -> None:
    async def scenario():
        job_id = "sse-connect"
        jobs[job_id] = JobStatus(
            status="processing",
            result=None,
            progress=0.05,
            stage_label="Queued…",
            analysis_stage="initializing",
        )
        gen = job_progress_stream(job_id)
        event, data = await _next_frame(gen)
        assert event == "connected"
        assert data == {"job_id": job_id, "message": "SSE connected"}

        event, data = await _next_frame(gen)
        assert event == "status"
        assert data is not None
        assert data["status"] == "processing"
        assert data["progress"] == 0.05
        assert data["analysis_stage"] == "initializing"
        await gen.aclose()

    asyncio.run(scenario())


def test_status_emitted_on_change_with_analysis_stage() -> None:
    async def scenario():
        job_id = "sse-stage"
        jobs[job_id] = JobStatus(status="processing", result=None, progress=0.4, analysis_stage="stems_separating")
        gen = job_progress_stream(job_id)
        await _next_frame(gen)  # connected
        await _next_frame(gen)  # initial status

        jobs[job_id] = JobStatus(status="processing", result=None, progress=0.62, analysis_stage="chords_inferring")
        event, data = await _next_frame(gen)
        assert event == "status"
        assert data is not None
        assert data["analysis_stage"] == "chords_inferring"
        assert data["progress"] == 0.62
        await gen.aclose()

    asyncio.run(scenario())


def test_no_duplicate_status_frames_while_unchanged() -> None:
    """BUG-01: no frames at all (only heartbeats, which are far slower) while state is static."""

    async def scenario():
        job_id = "sse-quiet"
        jobs[job_id] = JobStatus(status="processing", result=None, progress=0.28, analysis_stage="stems_separating")
        gen = job_progress_stream(job_id)
        await _next_frame(gen)  # connected
        await _next_frame(gen)  # initial status

        # ~15 ticks pass with no store change → next frame must not arrive.
        # wait_for cancels the pending __anext__, which closes the stream — fine here.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(gen.__anext__(), timeout=_FAST_TICK * 15)

    asyncio.run(scenario())


def test_complete_emits_result_then_closes_stream() -> None:
    async def scenario():
        job_id = "sse-complete"
        jobs[job_id] = JobStatus(status="processing", result=None, progress=0.62, analysis_stage="chords_inferring")
        gen = job_progress_stream(job_id)
        await _next_frame(gen)  # connected
        await _next_frame(gen)  # initial status

        lesson = LessonJSON(job_id=job_id, song_title="Gravity", artist="John Mayer")
        jobs[job_id] = JobStatus(status="complete", result=lesson, error=None, analysis_stage="complete")

        event, data = await _next_frame(gen)
        assert event == "complete"
        assert data is not None
        assert data["status"] == "complete"
        assert data["result"]["song_title"] == "Gravity"

        # Terminal event is the last frame — no post-terminal polling/status frames.
        await _expect_closed(gen)

    asyncio.run(scenario())


def test_failed_emits_error_then_closes_stream() -> None:
    async def scenario():
        job_id = "sse-failed"
        jobs[job_id] = JobStatus(status="processing", result=None, progress=0.12)
        gen = job_progress_stream(job_id)
        await _next_frame(gen)  # connected
        await _next_frame(gen)  # initial status

        jobs[job_id] = JobStatus(
            status="failed",
            result=None,
            error="Analysis failed.",
            error_code="analysis_failed",
        )
        event, data = await _next_frame(gen)
        assert event == "failed"
        assert data is not None
        assert data["status"] == "failed"
        assert data["error"] == "Analysis failed."
        assert data["error_code"] == "analysis_failed"

        await _expect_closed(gen)

    asyncio.run(scenario())


def test_unknown_job_reports_queued_then_tracks_appearance() -> None:
    async def scenario():
        job_id = "sse-late-arrival"
        gen = job_progress_stream(job_id)

        await _next_frame(gen)  # connected
        event, data = await _next_frame(gen)
        assert event == "status"
        assert data is not None
        assert data["status"] == "queued"  # mirrors GET /analyze/{job_id}

        jobs[job_id] = JobStatus(status="processing", result=None, progress=0.05, analysis_stage="initializing")
        event, data = await _next_frame(gen)
        assert event == "status"
        assert data is not None
        assert data["status"] == "processing"
        await gen.aclose()

    asyncio.run(scenario())


def test_sse_response_headers() -> None:
    resp = sse_response("any-job")
    assert resp.media_type == "text/event-stream"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"


def test_partial_result_arrival_emits_status_frame() -> None:
    """Commit 152: attaching the partial chord payload must emit a `status` event."""

    async def scenario():
        job_id = "sse-partial"
        jobs[job_id] = JobStatus(
            status="processing",
            result=None,
            progress=0.6,
            stage_label="Transcribing with MT3…",
            analysis_stage="mt3_inferring",
        )
        gen = job_progress_stream(job_id)
        await _next_frame(gen)  # connected
        await _next_frame(gen)  # initial status (partial_result is null)

        partial = PartialAnalysisResult(
            chord_timeline=ChordTimeline(
                events=[ChordEvent(timestamp=0.0, chord="G:maj", confidence=0.9)]
            ),
            bpm=96.5,
            total_duration=183.2,
        )
        _set_job_partial_result(job_id, partial)

        event, data = await _next_frame(gen)
        assert event == "status"
        assert data is not None
        assert data["analysis_stage"] == "mt3_inferring"
        assert data["partial_result"] is not None
        assert data["partial_result"]["bpm"] == 96.5
        assert data["partial_result"]["chord_timeline"]["events"][0]["chord"] == "G:maj"
        await gen.aclose()

    asyncio.run(scenario())
