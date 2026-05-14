"""
Guitar position utilities - convert MIDI pitch to guitar string/fret positions.

Standard guitar tuning (6 strings, 24 frets):
- String 6 (low E): MIDI 40
- String 5 (A): MIDI 45
- String 4 (D): MIDI 50
- String 3 (G): MIDI 55
- String 2 (B): MIDI 59
- String 1 (high E): MIDI 64
"""

from __future__ import annotations

from dataclasses import dataclass


OPEN_STRING_MIDI = {
    6: 40,   # E2
    5: 45,   # A2
    4: 50,   # D3
    3: 55,   # G3
    2: 59,   # B3
    1: 64,   # E4
}

MAX_FRET = 24


@dataclass
class GuitarPosition:
    """Represents a position on the guitar fretboard."""
    string: int  # 1-6 (1 = high E, 6 = low E)
    fret: int    # 0-24
    midi: int    # The original MIDI pitch
    
    @property
    def fret_string(self) -> str:
        """Returns fret number as string for display."""
        return str(self.fret)


def midi_to_guitar_position(midi: int) -> GuitarPosition:
    """
    Convert a MIDI note number to the lowest (easiest) guitar position.
    
    Args:
        midi: MIDI note number (0-127)
        
    Returns:
        GuitarPosition with the lowest fret position on the lowest string possible
        
    Raises:
        ValueError: If MIDI note is outside playable guitar range (E2=40 to E6=84)
    """
    if midi < 40:
        raise ValueError(f"MIDI {midi} is below playable range (lowest guitar note is E2=40)")
    if midi > 64 + MAX_FRET:
        raise ValueError(f"MIDI {midi} is above playable range (highest guitar note is E6={64 + MAX_FRET})")
    
    # Find the position with the LOWEST FRET (easiest to play)
    # Tie-break: prefer lower string (closer to bass) when same fret
    all_positions = midi_to_all_guitar_positions(midi)
    if not all_positions:
        raise ValueError(f"Could not find valid position for MIDI {midi}")
    
    # all_positions is already sorted by (fret, string) ascending
    # But we want to prefer lower-pitched strings (higher string number) on ties
    # Re-sort: lowest fret first, then highest string number (= lower-pitched string)
    all_positions.sort(key=lambda p: (p.fret, -p.string))
    return all_positions[0]


def midi_to_all_guitar_positions(midi: int) -> list[GuitarPosition]:
    """
    Get all valid guitar positions for a given MIDI note.
    
    Args:
        midi: MIDI note number (0-127)
        
    Returns:
        List of all valid GuitarPositions, sorted by fret (lowest first)
    """
    if midi < 40 or midi > 64 + MAX_FRET:
        return []
    
    positions = []
    for string in range(1, 7):  # 1 to 6
        open_midi = OPEN_STRING_MIDI[string]
        if midi >= open_midi:
            fret = midi - open_midi
            if fret <= MAX_FRET:
                positions.append(GuitarPosition(string=string, fret=fret, midi=midi))
    
    # Sort by fret, then by string (lower strings preferred when same fret)
    positions.sort(key=lambda p: (p.fret, p.string))
    return positions


def guitar_position_to_midi(string: int, fret: int) -> int:
    """
    Convert guitar string and fret to MIDI note number.
    
    Args:
        string: Guitar string (1-6, 1 = high E)
        fret: Fret number (0-24)
        
    Returns:
        MIDI note number
        
    Raises:
        ValueError: If string or fret is out of range
    """
    if string < 1 or string > 6:
        raise ValueError(f"Invalid string {string}, must be 1-6")
    if fret < 0 or fret > MAX_FRET:
        raise ValueError(f"Invalid fret {fret}, must be 0-24")
    
    return OPEN_STRING_MIDI[string] + fret


def get_string_name(string: int) -> str:
    """Get the standard name for a guitar string."""
    names = {
        1: "high E",
        2: "B",
        3: "G",
        4: "D",
        5: "A",
        6: "low E",
    }
    return names.get(string, f"String {string}")