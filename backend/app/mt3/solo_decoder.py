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

    filtered_segments = _detect_bends(filtered_segments)
    filtered_segments = _detect_vibrato(filtered_segments)
    filtered_segments = _detect_grace_notes(filtered_segments)

    beat_times = beat_grid.beats if beat_grid.beats else [0.0]

    quantized_notes: list[SoloNote] = []
    for segment in filtered_segments:
        quantized_start = _quantize_to_grid(segment.start_time, beat_times, quantize_type="onset")
        quantized_dur = max(0.0, _quantize_to_grid(segment.end_time, beat_times, quantize_type="offset") - quantized_start)

        coherence = _coherence_factor(segment, filtered_segments)
        base_confidence = segment.max_confidence
        event_confidence = base_confidence * coherence

        quantized_notes.append(SoloNote(
            start_time=quantized_start,
            duration=quantized_dur if quantized_dur > 0 else _MIN_NOTE_DURATION_S,
            pitch=segment.pitch,
            velocity=int(min(segment.mean_velocity, 127)),
            confidence=round(event_confidence, 3),
            technique=list(segment.technique),
        ))

    quantized_notes.sort(key=lambda n: n.start_time)
    quantized_notes = _resolve_simultaneous_notes(quantized_notes)

    bpm = beat_grid.bpm if beat_grid.bpm > 0 else 120.0
    quantized_notes = _merge_boundary_notes(quantized_notes, bpm)

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
    technique: list[str] = field(default_factory=list)


@dataclass
class _ActiveNote:
    """A note still ringing at a segment boundary (tie mechanism)."""
    start_time: float
    pitch: int
    velocity: float
    end_time: float


class _TieRegistry:
    """Tracks active notes across segment boundaries and resolves ties.

    Matches notes by pitch proximity (±1 semitone), onset timing (within
    tie_epsilon_s of boundary), and velocity similarity.
    """

    def __init__(
        self,
        bpm: float,
        tie_epsilon_s: float = 0.050,
        velocity_tolerance: float = 0.3,
        max_sustain_beats: int = 4,
    ):
        self.active_notes: list[_ActiveNote] = []
        self.last_segment_end: float = 0.0
        self.beat_duration = 60.0 / bpm if bpm > 0 else 0.5
        self.tie_epsilon_s = tie_epsilon_s
        self.velocity_tolerance = velocity_tolerance
        self.max_sustain_beats = max_sustain_beats

    def register_segment_end(self, notes: list[SoloNote], segment_end: float):
        """Collect notes still ringing at the segment boundary."""
        self.active_notes = []
        for note in notes:
            note_end = note.start_time + note.duration
            if note_end > segment_end:
                self.active_notes.append(_ActiveNote(
                    start_time=note.start_time,
                    pitch=note.pitch,
                    velocity=float(note.velocity),
                    end_time=note_end,
                ))
        self.last_segment_end = segment_end

    def resolve_segment_start(self, notes: list[SoloNote]) -> list[SoloNote]:
        """Merge tied notes, close truncated ones, keep new notes.

        Returns deduplicated note list with cross-boundary ties resolved.
        """
        output: list[SoloNote] = []
        matched_indices: set[int] = set()

        for active in self.active_notes:
            max_duration = self.max_sustain_beats * self.beat_duration
            if active.end_time - active.start_time > max_duration:
                active.end_time = active.start_time + max_duration

            match_idx = self._find_matching_note(notes, active)

            if match_idx is not None:
                matched_indices.add(match_idx)
                new_note = notes[match_idx]
                merged_duration = new_note.start_time + new_note.duration - active.start_time
                output.append(SoloNote(
                    start_time=round(active.start_time, 3),
                    duration=round(merged_duration, 3),
                    pitch=active.pitch,
                    velocity=int(max(active.velocity, new_note.velocity)),
                    confidence=max(new_note.confidence, 0.5),
                    is_tied=True,
                    technique=new_note.technique,
                ))
            else:
                truncated_duration = min(self.last_segment_end, active.end_time) - active.start_time
                if truncated_duration > 0:
                    output.append(SoloNote(
                        start_time=round(active.start_time, 3),
                        duration=round(truncated_duration, 3),
                        pitch=active.pitch,
                        velocity=int(active.velocity),
                        confidence=0.5,
                    ))

        for i, note in enumerate(notes):
            if i not in matched_indices:
                output.append(note)

        output.sort(key=lambda n: n.start_time)
        return output

    def _find_matching_note(
        self,
        notes: list[SoloNote],
        active: _ActiveNote,
    ) -> int | None:
        """Find a note in the next segment that matches the active note.

        Criteria: same pitch (±1 semitone), onset within epsilon of boundary,
        velocity within tolerance.
        """
        for i, note in enumerate(notes):
            pitch_match = abs(note.pitch - active.pitch) <= 1
            onset_near_boundary = abs(note.start_time - self.last_segment_end) <= self.tie_epsilon_s
            if not (pitch_match and onset_near_boundary):
                continue

            if active.velocity > 0:
                vel_ratio = abs(note.velocity - active.velocity) / active.velocity
                velocity_match = vel_ratio <= self.velocity_tolerance
            else:
                velocity_match = True

            if velocity_match:
                return i

        return None


