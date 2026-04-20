"""Deterministic curriculum scoring for commit 65 (ZPD-aware next suggestion)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.schemas import LessonJSON, PlayerProfile


_WEAK_AREA_TOKENS: dict[str, tuple[str, ...]] = {
    "bending": ("bend", "bending"),
    "vibrato": ("vibrato",),
    "timing": ("alternate-picking", "alternate picking", "timing"),
    "phrasing": ("slide", "legato", "phrasing"),
    "pitch": ("pitch", "intonation"),
}

_TECHNIQUE_SKILL_LABEL: dict[str, str] = {
    "bend_accuracy": "Bending",
    "vibrato_control": "Vibrato",
    "timing": "Timing",
    "phrasing": "Phrasing",
    "pitch_accuracy": "Pitch",
}


@dataclass(frozen=True)
class CurriculumSuggestion:
    job_id: str
    reason_label: str
    technique_focus: str
    score: float


def _extract_section_techniques(lesson: LessonJSON) -> set[str]:
    out: set[str] = set()
    for sec in lesson.sections or []:
        raw = getattr(sec, "technique_tags", None) or getattr(sec, "techniques", None) or getattr(sec, "technique_hints", None)
        if isinstance(raw, str):
            v = raw.strip().lower()
            if v:
                out.add(v)
            continue
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    out.add(item.strip().lower())
    return out


def _lesson_style(lesson: LessonJSON) -> str:
    return (lesson.style_label or "").strip().lower()


def _dominant_style(lessons: Iterable[LessonJSON]) -> str | None:
    freq: dict[str, int] = {}
    for l in lessons:
        s = _lesson_style(l)
        if not s:
            continue
        freq[s] = freq.get(s, 0) + 1
    if not freq:
        return None
    return sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _matched_weak_areas(weak_areas: list[str], techniques: set[str]) -> list[str]:
    matched: list[str] = []
    for wa in weak_areas:
        key = wa.strip().lower()
        if not key:
            continue
        tokens = _WEAK_AREA_TOKENS.get(key, (key,))
        if any(any(tok in t for t in techniques) for tok in tokens):
            matched.append(key)
    return matched


def _lesson_difficulty01(lesson: LessonJSON, techniques: set[str]) -> float:
    tempo = float(lesson.tempo or 100.0)
    tempo01 = max(0.0, min(1.0, (tempo - 70.0) / 120.0))
    confs = [float(getattr(sec, "confidence")) for sec in lesson.sections if getattr(sec, "confidence", None) is not None]
    conf01 = sum(confs) / len(confs) if confs else 0.6
    tech01 = min(1.0, len(techniques) / 5.0)
    return max(0.0, min(1.0, conf01 * 0.45 + tempo01 * 0.35 + tech01 * 0.2))


def _taste_affinity_boost(techniques: set[str], affinity: list[str]) -> float:
    """Small deterministic ZPD nudge from commit 68 `TasteProfile.technique_affinity`."""
    if not techniques or not affinity:
        return 0.0
    blob = " ".join(sorted(techniques)).lower()
    hits = 0
    for a in affinity:
        al = (a or "").strip().lower()
        if al and al in blob:
            hits += 1
    return min(0.15, 0.05 * float(hits))


def suggest_next_session(player_profile: PlayerProfile | None, library_lessons: list[LessonJSON]) -> list[CurriculumSuggestion]:
    if not library_lessons:
        return []

    profile = player_profile or PlayerProfile()
    weak_areas = [w.strip().lower() for w in (profile.weak_areas or []) if isinstance(w, str) and w.strip()]
    weak_count = len(weak_areas)
    dominant_style = _dominant_style(library_lessons)
    taste_affinity = list(profile.taste_profile.technique_affinity) if profile.taste_profile else []
    node_scores = {n.id: float(n.score) for n in profile.skill_nodes if n.score is not None}
    skill_floor = min(node_scores.values()) if node_scores else 0.45

    out: list[CurriculumSuggestion] = []
    for lesson in library_lessons:
        job_id = (lesson.job_id or "").strip()
        if not job_id:
            continue
        techniques = _extract_section_techniques(lesson)
        matched_weak = _matched_weak_areas(weak_areas, techniques)
        overlap = (len(matched_weak) / weak_count) if weak_count > 0 else 0.0

        style = _lesson_style(lesson)
        style_match = 1.0 if dominant_style and style and style == dominant_style else 0.0
        taste_style = (profile.taste_profile.style_label or "").strip().lower() if profile.taste_profile else ""
        if taste_style and style and style == taste_style:
            style_match = max(style_match, 0.85)

        lesson_diff = _lesson_difficulty01(lesson, techniques)
        floor_penalty = 0.2 if lesson_diff > (skill_floor + 0.35) else 1.0
        mastered_penalty = 1.0
        if node_scores and matched_weak:
            if all(node_scores.get("bend_accuracy", 0.0) > 0.85 for m in matched_weak if m == "bending"):
                mastered_penalty = 0.2
        novelty = min(mastered_penalty, floor_penalty)

        aff_boost = _taste_affinity_boost(techniques, taste_affinity)
        score = overlap * 0.5 + style_match * 0.3 + novelty * 0.2 + aff_boost
        focus = (
            _TECHNIQUE_SKILL_LABEL.get("bend_accuracy")
            if "bending" in matched_weak
            else (_TECHNIQUE_SKILL_LABEL.get("vibrato_control") if "vibrato" in matched_weak else "Technique")
        )
        if matched_weak:
            reason = f"Targets weak area: {matched_weak[0]}."
        elif style_match > 0:
            reason = f"Style-matched motivation: {style or 'your common style'}."
        else:
            reason = "Balanced next step to build range without overload."

        out.append(
            CurriculumSuggestion(
                job_id=job_id,
                reason_label=reason,
                technique_focus=focus,
                score=round(score, 6),
            )
        )

    return sorted(out, key=lambda s: (-s.score, s.job_id))
