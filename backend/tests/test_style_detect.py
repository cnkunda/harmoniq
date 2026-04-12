from __future__ import annotations

from app.pipeline_proof import LibrosaSummary
from app.style_detect import infer_style_from_librosa_summary


def _summary(*, bpm: float, duration_s: float = 30.0, n_seg: int = 2) -> LibrosaSummary:
    segments = [{"label": f"S{i}", "start_s": float(i)} for i in range(n_seg)]
    return LibrosaSummary(
        duration_s=duration_s,
        tempo_bpm=bpm,
        beat_times_s=[0.0, 0.5],
        key_name="C major",
        mode="major",
        segments=segments,
        bar_timestamps_s=[0.0],
        key_confidence=0.7,
        tempo_confidence=0.7,
    )


def test_infer_style_uptempo_label():
    r = infer_style_from_librosa_summary(_summary(bpm=150.0))
    assert "uptempo" in r.style_label.lower()
    assert r.technique_hints


def test_infer_style_slow_ballad():
    r = infer_style_from_librosa_summary(_summary(bpm=72.0))
    assert "ballad" in r.style_label.lower() or "slow" in r.style_label.lower()


def test_infer_style_respects_skip_env(monkeypatch):
    monkeypatch.setenv("HARMONIQ_SKIP_STYLE_DETECT", "1")
    r = infer_style_from_librosa_summary(_summary(bpm=150.0))
    assert r.style_label == "general"
    assert r.technique_hints == []
