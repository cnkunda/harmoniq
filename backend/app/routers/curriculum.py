"""Harmoniq curriculum router — session suggestions and practice plan generation."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from app.curriculum import suggest_next_session
from app.jobs import jobs
from app.schemas import CurriculumSuggestRequest, CurriculumSuggestResponse, CurriculumSuggestionItem, PracticePlan, PracticePlanRequest, LessonJSON
from app.sequencer import generate_practice_plan

logger = logging.getLogger("harmoniq.api.curriculum")

router = APIRouter(tags=["Curriculum"])


@router.post(
    "/curriculum/suggest",
    response_model=CurriculumSuggestResponse,
    summary="POST /curriculum/suggest — ranked next-session suggestions",
)
async def curriculum_suggest(payload: CurriculumSuggestRequest) -> CurriculumSuggestResponse:
    if os.getenv("HARMONIQ_SKIP_CURRICULUM", "").strip() == "1":
        logger.info("curriculum_suggest skipped via HARMONIQ_SKIP_CURRICULUM=1")
        return CurriculumSuggestResponse(ranked=[])
    candidate_lessons = []
    for job_id in payload.job_ids:
        key = str(job_id).strip()
        if not key:
            continue
        job = jobs.get(key)
        if not job or job.status != "complete" or job.result is None:
            continue
        candidate_lessons.append(job.result)
    ranked = suggest_next_session(payload.player_profile, candidate_lessons)
    return CurriculumSuggestResponse(ranked=[
        CurriculumSuggestionItem(job_id=item.job_id, reason_label=item.reason_label, technique_focus=item.technique_focus)
        for item in ranked
    ])


@router.post(
    "/practice/plan",
    response_model=PracticePlan,
    summary="POST /practice/plan — ordered drill queue from profile + library",
)
async def practice_plan(payload: PracticePlanRequest) -> PracticePlan:
    skip_llm = os.getenv("HARMONIQ_SKIP_PRACTICE_PLAN", "").strip() == "1"
    if skip_llm:
        logger.info("practice_plan using template intros (HARMONIQ_SKIP_PRACTICE_PLAN=1)")
    embedded_by_id: dict[str, LessonJSON] = {}
    for lesson in payload.library_lessons:
        jid = (lesson.job_id or "").strip()
        if jid:
            embedded_by_id[jid] = lesson
    candidate_lessons: list[LessonJSON] = []
    seen: set[str] = set()
    for job_id in payload.job_ids:
        key = str(job_id).strip()
        if not key or key in seen:
            continue
        job = jobs.get(key)
        chosen: LessonJSON | None = None
        if job and job.status == "complete" and job.result is not None:
            chosen = job.result
        else:
            chosen = embedded_by_id.get(key)
        if chosen is not None:
            candidate_lessons.append(chosen)
            seen.add(key)
    return generate_practice_plan(
        player_profile=payload.player_profile,
        library_lessons=candidate_lessons,
        duration_minutes=payload.duration_minutes,
        skip_llm=skip_llm,
        mood=payload.mood,
    )
