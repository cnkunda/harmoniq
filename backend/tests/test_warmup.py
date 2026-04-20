"""Session warm-up generator (commit 73)."""

from __future__ import annotations

from app.exercises.warmup_generator import generate_warmup
from app.schemas import PlayerProfile, TasteProfile


def test_second_exercise_targets_weak_area_string_skipping() -> None:
    profile = PlayerProfile(weak_areas=["string_skipping"])
    plan = generate_warmup(profile, TasteProfile(), seed=42)
    assert len(plan.exercises) == 3
    assert plan.exercises[1].technique_tag == "string_skipping"


def test_opener_is_chromatic_or_spider() -> None:
    profile = PlayerProfile(weak_areas=["bending"])
    for seed in range(8):
        plan = generate_warmup(profile, TasteProfile(style_label="rock"), seed=seed)
        first = plan.exercises[0].name.lower()
        assert "chromatic" in first or "spider" in first
