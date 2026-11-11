"""Guitar tablature intelligence (Commit 1 / W4).

This package assigns string/fret positions to symbolic notes with a
playability-aware dynamic program, and provides the metrics needed to
compare it against the existing per-note ``allCellsForMidi`` heuristic.

It is evaluation-only: the analysis pipeline does not import it yet.
"""

from app.fretting.assign import Assignment, assign_tab, group_notes
from app.fretting.positions import (
    Position,
    baseline_position,
    candidates_for_pitch,
    is_playable_pitch,
)
from app.fretting.tuning import (
    MAX_FRET,
    NUM_STRINGS,
    Tuning,
    drop_d,
    full_step_down,
    get_tuning,
    half_step_down,
    standard,
)
from app.fretting.types import TabNote

__all__ = [
    "Assignment",
    "MAX_FRET",
    "NUM_STRINGS",
    "Position",
    "TabNote",
    "Tuning",
    "assign_tab",
    "baseline_position",
    "candidates_for_pitch",
    "drop_d",
    "full_step_down",
    "get_tuning",
    "group_notes",
    "half_step_down",
    "is_playable_pitch",
    "standard",
]
