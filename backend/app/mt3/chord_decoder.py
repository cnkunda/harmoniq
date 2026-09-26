"""MT3 Event Stream → Chord Timeline Decoder.

Converts the raw MT3 event stream into a harmonically analysed chord timeline
by aggregating sounding pitches per time slice, matching against the chord
interval template set, and applying consistency constraints.

Approach (matches Guitar-TECHS / EGSet12 methodology):
  1. Sort events by time, build active-pitch sets at 0.1s intervals
  2. For each interval: get pitch class set of all active (ringing) notes
  3. Match against CHORD_INTERVALS template set via Jaccard score
  4. Apply >0.66 coverage threshold; "N" if no template scores above threshold
  5. Map from 277-class to 25-class MIREX for frontend compatibility
"""

from __future__ import annotations

import bisect
from collections import Counter, defaultdict

import numpy as np

from app.chord_vocab import (
    CHORD_INTERVALS,
    MIREX_QUALITY_MAP,
    MIREX_TO_IDX,
    ROOT_NOTES,
)
from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.schemas import BeatGrid, ChordEvent, ChordTimeline

# Time slice for chord analysis (0.1s = 10 FPS, matching CQT hop)
_HOP_SECONDS = 0.1

# Minimum Jaccard score to accept a chord match (same threshold as
# Guitar-TECHS and EGSet12 extraction scripts)
_JACCARD_THRESHOLD = 0.66

# Minimum number of simultaneous pitches to consider a chord present
_MIN_PITCHES_FOR_CHORD = 3

# Commitment B9: Minimum confidence threshold for voicing detection
_VOICING_CONFIDENCE_THRESHOLD = 0.6

# GM program numbers to consider for chord inference (guitar + piano family)
_CHORD_INSTRUMENTS = set(range(24, 32)) | set(range(0, 8))

# Guitar family programs (24-31): acoustic/electric guitar variants
_GUITAR_PROGRAMS = set(range(24, 32))

# Percussion program (GM Channel 10)
_PERCUSSION_PROGRAM = 128

def decode_events_to_chord_timeline(
    event_stream: Mt3EventStream,
    beat_grid: BeatGrid,
    *,
    prefer_guitar_programs: bool = True,
    min_confidence: float = 0.3,
) -> ChordTimeline:
    """Convert an MT3 event stream into a ChordTimeline.

    Args:
        event_stream: The raw MT3 output to decode.
        beat_grid: Beat grid for timestamp alignment.
        prefer_guitar_programs: If True, weight guitar-family events higher
            in pitch aggregation. When both guitar and piano notes are
            present, guitar pitches dominate chord inference.
        min_confidence: Minimum event confidence to include in analysis.

    Returns:
        A ChordTimeline with one ChordEvent per time slice.
    """
    if not event_stream.events:
        return ChordTimeline(events=[], metadata={"source": "mt3", "decoder": "chord_decoder", "note_count": 0})

    events = [e for e in event_stream.events if e.confidence >= min_confidence]
    if not events:
        return ChordTimeline(events=[], metadata={"source": "mt3", "decoder": "chord_decoder", "note_count": 0})

    audio_end = event_stream.audio_duration_s or max(e.time for e in events) + 1.0

    active_notes, bass_notes = _build_active_note_grid(
        events, audio_end, prefer_guitar=prefer_guitar_programs,
    )
    chord_events = _infer_chords_from_active_notes(active_notes, bass_notes, audio_end)

    beat_times = beat_grid.beats if beat_grid.beats else [0.0]
    for event in chord_events:
        event.timestamp = _quantize_to_nearest_beat(event.timestamp, beat_times)

    timeline = ChordTimeline(
        events=chord_events,
        metadata={
            "source": "mt3",
            "decoder": "chord_decoder",
            "note_count": len(events),
            "event_count": len(event_stream.events),
            "mean_confidence": event_stream.mean_confidence,
        },
    )
    return timeline


