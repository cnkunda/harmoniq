"""Solo Harmony Enrichment — Chord-Tone Classification & Position Inference (Commit 123).

Post-processes raw Basic Pitch solo notes through a harmony analysis layer that:
  1. Labels every note with its role in the current chord (root, 3rd, 5th, tension, chromatic)
  2. Infers the fretboard position (CAGED shape) per bar
  3. Suggests scales for improvisation

Cross-references chord_timeline with solo_notes to produce HarmonizedSoloNotes
and per_bar_analysis (list[BarScope]).

Known limitation: Key estimation uses Krumhansl-Schmuckler which only returns
"major" or "minor". Modal repertoire (Mixolydian, Dorian, etc.) may have inflated
chromatic_pct. A low-effort heuristic (§Modal Heuristic) reclassifies common
modal extensions as tensions to partially mitigate this.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES
from app.guitar_position import OPEN_STRING_MIDI, midi_to_all_guitar_positions
from app.schemas import (
    BarScope,
    BeatGrid,
    ChordEvent,
    ChordToneAnalysis,
    ChordTimeline,
    HarmonizedSoloNote,
    HarmonizedSoloNotes,
    SoloNote,
    SoloNotes,
)

logger = logging.getLogger("harmoniq.solo_harmony")

# ---- Scale patterns (semitone offsets from root) ----

MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]

# ---- Degree names for chord tones and tensions (semitone → label) ----

CHORD_DEGREE_NAMES: dict[int, str] = {
    0: "R", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4",
    6: "b5", 7: "5", 8: "#5", 9: "6", 10: "b7", 11: "7",
}

# ---- Degree numbers (diatonic position within the chord's parent scale) ----
# Maps semitone distance from root → scale degree number (1-7).
# Each degree covers two semitones (natural + altered), e.g.:
#   degree 3 = b3 (semitone 3) or 3 (semitone 4)
#   degree 5 = b5 (semitone 6) or 5 (semitone 7)

CHORD_DEGREE_NUMBERS: dict[int, int] = {
    0: 1,   # root
    1: 2,   # b2
    2: 2,   # 2
    3: 3,   # b3
    4: 3,   # 3
    5: 4,   # 4
    6: 5,   # b5
    7: 5,   # 5
    8: 6,   # #5 / b6
    9: 6,   # 6
    10: 7,  # b7
    11: 7,  # 7
}

# ---- Modal heuristic: pitch classes commonly accepted as tensions in major keys ----
# Addresses the KS diatonic trap where modes get misclassified as major/minor.

MODAL_EXTENSIONS_MAJOR: set[int] = {10, 3, 8}  # b7, b3, b6

# ---- CAGED shapes: canonical fret/string positions relative to shape root ----
# Each shape is a list of (string, fret) pairs.
# The shape root is always at fret 0 on the anchor string.

CAGED_SHAPES: dict[str, list[tuple[int, int]]] = {
    "C": [(5, 0), (4, 2), (3, 2), (2, 1), (1, 0)],
    "A": [(5, 0), (4, 2), (3, 2), (2, 0), (1, 0)],
    "G": [(6, 0), (5, 2), (4, 0), (3, 0), (2, 0), (1, 3)],
    "E": [(6, 0), (5, 2), (4, 2), (3, 1), (2, 0), (1, 0)],
    "D": [(4, 0), (3, 2), (2, 3), (1, 2)],
}

# Anchor string for each shape (string that carries the root at fret 0)

CAGED_ANCHOR_STRING: dict[str, int] = {
    "C": 5, "A": 5, "G": 6, "E": 6, "D": 4,
}


# ---- Helper functions ----


def parse_key_name(key_name: str) -> tuple[int, str]:
    """Parse 'G major' → (7, 'major').

    Returns (key_root_pitch_class, mode_str).
    Handles flat root names (e.g., 'Bb major' → (10, 'major')).
    """
    parts = key_name.strip().split()
    root_str = parts[0]
    mode = parts[1] if len(parts) > 1 else "major"

    # Direct match in ROOT_NOTES
    if root_str in ROOT_NOTES:
        key_root = ROOT_NOTES.index(root_str)
    # Flat alias lookup (e.g., "Bb" → "A#", "Eb" → "D#", "Ab" → "G#")
    elif root_str.endswith("b") and len(root_str) == 2:
        flat_name = root_str[0]
        # Cb=B, Db=C#, Eb=D#, Fb=E, Gb=F#, Ab=G#, Bb=A#
        flat_to_sharp = {"C": "B", "D": "C#", "E": "D#", "F": "E", "G": "F#", "A": "G#", "B": "A#"}
        sharp_name = flat_to_sharp.get(flat_name, "C")
        key_root = ROOT_NOTES.index(sharp_name) if sharp_name in ROOT_NOTES else 0
    else:
        key_root = 0

    return key_root, mode


def build_scale_pitch_classes(key_root: int, mode: str) -> set[int]:
    """Generate the 7 pitch classes for a major or natural minor scale."""
    intervals = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    return {(key_root + i) % 12 for i in intervals}


def parse_chord(chord_label: str) -> tuple[int, str, list[int]] | None:
    """Parse chord label into (root_pitch_class, quality, intervals).

    Returns None for 'N' (no chord) or malformed labels.
    """
    if chord_label == "N" or ":" not in chord_label:
        return None
    root_str, quality = chord_label.split(":", 1)
    if root_str not in ROOT_NOTES:
        return None
    root_idx = ROOT_NOTES.index(root_str)
    intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])
    return root_idx, quality, intervals


def find_active_chord(t: float, events: list[ChordEvent]) -> ChordEvent | None:
    """Return the last ChordEvent whose timestamp <= t, or None."""
    active = None
    for e in events:
        if e.timestamp <= t:
            active = e
        else:
            break
    return active


# ---- ChordToneClassifier ----


class ChordToneClassifier:
    """Classifies a MIDI pitch against the current chord and key.

    Given chord (root, quality) and a MIDI pitch, determines:
    - Whether the pitch is a chord tone, tension, or chromatic passing tone
    - The diatonic scale degree (1-7) or None for chromatic notes
    - A human-readable label (R, 3, 5, b7, etc.)
    - The semitone distance from the chord root (0-11)
    """

    def __init__(self, key_root: int, mode: str) -> None:
        self.key_root = key_root
        self.mode = mode
        self.scale_pcs = build_scale_pitch_classes(key_root, mode)

    def classify(self, pitch: int, chord_label: str) -> ChordToneAnalysis | None:
        """Classify a MIDI pitch against the given chord.

        Returns None when chord_label is 'N' or unparseable.
        """
        parsed = parse_chord(chord_label)
        if parsed is None:
            return None

        root_pc, _quality, intervals = parsed
        note_pc = pitch % 12
        semitone_distance = (note_pc - root_pc) % 12

        # --- Chord tone ---
        if semitone_distance in intervals:
            scale_degree = CHORD_DEGREE_NUMBERS.get(semitone_distance)
            return ChordToneAnalysis(
                scale_degree=scale_degree,
                scale_degree_name=CHORD_DEGREE_NAMES[semitone_distance],
                chord_tone_type="chord_tone",
                semitone_distance=semitone_distance,
            )

        # --- Tension (in scale but not in chord) ---
        if note_pc in self.scale_pcs:
            scale_degree = CHORD_DEGREE_NUMBERS.get(semitone_distance)
            return ChordToneAnalysis(
                scale_degree=scale_degree,
                scale_degree_name=CHORD_DEGREE_NAMES[semitone_distance],
                chord_tone_type="tension",
                semitone_distance=semitone_distance,
            )

        # --- Modal heuristic: reclassify common modal extensions as tensions ---
        # Addresses KS diatonic trap (§16.11.1). When a note is chromatic
        # but matches a common modal extension (b7, b3, b6 in major keys),
        # relabel as tension to avoid inflated chromatic_pct.
        if self.mode == "major" and semitone_distance in MODAL_EXTENSIONS_MAJOR:
            scale_degree = CHORD_DEGREE_NUMBERS.get(semitone_distance)
            return ChordToneAnalysis(
                scale_degree=scale_degree,
                scale_degree_name=CHORD_DEGREE_NAMES[semitone_distance],
                chord_tone_type="tension",
                semitone_distance=semitone_distance,
            )

        # --- Chromatic ---
        return ChordToneAnalysis(
            scale_degree=None,
            scale_degree_name=CHORD_DEGREE_NAMES[semitone_distance],
            chord_tone_type="chromatic",
            semitone_distance=semitone_distance,
        )


# ---- PositionInferenceEngine ----


class PositionInferenceEngine:
    """Infers the CAGED fretboard position for a group of notes in a bar.

    For each of the 5 CAGED shapes of the current chord:
    1. Computes the shape's root fret on the neck
    2. Generates the shape's fret positions on each string
    3. Checks which played notes are reachable within a 5-fret span
    4. Scores: hit_rate × (1.0 - 0.1 × max(0, span - 4))

    Winner → label like "position 2 (CAGED: E-form)".
    """

    MAX_SPAN = 4  # Penalty starts at span > 4 (§16.11.5)

    def __init__(self, chord_root_pc: int) -> None:
        self.chord_root_pc = chord_root_pc

    def _shape_root_fret(self, shape_name: str) -> int:
        """Compute the fret where this shape's root sits on the neck.

        Example: A-form (root on 5th string) for C chord (root_pc=0):
        fret = (0 - OPEN_STRING_MIDI[5] % 12) % 12 = (0 - 5) % 12 = 7
        """
        anchor = CAGED_ANCHOR_STRING[shape_name]
        open_pc = OPEN_STRING_MIDI[anchor] % 12
        return (self.chord_root_pc - open_pc) % 12

    def _shape_positions(self, shape_name: str, root_fret: int) -> list[tuple[int, int]]:
        """Generate (string, fret) positions for this shape at the given root fret."""
        return [
            (s, f + root_fret) for s, f in CAGED_SHAPES[shape_name]
        ]

    def _shape_fret_range(self, positions: list[tuple[int, int]]) -> tuple[int, int]:
        """Return (min_fret, max_fret) for a shape's positions."""
        frets = [f for _, f in positions]
        return min(frets), max(frets)

    def score_shape(
        self,
        shape_name: str,
        bar_notes: list[SoloNote],
    ) -> tuple[float, str | None]:
        """Score how well this CAGED shape fits the bar's notes.

        Returns (score, position_label). Score ∈ [0, 1].
        """
        root_fret = self._shape_root_fret(shape_name)
        shape_pos = self._shape_positions(shape_name, root_fret)
        shape_min, shape_max = self._shape_fret_range(shape_pos)

        # Build lookup: string → set of frets in this shape
        shape_by_string: dict[int, set[int]] = defaultdict(set)
        for s, f in shape_pos:
            shape_by_string[s].add(f)

        # Check which notes fit within the shape's fret range + 1 fret buffer
        # This allows notes just outside the canonical shape (common in real playing)
        fret_lo = shape_min - 1
        fret_hi = shape_max + 1

        hits = 0
        note_frets: list[int] = []

        for note in bar_notes:
            positions = midi_to_all_guitar_positions(note.pitch)
            if not positions:
                continue  # Skip out-of-bounds MIDI (§16.11.6)

            # Check if any position of this note falls within the shape's range
            # and on a string used by this shape
            note_hit = False
            for pos in positions:
                if pos.string in shape_by_string and fret_lo <= pos.fret <= fret_hi:
                    note_hit = True
                    note_frets.append(pos.fret)
                    break

            if note_hit:
                hits += 1

        if not bar_notes:
            return 0.0, None

        hit_rate = hits / len(bar_notes)

        # Span penalty (§16.11.5): 5-fret window with stretch penalty
        if note_frets:
            span = max(note_frets) - min(note_frets) + 1
            stretch_penalty = max(0.0, 0.1 * (span - self.MAX_SPAN))
        else:
            span = 0
            stretch_penalty = 0.0

        score = hit_rate * (1.0 - stretch_penalty)

        # Generate label only if we have a meaningful score
        if hit_rate > 0:
            label = f"position {root_fret + 1} (CAGED: {shape_name}-form)"
        else:
            label = None

        return score, label

    def infer_position(self, bar_notes: list[SoloNote]) -> str | None:
        """Find the best CAGED position for a group of notes.

        Returns the position label or None if no shape fits.
        """
        best_score = 0.0
        best_label: str | None = None

        for shape_name in CAGED_SHAPES:
            score, label = self.score_shape(shape_name, bar_notes)
            if score > best_score:
                best_score = score
                best_label = label

        return best_label


