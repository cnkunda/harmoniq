"""Tests for the Fretting-Transformer playability cost."""

from __future__ import annotations

import pytest

from app.fretting.playability import (
    DEFAULT_ALPHA,
    fret_stretch,
    locality,
    sequence_difficulty,
    transition_difficulty,
    vertical_stretch,
)
from app.fretting.positions import Position


class TestComponents:
    def test_fret_stretch_up_is_cheaper(self) -> None:
        up = fret_stretch(Position(1, 2), Position(1, 5))
        down = fret_stretch(Position(1, 5), Position(1, 2))
        assert up == pytest.approx(1.5)
        assert down == pytest.approx(2.25)

    def test_locality(self) -> None:
        assert locality(Position(1, 2), Position(1, 4)) == pytest.approx(
            DEFAULT_ALPHA * 6
        )

    def test_vertical_stretch(self) -> None:
        assert vertical_stretch(Position(1, 0), Position(1, 0)) == 0.0
        assert vertical_stretch(Position(1, 0), Position(2, 0)) == 0.25
        assert vertical_stretch(Position(1, 0), Position(3, 0)) == 0.5


class TestDifficulty:
    def test_same_position_is_zero(self) -> None:
        position = Position(1, 0)
        assert transition_difficulty(position, position) == 0.0

    def test_extreme_jump_matches_paper_range(self) -> None:
        # Open low E -> 24th fret high E is the documented maximum (18.5).
        value = transition_difficulty(Position(6, 0), Position(1, 24))
        assert value == pytest.approx(18.5)

    def test_sequence_mean(self) -> None:
        positions = [Position(1, 0), Position(1, 1)]
        # 0.5 fret stretch + 0.25 locality + 0.0 same-string vertical = 0.75
        assert sequence_difficulty(positions) == pytest.approx(0.75)

    def test_single_position(self) -> None:
        assert sequence_difficulty([Position(1, 0)]) == 0.0
        assert sequence_difficulty([]) == 0.0

    def test_negative_alpha_rejected(self) -> None:
        with pytest.raises(ValueError, match="alpha"):
            locality(Position(1, 0), Position(1, 1), alpha=-0.1)
