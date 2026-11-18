"""Chord 170 v2 data pipeline.

Phase 2 scope:
  * Label mapping — legacy 277-class datasets to 170-class labels.
  * Bass derivation — lowest active note (GuitarSet, EGSet12, Guitar-TECHS,
    pseudo-labels) or the annotation's own slash bass (IDMT, RWC).
  * Pseudo-label filtering — ≥3 active pitches, confidence ≥ 0.6, N capped
    at ≤ 20% of the training set.
  * Track-level splits — windows are never split across splits; a track id
    must not appear under two different splits.
  * Dataset cards — per-source counts, N rate, unique classes, bass
    coverage, and an explicit overlap check.

Layout:

* Real datasets keep their existing ``<data>/processed/cqt/*.npz`` feature
  cache untouched. Derived labels/bass are written as sidecars to
  ``<data>/processed/chord170/<track>.npz`` and merged by the loader.
* Pseudo-labels are rebuilt from the W1 teacher outputs (MT3 chords +
  notes) into ``<out>/pseudo_v2/processed/cqt/*.npz`` with the full v2
  schema (features, labels170, bass_labels, confidence, centre times,
  source, teacher, split, loss_weight).

Usage (from backend/)::

    python scripts/chord_data_v2.py build-real --dataset guitarset
    python scripts/chord_data_v2.py build-real --dataset all
    python scripts/chord_data_v2.py build-pseudo
    python scripts/chord_data_v2.py card --out ../docs/audit/amt/chord170_phase2_dataset.json
    python scripts/chord_data_v2.py summary data/guitarset --split test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import (  # noqa: E402
    active_pitches,
    bass_from_degree,
    bass_pitch_class_from_notes,
    count_active_pitches,
    parse_annotation_label,
    pitch_class_from_name,
    pitch_to_pitch_class,
)
from app.chord_vocab_170 import (  # noqa: E402
    BASS_TO_IDX,
    BASS_VOCAB,
    BASS_X_IDX,
    MAP_277_TO_170_TABLE,
    N_IDX_170,
    NUM_CLASSES_170,
    X_IDX_170,
    compose_label,
)

DATA_ROOT = _BACKEND_DIR / "data"
DEFAULT_PSEUDO_OUT = DATA_ROOT / "chord170" / "pseudo_v2"
W1_ROOT = DATA_ROOT / "pseudo_label" / "w1"
SPLITS_PATH = DATA_ROOT / "chord170" / "splits.json"

_N_277_IDX = 276
_MAP_TABLE = np.asarray(MAP_277_TO_170_TABLE, dtype=np.int64)

def _decode(value) -> str:
    """Decode numpy bytes scalars (W1 npz files) to plain strings.

    ``np.savez`` wraps ``np.bytes_`` scalars in 0-d arrays, so both the
    array and the bytes cases are handled here.
    """
    if isinstance(value, np.ndarray):
        value = value.item() if value.shape == () else value.flat[0]
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8", "replace")
    return str(value)


# All datasets the builder knows about, with their CQT cache roots.
REAL_DATASETS: dict[str, Path] = {
    "guitarset": DATA_ROOT / "guitarset",
    "egset12": DATA_ROOT / "egset12",
    "guitar_techs": DATA_ROOT / "guitar_techs",
    "idmt_smt_guitar": DATA_ROOT / "idmt_smt_guitar",
    "rwc": DATA_ROOT / "rwc",
}


# ---------------------------------------------------------------------------
# Loaders (176-class labels + sidecar bass)
# ---------------------------------------------------------------------------


def load_split_overrides(path: Path = SPLITS_PATH) -> dict | None:
    """Load the external split map (source → {track_id: split}), if present."""
    if not Path(path).exists():
        return None
    try:
        payload = json.loads(Path(path).read_text())
        return payload.get("splits", {})
    except Exception as exc:
        print(f"  [WARN] could not read {path}: {exc}")
        return None


def resolve_split(
    source: str | None,
    track_id: str,
    default: str,
    overrides: dict | None,
) -> str:
    """Resolve a track's split, honouring the external split overrides."""
    if not overrides or not source:
        return default
    return overrides.get(source, {}).get(track_id, default)


def list_track_files(
    data_dir: Path,
    split: str | None = None,
    *,
    source: str | None = None,
    overrides: dict | None = None,
) -> list[Path]:
    """Return sorted .npz files under ``<data_dir>/processed/cqt``.

    When ``source`` and split overrides are available they take precedence
    over the npz's own split key (external gate splits). Tracks resolved to
    ``exclude`` are skipped.
    """
    cqt_dir = Path(data_dir) / "processed" / "cqt"
    files: list[Path] = []
    for npz_path in sorted(cqt_dir.glob("*.npz")):
        try:
            data = np.load(npz_path)
            track_id = _decode(data["track_id"]) if "track_id" in data.files else npz_path.stem
            track_split = _decode(data["split"]) if "split" in data.files else "train"
        except Exception as exc:
            print(f"  [WARN] skipping {npz_path.name}: {exc}")
            continue
        resolved = resolve_split(source, track_id, track_split, overrides)
        if resolved == "exclude":
            continue
        if split is not None and resolved != split:
            continue
        files.append(npz_path)
    return files


def _sidecar_path(npz_path: Path) -> Path:
    """Derived label/bass sidecar for a CQT window file."""
    return npz_path.parent.parent / "chord170" / npz_path.name


