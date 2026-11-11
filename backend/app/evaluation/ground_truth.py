"""Ground-truth loaders for the W0 evaluation harness.

The loaders are deliberately dependency-light: JAMS files are plain JSON
and are read with the standard library (``jams`` is not declared in the
backend dependencies). MIDI files use ``pretty_midi``, which is already a
project dependency.

Only the annotation shapes used by the bundled datasets are supported.
Unknown formats fail loudly instead of producing empty metrics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.evaluation.manifest import TrackSpec


class GroundTruthError(ValueError):
    """Raised when a ground-truth file is missing or malformed."""


@dataclass(frozen=True)
class GTNote:
    """A reference note. ``offset`` is an absolute time in seconds."""

    pitch: int
    onset: float
    offset: float
    velocity: int | None = None
    program: int | None = None
    confidence: float | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.offset - self.onset)


@dataclass(frozen=True)
class GTChord:
    """A chord interval (reference or predicted)."""

    start: float
    end: float
    chord: str
    confidence: float | None = None


@dataclass
class GroundTruth:
    """All reference annotations for one track."""

    notes: list[GTNote] = field(default_factory=list)
    chords: list[GTChord] = field(default_factory=list)
    source: str = "unknown"

    @property
    def has_notes(self) -> bool:
        return bool(self.notes)

    @property
    def has_chords(self) -> bool:
        return bool(self.chords)


def _round_pitch(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise GroundTruthError(f"invalid pitch value: {value!r}") from exc


def _jams_annotations(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GroundTruthError(f"invalid JAMS JSON: {path}: {exc}") from exc
    annotations = payload.get("annotations")
    if not isinstance(annotations, list):
        raise GroundTruthError(f"JAMS annotations missing: {path}")
    return annotations


def load_jams_notes(path: Path, *, program: int | None = None) -> list[GTNote]:
    """Merge every ``note_midi`` annotation into one note list.

    GuitarSet and EGSet12 store one annotation per string; the merge is
    intentional because the evaluator scores the mixture, not per-string
    streams.
    """
    notes: list[GTNote] = []
    for ann in _jams_annotations(path):
        if ann.get("namespace") != "note_midi":
            continue
        for item in ann.get("data", []) or []:
            try:
                onset = float(item["time"])
                duration = float(item.get("duration", 0.0))
            except (KeyError, TypeError, ValueError) as exc:
                raise GroundTruthError(
                    f"invalid note_midi entry in {path}: {item!r}"
                ) from exc
            notes.append(
                GTNote(
                    pitch=_round_pitch(item.get("value")),
                    onset=onset,
                    offset=onset + max(0.0, duration),
                    velocity=(
                        int(item["velocity"])
                        if item.get("velocity") is not None
                        else None
                    ),
                    program=program,
                    confidence=(
                        float(item["confidence"])
                        if item.get("confidence") is not None
                        else None
                    ),
                )
            )
    return sorted(notes, key=lambda n: (n.onset, n.pitch, n.offset))


def load_timeline_chords(path: Path) -> list[GTChord]:
    """Load a processed Harmoniq chord timeline (``[{start,end,chord}]``)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GroundTruthError(f"invalid timeline JSON: {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise GroundTruthError(f"timeline must be a JSON list: {path}")
    chords: list[GTChord] = []
    for item in payload:
        if not isinstance(item, dict):
            raise GroundTruthError(f"timeline entry must be an object: {item!r}")
        try:
            start = float(item["start"])
            end = float(item["end"])
            label = str(item["chord"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GroundTruthError(
                f"invalid timeline entry in {path}: {item!r}"
            ) from exc
        if end <= start:
            continue
        chords.append(GTChord(start=start, end=end, chord=label))
    return sorted(chords, key=lambda c: (c.start, c.end, c.chord))


def load_jams_chords(path: Path) -> list[GTChord]:
    """Load chord annotations directly from JAMS (fallback when no timeline)."""
    annotations = [
        ann for ann in _jams_annotations(path) if ann.get("namespace") == "chord"
    ]
    if not annotations:
        return []
    # Prefer the first chord annotation, matching parse_guitarset.py.
    chords: list[GTChord] = []
    for item in annotations[0].get("data", []) or []:
        try:
            start = float(item["time"])
            end = start + float(item.get("duration", 0.0))
            label = str(item["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GroundTruthError(
                f"invalid chord entry in {path}: {item!r}"
            ) from exc
        if end <= start:
            continue
        chords.append(GTChord(start=start, end=end, chord=label))
    return sorted(chords, key=lambda c: (c.start, c.end, c.chord))


def load_midi_notes(path: Path, *, program_override: int | None = None) -> list[GTNote]:
    """Load notes from a MIDI file, merging all tracks."""
    try:
        import pretty_midi
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise GroundTruthError(
            "pretty_midi is required to read MIDI ground truth"
        ) from exc

    try:
        midi = pretty_midi.PrettyMIDI(str(path))
    except Exception as exc:
        raise GroundTruthError(f"could not read MIDI {path}: {exc}") from exc

    notes: list[GTNote] = []
    for instrument in midi.instruments:
        if instrument.is_drum:
            continue
        program = (
            program_override
            if program_override is not None
            else int(instrument.program)
        )
        for note in instrument.notes:
            notes.append(
                GTNote(
                    pitch=int(note.pitch),
                    onset=float(note.start),
                    offset=float(note.end),
                    velocity=int(note.velocity),
                    program=program,
                )
            )
    return sorted(notes, key=lambda n: (n.onset, n.pitch, n.offset))


def load_notes_json(path: Path) -> list[GTNote]:
    """Load a generic note list.

    Accepted keys: ``pitch``/``midi``, ``onset``/``start``/``start_time``,
    ``offset``/``end``/``end_time`` and optional ``duration``. This keeps
    external predictions importable without a bespoke converter.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GroundTruthError(f"invalid notes JSON: {path}: {exc}") from exc

    if isinstance(payload, dict):
        payload = payload.get("notes", [])
    if not isinstance(payload, list):
        raise GroundTruthError(f"notes JSON must be a list: {path}")

    notes: list[GTNote] = []
    for item in payload:
        if not isinstance(item, dict):
            raise GroundTruthError(f"note entry must be an object: {item!r}")
        pitch_value = item.get("pitch", item.get("midi"))
        onset_value = item.get("onset", item.get("start", item.get("start_time")))
        offset_value = item.get("offset", item.get("end", item.get("end_time")))
        if onset_value is None:
            raise GroundTruthError(f"note entry missing onset: {item!r}")
        onset = float(onset_value)
        if offset_value is None:
            offset = onset + float(item.get("duration", 0.0))
        else:
            offset = float(offset_value)
        notes.append(
            GTNote(
                pitch=_round_pitch(pitch_value),
                onset=onset,
                offset=offset,
                velocity=(
                    int(item["velocity"])
                    if item.get("velocity") is not None
                    else None
                ),
                program=(
                    int(item["program"])
                    if item.get("program") is not None
                    else None
                ),
                confidence=(
                    float(item["confidence"])
                    if item.get("confidence") is not None
                    else None
                ),
            )
        )
    return sorted(notes, key=lambda n: (n.onset, n.pitch, n.offset))


def load_ground_truth(
    track: TrackSpec,
    *,
    gt_path: Path | None,
    chord_gt_path: Path | None,
) -> GroundTruth:
    """Load and validate the reference annotations for one track.

    Raises:
        GroundTruthError: malformed input or no usable annotations.
    """
    if track.qualitative:
        return GroundTruth(source=track.source)

    notes: list[GTNote] = []
    chords: list[GTChord] = []

    if track.gt_format in ("guitarset_jams", "egset12_jams"):
        if gt_path is None:
            raise GroundTruthError(f"track {track.id!r}: missing JAMS path")
        notes = load_jams_notes(gt_path, program=24)
        chords = (
            load_timeline_chords(chord_gt_path)
            if chord_gt_path is not None
            else load_jams_chords(gt_path)
        )
    elif track.gt_format == "guitar_techs_midi":
        if gt_path is None:
            raise GroundTruthError(f"track {track.id!r}: missing MIDI path")
        notes = load_midi_notes(gt_path, program_override=24)
        if chord_gt_path is not None:
            chords = load_timeline_chords(chord_gt_path)
    elif track.gt_format == "midi":
        if gt_path is None:
            raise GroundTruthError(f"track {track.id!r}: missing MIDI path")
        notes = load_midi_notes(gt_path)
        if chord_gt_path is not None:
            chords = load_timeline_chords(chord_gt_path)
    elif track.gt_format == "notes_json":
        if gt_path is None:
            raise GroundTruthError(f"track {track.id!r}: missing notes JSON path")
        notes = load_notes_json(gt_path)
        if chord_gt_path is not None:
            chords = load_timeline_chords(chord_gt_path)
    elif track.gt_format == "chord_timeline":
        if chord_gt_path is None:
            raise GroundTruthError(
                f"track {track.id!r}: missing chord timeline path"
            )
        chords = load_timeline_chords(chord_gt_path)
    elif track.gt_format == "none":
        if chord_gt_path is None:
            raise GroundTruthError(
                f"track {track.id!r}: gt_format='none' needs a chord timeline"
            )
        chords = load_timeline_chords(chord_gt_path)
    else:  # pragma: no cover - Literal is validated by pydantic
        raise GroundTruthError(
            f"track {track.id!r}: unsupported gt_format {track.gt_format!r}"
        )

    if not notes and not chords:
        raise GroundTruthError(f"track {track.id!r}: ground truth is empty")

    return GroundTruth(notes=notes, chords=chords, source=track.source)
