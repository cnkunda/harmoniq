"""Teacher registry for W2 comparison.

Names:
    mt3         — production MT3 (JAX/T5X)
    mr_mt3      — MR-MT3 PyTorch (MIT)
    yourmt3     — YourMT3+ YPTF.MoE+Multi PyTorch
    musicfm     — MusicFM/MIROS placeholder (blocked)
"""

from __future__ import annotations

from app.teachers.events import (
    TeacherError,
    TeacherNote,
    TeacherOutput,
    TeacherTimeout,
    TeacherUnavailable,
    events_to_notes,
    midi_file_to_notes,
    notes_to_event_stream,
)
from app.teachers.leakage import aggregate_leakage, leakage_report
from app.teachers.mt3 import Mt3Teacher
from app.teachers.mt3_infer import Mt3InferTeacher
from app.teachers.musicfm import MusicFmTeacher

_TEACHERS = {
    "mt3": lambda: Mt3Teacher(),
    "mr_mt3": lambda: Mt3InferTeacher("mr_mt3"),
    "yourmt3": lambda: Mt3InferTeacher("yourmt3"),
    "musicfm": lambda: MusicFmTeacher(),
}

TEACHER_NAMES = tuple(_TEACHERS)


def get_teacher(name: str):
    if name not in _TEACHERS:
        raise ValueError(
            f"unknown teacher {name!r}; choose from {', '.join(TEACHER_NAMES)}"
        )
    return _TEACHERS[name]()


def teacher_statuses() -> dict[str, dict[str, object]]:
    """Return availability + reason for every registered teacher."""
    statuses: dict[str, dict[str, object]] = {}
    for name in TEACHER_NAMES:
        teacher = get_teacher(name)
        available = bool(teacher.is_available())
        statuses[name] = {
            "available": available,
            "display_name": getattr(teacher, "display_name", name),
            "reason": None if available else teacher.unavailable_reason(),
        }
    return statuses


__all__ = [
    "TEACHER_NAMES",
    "TeacherError",
    "TeacherNote",
    "TeacherOutput",
    "TeacherTimeout",
    "TeacherUnavailable",
    "aggregate_leakage",
    "events_to_notes",
    "get_teacher",
    "leakage_report",
    "midi_file_to_notes",
    "notes_to_event_stream",
    "teacher_statuses",
]