def _merge_boundary_notes(
    notes: list[SoloNote],
    bpm: float,
    window_sec: float = 12.8,
) -> list[SoloNote]:
    """Post-decode merge pass: resolve ties at segment boundaries.

    Applies the _TieRegistry mechanism to notes that span virtual segment
    boundaries (every 128 chord frames = 12.8s at _HOP_SEC=0.1).

    Args:
        notes: Quantized solo notes.
        bpm: Tempo for sustain timeout calculation.
        window_sec: Duration of one non-overlapping window.

    Returns:
        Deduplicated note list with cross-boundary ties merged.
    """
    if not notes:
        return []

    registry = _TieRegistry(bpm=bpm)
    all_notes = list(notes)
    result: list[SoloNote] = []

    boundaries = []
    b = window_sec
    max_time = max(n.start_time + n.duration for n in all_notes)
    while b < max_time:
        boundaries.append(b)
        b += window_sec

    for boundary in boundaries:
        segment_notes = [n for n in all_notes if n.start_time < boundary]
        remaining = [n for n in all_notes if n.start_time >= boundary]

        if not segment_notes:
            continue

        registry.register_segment_end(segment_notes, boundary)
        resolved = registry.resolve_segment_start(remaining)

        closed_notes = [n for n in segment_notes if n.start_time + n.duration <= boundary]
        result.extend(closed_notes)

        all_notes = resolved

    result.extend(all_notes)
    result.sort(key=lambda n: (n.start_time, n.pitch))

    if len(result) < len(notes):
        logger.info(
            "Boundary tie merge: %d notes → %d notes (%d merged)",
            len(notes), len(result), len(notes) - len(result),
        )

    return result


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

    Looks for adjacent segments where:
    - Pitches are within 2 semitones of each other
    - Timing gap is < 50ms (continuous slide)
    - Same program

    Tags matched segments with technique tag "bend".
    """
    if len(segments) < 2:
        return segments

    sorted_segs = sorted(segments, key=lambda s: (s.start_time, s.pitch))
    tagged: set[int] = set()

    for i in range(len(sorted_segs) - 1):
        seg1 = sorted_segs[i]
        seg2 = sorted_segs[i + 1]

        if seg1.program != seg2.program:
            continue

        pitch_diff = abs(seg2.pitch - seg1.pitch)
        gap = seg2.start_time - seg1.end_time

        if pitch_diff <= 2 and 0 <= gap < 0.050:
            if i not in tagged:
                seg1.technique.append("bend")
                tagged.add(i)
            if (i + 1) not in tagged:
                seg2.technique.append("bend")
                tagged.add(i + 1)

    return segments


def _detect_vibrato(segments: list[NoteSegment]) -> list[NoteSegment]:
    """Detect vibrato from rapid pitch modulation patterns.

    Looks for 3+ consecutive segments at the same pitch (±1 semitone) with
    durations < 100ms each, totaling < 500ms. This pattern indicates rapid
    oscillation around a target pitch.

    Tags matching segments with technique tag "vibrato".
    """
    if len(segments) < 3:
        return segments

    sorted_segs = sorted(segments, key=lambda s: (s.start_time, s.pitch))
    tagged: set[int] = set()

    i = 0
    while i < len(sorted_segs):
        ref_pitch = sorted_segs[i].pitch
        run_indices = [i]

        j = i + 1
        while j < len(sorted_segs):
            seg = sorted_segs[j]
            prev = sorted_segs[j - 1]
            gap = seg.start_time - prev.end_time
            if (
                abs(seg.pitch - ref_pitch) <= 1
                and (seg.end_time - seg.start_time) < 0.100
                and gap < 0.050
            ):
                run_indices.append(j)
                j += 1
            else:
                break

        if len(run_indices) >= 3:
            total_duration = (
                sorted_segs[run_indices[-1]].end_time
                - sorted_segs[run_indices[0]].start_time
            )
            if total_duration < 0.500:
                for idx in run_indices:
                    if idx not in tagged:
                        sorted_segs[idx].technique.append("vibrato")
                        tagged.add(idx)

        i = j if j > i + 1 else i + 1

    return segments


def _detect_grace_notes(segments: list[NoteSegment]) -> list[NoteSegment]:
    """Detect grace notes: short notes preceding a longer note.

    A grace note is shorter than _GRACE_NOTE_DURATION_S (0.08s) and
    immediately precedes a longer note within 50ms. Grace notes are
    musically meaningful and NOT removed — only tagged.

    Tags matching segments with technique tag "grace_note".
    """
    if len(segments) < 2:
        return segments

    sorted_segs = sorted(segments, key=lambda s: s.start_time)

    for i, seg in enumerate(sorted_segs):
        duration = seg.end_time - seg.start_time
        if duration >= _GRACE_NOTE_DURATION_S:
            continue

        for j in range(i + 1, len(sorted_segs)):
            next_seg = sorted_segs[j]
            gap = next_seg.start_time - seg.end_time
            if gap > 0.050:
                break
            next_duration = next_seg.end_time - next_seg.start_time
            if next_duration > _GRACE_NOTE_DURATION_S:
                if "grace_note" not in seg.technique:
                    seg.technique.append("grace_note")
                break

    return segments


def _coherence_factor(
    segment: NoteSegment,
    all_segments: list[NoteSegment],
) -> float:
    """Compute polyphonic coherence factor for confidence weighting.

    Returns 1.0 for monophonic context, 0.9 when the segment overlaps
    in time with other segments (polyphonic context).
    """
    for other in all_segments:
        if other is segment:
            continue
        if other.program != segment.program:
            continue
        overlap = (
            segment.start_time < other.end_time
            and other.start_time < segment.end_time
        )
        if overlap:
            return 0.9
    return 1.0
