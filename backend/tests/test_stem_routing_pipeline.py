"""Integration tests for Commit 111 stem routing pipeline.

Verifies that ``build_lesson_json_from_librosa`` actually passes the
bass+other chord mix and the dynamically-selected melodic stem into
``infer_chords`` and ``infer_solo``. Also covers the hardcoded fallback
path (no hints) and routing telemetry logging.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.analyze_audio import build_lesson_json_from_librosa
from app.schemas import ChordTimeline, SoloNotes, StemRoutingHints


@pytest.fixture
def stem_wavs(tmp_path):
    sr = 44100
    rng = np.random.default_rng(7)
    stems = {
        k: (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)
        for k in ("guitar", "bass", "other", "vocals")
    }
    paths = {}
    for k, data in stems.items():
        p = tmp_path / "stems" / f"{k}.wav"
        p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(p), data, sr)
        paths[k] = p
    return paths


def _write_minimal_input(tmp_path, stems):
    """Write the input WAV and minimal stem inputs that build_lesson_json expects."""
    job_dir = tmp_path / "data" / "jobs" / "test_job"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "stems").mkdir(exist_ok=True)
    sr = 44100
    for k, src in stems.items():
        dst = job_dir / "stems" / f"{k}.wav"
        data, _ = sf.read(str(src))
        sf.write(str(dst), data, sr)
    song_wav = job_dir / "song.wav"
    sf.write(str(song_wav), np.zeros(sr, dtype=np.float32), sr)
    return job_dir, song_wav


def test_chord_inference_uses_bass_other_mix_when_hints_present(tmp_path, stem_wavs, monkeypatch):
    job_dir, song_wav = _write_minimal_input(tmp_path, stem_wavs)

    captured_chord_path = {}

    def fake_infer_chords(audio_path, beat_grid):
        captured_chord_path["path"] = str(audio_path)
        return ChordTimeline(events=[])

    def fake_infer_solo(audio_path, beat_grid):
        return SoloNotes(notes=[])

    monkeypatch.setattr("app.analyze_audio.infer_chords", fake_infer_chords)
    monkeypatch.setattr("app.analyze_audio.infer_solo", fake_infer_solo)
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid())
    monkeypatch.setattr("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {})

    hints = StemRoutingHints(
        chord_mix_stems=["bass", "other"],
        melodic_preference_order=["guitar", "vocals"],
        selected_melodic_stem="guitar",
    )

    build_lesson_json_from_librosa(
        "test_job",
        guitar_stem_path=job_dir / "stems" / "guitar.wav",
        vocals_stem_path=job_dir / "stems" / "vocals.wav",
        stems={"guitar": "stems/guitar.wav", "bass": "stems/bass.wav",
               "other": "stems/other.wav", "vocals": "stems/vocals.wav"},
        wav_path=str(song_wav),
        routing_hints=hints,
        stem_abs_paths={
            "guitar": job_dir / "stems" / "guitar.wav",
            "bass": job_dir / "stems" / "bass.wav",
            "other": job_dir / "stems" / "other.wav",
            "vocals": job_dir / "stems" / "vocals.wav",
        },
    )

    chord_path = Path(captured_chord_path["path"])
    assert chord_path == job_dir / "chord_mix.wav"
    assert chord_path.is_file()
    # The mix should be a real WAV file
    data, _ = sf.read(str(chord_path))
    assert len(data) > 0


def test_solo_uses_selected_melodic_stem_from_hints(tmp_path, stem_wavs, monkeypatch):
    job_dir, song_wav = _write_minimal_input(tmp_path, stem_wavs)

    captured_solo_path = {}

    def fake_infer_chords(audio_path, beat_grid):
        return ChordTimeline(events=[])

    def fake_infer_solo(audio_path, beat_grid):
        captured_solo_path["path"] = str(audio_path)
        return SoloNotes(notes=[])

    monkeypatch.setattr("app.analyze_audio.infer_chords", fake_infer_chords)
    monkeypatch.setattr("app.analyze_audio.infer_solo", fake_infer_solo)
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid())
    monkeypatch.setattr("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {})

    hints = StemRoutingHints(
        selected_melodic_stem="guitar",  # normal case
    )

    build_lesson_json_from_librosa(
        "test_job",
        guitar_stem_path=job_dir / "stems" / "guitar.wav",
        vocals_stem_path=job_dir / "stems" / "vocals.wav",
        stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
        wav_path=str(song_wav),
        routing_hints=hints,
        stem_abs_paths={
            "guitar": job_dir / "stems" / "guitar.wav",
            "vocals": job_dir / "stems" / "vocals.wav",
        },
    )

    assert Path(captured_solo_path["path"]) == job_dir / "stems" / "guitar.wav"


def test_solo_falls_back_when_selected_silent(tmp_path, stem_wavs, monkeypatch):
    job_dir, song_wav = _write_minimal_input(tmp_path, stem_wavs)

    # Make the "selected" stem silent (vocals in this test) so the resolver
    # cascades to guitar.
    sr = 44100
    silent_vocals = job_dir / "stems" / "vocals.wav"
    sf.write(str(silent_vocals), np.zeros(sr, dtype=np.float32), sr)

    captured_solo_path = {}

    def fake_infer_chords(audio_path, beat_grid):
        return ChordTimeline(events=[])

    def fake_infer_solo(audio_path, beat_grid):
        captured_solo_path["path"] = str(audio_path)
        return SoloNotes(notes=[])

    monkeypatch.setattr("app.analyze_audio.infer_chords", fake_infer_chords)
    monkeypatch.setattr("app.analyze_audio.infer_solo", fake_infer_solo)
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid())
    monkeypatch.setattr("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {})

    hints = StemRoutingHints(
        selected_melodic_stem="vocals",  # will be silent
    )

    build_lesson_json_from_librosa(
        "test_job",
        guitar_stem_path=job_dir / "stems" / "guitar.wav",
        vocals_stem_path=job_dir / "stems" / "vocals.wav",
        stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
        wav_path=str(song_wav),
        routing_hints=hints,
        stem_abs_paths={
            "guitar": job_dir / "stems" / "guitar.wav",
            "vocals": job_dir / "stems" / "vocals.wav",
        },
    )

    # Should fall back to guitar since vocals is silent
    assert Path(captured_solo_path["path"]) == job_dir / "stems" / "guitar.wav"


def test_hardcoded_paths_preserved_when_no_hints(tmp_path, stem_wavs, monkeypatch):
    job_dir, song_wav = _write_minimal_input(tmp_path, stem_wavs)

    captured_chord_path = {}
    captured_solo_path = {}

    def fake_infer_chords(audio_path, beat_grid):
        captured_chord_path["path"] = str(audio_path)
        return ChordTimeline(events=[])

    def fake_infer_solo(audio_path, beat_grid):
        captured_solo_path["path"] = str(audio_path)
        return SoloNotes(notes=[])

    monkeypatch.setattr("app.analyze_audio.infer_chords", fake_infer_chords)
    monkeypatch.setattr("app.analyze_audio.infer_solo", fake_infer_solo)
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid())
    monkeypatch.setattr("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {})

    # No routing_hints, no stem_abs_paths — fallback to old behavior.
    # Without mix_wav_path the chord mix falls back to the guitar stem
    # (matches pre-Commit-111 behavior at analyze_audio.py:280).
    build_lesson_json_from_librosa(
        "test_job",
        guitar_stem_path=job_dir / "stems" / "guitar.wav",
        vocals_stem_path=job_dir / "stems" / "vocals.wav",
        stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
        wav_path=str(song_wav),
    )

    # Chord: falls back to guitar stem (no mix_wav_path supplied)
    assert captured_chord_path["path"] == str(job_dir / "stems" / "guitar.wav")
    # Solo: should use guitar stem
    assert captured_solo_path["path"] == str(job_dir / "stems" / "guitar.wav")


def test_hardcoded_paths_use_mix_wav_path_when_provided(tmp_path, stem_wavs, monkeypatch):
    """When mix_wav_path is supplied (production call site), chord inference
    uses the full mix as the pre-Commit-111 fallback."""
    job_dir, song_wav = _write_minimal_input(tmp_path, stem_wavs)

    captured_chord_path = {}

    def fake_infer_chords(audio_path, beat_grid):
        captured_chord_path["path"] = str(audio_path)
        return ChordTimeline(events=[])

    monkeypatch.setattr("app.analyze_audio.infer_chords", fake_infer_chords)
    monkeypatch.setattr("app.analyze_audio.infer_solo", lambda *a, **k: SoloNotes(notes=[]))
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid())
    monkeypatch.setattr("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {})

    build_lesson_json_from_librosa(
        "test_job",
        guitar_stem_path=job_dir / "stems" / "guitar.wav",
        vocals_stem_path=job_dir / "stems" / "vocals.wav",
        stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
        wav_path=str(song_wav),
        mix_wav_path=song_wav,  # production call site passes this
    )

    # Chord: uses mix_wav_path (the full mix) when hints are absent
    assert captured_chord_path["path"] == str(song_wav)


def test_routing_decisions_logged(tmp_path, stem_wavs, monkeypatch, caplog):
    job_dir, song_wav = _write_minimal_input(tmp_path, stem_wavs)

    monkeypatch.setattr("app.analyze_audio.infer_chords", lambda *a, **k: ChordTimeline(events=[]))
    monkeypatch.setattr("app.analyze_audio.infer_solo", lambda *a, **k: SoloNotes(notes=[]))
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid())
    monkeypatch.setattr("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {})

    hints = StemRoutingHints(chord_mix_stems=["bass", "other"], selected_melodic_stem="guitar")

    with caplog.at_level(logging.INFO, logger="harmoniq.analyze_audio"):
        build_lesson_json_from_librosa(
            "test_job",
            guitar_stem_path=job_dir / "stems" / "guitar.wav",
            vocals_stem_path=job_dir / "stems" / "vocals.wav",
            stems={"guitar": "stems/guitar.wav", "bass": "stems/bass.wav", "other": "stems/other.wav"},
            wav_path=str(song_wav),
            routing_hints=hints,
            stem_abs_paths={
                "guitar": job_dir / "stems" / "guitar.wav",
                "bass": job_dir / "stems" / "bass.wav",
                "other": job_dir / "stems" / "other.wav",
            },
        )

    # At least one log line should mention stem_routing
    assert any("stem_routing" in record.message for record in caplog.records)


def test_stem_routing_persisted_to_lesson(tmp_path, stem_wavs, monkeypatch):
    job_dir, song_wav = _write_minimal_input(tmp_path, stem_wavs)

    monkeypatch.setattr("app.analyze_audio.infer_chords", lambda *a, **k: ChordTimeline(events=[]))
    monkeypatch.setattr("app.analyze_audio.infer_solo", lambda *a, **k: SoloNotes(notes=[]))
    monkeypatch.setattr("app.analyze_audio.librosa_summarize", lambda p: _fake_summary())
    monkeypatch.setattr("app.analyze_audio.estimate_beat_grid", lambda p: _fake_beat_grid())
    monkeypatch.setattr("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", lambda *a, **k: {})

    hints = StemRoutingHints(chord_mix_stems=["bass", "other"], selected_melodic_stem="guitar")

    lesson = build_lesson_json_from_librosa(
        "test_job",
        guitar_stem_path=job_dir / "stems" / "guitar.wav",
        vocals_stem_path=job_dir / "stems" / "vocals.wav",
        stems={"guitar": "stems/guitar.wav", "bass": "stems/bass.wav", "other": "stems/other.wav"},
        wav_path=str(song_wav),
        routing_hints=hints,
        stem_abs_paths={
            "guitar": job_dir / "stems" / "guitar.wav",
            "bass": job_dir / "stems" / "bass.wav",
            "other": job_dir / "stems" / "other.wav",
        },
    )

    assert lesson.stem_routing is not None
    assert lesson.stem_routing.resolved_chord_path is not None
    assert Path(lesson.stem_routing.resolved_chord_path).is_file()


# --- Test helpers ---

def _fake_summary():
    from app.pipeline_proof import LibrosaSummary
    return LibrosaSummary(
        duration_s=2.0,
        tempo_bpm=120.0,
        beat_times_s=[0.0, 0.5, 1.0, 1.5],
        key_name="C major",
        mode="major",
        segments=[{"label": "Intro", "start_s": 0.0}],
        bar_timestamps_s=[0.0, 1.0],
        key_confidence=0.9,
        tempo_confidence=0.9,
    )


def _fake_beat_grid():
    from app.schemas import BeatGrid
    return BeatGrid(
        bpm=120.0,
        pulse_bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5],
        downbeats=[0.0, 1.0],
        time_signature={"numerator": 4, "denominator": 4},
        tick_value=0.25,
    ).model_dump()