def _window_centers(data: "np.lib.npyio.NpzFile", n_windows: int) -> np.ndarray:
    """Window centre times: stored when present, else the k*6.4 s grid."""
    if "frame_times" in data.files:
        return np.asarray(data["frame_times"], dtype=np.float64)
    from app.cqt_constants import HOP_FRAMES, HOP_SEC

    return np.arange(n_windows, dtype=np.float64) * HOP_FRAMES * HOP_SEC


def _crop_window(features: np.ndarray, window: int) -> np.ndarray:
    """Centre-crop features to a shorter context window (default 128)."""
    if window is None or window >= features.shape[1]:
        return features
    offset = (features.shape[1] - int(window)) // 2
    return features[:, offset:offset + int(window), :]


def _normalize_track(features: np.ndarray, mode: str) -> np.ndarray:
    """Per-track per-bin standardisation (removes recording/timbre bias)."""
    if mode != "track":
        return features
    frames = features.reshape(-1, features.shape[-1])
    mean = frames.mean(axis=0, keepdims=True)
    std = frames.std(axis=0, keepdims=True) + 1e-6
    return ((features - mean[None, :, :]) / std[None, :, :]).astype(np.float32)


def load_track(npz_path: Path, *, source: str | None = None,
               overrides: dict | None = None,
               normalize: str = "none",
               crop_window: int = 128) -> dict | None:
    """Load one .npz window file into 170-class arrays (+ sidecar bass)."""
    try:
        data = np.load(npz_path)
        if "labels170" in data.files:
            # v2 pseudo-label schema: 170 labels + bass in the same file.
            labels170 = data["labels170"].astype(np.int64)
            n_windows = labels170.shape[0]
            bass = (data["bass_labels"].astype(np.int64)
                    if "bass_labels" in data.files
                    else np.full(n_windows, BASS_X_IDX, dtype=np.int64))
            confidence = (data["confidence"].astype(np.float32)
                          if "confidence" in data.files
                          else np.ones(n_windows, dtype=np.float32))
            split = _decode(data["split"]) if "split" in data.files else "train"
            track_id = _decode(data["track_id"]) if "track_id" in data.files else npz_path.stem
            split = resolve_split(source, track_id, split, overrides)
            return {
                "features": _crop_window(
                    _normalize_track(data["features"].astype(np.float32), normalize),
                    crop_window),
                "labels170": labels170,
                "labels277": None,  # v2 pseudo-label files have no 277 labels
                "bass_labels": bass,
                "confidence": confidence,
                "track_id": track_id,
                "split": split,
                "loss_weight": float(data["loss_weight"]) if "loss_weight" in data.files else 1.0,
                "center_times": _window_centers(data, n_windows),
            }
        labels277 = data["labels"].astype(np.int64)
        labels170 = _MAP_TABLE[labels277]
        n_windows = labels277.shape[0]
        sid = _sidecar_path(npz_path)
        extra: dict = {}
        if "bass_labels" in data.files:
            bass = data["bass_labels"].astype(np.int64)
        else:
            bass = np.full(labels170.shape, BASS_X_IDX, dtype=np.int64)
        if sid.exists():
            sc = np.load(sid)
            if sc["labels170"].shape == labels170.shape:
                labels170 = sc["labels170"].astype(np.int64)
            bass = sc["bass_labels"].astype(np.int64)
            if bass.shape != labels170.shape:
                print(f"  [WARN] {npz_path.name}: sidecar bass shape mismatch — unknown bass")
                bass = np.full(labels170.shape, BASS_X_IDX, dtype=np.int64)
            if "confidence" in sc.files:
                extra["confidence"] = sc["confidence"].astype(np.float32)
        split = _decode(data["split"]) if "split" in data.files else "train"
        track_id = _decode(data["track_id"]) if "track_id" in data.files else npz_path.stem
        split = resolve_split(source, track_id, split, overrides)
        return {
            "features": _crop_window(
                _normalize_track(data["features"].astype(np.float32), normalize),
                crop_window),
            "labels170": labels170,
            "labels277": labels277,
            "bass_labels": bass,
            "confidence": extra.get("confidence", np.ones(n_windows, dtype=np.float32)),
            "track_id": _decode(data["track_id"]),
            "split": split,
            "loss_weight": float(data["loss_weight"]) if "loss_weight" in data.files else 1.0,
            "center_times": _window_centers(data, n_windows),
        }
    except Exception as exc:
        print(f"  [WARN] skipping {npz_path.name}: {exc}")
        return None


def load_dataset_dir_170(
    data_dir: Path,
    split: str | None = None,
    *,
    limit_tracks: int = 0,
    source: str | None = None,
    normalize: str = "none",
    crop_window: int = 128,
) -> dict:
    """Load a dataset's windows as concatenated 170-class arrays."""
    features: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    labels277: list[np.ndarray | None] = []
    bass: list[np.ndarray] = []
    conf: list[np.ndarray] = []
    centers: list[np.ndarray] = []
    track_ids: list[str] = []
    weights: list[float] = []
    n_tracks = 0
    overrides = load_split_overrides()
    for npz_path in list_track_files(data_dir, split, source=source, overrides=overrides):
        track = load_track(npz_path, source=source, overrides=overrides,
                           normalize=normalize, crop_window=crop_window)
        if track is None:
            continue
        features.append(track["features"])
        labels.append(track["labels170"])
        labels277.append(track.get("labels277"))
        bass.append(track["bass_labels"])
        conf.append(track["confidence"])
        centers.append(track["center_times"])
        track_ids.extend([track["track_id"]] * track["features"].shape[0])
        weights.append(track["loss_weight"])
        n_tracks += 1
        if limit_tracks and n_tracks >= limit_tracks:
            break
    if not features:
        return {
            "features": np.zeros((0, 128, 144), dtype=np.float32),
            "labels170": np.zeros((0,), dtype=np.int64),
            "labels277": None,
            "bass_labels": np.zeros((0,), dtype=np.int64),
            "confidence": np.zeros((0,), dtype=np.float32),
            "center_times": np.zeros((0,), dtype=np.float64),
            "track_ids": [],
            "loss_weights": [],
        }
    if any(x is None for x in labels277):
        concatenated277 = None
    else:
        concatenated277 = np.concatenate(labels277, axis=0)
    return {
        "features": np.concatenate(features, axis=0),
        "labels170": np.concatenate(labels, axis=0),
        "labels277": concatenated277,
        "bass_labels": np.concatenate(bass, axis=0),
        "confidence": np.concatenate(conf, axis=0),
        "center_times": np.concatenate(centers, axis=0),
        "track_ids": track_ids,
        "loss_weights": weights,
    }


