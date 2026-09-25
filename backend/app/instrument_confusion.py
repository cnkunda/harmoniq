"""Commit 121: Instrument confusion diagnostic for dual-path inference.

Provides per-section confusion scoring from the dual-path fusion log,
enabling coaching feedback to be hedged when instrument interference is likely.
"""

from __future__ import annotations

from app.schemas import ChordTimeline, LessonSectionStub, SectionConfusionScore


def compute_per_section_confusion(
    sections: list[LessonSectionStub],
    chord_timeline: ChordTimeline | None,
    fusion_log: list[dict],
) -> list[SectionConfusionScore]:
    """Compute per-section instrument confusion from dual-path fusion log.

    Counts total events from the fused chord_timeline and disagreements
    from the fusion_log within each section's time range.

    Returns empty list when dual-path was not used (fusion_log empty).
    """
    if not fusion_log or not sections or not chord_timeline:
        return []

    all_events = chord_timeline.events if chord_timeline else []

    result: list[SectionConfusionScore] = []
    for i, sec in enumerate(sections):
        sec_start = sec.start_time_seconds
        sec_end = sec.end_time_seconds
        if sec_end is None and i + 1 < len(sections):
            sec_end = sections[i + 1].start_time_seconds

        total_in_section = 0
        for ev in all_events:
            if sec_start is not None and ev.timestamp < sec_start:
                continue
            if sec_end is not None and ev.timestamp >= sec_end:
                continue
            total_in_section += 1

        disagreements = 0
        for entry in fusion_log:
            ts = entry.get("timestamp")
            if ts is None:
                continue
            if sec_start is not None and ts < sec_start:
                continue
            if sec_end is not None and ts >= sec_end:
                continue
            disagreements += 1

        confusion = disagreements / total_in_section if total_in_section > 0 else 0.0
        result.append(SectionConfusionScore(
            section_index=i,
            label=sec.label or f"Section {i + 1}",
            start_time=sec_start,
            end_time=sec_end,
            instrument_confusion=round(confusion, 4),
            is_high_confusion=confusion > 0.3,
            beat_count=total_in_section,
            disagreement_count=disagreements,
        ))

    return result
