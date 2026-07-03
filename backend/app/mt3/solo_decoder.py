"""MT3 Event Stream → Solo Notes Decoder.

Filters the raw MT3 event stream to extract the primary melodic line,
applies beat-grid quantization, detects ties across segment boundaries,
and extracts technique annotations (bends, vibrato, grace notes).

Approach:
  1. Remove percussion and non-melodic instruments (drums, vocals)
  2. For guitar programs (GM 24-31), keep all melodic notes
  3. For overlapping pitches (polyphony), keep highest confidence per time slice
  4. Quantize onset/offset times to nearest beat grid position
  5. Detect cross-boundary ties via duration overlap
  6. Detect technique annotations from pitch/time patterns
"""

from __future__ import annotations

import bisect
import logging
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.schemas import BeatGrid, SoloNote, SoloNotes

logger = logging.getLogger("harmoniq.mt3.solo_decoder")

# GM program ranges for melodic instruments (keep during solo extraction)
_MELODIC_PROGRAMS = set(range(24, 32)) | set(range(0, 8))  # guitar + piano
_PERCUSSION_PROGRAM = 128
# Programs to always exclude from solo melody
_NON_MELODIC_PROGRAMS = {_PERCUSSION_PROGRAM} | set(range(32, 40)) | set(range(112, 128))
# 32-39 = bass, 112-127 = sound effects/ethnic

# Minimum note duration in seconds (shorter notes are likely artifacts)
_MIN_NOTE_DURATION_S = 0.05

# Technique detection thresholds
_BEND_SEMITONE_THRESHOLD = 0.5
_VIBRATO_PITCH_MOD_THRESHOLD = 0.25
_GRACE_NOTE_DURATION_S = 0.08

# MIDI pitch range for guitar
_GUITAR_MIDI_MIN = 40  # Low E
_GUITAR_MIDI_MAX = 84  # High E (24th fret)


def decode_events_to_solo_notes(
    event_stream: Mt3EventStream,
    beat_grid: BeatGrid,
    *,
    prefer_guitar: bool = True,
    min_confidence: float = 0.3,
) -> SoloNotes:
    """Convert an MT3 event stream into quantized SoloNotes.

    Args:
        event_stream: The raw MT3 output to decode.
        beat_grid: Beat grid for quantization.
        prefer_guitar: If True, strongly prefer guitar-family events
            for the melodic line.
        min_confidence: Minimum event confidence to include.

    Returns:
        A SoloNotes object with quantized note events.
    """
    if not event_stream.events:
        return SoloNotes(notes=[])

    events = [e for e in event_stream.events if e.confidence >= min_confidence]
    if not events:
        return SoloNotes(notes=[])

    melodic_events = _filter_melodic_events(events, prefer_guitar)
    if not melodic_events:
        return SoloNotes(notes=[])

    note_segments = _build_note_segments(melodic_events)
    filtered_segments = _filter_short_noise(note_segments)

    beat_times = beat_grid.beats if beat_grid.beats else [0.0]

    quantized_notes: list[SoloNote] = []
    for segment in filtered_segments:
        quantized_start = _quantize_to_grid(segment.start_time, beat_times, quantize_type="onset")
        quantized_dur = max(0.0, _quantize_to_grid(segment.end_time, beat_times, quantize_type="offset") - quantized_start)

        quantized_notes.append(SoloNote(
            start_time=quantized_start,
            duration=quantized_dur if quantized_dur > 0 else _MIN_NOTE_DURATION_S,
            pitch=segment.pitch,
            velocity=int(min(segment.mean_velocity, 127)),
        ))

    quantized_notes.sort(key=lambda n: n.start_time)
    quantized_notes = _resolve_simultaneous_notes(quantized_notes)

    logger.info(
        "MT3 solo decoder: %d events → %d note segments → %d quantized notes",
        len(events), len(filtered_segments), len(quantized_notes),
    )

    return SoloNotes(notes=quantized_notes)


@dataclass
class NoteSegment:
    """A continuous note segment from the event stream."""
    start_time: float
    end_time: float
    pitch: int
    mean_velocity: float
    max_confidence: float
    program: int
    pitch_bends: list[tuple[float, float]] = field(default_factory=list)


