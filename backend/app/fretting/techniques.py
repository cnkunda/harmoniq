"""Prototype guitar technique labels from a symbolic note sequence.

This is deliberately a heuristic prototype, not a trained classifier. It
reuses the pitch/time patterns already used by
``app.mt3.solo_decoder`` (bends, vibrato) and adds same-string legato
patterns (slide / hammer-on / pull-off) when an assignment is available.

The labels are reported as counts only; no ground-truth technique metric
is claimed. A learned technique classifier is future work (TART,
arXiv:2510.02597).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.fretting.types import TabNote

#: Maximum gap between two notes for a legato/technique transition.
LEGATO_GAP_S = 0.05
#: A tighter gap is more likely a slide than a hammer-on/pull-off.
SLIDE_GAP_S = 0.03
#: A quick short second note is treated as a bend inflection.
BEND_MAX_DURATION_S = 0.15
#: Number of repeated notes needed to call it vibrato.
VIBRATO_MIN_NOTES = 3


@dataclass
class TechniqueLabels:
    """Technique tags keyed by the input note index."""

    by_index: dict[int, list[str]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


def _add(labels: dict[int, list[str]], index: int, tag: str) -> None:
    tags = labels.setdefault(index, [])
    if tag not in tags:
        tags.append(tag)


def label_techniques(
    notes: Sequence[TabNote],
    *,
    assignment: Sequence[TabNote] | None = None,
) -> TechniqueLabels:
    """Label technique candidates in a note sequence.

    Args:
        notes: Notes in performance order (any order; sorted internally).
        assignment: Optional notes carrying ``string``/``fret``. When
            omitted, only vibrato (a pitch/time-only pattern) is produced.

    Returns:
        :class:`TechniqueLabels` keyed by the index in ``notes``.
    """
    order = sorted(
        range(len(notes)),
        key=lambda index: (notes[index].onset, notes[index].pitch, index),
    )
    ordered = [notes[index] for index in order]
    string_by_index: dict[int, int | None] = {}
    if assignment is not None:
        if len(assignment) != len(notes):
            raise ValueError(
                "assignment must align 1:1 with notes: "
                f"{len(assignment)} != {len(notes)}"
            )
        string_by_index = {
            index: assignment[index].string for index in range(len(notes))
        }

    labels: dict[int, list[str]] = {}

    for position in range(len(ordered) - 1):
        current_index = order[position]
        next_index = order[position + 1]
        current = ordered[position]
        following = ordered[position + 1]
        delta = int(following.pitch) - int(current.pitch)
        gap = float(following.onset) - float(current.offset)
        if abs(delta) not in (1, 2) or gap > LEGATO_GAP_S:
            continue
        current_string = string_by_index.get(current_index)
        next_string = string_by_index.get(next_index)
        same_string = (
            current_string is not None
            and next_string is not None
            and current_string == next_string
        )
        if not same_string:
            continue
        if gap <= SLIDE_GAP_S and current.duration >= BEND_MAX_DURATION_S:
            _add(labels, current_index, "slide")
            _add(labels, next_index, "slide")
        elif following.duration <= BEND_MAX_DURATION_S:
            _add(labels, current_index, "bend")
            _add(labels, next_index, "bend")
        else:
            tag = "hammer_on" if delta > 0 else "pull_off"
            _add(labels, current_index, tag)
            _add(labels, next_index, tag)

    run_start = 0
    while run_start < len(ordered):
        run_end = run_start + 1
        while (
            run_end < len(ordered)
            and ordered[run_end].pitch == ordered[run_start].pitch
            and float(ordered[run_end].onset)
            - float(ordered[run_end - 1].offset)
            <= LEGATO_GAP_S
        ):
            run_end += 1
        if run_end - run_start >= VIBRATO_MIN_NOTES:
            for position in range(run_start, run_end):
                _add(labels, order[position], "vibrato")
        run_start = run_end

    counts = Counter(
        tag for tags in labels.values() for tag in tags
    )
    return TechniqueLabels(
        by_index={index: tags for index, tags in sorted(labels.items())},
        counts=dict(sorted(counts.items())),
    )
