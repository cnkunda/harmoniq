"""Instrument-leakage diagnostics for teacher comparison.

W2 needs note-level evidence about instrument confusion, not the chord-level
proxy used by the production pipeline. These metrics are computed directly
from a teacher's note output:

- non-guitar GM program share (guitar family = programs 24–31)
- out-of-guitar-range pitch share (E2=40 … E6=84)
- union leakage rate
- program/family histograms

Notes with ``program=None`` are treated as unknown and excluded from the
program-share denominator, but still count toward the total for the union.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from app.teachers.events import TeacherNote

GUITAR_PROGRAMS = frozenset(range(24, 32))
GUITAR_MIN_PITCH = 40
GUITAR_MAX_PITCH = 84


def _program_family(program: int | None) -> str:
    if program is None:
        return "unknown"
    if program in GUITAR_PROGRAMS:
        return "guitar"
    if 0 <= program <= 7:
        return "piano"
    if 32 <= program <= 39:
        return "bass"
    if 40 <= program <= 47:
        return "strings"
    if 48 <= program <= 55:
        return "ensemble"
    if 56 <= program <= 63:
        return "brass"
    if 64 <= program <= 71:
        return "reed"
    if 72 <= program <= 79:
        return "pipe"
    if 80 <= program <= 87:
        return "synth_lead"
    if 88 <= program <= 95:
        return "synth_pad"
    if 96 <= program <= 103:
        return "synth_effects"
    if 104 <= program <= 111:
        return "ethnic"
    if 112 <= program <= 119:
        return "percussive"
    if 120 <= program <= 127:
        return "sound_effects"
    return "other"


def leakage_report(
    notes: Iterable[TeacherNote],
    *,
    expected_programs: Iterable[int] | None = None,
) -> dict[str, object]:
    """Compute note-level leakage/confusion metrics."""
    notes = list(notes)
    total = len(notes)
    if total == 0:
        return {
            "notes": 0,
            "known_program_notes": 0,
            "non_guitar_program_notes": 0,
            "non_guitar_program_share": None,
            "out_of_range_notes": 0,
            "out_of_range_share": None,
            "leakage_notes": 0,
            "leakage_rate": None,
            "program_counts": {},
            "family_counts": {},
            "expected_programs": sorted(set(expected_programs or [])),
        }

    known = [note for note in notes if note.program is not None]
    non_guitar = [
        note
        for note in known
        if int(note.program) not in GUITAR_PROGRAMS
    ]
    out_of_range = [
        note
        for note in notes
        if note.pitch < GUITAR_MIN_PITCH or note.pitch > GUITAR_MAX_PITCH
    ]
    leakage_notes = [
        note
        for note in notes
        if (note.program is not None and int(note.program) not in GUITAR_PROGRAMS)
        or note.pitch < GUITAR_MIN_PITCH
        or note.pitch > GUITAR_MAX_PITCH
    ]

    program_counts = Counter(
        str(note.program) if note.program is not None else "unknown"
        for note in notes
    )
    family_counts = Counter(_program_family(note.program) for note in notes)

    return {
        "notes": total,
        "known_program_notes": len(known),
        "non_guitar_program_notes": len(non_guitar),
        "non_guitar_program_share": (
            round(len(non_guitar) / len(known), 6) if known else None
        ),
        "out_of_range_notes": len(out_of_range),
        "out_of_range_share": round(len(out_of_range) / total, 6),
        "leakage_notes": len(leakage_notes),
        "leakage_rate": round(len(leakage_notes) / total, 6),
        "program_counts": dict(sorted(program_counts.items(), key=lambda item: item[0])),
        "family_counts": dict(sorted(family_counts.items())),
        "expected_programs": sorted(set(expected_programs or [])),
    }


def aggregate_leakage(reports: Iterable[dict[str, object]]) -> dict[str, object]:
    """Aggregate per-track leakage reports into a teacher-level summary."""
    reports = [report for report in reports if report]
    if not reports:
        return {
            "tracks": 0,
            "notes": 0,
            "leakage_rate": None,
            "non_guitar_program_share": None,
            "out_of_range_share": None,
            "family_counts": {},
        }

    def _weighted(key: str) -> float | None:
        numerator = 0
        denominator = 0
        for report in reports:
            value = report.get(key)
            if value is None:
                continue
            notes = int(report.get("notes", 0))
            if key == "non_guitar_program_share":
                notes = int(report.get("known_program_notes", 0))
            numerator += float(value) * notes
            denominator += notes
        return round(numerator / denominator, 6) if denominator else None

    families: Counter[str] = Counter()
    for report in reports:
        for family, count in (report.get("family_counts") or {}).items():
            families[str(family)] += int(count)

    return {
        "tracks": len(reports),
        "notes": sum(int(report.get("notes", 0)) for report in reports),
        "leakage_rate": _weighted("leakage_rate"),
        "non_guitar_program_share": _weighted("non_guitar_program_share"),
        "out_of_range_share": _weighted("out_of_range_share"),
        "family_counts": dict(sorted(families.items())),
    }
