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
        assert any(kw in first for kw in ["chromatic", "spider", "tritone", "interpolat", "slonimsky"])


def test_difficulty_filtering() -> None:
    """difficulty=1 should only return exercises with difficulty <= 1."""
    profile = PlayerProfile(weak_areas=["finger_independence"])
    for seed in range(20):
        plan = generate_warmup(profile, TasteProfile(), seed=seed, difficulty=1)
        for ex in plan.exercises:
            assert ex.difficulty <= 1, f"{ex.name} has difficulty {ex.difficulty} > 1"


def test_difficulty_defaults_to_2() -> None:
    """Default difficulty picks exercises up to level 2."""
    profile = PlayerProfile(weak_areas=["timing"])
    plan = generate_warmup(profile, TasteProfile(), seed=42)
    assert len(plan.exercises) == 3


def test_difficulty_from_experience_level() -> None:
    """beginner experience_level maps to difficulty 1."""
    from app.schemas import LearningContext

    lc = LearningContext(experience_level="beginner")
    profile = PlayerProfile(weak_areas=["finger_independence"], learning_context=lc)
    plan = generate_warmup(profile, TasteProfile(), seed=42)
    for ex in plan.exercises:
        assert ex.difficulty <= 1
