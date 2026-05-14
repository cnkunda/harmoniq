"""Harmoniq taste router — Spotify taste derivation, quiz-based taste profiling."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Query

import app.spotify as spotify_api
from app.schemas import TasteDeriveRequest, TasteProfile, SpotifyTasteProfile
from app.taste import derive_taste_profile

logger = logging.getLogger("harmoniq.api.taste")

router = APIRouter(tags=["Taste"])


@router.post(
    "/taste/derive",
    response_model=TasteProfile,
    summary="POST /taste/derive — deterministic TasteProfile from Spotify or quiz",
)
async def taste_derive(payload: TasteDeriveRequest) -> TasteProfile:
    if os.getenv("HARMONIQ_SKIP_TASTE_DERIVE", "").strip() == "1":
        raise HTTPException(status_code=503, detail="Taste derivation disabled (HARMONIQ_SKIP_TASTE_DERIVE=1).")
    return derive_taste_profile(spotify_profile=payload.spotify_profile, quiz_answers=payload.quiz_answers, taste_source=payload.taste_source)


@router.get(
    "/taste/spotify",
    response_model=SpotifyTasteProfile,
    summary="GET /taste/spotify — aggregated taste",
)
async def taste_spotify(client_session: str = Query(..., min_length=1, max_length=256)) -> SpotifyTasteProfile:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    try:
        return await spotify_api.build_taste_profile(client_session)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
