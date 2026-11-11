"""Tests for W4 tuning/capo conditioning."""

from __future__ import annotations

import pytest

from app.fretting.tuning import (
    DROP_D_OPEN_MIDI,
    NUM_STRINGS,
    STANDARD_OPEN_MIDI,
    drop_d,
    full_step_down,
    get_tuning,
    half_step_down,
    standard,
)


class TestStandardTuning:
    def test_open_pitches(self) -> None:
        tuning = standard()
        assert tuning.open_pitch(1) == 64  # high E
        assert tuning.open_pitch(6) == 40  # low E
        assert tuple(tuning.open_pitch(s) for s in range(1, 7)) == (
            64,
            59,
            55,
            50,
            45,
            40,
        )

    def test_pitch_for(self) -> None:
        tuning = standard()
        assert tuning.pitch_for(1, 0) == 64
        assert tuning.pitch_for(6, 12) == 52
        assert tuning.pitch_for(2, 3) == 62

    def test_capo_raises_every_string(self) -> None:
        tuning = standard(capo=3)
        assert tuning.open_pitch(1) == 67
        assert tuning.open_pitch(6) == 43
        assert tuning.pitch_for(1, 0) == 67

    def test_with_capo_is_immutable(self) -> None:
        base = standard()
        raised = base.with_capo(2)
        assert base.capo == 0
        assert raised.capo == 2
        assert base.open_pitch(1) == 64
        assert raised.open_pitch(1) == 66


class TestAlternateTunings:
    @pytest.mark.parametrize(
        "factory,offset",
        [(half_step_down, -1), (full_step_down, -2)],
    )
    def test_uniform_tunings(self, factory, offset: int) -> None:
        tuning = factory()
        for index, pitch in enumerate(STANDARD_OPEN_MIDI):
            assert tuning.open_pitch(index + 1) == pitch + offset

    def test_drop_d(self) -> None:
        tuning = drop_d()
        assert tuning.open_pitch(6) == 38
        assert tuple(tuning.open_midi) == DROP_D_OPEN_MIDI
        assert tuning.open_pitch(1) == 64
        assert tuning.open_pitch(5) == 45


class TestValidation:
    def test_unknown_tuning(self) -> None:
        with pytest.raises(ValueError, match="unknown tuning"):
            get_tuning("bebop")

    def test_get_tuning_standard(self) -> None:
        assert get_tuning("standard").name == "standard"

    def test_invalid_capo(self) -> None:
        with pytest.raises(ValueError, match="capo"):
            standard(capo=-1)

    def test_wrong_string_count(self) -> None:
        from app.fretting.tuning import Tuning

        with pytest.raises(ValueError, match="6 strings"):
            Tuning("bad", (64, 59, 55))

    def test_invalid_string_number(self) -> None:
        with pytest.raises(ValueError, match="string must be"):
            standard().open_pitch(0)
        with pytest.raises(ValueError, match="string must be"):
            standard().open_pitch(NUM_STRINGS + 1)

    def test_negative_fret(self) -> None:
        with pytest.raises(ValueError, match="fret"):
            standard().pitch_for(1, -1)