def summarize_dataset(data_dir: Path, split: str | None = None,
                      *, source: str | None = None) -> dict:
    """Dataset-card summary for one dataset directory."""
    data = load_dataset_dir_170(data_dir, split, source=source)
    labels = data["labels170"]
    bass = data["bass_labels"]
    n = len(labels)
    summary: dict = {
        "data_dir": str(data_dir),
        "split": split,
        "n_tracks": len(set(data["track_ids"])),
        "n_windows": int(n),
    }
    if n == 0:
        summary.update({"n_rate": 0.0, "x_rate": 0.0, "unique_classes": 0,
                        "bass_unknown_rate": 0.0, "slash_rate": 0.0})
        return summary
    chord_idx = labels < N_IDX_170
    known_bass = bass != BASS_X_IDX
    root_pc = np.array([int(i) % 12 for i in range(NUM_CLASSES_170)])
    slash = chord_idx & known_bass & (bass % 12 != root_pc[np.clip(labels, 0, NUM_CLASSES_170 - 1)])
    from app.chord_vocab_170 import QUALITIES_14

    quality_support: dict[str, int] = {}
    for quality_index, quality in enumerate(QUALITIES_14):
        low = quality_index * 12
        quality_support[quality] = int(np.sum((labels >= low) & (labels < low + 12)))
    quality_support["N"] = int(np.sum(labels == N_IDX_170))
    summary.update({
        "n_rate": float(np.mean(labels == N_IDX_170)),
        "x_rate": float(np.mean(labels == X_IDX_170)),
        "unique_classes": int(len(np.unique(labels))),
        "bass_unknown_rate": float(np.mean(bass == BASS_X_IDX)),
        "slash_rate": float(np.mean(slash)),
        "known_bass_frames": int(np.sum(known_bass)),
        "inversion_frames": int(np.sum(slash)),
        "quality_support": {k: v for k, v in quality_support.items() if v},
    })
    return summary


# ---------------------------------------------------------------------------
# Annotation readers (bass sources)
# ---------------------------------------------------------------------------


def _read_jams_notes(jams_path: Path) -> list[tuple[float, float, float]]:
    """Extract ``(start, end, midi)`` notes from a JAMS note_midi annotation."""
    try:
        payload = json.loads(Path(jams_path).read_text())
    except Exception as exc:
        print(f"  [WARN] could not read {Path(jams_path).name}: {exc}")
        return []
    notes: list[tuple[float, float, float]] = []
    for ann in payload.get("annotations", []):
        if ann.get("namespace") != "note_midi":
            continue
        data = ann.get("data")
        if not isinstance(data, list):
            continue
        for item in data:
            try:
                start = float(item["time"])
                duration = float(item.get("duration", 0.0))
                pitch = float(item["value"])
            except (KeyError, TypeError, ValueError):
                continue
            notes.append((start, start + max(duration, 0.0), pitch))
    return notes


def guitarset_notes(annotation_dir: Path) -> dict[str, list[tuple[float, float, float]]]:
    """Track id (without ``_mix``) → note list from GuitarSet JAMS."""
    out: dict[str, list[tuple[float, float, float]]] = {}
    for jams in sorted(Path(annotation_dir).glob("*.jams")):
        out[jams.stem] = _read_jams_notes(jams)
    return out


def egset12_notes(raw_dir: Path) -> dict[str, list[tuple[float, float, float]]]:
    """Track id (JAMS stem) → note list from EGSet12 JAMS."""
    out: dict[str, list[tuple[float, float, float]]] = {}
    for jams in sorted(Path(raw_dir).glob("*.jams")):
        out[jams.stem] = _read_jams_notes(jams)
    return out


def guitar_techs_notes(raw_dir: Path) -> dict[str, list[tuple[float, float, float]]]:
    """Track id (``<player>_<set>_<name>``) → merged note list from MIDI."""
    out: dict[str, list[tuple[float, float, float]]] = {}
    try:
        import pretty_midi
    except ImportError:
        print("  [WARN] pretty_midi unavailable — Guitar-TECHS bass stays unknown")
        return out
    for midi_path in sorted(Path(raw_dir).glob("*/midi/*.mid")):
        set_dir = midi_path.parent.parent.name  # e.g. P1_chords
        name = midi_path.stem
        if name.startswith("midi_"):
            name = name[len("midi_"):]
        track_id = f"{set_dir}_{name}"
        try:
            midi = pretty_midi.PrettyMIDI(str(midi_path))
        except Exception as exc:
            print(f"  [WARN] could not parse {midi_path.name}: {exc}")
            continue
        out[track_id] = [
            (float(note.start), float(note.end), float(note.pitch))
            for instrument in midi.instruments
            for note in instrument.notes
        ]
    return out


