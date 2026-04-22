"""Basic Pitch Solo Inference with Grid Quantization (Commit 79)."""

from pathlib import Path
from app.schemas import BeatGrid, SoloNote, SoloNotes

def _snap_to_grid(time_s: float, grid_beats: list[float]) -> float:
    """Finds the closest tick in the beat grid to the given time."""
    if not grid_beats:
        return time_s
    return min(grid_beats, key=lambda b: abs(b - time_s))

def infer_solo(melodic_stem_path: Path, beat_grid: BeatGrid) -> SoloNotes:
    try:
        from basic_pitch.inference import predict
    except ImportError:
        # Graceful fallback for environments without TensorFlow/Basic Pitch
        print("WARNING: basic-pitch not installed. Returning empty solo notes.")
        return SoloNotes(notes=[])

    # Run Basic Pitch
    # Basic pitch returns model_output, midi_data, and note_events
    _, _, raw_note_events = predict(str(melodic_stem_path))
    
    cleaned_notes = []
    grid_beats = beat_grid.beats
    
    # Minimum duration (e.g., if a tick is an 8th note, we don't want 64th notes)
    # We use 50% of the tick_value as the absolute minimum human-playable note
    min_duration_s = (60.0 / beat_grid.bpm) * (beat_grid.tick_value * 0.5)

    for idx, note in enumerate(raw_note_events):
        # raw_note_events format from basic-pitch: 
        # (start_time, end_time, pitch, velocity, pitch_bends)
        start_time, end_time, pitch, velocity, _ = note
        duration = end_time - start_time
        
        # 1. Filter micro-durations (noise)
        if duration < min_duration_s:
            continue
            
        # 2. Quantize to Grid
        q_start = _snap_to_grid(start_time, grid_beats)
        q_end = _snap_to_grid(end_time, grid_beats)
        q_duration = q_end - q_start
        
        # If quantization crushed the note to 0 length, skip it
        if q_duration <= 0:
            continue
            
        # 3. Monophonic Cleanup (Prevent Overlaps)
        # If this note starts before the previous note ended, 
        # truncate the previous note to enforce strict monophony.
        if cleaned_notes and q_start < (cleaned_notes[-1].start_time + cleaned_notes[-1].duration):
            prev_note = cleaned_notes[-1]
            prev_note.duration = q_start - prev_note.start_time
            if prev_note.duration <= 0:
                cleaned_notes.pop() # Remove if it was completely swallowed

        cleaned_notes.append(SoloNote(
            start_time=round(q_start, 3),
            duration=round(q_duration, 3),
            pitch=int(pitch),
            velocity=int(velocity * 127) # Normalize 0-1 to MIDI 0-127
        ))
        
    return SoloNotes(notes=cleaned_notes)