"""Tests for the W3 guitar-vocabulary event tokens."""

from __future__ import annotations

import pytest

from app.student import vocab


class TestGuitarRange:
    def test_bounds_are_inclusive(self):
        assert vocab.in_guitar_range(vocab.GUITAR_PITCH_MIN)
        assert vocab.in_guitar_range(vocab.GUITAR_PITCH_MAX)
        assert not vocab.in_guitar_range(vocab.GUITAR_PITCH_MIN - 1)
        assert not vocab.in_guitar_range(vocab.GUITAR_PITCH_MAX + 1)

    def test_out_of_range_token_raises(self):
        with pytest.raises(ValueError):
            vocab.onset_token(0)
        with pytest.raises(ValueError):
            vocab.offset_token(127)


class TestTokenMapping:
    def test_onset_offset_round_trip(self):
        for pitch in (40, 60, 88, 96):
            onset = vocab.onset_token(pitch)
            offset = vocab.offset_token(pitch)
            assert vocab.is_onset(onset)
            assert vocab.is_offset(offset)
            assert vocab.token_pitch(onset) == pitch
            assert vocab.token_pitch(offset) == pitch

    def test_velocity_bins(self):
        assert vocab.velocity_bin(0) == 0
        assert vocab.velocity_bin(127) == vocab.NUM_VELOCITY_BINS - 1
        for value in (1, 40, 80, 120):
            token = vocab.velocity_token(vocab.velocity_bin(value))
            assert vocab.is_velocity(token)
            assert 0 <= vocab.velocity_from_bin(token - vocab.VELOCITY_BASE) <= 127


class TestDecodeTokens:
    def test_simple_note(self):
        tokens = [
            vocab.BOS,
            vocab.onset_token(60),
            vocab.velocity_token(vocab.velocity_bin(80)),
            vocab.TIME_SHIFT,
            vocab.TIME_SHIFT,
            vocab.offset_token(60),
            vocab.EOS,
        ]
        notes = vocab.decode_tokens(tokens)
        assert len(notes) == 1
        note = notes[0]
        assert note.pitch == 60
        assert note.onset == pytest.approx(0.0)
        assert note.offset == pytest.approx(0.2)
        assert note.velocity > 0

    def test_unclosed_note_is_still_emitted(self):
        tokens = [
            vocab.BOS,
            vocab.onset_token(64),
            vocab.velocity_token(0),
            vocab.EOS,
        ]
        notes = vocab.decode_tokens(tokens)
        assert len(notes) == 1
        assert notes[0].offset > notes[0].onset

    def test_retrigger_closes_previous(self):
        tokens = [
            vocab.BOS,
            vocab.onset_token(64),
            vocab.velocity_token(0),
            vocab.TIME_SHIFT,
            vocab.onset_token(64),
            vocab.velocity_token(0),
            vocab.TIME_SHIFT,
            vocab.offset_token(64),
            vocab.EOS,
        ]
        notes = vocab.decode_tokens(tokens)
        assert len(notes) == 2
        assert notes[0].onset < notes[1].onset
