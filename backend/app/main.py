"""Harmoniq API entrypoint — health, CORS, async analyze job polling (PRIORITIES §4)."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load `backend/.env` so SPOTIFY_CLIENT_ID and other local secrets apply when using `uvicorn`
# (shell env still wins if already set).
_backend_root = Path(__file__).resolve().parents[1]
load_dotenv(_backend_root / ".env")

import base64
import binascii
import json
import logging
import inspect
import math
import os
import re
from pathlib import Path
import uuid
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.exporter import (
    ExportDisabledError,
    ExportUnsupportedError,
    export_gp5_base64,
)
from app.schemas import (
    AnalyzeJobCreated,
    CoachHydrationStatus,
    CurriculumSuggestRequest,
    CurriculumSuggestResponse,
    CurriculumSuggestionItem,
    ExportRequest,
    JamBackingRequest,
    JamBackingResponse,
    JamScoreRequest,
    JamScoreResult,
    JobStatus,
    LessonJSON,
    OnboardingPlacementRequest,
    OnboardingPlacementResponse,
    PlayerProfile,
    PracticePlan,
    PracticePlanRequest,
    QuickFeedbackRequest,
    QuickFeedbackResponse,
    ScoreRequest,
    ScoreResult,
    SpotifyTasteProfile,
    TasteDeriveRequest,
    TasteProfile,
)
from app import spotify as spotify_api
from app.curriculum import suggest_next_session
from app.sequencer import generate_practice_plan
from app.taste import derive_taste_profile
from app.ingest import get_job_dir
from app.jobs import ANALYSIS_FAILED_USER_MESSAGE, enqueue_analyze_job, get_coach_hydration, jobs
from app.coach import (
    generate_jam_coach_summary,
    generate_onboarding_placement_summary,
    generate_quick_feedback,
)
from app.scoring_constants import RELIABILITY_BANDS, SCORE_CONTRACT_VERSION, clamp01
from app.jam_backing import (
    LyriaProviderError,
    build_instrumental_prompt,
    call_gemini_lyria_instrumental,
    gemini_lyria_config,
    load_bundled_track_wav,
    select_bundled_track,
)
from app.tab_catalog.provider import TabSearchResponse, search_tabs

logger = logging.getLogger("harmoniq.api")
logger.setLevel(logging.INFO)

PITCH_CLASS_KEY_RE = re.compile(r"^pc_(C|C#|D|D#|E|F|F#|G|G#|A|A#|B)$")
GENERIC_MAP_KEY_RE = re.compile(r"^[A-Za-z0-9_:#\-/+(). ]{1,64}$")


def _parse_player_profile_field(raw: object) -> PlayerProfile | None:
    """Accept JSON object or JSON string; invalid payloads are dropped (safe generic coaching)."""
    if raw is None:
        return None
    data: object
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            logger.warning("player_profile JSON decode failed; ignoring")
            return None
    elif isinstance(raw, dict):
        data = raw
    else:
        logger.warning("player_profile unsupported type=%s; ignoring", type(raw).__name__)
        return None
    if not isinstance(data, dict):
        return None
    try:
        return PlayerProfile.model_validate(data)
    except Exception:
        logger.warning("player_profile validation failed; ignoring")
        return None

app = FastAPI(
    title="Harmoniq API",
    description="Local analysis backend for Harmoniq (in-memory job runner; real pipeline later).",
    version="0.1.0",
)


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
    # Expo / Metro may use any port (e.g. `expo start --port 8082`); without this, OPTIONS preflight
    # returns 400 and the browser shows a network-style failure ("need a connection…").
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


@app.get(
    "/lesson-file",
    tags=["Artifacts"],
    summary="Serve a lesson stem or other job-relative audio file (PRIORITIES §20)",
)
async def lesson_file(
    rel: str = Query(..., description="Path relative to backend root, e.g. data/jobs/…/stems/guitar.wav"),
) -> FileResponse:
    """Return WAV/audio from disk; used by the app to decode stems referenced in LessonJSON.stems."""
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


@app.post(
    "/export",
    tags=["Export"],
    summary="POST /export — GP5 to MIDI or MusicXML (PRIORITIES §58)",
    responses={
        422: {"description": "Invalid payload, bad base64, or format not available in this build"},
        503: {"description": "Export disabled (HARMONIQ_SKIP_EXPORT=1)"},
    },
)
async def export_tab(req: ExportRequest) -> Response:
    """Convert base64-encoded GP5 to a downloadable artifact."""
    try:
        data, mime, ext, stem = export_gp5_base64(
            req.gp5_base64,
            req.export_format,
            title_hint=req.title,
        )
    except ExportDisabledError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ExportUnsupportedError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except binascii.Error:
        raise HTTPException(status_code=422, detail="Invalid GP5 base64.") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    filename = f"{stem}{ext}"
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # per README: max 50MB


class UploadTooLargeError(ValueError):
    pass


async def _save_uploadfile_limited(
    upload: UploadFile,
    dest_path: Path,
    *,
    max_bytes: int,
    chunk_bytes: int = 1024 * 1024,
) -> None:
    """Stream UploadFile to disk while enforcing a hard byte limit."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with dest_path.open("wb") as f:
        while True:
            chunk = await upload.read(chunk_bytes)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise UploadTooLargeError(f"Upload exceeds max_bytes={max_bytes}")
            f.write(chunk)


