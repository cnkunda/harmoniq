"""Tests for the 170-class evaluation metrics (Phase 3)."""

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
    BASS_X_IDX,
    CHORD_TO_IDX_170,
    N_IDX_170,
    X_IDX_170,
)
from scripts.eval_chord_170 import (  # noqa: E402
    bass_accuracy,
    evaluate_arrays,
    expected_calibration_error,
    label_to_harte,
    macro_f1,
    per_quality_report,
    slash_accuracy,
    top_k_accuracy,
    wcsr_metrics,
    window_intervals,
)


class TestHarteLabels:
    def test_plain_label(self):
        assert label_to_harte(CHORD_TO_IDX_170["C:maj"]) == "C:maj"

    def test_root_position_bass_omitted(self):
        idx = CHORD_TO_IDX_170["C:maj"]
        assert label_to_harte(idx, BASS_TO_IDX["C"]) == "C:maj"

    def test_inversion_degree(self):
        idx = CHORD_TO_IDX_170["C:maj"]
        assert label_to_harte(idx, BASS_TO_IDX["E"]) == "C:maj/3"

    def test_seventh_inversion(self):
        idx = CHORD_TO_IDX_170["C:maj7"]
        assert label_to_harte(idx, BASS_TO_IDX["B"]) == "C:maj7/7"

    def test_non_chord_tone_bass(self):
        idx = CHORD_TO_IDX_170["C:maj"]
        assert label_to_harte(idx, BASS_TO_IDX["D#"]) == "C:maj/b3"

    def test_unknown_bass_omitted(self):
        idx = CHORD_TO_IDX_170["G:min"]
        assert label_to_harte(idx, BASS_X_IDX) == "G:min"

    def test_n_and_x(self):
        assert label_to_harte(N_IDX_170) == "N"
        assert label_to_harte(X_IDX_170) == "X"


class TestWindowIntervals:
    def test_sorted_positive(self):
        iv = window_intervals(np.array([12.8, 0.0, 6.4]), hop_s=6.4)
        assert iv.shape == (3, 2)
        assert np.all(iv[:, 1] > iv[:, 0])
        assert np.all(iv[1:, 0] >= iv[:-1, 1] - 1e-9)

    def test_empty(self):
        assert window_intervals(np.array([])).shape == (0, 2)

    def test_dedupe(self):
        iv = window_intervals(np.array([0.0, 0.0, 6.4]))
        assert len(iv) == 2


class TestWcsr:
    def test_perfect(self):
        ref = np.array(["C:maj", "C:min7", "N", "C:maj/3"])
        centres = np.arange(4) * 6.4
        scores = wcsr_metrics(ref, ref, centres)
        for key, value in scores.items():
            assert value == pytest.approx(1.0), key

    def test_maj_min_confusion(self):
        ref = np.array(["C:maj", "C:maj"])
        est = np.array(["C:min", "C:min"])
        scores = wcsr_metrics(ref, est, np.array([0.0, 6.4]))
        assert scores["root"] == pytest.approx(1.0)
        assert scores["majmin"] == pytest.approx(0.0)
        assert scores["mirex"] == pytest.approx(0.0)

    def test_inversion_matters(self):
        ref = np.array(["C:maj/3"])
        est = np.array(["C:maj"])
        scores = wcsr_metrics(ref, est, np.array([0.0]))
        assert scores["mirex"] == pytest.approx(1.0)   # root/majmin/tetrads ignore bass
        # mir_eval's non-inversion metrics deliberately ignore the bass.

    def test_x_scores_as_no_chord(self):
        ref = np.array(["X"])
        est = np.array(["N"])
        scores = wcsr_metrics(ref, est, np.array([0.0]))
        assert scores["mirex"] == pytest.approx(1.0)


class TestMacroF1:
    def test_perfect(self):
        y = np.array([0, 1, 2])
        assert macro_f1(y, y) == pytest.approx(1.0)

    def test_disjoint(self):
        assert macro_f1(np.array([0, 0]), np.array([1, 1])) == pytest.approx(0.0)

    def test_partial(self):
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 1, 1, 1])
        # class 0: tp=1 fp=0 fn=1 → F1=2/3; class 1: tp=2 fp=1 fn=0 → F1=0.8
        assert macro_f1(y_true, y_pred) == pytest.approx((2 / 3 + 0.8) / 2)


