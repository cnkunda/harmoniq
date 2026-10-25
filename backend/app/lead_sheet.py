"""Lead-sheet generation from a MIDI melody plus raw lyric text (Commit 177).

The commit deliberately keeps ingestion narrow:

- MIDI must use a single quarter-note-based time signature and a single tempo.
- Lyrics are split on whitespace and explicit hyphens. No automatic
  syllabification is attempted.
- Chord symbols are supplied by the caller (analysis or manual input); this
  module does not infer harmony from the MIDI notes.
"""

from __future__ import annotations

import io
import logging
import re
import statistics

import pretty_midi

from app.musicxml_builder import build_musicxml
from app.schemas import BeatGrid, ChordTimeline, SoloNote, SoloNotes, TimeSignature

logger = logging.getLogger("harmoniq.lead_sheet")

_HYPHEN_SPLIT = re.compile(r"-+")


class LeadSheetInputError(ValueError):
    """Raised when MIDI or lyric input cannot produce a lead sheet."""


def tokenize_lyrics(raw: str) -> list[str]:
    """Split raw lyrics into MusicXML-ready syllable tokens.

    Whitespace separates words. Explicit hyphens split a word into syllables;
    the returned tokens carry the leading/trailing hyphens that music21 uses to
    derive ``begin`` / ``middle`` / ``end`` syllabic values.

    Examples:
        >>> tokenize_lyrics("Hel-lo world")
        ['Hel-', '-lo', 'world']
        >>> tokenize_lyrics("hap-py-ness")
        ['hap-', '-py-', '-ness']
    """
    if not raw or not raw.strip():
        return []

    tokens: list[str] = []
    for word in raw.split():
        if not word.strip("-"):
            continue
        if word.startswith("-") or word.endswith("-"):
            tokens.append(word)
            continue
        parts = [part for part in _HYPHEN_SPLIT.split(word) if part]
        if len(parts) == 1:
            tokens.append(parts[0])
            continue
        last = len(parts) - 1
        for index, part in enumerate(parts):
            prefix = "-" if index > 0 else ""
            suffix = "-" if index < last else ""
            tokens.append(f"{prefix}{part}{suffix}")
    return tokens


def _parse_midi(midi_bytes: bytes) -> pretty_midi.PrettyMIDI:
    if not midi_bytes:
        raise LeadSheetInputError("MIDI payload is empty.")
    try:
        return pretty_midi.PrettyMIDI(io.BytesIO(midi_bytes))
    except Exception as exc:
        raise LeadSheetInputError(f"Could not parse MIDI file: {exc}") from exc


def _select_melody_instrument(
    midi: pretty_midi.PrettyMIDI,
    melody_track_index: int | None,
) -> pretty_midi.Instrument:
    if melody_track_index is not None:
        if melody_track_index < 0 or melody_track_index >= len(midi.instruments):
            raise LeadSheetInputError(
                f"melody_track_index={melody_track_index} is out of range "
                f"(MIDI has {len(midi.instruments)} tracks)."
            )
        instrument = midi.instruments[melody_track_index]
        if instrument.is_drum:
            raise LeadSheetInputError(
                f"Track {melody_track_index} is a drum track and cannot provide a melody."
            )
        if not instrument.notes:
            raise LeadSheetInputError(
                f"Track {melody_track_index} contains no notes."
            )
        return instrument

    candidates = [
        instrument
        for instrument in midi.instruments
        if not instrument.is_drum and instrument.notes
    ]
    if not candidates:
        raise LeadSheetInputError("MIDI contains no non-drum track with melody notes.")

    # Highest median pitch is a predictable approximation of the top-line
    # melody when no track index is supplied. Callers can override it.
    return max(
        candidates,
        key=lambda instrument: (
            statistics.median(note.pitch for note in instrument.notes),
            len(instrument.notes),
        ),
    )


def _melody_notes(instrument: pretty_midi.Instrument) -> list[SoloNote]:
    """Collapse polyphonic material to the highest note at each onset."""
    by_onset: dict[float, pretty_midi.Note] = {}
    for note in instrument.notes:
        onset = round(float(note.start), 6)
        current = by_onset.get(onset)
        if current is None or note.pitch > current.pitch:
            by_onset[onset] = note

    if not by_onset:
        raise LeadSheetInputError("Selected melody track contains no notes.")

    notes: list[SoloNote] = []
    for onset in sorted(by_onset):
        note = by_onset[onset]
        duration = max(float(note.end) - float(note.start), 1e-3)
        notes.append(
            SoloNote(
                start_time=float(note.start),
                duration=duration,
                pitch=int(note.pitch),
                velocity=max(1, min(127, int(note.velocity))),
                confidence=1.0,
            )
        )
    return notes


