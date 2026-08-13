"""Real-audio window dataset + evaluation tests (Commit 106)."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from real_dataset import (  # noqa: E402
    EVAL_STRIDE,
    RealChordDataset,
    evaluate_real,
    make_mixed_batch,
    root_accuracy,
)
from real_label_vocab import NO_CHORD_IDX  # noqa: E402


def build_fake_real_dir(tmp_path, n_tracks=6, n_frames=200):
    """Create manifest/split/npz caches for n_tracks deterministic tracks."""
    real_dir = tmp_path / "real_audio"
    processed = real_dir / "processed"
    processed.mkdir(parents=True)
    manifest = []
    split = {}
    for i in range(n_tracks):
        track_id = f"artist{(i % 3):02d}_track{i:02d}"
        rng = np.random.default_rng(i)
        features = rng.random((n_frames, 40), dtype=np.float32)
        labels = np.arange(n_frames, dtype=np.int32) % 3  # classes 0,1,2 only
        center_mask = np.ones(n_frames, dtype=bool)
        np.savez_compressed(
            processed / f"{track_id}.npz",
            features=features,
            labels=labels,
            center_mask=center_mask,
            frame_times=np.arange(n_frames, dtype=np.float32) * 0.1,
            artist=f"artist{i % 3:02d}",
            source="fake",
        )
        manifest.append(
            {
                "track_id": track_id,
                "source": "fake",
                "artist": f"artist{i % 3:02d}",
                "n_frames": n_frames,
                "n_usable": n_frames,
                "coverage": 1.0,
                "duration_s": n_frames * 0.1,
                "gate_ok": True,
                "reason": "",
            }
        )
        # train: artists 00/01 (tracks 0-3), val: artist 02 (tracks 4), test: none
        split[track_id] = {
            "artist": f"artist{i % 3:02d}",
            "split": "train" if i % 3 != 2 else "val",
        }
    (real_dir / "manifest.json").write_text(json.dumps(manifest))
    (real_dir / "split.json").write_text(json.dumps(split))
    return real_dir


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------


def test_constructor_selects_split_tracks(tmp_path):
    real_dir = build_fake_real_dir(tmp_path)
    ds = RealChordDataset(real_dir, "train")
    assert len(ds.tracks) == 4  # tracks 0,1,3,4 (artists 00,01)
    assert ds.artists == {"artist00": 2, "artist01": 2}


def test_constructor_raises_on_empty_split(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_tracks=3)
    with pytest.raises(ValueError, match="no gated tracks"):
        RealChordDataset(real_dir, "test")


def test_gated_out_tracks_are_excluded(tmp_path):
    real_dir = build_fake_real_dir(tmp_path)
    manifest = json.loads((real_dir / "manifest.json").read_text())
    manifest[0]["gate_ok"] = False
    (real_dir / "manifest.json").write_text(json.dumps(manifest))
    ds = RealChordDataset(real_dir, "train")
    assert all(t["gate_ok"] for t in ds.tracks)
    assert "artist00_track00" not in [t["track_id"] for t in ds.tracks]


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def test_sample_window_shape_and_dtype(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_frames=300)
    ds = RealChordDataset(real_dir, "train", window=128)
    X, y = ds.sample_window()
    assert X.shape == (128, 40)
    assert X.dtype == np.float32
    assert 0 <= y <= 2


def test_sample_window_pads_edges_with_zeros(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_frames=10)
    ds = RealChordDataset(real_dir, "train", window=128, jitter_frames=0)
    # All usable centers in a 10-frame track produce edge windows
    padded = 0
    total = 0
    for _ in range(200):
        X, _ = ds.sample_window()
        total += 1
        if X[:118].sum() == 0 or X[10:].sum() == 0 or X[118:].sum() == 0:
            padded += 1
    assert padded == total  # every window from a 10-frame track is padded


def test_sample_window_label_is_center_frame(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_frames=300)
    ds = RealChordDataset(real_dir, "train", window=64, jitter_frames=0)
    X, y = ds.sample_window()
    assert int(np.argmax(X, axis=1).max()) >= 0  # features present


# ---------------------------------------------------------------------------
# Mixed batch builder
# ---------------------------------------------------------------------------


def test_make_mixed_batch_ratio_and_shuffle(tmp_path):
    real_dir = build_fake_real_dir(tmp_path)
    ds = RealChordDataset(real_dir, "train", seed=7)
    rng = np.random.default_rng(7)

    def fake_synth(n, rng):
        return np.zeros((n, 128, 40), dtype=np.float32), np.full(n, NO_CHORD_IDX)

    X, y = make_mixed_batch(ds, fake_synth, batch_size=64, real_ratio=0.7, rng=rng)
    assert X.shape == (64, 128, 40)
    assert len(y) == 64
    # 70% real (45) + 30% synth (19); synth windows are all zeros -> detectable
    n_real = int((X.sum(axis=(1, 2)) > 0).sum())
    assert n_real == 45
    assert (y == NO_CHORD_IDX).sum() == 19
    # shuffled: real windows not all at the front
    assert (y[:20] == NO_CHORD_IDX).sum() < 20


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def test_root_accuracy_math():
    y_true = np.array([0, 1, 26, 276])   # C:maj, C#:maj, D:7, N
    y_pred = np.array([0, 26, 14, 276])  # C:maj, D:7, D:min, N
    assert root_accuracy(y_true, y_true) == 1.0
    # matches: (0,0) ✓, (0,2) ✗, (2,2) ✓, (-1,-1) ✓ -> 3/4
    assert root_accuracy(y_true, y_pred) == 0.75
    # chord-only: N pair excluded -> 2/3
    assert root_accuracy(y_true, y_pred, include_no_chord=False) == pytest.approx(2 / 3)


def test_evaluate_real_metrics(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_frames=300)
    ds = RealChordDataset(real_dir, "train")
    # label[k] = k % 3 (classes 0,1,2). Deterministic predictor: counter-based
    # cycle 0,1,0,... aligned with the eval windows.
    counter = {"i": 0}

    def predict_fn(X):
        n = len(X)
        out = np.zeros((n, 277), dtype=np.float32)
        for j in range(n):
            out[j, [0, 1, 0][(counter["i"] + j) % 3]] = 1.0
        counter["i"] += n
        return out

    metrics = evaluate_real(predict_fn, ds)
    overall = metrics["overall"]
    assert overall["n_windows"] > 0
    y_true_all = []
    for _, _, y in ds.windows_for_eval(stride=EVAL_STRIDE):
        y_true_all.extend(int(v) for v in y)
    n = len(y_true_all)
    expected_correct = 0
    for k, t in enumerate(y_true_all):
        if t == [0, 1, 0][k % 3]:
            expected_correct += 1
    assert overall["full_accuracy"] == pytest.approx(expected_correct / n)
    assert 0.0 <= overall["root_accuracy"] <= 1.0
    assert set(metrics["per_artist"]) == {"artist00", "artist01"}
    assert "triad" in metrics["per_group"]


def test_evaluate_real_perfect_predictor(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_frames=200)
    ds = RealChordDataset(real_dir, "train")
    # Relabel every window to class 0 so a constant predictor is perfect.
    for track in ds.tracks:
        np.savez_compressed(
            ds.real_dir / "processed" / f"{track['track_id']}.npz",
            features=np.ones((200, 40), dtype=np.float32),
            labels=np.zeros(200, dtype=np.int32),
            center_mask=np.ones(200, dtype=bool),
            frame_times=np.arange(200, dtype=np.float32) * 0.1,
            artist=track["artist"],
            source="fake",
        )
    ds._cache.clear()

    def predict_fn(X):
        out = np.zeros((len(X), 277), dtype=np.float32)
        out[:, 0] = 1.0
        return out

    metrics = evaluate_real(predict_fn, ds)
    assert metrics["overall"]["full_accuracy"] == 1.0
    assert metrics["overall"]["root_accuracy"] == 1.0
    assert metrics["per_group"]["triad"] == 1.0


# ---------------------------------------------------------------------------
# Commit 103: label-aware augmentation
# ---------------------------------------------------------------------------


class _SeqRng:
    """Deterministic stub rng returning pre-scripted values in order."""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def random(self):
        v = self._values[self._i]
        self._i += 1
        return v

    def uniform(self, a, b):
        v = self._values[self._i]
        self._i += 1
        return v

    def integers(self, a, b):
        v = self._values[self._i]
        self._i += 1
        return v


def test_shift_pitch_rolls_within_octaves():
    from real_dataset import shift_pitch

    w = np.zeros((3, 40), dtype=np.float32)
    w[:, 0] = 1.0   # octave 1 root
    w[:, 12] = 2.0  # octave 2 root
    w[:, 24] = 3.0  # octave 3 root
    s = shift_pitch(w, 2)
    # each octave rolled internally by +2 (register preserved)
    assert s[0, 2] == 1.0 and s[0, 0] == 0.0
    assert s[0, 14] == 2.0 and s[0, 12] == 0.0
    assert s[0, 26] == 3.0 and s[0, 24] == 0.0
    # bass channel mirrors the lowest bins of the rolled CQT
    np.testing.assert_array_equal(s[:, 36:], s[:, :4])


def test_shift_pitch_zero_is_identity():
    from real_dataset import shift_pitch

    w = np.random.rand(5, 40).astype(np.float32)
    np.testing.assert_array_equal(shift_pitch(w, 0), w)


def test_time_stretch_preserves_shape_and_identity():
    from real_dataset import time_stretch

    w = np.random.rand(128, 40).astype(np.float32)
    np.testing.assert_array_equal(time_stretch(w, 1.0), w)
    assert time_stretch(w, 1.1).shape == w.shape
    assert time_stretch(w, 0.9).shape == w.shape


def test_transpose_class_moves_root_keeps_quality():
    from real_dataset import transpose_class

    # C:maj (index 0) +2 semitones -> D:maj (index 2)
    assert transpose_class(0, 2) == 2
    # C#:maj (index 1) +11 -> C:maj
    assert transpose_class(1, 11) == 0
    # wraps mod 12
    assert transpose_class(0, 14) == 2
    # no-chord maps to itself
    assert transpose_class(NO_CHORD_IDX, 5) == NO_CHORD_IDX


def test_augment_window_pitch_shift_transposes_label(tmp_path):
    from real_dataset import augment_window

    src = np.zeros((9, 40), dtype=np.float32)
    src[:, 0] = 1.0
    src[:, 12] = 1.0
    src[:, 24] = 1.0
    labels = np.zeros(200, dtype=np.int32)
    rng = _SeqRng([0.9, 0.0, 1])  # stretch skipped, pitch triggered, k=+1
    cfg = {"time_stretch_rate": 0.0, "pitch_shift_rate": 1.0, "pitch_shift_max": 2}
    window, label = augment_window(src, label=5, data={"labels": labels},
                                   center=100, rng=rng, cfg=cfg)
    from real_dataset import shift_pitch, transpose_class

    np.testing.assert_array_equal(window, shift_pitch(src, 1))
    assert label == transpose_class(5, 1)


def test_augment_window_time_stretch_relabels_center(tmp_path):
    from real_dataset import augment_window

    labels = np.zeros(400, dtype=np.int32)
    labels[190:] = 4          # center 199 -> class 4
    center = 199
    src = np.random.rand(128, 40).astype(np.float32)
    # stretch only: random()=0.1 < 0.3 -> stretch; uniform=1.1; random()=0.9 >= 0.4 -> no pitch
    rng = _SeqRng([0.1, 1.1, 0.9])
    cfg = {"time_stretch_rate": 0.3, "time_stretch_range": (0.9, 1.1),
           "pitch_shift_rate": 0.4, "pitch_shift_max": 2}
    window, label = augment_window(src, label=4, data={"labels": labels},
                                   center=199, rng=rng, cfg=cfg)
    # new center (index 64) lands at original frame round(199 / 1.1) = 181 -> class 0
    assert label == 0
    assert window.shape == src.shape


def test_class_weight_map_balanced_and_capped(tmp_path):
    from real_dataset import class_weight_map

    real_dir = build_fake_real_dir(tmp_path, n_frames=300)
    ds = RealChordDataset(real_dir, "train", seed=1)
    w = class_weight_map(ds)
    assert w.shape == (277,)
    assert w.dtype == np.float32
    # labels are arange % 3 -> classes 0,1,2 balanced, mean weight ~1
    assert abs(w[0] - 1.0) < 0.1
    assert abs(w[1] - 1.0) < 0.1
    assert abs(w[2] - 1.0) < 0.1
    # unused classes get weight 1.0 (synthetic temperature sampling covers them)
    assert w[3] == pytest.approx(1.0)
    assert w.max() <= 5.0 and w.min() >= 0.2


def test_class_weight_map_imbalanced(tmp_path):
    from real_dataset import class_weight_map

    real_dir = build_fake_real_dir(tmp_path, n_frames=300)
    # rewrite labels: 90% class 0, 10% class 1
    for track_id in sorted(p.name for p in (real_dir / "processed").glob("*.npz")):
        data = np.load(real_dir / "processed" / track_id)
        n = len(data["labels"])
        labels = np.zeros(n, dtype=np.int32)
        labels[::10] = 1
        np.savez_compressed(
            real_dir / "processed" / track_id,
            features=data["features"],
            labels=labels,
            center_mask=data["center_mask"],
            frame_times=data["frame_times"],
            artist=str(data["artist"]),
            source="fake",
        )
    ds = RealChordDataset(real_dir, "train", seed=1)
    w = class_weight_map(ds)
    assert w[0] < w[1]  # frequent class weighted down, rare class up


def test_make_mixed_batch_sample_weights(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_frames=300)
    ds = RealChordDataset(real_dir, "train", seed=7)
    rng = np.random.default_rng(7)
    cw = np.ones(277, dtype=np.float32)
    cw[0] = 0.5
    cw[1] = 2.0

    def fake_synth(n, rng):
        return np.zeros((n, 128, 40), dtype=np.float32), np.full(n, NO_CHORD_IDX)

    X, y, w = make_mixed_batch(ds, fake_synth, batch_size=64, real_ratio=0.7,
                               rng=rng, class_weights=cw)
    assert X.shape == (64, 128, 40)
    assert len(w) == 64
    n_real = int((X.sum(axis=(1, 2)) > 0).sum())
    for i in range(64):
        if X[i].sum() > 0:  # real window -> real-data class weight
            assert w[i] == pytest.approx(cw[int(y[i])])
        else:  # synthetic window -> weight 1.0 (temp sampling handles imbalance)
            assert w[i] == pytest.approx(1.0)
    assert n_real == 45
    assert set(np.unique(w)) <= {0.5, 1.0, 2.0}


# ---------------------------------------------------------------------------
# Commit 103: confusion matrix + per-class P/R/F1
# ---------------------------------------------------------------------------


def test_confusion_metrics_perfect_predictor():
    from real_dataset import confusion_metrics

    y_true = np.arange(12, dtype=np.int32)
    cm = confusion_metrics(y_true, y_true)
    assert all(m["f1"] == 1.0 for m in cm["per_class"].values())
    assert cm["per_root"]["C"]["f1"] == 1.0
    assert cm["per_quality"]["maj"]["f1"] == 1.0
    assert cm["top_confusions"] == []
    assert cm["root_confusion"].shape == (13, 13)
    assert int(cm["root_confusion"].sum()) == 12
    assert int(np.diag(cm["root_confusion"]).sum()) == 12


def test_confusion_metrics_identifies_confused_pairs():
    from real_dataset import confusion_metrics

    # class 3 = D#:maj, 4 = E:maj, 10 = A#:maj, 11 = B:maj
    y_true = np.array([3, 3, 3, 10, 10], dtype=np.int32)
    y_pred = np.array([3, 4, 4, 10, 11], dtype=np.int32)
    cm = confusion_metrics(y_true, y_pred, top_k=5)
    assert cm["top_confusions"][0] == {
        "true": "D#", "predicted": "E", "count": 2,
    }
    assert cm["top_confusions"][1]["true"] == "A#"
    assert 4 not in cm["per_class"]  # absent from y_true -> excluded
    assert cm["per_root"]["D#"]["recall"] == pytest.approx(1 / 3, abs=0.001)
    assert cm["root_confusion"][4, 5] == 2  # D# true (row 1+3), E predicted


def test_evaluate_real_with_confusion(tmp_path):
    real_dir = build_fake_real_dir(tmp_path, n_frames=300)
    # all-class-0 tracks so the constant predictor is perfect
    for p in (real_dir / "processed").glob("*.npz"):
        data = np.load(p)
        np.savez_compressed(
            p,
            features=data["features"],
            labels=np.zeros(len(data["labels"]), dtype=np.int32),
            center_mask=data["center_mask"],
            frame_times=data["frame_times"],
            artist=str(data["artist"]),
            source="fake",
        )
    ds = RealChordDataset(real_dir, "train")

    def predict_fn(X):
        out = np.zeros((len(X), 277), dtype=np.float32)
        out[:, 0] = 1.0
        return out

    metrics = evaluate_real(predict_fn, ds, with_confusion=True)
    assert "per_class" in metrics
    assert "confusion" in metrics
    assert metrics["per_class"][0]["f1"] == 1.0
    assert len(metrics["confusion"]["root_confusion"]) == 13
    # without the flag, existing key set is untouched
    plain = evaluate_real(predict_fn, ds)
    assert "per_class" not in plain
    assert "confusion" not in plain