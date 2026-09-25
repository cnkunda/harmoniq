"""MT3-specific Pydantic schemas for the event stream and transcription metadata."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Mt3Event(BaseModel):
    """A single event from the MT3 token-level event stream.

    MT3 outputs a sequence of atomic tokens that represent note onsets, offsets,
    pitch changes, velocity changes, and instrument assignments. These are
    decoded into structured Mt3Event objects by the model server.
    """

    time: float = Field(..., description="Event time in seconds")
    pitch: int = Field(..., ge=0, le=127, description="MIDI pitch number")
    velocity: int = Field(default=80, ge=0, le=127, description="MIDI velocity")
    program: int = Field(
        default=24,
        ge=0,
        le=128,
        description="General MIDI program number (24-31 = guitar family; 128 = percussion)",
    )
    is_onset: bool = Field(default=True, description="True if this is a note-on event")
    is_offset: bool = Field(default=False, description="True if this is a note-off event")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Model confidence for this event")


class Mt3EventStream(BaseModel):
    """The full decoded output of a single MT3 inference call.

    Contains all detected notes across all instruments, with timing and
    confidence information. Downstream decoders (chord, solo) filter and
    process this stream independently.
    """

    events: list[Mt3Event] = Field(default_factory=list, description="All detected note events")
    audio_duration_s: float = Field(default=0.0, description="Duration of the input audio in seconds")
    model_version: str = Field(default="mt3-t5-small", description="MT3 model variant used")
    inference_time_ms: float = Field(default=0.0, description="Inference wall time in milliseconds")
    mean_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Mean confidence across all events")
    num_instruments: int = Field(default=0, description="Number of distinct instrument programs detected")


TranscriptionSource = Literal["mt3", "crnn", "chroma", "none"]
"""Identifies which tier of the fallback chain produced the transcription result."""
