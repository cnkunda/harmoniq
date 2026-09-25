"""Export a corrected chord timeline to .lab format for training data contribution.

The .lab format (Isophonics / McGill Billboard convention):
    onset  offset  chord_label

Lines are whitespace-separated with at least 3 columns.
"""

from __future__ import annotations

from app.schemas import ChordTimeline


def chord_timeline_to_lab(timeline: ChordTimeline) -> str:
    """Convert a ChordTimeline to .lab file content.

    Each chord event becomes a line: ``onset offset chord_label``.
    Duration of each event is inferred from the next event's timestamp,
    with a default of 2.0 seconds for the final event.

    Args:
        timeline: The corrected chord timeline.

    Returns:
        Multi-line .lab string ready to write to disk.
    """
    if not timeline.events:
        return ""

    lines: list[str] = []
    for i, ev in enumerate(timeline.events):
        onset = ev.timestamp
        if i + 1 < len(timeline.events):
            offset = timeline.events[i + 1].timestamp
        else:
            offset = onset + 2.0
        lines.append(f"{onset:.3f}\t{offset:.3f}\t{ev.chord}")

    return "\n".join(lines) + "\n"