def _build_active_note_grid(
    events: list[Mt3Event],
    audio_end: float,
    *,
    prefer_guitar: bool = True,
) -> tuple[dict[float, dict[int, list[Mt3Event]]], dict[float, int | None]]:
    """Build a time-sliced grid of active (sounding) notes and bass pitches.

    For each 0.1s hop, determine which pitches are actively sounding
    by tracking onsets and offsets across the event stream. Percussion
    (program 128) is always excluded. When prefer_guitar is True and a
    pitch class has events from both guitar-family and non-guitar-family
    programs, only guitar-family events are kept.

    Returns:
        Tuple of (grid, bass_notes):
        - grid: time_slice → {pitch_class: [active_events]}
        - bass_notes: time_slice → lowest active MIDI pitch (or None)
    """
    onsets: list[Mt3Event] = []
    offsets: dict[int, list[float]] = defaultdict(list)

    for event in events:
        if event.program == _PERCUSSION_PROGRAM:
            continue
        if event.is_onset and not event.is_offset:
            onsets.append(event)
        elif event.is_offset:
            offsets[event.pitch].append(event.time)

    onsets.sort(key=lambda e: e.time)

    time_slices = np.arange(0.0, audio_end + _HOP_SECONDS, _HOP_SECONDS)
    grid: dict[float, dict[int, list[Mt3Event]]] = {}
    bass_notes: dict[float, int | None] = {}

    for t in time_slices:
        t = float(round(t, 2))
        raw_active: dict[int, list[Mt3Event]] = {}

        for onset_event in onsets:
            if onset_event.time > t:
                break

            offset_times = offsets.get(onset_event.pitch, [])
            future_offsets = [ot for ot in offset_times if ot >= onset_event.time]
            if future_offsets and min(future_offsets) <= t:
                continue

            pc = onset_event.pitch % 12
            if pc not in raw_active:
                raw_active[pc] = []
            raw_active[pc].append(onset_event)

        if prefer_guitar:
            active: dict[int, list[Mt3Event]] = {}
            for pc, note_events in raw_active.items():
                guitar_events = [e for e in note_events if e.program in _GUITAR_PROGRAMS]
                active[pc] = guitar_events if guitar_events else note_events
        else:
            active = raw_active

        grid[t] = active

        # Compute lowest active MIDI pitch for bass detection.
        # Use raw_active (all instruments) — never guitar-filtered — because
        # the guitar often does not play the bass note (Branch A constraint
        # from PRIORITIES.md B8).
        lowest_midi: int | None = None
        for note_events in raw_active.values():
            for e in note_events:
                if lowest_midi is None or e.pitch < lowest_midi:
                    lowest_midi = e.pitch
        bass_notes[t] = lowest_midi

    return grid, bass_notes


