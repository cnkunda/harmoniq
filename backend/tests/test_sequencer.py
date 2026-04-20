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
