"""
Orient clip generation for commit #84 / Commit 97.

Generates a short audio example demonstrating the session's target technique
through the jam-backing provider chain (ACE-Step → Lyria → MRT2 → bundled).
Falls back to a silent placeholder only when generation is skipped or fails.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.coach import generate_orient_annotation
from app.ingest import get_data_dir

logger = logging.getLogger("harmoniq.lyria_clip")
logger.setLevel(logging.INFO)

async def generate_orient_clip(
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

    try:
        from app.music_generation import BackingRequest, generate_backing

        style_hint = ", ".join(part for part in (style_label, technique) if part and part.strip()) or None
        request = BackingRequest(
            musical_key=(key or "A minor").strip(),
            bpm=int(round(bpm)) if bpm else None,
            style_hint=style_hint,
            duration_secs=8.0,
        )
        result = await generate_backing(request)

        orient_dir = get_data_dir() / "orient_clips" / job_id
        orient_dir.mkdir(parents=True, exist_ok=True)
        wav_path = orient_dir / "orient_clip.wav"
        wav_path.write_bytes(result.wav_bytes)

        annotation = generate_orient_annotation(
            style_label=style_label,
            technique=technique,
            key=key,
            bpm=bpm,
        )
        duration = max(0.1, (result.duration_ms or 8000) / 1000)
        used_placeholder = result.provider in {"bundled", "synth"} or result.used_fallback
        return {
            "wav_path": f"data/orient_clips/{job_id}/orient_clip.wav",
            "annotation": annotation,
            "duration": duration,
            "used_placeholder": used_placeholder,
            "placeholder_reason": (
                f"provider_fallback:{result.provider}" if used_placeholder else None
            ),
            "provider": result.provider,
            "key_label": result.key_label,
            "bpm": result.bpm,
        }
    except Exception as exc:  # noqa: BLE001 - orient clip must never block a session
        logger.exception("Orient clip generation failed for job %s", job_id)
        return _generate_placeholder_clip(
            job_id,
            style_label,
            technique,
            key,
            bpm,
            reason=f"generation_failed:{exc}",
        )

def _generate_placeholder_clip(
    job_id: str,
    style_label: str | None,
    technique: str | None,
    key: str | None,
    bpm: float | None,
    reason: str,
) -> dict[str, Any]:
    """Generate a silent WAV file and a context-aware annotation.

    Stores the orient clip at data/orient_clips/<job_id>/orient_clip.wav
    so that it is served via the /lesson-file endpoint (relative path).
    """
    orient_dir = get_data_dir() / "orient_clips" / job_id
    orient_dir.mkdir(parents=True, exist_ok=True)

    wav_path = orient_dir / "orient_clip.wav"
    _create_silent_wav(wav_path, duration_seconds=30, sample_rate=44100)

    # Use the coach module for a context-aware annotation
    annotation = generate_orient_annotation(
        style_label=style_label,
        technique=technique,
        key=key,
        bpm=bpm,
    )

    # Return a path relative to backend root, served by /lesson-file
    rel_path = f"data/orient_clips/{job_id}/orient_clip.wav"
    return {
        "wav_path": rel_path,
        "annotation": annotation,
        "duration": 30,
        "used_placeholder": True,
        "placeholder_reason": reason,
    }


def _create_silent_wav(path: Path, duration_seconds: float, sample_rate: int = 44100) -> None:
    """Create a minimal silent WAV file (placeholder audio)."""
    import wave

    num_samples = int(duration_seconds * sample_rate)
    with wave.open(str(path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        silence_data = b"\x00\x00" * num_samples
        wav_file.writeframes(silence_data)