@app.post(
    "/analyze",
    response_model=AnalyzeJobCreated,
    tags=["Analyze"],
    summary="POST /analyze (async — returns job_id immediately)",
)


async def analyze(request: Request) -> AnalyzeJobCreated:
    """POST /analyze: JSON youtube_url or multipart upload."""
    job_id = str(uuid.uuid4())

    youtube_url: str | None = None
    upload_path: str | None = None
    player_profile: PlayerProfile | None = None

    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            youtube_url = form.get("youtube_url") or form.get("url")  # accept both keys
            player_profile = _parse_player_profile_field(form.get("player_profile"))

            if upload is not None:
                suffix = Path(upload.filename or "").suffix or ".audio"
                job_dir = get_job_dir(job_id)
                dest = job_dir / f"input{suffix}"
                if isinstance(upload, UploadFile):
                    await _save_uploadfile_limited(
                        upload,
                        dest,
                        max_bytes=MAX_UPLOAD_BYTES,
                    )
                elif isinstance(upload, (bytes, bytearray)):
                    if len(upload) > MAX_UPLOAD_BYTES:
                        raise UploadTooLargeError(f"Upload exceeds max_bytes={MAX_UPLOAD_BYTES}")
                    dest.write_bytes(bytes(upload))
                elif hasattr(upload, "read"):
                    raw = upload.read()
                    if inspect.isawaitable(raw):
                        raw = await raw
                    if isinstance(raw, str):
                        raw = raw.encode()
                    if not isinstance(raw, (bytes, bytearray)):
                        raise TypeError("Multipart file must be bytes-like")
                    if len(raw) > MAX_UPLOAD_BYTES:
                        raise UploadTooLargeError(f"Upload exceeds max_bytes={MAX_UPLOAD_BYTES}")
                    dest.write_bytes(bytes(raw))
                else:
                    raise TypeError("Expected multipart 'file' to be UploadFile or bytes-like")
                upload_path = str(dest)

        else:
            body = await request.json()
            if isinstance(body, dict):
                youtube_url = body.get("url") or body.get("youtube_url")
                player_profile = _parse_player_profile_field(body.get("player_profile"))

    except UploadTooLargeError:
        logger.warning("POST /analyze upload too large job_id=%s", job_id)
        jobs[job_id] = JobStatus(status="failed", result=None, error=ANALYSIS_FAILED_USER_MESSAGE)
        return AnalyzeJobCreated(job_id=job_id)

    except Exception:
        logger.exception("POST /analyze failed to parse input job_id=%s", job_id)
        jobs[job_id] = JobStatus(status="failed", result=None, error=ANALYSIS_FAILED_USER_MESSAGE)
        return AnalyzeJobCreated(job_id=job_id)

    logger.info(
        "POST /analyze created job_id=%s status=processing youtube_url=%r upload_path=%r",
        job_id,
        youtube_url,
        upload_path,
    )

    enqueue_analyze_job(
        job_id=job_id,
        youtube_url=youtube_url,
        upload_path=upload_path,
        player_profile=player_profile,
    )
    return AnalyzeJobCreated(job_id=job_id)


