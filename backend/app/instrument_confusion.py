"""Commit 121: Instrument confusion diagnostic for dual-path inference.

Provides per-section confusion scoring from the dual-path fusion log,
enabling coaching feedback to be hedged when instrument interference is likely.

Commit 156: adds a heuristic MT3-path proxy for jobs where the dual-path
CRNN branch never ran (MT3-primary transcriptions). The proxy is the share
of low-confidence chord events per section — a measure of model
uncertainty, NOT stem-vs-mix divergence. It is clearly labeled as a
heuristic: it can overstate confusion from other causes. Dual-path
divergence remains the primary signal wherever it exists.
"""

from __future__ import annotations

from app.confidence_thresholds import HEDGE_TRIGGER
from app.schemas import ChordTimeline, LessonSectionStub, SectionConfusionScore

#: Chord-event confidence below this counts as "uncertain" for the MT3 proxy.
MT3_PROXY_LOW_CONFIDENCE = 0.5


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
            is_high_confusion=confusion >= HEDGE_TRIGGER,
            beat_count=total_in_section,
            disagreement_count=disagreements,
        ))

    return result


def heuristic_mt3_section_confusion(
    sections: list[LessonSectionStub],
    chord_timeline: ChordTimeline | None,
) -> list[SectionConfusionScore]:
    """Heuristic per-section confusion for MT3-primary jobs (Commit 156).

    The dual-path CRNN branch never runs on the MT3 path, so there is no
    stem-vs-mix divergence to count. This proxy scores each section by the
    share of chord events whose confidence falls below
    MT3_PROXY_LOW_CONFIDENCE. Sections with no usable events are skipped
    (missing means unknown, never 0); consumers match entries by
    section_index.

    This measures model uncertainty, not instrument interference — treat
    hedges driven by it as approximate and prefer dual-path divergence
    wherever both exist.
    """
    result: list[SectionConfusionScore] = []
    if not sections or chord_timeline is None:
        return result

    events = [e for e in chord_timeline.events if e.chord != "N"]
    for i, sec in enumerate(sections):
        sec_start = sec.start_time_seconds
        sec_end = sec.end_time_seconds
        if sec_end is None and i + 1 < len(sections):
            sec_end = sections[i + 1].start_time_seconds

        in_section = [
            e for e in events
            if (sec_start is None or e.timestamp >= sec_start)
            and (sec_end is None or e.timestamp < sec_end)
        ]
        if not in_section:
            # No usable events: confusion is unknown, so emit no entry.
            # (Missing means unchanged copy — never fabricate 0.0.)
            # Consumers match entries by section_index.
            continue

        low = sum(1 for e in in_section if (e.confidence or 0.0) < MT3_PROXY_LOW_CONFIDENCE)
        confusion = low / len(in_section)
        result.append(SectionConfusionScore(
            section_index=i,
            label=sec.label or f"Section {i + 1}",
            start_time=sec_start,
            end_time=sec_end,
            instrument_confusion=round(confusion, 4),
            is_high_confusion=confusion >= HEDGE_TRIGGER,
            beat_count=len(in_section),
            disagreement_count=low,
        ))

    return result
