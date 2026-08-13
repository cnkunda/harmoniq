#!/usr/bin/env python3
"""Training callbacks for the real-audio chord model pipeline (Commit 103).

Standalone, framework-free hook classes used by ``build_chord_tflite.py``:
the streaming real/synthetic training loop stays a manual
``train_on_batch`` loop (no ``model.fit``/generator refactor), and these
classes decide *when to stop* and *when to lower the learning rate* based on
the per-epoch validation metric.  ``EarlyStopping`` additionally exposes
``best_epoch``/``best_value`` so the loop can restore the best weights.

Design notes:
- No TensorFlow import at module top — unit-testable without TF.
- Callbacks are inspectable: pure state + one ``on_epoch_end`` call each.
- All compares use ``>`` semantics (higher is better), matching the repo's
  "root accuracy" monitoring convention.
"""

from __future__ import annotations

from typing import Callable, Optional


class EarlyStopping:
    """Stop training when a monitored (higher-is-better) metric plateaus.

    Usage::

        es = EarlyStopping(patience=5)
        for epoch in range(epochs):
            val_root = evaluate(...)
            if es.on_epoch_end(epoch, val_root):
                break
        # loop then restores the weights saved at es.best_epoch

    Args:
        patience: Epochs without improvement before stopping.
        min_delta: Minimum improvement to count as "better".
    """

    def __init__(self, patience: int = 5, min_delta: float = 0.0, name: str = "val_root"):
        if patience < 1:
            raise ValueError(f"patience must be >= 1, got {patience}")
        self.patience = int(patience)
        self.min_delta = float(min_delta)
        self.name = name
        self.best_value = -float("inf")
        self.best_epoch = -1
        self._stale_epochs = 0
        self._stopped = False

    def on_epoch_end(self, epoch: int, metric: float) -> bool:
        """Record the epoch's metric; return True when training must stop.

        ``metric`` must be a float (higher is better).  ``None`` counts as
        no improvement (safe for an early failed evaluation).
        """
        if metric is not None and metric > self.best_value + self.min_delta:
            self.best_value = float(metric)
            self.best_epoch = int(epoch)
            self._stale_epochs = 0
        else:
            self._stale_epochs += 1

        if self._stale_epochs >= self.patience:
            self._stopped = True
        return self._stopped

    @property
    def stopped(self) -> bool:
        return self._stopped

    @property
    def stale_epochs(self) -> int:
        return self._stale_epochs


class ReduceLROnPlateau:
    """Halve the learning rate when a monitored metric plateaus.

    Usage::

        sched = ReduceLROnPlateau(factor=0.5, patience=3, min_lr=1e-5)
        for epoch in range(epochs):
            val_root = evaluate(...)
            sched.on_epoch_end(epoch, val_root, set_lr=my_setter)

    ``set_lr(new_lr)`` is invoked the first time the metric has been stale
    for ``patience`` epochs.  ``current_lr`` must be known before the first
    reduction — either seed it via ``initial_lr`` at construction or call
    ``on_epoch_end`` with a ``set_lr`` that records the current value.

    Returns True on the epoch where a reduction is applied.
    """

    def __init__(
        self,
        factor: float = 0.5,
        patience: int = 3,
        min_lr: float = 1e-5,
        min_delta: float = 0.0,
        initial_lr: Optional[float] = None,
        name: str = "val_root",
    ):
        if not 0.0 < factor < 1.0:
            raise ValueError(f"factor must be in (0, 1), got {factor}")
        if patience < 1:
            raise ValueError(f"patience must be >= 1, got {patience}")
        self.factor = float(factor)
        self.patience = int(patience)
        self.min_lr = float(min_lr)
        self.min_delta = float(min_delta)
        self.name = name
        self.initial_lr = float(initial_lr) if initial_lr is not None else None
        self.current_lr = self.initial_lr
        self.reductions = 0
        self.best_value = -float("inf")
        self._stale_epochs = 0

    def on_epoch_end(
        self,
        epoch: int,
        metric: float,
        set_lr: Optional[Callable[[float], None]] = None,
    ) -> bool:
        """Record the epoch's metric; reduce LR (and return True) on plateau."""
        improved = metric is not None and metric > self.best_value + self.min_delta
        if improved:
            self.best_value = float(metric)
            self._stale_epochs = 0
            return False

        self._stale_epochs += 1
        if self._stale_epochs < self.patience:
            return False

        self._stale_epochs = 0
        if self.current_lr is None:
            raise ValueError(
                "ReduceLROnPlateau: current learning rate unknown — pass "
                "initial_lr at construction or supply set_lr"
            )
        new_lr = max(self.current_lr * self.factor, self.min_lr)
        if new_lr >= self.current_lr:
            return False  # already at min_lr
        self.current_lr = new_lr
        self.reductions += 1
        if set_lr is not None:
            set_lr(new_lr)
        return True