"""Basic Pitch Solo Inference with Grid Quantization (Commit 79)."""

import bisect
from pathlib import Path
from app.schemas import BeatGrid, SoloNote, SoloNotes

def _snap_to_grid(time_s: float, grid_beats: list[float]) -> float:
    """Finds the closest tick in the beat grid to the given time."""
    if not grid_beats:
        return time_s
    idx = bisect.bisect_left(grid_beats, time_s)
    if idx == 0:
        return grid_beats[0]
    if idx == len(grid_beats):
        return grid_beats[-1]
    # Check if the time is closer to the current index or the previous one
    before = grid_beats[idx - 1]
    after = grid_beats[idx]
    return before if abs(time_s - before) < abs(time_s - after) else after

def infer_solo(melodic_stem_path: Path, beat_grid: BeatGrid) -> SoloNotes:
    try:
        from basic_pitch.inference import predict
    except ImportError:
        # Graceful fallback for environments without TensorFlow/Basic Pitch
        print("WARNING: basic-pitch not installed. Returning empty solo notes.")
        return SoloNotes(notes=[])

    # Minimum duration (e.g., if a tick is an 8th note, we don't want 64th notes)
    # We use 50% of the tick_value as the absolute minimum human-playable note
    min_duration_s = (60.0 / beat_grid.bpm) * (beat_grid.tick_value * 0.5)

    # Run Basic Pitch with internal filtering to reduce noise at the source
    # onset_threshold: confidence required to detect a new note (higher = fewer ghost notes)
    # frame_threshold: confidence to keep a note continuing
    # minimum_note_length: minimum duration in ms (Basic Pitch expects milliseconds)
    _, _, raw_note_events = predict(
        str(melodic_stem_path),
        onset_threshold=0.6,
        frame_threshold=0.4,
        minimum_note_length=min_duration_s * 1000
    )

    # First pass: collect all valid notes for velocity normalization
    # Basic Pitch velocity is conservative (0.3-0.6 range), so we apply
    # dynamic range compression to make the loudest note hit professional levels (120+)
    MIN_MIDI_VELOCITY = 40  # Quietest audible note
    MAX_MIDI_VELOCITY = 120  # Loudest note (headroom for 127)

    raw_notes = []
    for note in raw_note_events:
        start_time, end_time, pitch, velocity, _ = note
        duration = end_time - start_time

        # Filter micro-durations (noise)
        if duration < min_duration_s:
            continue

        raw_notes.append((start_time, end_time, pitch, velocity))

    if not raw_notes:
        return SoloNotes(notes=[])

    # Find max velocity for dynamic range compression
    max_input_velocity = max(n[3] for n in raw_notes)
    # Avoid division by zero; if all velocities are 0, default to 0.5
    if max_input_velocity < 0.01:
        max_input_velocity = 0.5

    # Calculate velocity scaling factor to map max to MAX_MIDI_VELOCITY
    # while keeping relative dynamics and ensuring minimum audible velocity
    velocity_range = MAX_MIDI_VELOCITY - MIN_MIDI_VELOCITY

    cleaned_notes = []
    grid_beats = beat_grid.beats
    LEGATO_OVERLAP_S = 0.010

    for start_time, end_time, pitch, velocity in raw_notes:
        duration = end_time - start_time

        # Quantize to Grid
        q_start = _snap_to_grid(start_time, grid_beats)
        q_end = _snap_to_grid(end_time, grid_beats)
        q_duration = q_end - q_start

        # If quantization crushed the note to 0 length, give it minimum duration
        if q_duration <= 0:
            q_duration = (60.0 / beat_grid.bpm) * beat_grid.tick_value

        # Monophonic Cleanup (Prevent Overlaps) with legato feel
        if cleaned_notes and q_start < (cleaned_notes[-1].start_time + cleaned_notes[-1].duration):
            prev_note = cleaned_notes[-1]
            prev_note.duration = q_start - prev_note.start_time + LEGATO_OVERLAP_S
            if prev_note.duration <= 0:
                cleaned_notes.pop()

        # Dynamic range compression: normalize velocity relative to max in this solo
        normalized_velocity = (velocity / max_input_velocity) * velocity_range + MIN_MIDI_VELOCITY
        midi_velocity = int(max(MIN_MIDI_VELOCITY, min(MAX_MIDI_VELOCITY, normalized_velocity)))

        cleaned_notes.append(SoloNote(
            start_time=round(q_start, 3),
            duration=round(q_duration, 3),
            pitch=int(pitch),
            velocity=midi_velocity
        ))

    return SoloNotes(notes=cleaned_notes)