"""Tests for 170-class label composition, parsing, and the v2 data loader."""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Phase 2: bass derivation and annotation normalization
# ---------------------------------------------------------------------------


class TestBassFromNotes:
    def test_pitch_to_pitch_class(self):
        from app.chord_labels import pitch_to_pitch_class

        assert pitch_to_pitch_class(60) == 0     # C4
        assert pitch_to_pitch_class(61) == 1     # C#4
        assert pitch_to_pitch_class(59.4) == 11  # rounds to B3
        assert pitch_to_pitch_class(64) == 4     # E4

    def test_active_pitches_interval(self):
        from app.chord_labels import active_pitches

        notes = [(0.0, 1.0, 60), (0.5, 2.0, 64)]
        assert active_pitches(notes, 0.2) == [60]
        assert active_pitches(notes, 0.7) == [60, 64]
        assert active_pitches(notes, 2.5) == []

    def test_bass_is_lowest_active_note(self):
        from app.chord_labels import bass_pitch_class_from_notes

        notes = [(0.0, 2.0, 67), (0.0, 2.0, 48), (0.0, 2.0, 64)]
        assert bass_pitch_class_from_notes(notes, 1.0) == 0  # C3 = lowest

    def test_bass_none_when_silent(self):
        from app.chord_labels import bass_pitch_class_from_notes

        assert bass_pitch_class_from_notes([(0.0, 1.0, 60)], 5.0) is None

    def test_count_active_pitch_classes_dedupes_octaves(self):
        from app.chord_labels import count_active_pitches

        notes = [(0.0, 2.0, 60), (0.0, 2.0, 72), (0.0, 2.0, 64)]
        assert count_active_pitches(notes, 1.0) == 2


class TestAnnotationLabels:
    def test_degree_bass(self):
        from app.chord_labels import bass_from_degree

        assert bass_from_degree("Eb", "3") == 7    # G
        assert bass_from_degree("Eb", "b3") == 6   # Gb
        assert bass_from_degree("C", "5") == 7     # G
        assert bass_from_degree("C", "b7") == 10   # Bb
        assert bass_from_degree("C", "7") == 11    # B
        assert bass_from_degree("C", "b5") == 6    # Gb
        assert bass_from_degree("C", "13") is None

    def test_normalize_rwc_forms(self):
        from app.chord_labels import normalize_quality

        assert normalize_quality("maj(*3)") == "maj"
        assert normalize_quality("min(*b3,*5)") == "min"
        assert normalize_quality("7(b9)") == "7"
        assert normalize_quality("sus4(b7)") == "sus4"
        assert normalize_quality("sus2(b7)") == "sus2"
        assert normalize_quality("maj7(9)") == "maj7"
        assert normalize_quality("hdim7") == "hdim7"
        assert normalize_quality("maj9") == "maj7"
        assert normalize_quality("min9") == "min7"
        assert normalize_quality("9") == "7"

    def test_normalize_idmt_shorthand(self):
        from app.chord_labels import normalize_quality

        assert normalize_quality("") == "maj"
        assert normalize_quality("min75b") == "hdim7"
        assert normalize_quality("79b") == "7"
        assert normalize_quality("minmaj79") == "minmaj7"
        assert normalize_quality("sus9") == "sus4"
        assert normalize_quality("5") == "maj"

    def test_normalize_unmappable_returns_none(self):
        from app.chord_labels import normalize_quality

        assert normalize_quality("weird") is None

    def test_parse_annotation_label(self):
        from app.chord_labels import parse_annotation_label

        assert parse_annotation_label("G") == ("G", "maj", None)
        assert parse_annotation_label("D7/C") == ("D", "7", 0)
        assert parse_annotation_label("Eb:maj/3") == ("Eb", "maj", 7)
        assert parse_annotation_label("F:maj/5") == ("F", "maj", 0)
        assert parse_annotation_label("N") is None
        assert parse_annotation_label("NC") is None
        assert parse_annotation_label("H:maj") is None
        assert parse_annotation_label("C:weird") is None

    def test_chord_tones(self):
        from app.chord_labels import chord_tones

        assert chord_tones("C", "maj") == {0, 4, 7}
        assert chord_tones("C", "hdim7") == {0, 3, 6, 10}


