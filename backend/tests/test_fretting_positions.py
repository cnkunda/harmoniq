"""Tests for W4 candidate positions and the allCellsForMidi baseline."""

from __future__ import annotations

from app.fretting.positions import (
    Position,
    baseline_position,
    candidates_for_pitch,
    is_playable_pitch,
)
from app.fretting.tuning import standard


class TestBaselineParity:
    """Mirror src/music/fretboardCell.ts: lowest fret, then high E first."""

    def test_open_low_e(self) -> None:
        assert baseline_position(40) == Position(6, 0)

    def test_middle_c(self) -> None:
        # 60 has no high-E position; B string fret 1 is the lowest.
        assert baseline_position(60) == Position(2, 1)

    def test_open_high_e(self) -> None:
        assert baseline_position(64) == Position(1, 0)

    def test_g4_prefers_high_e_over_b_string(self) -> None:
        # G4: high E fret 3, B fret 8, G fret 12, ...
        assert baseline_position(67) == Position(1, 3)

    def test_high_note(self) -> None:
        assert baseline_position(84) == Position(1, 20)

    def test_out_of_range(self) -> None:
        assert baseline_position(39) is None
        assert baseline_position(89) is None
        assert not is_playable_pitch(39)
        assert not is_playable_pitch(89)


class TestCandidates:
    def test_all_positions_for_g4(self) -> None:
        positions = candidates_for_pitch(67, standard())
        assert positions == [
            Position(1, 3),
            Position(2, 8),
            Position(3, 12),
            Position(4, 17),
            Position(5, 22),
        ]

    def test_capo_shifts_candidates(self) -> None:
        positions = candidates_for_pitch(67, standard(capo=3))
        assert positions[0] == Position(1, 0)
        assert Position(2, 5) in positions

    def test_max_fret_filter(self) -> None:
        assert candidates_for_pitch(88, standard(), max_fret=12) == []
        assert candidates_for_pitch(76, standard(), max_fret=12) == [
            Position(1, 12)
        ]

    def test_rounds_fractional_pitch(self) -> None:
        assert candidates_for_pitch(67.4, standard())[0] == Position(1, 3)
        assert candidates_for_pitch(67.6, standard())[0] == Position(1, 4)
