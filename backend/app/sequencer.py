"""Deterministic practice plan assembly (commit 70) — slot order, durations, ZPD song pick."""

from __future__ import annotations

from typing import Any

from app.coach import generate_practice_plan_intros, template_practice_plan_intros
from app.curriculum import suggest_next_session
from app.exercises.warmup_generator import generate_warmup
from app.schemas import DrillSlot, LessonJSON, PlayerProfile, PracticePlan, SlotType, WarmupPlan

_TECHNIQUE_LABEL: dict[str, str] = {
    "bending": "Bending",
    "vibrato": "Vibrato",
    "timing": "Timing",
    "phrasing": "Phrasing",
    "pitch": "Pitch",
}


def _top_technique_focus(profile: PlayerProfile | None) -> str:
    if profile and profile.weak_areas:
        w = (profile.weak_areas[0] or "").strip().lower()
        if w:
            return _TECHNIQUE_LABEL.get(w, w.replace("_", " ").title())
    return "Timing"


def _song_section_title(lesson: LessonJSON) -> str:
    title = (lesson.song_title or "Library song").strip() or "Library song"
    sec0 = lesson.sections[0] if lesson.sections else None
    label = ""
    if sec0 is not None:
        label = (getattr(sec0, "label", None) or "").strip()
    if label:
        return f"{title} — {label}"
    return f"{title} — section work"


def _comfort_bpm_low(profile: PlayerProfile) -> int:
    taste = profile.taste_profile
    if taste and taste.bpm_comfort_range and len(taste.bpm_comfort_range) > 0:
        return int(taste.bpm_comfort_range[0])
    return 80


def _scale_warmup_plan_to_duration(wp: WarmupPlan, target_sec: int) -> WarmupPlan:
    """Shrink or stretch exercise seconds so the opener fits a smaller slot budget."""
    cur = wp.total_duration_seconds
    if cur <= 0 or target_sec >= cur:
        return wp
    factor = target_sec / cur
    secs = [max(30, int(round(e.duration_seconds * factor))) for e in wp.exercises]
    drift = target_sec - sum(secs)
    secs[-1] = max(30, secs[-1] + drift)
    new_ex = [e.model_copy(update={"duration_seconds": secs[i]}) for i, e in enumerate(wp.exercises)]
    return WarmupPlan(exercises=new_ex, total_duration_seconds=sum(e.duration_seconds for e in new_ex))


def generate_practice_plan(
    *,
    player_profile: PlayerProfile | None,
    library_lessons: list[LessonJSON],
    duration_minutes: int = 25,
    skip_llm: bool = False,
) -> PracticePlan:
    """Build ordered drill slots; Claude hydrates one-sentence coach_intro per slot (batched)."""
    total_sec = max(600, min(7200, int(duration_minutes) * 60))
    profile = player_profile or PlayerProfile()
    lib = [l for l in library_lessons if (l.job_id or "").strip()]
    n_lib = len(lib)
    seed = n_lib + len(profile.weak_areas or []) * 17 + int(duration_minutes) * 3
    comfort = _comfort_bpm_low(profile)
    wp = generate_warmup(profile, profile.taste_profile, session_bpm=comfort, seed=seed)

    slots_outline: list[dict[str, Any]] = []

    if n_lib < 2:
        w = min(wp.total_duration_seconds, total_sec - 120)
        if w < wp.total_duration_seconds:
            wp = _scale_warmup_plan_to_duration(wp, w)
        fj = total_sec - w
        slots_outline.append(
            {
                "slot_type": "warmup",
                "title": "Session warm-up",
                "duration_seconds": w,
                "exercise_ref": "warmup_session",
                "technique_focus": None,
                "lesson_ref": None,
                "song_title": None,
                "warmup_plan": wp.model_dump(mode="json"),
            },
        )
        slots_outline.append(
            {
                "slot_type": "free_jam",
                "title": "Free jam",
                "duration_seconds": fj,
                "exercise_ref": None,
                "technique_focus": None,
                "lesson_ref": None,
                "song_title": None,
            },
        )
    else:
        old_w = min(300, max(180, int(total_sec * 0.16)))
        t = min(360, max(240, int(total_sec * 0.20)))
        song = max(240, int(total_sec * 0.38))
        fj = total_sec - old_w - t - song
        if fj < 120:
            shift = 120 - fj
            fj = 120
            song = max(180, song - shift)

        tech_label = _top_technique_focus(profile)
        ranked = suggest_next_session(profile, lib)
        if not ranked:
            raise RuntimeError("practice_plan: suggest_next_session returned empty despite non-empty library")
        pick = ranked[0]
        lesson = next((x for x in lib if (x.job_id or "").strip() == pick.job_id), lib[0])
        job_id = (lesson.job_id or "").strip()
        if not job_id:
            raise RuntimeError("practice_plan: chosen lesson missing job_id")

        w = wp.total_duration_seconds
        delta = w - old_w
        fj = fj - delta
        if fj < 120:
            shortfall = 120 - fj
            fj = 120
            song = max(180, song - shortfall)

        slots_outline.append(
            {
                "slot_type": "warmup",
                "title": "Session warm-up",
                "duration_seconds": w,
                "exercise_ref": "warmup_session",
                "technique_focus": None,
                "lesson_ref": None,
                "song_title": None,
                "warmup_plan": wp.model_dump(mode="json"),
            },
        )
        slots_outline.append(
            {
                "slot_type": "technique",
                "title": f"{tech_label} drill",
                "duration_seconds": t,
                "exercise_ref": None,
                "technique_focus": (profile.weak_areas[0] if profile.weak_areas else "timing"),
                "lesson_ref": None,
                "song_title": None,
            },
        )
        slots_outline.append(
            {
                "slot_type": "song_section",
                "title": _song_section_title(lesson),
                "duration_seconds": song,
                "exercise_ref": None,
                "technique_focus": None,
                "lesson_ref": job_id,
                "song_title": (lesson.song_title or "").strip() or None,
            },
        )
        slots_outline.append(
            {
                "slot_type": "free_jam",
                "title": "Free jam",
                "duration_seconds": fj,
                "exercise_ref": None,
                "technique_focus": None,
                "lesson_ref": None,
                "song_title": None,
            },
        )

    intros = (
        template_practice_plan_intros(slots_outline, profile)
        if skip_llm
        else generate_practice_plan_intros(slots_outline, profile)
    )
    if len(intros) != len(slots_outline):
        raise RuntimeError(
            f"practice_plan: intro count mismatch ({len(intros)} != {len(slots_outline)})",
        )

    slots: list[DrillSlot] = []
    for meta, intro in zip(slots_outline, intros, strict=True):
        st: SlotType = meta["slot_type"]
        wplan_raw = meta.get("warmup_plan")
        wplan = WarmupPlan.model_validate(wplan_raw) if isinstance(wplan_raw, dict) else None
        slots.append(
            DrillSlot(
                slot_type=st,
                duration_seconds=int(meta["duration_seconds"]),
                title=str(meta["title"]),
                coach_intro=intro,
                lesson_ref=meta.get("lesson_ref"),
                exercise_ref=meta.get("exercise_ref"),
                technique_focus=meta.get("technique_focus"),
                warmup_plan=wplan,
            ),
        )

    total = sum(s.duration_seconds for s in slots)
    return PracticePlan(slots=slots, total_duration_seconds=total)
