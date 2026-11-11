"""Teacher event/note conversion helpers.

All teachers speak the same note contract:

    TeacherNote(pitch, onset, offset, velocity, program, confidence)

MT3 emits onset/offset event streams; the PyTorch teachers emit MIDI. These
helpers normalize both into notes and back into an ``Mt3EventStream`` so the
shared chord decoder can be applied consistently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.mt3.schemas import Mt3Event, Mt3EventStream


class TeacherError(RuntimeError):
    """Base class for teacher failures."""


class TeacherUnavailable(TeacherError):
    """The teacher is not installed/configured."""


class TeacherTimeout(TeacherError):
    """The teacher exceeded its per-track time budget."""


@dataclass(frozen=True)
class TeacherNote:
    """A normalized note produced by any teacher."""

    pitch: int
    onset: float
    offset: float
    velocity: int = 80
    program: int | None = 24
    confidence: float = 0.9

    @property
    def duration(self) -> float:
        return max(0.0, self.offset - self.onset)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pitch": int(self.pitch),
            "onset": round(float(self.onset), 6),
            "offset": round(float(self.offset), 6),
            "velocity": int(self.velocity),
            "program": int(self.program) if self.program is not None else None,
            "confidence": round(float(self.confidence), 6),
        }


@dataclass
class TeacherOutput:
    """A teacher's transcription for one track."""

    notes: list[TeacherNote] = field(default_factory=list)
    latency_ms: float = 0.0
    model_version: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "notes": [note.as_dict() for note in self.notes],
            "latency_ms": round(float(self.latency_ms), 3),
            "model_version": self.model_version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TeacherOutput":
        return cls(
            notes=[
                TeacherNote(
                    pitch=int(item["pitch"]),
                    onset=float(item["onset"]),
                    offset=float(item["offset"]),
                    velocity=int(item.get("velocity", 80)),
                    program=(
                        int(item["program"])
                        if item.get("program") is not None
                        else None
                    ),
                    confidence=float(item.get("confidence", 0.9)),
                )
                for item in payload.get("notes", [])
            ],
            latency_ms=float(payload.get("latency_ms", 0.0)),
            model_version=str(payload.get("model_version", "unknown")),
            metadata=dict(payload.get("metadata") or {}),
        )


def events_to_notes(
    events: Iterable[Any],
    *,
    audio_duration: float | None = None,
) -> list[TeacherNote]:
    """Pair onset/offset events into notes.

    Notes still open at the end are closed at ``audio_duration`` or the last
    event time plus 50 ms. Events without a matching offset still produce a
    short note so a malformed teacher output is visible rather than dropped.
    """
    ordered = sorted(
        events,
        key=lambda event: (
            float(getattr(event, "time", 0.0)),
            0 if getattr(event, "is_onset", True) else 1,
        ),
    )
    active: dict[tuple[int, int | None], Any] = {}
    notes: list[TeacherNote] = []
    last_time = 0.0

    def _close(key: tuple[int, int | None], end: float) -> None:
        onset = active.pop(key, None)
        if onset is None:
            return
        start = float(getattr(onset, "time", 0.0))
        pitch = int(getattr(onset, "pitch", 0))
        program = getattr(onset, "program", None)
        notes.append(
            TeacherNote(
                pitch=pitch,
                onset=start,
                offset=max(end, start + 0.01),
                velocity=int(getattr(onset, "velocity", 80) or 80),
                program=int(program) if program is not None else None,
                confidence=float(getattr(onset, "confidence", 0.9) or 0.9),
            )
        )

    for event in ordered:
        time_s = float(getattr(event, "time", 0.0))
        last_time = max(last_time, time_s)
        pitch = int(getattr(event, "pitch", 0))
        raw_program = getattr(event, "program", 24)
        program = int(raw_program) if raw_program is not None else None
        key = (pitch, program)
        is_offset = bool(getattr(event, "is_offset", False)) or not bool(
            getattr(event, "is_onset", True)
        )
        if is_offset:
            _close(key, time_s)
        else:
            # A repeated onset without an offset closes the prior note.
            if key in active:
                _close(key, time_s)
            active[key] = event

    end_time = (
        float(audio_duration)
        if audio_duration is not None and audio_duration > last_time
        else last_time + 0.05
    )
    for key in list(active):
        _close(key, end_time)

    return sorted(notes, key=lambda note: (note.onset, note.pitch, note.offset))


def notes_to_event_stream(
    notes: Iterable[TeacherNote],
    *,
    audio_duration: float,
    model_version: str = "teacher",
) -> Mt3EventStream:
    """Convert notes to an MT3-style event stream for the shared chord decoder."""
    events: list[Mt3Event] = []
    for note in notes:
        events.append(
            Mt3Event(
                time=float(note.onset),
                pitch=int(note.pitch),
                velocity=int(note.velocity),
                program=int(note.program) if note.program is not None else 24,
                is_onset=True,
                confidence=float(note.confidence),
            )
        )
        events.append(
            Mt3Event(
                time=float(note.offset),
                pitch=int(note.pitch),
                velocity=0,
                program=int(note.program) if note.program is not None else 24,
                is_onset=False,
                is_offset=True,
                confidence=float(note.confidence),
            )
        )
    events.sort(key=lambda event: (event.time, event.pitch, 0 if event.is_onset else 1))
    mean_confidence = (
        sum(note.confidence for note in notes) / len(notes)
        if notes
        else 0.0
    )
    programs = {
        note.program for note in notes if note.program is not None and note.program != 128
    }
    return Mt3EventStream(
        events=events,
        audio_duration_s=float(audio_duration),
        model_version=model_version,
        inference_time_ms=0.0,
        mean_confidence=float(mean_confidence),
        num_instruments=len(programs),
    )


def midi_file_to_notes(path: Path, *, program_override: int | None = None) -> list[TeacherNote]:
    """Read notes from a MIDI file produced by a PyTorch teacher."""
    try:
        import pretty_midi
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise TeacherError("pretty_midi is required to read teacher MIDI") from exc

    try:
        midi = pretty_midi.PrettyMIDI(str(path))
    except Exception as exc:
        raise TeacherError(f"could not read teacher MIDI {path}: {exc}") from exc

    notes: list[TeacherNote] = []
    for instrument in midi.instruments:
        if instrument.is_drum:
            continue
        program = (
            program_override
            if program_override is not None
            else int(instrument.program)
        )
        for note in instrument.notes:
            notes.append(
                TeacherNote(
                    pitch=int(note.pitch),
                    onset=float(note.start),
                    offset=float(note.end),
                    velocity=int(note.velocity),
                    program=program,
                    confidence=0.9,
                )
            )
    return sorted(notes, key=lambda note: (note.onset, note.pitch, note.offset))
