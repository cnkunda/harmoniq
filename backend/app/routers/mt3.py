"""MT3 inference router — single and batch inference endpoints.

Commit A1.1: Exposes the MT3 model server via FastAPI so callers can
run inference on uploaded audio files and receive structured event streams.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.mt3.model_server import Mt3ModelServer, mt3_infer
from app.mt3.schemas import Mt3EventStream

logger = logging.getLogger("harmoniq.routers.mt3")

router = APIRouter(prefix="/mt3", tags=["mt3"])


@router.post(
    "/infer",
    response_model=Mt3EventStream,
    summary="Run MT3 inference on a single WAV file",
    description=(
        "Accepts a path to a 44.1kHz mono WAV file (guitar stem), resamples to 16kHz, "
        "runs the MT3 T5-small model, and returns a structured event stream of all "
        "detected notes across all instruments. Returns 503 if MT3 is unavailable."
    ),
)
async def infer_single(wav_path: str) -> Mt3EventStream:
    """Run MT3 inference on a single WAV file.

    Args:
        wav_path: Absolute or backend-relative path to a WAV file.

    Returns:
        Mt3EventStream with all detected note events, or 503 if MT3 is unavailable.
    """
    path = Path(wav_path)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"WAV file not found: {wav_path}",
        )

    server = Mt3ModelServer()
    if not server.is_available():
        raise HTTPException(
            status_code=503,
            detail="MT3 server unavailable (dependencies not installed or model not loaded). "
            "Install with: pip install -e '.[mt3]'",
        )

    result = mt3_infer(str(path))
    if not result.events and result.inference_time_ms == 0 and result.audio_duration_s > 0:
        logger.warning("MT3 inference produced no events for %s", wav_path)
    return result


@router.post(
    "/infer/batch",
    response_model=list[Mt3EventStream],
    summary="Run MT3 inference on multiple WAV files",
    description=(
        "Accepts a list of WAV file paths. Runs inference on each file sequentially "
        "and returns a list of Mt3EventStream objects in corresponding order. "
        "Failed or missing files return an empty stream (audio_duration_s=0.0)."
    ),
)
async def infer_batch(wav_paths: list[str]) -> list[Mt3EventStream]:
    """Run MT3 inference on multiple WAV files (batch mode).

    Args:
        wav_paths: List of paths to 44.1kHz mono WAV files.

    Returns:
        List of Mt3EventStream objects, one per input path. Missing files
        return an empty stream rather than failing the entire batch.
    """
    results: list[Mt3EventStream] = []
    for wav_path in wav_paths:
        path = Path(wav_path)
        if not path.is_file():
            logger.warning("Batch MT3: file not found, returning empty stream: %s", wav_path)
            results.append(Mt3EventStream(audio_duration_s=0.0))
            continue
        results.append(mt3_infer(str(path)))
    return results


@router.get(
    "/status",
    response_model=dict,
    summary="Check MT3 server availability",
    description="Returns whether the MT3 model is loaded and ready for inference.",
)
async def mt3_status() -> dict:
    """Check if the MT3 model server is available."""
    server = Mt3ModelServer()
    available = server.is_available()
    return {
        "available": available,
        "model": "mt3-t5-small",
        "cache_dir": str(
            Path(__file__).resolve().parent.parent.parent / "data" / "models" / "mt3"
        ),
    }
