"""End-to-end integration test: known song shape → full pipeline → LessonJSON.

Verifies that ``build_lesson_json_from_librosa`` correctly wires together
real librosa analysis (beat grid, key estimation, segmentation) with
mocked MT3/CRNN transcription and returns a valid LessonJSON with both
chord and solo data. Also verifies fallback chain produces valid output
when MT3 is unavailable.

This is the key AC 8 verification: it tests the actual pipeline orchestration
with real audio processing, only mocking the heavy ML model inference.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.analyze_audio import build_lesson_json_from_librosa
from app.mt3.fallback import TranscriptionResult
from app.schemas import ChordEvent, ChordTimeline, SoloNote, SoloNotes


def _sine_wav(path: Path, freq: float, duration: float, sr: int = 44100) -> None:
    """Write a sine wave WAV file at the given frequency and duration."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    data = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), data, sr)


def _chord_sine_wav(path: Path, freqs: list[float], duration: float, sr: int = 44100) -> None:
    """Write a WAV with stacked sine waves (simulates a strummed chord)."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    data = np.zeros_like(t)
    for freq in freqs:
        data += 0.3 * np.sin(2 * np.pi * freq * t)
    data = (data / max(1.0, np.max(np.abs(data)))).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), data, sr)


@pytest.fixture
def synthetic_song(tmp_path: Path):
    """Create a 6-second synthetic 'song' with a C→G→Am→F progression.

    Returns (job_dir, song_wav_path, guitar_stem_path) for use in tests.
    """
    sr = 44100
    job_dir = tmp_path / "data" / "jobs" / "e2e_test_job"
    stems_dir = job_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)

    # C:maj (C4=261.63, E4=329.63, G4=392.00) for 2s
    # G:maj (G3=196.00, B3=246.94, D4=293.66) for 2s
    # A:min (A3=220.00, C4=261.63, E4=329.63) for 1s
    # F:maj (F3=174.61, A3=220.00, C4=261.63) for 1s
    chord_freqs = [
        [261.63, 329.63, 392.00],
        [196.00, 246.94, 293.66],
        [220.00, 261.63, 329.63],
        [174.61, 220.00, 261.63],
    ]
    chord_notes = [
        [60, 64, 67],   # C4, E4, G4
        [55, 59, 62],   # G3, B3, D4
        [57, 60, 64],   # A3, C4, E4
        [53, 57, 60],   # F3, A3, C4
    ]
    chord_names = ["C:maj", "G:maj", "A:min", "F:maj"]
    chord_durations = [2.0, 2.0, 1.0, 1.0]

    song_path = job_dir / "song.wav"
    guitar_path = stems_dir / "guitar.wav"
    vocals_path = stems_dir / "vocals.wav"

    song_segments = []
    for freqs, dur in zip(chord_freqs, chord_durations):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        seg = np.zeros_like(t)
        for freq in freqs:
            seg += 0.3 * np.sin(2 * np.pi * freq * t)
        song_segments.append(seg)
    song_data = np.concatenate(song_segments)
    song_data = (song_data / max(1.0, np.max(np.abs(song_data)))).astype(np.float32)
    sf.write(str(song_path), song_data, sr)
    sf.write(str(guitar_path), song_data, sr)
    sf.write(str(vocals_path), np.zeros(int(sr * 6), dtype=np.float32), sr)

    # Expected beat grid: 120 BPM → 0.5s beats
    expected_beats = [i * 0.5 for i in range(12)]  # 6 seconds at 120 BPM

    return {
        "job_dir": job_dir,
        "song_path": song_path,
        "guitar_path": guitar_path,
        "vocals_path": vocals_path,
        "expected_beats": expected_beats,
        "chord_names": chord_names,
        "chord_notes": chord_notes,
        "sr": sr,
    }


def _fake_transcription_result() -> TranscriptionResult:
    """Return a known-good TranscriptionResult with both chord and solo data."""
    return TranscriptionResult(
        chord_timeline=ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.95),
            ChordEvent(timestamp=0.5, chord="C:maj", confidence=0.93),
            ChordEvent(timestamp=1.0, chord="C:maj", confidence=0.94),
            ChordEvent(timestamp=1.5, chord="C:maj", confidence=0.92),
            ChordEvent(timestamp=2.0, chord="G:maj", confidence=0.90),
            ChordEvent(timestamp=2.5, chord="G:maj", confidence=0.91),
            ChordEvent(timestamp=3.0, chord="G:maj", confidence=0.89),
            ChordEvent(timestamp=3.5, chord="G:maj", confidence=0.88),
            ChordEvent(timestamp=4.0, chord="A:min", confidence=0.87),
            ChordEvent(timestamp=4.5, chord="A:min", confidence=0.86),
            ChordEvent(timestamp=5.0, chord="F:maj", confidence=0.92),
            ChordEvent(timestamp=5.5, chord="F:maj", confidence=0.90),
        ]),
        solo_notes=SoloNotes(notes=[
            SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100),
            SoloNote(start_time=0.5, duration=0.5, pitch=64, velocity=90),
            SoloNote(start_time=1.0, duration=0.5, pitch=67, velocity=95),
            SoloNote(start_time=2.0, duration=0.5, pitch=55, velocity=88),
            SoloNote(start_time=3.0, duration=0.5, pitch=57, velocity=92),
        ]),
        source="mt3",
        mean_confidence=0.91,
    )


class TestFullPipelineIntegration:
    """Real librosa analysis + mocked MT3 inference → LessonJSON verification."""

    def _patch_common(self, monkeypatch):
        """Apply common monkeypatches for all integration tests."""
        monkeypatch.setattr(
            "app.analyze_audio.transcribe_with_fallback",
            lambda *args, **kwargs: _fake_transcription_result(),
        )
        monkeypatch.setattr(
            "app.analyze_audio.generate_tab_artifacts_for_guitar_stem",
            lambda *a, **k: {"tab_full_gp5_base64": None, "tab_skeleton_gp5_base64": None},
        )
        monkeypatch.setattr(
            "app.analyze_audio.transcribe_vocals_to_lyrics_aligned",
            lambda *args, **kwargs: ([], 0.0),
        )

    def test_e2e_pipeline_produces_lesson_json_with_both_chord_and_solo(
        self, synthetic_song, monkeypatch,
    ):
        """Known song through real librosa pipeline yields LessonJSON with chord+solo data."""
        self._patch_common(monkeypatch)

        result = build_lesson_json_from_librosa(
            "e2e_test_job",
            guitar_stem_path=synthetic_song["guitar_path"],
            vocals_stem_path=synthetic_song["vocals_path"],
            stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
            wav_path=str(synthetic_song["song_path"]),
        )

        # Core AC: chord_timeline and solo_notes both populated
        assert result.chord_timeline is not None
        assert len(result.chord_timeline.events) > 0, \
            f"Expected at least 1 chord event, got 0"
        assert result.solo_notes is not None
        assert len(result.solo_notes.notes) > 0, \
            f"Expected at least 1 solo note, got 0"

        # AC 9: transcription_source populated
        assert result.transcription_source == "mt3"

        # Beat grid computed from real librosa analysis
        assert result.beat_grid_structured is not None
        assert len(result.beat_grid_structured.beats) > 0

        # MusicXML is valid
        assert result.musicxml is not None
        assert "<score-partwise" in result.musicxml
        assert len(result.musicxml) > 0

        # Metadata present
        assert result.job_id == "e2e_test_job"
        assert result.tempo is not None and result.tempo > 0

    def test_e2e_pipeline_fallback_to_crnn_when_mt3_empty(
        self, synthetic_song, monkeypatch,
    ):
        """When MT3 returns empty chords, CRNN fallback should produce valid output."""
        mt3_result = _fake_transcription_result()
        mt3_result.chord_timeline = ChordTimeline(events=[])
        mt3_result.solo_notes = SoloNotes(notes=[])
        mt3_result.source = "mt3"

        def fake_transcribe(*args, **kwargs):
            return mt3_result

        def fake_infer_chords(*args, **kwargs):
            return ChordTimeline(events=[
                ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.90),
            ])

        monkeypatch.setattr("app.analyze_audio.transcribe_with_fallback", fake_transcribe)
        monkeypatch.setattr("app.analyze_audio.infer_chords", fake_infer_chords)
        monkeypatch.setattr("app.analyze_audio.infer_solo", lambda *a, **k: SoloNotes(notes=[
            SoloNote(start_time=0.0, duration=0.5, pitch=60, velocity=100),
        ]))
        monkeypatch.setattr(
            "app.analyze_audio.generate_tab_artifacts_for_guitar_stem",
            lambda *a, **k: {"tab_full_gp5_base64": None, "tab_skeleton_gp5_base64": None},
        )
        monkeypatch.setattr(
            "app.analyze_audio.transcribe_vocals_to_lyrics_aligned",
            lambda *args, **kwargs: ([], 0.0),
        )

        result = build_lesson_json_from_librosa(
            "e2e_test_job",
            guitar_stem_path=synthetic_song["guitar_path"],
            vocals_stem_path=synthetic_song["vocals_path"],
            stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
            wav_path=str(synthetic_song["song_path"]),
        )

        # Fallback produces valid output
        assert result.chord_timeline is not None
        assert len(result.chord_timeline.events) > 0
        assert result.transcription_source == "crnn"
        assert result.solo_notes is not None
        assert len(result.solo_notes.notes) > 0
        assert result.beat_grid_structured is not None

    def test_e2e_pipeline_handles_all_tiers_failure(
        self, synthetic_song, monkeypatch,
    ):
        """When all transcription tiers fail, pipeline still returns LessonJSON with source='none'."""
        mt3_result = _fake_transcription_result()
        mt3_result.chord_timeline = ChordTimeline(events=[])
        mt3_result.solo_notes = SoloNotes(notes=[])
        mt3_result.source = "none"

        def fake_transcribe(*args, **kwargs):
            return mt3_result

        monkeypatch.setattr("app.analyze_audio.transcribe_with_fallback", fake_transcribe)

        def raise_error(*args, **kwargs):
            raise RuntimeError("All inference tiers unavailable")

        monkeypatch.setattr("app.analyze_audio.infer_chords", raise_error)
        monkeypatch.setattr("app.analyze_audio.infer_solo", lambda *a, **k: SoloNotes(notes=[]))
        monkeypatch.setattr(
            "app.analyze_audio.generate_tab_artifacts_for_guitar_stem",
            lambda *a, **k: {"tab_full_gp5_base64": None, "tab_skeleton_gp5_base64": None},
        )
        monkeypatch.setattr(
            "app.analyze_audio.transcribe_vocals_to_lyrics_aligned",
            lambda *args, **kwargs: ([], 0.0),
        )

        result = build_lesson_json_from_librosa(
            "e2e_test_job",
            guitar_stem_path=synthetic_song["guitar_path"],
            vocals_stem_path=synthetic_song["vocals_path"],
            stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
            wav_path=str(synthetic_song["song_path"]),
        )

        # Pipeline should report source="none" when all tiers fail
        assert result.transcription_source == "none"
        assert result.tempo is not None and result.tempo > 0
        assert result.beat_grid_structured is not None
        assert result.musicxml is not None

    def test_e2e_pipeline_sections_and_bpm_populated(
        self, synthetic_song, monkeypatch,
    ):
        """Real librosa analysis should populate BPM, sections, and key."""
        self._patch_common(monkeypatch)

        result = build_lesson_json_from_librosa(
            "e2e_test_job",
            guitar_stem_path=synthetic_song["guitar_path"],
            vocals_stem_path=synthetic_song["vocals_path"],
            stems={"guitar": "stems/guitar.wav", "vocals": "stems/vocals.wav"},
            wav_path=str(synthetic_song["song_path"]),
        )

        assert result.tempo is not None and result.tempo > 0
        assert result.key is not None
        assert result.beat_grid_structured is not None
        assert len(result.beat_grid_structured.beats) > 0
        assert result.sections is not None and len(result.sections) > 0
