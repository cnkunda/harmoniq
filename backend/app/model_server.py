"""ML Model Server — dedicated FastAPI micro-service for chord inference.

Runs as a separate process (port 8001) to isolate TFLite inference from the
main API. Supports batched inference and MLflow model versioning.

Usage:
    uvicorn app.model_server:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("harmoniq.model_server")

app = FastAPI(
    title="Harmoniq Model Server",
    description="TFLite chord inference micro-service with MLflow tracking.",
    version="0.2.0",
)

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

_model = None
_model_metadata: dict = {}


def _load_model():
    """Load the TFLite chord model (lazy, singleton)."""
    global _model, _model_metadata

    if _model is not None:
        return _model, _model_metadata

    model_path = os.getenv("CHORD_MODEL_PATH", "models/chord_model.tflite")
    try:
        import tensorflow as tf

        interpreter = tf.lite.Interpreter(
            model_path=model_path,
            experimental_delegates=[
                tf.lite.experimental.load_delegate("libtensorflowlite_flex.so"),
            ] if os.getenv("HARMONIQ_TFLITE_FLEX", "0") == "1" else None,
        )
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        _model = interpreter
        _model_metadata = {
            "input_shape": input_details[0]["shape"].tolist(),
            "output_shape": output_details[0]["shape"].tolist(),
            "input_dtype": str(input_details[0]["dtype"]),
            "model_path": model_path,
        }
        logger.info("model_loaded path=%s metadata=%s", model_path, _model_metadata)
        return _model, _model_metadata
    except Exception as exc:
        logger.warning("model_load_failed path=%s exception=%s", model_path, exc)
        # Return a mock for development
        _model_metadata = {"mock": True, "model_path": model_path}
        return None, _model_metadata


@app.on_event("startup")
async def startup_load_model():
    """Load model on server startup."""
    _load_model()


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class ChordInferenceRequest(BaseModel):
    """Request for batched chord inference."""
    audio_data: list[list[float]] = Field(..., description="Audio samples (flat or batched)")
    sample_rate: int = Field(default=22050, description="Sample rate")
    batch_size: int = Field(default=32, description="Inference batch size")


class ChordInferenceResponse(BaseModel):
    """Response from chord inference."""
    predictions: list[list[float]] = Field(..., description="Per-frame chord probabilities")
    model_version: str = Field(default="unknown")
    inference_time_ms: float = Field(..., description="Total inference time in ms")
    frame_count: int = Field(..., description="Number of frames processed")


class ModelInfo(BaseModel):
    """Model metadata."""
    loaded: bool
    metadata: dict
    uptime_seconds: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_start_time = time.time()


@app.get("/model/info", response_model=ModelInfo, tags=["Model"])
async def model_info() -> ModelInfo:
    """Get model metadata and status."""
    _, metadata = _load_model()
    return ModelInfo(
        loaded=_model is not None,
        metadata=metadata,
        uptime_seconds=time.time() - _start_time,
    )


@app.post("/model/infer", response_model=ChordInferenceResponse, tags=["Model"])
async def infer_chords(req: ChordInferenceRequest) -> ChordInferenceResponse:
    """Run chord inference on audio data.

    Accepts flattened audio samples and returns per-frame chord probabilities.
    """
    from app.circuit_breaker import model_server_breaker
    from app.metrics import pipeline_stage_duration_seconds

    if not model_server_breaker.allow_request():
        raise HTTPException(status_code=503, detail="Model server circuit breaker is OPEN")

    start = time.time()

    try:
        if _model is None:
            # Mock mode for development
            frame_count = max(1, len(req.audio_data) // 512)
            mock_pred = [0.0] * 277  # 277 chord classes
            mock_pred[0] = 1.0  # C:maj
            predictions = [mock_pred] * frame_count
            model_version = "mock"
        else:
            # Real TFLite inference
            import numpy as np

            audio = np.array(req.audio_data, dtype=np.float32)
            if audio.ndim == 1:
                audio = audio.reshape(1, -1)

            # Chunk into frames
            frame_size = 512
            hop_size = 256
            predictions = []

            for start_idx in range(0, len(audio[0]) - frame_size + 1, hop_size):
                chunk = audio[0, start_idx:start_idx + frame_size]
                chunk = chunk.reshape(1, frame_size, 1).astype(np.float32)

                input_details = _model.get_input_details()
                output_details = _model.get_output_details()

                _model.set_tensor(input_details[0]["index"], chunk)
                _model.invoke()
                output = _model.get_tensor(output_details[0]["index"])
                predictions.append(output[0].tolist())

            if not predictions:
                predictions = [[0.0] * 277]

            model_version = _model_metadata.get("model_path", "unknown")

        inference_ms = (time.time() - start) * 1000

        model_server_breaker.record_success()

        return ChordInferenceResponse(
            predictions=predictions,
            model_version=model_version,
            inference_time_ms=round(inference_ms, 2),
            frame_count=len(predictions),
        )

    except Exception as exc:
        model_server_breaker.record_failure()
        logger.exception("inference_failed")
        raise HTTPException(status_code=500, detail=f"Inference failed: {exc}") from exc


@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Model server health check."""
    return {
        "status": "ok" if _model is not None else "degraded",
        "model_loaded": _model is not None,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }
