"""ML Fallback Logic — composite transcription confidence tests."""

from __future__ import annotations

import pytest

from app.transcription_confidence import (
    chord_section_confidence,
    composite_transcription_confidence,
    vocals_coverage_confidence,
)
from app.schemas import ChordEvent, ChordTimeline


def _timeline() -> ChordTimeline:
    return ChordTimeline(
        events=[
            ChordEvent(timestamp=0.0, chord="C", confidence=0.95),
            ChordEvent(timestamp=2.0, chord="G", confidence=0.7),
            ChordEvent(timestamp=4.0, chord="N", confidence=1.0),
            ChordEvent(timestamp=6.0, chord="Am", confidence=0.8),
        ]
    )


def test_chord_section_confidence_is_duration_weighted_and_skips_no_chord():
    tl = _timeline()
    conf = chord_section_confidence(tl)
    assert conf is not None
    # N excluded; C lasts 2s @0.95, G lasts 4s (until Am) @0.7, Am 1s (tail) @0.8
    assert conf == pytest.approx((1.9 + 2.8 + 0.8) / 7.0)


def test_chord_section_confidence_honors_section_bounds():
    tl = _timeline()
    assert chord_section_confidence(tl, section_start=2.0, section_end=6.0) == pytest.approx(0.7)
    assert chord_section_confidence(tl, section_start=0.0, section_end=2.0) == pytest.approx(0.95)


def test_chord_section_confidence_empty_timeline_returns_none():
    assert chord_section_confidence(None) is None
    assert chord_section_confidence(ChordTimeline(events=[])) is None
    assert chord_section_confidence(ChordTimeline(events=[ChordEvent(timestamp=0.0, chord="N", confidence=1.0)])) is None


def test_vocals_coverage_confidence_maps_beat_ratio():
    beats = 100
    half = [{"beat": i} for i in range(50)]
    assert vocals_coverage_confidence(half, beats) == pytest.approx(0.92)
    quarter = [{"beat": i} for i in range(25)]
    assert vocals_coverage_confidence(quarter, beats) == pytest.approx(0.82)
    sparse = [{"beat": i} for i in range(12)]
    assert vocals_coverage_confidence(sparse, beats) == pytest.approx(0.7)
    tiny = [{"beat": i} for i in range(4)]
    assert vocals_coverage_confidence(tiny, beats) == pytest.approx(0.55)
    none = [{"beat": i} for i in range(1)]
    assert vocals_coverage_confidence(none, beats) == pytest.approx(0.35)


def test_vocals_coverage_ignores_non_beat_rows_and_dedups():
    rows = [{"beat": 3}, {"beat": 3}, {"word": "no-beat"}, {}]
    # 2 unique beats of 40 -> ratio 0.05 -> 0.35 bucket
    assert vocals_coverage_confidence(rows, 40) == pytest.approx(0.35)


def test_vocals_coverage_normalizes_in_bar_rows():
    """Regression: map_words_to_lyrics_aligned emits beat-within-bar (0..3) +
    bar, which used to collapse coverage to <= 4 distinct slots and floor
    every vocal song at 0.35."""
    # 50 words across bars 0..12, beat 0..3 -> 50 unique (bar, beat) slots
    rows = [
        {"word": f"w{i}", "time_seconds": float(i) * 0.5, "bar": i // 4, "beat": i % 4}
        for i in range(50)
    ]
    assert vocals_coverage_confidence(rows, 100) == pytest.approx(0.92)
    # Sparse in-bar coverage of a 100-beat song -> 0.35 bucket, not floor-collapsed
    sparse = [{"word": "w", "bar": i // 4, "beat": i % 4} for i in range(2)]
    assert vocals_coverage_confidence(sparse, 100) == pytest.approx(0.35)
    # Mixed producers: absolute beats + in-bar rows both count
    mixed = [{"beat": 0}, {"beat": 40}, {"word": "w", "bar": 2, "beat": 1}]
    # slots {0, 40, 9} -> 3/100 -> 0.55 bucket
    assert vocals_coverage_confidence(mixed, 100) == pytest.approx(0.55)


def test_vocals_coverage_no_data_returns_none():
    assert vocals_coverage_confidence(None, 100) is None
    assert vocals_coverage_confidence([], 100) is None
    assert vocals_coverage_confidence([{"beat": 0}], 0) is None


def test_composite_blend_and_instrumental():
    # both signals -> 60/40 blend
    assert composite_transcription_confidence(0.9, 0.8) == pytest.approx(0.86)
    # instrumental (no vocals) -> chord alone
    assert composite_transcription_confidence(0.85, None) == pytest.approx(0.85)
    # chords failed but vocals present -> discounted vocals
    assert composite_transcription_confidence(None, 0.8) == pytest.approx(0.68)
    # nothing at all -> old failure floor
    assert composite_transcription_confidence(None, None) == pytest.approx(0.1)


def test_composite_caps_when_guitar_stem_unusable():
    assert composite_transcription_confidence(0.95, 0.92, guitar_stem_usable=False) == pytest.approx(0.25)
    assert composite_transcription_confidence(0.1, None, guitar_stem_usable=False) <= 0.25


def test_composite_clamps_to_sane_range():
    assert composite_transcription_confidence(1.5, None) <= 1.0
    assert composite_transcription_confidence(-1.0, None) >= 0.05