"""Heuristic per-section guitar playing-style and part-role detection.

This module intentionally starts rule-based. The goal is to give the UI an
honest, explainable hint about what the guitar is doing in a section:

- strummed chord accompaniment
- fingerpicked / arpeggiated chord work
- picked single-note lead / solo
- muted or mixed playing

It consumes artifacts the pipeline already produces: the raw MT3 event stream
(when available), ``SoloNotes``, ``ChordTimeline``, and the librosa summary
curves. No additional model is required. A learned classifier can replace the
heuristic later without changing the API contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES
from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.schemas import (
    BeatGrid,
    ChordTimeline,
    LessonSectionStub,
    PerformanceProfile,
    SoloNote,
    SoloNotes,
)

_GUITAR_PROGRAMS = set(range(24, 32))
_ATTACK_WINDOW_S = 0.05
_MIN_EVENT_CONFIDENCE = 0.25
_CHORD_TONE_TOLERANCE = 0.75

_ROOTS = {name: i for i, name in enumerate(ROOT_NOTES)}
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


@dataclass
class _Features:
    duration_s: float = 0.0
    note_count: int = 0
    notes_per_sec: float = 0.0
    attack_count: int = 0
    mean_polyphony: float = 1.0
    simultaneous_attack_ratio: float = 0.0
    mean_attack_pitch_span: float = 0.0
    pitch_range: float = 0.0
    unique_pitch_ratio: float = 0.0
    chord_tone_ratio: float = 0.0
    ioi_regularity: float = 0.0
    technique_ratio: float = 0.0
    onset_density: float = 0.0
    rms_mean: float = 0.0
    centroid_mean: float = 0.0
    section_label: str = ""
    technique_tags: list[str] = field(default_factory=list)
    evidence: dict[str, float] = field(default_factory=dict)


def build_performance_profiles(
    sections: list[LessonSectionStub],
    *,
    chord_timeline: ChordTimeline | None = None,
    solo_notes: SoloNotes | None = None,
    mt3_events: Mt3EventStream | None = None,
    beat_grid: BeatGrid | None = None,
    onset_novelty: object | None = None,
    rms_curve: object | None = None,
    spectral_centroid: object | None = None,
    times: object | None = None,
    song_duration_s: float | None = None,
) -> tuple[list[PerformanceProfile], PerformanceProfile]:
    """Build one profile per section plus a duration-weighted song summary.

    Section-scoped transcription data is preferred when present; otherwise the
    song-level timelines are filtered by the section's time range.
    """
    if not sections:
        return [], PerformanceProfile()

    profiles: list[PerformanceProfile] = []
    for i, section in enumerate(sections):
        start_s, end_s = _section_bounds(sections, i, fallback_end=song_duration_s)
        section_chords = _section_chord_events(section, chord_timeline, start_s, end_s)
        section_notes = _section_solo_notes(section, solo_notes, start_s, end_s)
        section_events = _section_mt3_events(mt3_events, start_s, end_s)

        features = _extract_features(
            start_s=start_s,
            end_s=end_s,
            chord_events=section_chords,
            notes=section_notes,
            events=section_events,
            section_label=(section.label or ""),
            onset_novelty=onset_novelty,
            rms_curve=rms_curve,
            spectral_centroid=spectral_centroid,
            times=times,
        )
        profile = classify_performance(features)
        profiles.append(profile)

        section.performance_profile = profile
        section.technique_tags = list(profile.technique_tags)

    return profiles, _summarize_profiles(sections, profiles, song_duration_s=song_duration_s)


def classify_performance(features: _Features) -> PerformanceProfile:
    """Classify one section from its extracted features."""
    if features.duration_s <= 0.0 or (
        features.note_count == 0 and features.attack_count == 0
    ):
        return PerformanceProfile(source="heuristic", evidence=features.evidence)

    polyphonic = (
        features.simultaneous_attack_ratio >= 0.30
        and features.mean_polyphony >= 1.8
    )
    label = features.section_label.strip().lower()

    chord_tone = features.chord_tone_ratio
    strum_score = _clamp(
        0.40 * features.simultaneous_attack_ratio
        + 0.25 * _squash(features.mean_polyphony / 3.0)
        + 0.20 * _squash(max(0.0, features.mean_attack_pitch_span - 7.0) / 12.0)
        + 0.15 * chord_tone
    )
    finger_score = _clamp(
        0.35 * (1.0 - features.simultaneous_attack_ratio)
        + 0.25 * chord_tone
        + 0.20 * features.ioi_regularity
        + 0.20 * _squash(features.notes_per_sec / 2.5)
    )
    lead_score = _clamp(
        0.30 * (1.0 - features.simultaneous_attack_ratio)
        + 0.25 * _squash(features.pitch_range / 19.0)
        + 0.20 * _squash(features.notes_per_sec / 3.0)
        + 0.15 * features.technique_ratio
        + 0.10 * _squash(features.onset_density / 2.0)
    )

    # Section labels are weak priors, never decisive on their own.
    if label == "solo":
        lead_score += 0.20
    elif label == "instrumental":
        lead_score += 0.05

    if polyphonic:
        strum_score += 0.10
        lead_score -= 0.10

    scores = {
        "strummed": _clamp(strum_score),
        "fingerpicked_arpeggiated": _clamp(finger_score),
        "picked": _clamp(lead_score),
    }

    top_style = max(scores, key=scores.get)
    top_score = scores[top_style]

    if top_score < 0.32 and not polyphonic:
        return PerformanceProfile(
            technique_tags=_technique_tags(features, "unknown"),
            confidence=round(_clamp(top_score * 0.5), 3),
            source="heuristic",
            evidence={k: round(v, 3) for k, v in features.evidence.items()},
        )

    playing_style: str = "picked"
    part_role: str = "lead_solo"

    if polyphonic and scores["strummed"] >= 0.42:
        playing_style = "strummed"
        part_role = "rhythm"
    elif (
        not polyphonic
        and scores["fingerpicked_arpeggiated"] >= 0.48
        and chord_tone >= 0.55
    ):
        playing_style = "fingerpicked_arpeggiated"
        part_role = "chord_melody"
    elif scores["picked"] >= 0.48:
        playing_style = "picked"
        part_role = "lead_solo"
    else:
        playing_style = top_style
        part_role = "rhythm" if top_style == "strummed" else (
            "chord_melody" if top_style == "fingerpicked_arpeggiated" else "lead_solo"
        )

    # Mixed sections: both a strong chord attack profile and a strong lead line.
    if (
        features.simultaneous_attack_ratio >= 0.35
        and features.notes_per_sec >= 2.0
        and scores["picked"] >= 0.55
    ):
        playing_style = "mixed"
        part_role = "mixed"
        top_score = max(top_score, 0.55)

    # Muted playing: low spectral centroid + dense attacks. Only trust this
    # when we have audio features and polyphonic attacks.
    if (
        polyphonic
        and features.centroid_mean > 0.0
        and features.centroid_mean < 1400.0
        and features.onset_density >= 1.5
    ):
        playing_style = "muted"
        part_role = "rhythm"

    confidence = _confidence(top_score, scores, features)

    return PerformanceProfile(
        playing_style=playing_style,  # type: ignore[arg-type]
        part_role=part_role,  # type: ignore[arg-type]
        technique_tags=_technique_tags(features, playing_style),
        confidence=confidence,
        source="heuristic",
        evidence={k: round(v, 3) for k, v in features.evidence.items()},
    )


def _extract_features(
    *,
    start_s: float,
    end_s: float,
    chord_events: list[tuple[float, str]],
    notes: list[SoloNote],
    events: list[Mt3Event],
    section_label: str,
    onset_novelty: object | None,
    rms_curve: object | None,
    spectral_centroid: object | None,
    times: object | None,
) -> _Features:
    duration = max(0.0, end_s - start_s)
    if duration <= 0.0:
        return _Features(section_label=section_label)

    attacks = _group_attacks(events) if events else _group_note_attacks(notes)
    pitches = [n.pitch for n in notes]
    if not pitches and events:
        pitches = [e.pitch for e in events]

    note_count = (
        len(notes)
        if notes
        else sum(1 for event in events if event.is_onset and not event.is_offset)
    )
    notes_per_sec = note_count / duration if duration > 0 else 0.0
    attack_count = len(attacks)
    mean_polyphony = (
        sum(len(a) for a in attacks) / attack_count if attack_count else 1.0
    )
    simultaneous_ratio = (
        sum(1 for a in attacks if len(a) >= 2) / attack_count if attack_count else 0.0
    )
    pitch_spans = [
        max(a) - min(a) for a in attacks if len(a) >= 2
    ]
    mean_attack_pitch_span = float(np.mean(pitch_spans)) if pitch_spans else 0.0
    pitch_range = float(max(pitches) - min(pitches)) if pitches else 0.0
    unique_pitch_ratio = (
        len(set(pitches)) / len(pitches) if pitches else 0.0
    )
    chord_tone_ratio = _chord_tone_ratio(notes, chord_events)
    ioi_regularity = _ioi_regularity([n.start_time for n in notes])
    technique_tags = sorted(
        {tag for note in notes for tag in note.technique if isinstance(tag, str) and tag}
    )
    technique_ratio = (
        sum(1 for n in notes if n.technique) / len(notes) if notes else 0.0
    )
    onset_density = _onset_density(
        times, onset_novelty, start_s, end_s
    )
    rms_mean = _curve_mean(times, rms_curve, start_s, end_s)
    centroid_mean = _curve_mean(times, spectral_centroid, start_s, end_s)

    evidence = {
        "duration_s": duration,
        "note_count": float(note_count),
        "notes_per_sec": notes_per_sec,
        "attack_count": float(attack_count),
        "mean_polyphony": mean_polyphony,
        "simultaneous_attack_ratio": simultaneous_ratio,
        "mean_attack_pitch_span": mean_attack_pitch_span,
        "pitch_range": pitch_range,
        "unique_pitch_ratio": unique_pitch_ratio,
        "chord_tone_ratio": chord_tone_ratio,
        "ioi_regularity": ioi_regularity,
        "technique_ratio": technique_ratio,
        "onset_density": onset_density,
        "rms_mean": rms_mean,
        "centroid_mean": centroid_mean,
    }

    return _Features(
        duration_s=duration,
        note_count=note_count,
        notes_per_sec=notes_per_sec,
        attack_count=attack_count,
        mean_polyphony=mean_polyphony,
        simultaneous_attack_ratio=simultaneous_ratio,
        mean_attack_pitch_span=mean_attack_pitch_span,
        pitch_range=pitch_range,
        unique_pitch_ratio=unique_pitch_ratio,
        chord_tone_ratio=chord_tone_ratio,
        ioi_regularity=ioi_regularity,
        technique_ratio=technique_ratio,
        onset_density=onset_density,
        rms_mean=rms_mean,
        centroid_mean=centroid_mean,
        section_label=section_label,
        technique_tags=technique_tags,
        evidence=evidence,
    )


def _group_attacks(events: list[Mt3Event]) -> list[list[int]]:
    onsets = sorted(
        (
            e
            for e in events
            if e.is_onset
            and not e.is_offset
            and e.program in _GUITAR_PROGRAMS
            and e.confidence >= _MIN_EVENT_CONFIDENCE
        ),
        key=lambda e: e.time,
    )
    return _group_onset_pitches([(e.time, e.pitch) for e in onsets])


def _group_note_attacks(notes: list[SoloNote]) -> list[list[int]]:
    return _group_onset_pitches([(n.start_time, n.pitch) for n in notes])


def _group_onset_pitches(items: list[tuple[float, int]]) -> list[list[int]]:
    if not items:
        return []
    items = sorted(items, key=lambda x: x[0])
    groups: list[list[int]] = []
    current: list[int] = [items[0][1]]
    group_start = items[0][0]
    for t, pitch in items[1:]:
        if t - group_start <= _ATTACK_WINDOW_S:
            current.append(pitch)
        else:
            groups.append(current)
            current = [pitch]
            group_start = t
    groups.append(current)
    return groups


def _chord_tone_ratio(
    notes: list[SoloNote],
    chord_events: list[tuple[float, str]],
) -> float:
    if not notes or not chord_events:
        return 0.0
    hits = 0
    for note in notes:
        chord = _chord_at(chord_events, note.start_time)
        if not chord:
            continue
        if (note.pitch % 12) in _chord_pitch_classes(chord):
            hits += 1
    return hits / len(notes)


def _chord_at(events: list[tuple[float, str]], time_s: float) -> str | None:
    chord: str | None = None
    for timestamp, symbol in events:
        if timestamp <= time_s:
            chord = symbol
        else:
            break
    if not chord or chord == "N":
        return None
    return chord


def _chord_pitch_classes(symbol: str) -> set[int]:
    parts = symbol.split(":", 1)
    root = _normalize_root(parts[0])
    if root is None:
        return set()
    quality = parts[1].strip().lower() if len(parts) > 1 else "maj"
    intervals = CHORD_INTERVALS.get(quality)
    if intervals is None:
        intervals = CHORD_INTERVALS["maj"]
    return {(root + interval) % 12 for interval in intervals}


def _normalize_root(root: str) -> int | None:
    root = root.strip()
    if root in _FLAT_TO_SHARP:
        root = _FLAT_TO_SHARP[root]
    return _ROOTS.get(root)


def _ioi_regularity(onset_times: list[float]) -> float:
    if len(onset_times) < 3:
        return 0.0
    sorted_times = sorted(onset_times)
    iois = np.diff(sorted_times)
    iois = iois[iois > 1e-6]
    if iois.size < 2:
        return 0.0
    mean = float(iois.mean())
    if mean <= 1e-6:
        return 0.0
    cv = float(iois.std() / mean)
    return _clamp(1.0 - min(1.0, cv))


def _onset_density(
    times: object | None,
    curve: object | None,
    start_s: float,
    end_s: float,
) -> float:
    if times is None or curve is None:
        return 0.0
    t = np.asarray(times, dtype=float)
    c = np.asarray(curve, dtype=float)
    if t.size == 0 or c.size == 0 or t.size != c.size:
        return 0.0
    mask = (t >= start_s) & (t < end_s)
    if not np.any(mask):
        return 0.0
    section = c[mask]
    section_t = t[mask]
    if section.size < 3:
        return 0.0
    threshold = float(section.mean() + 0.5 * section.std())
    peaks = 0
    for i in range(1, section.size - 1):
        if section[i] >= threshold and section[i] >= section[i - 1] and section[i] >= section[i + 1]:
            peaks += 1
    duration = max(1e-6, float(section_t[-1] - section_t[0]))
    return peaks / duration


def _curve_mean(
    times: object | None,
    curve: object | None,
    start_s: float,
    end_s: float,
) -> float:
    if times is None or curve is None:
        return 0.0
    t = np.asarray(times, dtype=float)
    c = np.asarray(curve, dtype=float)
    if t.size == 0 or c.size == 0 or t.size != c.size:
        return 0.0
    mask = (t >= start_s) & (t < end_s)
    if not np.any(mask):
        return 0.0
    return float(c[mask].mean())


def _technique_tags(features: _Features, playing_style: str) -> list[str]:
    tags = list(features.technique_tags)
    style_tag = {
        "strummed": "strumming",
        "fingerpicked_arpeggiated": "fingerpicking",
        "picked": "picking",
        "muted": "muted_attacks",
        "mixed": "mixed_technique",
    }.get(playing_style)
    if style_tag and style_tag not in tags:
        tags.append(style_tag)
    return tags


def _confidence(
    top_score: float,
    scores: dict[str, float],
    features: _Features,
) -> float:
    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]
    evidence = min(1.0, (features.note_count + features.attack_count) / 24.0)
    return round(_clamp(0.35 * top_score + 0.45 * margin + 0.20 * evidence), 3)


def _summarize_profiles(
    sections: list[LessonSectionStub],
    profiles: list[PerformanceProfile],
    *,
    song_duration_s: float | None = None,
) -> PerformanceProfile:
    weights: dict[str, float] = {}
    technique_counts: dict[str, int] = {}
    total = 0.0
    for index, profile in enumerate(profiles):
        start_s, end_s = _section_bounds(sections, index, fallback_end=song_duration_s)
        weight = max(0.0, end_s - start_s)
        total += weight
        if profile.playing_style != "unknown":
            weights[profile.playing_style] = weights.get(profile.playing_style, 0.0) + weight
        for tag in profile.technique_tags:
            technique_counts[tag] = technique_counts.get(tag, 0) + 1

    if not weights:
        return PerformanceProfile()

    style = max(weights, key=weights.get)
    role_by_style = {
        "strummed": "rhythm",
        "fingerpicked_arpeggiated": "chord_melody",
        "picked": "lead_solo",
        "mixed": "mixed",
    }
    return PerformanceProfile(
        playing_style=style,  # type: ignore[arg-type]
        part_role=role_by_style.get(style, "unknown"),  # type: ignore[arg-type]
        technique_tags=sorted(technique_counts),
        confidence=round(weights[style] / total, 3) if total > 0 else 0.0,
        source="heuristic",
        evidence={"weighted_share": round(weights[style] / total, 3) if total > 0 else 0.0},
    )


def _section_bounds(
    sections: list[LessonSectionStub],
    index: int,
    *,
    fallback_end: float | None = None,
) -> tuple[float, float]:
    section = sections[index]
    start = section.start_time_seconds
    if start is None:
        start = 0.0
    end = section.end_time_seconds
    if end is None or float(end) <= float(start):
        next_start = sections[index + 1].start_time_seconds if index + 1 < len(sections) else None
        if next_start is not None and float(next_start) > float(start):
            end = next_start
        elif fallback_end is not None and float(fallback_end) > float(start):
            end = fallback_end
        else:
            end = start
    return float(start), float(max(start, end))


def _section_chord_events(
    section: LessonSectionStub,
    global_timeline: ChordTimeline | None,
    start_s: float,
    end_s: float,
) -> list[tuple[float, str]]:
    raw = getattr(section, "chord_timeline", None)
    events = _events_from_timeline(raw) if raw is not None else []
    if not events and global_timeline is not None:
        events = [(e.timestamp, e.chord) for e in global_timeline.events]
    return [
        (float(t), str(c))
        for t, c in events
        if start_s <= float(t) < end_s
    ]


def _events_from_timeline(raw: object) -> list[tuple[float, str]]:
    events: object
    if isinstance(raw, dict):
        events = raw.get("events") or []
    else:
        events = getattr(raw, "events", [])
    if not events:
        return []
    out: list[tuple[float, str]] = []
    for event in events:
        if isinstance(event, dict):
            timestamp = event.get("timestamp")
            chord = event.get("chord")
        else:
            timestamp = getattr(event, "timestamp", None)
            chord = getattr(event, "chord", None)
        if isinstance(timestamp, (int, float)) and isinstance(chord, str):
            out.append((float(timestamp), chord))
    return out


def _section_solo_notes(
    section: LessonSectionStub,
    global_notes: SoloNotes | None,
    start_s: float,
    end_s: float,
) -> list[SoloNote]:
    raw = getattr(section, "solo_notes", None)
    notes = _notes_from_raw(raw) if raw is not None else []
    if not notes and global_notes is not None:
        notes = list(global_notes.notes)
    return [
        note
        for note in notes
        if start_s <= note.start_time < end_s
    ]


def _notes_from_raw(raw: object) -> list[SoloNote]:
    if isinstance(raw, SoloNotes):
        return list(raw.notes)
    if isinstance(raw, dict):
        items = raw.get("notes") or []
    else:
        items = getattr(raw, "notes", [])
    out: list[SoloNote] = []
    for item in items or []:
        if isinstance(item, SoloNote):
            out.append(item)
        elif isinstance(item, dict):
            try:
                out.append(SoloNote.model_validate(item))
            except Exception:
                continue
    return out


def _section_mt3_events(
    stream: Mt3EventStream | None,
    start_s: float,
    end_s: float,
) -> list[Mt3Event]:
    if stream is None:
        return []
    return [
        event
        for event in stream.events
        if start_s <= event.time < end_s
    ]


def _squash(value: float) -> float:
    if value <= 0.0:
        return 0.0
    return value / (1.0 + value)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