def _infer_chords_from_active_notes(
    active_notes: dict[float, dict[int, list[Mt3Event]]],
    bass_notes: dict[float, int | None],
    audio_end: float,
) -> list[ChordEvent]:
    """Convert active-note grid to chord events via template matching.

    For each time slice, builds a pitch class set from active notes,
    scores all 23 chord templates, and picks the best match above threshold.
    Consecutive slices with the same chord are merged. Bass note and
    inversion are derived from the lowest active MIDI pitch per slice.
    """
    chord_events: list[ChordEvent] = []

    prev_chord: str | None = None
    prev_start: float = 0.0
    prev_confidence: float = 0.0
    prev_bass_counter: Counter[str] = Counter()
    current_active_notes: dict[int, list[Mt3Event]] = {}

    times = sorted(active_notes.keys())

    for i, t in enumerate(times):
        active_pcs = set(active_notes[t].keys())

        if len(active_pcs) < _MIN_PITCHES_FOR_CHORD:
            chord_label = "N"
            confidence = _n_confidence(len(active_pcs), active_notes[t])
        else:
            chord_label, confidence = _match_chord_template(active_pcs)

        low_midi = bass_notes.get(t)
        current_bass_note = ROOT_NOTES[low_midi % 12] if low_midi is not None else None

        if chord_label == prev_chord:
            prev_confidence = max(prev_confidence, confidence)
            if current_bass_note is not None:
                prev_bass_counter[current_bass_note] += 1
            for pc, events in active_notes[t].items():
                if pc not in current_active_notes:
                    current_active_notes[pc] = []
                current_active_notes[pc].extend(events)
            continue

        if prev_chord is not None:
            chord_events.append(_make_chord_event(
                timestamp=round(prev_start, 2),
                chord=prev_chord,
                confidence=round(prev_confidence, 4),
                bass_counter=prev_bass_counter,
                active_notes=current_active_notes,
            ))

        prev_chord = chord_label
        prev_start = t
        prev_confidence = confidence
        prev_bass_counter = Counter()
        current_active_notes = {}
        if current_bass_note is not None and chord_label != "N":
            prev_bass_counter[current_bass_note] += 1
        for pc, events in active_notes[t].items():
            if pc not in current_active_notes:
                current_active_notes[pc] = []
            current_active_notes[pc].extend(events)

    if prev_chord is not None:
        chord_events.append(_make_chord_event(
            timestamp=round(prev_start, 2),
            chord=prev_chord,
            confidence=round(prev_confidence, 4),
            bass_counter=prev_bass_counter,
            active_notes=current_active_notes,
        ))

    if not chord_events:
        chord_events.append(ChordEvent(
            timestamp=0.0,
            chord="N",
            confidence=1.0,
        ))

    return chord_events


def _make_chord_event(
    timestamp: float,
    chord: str,
    confidence: float,
    bass_counter: Counter[str],
    active_notes: dict[int, list[Mt3Event]] | None = None,
) -> ChordEvent:
    """Build a ChordEvent with bass note, inversion, and voicing.

    When active_notes is provided and the chord is a named chord, attempts
    CAGED voicing recognition from the raw MIDI pitch distribution.
    """
    root = chord.split(":")[0] if chord != "N" and ":" in chord else None
    most_common_bass = bass_counter.most_common(1)[0][0] if bass_counter else None

    if most_common_bass is not None and most_common_bass == root:
        final_bass = None
    else:
        final_bass = most_common_bass

    inversion = None
    if final_bass is not None and root is not None and chord != "N" and ":" in chord:
        quality = chord.split(":")[1]
        inversion = _identify_inversion(root, quality, final_bass)

    # Commit B9: CAGED voicing detection from active note pitch distribution
    voicing_shape: str | None = None
    voicing_position: int | None = None
    if active_notes and chord != "N" and ":" in chord and root is not None:
        from app.mt3.voicing_recognizer import recognize_voicing
        quality = chord.split(":")[1]
        result = recognize_voicing(active_notes, root, quality)
        if result.shape and result.confidence >= _VOICING_CONFIDENCE_THRESHOLD:
            voicing_shape = result.shape
            voicing_position = result.position

    return ChordEvent(
        timestamp=timestamp,
        chord=chord,
        confidence=confidence,
        bass=final_bass,
        inversion=inversion,
        voicing_shape=voicing_shape,
        voicing_position=voicing_position,
    )


def _identify_inversion(
    chord_root: str,
    quality: str | None,
    bass_note: str | None,
) -> int | None:
    """Identify chord inversion from bass note relative to chord intervals.

    Args:
        chord_root: Root note name (e.g., 'C', 'F#').
        quality: Chord quality string (e.g., 'maj', 'min7').
        bass_note: Detected bass note name (e.g., 'E', 'G').

    Returns:
        None for root position, 1 for first inversion (bass = 3rd),
        2 for second inversion (bass = 5th), 3 for third inversion (bass = 7th).
    """
    if bass_note is None or quality is None:
        return None
    intervals = CHORD_INTERVALS.get(quality)
    if intervals is None:
        return None
    try:
        root_pc = ROOT_NOTES.index(chord_root)
        bass_pc = ROOT_NOTES.index(bass_note)
    except ValueError:
        return None
    semitone_distance = (bass_pc - root_pc) % 12

    # Map interval positions to inversion numbers
    for position, interval in enumerate(intervals):
        if interval % 12 == semitone_distance:
            if position == 1:
                return 1
            elif position == 2:
                return 2
            elif position == 3:
                return 3
            return None
    return None