class TestPerQuality:
    def test_report_counts(self):
        c_maj = CHORD_TO_IDX_170["C:maj"]
        d_min = CHORD_TO_IDX_170["D:min"]
        report = per_quality_report(np.array([c_maj, c_maj, d_min]),
                                    np.array([c_maj, d_min, d_min]))
        assert report["maj"]["support"] == 2
        assert report["maj"]["recall"] == pytest.approx(0.5)
        assert report["min"]["recall"] == pytest.approx(1.0)


class TestBassAndSlash:
    def test_bass_accuracy(self):
        chord = np.array([CHORD_TO_IDX_170["C:maj"]] * 3 + [N_IDX_170])
        bass_true = np.array([BASS_TO_IDX["C"], BASS_TO_IDX["E"], BASS_X_IDX, BASS_X_IDX])
        bass_pred = np.array([BASS_TO_IDX["C"], BASS_TO_IDX["C"], BASS_TO_IDX["C"], BASS_X_IDX])
        report = bass_accuracy(bass_true, bass_pred, chord)
        assert report["n_known"] == 2
        assert report["known_bass"] == pytest.approx(0.5)
        assert report["overall"] == pytest.approx(0.5)  # C, wrong, wrong, unk

    def test_slash_split(self):
        c_maj = CHORD_TO_IDX_170["C:maj"]
        chord_true = np.array([c_maj, c_maj])
        chord_pred = np.array([c_maj, c_maj])
        bass_true = np.array([BASS_TO_IDX["C"], BASS_TO_IDX["E"]])
        bass_pred = np.array([BASS_TO_IDX["C"], BASS_TO_IDX["G"]])
        report = slash_accuracy(chord_true, chord_pred, bass_true, bass_pred)
        assert report["n_root_position"] == 1
        assert report["n_slash"] == 1
        assert report["root_position_acc"] == pytest.approx(1.0)
        assert report["slash_acc"] == pytest.approx(0.0)


class TestCalibrationAndTopK:
    def test_top_k(self):
        probs = np.array([[0.5, 0.3, 0.1, 0.1], [0.1, 0.1, 0.1, 0.7]])
        y = np.array([2, 0])  # top-3 hit both; top-2 miss in row 0
        assert top_k_accuracy(probs, y, 2) == pytest.approx(0.5)
        assert top_k_accuracy(probs, y, 3) == pytest.approx(1.0)

    def test_ece_perfect_calibration(self):
        probs = np.array([[1.0, 0.0], [1.0, 0.0]])
        y = np.array([0, 0])
        assert expected_calibration_error(probs, y) == pytest.approx(0.0)

    def test_ece_overconfident(self):
        probs = np.array([[1.0, 0.0], [1.0, 0.0]])
        y = np.array([1, 1])
        assert expected_calibration_error(probs, y) == pytest.approx(1.0)

    def test_ece_duration_weighting(self):
        probs = np.array([[1.0, 0.0], [0.6, 0.4]])
        y = np.array([0, 1])
        # First: conf 1.0 correct; second: conf 0.6 wrong → ECE = 0.6 with
        # equal weights; doubling the first weight halves the contribution.
        report = expected_calibration_error(probs, y, weights=np.array([2.0, 1.0]))
        assert report == pytest.approx(0.2)