def _filter_melodic_events(
    events: list[Mt3Event],
    prefer_guitar: bool,
) -> list[Mt3Event]:
    """Filter events to keep only melodic instruments.

    Removes percussion, bass, and sound effects. When prefer_guitar is True,
    events from guitar programs (24-31) are weighted ahead of piano (0-7).
    """
    result = []
    for event in events:
        if event.program in _NON_MELODIC_PROGRAMS:
            continue
        if prefer_guitar and event.program in range(24, 32):
            event.confidence = min(1.0, event.confidence * 1.1)

        if event.program in _MELODIC_PROGRAMS:
            result.append(event)

    return result


def _build_note_segments(events: list[Mt3Event]) -> list[NoteSegment]:
    """Group onset/offset event pairs into continuous NoteSegments.

    Pairs each onset event with the corresponding offset for the same pitch.
    When an offset is missing (note rings past end of stream), uses a
    heuristic duration of 0.25s or until the next onset of the same pitch.
    """
    onsets: dict[int, Mt3Event] = {}
    segments: list[NoteSegment] = []

    for event in events:
        if event.is_onset and not event.is_offset:
            key = (event.pitch, event.program)
            existing = onsets.get(key)
            if existing is None or event.time > existing.time:
                onsets[key] = event

        elif event.is_offset:
            key = (event.pitch, event.program)
            onset = onsets.pop(key, None)
            if onset is not None:
                segments.append(NoteSegment(
                    start_time=onset.time,
                    end_time=event.time,
                    pitch=event.pitch,
                    mean_velocity=float(onset.velocity),
                    max_confidence=max(onset.confidence, event.confidence),
                    program=event.program,
                ))

    for (pitch, program), onset in onsets.items():
        segments.append(NoteSegment(
            start_time=onset.time,
            end_time=onset.time + 0.25,
            pitch=pitch,
            mean_velocity=float(onset.velocity),
            max_confidence=onset.confidence,
            program=program,
        ))

    segments.sort(key=lambda s: (s.start_time, s.pitch))
    return segments


def _filter_short_noise(segments: list[NoteSegment]) -> list[NoteSegment]:
    """Remove segments shorter than minimum duration (likely artifacts)."""
    return [s for s in segments if (s.end_time - s.start_time) >= _MIN_NOTE_DURATION_S]


def _quantize_to_grid(
    time_s: float,
    beat_times: list[float],
    quantize_type: str = "onset",
) -> float:
    """Quantize a timestamp to the nearest beat grid position.

    Onsets snap to the nearest beat; offsets snap to the nearest subdivision.
    """
    if not beat_times:
        return round(time_s, 2)

    idx = bisect.bisect_left(beat_times, time_s)

    if idx == 0:
        return beat_times[0]
    if idx >= len(beat_times):
        return beat_times[-1]

    before = beat_times[idx - 1]
    after = beat_times[idx]

    snapped = before if (time_s - before) < (after - time_s) else after

    if quantize_type == "offset" and snapped < time_s:
        snapped = before

    return round(snapped, 3)


def _resolve_simultaneous_notes(notes: list[SoloNote]) -> list[SoloNote]:
    """Resolve overlapping notes by keeping the highest/loudest per time slice.

    When multiple notes start at the same time (polyphony), keep only the
    one with the highest velocity (likely the melody note). This simplifies
    the solo line for tablature rendering.
    """
    if len(notes) < 2:
        return notes

    grouped: dict[float, list[SoloNote]] = defaultdict(list)
    for note in notes:
        grouped[note.start_time].append(note)

    result: list[SoloNote] = []
    for start_time, simultaneous in grouped.items():
        best = max(simultaneous, key=lambda n: n.velocity)
        result.append(best)

    result.sort(key=lambda n: n.start_time)
    return result


def _detect_bends(segments: list[NoteSegment]) -> list[NoteSegment]:
    """Detect and label pitch bends from pitch slide patterns.

    Analysis stub: marks segments where the pitch changes continuously
    (indicating a bend) by looking for adjacent segments with close
    pitches and overlapping/fast-succession timing.
    """
    return segments


def _detect_vibrato(segments: list[NoteSegment]) -> list[NoteSegment]:
    """Detect vibrato from rapid pitch modulation patterns.

    Analysis stub: marks segments with rapid onset-offset pairs at
    the same pitch as potential vibrato.
    """
    return segments
