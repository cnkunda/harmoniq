"""Harmoniq discovery router — song recommendations based on harmonic similarity."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.discovery import generate_discovery_suggestions
from app.jobs import jobs
from app.schemas import DiscoveryRequest, DiscoveryResponse, DiscoverySuggestionItem, LessonJSON

logger = logging.getLogger("harmoniq.api.discovery")

router = APIRouter(tags=["Discovery"])


@router.post(
    "/discovery/recommendations",
    response_model=DiscoveryResponse,
    summary="POST /discovery/recommendations — song discovery based on harmonic similarity",
)
async def discovery_recommendations(req: DiscoveryRequest):
    candidate_lessons = list(req.library_lessons) if req.library_lessons else []
    if not candidate_lessons:
        for job in jobs.values():
            if job.result:
                candidate_lessons.append(job.result)
    mastered_lessons: list[LessonJSON] = []
    mastered_ids = set(req.mastered_job_ids)
    for lesson in candidate_lessons:
        if lesson.job_id and lesson.job_id in mastered_ids:
            mastered_lessons.append(lesson)
    for job_id in req.mastered_job_ids:
        if not any(l.job_id == job_id for l in mastered_lessons):
            job = jobs.get(job_id)
            if job and job.result:
                mastered_lessons.append(job.result)
    suggestions = generate_discovery_suggestions(
        mastered_lessons=mastered_lessons,
        candidate_lessons=candidate_lessons,
        skill_nodes=req.skill_nodes,
        limit=req.limit,
        min_similarity=req.min_similarity,
    )
    suggestion_items = [
        DiscoverySuggestionItem(
            job_id=s.job_id,
            song_title=s.song_title,
            artist=s.artist,
            key=s.key,
            style_label=s.style_label,
            tempo=s.tempo,
            reason_label=s.reason_label,
            similarity_score=s.similarity_score,
            technique_focus=s.technique_focus,
        )
        for s in suggestions
    ]
    return DiscoveryResponse(suggestions=suggestion_items)