def _match_chord_template(
    active_pcs: set[int],
) -> tuple[str, float]:
    """Match a pitch class set against CHORD_INTERVALS.

    Tries each root (C-B) x quality combination, computes Jaccard score
    for selection and pitch set coverage fraction for confidence. Returns
    the best match above _JACCARD_THRESHOLD.

    Confidence is derived from coverage fraction: the proportion of the
    matched template's pitch classes that are present in the active set.
    This gives an intuitive measure of "how complete is this chord."

    Returns:
        Tuple of (chord_label, confidence).
    """
    best_label = "N"
    best_score = 0.0
    best_coverage = 0.0

    for root_idx, root in enumerate(ROOT_NOTES):
        for quality, intervals in CHORD_INTERVALS.items():
            template_pcs = {(root_idx + interval) % 12 for interval in intervals}

            intersection = len(active_pcs & template_pcs)
            union = len(active_pcs | template_pcs)

            if union == 0:
                continue

            jaccard = intersection / union
            coverage = intersection / len(template_pcs) if template_pcs else 0.0

            if jaccard > best_score:
                best_score = jaccard
                best_label = f"{root}:{quality}"
                best_coverage = coverage

    if best_score >= _JACCARD_THRESHOLD:
        mirex_label = _to_mirex(best_label)
        return mirex_label, best_coverage

    return "N", 1.0 - best_score


def _to_mirex(chord_label: str) -> str:
    """Map a 277-class chord label to its nearest 25-class MIREX equivalent.

    If the quality maps to MIREX major or minor, returns the appropriate
    MIREX label. Otherwise returns the original label (N or unclassified).
    """
    if chord_label == "N":
        return "N"

    parts = chord_label.split(":")
    if len(parts) != 2:
        return chord_label

    root, quality = parts
    target_quality = MIREX_QUALITY_MAP.get(quality)
    if target_quality is None:
        return chord_label

    mirex_label = f"{root}:{target_quality}"
    if mirex_label in MIREX_TO_IDX:
        return mirex_label

    return chord_label


def _quantize_to_nearest_beat(time_s: float, beat_times: list[float]) -> float:
    """Snap a timestamp to the nearest beat position.

    Args:
        time_s: The timestamp to quantize (in seconds).
        beat_times: Sorted list of beat positions (in seconds).

    Returns:
        The nearest beat position. If beat_times is empty, returns time_s unchanged.
        If time_s is before the first beat, returns the first beat.
        If time_s is after the last beat, returns the last beat.
    """
    if not beat_times:
        return time_s
    if time_s <= beat_times[0]:
        return beat_times[0]
    if time_s >= beat_times[-1]:
        return beat_times[-1]
    idx = bisect.bisect_left(beat_times, time_s)
    before = beat_times[idx - 1]
    after = beat_times[idx]
    return before if (time_s - before) < (after - time_s) else after


def _n_confidence(
    num_pcs: int,
    active_details: dict[int, list[Mt3Event]],
) -> float:
    """Confidence score for an N (no-chord) prediction.

    Derived from silence certainty: fewer active pitches with lower velocities
    → more confidently N.
    """
    if num_pcs == 0:
        return 1.0

    total_vel = sum(
        e.velocity for events in active_details.values() for e in events
    )
    max_vel = 127 * num_pcs
    velocity_ratio = total_vel / max_vel if max_vel > 0 else 0

    noise_confidence = 1.0 - (num_pcs / 12.0)
    vel_confidence = 1.0 - velocity_ratio
    return float(min(1.0, max(0.0, noise_confidence * 0.6 + vel_confidence * 0.4)))
