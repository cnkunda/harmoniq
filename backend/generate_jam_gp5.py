#!/usr/bin/env python3
"""
Generate a valid GP5 with actual notes for the jam reference tab.
This fixes the 'Cannot read properties of undefined (reading staves)' AlphaTab error.
"""
import base64
import tempfile
from pathlib import Path

# Import from the backend pipeline
from app.pipeline_proof import NoteEvent, build_gp5_from_note_events

def generate():
    # Create simple note events (A minor pentatonic pattern)
    # These are the same stub events used by the backend tests
    events = [
        NoteEvent(start_s=0.0, end_s=0.25, pitch_midi=64, amplitude=1.0),   # E4
        NoteEvent(start_s=0.5, end_s=0.75, pitch_midi=67, amplitude=1.0),   # G4
        NoteEvent(start_s=1.0, end_s=1.25, pitch_midi=69, amplitude=1.0),    # A4
        NoteEvent(start_s=1.5, end_s=1.75, pitch_midi=72, amplitude=1.0),   # C5
        NoteEvent(start_s=2.0, end_s=2.25, pitch_midi=74, amplitude=1.0),    # D5
    ]
    
    with tempfile.TemporaryDirectory() as td:
        output_path = Path(td) / "jam_reference.gp5"
        
        # Build the GP5 file with pyguitarpro
        build_gp5_from_note_events(
            events,
            bpm=90.0,
            output_gp5=output_path,
            title="Harmoniq jam reference",
            artist="Harmoniq",
        )
        
        # Read and encode to base64
        raw_bytes = output_path.read_bytes()
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        
        print("=" * 70)
        print("COPY THIS STRING INTO src/jam/jamReferenceTabGp5Base64.ts:")
        print("=" * 70)
        print()
        print(f"export const JAM_REFERENCE_TAB_GP5_BASE64 =")
        print(f"  '{b64}'")
        print()
        print(f"File size: {len(raw_bytes)} bytes")
        print(f"Base64 length: {len(b64)} characters")

if __name__ == "__main__":
    generate()