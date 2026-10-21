"""Practice plan sequencer (commit 70)."""

from __future__ import annotations

from app.schemas import LessonJSON, LessonSectionStub, PlayerProfile
from app.sequencer import generate_practice_plan


def _lesson(*, job_id: str, style: str, section_tags: list[str]) -> LessonJSON:
    return LessonJSON(
        job_id=job_id,
        song_title=f"Title-{job_id}",
        artist="Tester",
        style_label=style,
        tempo=100.0,
        sections=[
            LessonSectionStub.model_validate(
                {"label": "Intro", "confidence": 0.75, "technique_tags": section_tags},
            )
        ],
    )


def test_practice_plan_empty_library_two_slots() -> None:
    plan = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=[],
        duration_minutes=25,
        skip_llm=True,
    )
    assert len(plan.slots) == 2
    assert plan.slots[0].slot_type == "warmup"
    assert plan.slots[1].slot_type == "free_jam"
    assert plan.slots[0].exercise_ref == "warmup_session"
    assert plan.slots[0].warmup_plan is not None
    assert len(plan.slots[0].warmup_plan.exercises) == 3
    assert plan.slots[0].lesson_ref is None
    assert plan.total_duration_seconds == 25 * 60


def test_practice_plan_three_songs_four_slots_order_and_budget() -> None:
    lib = [
        _lesson(job_id="job-a", style="rock", section_tags=["bend"]),
        _lesson(job_id="job-b", style="rock", section_tags=["bend"]),
        _lesson(job_id="job-c", style="rock", section_tags=["vibrato"]),
    ]
    plan = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=lib,
        duration_minutes=25,
        skip_llm=True,
    )
    assert [s.slot_type for s in plan.slots] == ["warmup", "technique", "song_section", "free_jam"]
    total = sum(s.duration_seconds for s in plan.slots)
    assert total == 25 * 60
    assert 120 <= plan.slots[-1].duration_seconds <= 25 * 60
    song = plan.slots[2]
    assert song.lesson_ref in {"job-a", "job-b", "job-c"}
    assert song.slot_type == "song_section"
    assert plan.slots[0].slot_type == "warmup"
    assert plan.slots[0].warmup_plan is not None
    assert len(plan.slots[0].warmup_plan.exercises) == 3


def test_practice_plan_tired_shorter_and_skips_technique_slot() -> None:
    lib = [
        _lesson(job_id="job-a", style="rock", section_tags=["bend"]),
        _lesson(job_id="job-b", style="rock", section_tags=["vibrato"]),
    ]
    standard = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=lib,
        duration_minutes=25,
        skip_llm=True,
        mood=None,
    )
    tired = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=lib,
        duration_minutes=25,
        skip_llm=True,
        mood="tired",
    )
    assert tired.total_duration_seconds < standard.total_duration_seconds
    assert [s.slot_type for s in tired.slots] == ["warmup", "song_section", "free_jam"]


def test_mood_changes_template_intro_energy() -> None:
    lib = [
        _lesson(job_id="job-a", style="rock", section_tags=["bend"]),
        _lesson(job_id="job-b", style="rock", section_tags=["vibrato"]),
    ]
    tired = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=lib,
        duration_minutes=25,
        skip_llm=True,
        mood="tired",
    )
    on_fire = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=lib,
        duration_minutes=25,
        skip_llm=True,
        mood="on_fire",
    )
    assert "gentle" in tired.slots[0].coach_intro.lower()
    assert "great spark" in on_fire.slots[0].coach_intro.lower()


def _lesson_library() -> list[LessonJSON]:
    return [
        _lesson(job_id="job-a", style="rock", section_tags=["bend"]),
        _lesson(job_id="job-b", style="rock", section_tags=["vibrato"]),
    ]


def test_plan_and_slot_ids_are_stable_nonempty_and_unique() -> None:
    plan = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=_lesson_library(),
        duration_minutes=25,
        skip_llm=True,
    )
    assert plan.plan_id
    assert len({s.slot_id for s in plan.slots}) == len(plan.slots)
    assert all(s.slot_id for s in plan.slots)
    assert plan.total_duration_seconds == sum(s.duration_seconds for s in plan.slots)


def test_slot_difficulty_mapping() -> None:
    plan = generate_practice_plan(
        player_profile=PlayerProfile(weak_areas=["bending"]),
        library_lessons=_lesson_library(),
        duration_minutes=25,
        skip_llm=True,
    )
    by_type = {s.slot_type: s for s in plan.slots}
    assert by_type["technique"].difficulty == 2
    assert by_type["song_section"].difficulty == 3
    assert by_type["free_jam"].difficulty == 2
    warmup_difficulty = max(e.difficulty for e in by_type["warmup"].warmup_plan.exercises)
    assert by_type["warmup"].difficulty == warmup_difficulty
    assert all(s.intent == "practice" for s in plan.slots)


def test_due_skill_outranks_higher_scoring_non_due_skill() -> None:
    from datetime import date

    from app.curriculum import select_skill_focus
    from app.schemas import SkillNode

    profile = PlayerProfile(
        skill_nodes=[
            SkillNode(id="bend_accuracy", label="Bending", score=0.5),
            SkillNode(id="timing", label="Timing", score=0.6, next_review_date=date(2026, 1, 1)),
        ],
    )
    focus = select_skill_focus(profile, today=date(2026, 6, 1))
    assert focus is not None
    assert focus.node_id == "timing"
    assert focus.is_due is True


def test_weak_skill_becomes_practice_target() -> None:
    from app.schemas import SkillNode

    plan = generate_practice_plan(
        player_profile=PlayerProfile(
            weak_areas=["bending"],
            skill_nodes=[SkillNode(id="bend_accuracy", label="Bending", score=0.3)],
        ),
        library_lessons=_lesson_library(),
        duration_minutes=25,
        skip_llm=True,
    )
    technique = next(s for s in plan.slots if s.slot_type == "technique")
    assert technique.title == "Bending drill"
    assert technique.intent == "practice"
    assert technique.target_skill == "bend_accuracy"
    assert technique.technique_focus == "bending"


def test_strong_skill_becomes_review_slot_with_reclaimed_time() -> None:
    from app.schemas import SkillNode

    standard = generate_practice_plan(
        player_profile=PlayerProfile(skill_nodes=[SkillNode(id="bend_accuracy", label="Bending", score=0.5)]),
        library_lessons=_lesson_library(),
        duration_minutes=25,
        skip_llm=True,
    )
    strong = generate_practice_plan(
        player_profile=PlayerProfile(skill_nodes=[SkillNode(id="bend_accuracy", label="Bending", score=0.92)]),
        library_lessons=_lesson_library(),
        duration_minutes=25,
        skip_llm=True,
    )
    standard_technique = next(s for s in standard.slots if s.slot_type == "technique")
    review = next(s for s in strong.slots if s.slot_type == "technique")
    assert review.title == "Bending review"
    assert review.intent == "review"
    assert review.difficulty == 1
    assert review.duration_seconds < standard_technique.duration_seconds
    assert strong.total_duration_seconds == 25 * 60
    assert next(s for s in strong.slots if s.slot_type == "free_jam").duration_seconds > next(
        s for s in standard.slots if s.slot_type == "free_jam"
    ).duration_seconds
