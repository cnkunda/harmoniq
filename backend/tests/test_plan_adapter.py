"""Commit 162: deterministic mid-session plan adaptation."""

from __future__ import annotations

import pytest

from app.plan_adapter import adapt_practice_plan
from app.schemas import DrillSlot, PlanSlotPerformance, PracticePlan


def _slot(
    slot_id: str,
    *,
    slot_type: str = "technique",
    duration: int = 240,
    difficulty: int = 2,
    intent: str = "practice",
) -> DrillSlot:
    return DrillSlot(
        slot_id=slot_id,
        slot_type=slot_type,
        duration_seconds=duration,
        title=f"{slot_id} title",
        difficulty=difficulty,
        intent=intent,
    )


def _plan(*, free_jam_duration: int = 300) -> PracticePlan:
    slots = [
        _slot("warmup", slot_type="warmup", duration=180, difficulty=3),
        _slot("technique", duration=240, difficulty=2),
        _slot("song", slot_type="song_section", duration=600, difficulty=3),
        _slot("free", slot_type="free_jam", duration=free_jam_duration, difficulty=2),
    ]
    return PracticePlan(
        plan_id="plan-1",
        slots=slots,
        total_duration_seconds=sum(s.duration_seconds for s in slots),
    )


def _performance(
    slot_id: str,
    accuracy: float | None,
    *,
    completion: bool = True,
    confidence: str | None = "high",
    slot_type: str = "technique",
) -> PlanSlotPerformance:
    return PlanSlotPerformance(
        slot_id=slot_id,
        slot_type=slot_type,
        title=f"{slot_id} title",
        accuracy=accuracy,
        timing=0.8,
        confidence=confidence,
        completion=completion,
    )


def test_low_accuracy_inserts_remediation_after_current_slot() -> None:
    plan = _plan()
    result = adapt_practice_plan(plan, 1, _performance("technique", 0.4))

    assert result.adaptation is not None
    assert result.adaptation.action == "insert_remediation"
    assert result.next_slot_index == 2
    assert len(result.plan.slots) == 5
    remediation = result.plan.slots[2]
    assert remediation.slot_id == result.adaptation.inserted_slot_id
    assert remediation.intent == "remediation"
    assert remediation.remediation_for_slot_id == "technique"
    assert remediation.duration_seconds == 180
    assert remediation.difficulty == 1
    assert result.plan.slots[-1].duration_seconds == 120
    assert sum(s.duration_seconds for s in result.plan.slots) == 1320


def test_low_accuracy_keeps_overrun_when_free_jam_at_floor() -> None:
    plan = _plan(free_jam_duration=120)
    result = adapt_practice_plan(plan, 1, _performance("technique", 0.49))

    assert result.adaptation is not None
    assert result.plan.slots[-1].duration_seconds == 120
    assert result.plan.total_duration_seconds == 1320
    assert result.adaptation.original_duration_seconds == 1140
    assert result.adaptation.new_duration_seconds == 1320


def test_low_accuracy_on_final_slot_does_not_insert() -> None:
    plan = _plan()
    result = adapt_practice_plan(
        plan,
        3,
        _performance("free", 0.2, slot_type="free_jam"),
    )

    assert result.adaptation is None
    assert len(result.plan.slots) == 4
    assert result.next_slot_index == 4


def test_low_confidence_or_incomplete_or_missing_accuracy_does_not_adapt() -> None:
    plan = _plan()
    for performance in (
        _performance("technique", 0.2, confidence="low"),
        _performance("technique", 0.2, completion=False),
        _performance("technique", None),
    ):
        result = adapt_practice_plan(plan, 1, performance)
        assert result.adaptation is None
        assert len(result.plan.slots) == 4


def test_current_remediation_does_not_nest_another_remediation() -> None:
    plan = _plan()
    plan.slots[1].intent = "remediation"
    result = adapt_practice_plan(plan, 1, _performance("technique", 0.2))
    assert result.adaptation is None


def test_high_accuracy_skips_only_strictly_easier_next_slot() -> None:
    plan = _plan()
    result = adapt_practice_plan(plan, 0, _performance("warmup", 0.95, slot_type="warmup"))

    assert result.adaptation is not None
    assert result.adaptation.action == "skip_easier"
    assert [s.slot_id for s in result.plan.slots] == ["warmup", "song", "free"]
    assert result.next_slot_index == 1
    assert result.plan.total_duration_seconds == 1080

    no_skip = adapt_practice_plan(plan, 1, _performance("technique", 0.95))
    assert no_skip.adaptation is None
    assert len(no_skip.plan.slots) == 4


def test_threshold_boundaries_do_not_adapt() -> None:
    plan = _plan()
    low = adapt_practice_plan(plan, 1, _performance("technique", 0.5))
    high = adapt_practice_plan(plan, 0, _performance("warmup", 0.9, slot_type="warmup"))
    assert low.adaptation is None
    assert high.adaptation is None


def test_invalid_index_or_slot_id_raises_value_error() -> None:
    plan = _plan()
    with pytest.raises(ValueError):
        adapt_practice_plan(plan, 9, _performance("technique", 0.4))
    with pytest.raises(ValueError):
        adapt_practice_plan(plan, 1, _performance("other", 0.4))
