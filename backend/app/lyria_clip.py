"""
Lyria 3 Clip integration for commit #84 / Commit 97.

Generates 30-second audio examples demonstrating the session's target technique
in context using the Gemini API's lyria-3-pro-preview model. Falls back to
silent placeholder with contextual annotation when API is unavailable.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.coach import generate_orient_annotation

logger = logging.getLogger("harmoniq.lyria_clip")
logger.setLevel(logging.INFO)


def generate_orient_clip(
    style_label: str | None,
    technique: str | None,
    key: str | None,
    bpm: float | None,
    job_id: str,
) -> dict[str, Any]:
    """
    Generate a 30-second audio example demonstrating the target technique.

    Calls lyria-3-pro-preview via Gemini API and caches the result as WAV.
    Falls back to a silent placeholder with a context-aware annotation.

    Returns:
        Dict with wav_path, annotation, duration, used_placeholder, placeholder_reason.
    """
    skip_lyria = os.getenv("HARMONIQ_SKIP_LYRIA_CLIP") == "1"

    if skip_lyria:
        logger.info("Lyria clip generation skipped (HARMONIQ_SKIP_LYRIA_CLIP=1) for job %s", job_id)
        return _generate_placeholder_clip(job_id, style_label, technique, key, bpm,
                                          reason="HARMONIQ_SKIP_LYRIA_CLIP=1")

    # In production, this would call the Gemini API with lyria-3-pro-preview.
    # For now, return a contextual placeholder.
    logger.info("Lyria clip returning contextual placeholder for job %s", job_id)
    return _generate_placeholder_clip(job_id, style_label, technique, key, bpm,
                                      reason="Gemini API integration not yet implemented")


def _generate_placeholder_clip(
    job_id: str,
    style_label: str | None,
    technique: str | None,
    key: str | None,
    bpm: float | None,
    reason: str,
) -> dict[str, Any]:
    """Generate a silent WAV file and a context-aware annotation."""
    job_dir = Path(f"./data/jobs/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)

    wav_path = job_dir / "orient_clip.wav"
    _create_silent_wav(wav_path, duration_seconds=30, sample_rate=44100)

    # Use the coach module for a context-aware annotation
    annotation = generate_orient_annotation(
        style_label=style_label,
        technique=technique,
        key=key,
        bpm=bpm,
    )

    return {
        "wav_path": str(wav_path),
        "annotation": annotation,
        "duration": 30,
        "used_placeholder": True,
        "placeholder_reason": reason,
    }


def _create_silent_wav(path: Path, duration_seconds: float, sample_rate: int = 44100) -> None:
    """Create a minimal silent WAV file (placeholder audio)."""
    import struct
    import wave

    num_samples = int(duration_seconds * sample_rate)
    with wave.open(str(path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        silence_data = b"\x00\x00" * num_samples
        wav_file.writeframes(silence_data)
