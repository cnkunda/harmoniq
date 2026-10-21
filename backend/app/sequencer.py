"""Deterministic practice plan assembly (commit 70) — slot order, durations, ZPD song pick; commit 76 mood adaptation."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.coach import generate_practice_plan_intros, template_practice_plan_intros
from app.curriculum import select_skill_focus, suggest_next_session
from app.exercises.warmup_generator import generate_warmup
from app.schemas import DrillSlot, LessonJSON, MoodState, PlayerProfile, PracticePlan, SlotType, WarmupPlan

_TECHNIQUE_LABEL: dict[str, str] = {
    "bending": "Bending",
    "vibrato": "Vibrato",
    "timing": "Timing",
    "phrasing": "Phrasing",
    "pitch": "Pitch",
}
_MOOD_SEED: dict[MoodState, int] = {"focused": 11, "loose": 23, "tired": 37, "on_fire": 53}


def _top_technique_focus(profile: PlayerProfile | None) -> str:
    if profile and profile.weak_areas:
        w = (profile.weak_areas[0] or "").strip().lower()
        if w:
            return _TECHNIQUE_LABEL.get(w, w.replace("_", " ").title())
    return "Timing"


def _slot_difficulty(slot_type: SlotType, intent: str, wplan: WarmupPlan | None) -> int:
    if slot_type == "technique":
        return 1 if intent in {"review", "remediation"} else 2
    if slot_type == "song_section":
        return 3
    if slot_type == "free_jam":
        return 2
    if slot_type == "warmup":
        if wplan is not None and wplan.exercises:
            return max(1, min(3, max(int(e.difficulty) for e in wplan.exercises)))
        return 2
    return 2


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


def _comfort_bpm_for_mood(comfort: int, mood: MoodState | None) -> int:
    """Commit 76: mood nudges metronome / warm-up BPM anchor without leaving playable range."""
    if mood == "tired":
        return max(50, comfort - 10)
    if mood == "on_fire":
        return min(200, comfort + 14)
    if mood == "loose":
        return max(50, comfort - 5)
    return comfort


def _budget_seconds(duration_minutes: int, mood: MoodState | None) -> int:
    base = max(600, min(7200, int(duration_minutes) * 60))
    if mood == "tired":
        return max(600, int(round(base * 0.72)))
    if mood == "loose":
        return max(600, int(round(base * 0.94)))
    if mood == "on_fire":
        return min(7200, int(round(base * 1.04)))
    return base


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
    mood: MoodState | None = None,
) -> PracticePlan:
    """Build ordered drill slots; Claude hydrates one-sentence coach_intro per slot (batched)."""
    total_sec = _budget_seconds(duration_minutes, mood)
    profile = player_profile or PlayerProfile()
    focus = select_skill_focus(profile)
    lib = [l for l in library_lessons if (l.job_id or "").strip()]
    n_lib = len(lib)
    seed = n_lib + len(profile.weak_areas or []) * 17 + int(duration_minutes) * 3 + ((_MOOD_SEED.get(mood) or 0) if mood else 0)
    comfort = _comfort_bpm_low(profile)
    session_bpm = _comfort_bpm_for_mood(comfort, mood)
    wp = generate_warmup(profile, profile.taste_profile, session_bpm=session_bpm, seed=seed)

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
        omit_technique = mood == "tired"
        old_w = min(300, max(180, int(total_sec * 0.16)))
        t = min(360, max(240, int(total_sec * 0.20)))
        tech_intent = "review" if focus is not None and focus.is_strong else "practice"
        tech_duration = max(120, int(round(t * 0.6))) if tech_intent == "review" and not omit_technique else t
        song = max(240, int(total_sec * 0.38))
        fj = total_sec - old_w - tech_duration - song
        if not omit_technique:
            if fj < 120:
                shift = 120 - fj
                fj = 120
                song = max(180, song - shift)
        else:
            song = max(240, song + t)
            fj = total_sec - old_w - song
            if fj < 120:
                shortfall = 120 - fj
                fj = 120
                song = max(180, song - shortfall)

        tech_label = focus.label if focus is not None else _top_technique_focus(profile)
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
        if not omit_technique:
            slots_outline.append(
                {
                    "slot_type": "technique",
                    "title": f"{tech_label} review" if tech_intent == "review" else f"{tech_label} drill",
                    "duration_seconds": tech_duration,
                    "exercise_ref": None,
                    "technique_focus": (focus.area if focus is not None else (profile.weak_areas[0] if profile.weak_areas else "timing")),
                    "lesson_ref": None,
                    "song_title": None,
                    "intent": tech_intent,
                    "target_skill": focus.node_id if focus is not None else None,
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
        template_practice_plan_intros(slots_outline, profile, mood=mood)
        if skip_llm
        else generate_practice_plan_intros(slots_outline, profile, mood=mood)
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
        intent = str(meta.get("intent") or "practice")
        slots.append(
            DrillSlot(
                slot_id=str(uuid4()),
                slot_type=st,
                duration_seconds=int(meta["duration_seconds"]),
                title=str(meta["title"]),
                coach_intro=intro,
                lesson_ref=meta.get("lesson_ref"),
                exercise_ref=meta.get("exercise_ref"),
                technique_focus=meta.get("technique_focus"),
                warmup_plan=wplan,
                difficulty=_slot_difficulty(st, intent, wplan),
                intent=intent,
                target_skill=meta.get("target_skill"),
            ),
        )

    total = sum(s.duration_seconds for s in slots)
    return PracticePlan(plan_id=str(uuid4()), slots=slots, total_duration_seconds=total)

