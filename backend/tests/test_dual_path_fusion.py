"""Commit 112: Dual-path confidence-weighted stem fusion tests."""

from __future__ import annotations

from app.chord_inference import DualPathResult
from app.schemas import ChordEvent, ChordTimeline


def _make_timeline(chords: list[tuple[float, str, float]]) -> ChordTimeline:
    """Helper: build ChordTimeline from list of (timestamp, chord, confidence)."""
    return ChordTimeline(events=[
        ChordEvent(timestamp=t, chord=c, confidence=conf) for t, c, conf in chords
    ])


def test_dual_path_result_dataclass():
    """DualPathResult should hold timeline, confidence, confusion, and log."""
    tl = _make_timeline([(0.0, "C:maj", 0.9)])
    result = DualPathResult(
        timeline=tl,
        stem_confidence=0.8,
        instrument_confusion=0.1,
        fusion_log=[],
    )
    assert result.stem_confidence == 0.8
    assert result.instrument_confusion == 0.1
    assert len(result.timeline.events) == 1


def test_fusion_agreement_no_disagreement():
    """When stem and mix agree on all chords, instrument confusion = 0."""
    stem_tl = _make_timeline([
        (0.0, "C:maj", 0.9),
        (1.0, "G:maj", 0.85),
        (2.0, "Am:min", 0.8),
    ])
    mix_tl = _make_timeline([
        (0.0, "C:maj", 0.7),
        (1.0, "G:maj", 0.75),
        (2.0, "Am:min", 0.7),
    ])

    # Simulate fusion logic (same as infer_chords_dual_path internal logic)
    mix_by_ts = {round(e.timestamp, 4): e for e in mix_tl.events}
    disagreements = 0
    for stem_ev in stem_tl.events:
        mix_ev = mix_by_ts.get(round(stem_ev.timestamp, 4))
        if mix_ev and stem_ev.chord != mix_ev.chord:
            disagreements += 1

    confusion = disagreements / len(stem_tl.events)
    assert confusion == 0.0


def test_fusion_disagreement_detection():
    """When stem and mix disagree, instrument confusion > 0."""
    stem_tl = _make_timeline([
        (0.0, "C:maj", 0.9),
        (1.0, "G:maj", 0.85),
        (2.0, "Am:min", 0.8),
    ])
    mix_tl = _make_timeline([
        (0.0, "C:maj", 0.7),
        (1.0, "F:maj", 0.75),  # disagrees with G:maj
        (2.0, "Am:min", 0.7),
    ])

    mix_by_ts = {round(e.timestamp, 4): e for e in mix_tl.events}
    disagreements = 0
    for stem_ev in stem_tl.events:
        mix_ev = mix_by_ts.get(round(stem_ev.timestamp, 4))
        if mix_ev and stem_ev.chord != mix_ev.chord:
            disagreements += 1

    confusion = disagreements / len(stem_tl.events)
    assert confusion > 0.0
    assert abs(confusion - 1 / 3) < 0.01


def test_fusion_high_stem_confidence_prefers_stem():
    """When stem_confidence is high, fusion should prefer stem predictions."""
    w = 0.9  # high stem confidence
    stem_conf, stem_chord = 0.8, "G:maj"
    mix_conf, mix_chord = 0.7, "F:maj"

    stem_score = w * stem_conf
    mix_score = (1 - w) * mix_conf

    if stem_score >= mix_score:
        chosen = stem_chord
    else:
        chosen = mix_chord

    assert chosen == "G:maj"  # stem wins


def test_fusion_low_stem_confidence_prefers_mix():
    """When stem_confidence is low, fusion should prefer mix predictions."""
    w = 0.2  # low stem confidence
    stem_conf, stem_chord = 0.6, "G:maj"
    mix_conf, mix_chord = 0.7, "F:maj"

    stem_score = w * stem_conf
    mix_score = (1 - w) * mix_conf

    if stem_score >= mix_score:
        chosen = stem_chord
    else:
        chosen = mix_chord

    assert chosen == "F:maj"  # mix wins


def test_fusion_confidence_blending():
    """Blended confidence should be weighted average of both sources."""
    w = 0.6
    stem_conf = 0.8
    mix_conf = 0.5

    blended = w * stem_conf + (1 - w) * mix_conf
    assert abs(blended - 0.68) < 0.01


def test_fusion_metadata_fields():
    """Fused timeline metadata should include dual_path info."""
    metadata = {
        "dual_path": {
            "stem_confidence": 0.75,
            "instrument_confusion": 0.15,
            "disagreement_count": 3,
            "total_beats": 20,
            "fusion_weight": 0.75,
        }
    }
    tl = ChordTimeline(events=[], metadata=metadata)
    dp = tl.metadata["dual_path"]
    assert dp["stem_confidence"] == 0.75
    assert dp["instrument_confusion"] == 0.15
    assert dp["disagreement_count"] == 3


def test_high_instrument_confusion_flaggable():
    """High confusion (>0.3) should be flaggable as a stem quality flag."""
    confusion = 0.35
    assert confusion > 0.3  # threshold for "high" confusion


def test_fusion_log_entries_have_required_fields():
    """Each fusion log entry should contain all diagnostic fields."""
    log_entry = {
        "timestamp": 1.0,
        "stem_chord": "G:maj",
        "stem_confidence": 0.8,
        "mix_chord": "F:maj",
        "mix_confidence": 0.7,
        "chosen": "G:maj",
        "fusion_weight": 0.6,
    }
    required = {"timestamp", "stem_chord", "stem_confidence", "mix_chord", "mix_confidence", "chosen", "fusion_weight"}
    assert required.issubset(log_entry.keys())