class TestEvaluateArrays:
    def _run(self, *, perfect=True):
        labels = np.array([
            CHORD_TO_IDX_170["C:maj"],
            CHORD_TO_IDX_170["C:min7"],
            N_IDX_170,
            CHORD_TO_IDX_170["G:maj"],
            CHORD_TO_IDX_170["D:7"],
        ])
        preds = labels.copy()
        if not perfect:
            preds = np.array([
                CHORD_TO_IDX_170["C:maj"],
                CHORD_TO_IDX_170["C:min7"],
                CHORD_TO_IDX_170["C:maj"],
                CHORD_TO_IDX_170["G:maj"],
                CHORD_TO_IDX_170["D:maj"],
            ])
        probs = np.full((len(labels), 170), 0.001, dtype=np.float32)
        probs[np.arange(len(labels)), labels] = 0.5
        probs /= probs.sum(axis=1, keepdims=True)
        bass_true = np.array([
            BASS_TO_IDX["C"], BASS_TO_IDX["G"], BASS_X_IDX,
            BASS_TO_IDX["G"], BASS_TO_IDX["D"],
        ])
        bass_pred = bass_true.copy()
        track_ids = ["a", "a", "a", "b", "b"]
        centres = np.array([0.0, 6.4, 12.8, 0.0, 6.4])
        sources = ["guitarset", "guitarset", "guitarset", "egset12", "egset12"]
        return evaluate_arrays(labels, preds, bass_true, bass_pred, probs,
                               track_ids, centres, sources)

    def test_perfect_report(self):
        report = self._run()
        assert report["n_windows"] == 5
        assert report["n_tracks"] == 2
        assert report["macro_f1"] == pytest.approx(1.0)
        assert report["wcsr"]["mirex"] == pytest.approx(1.0)
        assert report["wcsr"]["root"] == pytest.approx(1.0)
        assert report["slash"]["n_slash"] == 1
        assert report["slash"]["n_root_position"] == 3
        assert "guitarset" in report["per_source"]
        assert "egset12" in report["per_source"]

    def test_imperfect_report(self):
        report = self._run(perfect=False)
        assert report["macro_f1"] < 1.0
        assert report["wcsr"]["mirex"] < 1.0
        # N→C:maj costs root on one of five windows → 4/5 duration-weighted.
        assert report["wcsr"]["root"] == pytest.approx(0.8)


class TestAblationSpace:
    def test_map_170_to_mirex25(self):
        from app.chord_vocab_170 import map_170_to_mirex25
        from app.chord_vocab import MIREX_TO_IDX

        assert map_170_to_mirex25(CHORD_TO_IDX_170["C:maj"]) == MIREX_TO_IDX["C:maj"]
        assert map_170_to_mirex25(CHORD_TO_IDX_170["C:min"]) == MIREX_TO_IDX["C:min"]
        assert map_170_to_mirex25(CHORD_TO_IDX_170["C:hdim7"]) == MIREX_TO_IDX["C:min"]
        assert map_170_to_mirex25(N_IDX_170) == MIREX_TO_IDX["N"]

    def test_probs_to_mirex25_sums_to_one(self):
        from scripts.eval_chord_170 import probs_to_mirex25

        probs = np.zeros((2, 170), dtype=np.float32)
        probs[:, CHORD_TO_IDX_170["C:maj"]] = 0.5
        probs[:, CHORD_TO_IDX_170["C:min7"]] = 0.5
        mapped = probs_to_mirex25(probs, "170")
        assert mapped.shape == (2, 25)
        assert np.allclose(mapped.sum(axis=1), 1.0)

    def test_evaluate_ablation_perfect(self):
        from scripts.eval_chord_170 import evaluate_ablation

        labels = np.array([CHORD_TO_IDX_170["C:maj"], CHORD_TO_IDX_170["D:min"]])
        probs = np.zeros((2, 170), dtype=np.float32)
        probs[np.arange(2), labels] = 1.0
        report = evaluate_ablation(labels, probs, ["t", "t"],
                                   np.array([0.0, 6.4]), space="170")
        assert report["exact_accuracy"] == pytest.approx(1.0)
        assert report["wcsr"]["mirex"] == pytest.approx(1.0)
        assert "ci" in report

    def test_evaluate_ablation_mirex25_native(self):
        from scripts.eval_chord_170 import evaluate_ablation

        labels = np.array([0, 12, 24])  # C:maj, C:min, N
        probs = np.eye(25, dtype=np.float32)[labels]
        report = evaluate_ablation(labels, probs, ["t"] * 3,
                                   np.array([0.0, 6.4, 12.8]), space="mirex25")
        assert report["exact_accuracy"] == pytest.approx(1.0)

    def test_bootstrap_ci_bounds(self):
        from scripts.eval_chord_170 import bootstrap_ci

        labels = np.array([0, 1, 2, 3])
        preds = np.array([0, 1, 0, 0])
        ci = bootstrap_ci(labels, preds, ["a", "a", "b", "b"], n_boot=200)
        assert ci["exact_accuracy"][0] <= ci["exact_accuracy"][1]
        assert 0.0 <= ci["exact_accuracy"][0]
        assert ci["exact_accuracy"][1] <= 1.0


