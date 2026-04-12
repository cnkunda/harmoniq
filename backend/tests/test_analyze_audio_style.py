from __future__ import annotations

from app import analyze_audio
from app import tabgen
from app.pipeline_proof import LibrosaSummary


def test_build_lesson_json_includes_style_label(monkeypatch, tmp_path):
    summary = LibrosaSummary(
        duration_s=30.0,
        tempo_bpm=150.0,
        beat_times_s=[0.0, 0.4],
        key_name="E minor",
        mode="minor",
        segments=[{"label": "A", "start_s": 0.0}],
        bar_timestamps_s=[0.0],
        key_confidence=0.8,
        tempo_confidence=0.85,
    )

    monkeypatch.setattr(analyze_audio, "librosa_summarize", lambda p: summary)

    def fake_gen(*_a, **_k):
        return {
            "tab_full_gp5_base64": tabgen.STUB_TAB_FULL_GP5_BASE64,
            "tab_skeleton_gp5_base64": tabgen.STUB_TAB_SKELETON_GP5_BASE64,
        }

    monkeypatch.setattr(analyze_audio, "generate_tab_artifacts_for_guitar_stem", fake_gen)

    wav_path = tmp_path / "g.wav"
    wav_path.write_bytes(b"x")

    lesson = analyze_audio.build_lesson_json_from_librosa(
        "job-style",
        guitar_stem_path=wav_path,
        vocals_stem_path=None,
        stems={"guitar": "jobs/j/stems/g.wav"},
        wav_path="jobs/j/song.wav",
    )
    assert lesson.style_label
    assert "uptempo" in lesson.style_label.lower()