def idmt_chord_labels(dataset_root: Path) -> dict[str, list[tuple[float, float, str]]]:
    """Track id (``<style>_<audio_stem>``) → ``(start, end, label)`` from CSVs.

    IDMT dataset4 chord CSVs are ``time,beat[:chord]`` lines; lines carrying
    only a beat index have no chord and are skipped. Labels look like ``G``,
    ``D7/C``, ``D7/Gb`` (slash bass is a pitch class).
    """
    out: dict[str, list[tuple[float, float, str]]] = {}
    csv_files = sorted(Path(dataset_root).rglob("annotation/chords/*.csv"))
    for csv_path in csv_files:
        style = csv_path.parent.parent.parent.name
        track_id = f"{style}_{csv_path.stem}"
        entries: list[tuple[float, str]] = []
        try:
            for line in csv_path.read_text().splitlines():
                parts = line.strip().split(",")
                if len(parts) < 2 or ":" not in parts[1]:
                    continue
                try:
                    start = float(parts[0])
                except ValueError:
                    continue
                chord = parts[1].split(":", 1)[1].strip()
                if chord:
                    entries.append((start, chord))
        except OSError as exc:
            print(f"  [WARN] could not read {csv_path.name}: {exc}")
            continue
        entries.sort(key=lambda item: item[0])
        intervals: list[tuple[float, float, str]] = []
        for index, (start, chord) in enumerate(entries):
            end = entries[index + 1][0] if index + 1 < len(entries) else start + 2.0
            intervals.append((start, end, chord))
        out[track_id] = intervals
    return out


def rwc_chord_labels(chords_root: Path) -> dict[str, list[tuple[float, float, str]]]:
    """Track id (audio stem) → ``(start, end, label)`` from RWC-P CSVs."""
    out: dict[str, list[tuple[float, float, str]]] = {}
    for csv_path in sorted(Path(chords_root).glob("*.csv")):
        intervals: list[tuple[float, float, str]] = []
        try:
            for line in csv_path.read_text().splitlines():
                parts = line.strip().split(";")
                if len(parts) != 3:
                    continue
                try:
                    start, end = float(parts[0]), float(parts[1])
                except ValueError:
                    continue
                if parts[2].strip():
                    intervals.append((start, end, parts[2].strip()))
        except OSError as exc:
            print(f"  [WARN] could not read {csv_path.name}: {exc}")
            continue
        out[csv_path.stem] = intervals
    return out


def _label_at(intervals: list[tuple[float, float, str]], time_s: float) -> str | None:
    for start, end, label in intervals:
        if start <= time_s < end:
            return label
    return None


def _bass_from_label_at(
    intervals: list[tuple[float, float, str]], time_s: float
) -> int | None:
    label = _label_at(intervals, time_s)
    if label is None:
        return None
    parsed = parse_annotation_label(label)
    if parsed is None:
        return None
    root, _quality, bass = parsed
    if bass is not None:
        return bass
    # No slash in the annotation → the annotation states root position.
    return pitch_class_from_name(root)


# ---------------------------------------------------------------------------
# Real-dataset sidecar builder
# ---------------------------------------------------------------------------


def _track_annotation_lookup(
    dataset: str, data_dir: Path
) -> tuple[str, dict]:
    """Return (mode, lookup) where mode is 'notes' or 'labels'."""
    if dataset == "guitarset":
        return "notes", guitarset_notes(data_dir / "raw" / "annotation")
    if dataset == "egset12":
        return "notes", egset12_notes(data_dir / "raw")
    if dataset == "guitar_techs":
        return "notes", guitar_techs_notes(data_dir / "raw")
    if dataset == "idmt_smt_guitar":
        return "labels", idmt_chord_labels(data_dir / "raw" / "audio" / "dataset4")
    if dataset == "rwc":
        return "labels", rwc_chord_labels(data_dir / "raw" / "chords" / "RWC-P")
    raise ValueError(f"unsupported dataset: {dataset}")


def _track_key(dataset: str, track_id: str) -> str:
    if dataset == "guitarset" and track_id.endswith("_mix"):
        return track_id[: -len("_mix")]
    return track_id


