"""Deterministic mid-session practice-plan adaptation (commit 162)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import (
    DrillSlot,
    PlanAdaptation,
    PlanAdaptResponse,
    PlanSlotPerformance,
    PlanSlotResult,
    PracticePlan,
)

_LOW_ACCURACY = 0.5
_HIGH_ACCURACY = 0.9
_REMEDIATION_SECONDS = 180
_MIN_FREE_JAM_SECONDS = 120


def _plan_total(plan: PracticePlan) -> int:
    return sum(slot.duration_seconds for slot in plan.slots)


def _reclaim_overrun(plan: PracticePlan, start_index: int, overrun: int) -> int:
    """Trim the first later free-jam slot, never below the 120s floor."""
    if overrun <= 0:
        return 0
    reclaimed = 0
    for slot in plan.slots[start_index + 1 :]:
        if slot.slot_type != "free_jam":
            continue
        available = max(0, slot.duration_seconds - _MIN_FREE_JAM_SECONDS)
        take = min(available, overrun - reclaimed)
        if take <= 0:
            continue
        slot.duration_seconds -= take
        reclaimed += take
        if reclaimed >= overrun:
            break
    return reclaimed


def _remediation_slot(current: DrillSlot) -> DrillSlot:
    title = f"Remediation — {current.title}"[:200]
    return DrillSlot(
        slot_id=str(uuid4()),
        slot_type=current.slot_type,
        duration_seconds=_REMEDIATION_SECONDS,
        title=title,
        coach_intro="Targeted retry of this drill at a slower, cleaner pace.",
        lesson_ref=current.lesson_ref,
        exercise_ref=current.exercise_ref,
        technique_focus=current.technique_focus,
        warmup_plan=current.warmup_plan.model_copy(deep=True) if current.warmup_plan is not None else None,
        difficulty=1,
        intent="remediation",
        target_skill=current.target_skill,
        remediation_for_slot_id=current.slot_id,
    )


def adapt_practice_plan(
    plan: PracticePlan,
    slot_index: int,
    performance: PlanSlotPerformance,
) -> PlanAdaptResponse:
    """Insert remediation after a weak slot, or skip a strictly easier next slot."""
    if slot_index < 0 or slot_index >= len(plan.slots):
        raise ValueError(f"slot_index {slot_index} is outside plan slots")
    current = plan.slots[slot_index]
    if performance.slot_id != current.slot_id:
        raise ValueError(
            f"slot_performance.slot_id {performance.slot_id!r} does not match plan slot {current.slot_id!r}",
        )

    slot_result = PlanSlotResult(
        slot_id=current.slot_id,
        slot_type=current.slot_type,
        title=current.title,
        accuracy=performance.accuracy,
        timing=performance.timing,
        confidence=performance.confidence,
        completion=performance.completion,
        completed_at=datetime.now(timezone.utc),
    )

    adapted = plan.model_copy(deep=True)
    original_total = _plan_total(adapted)
    adaptation: PlanAdaptation | None = None

    can_adapt = (
        performance.completion
        and performance.accuracy is not None
        and performance.confidence != "low"
    )

    if can_adapt and performance.accuracy < _LOW_ACCURACY:
        next_slot = adapted.slots[slot_index + 1] if slot_index + 1 < len(adapted.slots) else None
        already_remediated = (
            next_slot is not None
            and next_slot.intent == "remediation"
            and next_slot.remediation_for_slot_id == current.slot_id
        )
        if slot_index < len(adapted.slots) - 1 and current.intent != "remediation" and not already_remediated:
            remediation = _remediation_slot(current)
            adapted.slots.insert(slot_index + 1, remediation)
            _reclaim_overrun(adapted, slot_index, _REMEDIATION_SECONDS)
            adapted.total_duration_seconds = _plan_total(adapted)
            adaptation = PlanAdaptation(
                slot_id=current.slot_id,
                action="insert_remediation",
                reason=f"Accuracy {round(performance.accuracy * 100)}% is below 50%; added a 3-minute remediation.",
                original_duration_seconds=original_total,
                new_duration_seconds=adapted.total_duration_seconds,
                inserted_slot_id=remediation.slot_id,
            )

    if can_adapt and adaptation is None and performance.accuracy > _HIGH_ACCURACY:
        next_slot = adapted.slots[slot_index + 1] if slot_index + 1 < len(adapted.slots) else None
        if next_slot is not None and next_slot.difficulty < current.difficulty:
            adapted.slots.pop(slot_index + 1)
            adapted.total_duration_seconds = _plan_total(adapted)
            adaptation = PlanAdaptation(
                slot_id=current.slot_id,
                action="skip_easier",
                reason=f"Accuracy {round(performance.accuracy * 100)}% is above 90%; skipped an easier next slot.",
                original_duration_seconds=original_total,
                new_duration_seconds=adapted.total_duration_seconds,
            )

    if adaptation is None:
        adapted.total_duration_seconds = _plan_total(adapted)

    return PlanAdaptResponse(
        plan=adapted,
        next_slot_index=slot_index + 1,
        slot_result=slot_result,
        adaptation=adaptation,
    )
