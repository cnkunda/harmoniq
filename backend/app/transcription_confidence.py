"""
Composite transcription confidence (ML Fallback Logic milestone).

``LessonJSON.transcription_confidence`` was previously a lyric word-count
heuristic that never exceeded 0.7 — below the frontend "uncertain" bar
(0.72), so *every* transcript was flagged uncertain and the skeleton-tab
fallback never discriminated. This module computes a real per-section
signal from the chord model's blended max-softmax confidence and
vocal-alignment coverage, so clean audio scores high (>= 0.85) and
genuinely uncertain audio scores low.
"""

from __future__ import annotations

from typing import Any

from app.schemas import ChordTimeline


def chord_section_confidence(
    chord_timeline: ChordTimeline | dict | None,
    *,
    section_start: float | None = None,
    section_end: float | None = None,
) -> float | None:
    """Duration-weighted mean of ChordEvent confidence within a section.

    Events are weighted by how long they last (next event start minus this
    start), so a sustained chord counts more than a one-beat blip.  No-chord
    ("N") events are excluded — silence is not evidence of transcription
    quality.  Returns None when there are no useful events.

    Accepts either a ``ChordTimeline`` or a plain dict (sections store the
    timeline via ``model_dump()``), and events as models or dicts.
    """
    if isinstance(chord_timeline, dict):
        raw_events = chord_timeline.get("events") or []
    elif chord_timeline is None:
        return None
    else:
        raw_events = chord_timeline.events

    def _key(ev: Any, name: str, default: Any = None) -> Any:
        if isinstance(ev, dict):
            return ev.get(name, default)
        return getattr(ev, name, default)

    events = []
    for e in raw_events:
        chord = _key(e, "chord")
        if chord == "N":
            continue
        ts = _key(e, "timestamp")
        if ts is None:
            continue
        events.append(e)
    if section_start is not None:
        events = [e for e in events if _key(e, "timestamp") >= section_start]
    if section_end is not None:
        events = [e for e in events if _key(e, "timestamp") < section_end]
    if not events:
        return None
    events = sorted(events, key=lambda e: _key(e, "timestamp"))
    total_weight = 0.0
    weighted = 0.0
    for i, e in enumerate(events):
        if i + 1 < len(events):
            dur = max(0.0, _key(events[i + 1], "timestamp") - _key(e, "timestamp"))
        else:
            dur = 1.0
        if dur <= 0:
            continue
        total_weight += dur
        weighted += dur * float(_key(e, "confidence", 0.5) or 0.5)
    if total_weight <= 0:
        return None
    return float(weighted / total_weight)


def vocals_coverage_confidence(
    lyrics_aligned: list[dict[str, Any]] | None,
    num_beats: int,
    *,
    beats_per_bar: int = 4,
) -> float | None:
    """Map the fraction of beats covered by an aligned word to confidence.

    The old heuristic counted raw words (a 12-word song capped at 0.7, an
    instrumental scored 0.1 forever).  Coverage of the beat grid is a much
    better proxy for "we heard and anchored the vocal line".  A song where
    words land on >= half the beats is a confident lyric alignment; sparse
    coverage stays low.  Returns None when there is no vocal data (e.g.,
    instrumental-only tracks) — callers then rely on chord confidence.

    Row shapes: ``transcribe.map_words_to_lyrics_aligned`` emits
    ``{"word", "time_seconds", "bar", "beat"}`` with ``beat`` being the
    beat-within-bar index (0..beats_per_bar-1); other producers may emit an
    absolute beat index in ``beat``.  Both are normalized to an absolute
    beat slot before deduping so within-bar wraparound never collapses
    coverage to <= 4 distinct slots.
    """
    if not lyrics_aligned or num_beats <= 0:
        return None
    covered: set[int] = set()
    for row in lyrics_aligned:
        if not isinstance(row, dict):
            continue
        beat = row.get("beat")
        if not isinstance(beat, int) or beat < 0:
            continue
        bar = row.get("bar")
        if isinstance(bar, int) and bar >= 0 and beat < beats_per_bar:
            covered.add(bar * beats_per_bar + beat)
        else:
            covered.add(beat)
    ratio = len(covered) / num_beats
    if ratio >= 0.5:
        return 0.92
    if ratio >= 0.25:
        return 0.82
    if ratio >= 0.1:
        return 0.7
    if ratio >= 0.03:
        return 0.55
    return 0.35


def composite_transcription_confidence(
    chord_conf: float | None,
    vocals_conf: float | None,
    *,
    guitar_stem_usable: bool = True,
) -> float:
    """Blend per-instrument signals into a single [0.05, 1.0] confidence.

    - No signal at all -> 0.1 (parity with the old failure floor).
    - Instrumental (no vocals) -> chord confidence alone.
    - Chords failed but vocals present -> vocals, slightly discounted.
    - Both present -> 60/40 chord/vocals blend (chords carry the gating
      decision for tab fallback; vocals corroborate).
    - Guitar stem unusable -> capped at 0.25 by the caller; here we just
      never *raise* it above that floor when the stem is unusable.
    """
    if chord_conf is None and vocals_conf is None:
        return 0.1
    if vocals_conf is None:
        value = float(chord_conf or 0.1)
    elif chord_conf is None:
        value = 0.85 * float(vocals_conf)
    else:
        value = 0.6 * float(chord_conf) + 0.4 * float(vocals_conf)
    if not guitar_stem_usable:
        value = min(value, 0.25)
    return float(max(0.05, min(1.0, value)))