def build_real_sidecars(
    dataset: str,
    data_dir: Path,
    *,
    limit_tracks: int = 0,
    min_pitches: int = 0,
) -> dict:
    """Derive 170 labels + bass labels for one real dataset.

    Writes ``<data_dir>/processed/chord170/<track>.npz`` sidecars.
    ``min_pitches`` (pseudo-labels use 3) is 0 for real datasets — every
    annotated window is kept.
    """
    mode, lookup = _track_annotation_lookup(dataset, data_dir)
    cqt_files = list_track_files(data_dir)
    if not cqt_files:
        return {"dataset": dataset, "status": "no_cqt_cache",
                "hint": "run the dataset's extract_*_cqt.py first (or Modal prepare)"}
    out_dir = data_dir / "processed" / "chord170"
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = Counter()
    unmatched: list[str] = []
    bass_counts = Counter()
    for npz_path in cqt_files:
        data = np.load(npz_path)
        track_id = _decode(data["track_id"])
        key = _track_key(dataset, track_id)
        n_windows = int(data["labels"].shape[0])
        centers = _window_centers(data, n_windows)
        labels277 = data["labels"].astype(np.int64)
        labels170 = _MAP_TABLE[labels277]
        bass = np.full(n_windows, BASS_X_IDX, dtype=np.int64)
        source = lookup.get(key)
        if source is None:
            unmatched.append(track_id)
        else:
            for index, center in enumerate(centers):
                if labels170[index] in (N_IDX_170, X_IDX_170):
                    continue
                if mode == "notes":
                    if min_pitches and count_active_pitches(source, float(center)) < min_pitches:
                        continue
                    pc = bass_pitch_class_from_notes(source, float(center))
                else:
                    pc = _bass_from_label_at(source, float(center))
                if pc is not None:
                    bass[index] = BASS_TO_IDX[BASS_VOCAB[pc % 12]]
        np.savez_compressed(
            out_dir / npz_path.name,
            labels170=labels170.astype(np.int64),
            bass_labels=bass.astype(np.int64),
            confidence=np.ones(n_windows, dtype=np.float32),
        )
        stats["tracks"] += 1
        stats["windows"] += n_windows
        bass_counts["known"] += int(np.sum(bass != BASS_X_IDX))
        bass_counts["unknown"] += int(np.sum(bass == BASS_X_IDX))
        if limit_tracks and stats["tracks"] >= limit_tracks:
            break
    return {
        "dataset": dataset,
        "mode": mode,
        "tracks": stats["tracks"],
        "windows": stats["windows"],
        "bass_known_rate": (
            bass_counts["known"] / max(bass_counts["known"] + bass_counts["unknown"], 1)
        ),
        "unmatched_tracks": len(unmatched),
        "unmatched_sample": unmatched[:5],
        "sidecar_dir": str(out_dir),
    }


# ---------------------------------------------------------------------------
# Pseudo-label v2 builder
# ---------------------------------------------------------------------------


def _load_w1_track_labels(labels_dir: Path, track_id: str) -> dict | None:
    path = labels_dir / f"{track_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        print(f"  [WARN] could not read {path.name}: {exc}")
        return None


def _w1_kept_centers(
    payload: dict,
    npz_window_count: int,
    min_confidence: float = 0.5,
) -> np.ndarray | None:
    """Recover the centre times of W1's kept windows.

    W1 stored only kept windows and did not store their centre times. The
    keep mask is deterministic (centre k = k*6.4 s, keep when the covering
    interval confidence ≥ 0.5), except for the final chord interval whose
    original end was the audio duration while the JSON stores
    ``timestamp + 1.0``. The final interval is therefore extended to cover
    the tail and the first ``npz_window_count`` kept centres are taken
    (window order is preserved). Returns None when the recovered count
    cannot match the stored windows.
    """
    from app.cqt_constants import HOP_FRAMES, HOP_SEC
    from app.data_engine.confidence import ChordInterval, PseudoLabelConfig, label_windows

    chords = payload.get("chords", [])
    if not chords:
        return None
    intervals = [
        ChordInterval(
            start=float(item["start"]),
            end=float(item["end"]),
            chord=str(item["chord"]),
            confidence=float(item.get("confidence", 0.0)),
        )
        for item in chords
    ]
    # Extend the final interval past the track end so tail windows are
    # covered regardless of the original audio duration.
    last = intervals[-1]
    intervals[-1] = ChordInterval(
        start=last.start,
        end=float("inf"),
        chord=last.chord,
        confidence=last.confidence,
    )
    n_total = int(payload.get("windows_total") or npz_window_count)
    centers = np.arange(n_total, dtype=np.float64) * HOP_FRAMES * HOP_SEC
    config = PseudoLabelConfig(min_chord_confidence=min_confidence)
    _labels, _conf, keep = label_windows(intervals, centers, config)
    kept = centers[np.asarray(keep, dtype=bool)]
    if len(kept) < npz_window_count:
        return None
    return kept[:npz_window_count]


def _cap_n_windows(
    labels: np.ndarray,
    confidence: np.ndarray,
    n_cap: float,
) -> np.ndarray:
    """Return a keep mask capping N windows to ``n_cap`` of the set."""
    n_total = len(labels)
    n_count = int(np.sum(labels == N_IDX_170))
    if n_count == 0 or n_total == 0:
        return np.ones(n_total, dtype=bool)
    non_n = n_total - n_count
    allowed_n = int(np.floor(n_cap * non_n / max(1.0 - n_cap, 1e-6)))
    if n_count <= allowed_n:
        return np.ones(n_total, dtype=bool)
    # Keep the highest-confidence N windows (stable tie-break by index).
    n_indices = np.flatnonzero(labels == N_IDX_170)
    order = np.argsort(-confidence[n_indices], kind="stable")
    keep = np.ones(n_total, dtype=bool)
    drop = n_indices[order[allowed_n:]]
    keep[drop] = False
    return keep


