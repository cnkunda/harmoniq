"""Integration tests for commit 110 stem routing (bass+other mix, dynamic melodic stem)."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import soundfile as sf

import app.analyze_audio as aa
from app.schemas import ChordTimeline, SoloNotes
from app.stem_quality import StemClassification


def _write_tone(path: Path, *, freq: float = 220.0, amp: float = 0.5, dur: float = 0.5, sr: int = 44100) -> None:
    n = int(sr * dur)
    data = np.array([math.sin(2 * math.pi * freq * i / sr) * amp for i in range(n)], dtype=np.float32)
    sf.write(str(path), data, sr)


def _fake_summary():
    m = MagicMock()
    m.tempo_bpm = 120
    m.key_name = "C major"
    m.key_confidence = 0.9
    m.tempo_confidence = 0.9
    m.beat_times_s = [0.0, 0.5, 1.0, 1.5]
    m.bar_timestamps_s = [0.0]
    m.segments = [{"label": "Intro", "start_s": 0.0}]
    m.duration_s = 1.0
    return m


def _fake_beat():
    return {"bpm": 120, "pulse_bpm": 120, "beats": [0, 0.5, 1, 1.5], "downbeats": [0], "time_signature": {"numerator": 4, "denominator": 4}, "tick_value": 0.25}


def test_chord_uses_bass_other_mix_and_solo_uses_selected_stem():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        job_dir = tmp / "job1"
        job_dir.mkdir()
        stems_dir = job_dir / "stems"
        stems_dir.mkdir()
        for stem in ["guitar", "bass", "other", "vocals", "piano", "drums"]:
            _write_tone(stems_dir / f"{stem}.wav", freq=220 if stem != "other" else 330, dur=1.0)
        mix = job_dir / "song.wav"
        _write_tone(mix, dur=1.0)

        fake_summary = _fake_summary()
        fake_beat = _fake_beat()

        with patch("app.analyze_audio.librosa_summarize", return_value=fake_summary), \
             patch("app.analyze_audio.estimate_beat_grid", return_value=fake_beat), \
             patch("app.analyze_audio.infer_chords", return_value=(ChordTimeline(events=[]), {})) as mock_chords, \
             patch("app.analyze_audio.infer_solo", return_value=SoloNotes(notes=[])) as mock_solo, \
             patch("app.analyze_audio.transcribe_vocals_to_lyrics_aligned", return_value=([], 0)), \
             patch("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", return_value={}), \
             patch("app.analyze_audio.apply_tab_artifacts_to_sections", side_effect=lambda s, **k: s), \
             patch("app.analyze_audio.enrich_lesson_with_prerender_hints", side_effect=lambda l, **k: l):

            def patched_resolve(name, stems, gp):
                p = stems_dir / f"{name}.wav"
                return p if p.is_file() else None

            with patch("app.analyze_audio._resolve_stem_abs_path", side_effect=patched_resolve):
                with patch("app.analyze_audio._backend_root_for_analyze", return_value=tmp):
                    hints = {"chord_mix_stems": ["bass", "other"], "melodic_preference_order": ["guitar", "vocals", "bass"], "selected_melodic_stem": "bass"}
                    stems_dict = {k: f"data/jobs/job1/stems/{k}.wav" for k in ["guitar", "bass", "other", "vocals"]}
                    aa.build_lesson_json_from_librosa(
                        "job1",
                        guitar_stem_path=stems_dir / "guitar.wav",
                        vocals_stem_path=stems_dir / "vocals.wav",
                        stems=stems_dict,
                        wav_path=str(mix),
                        stem_routing_hints=hints,
                        job_dir=job_dir,
                    )
                    assert mock_chords.called
                    chord_path = mock_chords.call_args[0][0]
                    assert "mixed_bass_other.wav" in str(chord_path), f"expected mixed path, got {chord_path}"
                    assert (job_dir / "mixed_bass_other.wav").is_file()
                    assert mock_solo.called
                    solo_path = mock_solo.call_args[0][0]
                    assert "bass.wav" in str(solo_path), f"expected bass stem, got {solo_path}"


def test_solo_fallback_chain_selected_guitar_vocals():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        job_dir = tmp / "job"
        job_dir.mkdir()
        stems_dir = job_dir / "stems"
        stems_dir.mkdir()
        # guitar selected but silent/missing, vocals present
        for stem in ["bass", "other", "vocals"]:
            _write_tone(stems_dir / f"{stem}.wav", dur=0.5)
        # guitar file exists but we will simulate missing via patched resolve
        (stems_dir / "guitar.wav").write_text("")  # empty so _wav_has_audio will fail? but patched resolve will handle
        mix = job_dir / "song.wav"
        _write_tone(mix, dur=0.5)

        fake_summary = _fake_summary()
        fake_beat = _fake_beat()

        with patch("app.analyze_audio.librosa_summarize", return_value=fake_summary), \
             patch("app.analyze_audio.estimate_beat_grid", return_value=fake_beat), \
             patch("app.analyze_audio.infer_chords", return_value=(ChordTimeline(events=[]), {})), \
             patch("app.analyze_audio.infer_solo", return_value=SoloNotes(notes=[])) as mock_solo, \
             patch("app.analyze_audio.transcribe_vocals_to_lyrics_aligned", return_value=([], 0)), \
             patch("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", return_value={}), \
             patch("app.analyze_audio.apply_tab_artifacts_to_sections", side_effect=lambda s, **k: s), \
             patch("app.analyze_audio.enrich_lesson_with_prerender_hints", side_effect=lambda l, **k: l):

            def patched(name, stems, gp):
                # guitar missing, vocals present
                if name == "guitar":
                    return None
                p = stems_dir / f"{name}.wav"
                return p if p.is_file() else None

            with patch("app.analyze_audio._resolve_stem_abs_path", side_effect=patched):
                with patch("app.analyze_audio._backend_root_for_analyze", return_value=tmp):
                    hints = {"chord_mix_stems": ["bass", "other"], "melodic_preference_order": ["guitar", "vocals"], "selected_melodic_stem": "guitar"}
                    stems_dict = {k: f"stems/{k}.wav" for k in ["guitar", "bass", "other", "vocals"]}
                    aa.build_lesson_json_from_librosa(
                        "jid",
                        guitar_stem_path=stems_dir / "guitar.wav",
                        vocals_stem_path=stems_dir / "vocals.wav",
                        stems=stems_dict,
                        wav_path=str(mix),
                        stem_routing_hints=hints,
                        job_dir=job_dir,
                    )
                    solo_path = mock_solo.call_args[0][0]
                    assert "vocals.wav" in str(solo_path)


def test_fallback_when_hints_unavailable():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        job_dir = tmp / "job"
        job_dir.mkdir()
        stems_dir = job_dir / "stems"
        stems_dir.mkdir()
        _write_tone(stems_dir / "guitar.wav", dur=0.5)
        _write_tone(stems_dir / "bass.wav", dur=0.5)
        _write_tone(stems_dir / "other.wav", dur=0.5)
        mix = job_dir / "song.wav"
        _write_tone(mix, dur=0.5)

        fake_summary = _fake_summary()
        fake_beat = _fake_beat()

        with patch("app.analyze_audio.librosa_summarize", return_value=fake_summary), \
             patch("app.analyze_audio.estimate_beat_grid", return_value=fake_beat), \
             patch("app.analyze_audio.infer_chords", return_value=(ChordTimeline(events=[]), {})) as mock_chords, \
             patch("app.analyze_audio.infer_solo", return_value=SoloNotes(notes=[])) as mock_solo, \
             patch("app.analyze_audio.transcribe_vocals_to_lyrics_aligned", return_value=([], 0)), \
             patch("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", return_value={}), \
             patch("app.analyze_audio.apply_tab_artifacts_to_sections", side_effect=lambda s, **k: s), \
             patch("app.analyze_audio.enrich_lesson_with_prerender_hints", side_effect=lambda l, **k: l):
            aa.build_lesson_json_from_librosa(
                "jid",
                guitar_stem_path=stems_dir / "guitar.wav",
                vocals_stem_path=None,
                stems={"guitar": "stems/guitar.wav"},
                wav_path=str(mix),
                mix_wav_path=mix,
                stem_routing_hints=None,
                job_dir=job_dir,
            )
            assert str(mock_chords.call_args[0][0]) == str(mix)
            assert "guitar.wav" in str(mock_solo.call_args[0][0])


def test_quality_flags_influence_routing():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        job_dir = tmp / "job"
        job_dir.mkdir()
        stems_dir = job_dir / "stems"
        stems_dir.mkdir()
        for stem in ["guitar", "vocals", "bass", "other"]:
            _write_tone(stems_dir / f"{stem}.wav", dur=0.5)
        mix = job_dir / "song.wav"
        _write_tone(mix, dur=0.5)

        fake_summary = _fake_summary()
        fake_beat = _fake_beat()
        cls = StemClassification(guitar_stem_usable=False, analysis_audio_role="full_mix", flags=("guitar_near_silent",), user_warning=None)

        with patch("app.analyze_audio.librosa_summarize", return_value=fake_summary), \
             patch("app.analyze_audio.estimate_beat_grid", return_value=fake_beat), \
             patch("app.analyze_audio.infer_chords", return_value=(ChordTimeline(events=[]), {})), \
             patch("app.analyze_audio.infer_solo", return_value=SoloNotes(notes=[])) as mock_solo, \
             patch("app.analyze_audio.transcribe_vocals_to_lyrics_aligned", return_value=([], 0)), \
             patch("app.analyze_audio.generate_tab_artifacts_for_guitar_stem", return_value={}), \
             patch("app.analyze_audio.apply_tab_artifacts_to_sections", side_effect=lambda s, **k: s), \
             patch("app.analyze_audio.enrich_lesson_with_prerender_hints", side_effect=lambda l, **k: l):

            def patched(name, stems, gp):
                p = stems_dir / f"{name}.wav"
                return p if p.is_file() else None

            with patch("app.analyze_audio._resolve_stem_abs_path", side_effect=patched):
                with patch("app.analyze_audio._backend_root_for_analyze", return_value=tmp):
                    hints = {"chord_mix_stems": ["bass", "other"], "melodic_preference_order": ["guitar", "vocals"], "selected_melodic_stem": "guitar"}
                    stems_dict = {k: f"stems/{k}.wav" for k in ["guitar", "vocals", "bass", "other"]}
                    aa.build_lesson_json_from_librosa(
                        "jid",
                        guitar_stem_path=stems_dir / "guitar.wav",
                        vocals_stem_path=stems_dir / "vocals.wav",
                        stems=stems_dict,
                        wav_path=str(mix),
                        stem_classification=cls,
                        stem_routing_hints=hints,
                        job_dir=job_dir,
                    )
                    solo_path = mock_solo.call_args[0][0]
                    assert "vocals.wav" in str(solo_path), f"flag should route to vocals, got {solo_path}"