class TestPseudoLabelFilters:
    def test_n_cap_limits_n_windows(self):
        from scripts.chord_data_v2 import _cap_n_windows
        from app.chord_vocab_170 import N_IDX_170

        labels = np.array([0, N_IDX_170, 1, N_IDX_170, N_IDX_170, 2])
        conf = np.array([1.0, 0.9, 1.0, 0.95, 0.5, 1.0], dtype=np.float32)
        keep = _cap_n_windows(labels, conf, 0.2)
        # non_n = 3 → allowed_n = floor(0.2*3/0.8) = 0
        assert int(np.sum(keep & (labels == N_IDX_170))) == 0
        assert int(np.sum(keep)) == 3

    def test_n_cap_noop_when_under(self):
        from scripts.chord_data_v2 import _cap_n_windows
        from app.chord_vocab_170 import N_IDX_170

        labels = np.array([0, 1, 2, 3, N_IDX_170])
        conf = np.ones(5, dtype=np.float32)
        assert _cap_n_windows(labels, conf, 0.2).all()

    def test_cap_keeps_highest_confidence_n(self):
        from scripts.chord_data_v2 import _cap_n_windows
        from app.chord_vocab_170 import N_IDX_170

        labels = np.array([0, 1, 2, 3, N_IDX_170, N_IDX_170, N_IDX_170])
        conf = np.array([1, 1, 1, 1, 0.2, 0.9, 0.5], dtype=np.float32)
        keep = _cap_n_windows(labels, conf, 0.5)
        kept_n = np.flatnonzero(keep & (labels == N_IDX_170))
        # non_n=4 → allowed_n = floor(0.5*4/0.5) = 4, all 3 N kept
        assert len(kept_n) == 3


class TestPseudoLabelBuilder:
    def _write_w1_track(self, root: Path, track_id: str, labels277, conf, chords, notes):
        labels_dir = root / "labels"
        cqt_dir = root / "processed" / "cqt"
        labels_dir.mkdir(parents=True, exist_ok=True)
        cqt_dir.mkdir(parents=True, exist_ok=True)
        safe = track_id.replace("/", "_")
        np.savez_compressed(
            cqt_dir / f"{safe}.npz",
            features=np.zeros((len(labels277), 128, 144), dtype=np.float32),
            labels=np.asarray(labels277, dtype=np.int32),
            confidence=np.asarray(conf, dtype=np.float32),
            split=np.bytes_(b"train"),
            source=np.bytes_(b"test"),
            teacher=np.bytes_(b"mt3"),
            track_id=np.bytes_(track_id.encode()),
            loss_weight=np.float64(0.5),
            windows_total=np.int64(3),
        )
        payload = {
            "schema_version": 1,
            "track_id": track_id,
            "source": "test",
            "split": "train",
            "teacher": "mt3",
            "windows_total": 3,
            "windows_kept": len(labels277),
            "chords": chords,
            "notes": notes,
        }
        (labels_dir / f"{safe}.json").write_text(json.dumps(payload))

    def test_builder_applies_filters_and_bass(self, tmp_path):
        from scripts.chord_data_v2 import build_pseudo_labels_v2
        from app.chord_labels import bass_pitch_class_from_notes
        from app.chord_vocab import CHORD_TO_IDX
        from app.chord_vocab_170 import CHORD_TO_IDX_170

        w1 = tmp_path / "w1"
        out = tmp_path / "out"
        # 3 windows at 0 / 6.4 / 12.8 s, all C:maj with 3 active notes
        self._write_w1_track(
            w1, "track_a",
            labels277=[CHORD_TO_IDX["C:maj"]] * 3,
            conf=[1.0, 1.0, 1.0],
            chords=[{"start": 0.0, "end": 100.0, "chord": "C:maj", "confidence": 1.0}],
            notes=[
                {"start_time": 0.0, "duration": 100.0, "pitch": 48, "confidence": 1.0},
                {"start_time": 0.0, "duration": 100.0, "pitch": 64, "confidence": 1.0},
                {"start_time": 0.0, "duration": 100.0, "pitch": 67, "confidence": 1.0},
            ],
        )
        report = build_pseudo_labels_v2(w1, out)
        assert report["status"] == "ok"
        assert report["windows_after_filters"] == 3
        data = np.load(next((out / "processed" / "cqt").glob("*.npz")))
        assert data["labels170"].tolist() == [CHORD_TO_IDX_170["C:maj"]] * 3
        # Lowest note is C3 (48) → bass pitch class C (index 0)
        assert data["bass_labels"].tolist() == [0, 0, 0]

    def test_builder_drops_low_pitch_windows(self, tmp_path):
        from scripts.chord_data_v2 import build_pseudo_labels_v2
        from app.chord_vocab import CHORD_TO_IDX

        w1 = tmp_path / "w1"
        out = tmp_path / "out"
        self._write_w1_track(
            w1, "track_b",
            labels277=[CHORD_TO_IDX["C:maj"]] * 3,
            conf=[1.0, 1.0, 1.0],
            chords=[{"start": 0.0, "end": 100.0, "chord": "C:maj", "confidence": 1.0}],
            notes=[{"start_time": 0.0, "duration": 100.0, "pitch": 60, "confidence": 1.0}],
        )
        report = build_pseudo_labels_v2(w1, out)
        # Only 1 active pitch → every chord window filtered out
        assert report["status"] == "no_tracks" or report["windows_after_filters"] == 0