def build_pseudo_labels_v2(
    w1_root: Path = W1_ROOT,
    out_dir: Path = DEFAULT_PSEUDO_OUT,
    *,
    min_pitches: int = 3,
    min_confidence: float = 0.6,
    n_cap: float = 0.20,
    limit_tracks: int = 0,
) -> dict:
    """Rebuild W1 pseudo-labels with v2 filters, bass, and N capping."""
    labels_dir = w1_root / "labels"
    cqt_dir = w1_root / "processed" / "cqt"
    if not labels_dir.is_dir() or not cqt_dir.is_dir():
        return {"status": "missing_w1_artifacts", "labels_dir": str(labels_dir)}

    out_cqt = out_dir / "processed" / "cqt"
    out_cqt.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "w1_root": str(w1_root),
        "out_dir": str(out_dir),
        "filters": {
            "min_pitches": min_pitches,
            "min_confidence": min_confidence,
            "n_cap": n_cap,
            "old_confidence": 0.5,
        },
        "per_source": defaultdict(lambda: {
            "windows_in": 0, "windows_out": 0, "n_in": 0, "n_out": 0,
            "bass_known": 0, "unique_classes": set(),
        }),
        "tracks": 0,
        "skipped_alignment": [],
        "skipped_filters": 0,
        "windows_in": 0,
        "windows_after_filters": 0,
    }

    pending: list[dict] = []
    for npz_path in sorted(cqt_dir.glob("*.npz")):
        data = np.load(npz_path)
        track_id = _decode(data["track_id"])
        payload = _load_w1_track_labels(labels_dir, npz_path.stem)
        if payload is None:
            report["skipped_filters"] += 1
            continue
        kept_centers = _w1_kept_centers(payload, data["labels"].shape[0])
        if kept_centers is None:
            report["skipped_alignment"].append(track_id)
            continue

        notes = [
            (float(n["start_time"]), float(n["start_time"]) + float(n.get("duration", 0.0)),
             float(n["pitch"]))
            for n in payload.get("notes", [])
        ]
        labels277 = data["labels"].astype(np.int64)
        confidences = np.asarray(
            data["confidence"] if "confidence" in data.files
            else np.ones_like(labels277, dtype=np.float32),
            dtype=np.float32,
        )
        labels170 = _MAP_TABLE[labels277]
        bass = np.full(labels277.shape, BASS_X_IDX, dtype=np.int64)
        pitch_counts = np.zeros(labels277.shape, dtype=np.int64)
        for index, center in enumerate(kept_centers):
            if labels170[index] in (N_IDX_170, X_IDX_170):
                continue
            pitch_counts[index] = count_active_pitches(notes, float(center))
            pc = bass_pitch_class_from_notes(notes, float(center))
            if pc is not None and pitch_counts[index] >= min_pitches:
                bass[index] = BASS_TO_IDX[BASS_VOCAB[pc % 12]]

        keep = (confidences >= min_confidence)
        chord_mask = (labels170 != N_IDX_170) & (labels170 != X_IDX_170)
        keep &= ~chord_mask | (pitch_counts >= min_pitches)
        if not keep.any():
            report["skipped_filters"] += 1
            continue

        split = _decode(payload.get("split", "train"))
        source = _decode(payload.get("source", "pseudo"))
        pending.append({
            "track_id": track_id,
            "safe_id": npz_path.stem,
            "features": data["features"][keep],
            "labels170": labels170[keep],
            "bass_labels": bass[keep],
            "confidence": confidences[keep],
            "center_times": kept_centers[keep].astype(np.float32),
            "split": "train" if split == "train" else "test",
            "source": source,
            "teacher": _decode(payload.get("teacher", "mt3")),
            "loss_weight": float(data["loss_weight"]) if "loss_weight" in data.files else 0.5,
        })
        report["windows_in"] += int(data["labels"].shape[0])
        if limit_tracks and len(pending) >= limit_tracks:
            break

    if not pending:
        return {**report, "status": "no_tracks", "per_source": {}}

    safe_ids = [item["safe_id"] for item in pending]
    if len(set(safe_ids)) != len(safe_ids):
        dupes = sorted({sid for sid in safe_ids if safe_ids.count(sid) > 1})
        raise ValueError(f"duplicate safe track ids would overwrite each other: {dupes[:5]}")

    all_labels = np.concatenate([item["labels170"] for item in pending])
    all_conf = np.concatenate([item["confidence"] for item in pending])
    global_keep = _cap_n_windows(all_labels, all_conf, n_cap)

    offset = 0
    report["tracks"] = len(pending)
    report["windows_after_filters"] = int(np.sum(global_keep))
    for item in pending:
        size = len(item["labels170"])
        track_keep = global_keep[offset: offset + size]
        offset += size
        if not track_keep.any():
            continue
        np.savez_compressed(
            out_cqt / f"{item['safe_id']}.npz",
            features=item["features"][track_keep].astype(np.float32),
            labels170=item["labels170"][track_keep].astype(np.int64),
            bass_labels=item["bass_labels"][track_keep].astype(np.int64),
            confidence=item["confidence"][track_keep].astype(np.float32),
            center_times=item["center_times"][track_keep].astype(np.float32),
            track_id=np.bytes_(item["track_id"].encode("utf-8")),
            split=np.bytes_(item["split"]),
            source=np.bytes_(item["source"]),
            teacher=np.bytes_(item["teacher"]),
            loss_weight=np.float64(item["loss_weight"]),
            schema_version=np.int64(2),
        )
        stats = report["per_source"][item["source"]]
        keep_labels = item["labels170"][track_keep]
        stats["windows_in"] += size
        stats["windows_out"] += int(track_keep.sum())
        stats["n_in"] += int(np.sum(item["labels170"] == N_IDX_170))
        stats["n_out"] += int(np.sum(keep_labels == N_IDX_170))
        stats["bass_known"] += int(np.sum(item["bass_labels"][track_keep] != BASS_X_IDX))
        stats["unique_classes"].update(keep_labels.tolist())

    report["per_source"] = {
        source: {
            **{k: v for k, v in stats.items() if k != "unique_classes"},
            "unique_classes": len(stats["unique_classes"]),
        }
        for source, stats in report["per_source"].items()
    }
    report["status"] = "ok"
    return report