# ---- SoloHarmonizer ----


class SoloHarmonizer:
    """Orchestrator — cross-references chord_timeline with solo_notes.

    Produces:
    - harmonized_solo: HarmonizedSoloNotes (per-note chord context + aggregate %)
    - per_bar_analysis: list[BarScope] (per-bar position inference + suggested scales)
    """

    def __init__(
        self,
        chord_timeline: ChordTimeline,
        solo_notes: SoloNotes,
        beat_grid: BeatGrid,
        key_name: str,
    ) -> None:
        self.chord_timeline = chord_timeline
        self.solo_notes = solo_notes
        self.beat_grid = beat_grid

        # Parse key
        self.key_root, self.mode = parse_key_name(key_name)
        self.key_name = key_name

        # Build chord-tone classifier
        self.classifier = ChordToneClassifier(self.key_root, self.mode)

        # Run analysis
        self.harmonized_solo = self._analyze_notes()
        self.per_bar_analysis = self._analyze_bars()

    def _analyze_notes(self) -> HarmonizedSoloNotes:
        """Classify each solo note against the active chord."""
        events = self.chord_timeline.events
        harmonized: list[HarmonizedSoloNote] = []

        for note in self.solo_notes.notes:
            active = find_active_chord(note.start_time, events)

            if active is None or active.chord == "N":
                harmonized.append(HarmonizedSoloNote(
                    start_time=note.start_time,
                    duration=note.duration,
                    pitch=note.pitch,
                    velocity=note.velocity,
                    chord=None,
                    chord_analysis=None,
                ))
                continue

            chord_analysis = self.classifier.classify(note.pitch, active.chord)

            harmonized.append(HarmonizedSoloNote(
                start_time=note.start_time,
                duration=note.duration,
                pitch=note.pitch,
                velocity=note.velocity,
                chord=active.chord,
                chord_analysis=chord_analysis,
            ))

        # Aggregate percentages (§16.11.4): computed from notes with chord context only
        analyzed = [n for n in harmonized if n.chord_analysis is not None]
        total_analyzed = len(analyzed)

        if total_analyzed > 0:
            chord_tones = sum(
                1 for n in analyzed
                if n.chord_analysis.chord_tone_type == "chord_tone"
            )
            tensions = sum(
                1 for n in analyzed
                if n.chord_analysis.chord_tone_type == "tension"
            )
            chromatic = sum(
                1 for n in analyzed
                if n.chord_analysis.chord_tone_type == "chromatic"
            )
            chord_tone_pct = round(chord_tones / total_analyzed, 4)
            tension_note_pct = round(tensions / total_analyzed, 4)
            chromatic_pct = round(chromatic / total_analyzed, 4)
        else:
            chord_tone_pct = 0.0
            tension_note_pct = 0.0
            chromatic_pct = 0.0

        return HarmonizedSoloNotes(
            notes=harmonized,
            note_count=len(harmonized),
            chord_tone_pct=chord_tone_pct,
            tension_note_pct=tension_note_pct,
            chromatic_pct=chromatic_pct,
        )

    def _get_bar_boundaries(self) -> list[tuple[float, float]]:
        """Get bar (start, end) time pairs from beat_grid.downbeats."""
        downbeats = self.beat_grid.downbeats
        if len(downbeats) < 2:
            # Fallback: use beat_grid.beats as bar boundaries (1 beat = 1 bar)
            beats = self.beat_grid.beats
            if len(beats) < 2:
                return []
            boundaries = [(beats[i], beats[i + 1]) for i in range(len(beats) - 1)]
            return boundaries

        boundaries = [
            (downbeats[i], downbeats[i + 1])
            for i in range(len(downbeats) - 1)
        ]
        return boundaries

    def _notes_in_bar(
        self,
        bar_start: float,
        bar_end: float,
        harmonized_notes: list[HarmonizedSoloNote],
    ) -> list[tuple[int, HarmonizedSoloNote]]:
        """Return (global_index, note) pairs for notes within a bar's time range."""
        result: list[tuple[int, HarmonizedSoloNote]] = []
        for i, note in enumerate(harmonized_notes):
            if bar_start <= note.start_time < bar_end:
                result.append((i, note))
        return result

    def _suggest_scales(self, chord_label: str | None) -> list[str]:
        """Suggest 1-2 scale names for improvisation over this bar.

        Uses the key and chord to suggest appropriate scales.
        """
        if chord_label is None:
            return []

        key_str = f"{ROOT_NOTES[self.key_root]} {'major' if self.mode == 'major' else 'minor'}"

        parsed = parse_chord(chord_label)
        if parsed is None:
            return [key_str]

        root_pc, quality, _intervals = parsed
        root_name = ROOT_NOTES[root_pc]

        scales: list[str] = []

        # Primary: pentatonic in the key
        if self.mode == "major":
            scales.append(f"{ROOT_NOTES[self.key_root]} major pentatonic")
        else:
            scales.append(f"{ROOT_NOTES[self.key_root]} minor pentatonic")

        # Secondary: chord-specific scale hint
        if quality in ("maj", "maj7", "maj9"):
            scales.append(f"{root_name} lydian")
        elif quality in ("7", "9", "13", "7#9", "7b9"):
            scales.append(f"{root_name} mixolydian")
        elif quality in ("min", "min7", "min9"):
            scales.append(f"{root_name} dorian")
        elif quality in ("dim", "dim7"):
            scales.append(f"{root_name} locrian")
        elif quality in ("aug",):
            scales.append(f"{root_name} lydian augmented")

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for s in scales:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return unique[:2]

    def _analyze_bars(self) -> list[BarScope]:
        """Per-bar analysis: dominant chord, position inference, suggested scales."""
        bar_boundaries = self._get_bar_boundaries()
        if not bar_boundaries:
            return []

        harmonized_notes = self.harmonized_solo.notes
        bars: list[BarScope] = []

        for bar_idx, (bar_start, bar_end) in enumerate(bar_boundaries):
            bar_notes_info = self._notes_in_bar(bar_start, bar_end, harmonized_notes)

            # Collect note indices and SoloNote objects for position inference
            note_indices = [idx for idx, _ in bar_notes_info]
            bar_solo_notes = [
                SoloNote(
                    start_time=n.start_time,
                    duration=n.duration,
                    pitch=n.pitch,
                    velocity=n.velocity,
                )
                for _, n in bar_notes_info
            ]

            # Find dominant chord in this bar (most common non-N chord)
            chord_counts: dict[str, int] = defaultdict(int)
            for _, hn in bar_notes_info:
                if hn.chord is not None:
                    chord_counts[hn.chord] += 1

            dominant_chord: str | None = None
            if chord_counts:
                dominant_chord = max(chord_counts, key=chord_counts.get)  # type: ignore[arg-type]

            # Position inference (only if we have notes)
            primary_position: str | None = None
            if bar_solo_notes and dominant_chord is not None:
                parsed = parse_chord(dominant_chord)
                if parsed is not None:
                    engine = PositionInferenceEngine(parsed[0])
                    primary_position = engine.infer_position(bar_solo_notes)

            # Suggested scales
            suggested_scales = self._suggest_scales(dominant_chord)

            bars.append(BarScope(
                bar_index=bar_idx,
                start_time=bar_start,
                end_time=bar_end,
                chord=dominant_chord,
                suggested_scales=suggested_scales,
                primary_position=primary_position,
                notes=note_indices,
            ))

        return bars