class TestInversionDiagnostics:
    def test_slash_breakdown(self):
        from scripts.eval_chord_170 import slash_breakdown
        from app.chord_vocab_170 import BASS_TO_IDX, CHORD_TO_IDX_170

        c_maj = CHORD_TO_IDX_170["C:maj"]
        chord_true = np.array([c_maj, c_maj, c_maj])
        chord_pred = np.array([c_maj, CHORD_TO_IDX_170["C:min"], c_maj])
        bass_true = np.array([BASS_TO_IDX["C"], BASS_TO_IDX["E"], BASS_TO_IDX["G"]])
        bass_pred = np.array([BASS_TO_IDX["C"], BASS_TO_IDX["E"], BASS_TO_IDX["C"]])
        report = slash_breakdown(chord_true, chord_pred, bass_true, bass_pred)
        assert report["n"] == 2
        assert report["chord_exact"] == pytest.approx(0.5)
        assert report["bass_exact"] == pytest.approx(0.5)
        assert report["both_exact"] == pytest.approx(0.0)

    def test_fuse_head_probabilities(self):
        from scripts.eval_chord_170 import fuse_head_probabilities

        probs = np.full((1, 170), 1 / 170, dtype=np.float32)
        root = np.zeros((1, 13), dtype=np.float32); root[0, 0] = 1.0
        quality = np.zeros((1, 15), dtype=np.float32); quality[0, 0] = 1.0
        fused = fuse_head_probabilities(probs, root, quality)
        assert fused.shape == (1, 170)
        assert fused.sum() == pytest.approx(1.0)
        assert fused[0, 0] == pytest.approx(1.0)


class TestBassDisambiguation:
    def test_sixth_vs_relative_min7(self):
        from scripts.eval_chord_170 import disambiguate_by_bass
        from app.chord_vocab_170 import BASS_TO_IDX, CHORD_TO_IDX_170

        c6 = CHORD_TO_IDX_170["C:maj6"]   # {C,E,G,A}
        am7 = CHORD_TO_IDX_170["A:min7"]  # {A,C,E,G} — identical pitch set
        probs = np.zeros(170, dtype=np.float32)
        probs[c6] = 0.6
        probs[am7] = 0.5
        # Bass says A → prefer Am7
        assert disambiguate_by_bass(c6, BASS_TO_IDX["A"], probs) == am7
        # Bass says C → keep C6
        assert disambiguate_by_bass(c6, BASS_TO_IDX["C"], probs) == c6
        # Bass unknown → keep
        assert disambiguate_by_bass(c6, 12, probs) == c6

    def test_low_alternative_probability_kept(self):
        from scripts.eval_chord_170 import disambiguate_by_bass
        from app.chord_vocab_170 import BASS_TO_IDX, CHORD_TO_IDX_170

        c6 = CHORD_TO_IDX_170["C:maj6"]
        am7 = CHORD_TO_IDX_170["A:min7"]
        probs = np.zeros(170, dtype=np.float32)
        probs[c6] = 0.8
        probs[am7] = 0.1  # below 0.5 * 0.8
        assert disambiguate_by_bass(c6, BASS_TO_IDX["A"], probs) == c6

    def test_non_ambiguous_chord_unchanged(self):
        from scripts.eval_chord_170 import disambiguate_by_bass
        from app.chord_vocab_170 import BASS_TO_IDX, CHORD_TO_IDX_170

        c_maj = CHORD_TO_IDX_170["C:maj"]
        probs = np.zeros(170, dtype=np.float32)
        probs[c_maj] = 1.0
        assert disambiguate_by_bass(c_maj, BASS_TO_IDX["E"], probs) == c_maj