def sampling_probabilities(
    labels: np.ndarray,
    sources: np.ndarray,
    *,
    temperature: float = 0.3,
    n_classes: int = NUM_CLASSES_170,
    n_index: int = N_IDX_170,
) -> np.ndarray:
    """Per-window sampling probability: class temperature × source balance.

    Rare classes are up-weighted by ``(1/count)^temperature``; N is clamped
    so it is never up-weighted above the chord-class median; each source is
    re-weighted toward an equal share (clipped to [0.5, 4]).
    """
    n = len(labels)
    counts = np.bincount(labels, minlength=n_classes).astype(np.float64)
    safe_counts = np.maximum(counts, 1.0)
    class_weight = (1.0 / safe_counts) ** temperature
    chord_mask = np.array([
        i not in (n_index, n_classes - 1) for i in range(n_classes)
    ])
    if chord_mask.any():
        class_weight[n_index] = min(
            class_weight[n_index], float(np.median(class_weight[chord_mask]))
        )

    source_weight: dict[str, float] = {}
    unique_sources, source_counts = np.unique(sources, return_counts=True)
    target_share = 1.0 / len(unique_sources)
    for source, count in zip(unique_sources, source_counts):
        share = count / n
        source_weight[str(source)] = float(np.clip(target_share / max(share, 1e-6), 0.5, 4.0))

    prob = np.array([
        class_weight[label] * source_weight[str(source)]
        for label, source in zip(labels, sources)
    ], dtype=np.float64)
    prob /= prob.sum()

    # Never amplify N beyond 1.5x its natural share (spec: "do not
    # over-weight N"). Downscale N and renormalise the chord mass.
    n_mask = labels == n_index
    natural = float(n_mask.mean()) if n_mask.any() else 0.0
    if natural and prob[n_mask].sum() > max(1.5 * natural, natural + 0.05):
        cap = max(1.5 * natural, natural + 0.05)
        prob[n_mask] *= cap / prob[n_mask].sum()
        prob /= prob.sum()
    return prob



# ---------------------------------------------------------------------------
# Training sample weights (Stage B)
# ---------------------------------------------------------------------------

LABEL_SPACES: dict[str, int] = {"170": NUM_CLASSES_170, "277": 277, "mirex25": 25}
N_INDEX_BY_SPACE: dict[str, int] = {"170": N_IDX_170, "277": 276, "mirex25": 24}


def bass_sample_weights(
    bass: np.ndarray,
    chord: np.ndarray,
    *,
    inversion_weight: float = 2.0,
    mask_unknown: bool = True,
    label_space: str = "170",
) -> np.ndarray:
    """Per-window bass loss weights: 0 unknown, 1 root position, >1 inversions."""
    weights = np.ones(len(bass), dtype=np.float32)
    unknown = bass == BASS_X_IDX
    weights[unknown] = 0.0 if mask_unknown else 1.0
    n_index = N_INDEX_BY_SPACE[label_space]
    last = LABEL_SPACES[label_space] - 1
    roots = np.array([
        int(c) % 12 if int(c) not in (n_index, last) else -1 for c in chord
    ])
    inversions = (~unknown) & (roots >= 0) & (bass != roots)
    weights[inversions] = float(inversion_weight)
    return weights


