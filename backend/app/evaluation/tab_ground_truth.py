"""String-aware tablature ground truth for the W4 assignment track.

The W0 loader (:mod:`app.evaluation.ground_truth`) merges GuitarSet/EGSet12
``note_midi`` annotations into one note stream, which is correct for audio
scoring but discards the string index. W4 needs the index: GuitarSet and
EGSet12 store one ``note_midi`` annotation per string with
``annotation_metadata.data_source`` 0-5, where 0 is the low E string and 5
is the high E string.

Fret is derived from the rounded MIDI pitch and the standard open string:
``fret = round(pitch) - open_midi[string]``. Every staged GuitarSet and
EGSet12 note maps to fret 0-24 under standard tuning, so invalid values
fail loudly rather than being silently dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.fretting.tuning import MAX_FRET, NUM_STRINGS, STANDARD_OPEN_MIDI
from app.fretting.types import TabNote


class TabGroundTruthError(ValueError):
    """Raised when a tablature annotation file is missing or malformed."""


def _jams_annotations(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TabGroundTruthError(f"invalid JAMS JSON: {path}: {exc}") from exc
    annotations = payload.get("annotations")
    if not isinstance(annotations, list):
        raise TabGroundTruthError(f"JAMS annotations missing: {path}")
    return annotations


def _string_from_data_source(
    data_source: Any,
    *,
    path: Path,
) -> int:
    try:
        index = int(data_source)
    except (TypeError, ValueError) as exc:
        raise TabGroundTruthError(
            f"{path.name}: note_midi annotation has invalid data_source "
            f"{data_source!r}"
        ) from exc
    if not 0 <= index < NUM_STRINGS:
        raise TabGroundTruthError(
            f"{path.name}: data_source must be 0-{NUM_STRINGS - 1}, "
            f"got {index}"
        )
    # data_source 0 = low E (string 6); 5 = high E (string 1).
    return NUM_STRINGS - index


def load_string_aware_jams(
    path: Path | str,
    *,
    source: str,
) -> list[TabNote]:
    """Load per-string ``note_midi`` annotations from a GuitarSet/EGSet12 JAMS.

    Args:
        path: JAMS file path.
        source: Dataset name used in error messages.

    Raises:
        TabGroundTruthError: malformed annotations, missing string index, or
            a note outside the playable fretboard.
    """
    jams_path = Path(path)
    notes: list[TabNote] = []
    for annotation in _jams_annotations(jams_path):
        if annotation.get("namespace") != "note_midi":
            continue
        metadata = annotation.get("annotation_metadata") or {}
        string = _string_from_data_source(
            metadata.get("data_source"), path=jams_path
        )
        open_pitch = STANDARD_OPEN_MIDI[string - 1]
        for item in annotation.get("data", []) or []:
            try:
                onset = float(item["time"])
                duration = float(item.get("duration", 0.0))
                pitch = int(round(float(item["value"])))
            except (KeyError, TypeError, ValueError) as exc:
                raise TabGroundTruthError(
                    f"{source}/{jams_path.name}: invalid note_midi entry "
                    f"{item!r}"
                ) from exc
            fret = pitch - open_pitch
            if not 0 <= fret <= MAX_FRET:
                raise TabGroundTruthError(
                    f"{source}/{jams_path.name}: note pitch {pitch} on "
                    f"string {string} gives fret {fret}, outside 0-{MAX_FRET}"
                )
            notes.append(
                TabNote(
                    pitch=pitch,
                    onset=onset,
                    offset=onset + max(0.0, duration),
                    velocity=(
                        int(item["velocity"])
                        if item.get("velocity") is not None
                        else None
                    ),
                    string=string,
                    fret=fret,
                )
            )
    if not notes:
        raise TabGroundTruthError(
            f"{source}/{jams_path.name}: no note_midi annotations found"
        )
    return sorted(notes, key=lambda note: (note.onset, note.pitch, note.offset))


def load_guitarset_tab(path: Path | str) -> list[TabNote]:
    """Load string/fret ground truth from a GuitarSet JAMS file."""
    return load_string_aware_jams(path, source="guitarset")


def load_egset12_tab(path: Path | str) -> list[TabNote]:
    """Load string/fret ground truth from an EGSet12 JAMS file."""
    return load_string_aware_jams(path, source="egset12")


#: Guitar-TECHS MIDI uses one instrument per string, named high → low.
_STRING_BY_MIDI_NAME = {
    "e": 1,  # high E
    "B": 2,
    "G": 3,
    "D": 4,
    "A": 5,
    "E": 6,  # low E
}


def load_guitar_techs_tab(path: Path | str) -> list[TabNote]:
    """Load per-string ground truth from a Guitar-TECHS MIDI file.

    The dataset stores one MIDI instrument per plucked string. Files that do
    not contain exactly the six named string tracks are rejected rather than
    guessed at.

    Raises:
        TabGroundTruthError: malformed MIDI, wrong instrument set, or a note
            outside the playable fretboard.
    """
    try:
        import pretty_midi
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise TabGroundTruthError(
            "pretty_midi is required to read Guitar-TECHS MIDI"
        ) from exc

    midi_path = Path(path)
    try:
        midi = pretty_midi.PrettyMIDI(str(midi_path))
    except Exception as exc:  # noqa: BLE001 - surface the real reason
        raise TabGroundTruthError(
            f"could not read Guitar-TECHS MIDI {midi_path}: {exc}"
        ) from exc

    instruments = [
        instrument for instrument in midi.instruments if not instrument.is_drum
    ]
    names = [instrument.name.strip() for instrument in instruments]
    expected = set(_STRING_BY_MIDI_NAME)
    if len(names) != NUM_STRINGS or set(names) != expected:
        raise TabGroundTruthError(
            f"{midi_path.name}: expected six named string tracks "
            f"{sorted(expected)}, got {names}"
        )

    notes: list[TabNote] = []
    for instrument in instruments:
        string = _STRING_BY_MIDI_NAME[instrument.name.strip()]
        open_pitch = STANDARD_OPEN_MIDI[string - 1]
        for note in instrument.notes:
            pitch = int(note.pitch)
            fret = pitch - open_pitch
            if not 0 <= fret <= MAX_FRET:
                raise TabGroundTruthError(
                    f"{midi_path.name}: pitch {pitch} on string {string} "
                    f"gives fret {fret}, outside 0-{MAX_FRET}"
                )
            notes.append(
                TabNote(
                    pitch=pitch,
                    onset=float(note.start),
                    offset=float(note.end),
                    velocity=int(note.velocity),
                    string=string,
                    fret=fret,
                )
            )
    if not notes:
        raise TabGroundTruthError(f"{midi_path.name}: no notes found")
    return sorted(notes, key=lambda note: (note.onset, note.pitch, note.offset))


def load_tab_ground_truth(
    path: Path | str,
    *,
    gt_format: str,
) -> list[TabNote]:
    """Dispatch to the loader for a manifest ``gt_format``."""
    if gt_format == "guitarset_jams":
        return load_guitarset_tab(path)
    if gt_format == "egset12_jams":
        return load_egset12_tab(path)
    if gt_format == "guitar_techs_midi":
        return load_guitar_techs_tab(path)
    raise TabGroundTruthError(
        f"gt_format {gt_format!r} does not carry string/fret annotations"
    )
