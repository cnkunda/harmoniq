"""stem_quality metrics — isolation hints for piano-led mixes (MANUAL_QA isolation)."""

from __future__ import annotations

from app.stem_quality import (
    _compute_stem_confidence,
    collect_stem_quality_flags,
    stem_isolation_flags_from_metrics,
)


def test_flags_empty_when_balanced():
    assert stem_isolation_flags_from_metrics(r_g=0.05, r_p=0.05, corr_abs=0.5) == []


def test_piano_dominates_flag():
    flags = stem_isolation_flags_from_metrics(r_g=0.01, r_p=0.03, corr_abs=0.2)
    assert "piano_dominates_guitar" in flags


def test_collect_includes_near_silent_guitar():
    # Quiet guitar vs mix but ratio not "buried" (guitar RMS share of mix is OK)
    flags = collect_stem_quality_flags(r_m=0.01, r_g=0.0005, r_p=0.002, corr_abs=0.1)
    assert "guitar_near_silent" in flags
    assert "guitar_buried_in_mix" not in flags


def test_collect_buried_guitar():
    flags = collect_stem_quality_flags(r_m=0.5, r_g=0.005, r_p=0.05, corr_abs=0.1)
    assert "guitar_buried_in_mix" in flags


def test_envelope_collision_requires_strong_corr_and_piano_energy():
    # High corr but piano quieter than guitar → no collision flag
    assert stem_isolation_flags_from_metrics(r_g=0.05, r_p=0.02, corr_abs=0.95) == []

    flags = stem_isolation_flags_from_metrics(r_g=0.02, r_p=0.025, corr_abs=0.95)
    assert "guitar_piano_envelope_collision" in flags


# --- Commit 112: stem_confidence tests ---


def test_stem_confidence_clean_guitar_near_one():
    """Clean guitar stem with no flags should yield confidence ≈ 1.0."""
    conf = _compute_stem_confidence(
        r_m=0.5, r_g=0.3, r_p=0.01, corr_abs=0.2, flags=[],
    )
    assert conf == 1.0


def test_stem_confidence_near_silent_guitar_is_zero():
    """Near-silent guitar should yield confidence = 0.0."""
    conf = _compute_stem_confidence(
        r_m=0.5, r_g=0.0005, r_p=0.01, corr_abs=0.1,
        flags=["guitar_near_silent"],
    )
    assert conf == 0.0


def test_stem_confidence_buried_guitar_reduced():
    """Guitar buried in mix should reduce confidence significantly."""
    flags = collect_stem_quality_flags(r_m=0.5, r_g=0.005, r_p=0.05, corr_abs=0.1)
    assert "guitar_buried_in_mix" in flags
    conf = _compute_stem_confidence(r_m=0.5, r_g=0.005, r_p=0.05, corr_abs=0.1, flags=flags)
    assert 0.0 < conf < 0.7


def test_stem_confidence_piano_dominates_reduced():
    """Piano dominance should reduce confidence."""
    flags = ["piano_dominates_guitar"]
    conf = _compute_stem_confidence(
        r_m=0.5, r_g=0.01, r_p=0.1, corr_abs=0.3, flags=flags,
    )
    assert 0.0 < conf < 0.7


def test_stem_confidence_envelope_collision_reduced():
    """Envelope collision should reduce confidence."""
    flags = ["guitar_piano_envelope_collision"]
    conf = _compute_stem_confidence(
        r_m=0.5, r_g=0.02, r_p=0.025, corr_abs=0.95, flags=flags,
    )
    assert 0.0 < conf < 1.0  # reduced from perfect
    # Perfect correlation (1.0) with threshold 0.88 → corr_excess = (0.95-0.88)/(1-0.88) ≈ 0.58
    # Penalty = 0.3 * 0.58 ≈ 0.175 → confidence ≈ 0.825
    assert 0.7 < conf < 0.9


def test_stem_confidence_bounded_zero_one():
    """Confidence should always be in [0, 1]."""
    conf = _compute_stem_confidence(
        r_m=0.5, r_g=0.005, r_p=0.5, corr_abs=0.99,
        flags=["guitar_buried_in_mix", "piano_dominates_guitar", "guitar_piano_envelope_collision"],
    )
    assert 0.0 <= conf <= 1.0


def test_stem_confidence_stem_classification_has_field():
    """StemClassification dataclass should include stem_confidence field."""
    from app.stem_quality import StemClassification
    sc = StemClassification(
        guitar_stem_usable=True,
        analysis_audio_role="guitar_stem",
        flags=(),
        user_warning=None,
        stem_confidence=0.85,
    )
    assert sc.stem_confidence == 0.85


def test_stem_confidence_low_spectral_overlap_reduces():
    """Low spectral overlap should reduce confidence."""
    conf_high = _compute_stem_confidence(
        r_m=0.5, r_g=0.3, r_p=0.01, corr_abs=0.2, flags=[], spectral_overlap=0.9,
    )
    conf_low = _compute_stem_confidence(
        r_m=0.5, r_g=0.3, r_p=0.01, corr_abs=0.2, flags=[], spectral_overlap=0.4,
    )
    assert conf_high == 1.0
    assert conf_low < conf_high
    assert 0.5 < conf_low < 1.0


def test_stem_confidence_spectral_overlap_default_is_one():
    """Default spectral_overlap=1.0 should not penalize."""
    conf_default = _compute_stem_confidence(
        r_m=0.5, r_g=0.3, r_p=0.01, corr_abs=0.2, flags=[],
    )
    conf_explicit = _compute_stem_confidence(
        r_m=0.5, r_g=0.3, r_p=0.01, corr_abs=0.2, flags=[], spectral_overlap=1.0,
    )
    assert conf_default == conf_explicit
