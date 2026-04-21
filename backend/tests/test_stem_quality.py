"""stem_quality metrics — isolation hints for piano-led mixes (MANUAL_QA isolation)."""

from __future__ import annotations

from app.stem_quality import collect_stem_quality_flags, stem_isolation_flags_from_metrics


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
