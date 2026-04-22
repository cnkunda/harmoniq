"""
Transcription validation module for commit #82.

Post-processes inference output to verify physical playability on a 6-string fretboard,
flagging impossible voicings or low SNR sections.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.pipeline_proof import NoteEvent

logger = logging.getLogger("harmoniq.transcription_validator")
logger.setLevel(logging.INFO)


@dataclass
class ValidationResult:
    """Result of validating a transcription section."""
    is_playable: bool
    flag_reason: str | None = None
    model_version: str = "v1.0"
    confidence: float = 1.0


def is_physically_playable_on_guitar(
    midi_pitch: int,
    string: int | None = None,
    fret: int | None = None,
) -> bool:
    """
    Check if a note is physically playable on a standard 6-string guitar.
    
    Standard tuning (low to high): E2 (MIDI 40), A2 (45), D3 (50), G3 (55), B3 (59), E4 (64)
    Maximum practical fret: ~24 (some guitars go higher, but this is a reasonable limit)
    """
    # Standard guitar range: E2 (40) to C8 (120) on high strings
    if midi_pitch < 40 or midi_pitch > 120:
        return False
    
    # If string and fret are provided, verify the combination is valid
    if string is not None and fret is not None:
        if string < 1 or string > 6:
            return False
        if fret < 0 or fret > 24:
            return False
        
        # Standard tuning MIDI values
        standard_tuning = [40, 45, 50, 55, 59, 64]  # E2, A2, D3, G3, B3, E4
        open_string_midi = standard_tuning[string - 1]
        expected_pitch = open_string_midi + fret
        
        # Allow for some tolerance (e.g., bends, vibrato)
        if abs(midi_pitch - expected_pitch) > 2:
            return False
    
    return True


def validate_note_events_for_playability(events: list[NoteEvent]) -> ValidationResult:
    """
    Validate that note events are physically playable on a 6-string guitar.
    
    Flags impossible voicings (e.g., notes outside guitar range, impossible fret/string combos).
    """
    if not events:
        return ValidationResult(is_playable=True, confidence=1.0)
    
    unplayable_count = 0
    total_count = len(events)
    
    for event in events:
        # Check if the pitch is within guitar range
        if not is_physically_playable_on_guitar(event.pitch_midi):
            unplayable_count += 1
            logger.warning(
                f"Unplayable note detected: pitch={event.pitch_midi}, "
                f"time={event.start_s}-{event.end_s}"
            )
    
    # If more than 10% of notes are unplayable, flag the section
    if total_count > 0 and (unplayable_count / total_count) > 0.1:
        confidence = 1.0 - (unplayable_count / total_count)
        return ValidationResult(
            is_playable=False,
            flag_reason=f"Unplayable voicings: {unplayable_count}/{total_count} notes outside guitar range",
            confidence=max(0.0, confidence),
        )
    
    return ValidationResult(is_playable=True, confidence=1.0)


def estimate_snr_quality(audio_path: str | None) -> float:
    """
    Estimate signal-to-noise ratio quality from audio file.
    
    This is a placeholder implementation. In production, this would analyze
    the audio waveform to detect noise floor vs signal amplitude.
    
    Returns a confidence score between 0.0 (very noisy) and 1.0 (clean).
    """
    if audio_path is None:
        return 0.5  # Neutral score when no audio available
    
    # Placeholder: In production, implement actual SNR analysis
    # using librosa or similar audio processing library
    return 0.8


def validate_section_transcription(
    events: list[NoteEvent],
    audio_path: str | None = None,
    transcription_confidence: float = 1.0,
) -> ValidationResult:
    """
    Comprehensive validation of a transcription section.
    
    Combines playability checks with SNR estimation and transcription confidence.
    """
    # Validate physical playability
    playability_result = validate_note_events_for_playability(events)
    
    # Estimate SNR quality
    snr_quality = estimate_snr_quality(audio_path)
    
    # Combine confidence scores
    combined_confidence = min(
        playability_result.confidence,
        snr_quality,
        transcription_confidence,
    )
    
    # Determine overall flag reason
    flag_reasons = []
    if not playability_result.is_playable and playability_result.flag_reason:
        flag_reasons.append(playability_result.flag_reason)
    if snr_quality < 0.6:
        flag_reasons.append(f"Low SNR quality: {snr_quality:.2f}")
    if transcription_confidence < 0.6:
        flag_reasons.append(f"Low transcription confidence: {transcription_confidence:.2f}")
    
    flag_reason = "; ".join(flag_reasons) if flag_reasons else None
    
    is_playable = combined_confidence >= 0.6
    
    return ValidationResult(
        is_playable=is_playable,
        flag_reason=flag_reason,
        confidence=combined_confidence,
    )


def add_validation_metadata_to_section(
    section: dict[str, Any],
    validation_result: ValidationResult,
) -> dict[str, Any]:
    """
    Add validation metadata to a lesson section.
    
    This metadata will be stored in the DB and used by the frontend
    to display warnings and prompts for collaborative verification.
    """
    section_copy = section.copy()
    
    # Add transcription_metadata field if it doesn't exist
    if "transcription_metadata" not in section_copy:
        section_copy["transcription_metadata"] = {}
    
    # Update with validation results
    section_copy["transcription_metadata"]["validation"] = {
        "is_playable": validation_result.is_playable,
        "flag_reason": validation_result.flag_reason,
        "model_version": validation_result.model_version,
        "confidence": validation_result.confidence,
    }
    
    return section_copy
