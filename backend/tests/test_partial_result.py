"""Tests for Commit 152: partial chord result — Progressive Analysis Reveal.

Covers:
- ``build_lesson_json_from_librosa(on_chords_ready=...)`` fires exactly once,
  before the (potentially slow) solo fallback, carrying chord timeline + bpm + duration.
- ``jobs._set_job_partial_result`` mutates the in-memory job safely and later
  stage updates do not drop the partial payload.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from app.analyze_audio import build_lesson_json_from_librosa
from app.jobs import (
    _set_job_analysis_stage,
    _set_job_partial_result,
    _set_job_processing_progress,
    jobs,
)
from app.mt3 import TranscriptionResult
from app.schemas import (
    ChordEvent,
    ChordTimeline,
    JobStatus,
    PartialAnalysisResult,
    SoloNote,
    SoloNotes,
)


# ---- build_lesson_json_from_librosa: on_chords_ready ------------------------------------------

def _fake_summary():
    from app.pipeline_proof import LibrosaSummary
    return LibrosaSummary(
        duration_s=7.5,
        tempo_bpm=96.5,
        beat_times_s=[0.0, 0.625, 1.25, 1.875],
        key_name="C major",
        mode="major",
        segments=[{"label": "Intro", "start_s": 0.0}],
        bar_timestamps_s=[0.0, 2.5],
        key_confidence=0.9,
        tempo_confidence=0.9,
    )


def _fake_beat_grid_dict(bpm: float = 96.5):
    return {
        "bpm": bpm,
        "pulse_bpm": bpm,
        "beats": [0.0, 0.625, 1.25, 1.875],
        "downbeats": [0.0, 2.5],
        "time_signature": {"numerator": 4, "denominator": 4},
        "tick_value": 0.25,
    }


def _write_inputs(tmp_path):
    sr = 44100
    job_dir = tmp_path / "data" / "jobs" / "partial_job"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "stems").mkdir(exist_ok=True)
    rng = np.random.default_rng(11)
    for k in ("guitar", "vocals"):
        p = job_dir / "stems" / f"{k}.wav"
        sf.write(str(p), (0.1 * rng.uniform(-1, 1, sr)).astype(np.float32), sr)
    song_wav = job_dir / "song.wav"
    sf.write(str(song_wav), np.zeros(sr, dtype=np.float32), sr)
    return job_dir, song_wav


def _chord_timeline() -> ChordTimeline:
    return ChordTimeline(events=[
        ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ChordEvent(timestamp=2.5, chord="G:maj", confidence=0.8),
    ])


def _patch_common(monkeypatch, transcribe_result: TranscriptionResult, order: list[str]):
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid_dict())
    monkeypatch.setattr("app.analyze_audio.transcribe_with_fallback", lambda *a, **k: transcribe_result)
    monkeypatch.setattr(
        "app.analyze_audio.generate_tab_artifacts_for_guitar_stem",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        "app.analyze_audio.transcribe_vocals_to_lyrics_aligned",
        lambda *a, **k: ([], 0.0),
    )
    monkeypatch.setattr(
        "app.analyze_audio.infer_solo",
        lambda *a, **k: (order.append("solo_fallback") or SoloNotes(notes=[])),
    )


def _call_build(job_dir, song_wav, on_chords_ready=None):
    return build_lesson_json_from_librosa(
        "partial_job",
        guitar_stem_path=job_dir / "stems" / "guitar.wav",
        vocals_stem_path=job_dir / "stems" / "vocals.wav",
        stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
        wav_path=str(song_wav),
        on_chords_ready=on_chords_ready,
    )


class TestOnChordsReady:
    def test_fires_before_solo_fallback_with_bpm_and_duration(self, tmp_path, monkeypatch):
        """Chords are final before Basic Pitch solo runs — the preview must not wait."""
        job_dir, song_wav = _write_inputs(tmp_path)
        order: list[str] = []
        received: list[PartialAnalysisResult] = []

        # MT3 returns chords but NO solo notes → the slow solo fallback runs.
        transcribe = TranscriptionResult(
            chord_timeline=_chord_timeline(),
            solo_notes=SoloNotes(notes=[]),
            source="mt3",
            mean_confidence=0.9,
        )
        _patch_common(monkeypatch, transcribe, order)

        def on_chords_ready(partial: PartialAnalysisResult) -> None:
            order.append("chords_ready")
            received.append(partial)

        _call_build(job_dir, song_wav, on_chords_ready=on_chords_ready)

        assert order == ["chords_ready", "solo_fallback"]
        assert len(received) == 1
        partial = received[0]
        assert [e.chord for e in partial.chord_timeline.events] == ["C:maj", "G:maj"]
        assert partial.bpm == pytest.approx(96.5)
        assert partial.total_duration == pytest.approx(7.5)

    def test_fires_once_when_mt3_returns_solo(self, tmp_path, monkeypatch):
        job_dir, song_wav = _write_inputs(tmp_path)
        order: list[str] = []
        received: list[PartialAnalysisResult] = []

        transcribe = TranscriptionResult(
            chord_timeline=_chord_timeline(),
            solo_notes=SoloNotes(notes=[SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100)]),
            source="mt3",
            mean_confidence=0.9,
        )
        _patch_common(monkeypatch, transcribe, order)

        _call_build(job_dir, song_wav, on_chords_ready=lambda p: (order.append("chords_ready"), received.append(p)))

        assert order == ["chords_ready"]  # no solo fallback needed
        assert len(received) == 1

    def test_omitting_the_callback_keeps_the_pipeline_working(self, tmp_path, monkeypatch):
        job_dir, song_wav = _write_inputs(tmp_path)
        transcribe = TranscriptionResult(
            chord_timeline=_chord_timeline(),
            solo_notes=SoloNotes(notes=[]),
            source="mt3",
            mean_confidence=0.9,
        )
        _patch_common(monkeypatch, transcribe, order=[])

        lesson = _call_build(job_dir, song_wav)  # no on_chords_ready
        assert lesson.chord_timeline is not None


# ---- jobs store: _set_job_partial_result ------------------------------------------------------

def _partial(bpm: float = 96.5) -> PartialAnalysisResult:
    return PartialAnalysisResult(
        chord_timeline=_chord_timeline(),
        bpm=bpm,
        total_duration=7.5,
    )


@pytest.fixture
def processing_job():
    jobs.clear()
    jobs["job-1"] = JobStatus(
        status="processing",
        result=None,
        progress=0.6,
        stage_label="Transcribing (MT3)…",
        processing_started_at=1_700_000_000.0,
        analysis_stage="mt3_inferring",
    )
    yield "job-1"
    jobs.clear()


class TestSetJobPartialResult:
    def test_sets_partial_and_preserves_all_other_fields(self, processing_job):
        _set_job_partial_result(processing_job, _partial())

        job = jobs[processing_job]
        assert job.status == "processing"
        assert job.partial_result is not None
        assert job.partial_result.bpm == pytest.approx(96.5)
        assert job.progress == 0.6
        assert job.stage_label == "Transcribing (MT3)…"
        assert job.analysis_stage == "mt3_inferring"
        assert job.processing_started_at == 1_700_000_000.0

    def test_noop_for_missing_job(self):
        _set_job_partial_result("does-not-exist", _partial())  # must not raise
        assert "does-not-exist" not in jobs

    def test_noop_for_terminal_job(self, processing_job):
        lesson_partial = _partial()
        jobs[processing_job] = JobStatus(status="complete", result=None, error=None, analysis_stage="complete")
        _set_job_partial_result(processing_job, lesson_partial)

        assert jobs[processing_job].status == "complete"
        assert jobs[processing_job].partial_result is None

    def test_later_stage_updates_preserve_the_partial(self, processing_job):
        _set_job_partial_result(processing_job, _partial())

        _set_job_analysis_stage(processing_job, "building_musicxml", 0.88, "Building MusicXML…")
        assert jobs[processing_job].partial_result is not None
        assert jobs[processing_job].analysis_stage == "building_musicxml"

        _set_job_processing_progress(processing_job, 0.9, "Building MusicXML…")
        assert jobs[processing_job].partial_result is not None
        assert jobs[processing_job].progress == 0.9