class TestBtcTeacherMapping:
    def test_btc_to_170_is_bijection(self):
        from scripts.btc_teacher import BTC_INDEX_TO_170

        assert len(BTC_INDEX_TO_170) == 170
        assert sorted(BTC_INDEX_TO_170.tolist()) == list(range(170))

    def test_btc_index_labels(self):
        from scripts.btc_teacher import btc_label

        assert btc_label(0) == "C:min"
        assert btc_label(1) == "C:maj"
        assert btc_label(14) == "C#:min"
        assert btc_label(167) == "B:sus4"
        assert btc_label(168) == "X"
        assert btc_label(169) == "N"

    def test_btc_n_and_x_map_to_ours(self):
        from scripts.btc_teacher import map_btc_index_to_170
        from app.chord_vocab_170 import N_IDX_170, X_IDX_170

        assert map_btc_index_to_170(168) == X_IDX_170
        assert map_btc_index_to_170(169) == N_IDX_170

    def test_btc_chord_label_normalization(self):
        from scripts.btc_teacher import btc_chord_to_170

        assert btc_chord_to_170("C") == "C:maj"
        assert btc_chord_to_170("C:min7") == "C:min7"
        assert btc_chord_to_170("D#:maj7") == "D#:maj7"
        assert btc_chord_to_170("C:maj9") == "C:maj7"
        assert btc_chord_to_170("C:7sus4") == "C:sus4"
        assert btc_chord_to_170("N") == "N"
        assert btc_chord_to_170("X") == "X"
        assert btc_chord_to_170("H:maj") is None

    def test_check_mapping_shape(self):
        from scripts.btc_teacher import check_mapping

        report = check_mapping()
        assert report["is_bijection"] is True
        assert report["n_is_our_index"] is True
        assert report["x_is_our_index"] is True


class TestAugmentationLabels:
    def test_pitch_shift_remaps_roots(self):
        from app.chord_labels import pitch_shift_labels
        from app.chord_vocab_170 import CHORD_TO_IDX_170, BASS_TO_IDX

        chord, bass = pitch_shift_labels(
            np.array([CHORD_TO_IDX_170["C:maj"], CHORD_TO_IDX_170["C:min7"]]),
            np.array([BASS_TO_IDX["C"], BASS_TO_IDX["E"]]),
            2,
        )
        assert chord.tolist() == [
            CHORD_TO_IDX_170["D:maj"], CHORD_TO_IDX_170["D:min7"]
        ]
        assert bass.tolist() == [BASS_TO_IDX["D"], BASS_TO_IDX["F#"]]

    def test_pitch_shift_preserves_n_x_and_unknown_bass(self):
        from app.chord_labels import pitch_shift_labels
        from app.chord_vocab_170 import BASS_X_IDX, N_IDX_170, X_IDX_170

        chord, bass = pitch_shift_labels(
            np.array([N_IDX_170, X_IDX_170]), np.array([BASS_X_IDX, BASS_X_IDX]), 5
        )
        assert chord.tolist() == [N_IDX_170, X_IDX_170]
        assert bass.tolist() == [BASS_X_IDX, BASS_X_IDX]

    def test_pitch_shift_wraps_and_noops(self):
        from app.chord_labels import pitch_shift_labels
        from app.chord_vocab_170 import BASS_TO_IDX, CHORD_TO_IDX_170

        idx = CHORD_TO_IDX_170["B:maj"]
        chord, _ = pitch_shift_labels(np.array([idx]), np.array([BASS_TO_IDX["B"]]), 1)
        assert chord.tolist() == [CHORD_TO_IDX_170["C:maj"]]
        chord0, _ = pitch_shift_labels(np.array([idx]), np.array([BASS_TO_IDX["B"]]), 0)
        assert chord0.tolist() == [idx]


class TestSamplingProbabilities:
    def test_sums_to_one(self):
        from scripts.chord_data_v2 import sampling_probabilities

        labels = np.array([0, 1, 2, 3, 4])
        sources = np.array(["a", "a", "b", "b", "b"])
        probs = sampling_probabilities(labels, sources)
        assert probs.sum() == pytest.approx(1.0)
        assert (probs > 0).all()

    def test_rare_class_upweighted(self):
        from scripts.chord_data_v2 import sampling_probabilities

        labels = np.array([0] * 90 + [1] * 10)
        sources = np.array(["a"] * 100)
        probs = sampling_probabilities(labels, sources, temperature=0.3)
        assert probs[labels == 1].mean() > probs[labels == 0].mean()

    def test_source_balance_upweights_small_source(self):
        from scripts.chord_data_v2 import sampling_probabilities

        labels = np.array([0] * 90 + [1] * 10)
        sources = np.array(["big"] * 90 + ["small"] * 10)
        probs = sampling_probabilities(labels, sources, temperature=0.0)
        assert probs[sources == "small"].mean() > probs[sources == "big"].mean()

    def test_n_not_amplified(self):
        from scripts.chord_data_v2 import sampling_probabilities
        from app.chord_vocab_170 import N_IDX_170

        labels = np.array([0] * 40 + [1] * 40 + [2] * 10 + [N_IDX_170] * 10)
        sources = np.array(["a"] * 100)
        probs = sampling_probabilities(labels, sources, temperature=0.3)
        n_share = float(probs[labels == N_IDX_170].sum())
        natural = 0.10
        assert n_share <= max(1.5 * natural, natural + 0.05) + 1e-9