def inversion_training_labels(
    chord: np.ndarray, bass: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return (inversion class labels, sample weights) for the aux head.

    Unknown bass is masked (weight 0) so the head learns from real inversions.
    """
    from app.chord_labels import inversion_class

    labels = np.array([inversion_class(int(c), int(b)) for c, b in zip(chord, bass)],
                      dtype=np.int64)
    weights = (bass != BASS_X_IDX).astype(np.float32)
    return labels, weights


def chord_inversion_weights(
    chord: np.ndarray, bass: np.ndarray, weight: float = 2.0
) -> np.ndarray:
    """Multiplicative chord-loss weights for inversion frames (slash focus)."""
    weights = np.ones(len(chord), dtype=np.float32)
    if weight <= 1.0:
        return weights
    from app.chord_labels import inversion_class

    inversion = np.array([
        inversion_class(int(c), int(b)) for c, b in zip(chord, bass)
    ], dtype=np.int64)
    weights[(inversion > 0) & (inversion < 4)] = float(weight)
    return weights


def chord_class_weights(
    labels: np.ndarray,
    *,
    tau: float = 0.0,
    n_classes: int = NUM_CLASSES_170,
) -> np.ndarray:
    """Class-balanced per-window weights ``(1/count)^tau`` (mean-normalised)."""
    if tau <= 0:
        return np.ones(len(labels), dtype=np.float32)
    counts = np.bincount(labels, minlength=n_classes).astype(np.float64)
    safe = np.maximum(counts, 1.0)
    weight_by_class = (1.0 / safe) ** tau
    sample_weights = weight_by_class[labels]
    mean = float(sample_weights.mean()) if len(sample_weights) else 1.0
    sample_weights = sample_weights / max(mean, 1e-8)
    return sample_weights.astype(np.float32)


# ---------------------------------------------------------------------------
# Dataset card + split-overlap check
# ---------------------------------------------------------------------------


def check_track_split_overlap(sources: list[dict]) -> list[dict]:
    """Return track ids that appear under more than one split.

    ``sources`` entries: ``{"name": str, "data_dir": Path, "split": str}``.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for source in sources:
        data = load_dataset_dir_170(Path(source["data_dir"]), source.get("split"),
                                    source=source.get("name"))
        for track_id in set(data["track_ids"]):
            seen[track_id].add(str(source.get("split") or "all"))
    return [
        {"track_id": track_id, "splits": sorted(splits)}
        for track_id, splits in seen.items()
        if len(splits) > 1
    ]


def build_dataset_card(
    dataset_specs: list[dict],
    pseudo_dir: Path | None = None,
    out_path: Path | None = None,
) -> dict:
    """Write a dataset card (JSON) with per-source counts and split overlap.

    Each spec: ``{"name", "data_dir", "kind": "real"|"pseudo", "splits": [...]}``.
    """
    card: dict = {"sources": {}, "overlap": [], "totals": {}}
    per_split_windows: Counter = Counter()
    split_track_sets: dict[str, set[str]] = defaultdict(set)
    for spec in dataset_specs:
        entry: dict = {"kind": spec.get("kind", "real"), "splits": {}}
        for split in spec.get("splits", ["train", "val", "test"]):
            summary = summarize_dataset(Path(spec["data_dir"]), split,
                                        source=spec["name"])
            entry["splits"][split] = summary
            per_split_windows[split] += summary["n_windows"]
            # Track sets for every split so train↔eval leakage is detectable.
            data = load_dataset_dir_170(Path(spec["data_dir"]), split,
                                        source=spec["name"])
            split_track_sets[split].update(data["track_ids"])
        card["sources"][spec["name"]] = entry

    for split, tracks in split_track_sets.items():
        for other_split, other_tracks in split_track_sets.items():
            if other_split <= split:
                continue
            shared = tracks & other_tracks
            if shared:
                card["overlap"].append({
                    "splits": [split, other_split],
                    "track_count": len(shared),
                    "sample": sorted(shared)[:5],
                })
    card["totals"] = {
        "windows_per_split": dict(per_split_windows),
        "tracks_per_split": {k: len(v) for k, v in split_track_sets.items()},
        "cross_split_overlap_count": len(card["overlap"]),
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(card, indent=2))
    return card


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    real = sub.add_parser("build-real", help="derive label+bass sidecars for real datasets")
    real.add_argument("--dataset", default="all",
                      choices=["all", *REAL_DATASETS.keys()])
    real.add_argument("--limit-tracks", type=int, default=0)

    pseudo = sub.add_parser("build-pseudo", help="rebuild filtered pseudo-labels")
    pseudo.add_argument("--w1-root", type=Path, default=W1_ROOT)
    pseudo.add_argument("--out", type=Path, default=DEFAULT_PSEUDO_OUT)
    pseudo.add_argument("--min-pitches", type=int, default=3)
    pseudo.add_argument("--min-confidence", type=float, default=0.6)
    pseudo.add_argument("--n-cap", type=float, default=0.20)
    pseudo.add_argument("--limit-tracks", type=int, default=0)
    pseudo.add_argument("--report", type=Path, default=None)

    card = sub.add_parser("card", help="write the dataset card")
    card.add_argument("--out", type=Path,
                      default=_BACKEND_DIR / ".." / "docs" / "audit" / "amt"
                      / "chord170_phase2_dataset.json")

    summary = sub.add_parser("summary", help="summarize one dataset directory")
    summary.add_argument("data_dir", type=Path)
    summary.add_argument("--split", default=None)

    args = parser.parse_args(argv)

    if args.command == "build-real":
        datasets = list(REAL_DATASETS) if args.dataset == "all" else [args.dataset]
        results = [
            build_real_sidecars(name, REAL_DATASETS[name], limit_tracks=args.limit_tracks)
            for name in datasets
        ]
        print(json.dumps(results, indent=2))
        return 0

    if args.command == "build-pseudo":
        result = build_pseudo_labels_v2(
            args.w1_root, args.out,
            min_pitches=args.min_pitches,
            min_confidence=args.min_confidence,
            n_cap=args.n_cap,
            limit_tracks=args.limit_tracks,
        )
        print(json.dumps(result, indent=2, default=str))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2, default=str))
        return 0

    if args.command == "card":
        specs = [
            {"name": "guitarset", "data_dir": REAL_DATASETS["guitarset"], "kind": "real"},
            {"name": "egset12", "data_dir": REAL_DATASETS["egset12"], "kind": "real"},
            {"name": "guitar_techs", "data_dir": REAL_DATASETS["guitar_techs"], "kind": "real"},
            {"name": "idmt_smt_guitar", "data_dir": REAL_DATASETS["idmt_smt_guitar"], "kind": "real"},
            {"name": "rwc", "data_dir": REAL_DATASETS["rwc"], "kind": "real"},
            {"name": "pseudo_v2", "data_dir": DEFAULT_PSEUDO_OUT,
             "kind": "pseudo", "splits": ["train", "test"]},
            {"name": "pseudo_btc", "data_dir": DATA_ROOT / "chord170" / "pseudo_btc",
             "kind": "pseudo", "splits": ["train", "test"]},
            {"name": "slakh", "data_dir": DATA_ROOT / "chord170" / "slakh",
             "kind": "real", "splits": ["train", "val", "test"]},
        ]
        result = build_dataset_card(specs, out_path=args.out)
        print(json.dumps(result["totals"], indent=2))
        print(f"card written to {args.out}")
        return 0

    if args.command == "summary":
        print(json.dumps(summarize_dataset(args.data_dir, args.split), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
