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

from collections import defaultdict

import numpy as np

from app.chord_vocab import (CHORD_INTERVALS, MIREX_QUALITY_MAP, MIREX_TO_IDX,
                             MIREX_VOCAB, NUM_CLASSES_MIREX, ROOT_NOTES)
from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.schemas import BeatGrid, ChordEvent, ChordTimeline

# Time slice for chord analysis (0.1s = 10 FPS, matching CQT hop)
_HOP_SECONDS = 0.1

# Minimum Jaccard score to accept a chord match (same threshold as
# Guitar-TECHS and EGSet12 extraction scripts)
_JACCARD_THRESHOLD = 0.66

# Minimum number of simultaneous pitches to consider a chord present
_MIN_PITCHES_FOR_CHORD = 3

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

    active_notes = _build_active_note_grid(
        events, audio_end, prefer_guitar=prefer_guitar_programs,
    )
    chord_events = _infer_chords_from_active_notes(active_notes, audio_end)

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
) -> dict[float, dict[int, list[Mt3Event]]]:
    """Build a time-sliced grid of active (sounding) notes.

    For each 0.1s hop, determine which pitches are actively sounding
    by tracking onsets and offsets across the event stream. Percussion
    (program 128) is always excluded. When prefer_guitar is True and a
    pitch class has events from both guitar-family and non-guitar-family
    programs, only guitar-family events are kept.

    Returns:
        Dict mapping time_slice → {pitch_class: [active_events]}
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

    return grid


def _infer_chords_from_active_notes(
    active_notes: dict[float, dict[int, list[Mt3Event]]],
    audio_end: float,
) -> list[ChordEvent]:
    """Convert active-note grid to chord events via template matching.

    For each time slice, builds a pitch class set from active notes,
    scores all 23 chord templates, and picks the best match above threshold.
    Consecutive slices with the same chord are merged.
    """
    chord_events: list[ChordEvent] = []

    prev_chord: str | None = None
    prev_start: float = 0.0
    prev_confidence: float = 0.0

    times = sorted(active_notes.keys())

    for i, t in enumerate(times):
        active_pcs = set(active_notes[t].keys())

        if len(active_pcs) < _MIN_PITCHES_FOR_CHORD:
            chord_label = "N"
            confidence = _n_confidence(len(active_pcs), active_notes[t])
        else:
            chord_label, confidence = _match_chord_template(active_pcs)

        if chord_label == prev_chord:
            prev_confidence = max(prev_confidence, confidence)
            continue

        if prev_chord is not None:
            chord_events.append(ChordEvent(
                timestamp=round(prev_start, 2),
                chord=prev_chord,
                confidence=round(prev_confidence, 4),
            ))

        prev_chord = chord_label
        prev_start = t
        prev_confidence = confidence

    if prev_chord is not None:
        chord_events.append(ChordEvent(
            timestamp=round(prev_start, 2),
            chord=prev_chord,
            confidence=round(prev_confidence, 4),
        ))

    if not chord_events:
        chord_events.append(ChordEvent(
            timestamp=0.0,
            chord="N",
            confidence=1.0,
        ))

    return chord_events


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