@app.get(
    "/analyze/{job_id}",
    response_model=JobStatus,
    tags=["Analyze"],
    summary="GET /analyze/{job_id}",
)
async def analyze_status(job_id: str) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        logger.warning("GET /analyze/%s — unknown job_id (404)", job_id)
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    logger.info("GET /analyze/%s status=%s", job_id, job.status)
    return job


@app.get(
    "/analyze/{job_id}/coach",
    response_model=CoachHydrationStatus,
    tags=["Analyze"],
    summary="GET /analyze/{job_id}/coach — coach hydration status (commit 66)",
)
async def analyze_coach_status(job_id: str) -> CoachHydrationStatus:
    job = jobs.get(job_id)
    if job is None:
        logger.warning("GET /analyze/%s/coach — unknown job_id (404)", job_id)
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    status = get_coach_hydration(job_id)
    if status is None:
        return CoachHydrationStatus(status="pending", sections=[], fallback_reason=None)
    return status


@app.post(
    "/curriculum/suggest",
    response_model=CurriculumSuggestResponse,
    tags=["Curriculum"],
    summary="POST /curriculum/suggest — ranked next-session suggestions (commit 65)",
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
    return CurriculumSuggestResponse(
        ranked=[
            CurriculumSuggestionItem(
                job_id=item.job_id,
                reason_label=item.reason_label,
                technique_focus=item.technique_focus,
            )
            for item in ranked
        ]
    )


@app.post(
    "/practice/plan",
    response_model=PracticePlan,
    tags=["Practice"],
    summary="POST /practice/plan — ordered drill queue from profile + library (commit 70)",
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
    )


@app.post(
    "/taste/derive",
    response_model=TasteProfile,
    tags=["Taste"],
    summary="POST /taste/derive — deterministic TasteProfile from Spotify or quiz (commit 68)",
)
async def taste_derive(payload: TasteDeriveRequest) -> TasteProfile:
    if os.getenv("HARMONIQ_SKIP_TASTE_DERIVE", "").strip() == "1":
        raise HTTPException(
            status_code=503,
            detail="Taste derivation disabled (HARMONIQ_SKIP_TASTE_DERIVE=1).",
        )
    return derive_taste_profile(
        spotify_profile=payload.spotify_profile,
        quiz_answers=payload.quiz_answers,
        taste_source=payload.taste_source,
    )


@app.get(
    "/auth/spotify",
    response_model=None,
    tags=["Spotify"],
    summary="GET /auth/spotify — start OAuth (redirect or JSON authorize URL) (commit 67)",
)
async def auth_spotify_start(
    client_session: str = Query(..., min_length=1, max_length=256),
    format: str = Query("redirect", description="`redirect` (302 to Spotify) or `json`"),
    platform: str = Query("web", description="`web` or `native` — controls post-login redirect target"),
) -> RedirectResponse | dict[str, str]:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(
            status_code=503,
            detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).",
        )
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
    summary="GET /auth/spotify/callback — Spotify OAuth redirect (commit 67)",
)
async def auth_spotify_callback(request: Request) -> RedirectResponse:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(
            status_code=503,
            detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).",
        )
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


@app.get(
    "/taste/spotify",
    response_model=SpotifyTasteProfile,
    tags=["Spotify"],
    summary="GET /taste/spotify — aggregated taste (commit 67)",
)
async def taste_spotify(
    client_session: str = Query(..., min_length=1, max_length=256),
) -> SpotifyTasteProfile:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(
            status_code=503,
            detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).",
        )
    try:
        return await spotify_api.build_taste_profile(client_session)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.delete(
    "/auth/spotify",
    tags=["Spotify"],
    summary="DELETE /auth/spotify — revoke server-side Spotify session (commit 67)",
)
async def auth_spotify_disconnect(
    client_session: str = Query(..., min_length=1, max_length=256),
) -> Response:
    if spotify_api.spotify_feature_disabled():
        raise HTTPException(
            status_code=503,
            detail="Spotify integration disabled (HARMONIQ_SKIP_SPOTIFY=1).",
        )
    spotify_api.disconnect_client(client_session)
    return Response(status_code=204)


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
    raise HTTPException(
        status_code=501,
        detail="GP5 download is not available yet. Configure a licensed tab provider (HARMONIQ_TAB_CATALOG).",
    )


