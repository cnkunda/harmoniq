"""Warm-up fretboard_guide from pool → WarmupExercise (curriculum data on the wire)."""

from __future__ import annotations

from app.exercises.warmup_generator import _load_pool, generate_warmup
from app.schemas import FretboardGuide, PlayerProfile, TasteProfile, WarmupExercise


def test_pool_chr_02_defines_fretboard_guide() -> None:
    pool = _load_pool()
    row = next(x for x in pool if x.get("id") == "pool_chr_02")
    guide = FretboardGuide.model_validate(row["fretboard_guide"])
    assert len(guide.cells) == 2
    assert guide.cells[0].string == 3 and guide.cells[0].fret == 5
    assert guide.cells[1].string == 3 and guide.cells[1].fret == 6
    assert guide.caption


def test_warmup_exercise_roundtrip_fretboard_guide() -> None:
    g = FretboardGuide(
        cells=[{"string": 2, "fret": 4, "variant": "primary"}],
        caption="Test",
    )
    ex = WarmupExercise(
        name="X",
        description="",
        duration_seconds=45,
        technique_tag="timing",
        bpm=80,
        fretboard_guide=g,
    )
    dumped = ex.model_dump(mode="json")
    assert dumped["fretboard_guide"]["cells"][0]["fret"] == 4


def test_generate_warmup_preserves_guide_for_chromatic_pairs_opener() -> None:
    profile = PlayerProfile(weak_areas=["bending"])
    for seed in range(120):
        plan = generate_warmup(profile, TasteProfile(), seed=seed)
        ex0 = plan.exercises[0]
        if ex0.name == "Single-string chromatic pairs":
            assert ex0.fretboard_guide is not None
            assert len(ex0.fretboard_guide.cells) == 2
            assert ex0.fretboard_guide.caption
            return
    raise AssertionError("expected at least one seed with chromatic pairs opener")
