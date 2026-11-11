"""Tests for W3 framewise chord and solo-token target construction."""

from __future__ import annotations

import numpy as np
import pytest

from app.chord_vocab import CHORD_TO_IDX
from app.cqt_constants import HOP_SEC, WINDOW
from app.student import targets, vocab


class TestChordFrames:
    def test_constant_chord_fills_window(self):
        spans = [targets.ChordSpan(0.0, 100.0, "C:maj")]
        labels = targets.build_chord_frame_labels(spans, WINDOW // 2 * HOP_SEC)
        assert labels.shape == (WINDOW,)
        assert np.all(labels == CHORD_TO_IDX["C:maj"])

    def test_no_chord_fills_n(self):
        labels = targets.build_chord_frame_labels([], 6.4)
        assert np.all(labels == targets.NO_CHORD_INDEX)

    def test_boundary_switches(self):
        spans = [
            targets.ChordSpan(0.0, 6.4, "C:maj"),
            targets.ChordSpan(6.4, 20.0, "G:maj"),
        ]
        # Window centred at 6.4 s starts at 0.0 s.
        labels = targets.build_chord_frame_labels(spans, 6.4)
        assert labels[0] == CHORD_TO_IDX["C:maj"]
        assert labels[-1] == CHORD_TO_IDX["G:maj"]


class TestSoloTokens:
    def test_note_within_window(self):
        note = targets.TargetNote(pitch=60, onset=0.2, offset=0.5)
        result = targets.build_solo_token_target([note], 6.4)
        assert result.dropped_out_of_range == 0
        assert result.dropped_non_guitar == 0
        tokens = result.tokens.tolist()
        assert tokens[0] == vocab.BOS
        assert tokens[-1] == vocab.EOS
        assert vocab.onset_token(60) in tokens
        assert vocab.offset_token(60) in tokens
        # Onset is at frame 2 relative to a window start of 0.0.
        onset_index = tokens.index(vocab.onset_token(60))
        assert result.frame_indices[onset_index] == 2
        offset_index = tokens.index(vocab.offset_token(60))
        assert result.frame_indices[offset_index] == 5

    def test_out_of_range_note_dropped(self):
        note = targets.TargetNote(pitch=20, onset=0.1, offset=0.2)
        result = targets.build_solo_token_target([note], 6.4)
        assert result.dropped_out_of_range == 1
        assert result.tokens.tolist() == [vocab.BOS, vocab.EOS]

    def test_non_guitar_program_dropped(self):
        note = targets.TargetNote(
            pitch=60, onset=0.1, offset=0.2, program=0
        )
        result = targets.build_solo_token_target([note], 6.4)
        assert result.dropped_non_guitar == 1

    def test_note_outside_window_ignored(self):
        note = targets.TargetNote(pitch=60, onset=100.0, offset=100.2)
        result = targets.build_solo_token_target([note], 6.4)
        assert result.tokens.tolist() == [vocab.BOS, vocab.EOS]

    def test_pad_and_shift(self):
        note = targets.TargetNote(pitch=67, onset=0.0, offset=0.1)
        target = targets.build_solo_token_target([note], 6.4)
        tokens, frames, mask = targets.pad_token_batch([target], max_tokens=16)
        assert tokens.shape == (1, 16)
        assert frames.shape == (1, 16)
        assert mask.sum() == len(target.tokens)
        shifted = targets.shift_decoder_inputs(tokens)
        assert shifted[0, 0] == vocab.BOS
        assert shifted[0, 1] == target.tokens[0]


class TestConverters:
    def test_spans_and_notes_from_dicts(self):
        spans = targets.spans_from_dicts(
            [{"start": 0.0, "end": 1.0, "chord": "C:maj"}]
        )
        notes = targets.notes_from_dicts(
            [
                {
                    "start_time": 0.5,
                    "duration": 0.25,
                    "pitch": 64,
                    "velocity": 90,
                    "program": 24,
                }
            ]
        )
        assert spans[0].chord == "C:maj"
        assert notes[0].pitch == 64
        assert notes[0].offset == pytest.approx(0.75)


class TestRootLabels:
    def test_root_derivation(self):
        # Quality-major vocabulary: index = quality * 12 + root.
        labels = np.asarray([0, 1, 12, 25, targets.NO_CHORD_INDEX], dtype=np.int32)
        roots = targets.derive_root_labels(labels)
        assert roots.tolist() == [0, 1, 0, 1, targets.NO_ROOT_INDEX]

    def test_root_shape_matches_chords(self):
        chords = np.full((2, 128), targets.NO_CHORD_INDEX, dtype=np.int32)
        roots = targets.derive_root_labels(chords)
        assert roots.shape == chords.shape