@app.post(
    "/score",
    response_model=ScoreResult,
    tags=["Score"],
    summary="POST /score",
)
async def score(payload: ScoreRequest) -> ScoreResult:
    try:
        # Lazy import keeps /jam-score and lightweight tests runnable without full DSP stack.
        from app.score import score_recording

        return score_recording(payload)
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Score pipeline dependency missing: {exc.name}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/onboarding-placement",
    response_model=OnboardingPlacementResponse,
    tags=["Onboarding"],
    summary="POST /onboarding-placement — placement baseline coach paragraph",
)
async def onboarding_placement(payload: OnboardingPlacementRequest) -> OnboardingPlacementResponse:
    paragraph = generate_onboarding_placement_summary(
        pitch_avg=payload.pitch_avg,
        phrasing_avg=payload.phrasing_avg,
        timing_avg=payload.timing_avg,
        bend_error_cents_avg=payload.bend_error_cents_avg,
    )
    note: str | None = None
    if payload.placement_confidence == "low":
        note = "Some placement samples had lower reliability, so this baseline will tighten after a few normal sessions."
    elif payload.reliability_flags:
        note = "Baseline includes signal-quality guards and may be refined as cleaner phrase captures arrive."
    return OnboardingPlacementResponse(coach_paragraph=paragraph, confidence_note=note)


@app.post(
    "/quick-feedback",
    response_model=QuickFeedbackResponse,
    tags=["Coach"],
    summary="POST /quick-feedback — Play step per-beat accuracy coach line",
)
async def quick_feedback(payload: QuickFeedbackRequest) -> QuickFeedbackResponse:
    message = generate_quick_feedback([str(x) for x in payload.accuracy_pattern])
    return QuickFeedbackResponse(message=message)


@app.post(
    "/jam/backing",
    response_model=JamBackingResponse,
    tags=["Jam"],
    summary="POST /jam/backing — instrumental practice bed (Gemini Lyria + local fallback)",
)
async def jam_backing(payload: JamBackingRequest) -> JamBackingResponse:
    api_key, base_url, default_model = gemini_lyria_config()
    model = (payload.model or default_model).strip() or default_model
    prompt = build_instrumental_prompt(
        musical_key=payload.musical_key.strip(),
        bpm=payload.bpm,
        weak_areas=[str(x).strip() for x in payload.weak_areas if str(x).strip()],
        style_hint=payload.style_hint,
    )

    raw: bytes | None = None
    duration_ms: int | None = None
    prompt_used = prompt
    if api_key:
        try:
            raw, duration_ms = await call_gemini_lyria_instrumental(
                prompt=prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
        except LyriaProviderError as exc:
            logger.warning("jam_backing lyria provider error code=%s msg=%s", exc.code, exc)
        except httpx.HTTPError as exc:
            logger.warning("jam_backing lyria http error: %s", exc.__class__.__name__)
    else:
        logger.info("jam_backing no GEMINI_API_KEY; using bundled fallback")

    if raw is None:
        fallback = select_bundled_track(
            musical_key=payload.musical_key.strip(),
            bpm=payload.bpm,
            style_hint=payload.style_hint,
        )
        raw, duration_ms = load_bundled_track_wav(fallback)
        prompt_used = f"{prompt} [fallback_track={fallback.filename}]"

    b64 = base64.b64encode(raw).decode("ascii")
    return JamBackingResponse(
        audio_base64=b64,
        mime_type="audio/wav",
        format="wav",
        prompt_used=prompt_used,
        duration_ms=duration_ms,
    )


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
        scale_position_map=pitch_map,
        pitch_class_weight_map=pitch_map,
        position_weight_map=position_map,
        inferred_scale_label=payload.inferred_scale_label,
        inference_confidence=payload.inference_confidence,
        focus_pitch_class_key=focus_key,
        focus_pitch_class_weight=focus_weight,
        reliability_tags=reliability_tags,
        reliability={
            "score_contract_version": SCORE_CONTRACT_VERSION,
            "confidence": confidence,
            "signal_quality": round(signal_quality, 3),
            "reliability_flags": reliability_tags,
        },
    )
