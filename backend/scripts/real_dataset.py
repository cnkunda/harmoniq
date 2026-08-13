#!/usr/bin/env python3
"""Real-audio window dataset, mixed batch builder, and evaluation (Commit 101).

Consumes the cache produced by ``prepare_real_datasets.py``
(``backend/data/real_audio/``): per-track npz files with 40-dim CQT features,
frame-aligned class labels, a center mask, plus ``manifest.json`` /
``split.json``.  This module intentionally does not import
``build_chord_tflite.py`` (which depends on TensorFlow) so the dataset and
evaluation paths can be tested quickly and used standalone; the training
script passes its own synthetic-batch callable here.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from real_label_vocab import (
    CHORD_CLASS_MAP,
    CHORD_VOCAB,
    NO_CHORD_IDX,
    NUM_CLASSES,
    QUALITY_GROUP_MASKS,
    ROOT_NOTES,
)

HOP_SEC = 0.1  # 10 ms frame hop (40-dim CQT across 4 octaves)
EVAL_STRIDE = 8  # sample every 8th usable frame during evaluation

N_BINS = 36  # 3 octaves x 12 chroma (matches build_chord_tflite.CHROMA_BINS)
BASS_BINS = 4
FEATURE_DIM = N_BINS + BASS_BINS  # 40

# Commit 103 augmentation defaults (applied to real windows during training)
AUGMENT_DEFAULTS = {
    "pitch_shift_rate": 0.4,   # fraction of real windows pitch-transposed
    "pitch_shift_max": 2,      # +/- semitones
    "time_stretch_rate": 0.3,  # fraction of real windows time-stretched
    "time_stretch_range": (0.9, 1.1),
}

# class -> (root, quality) reverse lookup for label transposition
_CLASS_BY_ROOT_QUALITY = {
    (root, quality): idx for idx, (root, quality) in enumerate(CHORD_CLASS_MAP)
}


# ---------------------------------------------------------------------------
# Label-aware augmentation (Commit 103)
# ---------------------------------------------------------------------------


def shift_pitch(window: np.ndarray, shift_semitones: int) -> np.ndarray:
    """Transpose a (T, 40) CQT window by ``shift_semitones``.

    The 36 CQT bins are three octaves of 12; each octave is rolled *within*
    itself so register is preserved (a plain ``np.roll`` across the 36 bins
    would push octave-3 energy into octave-1, corrupting the octave
    structure the model uses).  The 4 bass bins are the lowest bins of the
    rolled CQT, mirroring how ``chord_inference._run_tflite_raw`` derives
    them (``cqt[:, :4]``).

    Callers must transpose the class label by the same amount (mod 12) via
    :func:`transpose_class`.
    """
    if shift_semitones == 0:
        return window
    cqt = window[:, :N_BINS].reshape(window.shape[0], 3, 12)
    rolled = np.roll(cqt, shift_semitones, axis=-1).reshape(window.shape[0], N_BINS)
    return np.concatenate([rolled, rolled[:, :BASS_BINS]], axis=-1)


def time_stretch(window: np.ndarray, stretch_factor: float) -> np.ndarray:
    """Interpolate temporal frames for speed variation (feature-space).

    ``result[t]`` samples the input at index ``t * stretch_factor``; a
    factor > 1 makes the same content take more frames (slower).
    """
    if abs(stretch_factor - 1.0) < 1e-6:
        return window
    original_length = window.shape[0]
    original_times = np.arange(original_length)
    stretched_times = original_times * stretch_factor
    result = np.zeros_like(window)
    for bin_idx in range(window.shape[1]):
        result[:, bin_idx] = np.interp(
            original_times, stretched_times, window[:, bin_idx],
            left=window[0, bin_idx], right=window[-1, bin_idx],
        )
    return result


def transpose_class(class_idx: int, semitones: int) -> int:
    """Transpose a class index by ``semitones`` (root moves, quality stays).

    The no-chord class maps to itself.
    """
    if class_idx == NO_CHORD_IDX:
        return NO_CHORD_IDX
    root, quality = CHORD_CLASS_MAP[class_idx]
    return _CLASS_BY_ROOT_QUALITY[((root + semitones) % 12, quality)]


def augment_window(window, label, data, center, rng, cfg=None):
    """Apply label-aware pitch shift / time stretch to one real window.

    Order matters: the window is stretched first (content re-indexed, label
    re-read from the ORIGINAL label array at the position that lands on the
    new center), then pitch-shifted (feature and label transposed together).

    Args:
        window: (T, 40) window sampled around ``center``.
        label: Class index of the window (label of frame ``center``).
        data: Track dict as returned by ``RealChordDataset._load``.
        center: Frame index the window is centered on.
        rng: ``numpy.random.Generator`` used for all stochastic choices.
        cfg: Augmentation config dict (keys of ``AUGMENT_DEFAULTS``).

    Returns:
        (window, label) — augmented window and its consistent label.
    """
    cfg = {**AUGMENT_DEFAULTS, **(cfg or {})}

    if rng.random() < cfg["time_stretch_rate"]:
        factor = float(rng.uniform(*cfg["time_stretch_range"]))
        if abs(factor - 1.0) > 1e-6:
            window = time_stretch(window, factor)
            src = int(round(center / factor))
            src = min(max(src, 0), len(data["labels"]) - 1)
            label = int(data["labels"][src])

    if rng.random() < cfg["pitch_shift_rate"]:
        k = int(rng.integers(-cfg["pitch_shift_max"], cfg["pitch_shift_max"] + 1))
        if k != 0:
            window = shift_pitch(window, k)
            label = transpose_class(label, k)

    return window, label


class RealChordDataset:
    """Random-window sampler over the gated, split real-audio cache."""

    def __init__(
        self,
        real_dir,
        split="train",
        window=128,
        jitter_frames=1,
        seed=None,
    ):
        self.real_dir = Path(real_dir)
        self.split = split
        self.window = window
        self.jitter = jitter_frames
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        else:
            self.rng = None

        manifest = json.loads((self.real_dir / "manifest.json").read_text())
        split_map = json.loads((self.real_dir / "split.json").read_text())

        self.tracks = []
        artists = Counter()
        for entry in manifest:
            if not entry.get("gate_ok"):
                continue
            train_split = split_map.get(entry["track_id"], {}).get("split")
            if train_split != split:
                continue
            track = dict(entry)
            track["artist"] = track.get(
                "artist", split_map.get(entry["track_id"], {}).get("artist", "?")
            )
            self.tracks.append(track)
            artists[track["artist"]] += 1

        self.artists = dict(artists)
        if not self.tracks:
            raise ValueError(f"no gated tracks found for split '{split}' in {self.real_dir}")

        usable = np.array([t["n_usable"] for t in self.tracks], dtype=float)
        self._sample_weights = usable / usable.sum()
        if self.rng is None:
            self.rng = np.random.default_rng()
        self._cache = {}

    # -- data access --------------------------------------------------------

    def _load(self, track_id):
        if track_id not in self._cache:
            data = np.load(self.real_dir / "processed" / f"{track_id}.npz")
            self._cache[track_id] = {
                "features": data["features"],
                "labels": data["labels"],
                "center_mask": data["center_mask"],
            }
        return self._cache[track_id]

    def _window(self, data, center):
        """Zero-padded window around a frame center (label of center frame)."""
        half = self.window // 2
        features = data["features"]
        n = features.shape[0]
        start = center - half
        end = start + self.window
        window = np.zeros((self.window, features.shape[1]), dtype=features.dtype)
        src_start = max(start, 0)
        src_end = min(end, n)
        window[src_start - start : src_end - start] = features[src_start:src_end]
        return window

    # -- sampling -----------------------------------------------------------

    def sample_window(self, rng=None, augment=None):
        """Draw one (window, label) pair from a random usable center frame.

        The label is taken from the un-jittered center frame; jitter shifts
        the audio content within the window (commit 102 augmentation).  When
        ``augment`` is a dict (Commit 103), label-aware pitch shift (±2
        semitones) and time stretch (0.9-1.1) are applied afterwards — the
        returned label is transposed/re-read to stay consistent with the
        augmented window.
        """
        rng = rng or self.rng
        track = self.tracks[rng.choice(len(self.tracks), p=self._sample_weights)]
        data = self._load(track["track_id"])
        centers = np.flatnonzero(data["center_mask"])
        center = int(centers[rng.integers(0, len(centers))])
        for _ in range(2):
            if self.jitter:
                candidate = int(center + rng.integers(-self.jitter, self.jitter + 1))
                if 0 <= candidate < len(data["labels"]):
                    center = candidate
        label = int(data["labels"][center])
        window = self._window(data, center)
        if augment:
            window, label = augment_window(window, label, data, center, rng, augment)
        return window, label

    def windows_for_eval(self, stride=EVAL_STRIDE):
        """Yield (artist, X, y) chunks over all usable frames, strided."""
        YIELD_CHUNK = 256
        for track in self.tracks:
            data = self._load(track["track_id"])
            centers = np.flatnonzero(data["center_mask"])[::stride]
            labels = data["labels"]
            for i in range(0, len(centers), YIELD_CHUNK):
                chunk = centers[i : i + YIELD_CHUNK]
                X = np.stack([self._window(data, int(c)) for c in chunk])
                yield track["artist"], X, labels[chunk]

    def class_distribution(self):
        counts = Counter()
        for _, _, y in self.windows_for_eval(stride=EVAL_STRIDE):
            counts.update(int(v) for v in y)
        return counts


# ---------------------------------------------------------------------------
# Mixed synthetic + real batch builder
# ---------------------------------------------------------------------------


def make_mixed_batch(dataset, synth_fn, batch_size, real_ratio=0.7, rng=None,
                     class_weights=None, augment=None):
    """Concatenate real windows with synthetic windows and shuffle.

    ``synth_fn(n, rng)`` must return ``(X (n, window, 40), y (n,))``.

    When ``class_weights`` (length-``NUM_CLASSES`` array) is given, the
    return value is ``(X, y, w)`` — a per-sample weight vector for
    ``train_on_batch(sample_weight=...)`` (Commit 103 class weighting).
    Class weights apply to REAL windows only: synthetic windows already
    have their imbalance handled by MT3 temperature sampling, so applying
    the real-data inverse-frequency weights on top would double-boost rare
    classes (verified: collapsed training accuracy).
    When ``augment`` (dict) is given, real windows get label-aware
    pitch shift / time stretch (Commit 103).
    """
    rng = rng or np.random.default_rng()
    n_real = int(round(batch_size * real_ratio))
    parts_X = []
    parts_y = []
    parts_w = []
    if n_real > 0:
        real = [dataset.sample_window(rng, augment=augment) for _ in range(n_real)]
        parts_X.append(np.stack([x for x, _ in real]))
        real_y = np.asarray([y for _, y in real], dtype=np.int32)
        parts_y.append(real_y)
        if class_weights is not None:
            parts_w.append(np.asarray([class_weights[int(y)] for y in real_y], dtype=np.float32))
    X_synth, y_synth = synth_fn(batch_size - n_real, rng)
    parts_X.append(X_synth)
    parts_y.append(np.asarray(y_synth))
    if class_weights is not None:
        parts_w.append(np.ones(len(y_synth), dtype=np.float32))
    X = np.concatenate(parts_X, axis=0)
    y = np.concatenate(parts_y, axis=0)
    perm = rng.permutation(len(y))
    X, y = X[perm], y[perm]
    if class_weights is None:
        return X, y
    w = np.concatenate(parts_w, axis=0)[perm]
    return X, y, w


def class_weight_map(dataset, cap=(0.2, 5.0), stride=EVAL_STRIDE):
    """Inverse-frequency per-class weights over a dataset's strided windows.

    Real audio is heavily imbalanced (maj ~14k vs rare types ~0); weighting
    counteracts that during mixed-batch training (Commit 103).  Weights are
    normalized to mean ~1 over the classes that appear in the dataset and
    clipped to ``cap``.  Classes with zero support get weight 1.0 — they are
    covered by synthetic temperature sampling during training, and inflating
    them here would double-boost rare classes.

    Returns a length-``NUM_CLASSES`` float32 array.
    """
    counts = np.zeros(NUM_CLASSES, dtype=np.int64)
    for _, _, y in dataset.windows_for_eval(stride=stride):
        for v in y:
            counts[int(v)] += 1
    n_classes = NUM_CLASSES
    total = int(counts.sum())
    if total == 0:
        return np.ones(NUM_CLASSES, dtype=np.float32)
    freq = counts / total
    nonzero = freq > 0
    weights = np.ones(n_classes, dtype=np.float32)
    if nonzero.any():
        weights[nonzero] = 1.0 / (n_classes * freq[nonzero])
        weights[nonzero] /= weights[nonzero].mean()
    lo, hi = float(cap[0]), float(cap[1])
    return np.clip(weights, lo, hi).astype(np.float32)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def root_index(class_idx):
    """Root (0-11) of a class index, -1 for the no-chord class."""
    if class_idx == NO_CHORD_IDX:
        return -1
    return CHORD_CLASS_MAP[class_idx][0]


def root_accuracy(y_true, y_pred, include_no_chord=True):
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    roots_t = np.array([root_index(int(v)) for v in y_true])
    roots_p = np.array([root_index(int(v)) for v in y_pred])
    if not include_no_chord:
        keep = roots_t != -1
        roots_t, roots_p = roots_t[keep], roots_p[keep]
    if len(roots_t) == 0:
        return 0.0
    return float((roots_t == roots_p).mean())


# ---------------------------------------------------------------------------
# Commit 103 diagnostics: confusion matrix + per-class precision/recall/F1
# ---------------------------------------------------------------------------


def _f1(precision, recall):
    if precision + recall <= 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def confusion_metrics(y_true, y_pred, top_k=10):
    """Per-class P/R/F1, root confusion matrix, and top confused pairs.

    Args:
        y_true: Ground truth class indices (N,).
        y_pred: Predicted class indices (N,).
        top_k: Number of most-confused (true, predicted) root pairs to keep.

    Returns:
        Dict with:
          - per_class: 277-class P/R/F1 for classes with support > 0
          - per_quality: per-quality P/R/F1 (incl. N)
          - per_root: per-root P/R/F1 (12 roots + N)
          - root_confusion: 13x13 matrix (rows: true root, cols: predicted;
            index 0 = N, 1-12 = C..B)
          - top_confusions: list of {true, predicted, count} root pairs,
            off-diagonal, sorted by count descending
    """
    y_true = np.asarray([int(v) for v in y_true])
    y_pred = np.asarray([int(v) for v in y_pred])
    n = len(y_true)
    if n == 0:
        return {"per_class": {}, "per_quality": {}, "per_root": {},
                "root_confusion": np.zeros((13, 13), dtype=int),
                "top_confusions": []}

    per_class = {}
    for c in np.unique(y_true):
        support = int((y_true == c).sum())
        pred_c = int((y_pred == c).sum())
        tp = int(((y_true == c) & (y_pred == c)).sum())
        precision = tp / pred_c if pred_c else 0.0
        recall = tp / support
        per_class[int(c)] = {
            "label": CHORD_VOCAB[int(c)],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(precision, recall), 4),
            "support": support,
        }

    qualities_t = [CHORD_CLASS_MAP[int(c)][1] for c in y_true]
    per_quality = {}
    for q in sorted(set(qualities_t)):
        mask_t = np.array([CHORD_CLASS_MAP[int(c)][1] == q for c in y_true])
        support = int(mask_t.sum())
        pred_q = np.array([CHORD_CLASS_MAP[int(c)][1] == q for c in y_pred])
        tp = int((mask_t & pred_q).sum())
        precision = tp / int(pred_q.sum()) if pred_q.sum() else 0.0
        recall = tp / support
        per_quality[q] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(precision, recall), 4),
            "support": support,
        }

    root_map = ["N"] + ROOT_NOTES  # matrix index i <-> root i-1 (index 0 = no-chord)
    roots_t = np.array([root_index(int(c)) for c in y_true])
    roots_p = np.array([root_index(int(c)) for c in y_pred])
    per_root = {}
    for r in range(-1, 12):
        mask_t = roots_t == r
        support = int(mask_t.sum())
        if support == 0:
            continue
        mask_p = roots_p == r
        tp = int((mask_t & mask_p).sum())
        precision = tp / int(mask_p.sum()) if mask_p.sum() else 0.0
        recall = tp / support
        per_root[root_map[r + 1]] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_f1(precision, recall), 4),
            "support": support,
        }

    root_confusion = np.zeros((13, 13), dtype=int)
    for t, p in zip(roots_t, roots_p):
        root_confusion[t + 1, p + 1] += 1

    off_diag = [
        (int(t), int(p), int(root_confusion[t, p]))
        for t in range(13) for p in range(13)
        if t != p and root_confusion[t, p] > 0
    ]
    off_diag.sort(key=lambda item: -item[2])
    top_confusions = [
        {"true": root_map[t], "predicted": root_map[p], "count": count}
        for t, p, count in off_diag[:top_k]
    ]

    return {
        "per_class": per_class,
        "per_quality": per_quality,
        "per_root": per_root,
        "root_confusion": root_confusion,
        "top_confusions": top_confusions,
    }


def evaluate_real(predict_fn, dataset, stride=EVAL_STRIDE, with_confusion=False):
    """Run full/root accuracy per artist, per group, and overall.

    ``predict_fn(X_batch)`` returns a probability matrix (N, NUM_CLASSES).
    Returns a metrics dict with ``overall``, ``per_group`` and
    ``per_artist`` entries.  With ``with_confusion=True`` (Commit 103)
    also returns per-class P/R/F1 + root confusion (see
    :func:`confusion_metrics`).
    """
    artist_windows = Counter()
    y_true_all = []
    y_pred_all = []
    artist_true = {}
    artist_pred = {}

    for artist, X, y_true in dataset.windows_for_eval(stride=stride):
        probs = predict_fn(X)
        y_pred = probs.argmax(axis=1)
        if y_pred.shape[0] != len(y_true):
            raise ValueError("predict_fn returned wrong batch size")
        artist_windows[artist] += len(y_true)
        y_true_all.extend(int(v) for v in y_true)
        y_pred_all.extend(int(v) for v in y_pred)
        artist_true.setdefault(artist, []).extend(int(v) for v in y_true)
        artist_pred.setdefault(artist, []).extend(int(v) for v in y_pred)

    metrics = {
        "overall": {
            "n_windows": len(y_true_all),
            "full_accuracy": float(
                (np.asarray(y_true_all) == np.asarray(y_pred_all)).mean()
            ),
            "root_accuracy": root_accuracy(y_true_all, y_pred_all),
            "root_accuracy_chord_only": root_accuracy(
                y_true_all, y_pred_all, include_no_chord=False
            ),
        },
        "per_artist": {},
        "per_group": {},
    }

    for artist in artist_true:
        metrics["per_artist"][artist] = {
            "n_windows": artist_windows[artist],
            "root_accuracy": root_accuracy(artist_true[artist], artist_pred[artist]),
        }

    y_true_arr = np.asarray(y_true_all)
    y_pred_arr = np.asarray(y_pred_all)
    for group, mask in QUALITY_GROUP_MASKS.items():
        keep = np.array([v in mask for v in y_true_arr])
        if keep.sum() == 0:
            continue
        metrics["per_group"][group] = float(
            (y_true_arr[keep] == y_pred_arr[keep]).mean()
        )

    if with_confusion:
        cm = confusion_metrics(y_true_all, y_pred_all)
        metrics["per_class"] = cm["per_class"]
        metrics["per_quality"] = cm["per_quality"]
        metrics["per_root"] = cm["per_root"]
        metrics["confusion"] = {
            "root_confusion": cm["root_confusion"].tolist(),
            "top_confusions": cm["top_confusions"],
        }

    return metrics


def write_eval_metrics(real_dir, split, metrics):
    out = Path(real_dir) / f"eval_{split}.json"
    out.write_text(json.dumps(metrics, indent=2))
    return out