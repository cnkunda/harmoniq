"""Training callback tests (Commit 103).

Framework-free tests for ``training_callbacks.py`` — no TensorFlow import.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from training_callbacks import EarlyStopping, ReduceLROnPlateau  # noqa: E402


class TestEarlyStopping:
    def test_improving_metric_never_stops(self):
        es = EarlyStopping(patience=5)
        for epoch in range(10):
            assert es.on_epoch_end(epoch, float(epoch)) is False

    def test_plateau_stops_after_patience(self):
        es = EarlyStopping(patience=3)
        # 0.8 improving -> then flat at 0.85 for 3 epochs
        for epoch, metric in [(0, 0.8), (1, 0.85), (2, 0.85), (3, 0.85)]:
            stop = es.on_epoch_end(epoch, metric)
            assert stop is False, f"should not stop at epoch {epoch}"
        # 4th consecutive stale epoch triggers stop
        assert es.on_epoch_end(4, 0.85) is True
        assert es.stopped

    def test_min_delta_ignores_tiny_improvements(self):
        es = EarlyStopping(patience=2, min_delta=0.01)
        es.on_epoch_end(0, 0.500)
        # +0.005 is below min_delta -> still stale
        es.on_epoch_end(1, 0.505)
        assert es.on_epoch_end(2, 0.505) is True

    def test_tracks_best_epoch_and_value(self):
        es = EarlyStopping(patience=10)
        metrics = [0.5, 0.6, 0.55, 0.7, 0.69, 0.7, 0.71]
        for epoch, m in enumerate(metrics):
            es.on_epoch_end(epoch, m)
        assert es.best_epoch == 6
        assert es.best_value == pytest.approx(0.71)

    def test_none_metric_counts_as_stale(self):
        es = EarlyStopping(patience=1)
        assert es.on_epoch_end(0, None) is True
        # None then an improvement resets the stale counter
        es = EarlyStopping(patience=2)
        assert es.on_epoch_end(0, None) is False  # stale 1
        assert es.on_epoch_end(1, 0.5) is False   # improvement resets
        assert es.on_epoch_end(2, 0.5) is False   # stale 1
        assert es.on_epoch_end(3, 0.5) is True    # stale 2 = patience

    def test_rejects_bad_patience(self):
        with pytest.raises(ValueError):
            EarlyStopping(patience=0)


class TestReduceLROnPlateau:
    def test_lr_halved_after_patience_stale(self):
        applied = []

        def set_lr(lr):
            applied.append(lr)

        sched = ReduceLROnPlateau(factor=0.5, patience=3, initial_lr=1e-3)
        # improvements, then 3 stale epochs -> reduction on the 3rd stale one
        sched.on_epoch_end(0, 0.5)
        sched.on_epoch_end(1, 0.6)
        sched.on_epoch_end(2, 0.6)
        sched.on_epoch_end(3, 0.6)
        assert sched.on_epoch_end(4, 0.6, set_lr=set_lr) is True
        assert applied == [5e-4]
        assert sched.current_lr == pytest.approx(5e-4)
        assert sched.reductions == 1

    def test_reduces_again_after_another_plateau(self):
        sched = ReduceLROnPlateau(factor=0.5, patience=2, initial_lr=1e-3)
        for m in [0.5, 0.5, 0.5]:
            sched.on_epoch_end(0, m)  # epoch numbering resets; patience logic matters
        assert sched.current_lr == pytest.approx(5e-4)
        for _ in range(2):
            sched.on_epoch_end(0, 0.5)
        assert sched.current_lr == pytest.approx(2.5e-4)
        assert sched.reductions == 2

    def test_improvement_resets_stale_counter(self):
        sched = ReduceLROnPlateau(factor=0.5, patience=3, initial_lr=1e-3)
        sched.on_epoch_end(0, 0.5)
        sched.on_epoch_end(1, 0.5)  # 1 stale
        sched.on_epoch_end(2, 0.8)  # improvement resets
        assert sched.reductions == 0
        sched.on_epoch_end(3, 0.8)
        sched.on_epoch_end(4, 0.8)
        assert sched.on_epoch_end(5, 0.8) is True
        assert sched.reductions == 1

    def test_never_below_min_lr(self):
        sched = ReduceLROnPlateau(factor=0.5, patience=1, min_lr=1e-5, initial_lr=1e-5)
        for _ in range(5):
            assert sched.on_epoch_end(0, 0.5) is False  # at min_lr: no further reduction
        assert sched.current_lr == pytest.approx(1e-5)
        assert sched.reductions == 0

    def test_requires_known_lr(self):
        sched = ReduceLROnPlateau(factor=0.5, patience=1)
        sched.on_epoch_end(0, 0.5)  # first call: improvement, no reduction
        with pytest.raises(ValueError, match="learning rate unknown"):
            sched.on_epoch_end(1, 0.5)

    def test_rejects_bad_factor_or_patience(self):
        with pytest.raises(ValueError):
            ReduceLROnPlateau(factor=1.5)
        with pytest.raises(ValueError):
            ReduceLROnPlateau(factor=0.0)
        with pytest.raises(ValueError):
            ReduceLROnPlateau(patience=0)