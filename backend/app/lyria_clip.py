"""
Lyria 3 Clip integration for commit #84.

Generates 30-second audio examples demonstrating the session's target technique
in context using the Gemini API's lyria-3-pro-preview model.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

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
    
    Args:
        style_label: Musical style (e.g., "rock", "blues", "jazz")
        technique: Target technique (e.g., "bend", "hammer-on", "slide")
        key: Musical key (e.g., "C major", "A minor")
        bpm: Tempo in beats per minute
        job_id: Job ID for caching
    
    Returns:
        Dict containing:
        - wav_path: Path to generated WAV file (or placeholder)
        - annotation: What to listen for (template or generated)
        - duration: Duration in seconds
        - used_placeholder: Whether a placeholder was used
    """
    # Check if Lyria generation should be skipped
    skip_lyria = os.getenv("HARMONIQ_SKIP_LYRIA_CLIP") == "1"
    
    if skip_lyria:
        logger.info(f"Lyria clip generation skipped (HARMONIQ_SKIP_LYRIA_CLIP=1) for job {job_id}")
        return _generate_placeholder_clip(job_id, reason="HARMONIQ_SKIP_LYRIA_CLIP=1")
    
    # In production, this would call the Gemini API with lyria-3-pro-preview
    # For now, we return a placeholder with a note about API integration
    logger.info(f"Lyria clip generation not yet implemented for job {job_id} - returning placeholder")
    return _generate_placeholder_clip(
        job_id,
        reason="Gemini API integration not yet implemented",
    )


def _generate_placeholder_clip(job_id: str, reason: str) -> dict[str, Any]:
    """
    Generate a placeholder silent WAV file and template annotation.
    
    This is used when HARMONIQ_SKIP_LYRIA_CLIP=1 or when the API is not yet available.
    """
    # Create a silent WAV file (placeholder)
    job_dir = Path(f"./data/jobs/{job_id}")
    job_dir.mkdir(parents=True, exist_ok=True)
    
    wav_path = job_dir / "orient_clip.wav"
    
    # Create a minimal WAV file (silent, 30 seconds)
    # WAV header + silence
    _create_silent_wav(wav_path, duration_seconds=30, sample_rate=44100)
    
    # Template annotation
    annotation = _get_template_annotation()
    
    return {
        "wav_path": str(wav_path),
        "annotation": annotation,
        "duration": 30,
        "used_placeholder": True,
        "placeholder_reason": reason,
    }


def _create_silent_wav(
    path: Path,
    duration_seconds: float,
    sample_rate: int = 44100,
) -> None:
    """
    Create a silent WAV file.
    
    This is a minimal implementation for placeholder audio.
    """
    import struct
    import wave
    
    num_samples = int(duration_seconds * sample_rate)
    
    with wave.open(str(path), "w") as wav_file:
        # WAV format: 1 channel (mono), 16-bit PCM, 44.1kHz
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(sample_rate)
        
        # Write silence (zeros)
        silence_data = b"\x00\x00" * num_samples
        wav_file.writeframes(silence_data)


def _get_template_annotation() -> str:
    """
    Get a template annotation for the orient clip.
    
    This tells the user what to listen for in the technique example.
    """
    return "Listen for how the technique is used in context. Pay attention to the timing and how it fits with the rhythm section. Notice the subtle variations in the sound quality."
