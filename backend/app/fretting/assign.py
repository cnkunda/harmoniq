"""Sequence-aware string/fret assignment.

Two modes are supported:

- ``baseline`` — one note at a time, lowest fret then high E first. This is
  the exact behaviour of ``allCellsForMidi`` in ``src/music/fretboardCell.ts``
  and is the G4 reference.
- ``dp`` — a Viterbi-style dynamic program over candidate positions. It
  minimises the Fretting-Transformer playability cost between consecutive
  note groups while keeping simultaneous notes on distinct strings. Pitch is
  never changed, so a successful assignment always preserves pitch.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.fretting.playability import DEFAULT_ALPHA, transition_difficulty
from app.fretting.positions import Position, baseline_position, candidates_for_pitch
from app.fretting.tuning import MAX_FRET, Tuning, standard
from app.fretting.types import TabNote

DEFAULT_GROUP_TOLERANCE_S = 0.03
DEFAULT_MAX_SPAN = 5
DEFAULT_MAX_GROUP_CANDIDATES = 256


@dataclass
class Assignment:
    """The result of one assignment pass."""

    mode: str
    tuning: Tuning
    #: Aligned 1:1 with the input ``notes`` sequence; unassigned notes keep
    #: ``string``/``fret`` as ``None``.
    notes: list[TabNote]
    #: Chronological note groups (simultaneous notes share a group).
    groups: list[list[TabNote]] = field(default_factory=list)
    unassignable: list[TabNote] = field(default_factory=list)
    total_cost: float = 0.0


def group_notes(
    notes: Sequence[TabNote],
    *,
    tolerance_s: float = DEFAULT_GROUP_TOLERANCE_S,
) -> list[list[TabNote]]:
    """Group notes whose onsets are within ``tolerance_s`` of the group start."""
    if tolerance_s < 0:
        raise ValueError(f"tolerance_s must be >= 0, got {tolerance_s}")
    ordered = sorted(notes, key=lambda note: (note.onset, note.pitch, note.offset))
    groups: list[list[TabNote]] = []
    for note in ordered:
        if (
            groups
            and abs(float(note.onset) - float(groups[-1][0].onset)) <= tolerance_s
        ):
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def _group_indices(notes: Sequence[TabNote], tolerance_s: float) -> list[list[int]]:
    """Group indices into the already ordered ``notes`` sequence."""
    groups: list[list[int]] = []
    starts: list[float] = []
    for index, note in enumerate(notes):
        if groups and abs(float(note.onset) - starts[-1]) <= tolerance_s:
            groups[-1].append(index)
        else:
            groups.append([index])
            starts.append(float(note.onset))
    return groups


def _representative(positions: Sequence[Position]) -> Position:
    """Hand anchor for a group: lowest fret, then the low E string."""
    return min(positions, key=lambda position: (position.fret, -position.string))


def _group_candidates(
    group: Sequence[TabNote],
    tuning: Tuning,
    *,
    max_fret: int,
    max_span: int | None,
    max_candidates: int,
) -> list[tuple[Position, ...]]:
    """Enumerate playable position combinations for one note group."""
    per_note = [
        candidates_for_pitch(note.pitch, tuning, max_fret=max_fret)
        for note in group
    ]
    if any(not candidates for candidates in per_note):
        return []
    if len(group) == 1:
        return [(position,) for position in per_note[0]]

    def _enumerate(span: int | None) -> list[tuple[Position, ...]]:
        results: list[tuple[Position, ...]] = []
        # DFS keeps the combination count manageable for six-note chords.
        limit = max(max_candidates * 8, max_candidates)
        chosen: list[Position] = []
        used_strings: set[int] = set()

        def _walk(index: int) -> None:
            if len(results) >= limit:
                return
            if index == len(per_note):
                results.append(tuple(chosen))
                return
            for position in per_note[index]:
                if position.string in used_strings:
                    continue
                if span is not None and chosen:
                    frets = [item.fret for item in chosen] + [position.fret]
                    if max(frets) - min(frets) > span:
                        continue
                chosen.append(position)
                used_strings.add(position.string)
                _walk(index + 1)
                used_strings.remove(position.string)
                chosen.pop()

        _walk(0)
        return results

    results = _enumerate(max_span)
    if not results and max_span is not None:
        # A wide but physically distinct voicing is still better than
        # dropping the group: relax the span constraint rather than lose
        # pitch. The playability cost still penalises the wide stretch.
        results = _enumerate(None)
    if not results:
        return []
    deduped = sorted(
        set(results),
        key=lambda combo: (
            max(item.fret for item in combo) - min(item.fret for item in combo),
            sum(item.fret for item in combo),
            tuple((item.string, item.fret) for item in combo),
        ),
    )
    return deduped[:max_candidates]


def _group_positions(
    group: Sequence[TabNote],
) -> list[Position]:
    """Assigned positions in a chronological group, if any."""
    return [
        Position(string=note.string, fret=note.fret)
        for note in group
        if note.string is not None and note.fret is not None
    ]


def _sequence_cost(groups: Sequence[Sequence[TabNote]], alpha: float) -> float:
    representatives: list[Position] = []
    for group in groups:
        positions = _group_positions(group)
        if positions:
            representatives.append(_representative(positions))
    if len(representatives) < 2:
        return 0.0
    total = sum(
        transition_difficulty(before, after, alpha=alpha)
        for before, after in zip(representatives, representatives[1:])
    )
    return round(total / (len(representatives) - 1), 6)


def _reassemble(
    indexed: Sequence[tuple[int, TabNote]],
    ordered: Sequence[TabNote],
) -> list[TabNote]:
    """Map the chronologically ordered notes back to the input order."""
    output: list[TabNote | None] = [None] * len(indexed)
    for ordered_index, (original_index, _note) in enumerate(indexed):
        output[original_index] = ordered[ordered_index]
    if any(note is None for note in output):
        raise RuntimeError("internal error: assignment did not cover every note")
    return [note for note in output if note is not None]


def assign_tab(
    notes: Sequence[TabNote],
    *,
    tuning: Tuning | None = None,
    mode: str = "dp",
    max_fret: int = MAX_FRET,
    alpha: float = DEFAULT_ALPHA,
    max_span: int | None = DEFAULT_MAX_SPAN,
    group_tolerance_s: float = DEFAULT_GROUP_TOLERANCE_S,
    max_group_candidates: int = DEFAULT_MAX_GROUP_CANDIDATES,
) -> Assignment:
    """Assign string/fret positions to ``notes``.

    Args:
        notes: Symbolic notes; any existing ``string``/``fret`` is ignored.
        tuning: Tuning/capo condition. Defaults to standard, no capo.
        mode: ``"baseline"`` or ``"dp"``.
        max_fret: Highest playable fret (inclusive).
        alpha: Locality weight for the playability cost.
        max_span: Maximum fret span within a simultaneous group. ``None``
            disables the constraint.
        group_tolerance_s: Onset window that defines a simultaneous group.
        max_group_candidates: Cap on position combinations per group.

    Returns:
        An :class:`Assignment` whose ``notes`` align with the input order.

    Raises:
        ValueError: unknown mode or invalid configuration.
    """
    if mode not in ("baseline", "dp"):
        raise ValueError(f"mode must be 'baseline' or 'dp', got {mode!r}")
    if max_span is not None and max_span < 0:
        raise ValueError(f"max_span must be >= 0, got {max_span}")
    if max_group_candidates < 1:
        raise ValueError(
            f"max_group_candidates must be >= 1, got {max_group_candidates}"
        )

    resolved_tuning = tuning or standard()
    indexed = list(enumerate(notes))
    indexed.sort(
        key=lambda pair: (
            pair[1].onset,
            pair[1].pitch,
            pair[1].offset,
            pair[0],
        )
    )
    # Assignment always starts from pitches alone; any position supplied on
    # the input is discarded so callers can safely reuse ground-truth notes.
    ordered = [
        note.with_position(None, None) for _index, note in indexed
    ]
    index_groups = _group_indices(ordered, group_tolerance_s)

    if mode == "baseline":
        assigned_ordered: list[TabNote] = []
        unassignable: list[TabNote] = []
        for note in ordered:
            position = baseline_position(
                note.pitch, resolved_tuning, max_fret=max_fret
            )
            if position is None:
                assigned_ordered.append(note)
                unassignable.append(note)
            else:
                assigned_ordered.append(
                    note.with_position(position.string, position.fret)
                )
        groups = [
            [assigned_ordered[index] for index in group]
            for group in index_groups
        ]
        assignment = Assignment(
            mode=mode,
            tuning=resolved_tuning,
            notes=_reassemble(indexed, assigned_ordered),
            groups=groups,
            unassignable=unassignable,
            total_cost=_sequence_cost(groups, alpha),
        )
        return assignment

    # ---- DP ----------------------------------------------------------
    candidate_groups: list[list[tuple[Position, ...]]] = []
    assignable_groups: list[list[int]] = []
    unassignable_indices: set[int] = set()
    for group in index_groups:
        group_notes = [ordered[index] for index in group]
        candidates = _group_candidates(
            group_notes,
            resolved_tuning,
            max_fret=max_fret,
            max_span=max_span,
            max_candidates=max_group_candidates,
        )
        if not candidates:
            unassignable_indices.update(group)
            continue
        assignable_groups.append(group)
        candidate_groups.append(candidates)

    assigned_ordered = list(ordered)
    if candidate_groups:
        # cost_rows[i][j] = (best cost to reach candidate j at group i,
        #                    previous candidate index)
        cost_rows: list[list[tuple[float, int]]] = []
        for group_index, candidates in enumerate(candidate_groups):
            row: list[tuple[float, int]] = []
            for candidate_index, candidate in enumerate(candidates):
                if group_index == 0:
                    row.append((0.0, -1))
                    continue
                current_rep = _representative(candidate)
                previous_row = cost_rows[group_index - 1]
                best_cost = float("inf")
                best_previous = -1
                for previous_index, (previous_cost, _unused) in enumerate(
                    previous_row
                ):
                    previous_rep = _representative(
                        candidate_groups[group_index - 1][previous_index]
                    )
                    cost = previous_cost + transition_difficulty(
                        previous_rep, current_rep, alpha=alpha
                    )
                    if cost < best_cost - 1e-9 or (
                        abs(cost - best_cost) <= 1e-9
                        and (best_previous == -1 or previous_index < best_previous)
                    ):
                        best_cost = cost
                        best_previous = previous_index
                row.append((best_cost, best_previous))
            cost_rows.append(row)

        last_row = cost_rows[-1]
        final_index = min(
            range(len(last_row)),
            key=lambda index: (last_row[index][0], index),
        )
        chosen_indices: list[int] = [0] * len(candidate_groups)
        cursor = final_index
        for group_index in range(len(candidate_groups) - 1, -1, -1):
            chosen_indices[group_index] = cursor
            cursor = cost_rows[group_index][cursor][1]

        for group, candidates, chosen_index in zip(
            assignable_groups, candidate_groups, chosen_indices
        ):
            combination = candidates[chosen_index]
            if len(combination) != len(group):
                raise RuntimeError(
                    "internal error: candidate/group length mismatch"
                )
            for note_index, position in zip(group, combination):
                assigned_ordered[note_index] = ordered[note_index].with_position(
                    position.string, position.fret
                )

    groups = [
        [assigned_ordered[index] for index in group] for group in index_groups
    ]
    unassignable = [assigned_ordered[index] for index in sorted(unassignable_indices)]
    return Assignment(
        mode=mode,
        tuning=resolved_tuning,
        notes=_reassemble(indexed, assigned_ordered),
        groups=groups,
        unassignable=unassignable,
        total_cost=_sequence_cost(groups, alpha),
    )
