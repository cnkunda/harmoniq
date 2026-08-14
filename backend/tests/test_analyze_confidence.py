"""ML Fallback Logic — composite confidence wiring in the lesson pipeline."""

from __future__ import annotations

import pytest

from app import analyze_audio
from app import tabgen
from app.pipeline_proof import LibrosaSummary
from app.schemas import BeatGrid, ChordEvent, ChordTimeline, SoloNotes
from app.stem_quality import StemClassification


def _summary(segments=None):
    return LibrosaSummary(
        duration_s=12.0,
        tempo_bpm=120.0,
        beat_times_s=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
        key_name="C major",
        mode="major",
        segments=segments or [{"label": "Verse", "start_s": 0.0}],
        bar_timestamps_s=[0.0],
        key_confidence=0.9,
        tempo_confidence=0.9,
    )


def _beat_grid() -> BeatGrid:
    return BeatGrid(
        bpm=120.0,
        pulse_bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5],
        downbeats=[0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    )


def _chord_timeline() -> ChordTimeline:
    # First event lasts 5s @0.9, second event 1s tail @0.6 -> weighted mean 0.85
    return ChordTimeline(
        events=[
            ChordEvent(timestamp=0.0, chord="C", confidence=0.9),
            ChordEvent(timestamp=5.0, chord="G", confidence=0.6),
        ]
    )


def _patch_pipeline(monkeypatch, tmp_path, *, vocals_rows, stem_classification=None):
    wav_path = tmp_path / "g.wav"
    wav_path.write_bytes(b"x")

    monkeypatch.setattr(analyze_audio, "librosa_summarize", lambda p: _summary())
    monkeypatch.setattr(analyze_audio, "estimate_beat_grid", lambda p: _beat_grid().model_dump())
    monkeypatch.setattr(analyze_audio, "infer_chords", lambda *a, **k: (_chord_timeline(), {}))
    monkeypatch.setattr(analyze_audio, "infer_solo", lambda *a, **k: SoloNotes(notes=[]))
    monkeypatch.setattr(analyze_audio, "build_musicxml", lambda **k: "")
    monkeypatch.setattr(analyze_audio, "enrich_lesson_with_prerender_hints", lambda lesson, **k: lesson)

    def fake_tabgen(*_a, **_k):
        return {
            "tab_full_gp5_base64": tabgen.STUB_TAB_FULL_GP5_BASE64,
            "tab_skeleton_gp5_base64": tabgen.STUB_TAB_SKELETON_GP5_BASE64,
        }

    monkeypatch.setattr(analyze_audio, "generate_tab_artifacts_for_guitar_stem", fake_tabgen)

    def fake_transcribe(*_a, **_k):
        return vocals_rows, 0.9

    monkeypatch.setattr(analyze_audio, "transcribe_vocals_to_lyrics_aligned", fake_transcribe)

    return wav_path, stem_classification


def test_lesson_confidence_blends_chords_and_vocal_coverage(monkeypatch, tmp_path):
    # 10 aligned words over 20 beats -> coverage 0.5 -> vocals conf 0.92
    vocals_rows = [{"word": "w", "beat": i} for i in range(10)]
    wav_path, sc = _patch_pipeline(monkeypatch, tmp_path, vocals_rows=vocals_rows)
    lesson = analyze_audio.build_lesson_json_from_librosa(
        "job-conf",
        guitar_stem_path=wav_path,
        vocals_stem_path=None,
        stems={"guitar": "jobs/j/stems/g.wav"},
        wav_path="jobs/j/song.wav",
        stem_classification=sc,
    )
    # chords: 0.85, vocals: 0.92 -> 0.6*0.85 + 0.4*0.92 = 0.878
    assert lesson.transcription_confidence == pytest.approx(0.878, abs=1e-3)
    for sec in lesson.sections:
        assert sec.confidence == pytest.approx(0.878, abs=1e-3)


def test_instrumental_track_uses_chord_confidence_alone(monkeypatch, tmp_path):
    wav_path, sc = _patch_pipeline(monkeypatch, tmp_path, vocals_rows=[])
    lesson = analyze_audio.build_lesson_json_from_librosa(
        "job-instr",
        guitar_stem_path=wav_path,
        vocals_stem_path=None,
        stems={"guitar": "jobs/j/stems/g.wav"},
        wav_path="jobs/j/song.wav",
        stem_classification=sc,
    )
    # No vocals -> composite == chord confidence (0.85). Instrumentals are NOT punished.
    assert lesson.transcription_confidence == pytest.approx(0.85, abs=1e-3)


def test_unusable_guitar_stem_floors_confidence_and_skips_tabs(monkeypatch, tmp_path):
    wav_path, sc = _patch_pipeline(
        monkeypatch,
        tmp_path,
        vocals_rows=[],
        stem_classification=StemClassification(
            guitar_stem_usable=False,
            analysis_audio_role="full_mix",
            flags=("guitar_near_silent",),
            user_warning="no guitar",
        ),
    )
    lesson = analyze_audio.build_lesson_json_from_librosa(
        "job-notabs",
        guitar_stem_path=wav_path,
        vocals_stem_path=None,
        stems={"guitar": "jobs/j/stems/g.wav"},
        wav_path="jobs/j/song.wav",
        stem_classification=sc,
    )
    assert lesson.transcription_confidence <= 0.25
    assert lesson.tabs_unavailable_reason == "no_isolated_guitar"
    assert lesson.guitar_stem_usable is False
    for sec in lesson.sections:
        assert sec.confidence <= 0.25
        assert not sec.model_dump().get("tab_full_gp5_base64")
        assert not sec.model_dump().get("tab_skeleton_gp5_base64")