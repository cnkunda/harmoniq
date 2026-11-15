"""Tests for 170-class label composition, parsing, and the v2 data loader."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab_170 import (  # noqa: E402
    BASS_TO_IDX,
    BASS_VOCAB,
    BASS_X_IDX,
    CHORD_VOCAB_170,
    N_IDX_170,
    ROOTS_12,
    X_IDX_170,
    compose_label,
    label_to_indices,
    parse_label,
    render_label,
)


class TestComposeLabel:
    def test_plain_label(self):
        assert compose_label("C", "maj7") == "C:maj7"

    def test_slash_label(self):
        assert compose_label("C", "maj", "E") == "C:maj/E"
        assert compose_label("C", "maj7", "B") == "C:maj7/B"

    def test_bass_equal_root_is_root_position(self):
        assert compose_label("C", "maj", "C") == "C:maj"

    def test_bass_unknown_yields_plain_label(self):
        assert compose_label("C", "maj", "X") == "C:maj"
        assert compose_label("C", "maj", None) == "C:maj"

    def test_non_chord_tone_bass_is_legal(self):
        # C/Eb on a C-major frame is a legal slash chord (decided in spec review)
        assert compose_label("C", "maj", "D#") == "C:maj/D#"

    def test_n_and_x(self):
        assert compose_label("N", None) == "N"
        assert compose_label("X", None) == "X"
        assert compose_label("N", None, "X") == "N"

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            compose_label("Cb", "maj")
        with pytest.raises(ValueError):
            compose_label("C", "9")  # 9 is collapsed — not in the 170 qualities
        with pytest.raises(ValueError):
            compose_label("C", "maj", "H")
        with pytest.raises(ValueError):
            compose_label("C", None)  # quality=None only valid for N/X


class TestParseLabel:
    def test_internal_format(self):
        assert parse_label("C:maj7/B") == ("C", "maj7", "B")

    def test_display_format(self):
        assert parse_label("Cmaj7/B") == ("C", "maj7", "B")
        assert parse_label("Cmaj7") == ("C", "maj7", None)

    def test_sharp_roots(self):
        assert parse_label("F#min7") == ("F#", "min7", None)
        assert parse_label("A#:maj7/B") == ("A#", "maj7", "B")

    def test_n_and_x(self):
        assert parse_label("N") == ("N", None, None)
        assert parse_label("X") == ("X", None, None)

    def test_invalid_labels_raise(self):
        with pytest.raises(ValueError):
            parse_label("C:9")
        with pytest.raises(ValueError):
            parse_label("H:maj")
        with pytest.raises(ValueError):
            parse_label("")
        with pytest.raises(ValueError):
            parse_label("C:maj/H")


class TestRoundTrip:
    def test_every_170_label_round_trips(self):
        for label in CHORD_VOCAB_170:
            root, quality, bass = parse_label(label)
            assert compose_label(root, quality, bass) == label

    def test_slash_chord_round_trip(self):
        for quality in ("maj", "min7", "maj7", "sus4"):
            for root, bass in zip(ROOTS_12, ROOTS_12[1:] + ROOTS_12[:1]):
                label = compose_label(root, quality, bass)
                assert parse_label(label) == (root, quality, bass)

    def test_render_label(self):
        assert render_label("C:maj7/B") == "Cmaj7/B"
        assert render_label("C:maj/E") == "Cmaj/E"
        assert render_label("C:maj") == "Cmaj"
        assert render_label("N") == "N"
        assert render_label("X") == "X"

    def test_render_parse_round_trip(self):
        for label in CHORD_VOCAB_170:
            assert parse_label(render_label(label)) == parse_label(label)


class TestLabelToIndices:
    def test_plain_label_bass_is_root(self):
        chord_idx, bass_idx = label_to_indices("C:maj")
        assert CHORD_VOCAB_170[chord_idx] == "C:maj"
        assert BASS_VOCAB[bass_idx] == "C"

    def test_slash_label_bass(self):
        chord_idx, bass_idx = label_to_indices("C:maj/E")
        assert CHORD_VOCAB_170[chord_idx] == "C:maj"
        assert BASS_VOCAB[bass_idx] == "E"

    def test_n_x_use_unknown_bass(self):
        assert label_to_indices("N") == (N_IDX_170, BASS_X_IDX)
        assert label_to_indices("X") == (X_IDX_170, BASS_X_IDX)


class TestDataLoader170:
    def _make_npz(self, path: Path, split: str, labels: list[int]) -> None:
        np.savez(
            path,
            features=np.zeros((len(labels), 128, 144), dtype=np.float32),
            labels=np.array(labels, dtype=np.int32),
            track_id="track_x",
            player_id="05",
            split=split,
            loss_weight=np.array(1.0),
        )

    def test_loads_170_labels_and_bass(self, tmp_path):
        from scripts.chord_data_v2 import load_dataset_dir_170
        from app.chord_vocab import CHORD_TO_IDX
        from app.chord_vocab_170 import map_277_to_170

        cqt_dir = tmp_path / "processed" / "cqt"
        cqt_dir.mkdir(parents=True)
        labels_277 = [CHORD_TO_IDX["C:maj"], CHORD_TO_IDX["C:9"], CHORD_TO_IDX["C:min7"], 276]
        self._make_npz(cqt_dir / "a.npz", "train", labels_277)

        data = load_dataset_dir_170(tmp_path, split="train")
        assert data["labels170"].tolist() == [
            map_277_to_170(i) for i in labels_277
        ]
        # No bass info in the source npz → all windows use the unknown-bass class
        assert (data["bass_labels"] == BASS_X_IDX).all()
        assert data["features"].shape == (4, 128, 144)

    def test_split_filtering_no_window_mixing(self, tmp_path):
        from scripts.chord_data_v2 import load_dataset_dir_170

        cqt_dir = tmp_path / "processed" / "cqt"
        cqt_dir.mkdir(parents=True)
        self._make_npz(cqt_dir / "train.npz", "train", [0, 1])
        self._make_npz(cqt_dir / "test.npz", "test", [5])
        train = load_dataset_dir_170(tmp_path, split="train")
        test = load_dataset_dir_170(tmp_path, split="test")
        assert len(train["labels170"]) == 2
        assert len(test["labels170"]) == 1

    def test_existing_bass_labels_are_used(self, tmp_path):
        from scripts.chord_data_v2 import load_dataset_dir_170
        from app.chord_vocab_170 import BASS_TO_IDX

        cqt_dir = tmp_path / "processed" / "cqt"
        cqt_dir.mkdir(parents=True)
        path = cqt_dir / "a.npz"
        self._make_npz(path, "train", [0, 0])
        # Overwrite with bass labels present (0 = C bass for both windows)
        np.savez(
            path,
            features=np.zeros((2, 128, 144), dtype=np.float32),
            labels=np.array([0, 0], dtype=np.int32),
            bass_labels=np.array([0, 4], dtype=np.int32),
            track_id="track_x",
            player_id="05",
            split="train",
            loss_weight=np.array(1.0),
        )
        data = load_dataset_dir_170(tmp_path, split="train")
        assert data["bass_labels"].tolist() == [BASS_TO_IDX["C"], BASS_TO_IDX["E"]]

    def test_counts_report(self, tmp_path):
        from scripts.chord_data_v2 import summarize_dataset

        cqt_dir = tmp_path / "processed" / "cqt"
        cqt_dir.mkdir(parents=True)
        self._make_npz(cqt_dir / "a.npz", "train", [0, 276, 276, 3])
        summary = summarize_dataset(tmp_path, split="train")
        assert summary["n_windows"] == 4
        assert summary["n_tracks"] == 1
        assert summary["n_rate"] == 0.5
        assert summary["unique_classes"] == 3
