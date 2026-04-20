"""
Regression tests for commit 63 skill-mutation EMA (mirrors `src/session/skillMutator.ts`).

The app applies these formulas client-side; this file ensures backend fixtures / docs
stay aligned with the TypeScript source of truth.
"""

from __future__ import annotations

import pytest

# Must match `SKILL_MUTATION_EMA_OLD` / `SKILL_MUTATION_EMA_SESSION` in skillMutator.ts
EMA_OLD = 0.85
EMA_SESS = 0.15
ROLL_WINDOW = 3
ROLL_WEAK_MAX = 0.5


def apply_skill_ema(old: float, session: float) -> float:
    o = old if old == old else 0.0
    s = max(0.0, min(1.0, session if session == session else 0.0))
    n = o * EMA_OLD + s * EMA_SESS
    return max(0.0, min(1.0, n))


def session_accuracy_from_labels(labels: list[str]) -> float | None:
    scored = [x for x in labels if x != "ignored"]
    if not scored:
        return None
    good = sum(1 for x in scored if x in ("hit", "close", "vibrato"))
    return good / len(scored)


def rolling_sessions_weak(rolling: list[float]) -> bool:
    if len(rolling) < ROLL_WINDOW:
        return False
    tail = rolling[-ROLL_WINDOW:]
    return sum(tail) / len(tail) < ROLL_WEAK_MAX


def test_ema_single_zero_session_preserves_strong_node_above_40pct() -> None:
    """Acceptance: single 0% session on a strong node does not drop weight below 40%."""
    nxt = apply_skill_ema(0.95, 0.0)
    assert nxt >= 0.4


def test_session_accuracy_miss_heavy_matches_bad_performance() -> None:
    labels = ["miss"] * 7 + ["hit"] * 3
    assert session_accuracy_from_labels(labels) == pytest.approx(0.3)


def test_three_session_rolling_weak() -> None:
    assert rolling_sessions_weak([0.49, 0.49]) is False
    assert rolling_sessions_weak([0.49, 0.49, 0.49]) is True


def test_expected_delta_fixture() -> None:
    """Known hit/miss pattern → expected EMA on top of a fixed prior score."""
    old = 0.9
    labels = ["miss"] * 7 + ["hit"] * 3
    sess = session_accuracy_from_labels(labels)
    assert sess is not None
    new = apply_skill_ema(old, sess)
    assert new < old
    assert 0.74 < new < 0.82
