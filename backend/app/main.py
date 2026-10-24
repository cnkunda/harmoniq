"""Harmoniq API entrypoint — health, CORS, and remaining inline routes. Routers are in app/routers/."""

from __future__ import annotations

import os

# Force CPU mode for TensorFlow — the installed CuDNN 9.1.0 is incompatible
# with TF 2.21.0 (compiled with CuDNN 9.3.0), causing "No DNN in stream
# executor" errors on GPU. Set before any TF import.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("KERAS_BACKEND", "tensorflow")

import asyncio
import base64
import json
import logging
import math
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path as FastPath, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app.coach import generate_jam_coach_summary, generate_onboarding_placement_summary, generate_quick_feedback, generate_orient_annotation, generate_theory_annotation
from app.jam_backing import Mrt2BackingGenerator, build_mrt2_prompt, load_bundled_track_wav, select_bundled_track
from app.lyria_clip import generate_orient_clip
from app.routers.analyze import router as analyze_router
from app.routers.export import router as export_router
from app.routers.discovery import router as discovery_router
from app.routers.taste import router as taste_router
from app.routers.curriculum import router as curriculum_router
from app.routers.mt3 import router as mt3_router
from app.routers.ws import router as ws_router
from app.schemas import (
    JamBackingRequest,
    JamBackingResponse,
    JamScoreRequest,
    JamScoreResult,
    OnboardingPlacementRequest,
    OnboardingPlacementResponse,
    OrientClipRequest,
    OrientClipResponse,
    QuickFeedbackRequest,
    QuickFeedbackResponse,
    ScoreRequest,
    ScoreResult,
    SpotifyAvailableGenreSeeds,
    SpotifyPlaybackState,
    SpotifyPlaylistDetail,
    SpotifyPlaylistItems,
    SpotifyPlaylistList,
    SpotifyRecommendationsResult,
    SpotifySearchResult,
    TheoryAnnotationRequest,
    TheoryAnnotationResponse,
)
from app.scoring_constants import RELIABILITY_BANDS, SCORE_CONTRACT_VERSION, clamp01
import app.spotify as spotify_api
from app.tab_catalog.provider import TabSearchResponse, search_tabs

# Load backend/.env so local secrets apply when using uvicorn
_backend_root = Path(__file__).resolve().parents[1]
load_dotenv(_backend_root / ".env")

logger = logging.getLogger("harmoniq.api")
logger.setLevel(logging.INFO)

PITCH_CLASS_KEY_RE = re.compile(r"^pc_(C|C#|D|D#|E|F|F#|G|G#|A|A#|B)$")
GENERIC_MAP_KEY_RE = re.compile(r"^[A-Za-z0-9._:#\-/+(). ]{1,64}$")

