"""Commit 179: mentor trajectory endpoint."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException

from app.mentor import MentorGenerationError, generate_mentor_note
from app.schemas import MentorTrajectoryRequest, MentorTrajectoryResponse

logger = logging.getLogger("harmoniq.api.mentor")

router = APIRouter(tags=["Mentor"])


@router.post(
    "/mentor/trajectory",
    response_model=MentorTrajectoryResponse,
    summary="POST /mentor/trajectory — monthly mentor note from a compact trajectory",
)
async def mentor_trajectory(payload: MentorTrajectoryRequest) -> MentorTrajectoryResponse:
    if os.getenv("HARMONIQ_SKIP_MENTOR", "").strip() == "1":
        raise HTTPException(status_code=503, detail="Mentor disabled (HARMONIQ_SKIP_MENTOR=1).")

    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_COACH_IN_TESTS") != "1":
        raise HTTPException(status_code=503, detail="Mentor disabled in tests.")

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Mentor unavailable: ANTHROPIC_API_KEY is not configured.")

    try:
        note = await asyncio.to_thread(generate_mentor_note, api_key=api_key, request=payload)
    except MentorGenerationError as exc:
        logger.warning("mentor generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Mentor could not produce a note this time. Try again.") from exc
    except Exception as exc:
        logger.exception("mentor generation crashed")
        raise HTTPException(status_code=502, detail="Mentor request failed.") from exc

    return MentorTrajectoryResponse(note=note)
