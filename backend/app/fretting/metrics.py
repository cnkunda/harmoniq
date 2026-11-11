"""Metrics for MIDI→tablature assignment.

Definitions follow the Fretting-Transformer (arXiv:2506.14223):

- **pitch accuracy** — the produced tablature preserves the input pitch;
- **tab accuracy** — the predicted ``(string, fret)`` matches the
  reference tablature;
- **difficulty** — mean playability cost over chronological note groups.

Unassigned notes count as misses for both accuracies. Difficulty uses one
hand anchor per group so simultaneous chord notes do not create spurious
zero-distance transitions.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.fretting.assign import Assignment
from app.fretting.playability import DEFAULT_ALPHA, sequence_difficulty
from app.fretting.positions import Position
from app.fretting.types import TabNote


def _control_positions(note: TabNote) -> Position | None:
    if note.string is None or note.fret is None:
        return None
    return Position(string=note.string, fret=note.fret)


def _group_anchor(group: Sequence[TabNote]) -> Position | None:
    positions = [
        position
        for position in (_control_positions(note) for note in group)
        if position is not None
    ]
    if not positions:
        return None
    return min(positions, key=lambda position: (position.fret, -position.string))


def group_validity(groups: Sequence[Sequence[TabNote]]) -> float | None:
    """Fraction of multi-note groups whose notes use distinct strings."""
    multi = [group for group in groups if len(group) > 1]
    if not multi:
        return None
    valid = 0
    for group in multi:
        strings = [note.string for note in group]
        if any(string is None for string in strings):
            continue
        if len(set(strings)) == len(strings):
            valid += 1
    return round(valid / len(multi), 6)


def evaluate_assignment(
    reference: Sequence[TabNote],
    assignment: Assignment,
    *,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, object]:
    """Score an assignment against reference tablature.

    Args:
        reference: Ground-truth notes (must carry ``string`` and ``fret``).
        assignment: The predicted assignment, aligned with ``reference``.
        alpha: Locality weight used for the difficulty score.

    Raises:
        ValueError: the sequences have different lengths.
    """
    if len(reference) != len(assignment.notes):
        raise ValueError(
            "reference and assignment must align: "
            f"{len(reference)} != {len(assignment.notes)}"
        )
    total = len(reference)
    assigned = 0
    tab_matches = 0
    for expected, predicted in zip(reference, assignment.notes):
        if predicted.string is None or predicted.fret is None:
            continue
        assigned += 1
        if (
            predicted.string == expected.string
            and predicted.fret == expected.fret
        ):
            tab_matches += 1

    anchors = [
        anchor
        for anchor in (_group_anchor(group) for group in assignment.groups)
        if anchor is not None
    ]
    difficulty = (
        sequence_difficulty(anchors, alpha=alpha) if len(anchors) >= 2 else 0.0
    )
    return {
        "notes": total,
        "assigned": assigned,
        "unassignable": total - assigned,
        "pitch_accuracy": round(assigned / total, 6) if total else None,
        "tab_accuracy": round(tab_matches / total, 6) if total else None,
        "tab_accuracy_assigned": (
            round(tab_matches / assigned, 6) if assigned else None
        ),
        "tab_matches": tab_matches,
        "difficulty": difficulty,
        "transitions": max(len(anchors) - 1, 0),
        "group_validity": group_validity(assignment.groups),
    }


def aggregate_metrics(
    results: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Aggregate per-track metric dicts.

    Accuracies are note-weighted; difficulty is the mean of per-track means
    over tracks that actually contain a transition.
    """
    total_notes = sum(int(result.get("notes", 0)) for result in results)
    assigned = sum(int(result.get("assigned", 0)) for result in results)
    tab_matches = sum(int(result.get("tab_matches", 0)) for result in results)
    difficulties = [
        float(result["difficulty"])
        for result in results
        if int(result.get("transitions", 0)) > 0
        and result.get("difficulty") is not None
    ]
    validities = [
        float(result["group_validity"])
        for result in results
        if result.get("group_validity") is not None
    ]
    return {
        "tracks": len(results),
        "notes": total_notes,
        "assigned": assigned,
        "unassignable": total_notes - assigned,
        "tab_matches": tab_matches,
        "pitch_accuracy": (
            round(assigned / total_notes, 6) if total_notes else None
        ),
        "tab_accuracy": (
            round(tab_matches / total_notes, 6) if total_notes else None
        ),
        "tab_accuracy_assigned": (
            round(tab_matches / assigned, 6) if assigned else None
        ),
        "difficulty": (
            round(sum(difficulties) / len(difficulties), 6)
            if difficulties
            else None
        ),
        "difficulty_tracks": len(difficulties),
        "group_validity": (
            round(sum(validities) / len(validities), 6) if validities else None
        ),
    }