async def _run_startup_cleanup():
    """Run data cleanup as a background task on startup."""
    skip = os.getenv("HARMONIQ_SKIP_CLEANUP", "").strip() == "1"
    if skip:
        logger.info("Startup cleanup skipped (HARMONIQ_SKIP_CLEANUP=1)")
        return
    try:
        from scripts.cleanup_data import run_cleanup

        backend_root = Path(__file__).resolve().parents[1]
        data_dir = backend_root / "data"
        retention_raw = os.getenv("HARMONIQ_CLEANUP_RETENTION_DAYS", "7").strip()
        retention = max(1, int(retention_raw)) if retention_raw else 7
        logger.info("Startup cleanup (retention=%d days, data=%s)", retention, data_dir)
        result = run_cleanup(data_dir, backend_root, retention, dry_run=False)
        if result["total_failed"] > 0:
            logger.warning("Startup cleanup completed with %d error(s)", result["total_failed"])
    except Exception:
        logger.exception("Startup cleanup failed")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run startup cleanup and yield."""
    asyncio.create_task(_run_startup_cleanup())

    # Initialize database connection
    try:
        from app.db import init_db as _init_db
        await asyncio.to_thread(_init_db)
        logger.info("Database initialized")
    except Exception:
        logger.warning("Database not available — running without persistence")

    # Load existing jobs from database (survives restarts)
    try:
        from app.jobs import jobs, load_jobs_from_db
        loaded = load_jobs_from_db()
        if loaded > 0:
            logger.info("Loaded %d jobs from database", loaded)
    except Exception:
        logger.exception("Failed to load jobs from database on startup")

    # Commit 110: reload completed/failed jobs from disk (fallback for legacy)
    try:
        from app.jobs import load_jobs_from_disk as _load_from_disk
        disk_loaded = _load_from_disk()
        if disk_loaded > 0:
            logger.info("Loaded %d legacy jobs from disk", disk_loaded)
    except Exception:
        logger.exception("Failed to load jobs from disk on startup")

    # Commit A1.1: warm-start MT3 model server on boot (non-blocking if unavailable)
    try:
        from app.mt3.model_server import Mt3ModelServer

        mt3_server = Mt3ModelServer()
        mt3_loaded = await asyncio.to_thread(mt3_server.warm_start)
        if mt3_loaded:
            logger.info("MT3 model warm-started successfully")
        else:
            load_err = mt3_server.load_error()
            logger.info(
                "MT3 model not loaded at startup%s — will use CRNN fallback",
                f" ({load_err})" if load_err else "",
            )
    except Exception:
        logger.exception("Failed to warm-start MT3 model — will use CRNN fallback")
    yield


app = FastAPI(
    title="Harmoniq API",
    description="Local analysis backend for Harmoniq (in-memory job runner; real pipeline later).",
    version="0.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

def _cors_allow_origins() -> list[str]:
    defaults = [
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:19006",
        "http://127.0.0.1:19006",
    ]
    raw = os.getenv("HARMONIQ_CORS_ORIGINS", "").strip()
    if not raw:
        return defaults
    extra = [o.strip() for o in raw.split(",") if o.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for o in defaults + extra:
        if o not in seen:
            seen.add(o)
            out.append(o)
    return out


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    # Expo / Metro may use any port — without this, OPTIONS preflight returns 400.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Centralized error handler
# ---------------------------------------------------------------------------

class HarmoniqAPIError(Exception):
    """Base for known API errors that map to a specific HTTP status."""
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@app.exception_handler(HarmoniqAPIError)
async def harmoniq_api_error_handler(request: Request, exc: HarmoniqAPIError) -> Response:
    return Response(status_code=exc.status_code, content=json.dumps({"detail": exc.detail}), media_type="application/json")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> Response:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return Response(status_code=500, content=json.dumps({"detail": "Internal server error."}), media_type="application/json")


# ---------------------------------------------------------------------------
# Include feature routers
# ---------------------------------------------------------------------------

app.include_router(analyze_router)
app.include_router(export_router)
app.include_router(discovery_router)
app.include_router(taste_router)
app.include_router(curriculum_router)
app.include_router(mt3_router)
app.include_router(ws_router)


# ---------------------------------------------------------------------------
# Remaining inline routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    """Health check with Redis connectivity."""
    health_status = {"status": "ok"}

    # Check Redis if configured
    try:
        from app.job_store import ping
        redis_ok = ping()
        health_status["redis"] = "ok" if redis_ok else "unreachable"
        if not redis_ok:
            health_status["status"] = "degraded"
    except Exception:
        health_status["redis"] = "unavailable"
        health_status["status"] = "degraded"

    return health_status


# ---------------------------------------------------------------------------
# Metrics (Prometheus)
# ---------------------------------------------------------------------------

@app.get(
    "/metrics",
    tags=["Observability"],
    summary="GET /metrics — Prometheus metrics endpoint",
)
def metrics():
    from app.metrics import metrics_response

    # Update Redis health gauge
    try:
        from app.metrics import redis_healthy as redis_gauge
        from app.job_store import ping
        redis_gauge.set(1 if ping() else 0)
    except Exception:
        logger.debug("redis health gauge update failed", exc_info=True)

    # Update queue / DLQ / GPU gauges (Commit 170)
    try:
        from app.metrics import update_queue_metrics, update_gpu_metrics

        update_queue_metrics()
        update_gpu_metrics()
    except Exception:
        logger.debug("queue/gpu gauge update failed", exc_info=True)

    # Update in-progress gauge from in-memory jobs
    try:
        from app.jobs import jobs as _jobs
        from app.metrics import jobs_in_progress as _jip

        _jip.set(sum(1 for j in _jobs.values() if getattr(j, "status", None) == "processing"))
    except Exception:
        logger.debug("jobs_in_progress gauge update failed", exc_info=True)

    # Include circuit breaker metrics
    body = metrics_response()
    return Response(content=body, media_type="text/plain")


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


@app.get(
    "/lesson-file",
    tags=["Artifacts"],
    summary="Serve a lesson stem or other job-relative audio file",
)
async def lesson_file(
    rel: str = Query(..., description="Path relative to backend root, e.g. data/jobs/…/stems/guitar.wav"),
) -> FileResponse:
    backend_root = _backend_root().resolve()
    rel_norm = rel.replace("\\", "/").lstrip("/")
    if not rel_norm or ".." in Path(rel_norm).parts:
        raise HTTPException(status_code=400, detail="Invalid rel path")
    candidate = (backend_root / rel_norm).resolve()
    if not str(candidate).startswith(str(backend_root)):
        raise HTTPException(status_code=403, detail="Path escapes backend root")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    suffix = candidate.suffix.lower()
    media = "audio/wav" if suffix == ".wav" else "application/octet-stream"
    return FileResponse(candidate, media_type=media, filename=candidate.name)


# ---------------------------------------------------------------------------
# Theory
# ---------------------------------------------------------------------------

@app.post(
    "/theory/annotation",
    response_model=TheoryAnnotationResponse,
    tags=["Theory"],
    summary="POST /theory/annotation — plain-language theory rationale for a chord",
    responses={422: {"description": "Invalid payload"}},
)
async def theory_annotation(req: TheoryAnnotationRequest) -> TheoryAnnotationResponse:
    rationale = generate_theory_annotation(key=req.key, chord=req.chord, chord_function=req.chord_function)
    return TheoryAnnotationResponse(rationale=rationale)


# ---------------------------------------------------------------------------
# Spotify Auth
# ---------------------------------------------------------------------------

@app.get(
    "/auth/spotify",
    tags=["Spotify"],
    summary="GET /auth/spotify — start OAuth (redirect or JSON authorize URL)",
    response_model=None,
)
async def auth_spotify_start(
    client_session: str = Query(..., min_length=1, max_length=256),
    format: str = Query("redirect", description="`redirect` (302 to Spotify) or `json`"),
    platform: str = Query("web", description="`web` or `native` — controls post-login redirect target"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    rp: Literal["native", "web"] = "native" if platform.strip().lower() == "native" else "web"
    try:
        _, authorize_url = spotify_api.begin_authorization(client_session, return_platform=rp)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    fmt = format.strip().lower()
    if fmt == "json":
        return {"authorize_url": authorize_url}
    return RedirectResponse(url=authorize_url, status_code=302)


@app.get(
    "/auth/spotify/callback",
    tags=["Spotify"],
    summary="GET /auth/spotify/callback — Spotify OAuth redirect",
)
async def auth_spotify_callback(request: Request) -> RedirectResponse:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    qp = request.query_params
    err = qp.get("error")
    state = (qp.get("state") or "").strip()
    code = qp.get("code")
    if err:
        popped = spotify_api.pop_pending_for_state(state) if state else None
        if popped:
            cs, rp = popped
            return RedirectResponse(spotify_api.oauth_failure_redirect(rp, cs))
        return RedirectResponse(spotify_api.oauth_failure_redirect("web", ""))
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state.")
    try:
        cs, plat = await spotify_api.exchange_code(str(code), state)
    except ValueError as exc:
        logger.warning("Spotify OAuth exchange failed: %s", exc)
        popped = spotify_api.pop_pending_for_state(state)
        if popped:
            cs2, rp2 = popped
            return RedirectResponse(spotify_api.oauth_failure_redirect(rp2, cs2))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=spotify_api.post_login_redirect(plat, cs))


@app.delete(
    "/auth/spotify",
    tags=["Spotify"],
    summary="DELETE /auth/spotify — revoke server-side Spotify session",
)
async def auth_spotify_disconnect(client_session: str = Query(..., min_length=1, max_length=256)) -> Response:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    spotify_api.disconnect_client(client_session)
    return Response(status_code=204)


@app.get(
    "/spotify/playback",
    response_model=SpotifyPlaybackState,
    tags=["Spotify"],
    summary="GET /spotify/playback — normalized current playback state",
)
async def spotify_playback(client_session: str = Query(..., min_length=1, max_length=256)) -> SpotifyPlaybackState:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    if os.getenv("HARMONIQ_SKIP_SPOTIFY_PLAYBACK", "").strip() == "1":
        raise HTTPException(status_code=503, detail="Spotify playback-follow disabled (HARMONIQ_SKIP_SPOTIFY_PLAYBACK=1).")
    try:
        return await spotify_api.get_playback_state(client_session)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Spotify Search
# ---------------------------------------------------------------------------

@app.get(
    "/spotify/search",
    response_model=SpotifySearchResult,
    tags=["Spotify"],
    summary="Search the Spotify catalog",
)
async def spotify_search(
    client_session: str = Query(..., min_length=1, max_length=256),
    q: str = Query(..., min_length=1, description="Search query"),
    type: str = Query("track,artist,album", description="Comma-separated item types: track,artist,album,playlist,show,episode,audiobook"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0, le=1000),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    try:
        result = await spotify_api.search(client_session, q, type_filter=type, limit=limit, offset=offset)
        return result
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Spotify Recommendations
# ---------------------------------------------------------------------------

@app.get(
    "/spotify/recommendations",
    response_model=SpotifyRecommendationsResult,
    tags=["Spotify"],
    summary="Get track recommendations based on seeds",
)
async def spotify_recommendations(
    client_session: str = Query(..., min_length=1, max_length=256),
    seed_artists: str = Query("", description="Comma-separated seed artist IDs"),
    seed_genres: str = Query("", description="Comma-separated seed genre names"),
    seed_tracks: str = Query("", description="Comma-separated seed track IDs"),
    limit: int = Query(20, ge=1, le=100),
    market: str = Query("", description="Market code (e.g. US)"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    artists = seed_artists.strip() or None
    genres = seed_genres.strip() or None
    tracks = seed_tracks.strip() or None
    if not artists and not genres and not tracks:
        raise HTTPException(status_code=400, detail="At least one of seed_artists, seed_genres, or seed_tracks must be provided.")
    m = market.strip() or None
    try:
        result = await spotify_api.get_recommendations(
            client_session,
            seed_artists=artists,
            seed_genres=genres,
            seed_tracks=tracks,
            limit=limit,
            market=m,
        )
        return result
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get(
    "/spotify/recommendations/available-genre-seeds",
    response_model=SpotifyAvailableGenreSeeds,
    tags=["Spotify"],
    summary="Get available genre seeds for recommendations",
)
async def spotify_available_genre_seeds(
    client_session: str = Query(..., min_length=1, max_length=256),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    try:
        result = await spotify_api.get_available_genre_seeds(client_session)
        return result
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Spotify Playlists
# ---------------------------------------------------------------------------

@app.get(
    "/spotify/playlists",
    response_model=SpotifyPlaylistList,
    tags=["Spotify"],
    summary="Get current user's playlists",
)
async def spotify_playlists(
    client_session: str = Query(..., min_length=1, max_length=256),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    try:
        return await spotify_api.get_current_user_playlists(client_session, limit=limit, offset=offset)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get(
    "/spotify/playlists/{playlist_id}",
    response_model=SpotifyPlaylistDetail,
    tags=["Spotify"],
    summary="Get a playlist by ID",
)
async def spotify_playlist_detail(
    client_session: str = Query(..., min_length=1, max_length=256),
    playlist_id: str = FastPath(..., min_length=1, description="Spotify playlist ID"),
    market: str = Query("", description="Market code (e.g. US)"),
    fields: str = Query("", description="Fields filter (e.g. name,owner,tracks.total)"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    m = market.strip() or None
    f = fields.strip() or None
    try:
        return await spotify_api.get_playlist(client_session, playlist_id, market=m, fields=f)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get(
    "/spotify/playlists/{playlist_id}/items",
    response_model=SpotifyPlaylistItems,
    tags=["Spotify"],
    summary="Get items in a playlist",
)
async def spotify_playlist_items(
    client_session: str = Query(..., min_length=1, max_length=256),
    playlist_id: str = FastPath(..., min_length=1, description="Spotify playlist ID"),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    market: str = Query("", description="Market code (e.g. US)"),
    fields: str = Query("", description="Fields filter"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    m = market.strip() or None
    f = fields.strip() or None
    try:
        return await spotify_api.get_playlist_items(client_session, playlist_id, limit=limit, offset=offset, market=m, fields=f)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Spotify Player Controls
# ---------------------------------------------------------------------------

@app.put(
    "/spotify/player/play",
    status_code=204,
    tags=["Spotify"],
    summary="Start/Resume playback (Premium required)",
)
async def spotify_player_play(
    client_session: str = Query(..., min_length=1, max_length=256),
    device_id: str = Query("", description="Target device ID (optional)"),
    context_uri: str = Query("", description="Context URI (album/artist/playlist)"),
    uris: str = Query("", description="Comma-separated track URIs to play"),
    position_ms: int = Query(0, ge=0, description="Start position in ms"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    did = device_id.strip() or None
    cu = context_uri.strip() or None
    uris_list = [u.strip() for u in uris.split(",") if u.strip()] if uris.strip() else None
    pos = position_ms if position_ms > 0 else None
    try:
        await spotify_api.start_playback(
            client_session,
            device_id=did,
            context_uri=cu,
            uris=uris_list,
            position_ms=pos,
        )
        return Response(status_code=204)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.put(
    "/spotify/player/pause",
    status_code=204,
    tags=["Spotify"],
    summary="Pause playback (Premium required)",
)
async def spotify_player_pause(
    client_session: str = Query(..., min_length=1, max_length=256),
    device_id: str = Query("", description="Target device ID (optional)"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    did = device_id.strip() or None
    try:
        await spotify_api.pause_playback(client_session, device_id=did)
        return Response(status_code=204)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.post(
    "/spotify/player/next",
    status_code=204,
    tags=["Spotify"],
    summary="Skip to next track (Premium required)",
)
async def spotify_player_next(
    client_session: str = Query(..., min_length=1, max_length=256),
    device_id: str = Query("", description="Target device ID (optional)"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    did = device_id.strip() or None
    try:
        await spotify_api.skip_to_next(client_session, device_id=did)
        return Response(status_code=204)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.post(
    "/spotify/player/previous",
    status_code=204,
    tags=["Spotify"],
    summary="Skip to previous track (Premium required)",
)
async def spotify_player_previous(
    client_session: str = Query(..., min_length=1, max_length=256),
    device_id: str = Query("", description="Target device ID (optional)"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    did = device_id.strip() or None
    try:
        await spotify_api.skip_to_previous(client_session, device_id=did)
        return Response(status_code=204)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.put(
    "/spotify/player/seek",
    status_code=204,
    tags=["Spotify"],
    summary="Seek to position in current track (Premium required)",
)
async def spotify_player_seek(
    client_session: str = Query(..., min_length=1, max_length=256),
    position_ms: int = Query(..., ge=0, description="Position in milliseconds"),
    device_id: str = Query("", description="Target device ID (optional)"),
):
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(status_code=503, detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).")
    did = device_id.strip() or None
    try:
        await spotify_api.seek_to_position(client_session, position_ms, device_id=did)
        return Response(status_code=204)
    except spotify_api.SpotifySessionExpired as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

@app.get(
    "/tabs/search",
    response_model=TabSearchResponse,
    tags=["Tabs"],
    summary="Search tab catalog (stub until licensed provider)",
)
async def tabs_search(q: str = Query("", description="Free-text song search")) -> TabSearchResponse:
    return search_tabs(q)


@app.get(
    "/tabs/{hit_id}/gp5",
    tags=["Tabs"],
    summary="Download Guitar Pro file for a catalog hit (not implemented)",
)
async def tabs_gp5_download(hit_id: str) -> None:
    _ = hit_id
    raise HTTPException(status_code=501, detail="GP5 download is not available yet. Configure a licensed tab provider (HARMONIQ_TAB_CATALOG).")


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

@app.post(
    "/score",
    response_model=ScoreResult,
    tags=["Score"],
    summary="POST /score",
)
async def score(payload: ScoreRequest) -> ScoreResult:
    try:
        from app.score import score_recording
        return score_recording(payload)
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Score pipeline dependency missing: {exc.name}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@app.post(
    "/onboarding-placement",
    response_model=OnboardingPlacementResponse,
    tags=["Onboarding"],
    summary="POST /onboarding-placement — placement baseline coach paragraph",
)
async def onboarding_placement(payload: OnboardingPlacementRequest) -> OnboardingPlacementResponse:
    paragraph = generate_onboarding_placement_summary(
        pitch_avg=payload.pitch_avg, phrasing_avg=payload.phrasing_avg,
        timing_avg=payload.timing_avg, bend_error_cents_avg=payload.bend_error_cents_avg,
    )
    note: str | None = None
    if payload.placement_confidence == "low":
        note = "Some placement samples had lower reliability, so this baseline will tighten after a few normal sessions."
    elif payload.reliability_flags:
        note = "Baseline includes signal-quality guards and may be refined as cleaner phrase captures arrive."
    return OnboardingPlacementResponse(coach_paragraph=paragraph, confidence_note=note)


# ---------------------------------------------------------------------------
# Coach / Quick feedback
# ---------------------------------------------------------------------------

@app.post(
    "/quick-feedback",
    response_model=QuickFeedbackResponse,
    tags=["Coach"],
    summary="POST /quick-feedback — Play step per-beat accuracy coach line",
)
async def quick_feedback(payload: QuickFeedbackRequest) -> QuickFeedbackResponse:
    message = generate_quick_feedback([str(x) for x in payload.accuracy_pattern])
    return QuickFeedbackResponse(message=message)


# ---------------------------------------------------------------------------
# Jam
# ---------------------------------------------------------------------------

@app.post(
    "/jam/backing",
    response_model=JamBackingResponse,
    tags=["Jam"],
    summary="POST /jam/backing — instrumental practice bed (MRT2 + bundled fallback)",
)
async def jam_backing(payload: JamBackingRequest) -> JamBackingResponse:
    prompt = build_mrt2_prompt(
        style_hint=payload.style_hint or "",
        musical_key=payload.musical_key.strip(),
        bpm=payload.bpm,
    )
    raw: bytes | None = None
    duration_ms: int | None = None
    prompt_used = prompt
    generator = Mrt2BackingGenerator()
    result = await asyncio.to_thread(generator.generate, prompt=prompt)
    if result is not None:
        raw, duration_ms = result
        logger.info("jam_backing generated with MRT2")
    if raw is None:
        logger.info("jam_backing MRT2 unavailable; using bundled fallback")
        fallback = select_bundled_track(musical_key=payload.musical_key.strip(), bpm=payload.bpm, style_hint=payload.style_hint)
        raw, duration_ms = load_bundled_track_wav(fallback)
        prompt_used = f"{prompt} [fallback_track={fallback.filename}]"
    b64 = base64.b64encode(raw).decode("ascii")
    return JamBackingResponse(audio_base64=b64, mime_type="audio/wav", format="wav", prompt_used=prompt_used, duration_ms=duration_ms)


@app.post(
    "/jam-score",
    response_model=JamScoreResult,
    tags=["Jam"],
    summary="POST /jam-score — jam session summary (stub → incremental)",
)
async def jam_score(payload: JamScoreRequest) -> JamScoreResult:
    def _normalize_pitch_class_map(raw: dict[str, float]) -> dict[str, float]:
        clean: dict[str, float] = {}
        for k, v in (raw or {}).items():
            if not isinstance(k, str) or not PITCH_CLASS_KEY_RE.match(k):
                raise HTTPException(status_code=422, detail=f"Invalid pitch-class key: {k!r}")
            n = float(v)
            if not math.isfinite(n) or n < 0:
                raise HTTPException(status_code=422, detail=f"Invalid pitch-class value for {k!r}")
            clean[k] = n
        if not clean:
            return {}
        total = sum(clean.values())
        if total <= 0:
            return {}
        return {k: (val / total) for k, val in clean.items()}

    def _normalize_generic_weight_map(raw: dict[str, float]) -> dict[str, float]:
        clean: dict[str, float] = {}
        for k, v in (raw or {}).items():
            if not isinstance(k, str) or not GENERIC_MAP_KEY_RE.match(k):
                raise HTTPException(status_code=422, detail=f"Invalid position-map key: {k!r}")
            n = float(v)
            if not math.isfinite(n) or n < 0:
                raise HTTPException(status_code=422, detail=f"Invalid position-map value for {k!r}")
            clean[k] = n
        if not clean:
            return {}
        total = sum(clean.values())
        if total <= 0:
            return {}
        return {k: (val / total) for k, val in clean.items()}

    pitch_raw = payload.pitch_class_weight_map or payload.scale_position_map or {}
    pitch_map = _normalize_pitch_class_map(pitch_raw)
    position_map = _normalize_generic_weight_map(payload.position_weight_map or {})
    coach = generate_jam_coach_summary(
        duration_seconds=int(payload.duration_seconds),
        inferred_scale_label=payload.inferred_scale_label,
        pitch_class_weight_map=pitch_map,
    )
    focus_key: str | None = None
    focus_weight: float | None = None
    reliability_tags: list[str] = []
    if int(payload.duration_seconds) >= 10 and pitch_map:
        top = max(pitch_map.items(), key=lambda kv: kv[1])
        focus_key = top[0]
        focus_weight = float(top[1])
    if int(payload.duration_seconds) < 10:
        reliability_tags.append("signal_short_window")
    if len(pitch_map) < 3 and int(payload.duration_seconds) >= 10:
        reliability_tags.append("map_sparse")
    if payload.inference_confidence == "high" and focus_weight is not None and focus_weight >= 0.34:
        reliability_tags.append("high_confidence_scale_match")
    signal_quality = clamp01((len(pitch_map) / 6.0) + (0.25 if int(payload.duration_seconds) >= 10 else 0.0))
    if signal_quality <= RELIABILITY_BANDS.low_max:
        confidence = "low"
    elif signal_quality >= RELIABILITY_BANDS.medium_max and "high_confidence_scale_match" in reliability_tags:
        confidence = "high"
    else:
        confidence = "medium"
    return JamScoreResult(
        coach_summary=coach,
        scale_position_map=pitch_map, pitch_class_weight_map=pitch_map, position_weight_map=position_map,
        inferred_scale_label=payload.inferred_scale_label,
        inference_confidence=payload.inference_confidence,
        focus_pitch_class_key=focus_key, focus_pitch_class_weight=focus_weight,
        reliability_tags=reliability_tags,
        reliability={
            "score_contract_version": SCORE_CONTRACT_VERSION,
            "confidence": confidence,
            "signal_quality": round(signal_quality, 3),
            "reliability_flags": reliability_tags,
        },
    )


# ---------------------------------------------------------------------------
# Commit 111: Jam Mode Summary Agent — Claude-powered post-jam analysis
# ---------------------------------------------------------------------------

from app.jam_scoring import compute_jam_grade, fallback_phrase_suggestion
from app.jam_vocabulary import detect_patterns, extract_bundle_metrics
from app.schemas import (
    JamPhraseFeedback,
    JamSummaryBundle,
    JamSummaryRequest,
    JamSummaryResponse,
)
from app.coach import (
    JAM_SUMMARY_PERSONAS,
    generate_jam_summary_with_claude,
    generate_jam_summary_fallback,
)


def _resolve_persona(player_level: str, explicit_persona: str | None) -> str:
    """Resolve coaching persona from player level or explicit override."""
    if explicit_persona and explicit_persona in JAM_SUMMARY_PERSONAS:
        return explicit_persona
    level_map = {
        "beginner": "learner",
        "intermediate": "intermediate",
        "advanced": "transcriber",
    }
    return level_map.get(player_level, "intermediate")


@app.post(
    "/jam/summary",
    response_model=JamSummaryResponse,
    tags=["Jam"],
    summary="POST /jam/summary — Claude-powered post-jam analysis with vocabulary mapping",
)
async def jam_summary(payload: JamSummaryRequest) -> JamSummaryResponse:
    # Normalize pitch class map
    pitch_map: dict[str, float] = {}
    for k, v in (payload.pitch_class_weight_map or {}).items():
        if isinstance(k, str) and isinstance(v, (int, float)) and v >= 0:
            pitch_map[k] = float(v)
    total = sum(pitch_map.values())
    if total > 0:
        pitch_map = {k: v / total for k, v in pitch_map.items()}

    # Resolve persona
    persona = _resolve_persona(payload.player_level, payload.persona)

    # Extract deterministic metrics from phrases
    metrics = extract_bundle_metrics(
        phrases=payload.phrases,
        pitch_class_weight_map=pitch_map,
        duration_seconds=payload.duration_seconds,
    )

    # Detect vocabulary patterns
    patterns = detect_patterns(payload.phrases)

    # Deterministic grade — computed before the LLM and never overridden by it.
    grade_result = compute_jam_grade(payload.phrases)
    weak_order = sorted(
        range(len(payload.phrases)),
        key=lambda index: (grade_result.phrase_scores[index].score, index),
    )[:5]

    # Build pattern details for Claude prompt
    pattern_details = ""
    if patterns:
        lines = []
        for p in patterns[:5]:
            lines.append(f"  - {p.pattern_type}: {', '.join(p.pitch_classes)} (×{p.occurrence_count}, {p.confidence:.0%} confidence)")
        pattern_details = "\n".join(lines)

    phrase_lines = []
    for index in weak_order:
        phrase = payload.phrases[index]
        intonation = (
            f"{phrase.intonation_cents:.1f} cents"
            if phrase.intonation_cents is not None
            else "unknown"
        )
        phrase_lines.append(
            f"  - index={index} | duration={phrase.duration_ms:.0f}ms | "
            f"nps={phrase.notes_per_second:.2f} | notes={phrase.note_count} | "
            f"variety={phrase.unique_pitch_classes} | span={phrase.midi_span} | "
            f"contour={phrase.contour} | timing={phrase.beat_offset_mean:.0f}ms "
            f"(std {phrase.beat_offset_std:.0f}ms) | intonation={intonation}"
        )
    phrase_table = "\n".join(phrase_lines) if phrase_lines else "none"

    # Try Claude first, fall back to deterministic summary
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    claude_result = None
    if api_key:
        try:
            claude_result = await asyncio.to_thread(
                generate_jam_summary_with_claude,
                api_key=api_key,
                duration_seconds=payload.duration_seconds,
                inferred_scale_label=payload.inferred_scale_label,
                inference_confidence=payload.inference_confidence,
                track_label=payload.track_label,
                track_key=payload.track_key,
                track_bpm=payload.track_bpm,
                phrase_count=metrics["phrase_count"],
                avg_notes_per_second=metrics["avg_notes_per_second"],
                dominant_contour=metrics["dominant_contour"],
                vocabulary_diversity=metrics["vocabulary_diversity"],
                pitch_class_weight_map=pitch_map,
                vocabulary_pattern_count=len(patterns),
                vocabulary_pattern_details=pattern_details,
                phrase_table=phrase_table,
                player_level=payload.player_level,
                previous_jam_count=payload.previous_jam_count,
                weak_areas=payload.weak_areas,
                persona=persona,
            )
        except Exception:
            logger.exception("Claude jam summary call failed")
            claude_result = None

    # Fallback to deterministic summary
    if claude_result is None:
        claude_result = generate_jam_summary_fallback(
            duration_seconds=payload.duration_seconds,
            inferred_scale_label=payload.inferred_scale_label,
            pitch_class_weight_map=pitch_map,
            phrase_count=metrics["phrase_count"],
            vocabulary_diversity=metrics["vocabulary_diversity"],
            player_level=payload.player_level,
        )

    # Merge LLM suggestions with deterministic fallbacks (weakest first, max 5).
    claude_suggestions: dict[int, str] = {}
    for item in claude_result.get("phrase_feedback", []) if isinstance(claude_result, dict) else []:
        if not isinstance(item, dict):
            continue
        phrase_index = item.get("phrase_index")
        suggestion = item.get("suggestion")
        if isinstance(phrase_index, int) and isinstance(suggestion, str) and suggestion.strip():
            claude_suggestions[phrase_index] = suggestion.strip()

    phrase_feedback: list[JamPhraseFeedback] = []
    for index in weak_order:
        phrase = payload.phrases[index]
        suggestion = claude_suggestions.get(index) or fallback_phrase_suggestion(phrase, index)
        phrase_feedback.append(
            JamPhraseFeedback(
                phrase_index=index,
                chord=payload.inferred_scale_label,
                clarity=round(clamp01(grade_result.phrase_scores[index].score / 100.0), 3),
                intonation_cents=phrase.intonation_cents,
                timing_ms=phrase.beat_offset_mean,
                transition_from=phrase.transition_from,
                transition_gap_ms=phrase.transition_gap_ms,
                suggestion=suggestion,
            )
        )

    coach_strengths = [
        item.strip()
        for item in claude_result.get("coach_strengths", [])
        if isinstance(item, str) and item.strip()
    ][:3]
    coach_focus_areas = [
        item.strip()
        for item in claude_result.get("coach_focus_areas", [])
        if isinstance(item, str) and item.strip()
    ][:3]

    # Build response bundle
    bundle = JamSummaryBundle(
        chord=payload.inferred_scale_label,
        clarity=metrics["clarity"],
        intonation_cents=metrics["intonation_cents"],
        timing_ms=metrics["timing_ms"],
        transition_from=payload.phrases[0].transition_from if payload.phrases else None,
        transition_gap_ms=payload.phrases[0].transition_gap_ms if payload.phrases else 0.0,
        grade=grade_result.grade,
        grade_score=grade_result.grade_score,
        grade_breakdown=grade_result.grade_breakdown,
        phrase_feedback=phrase_feedback,
        weakest_phrase_index=grade_result.weakest_phrase_index,
        phrase_count=metrics["phrase_count"],
        total_notes=metrics["total_notes"],
        avg_notes_per_second=metrics["avg_notes_per_second"],
        dominant_contour=metrics["dominant_contour"],
        pitch_class_distribution=pitch_map,
        vocabulary_patterns=patterns,
        vocabulary_diversity=metrics["vocabulary_diversity"],
        coach_summary=str(claude_result.get("coach_summary", "")).strip(),
        coach_strengths=coach_strengths,
        coach_focus_areas=coach_focus_areas,
        coach_next_step=str(claude_result.get("coach_next_step", "")).strip(),
        persona=persona,
        duration_seconds=payload.duration_seconds,
        inferred_scale_label=payload.inferred_scale_label,
        inference_confidence=payload.inference_confidence,
    )

    return JamSummaryResponse(
        bundle=bundle,
        coach_summary=bundle.coach_summary,
    )


# ---------------------------------------------------------------------------
# Session / Orient clip
# ---------------------------------------------------------------------------

@app.post(
    "/session/orient-clip",
    response_model=OrientClipResponse,
    tags=["Session"],
    summary="POST /session/orient-clip — generate orient clip for Orient phase",
)
async def orient_clip(req: OrientClipRequest):
    clip_result = generate_orient_clip(
        style_label=req.style_label, technique=req.technique,
        key=req.key, bpm=req.bpm, job_id=req.job_id,
    )
    return OrientClipResponse(
        wav_path=clip_result["wav_path"], annotation=clip_result["annotation"],
        duration=clip_result["duration"],
        used_placeholder=clip_result["used_placeholder"],
        placeholder_reason=clip_result["placeholder_reason"],
    )