def _build_beat_grid(
    midi: pretty_midi.PrettyMIDI,
    notes: list[SoloNote],
) -> BeatGrid:
    _, tempos = midi.get_tempo_changes()
    distinct_tempos = {round(float(tempo), 6) for tempo in tempos}
    if len(distinct_tempos) > 1:
        raise LeadSheetInputError(
            "MIDI tempo changes are not supported for lead-sheet generation; "
            "bounce the MIDI with a single tempo first."
        )
    bpm = float(tempos[0]) if len(tempos) else 120.0

    time_signatures = midi.time_signature_changes
    distinct_meters = {
        (int(signature.numerator), int(signature.denominator))
        for signature in time_signatures
    }
    if len(distinct_meters) > 1:
        raise LeadSheetInputError(
            "MIDI time-signature changes are not supported for lead-sheet generation."
        )
    if time_signatures:
        numerator = int(time_signatures[0].numerator)
        denominator = int(time_signatures[0].denominator)
    else:
        numerator, denominator = 4, 4

    if denominator != 4:
        raise LeadSheetInputError(
            f"Time signature {numerator}/{denominator} is not supported; "
            "lead-sheet generation currently requires a quarter-note denominator."
        )
    if not 20.0 <= bpm <= 900.0:
        raise LeadSheetInputError(f"MIDI tempo {bpm:g} BPM is outside the supported range.")

    quarter_note_s = 60.0 / bpm
    measure_s = quarter_note_s * numerator
    last_note_end = max(note.start_time + note.duration for note in notes)

    beats = [float(beat) for beat in midi.get_beats()]
    if not beats:
        beats = [0.0]
    if beats[0] > 0.0:
        beats.insert(0, 0.0)

    downbeats = [float(beat) for beat in midi.get_downbeats()]
    if not downbeats:
        downbeats = [0.0]
    if downbeats[0] > 0.0:
        downbeats.insert(0, 0.0)

    while downbeats[-1] < last_note_end - 1e-6:
        downbeats.append(downbeats[-1] + measure_s)
    if len(downbeats) == 1:
        downbeats.append(downbeats[0] + measure_s)

    while beats[-1] < downbeats[-1] - 1e-6:
        beats.append(beats[-1] + quarter_note_s)

    return BeatGrid(
        bpm=bpm,
        pulse_bpm=max(20.0, min(300.0, bpm)),
        beats=beats,
        downbeats=downbeats,
        time_signature=TimeSignature(numerator=numerator, denominator=denominator),
        tick_value=1.0 / denominator,
        tempo_changes=[],
    )


def build_lead_sheet_from_midi(
    midi_bytes: bytes,
    lyrics: str,
    *,
    chord_timeline: ChordTimeline | None = None,
    title: str = "Harmoniq Lead Sheet",
    artist: str = "Harmoniq AI",
    key_signature: str | None = None,
    melody_track_index: int | None = None,
) -> str:
    """Build a lead-sheet MusicXML document from MIDI bytes and raw lyrics.

    Lyrics are assigned to melody notes in onset order, one syllable per note.
    Extra melody notes remain instrumental. More syllables than notes is an
    error rather than a silent truncation.

    Raises:
        LeadSheetInputError: malformed MIDI, no usable melody, unsupported
            tempo/meter changes, or more lyric syllables than melody notes.
    """
    midi = _parse_midi(midi_bytes)
    instrument = _select_melody_instrument(midi, melody_track_index)
    notes = _melody_notes(instrument)
    beat_grid = _build_beat_grid(midi, notes)
    syllables = tokenize_lyrics(lyrics)

    if len(syllables) > len(notes):
        raise LeadSheetInputError(
            f"Lyrics contain {len(syllables)} syllables but the MIDI melody has "
            f"{len(notes)} notes."
        )

    logger.info(
        "lead_sheet: track=%s notes=%d syllables=%d bpm=%.1f meter=%d/4",
        instrument.name or instrument.program,
        len(notes),
        len(syllables),
        beat_grid.bpm,
        beat_grid.time_signature.numerator,
    )

    return build_musicxml(
        beat_grid=beat_grid,
        chord_timeline=chord_timeline or ChordTimeline(events=[]),
        solo_notes=SoloNotes(notes=notes),
        title=title,
        artist=artist,
        key_signature=key_signature,
        lyrics=syllables or None,
        layout="lead_sheet",
    )
