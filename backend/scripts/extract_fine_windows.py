"""Fine-hop 1.6 s windows for the gate iteration (train + test).

The context iteration showed that short windows fix cross-song generalization.
This script re-extracts features at a finer temporal grid (default window 16,
hop 16 frames = 1.6 s) from the annotated corpora, with the same 144-bin CQT
and L1 normalisation, so training and evaluation both see boundary-accurate
windows.

Bass labels:
  * GuitarSet / EGSet12: lowest active note from the JAMS annotations.
  * IDMT / RWC: the annotation's slash bass (root position = root).

Split assignment comes from ``data/chord170/splits.json`` (track-level).

Usage (Modal entrypoint ``prepare_fine`` in modal_chord_170.py)::

    python scripts/extract_fine_windows.py --datasets guitarset,egset12,idmt_smt_guitar,rwc --workers 8
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import (  # noqa: E402
    bass_pitch_class_from_notes,
    parse_annotation_label,
)
from app.chord_vocab import CHORD_TO_IDX, NUM_CLASSES  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    BASS_TO_IDX,
    BASS_VOCAB,
    BASS_X_IDX,
    CHORD_TO_IDX_170,
    MAP_277_TO_170_TABLE,
    N_IDX_170,
    QUALITIES_14,
)
from scripts.chord_data_v2 import (  # noqa: E402
    DATA_ROOT,
    REAL_DATASETS,
    SPLITS_PATH,
    egset12_notes,
    guitarset_notes,
    rwc_chord_labels,
    idmt_chord_labels,
)

TARGET_SR = 44100
HOP_SEC = 0.1
NUM_BINS = 144
BINS_PER_OCTAVE = 24
_MAP_TABLE = np.asarray(MAP_277_TO_170_TABLE, dtype=np.int64)
OUT_ROOT = DATA_ROOT / "chord170" / "fine"

DEFAULT_WINDOW = 16
DEFAULT_HOP = 16


def _load_splits() -> dict:
    if SPLITS_PATH.exists():
        return json.loads(SPLITS_PATH.read_text()).get("splits", {})
    return {}


def _label_at(timeline: list[dict], time_s: float) -> int:
    for item in timeline:
        if float(item["start"]) <= time_s < float(item["end"]):
            label = str(item["chord"])
            return CHORD_TO_IDX.get(label, NUM_CLASSES - 1)
    return NUM_CLASSES - 1


def _bass_from_intervals(intervals: list[tuple[float, float, str]], time_s: float) -> int:
    for start, end, label in intervals:
        if start <= time_s < end:
            parsed = parse_annotation_label(label)
            if parsed is None:
                return BASS_X_IDX
            root, _quality, bass = parsed
            if bass is not None:
                return BASS_TO_IDX[BASS_VOCAB[bass % 12]]
            from app.chord_labels import pitch_class_from_name

            pc = pitch_class_from_name(root)
            return BASS_TO_IDX[BASS_VOCAB[pc % 12]] if pc is not None else BASS_X_IDX
    return BASS_X_IDX


def _cqt_windows(audio_path: Path, window: int, hop: int) -> tuple[np.ndarray, np.ndarray]:
    import librosa

    y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    if y.size == 0:
        return np.zeros((0, window, NUM_BINS), dtype=np.float32), np.zeros(0)
    hop_length = int(sr * HOP_SEC)
    cqt = np.abs(librosa.cqt(y=y, sr=sr, hop_length=hop_length, n_bins=NUM_BINS,
                             bins_per_octave=BINS_PER_OCTAVE)).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    feats = cqt / norms
    half = window // 2
    padded = np.concatenate([np.zeros((half, NUM_BINS), dtype=np.float32), feats,
                             np.zeros((half, NUM_BINS), dtype=np.float32)], axis=0)
    n_windows = max(1, int(np.ceil(len(feats) / hop)))
    windows = np.zeros((n_windows, window, NUM_BINS), dtype=np.float32)
    for k in range(n_windows):
        start = k * hop
        windows[k] = padded[start:start + window]
    centres = np.arange(n_windows, dtype=np.float64) * hop * HOP_SEC
    return windows, centres


def _resolve_audio(raw: str, dataset: str) -> Path | None:
    """Resolve an audio path, rebasing machine-local paths onto this host."""
    path = Path(raw)
    if path.exists():
        return path
    parts = path.parts
    if dataset in parts:
        index = parts.index(dataset)
        candidate = REAL_DATASETS[dataset] / Path(*parts[index + 1:])
        if candidate.exists():
            return candidate
    return None


def _dataset_tracks(dataset: str, splits: dict) -> list[dict]:
    tracks: list[dict] = []
    root = REAL_DATASETS[dataset]
    timelines = root / "processed" / "timelines"
    if dataset == "guitarset":
        notes = guitarset_notes(root / "raw" / "annotation")
        for path in sorted(timelines.glob("*_comp.json")) + sorted(timelines.glob("*_solo.json")):
            stem = path.stem
            audio = root / "raw" / "audio_mono-mix" / f"{stem}_mix.wav"
            if not audio.exists():
                continue
            split = splits.get("guitarset", {}).get(f"{stem}_mix", "train")
            tracks.append({"track_id": stem, "timeline": path, "audio": audio,
                           "notes": notes.get(stem), "split": split})
    elif dataset == "egset12":
        notes = egset12_notes(root / "raw")
        for path in sorted(timelines.glob("*.json")):
            stem = path.stem
            audio = root / "raw" / f"{stem}.wav"
            if not audio.exists():
                continue
            split = splits.get("egset12", {}).get(stem, "train")
            tracks.append({"track_id": stem, "timeline": path, "audio": audio,
                           "notes": notes.get(stem), "split": split})
    elif dataset == "idmt_smt_guitar":
        labels = idmt_chord_labels(root / "raw" / "audio" / "dataset4")
        for path in sorted(timelines.glob("*.json")):
            stem = path.stem
            payload = json.loads(path.read_text())
            audio = None
            for item in payload:
                if item.get("path"):
                    audio = _resolve_audio(item["path"], dataset)
                    break
            if audio is None or not audio.exists():
                continue
            split = splits.get("idmt_smt_guitar", {}).get(stem, "train")
            tracks.append({"track_id": stem, "timeline": path, "audio": audio,
                           "intervals": labels.get(stem), "split": split})
    elif dataset == "rwc":
        labels = rwc_chord_labels(root / "raw" / "chords" / "RWC-P")
        for path in sorted(timelines.glob("*.json")):
            stem = path.stem
            audio = root / "raw" / "audio" / "RWC-P" / f"{stem}.wav"
            if not audio.exists():
                continue
            split = splits.get("rwc", {}).get(stem, "train")
            tracks.append({"track_id": stem, "timeline": path, "audio": audio,
                           "intervals": labels.get(stem), "split": split})
    else:
        raise ValueError(f"unsupported dataset: {dataset}")
    return tracks


def _process_track(track: dict, out_dir: Path, dataset: str,
                   window: int, hop: int) -> dict:
    try:
        timeline = json.loads(Path(track["timeline"]).read_text())
        windows, centres = _cqt_windows(Path(track["audio"]), window, hop)
        if len(windows) == 0:
            return {"track": track["track_id"], "status": "empty"}
        labels = np.zeros(len(windows), dtype=np.int64)
        bass = np.full(len(windows), BASS_X_IDX, dtype=np.int64)
        for index, centre in enumerate(centres):
            label_277 = _label_at(timeline, float(centre))
            labels[index] = _MAP_TABLE[label_277] if label_277 < NUM_CLASSES - 1 else N_IDX_170
            if track.get("notes"):
                pc = bass_pitch_class_from_notes(track["notes"], float(centre))
                if pc is not None:
                    bass[index] = BASS_TO_IDX[BASS_VOCAB[pc % 12]]
            elif track.get("intervals"):
                bass[index] = _bass_from_intervals(track["intervals"], float(centre))
        out_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            out_dir / f"{track['track_id']}.npz",
            features=windows,
            labels170=labels,
            bass_labels=bass,
            confidence=np.ones(len(labels), dtype=np.float32),
            center_times=centres.astype(np.float32),
            track_id=np.bytes_(track["track_id"].encode()),
            split=np.bytes_(track["split"].encode()),
            source=np.bytes_(f"{dataset}_fine".encode()),
            teacher=np.bytes_(b"annotation"),
            loss_weight=np.float64(1.0),
            schema_version=np.int64(2),
        )
        return {"track": track["track_id"], "status": "ok", "split": track["split"],
                "windows": int(len(labels)), "n_windows": int(np.sum(labels == N_IDX_170)),
                "bass_known": int(np.sum(bass != BASS_X_IDX))}
    except Exception as exc:
        return {"track": track["track_id"], "status": f"error:{type(exc).__name__}: {exc}"}


def extract(datasets: list[str], workers: int = 8, limit: int = 0,
            window: int = DEFAULT_WINDOW, hop: int = DEFAULT_HOP) -> dict:
    splits = _load_splits()
    report: dict = {"window": window, "hop": hop, "datasets": {}}
    for dataset in datasets:
        tracks = _dataset_tracks(dataset, splits)
        if limit:
            tracks = tracks[:limit]
        out_dir = OUT_ROOT / dataset / "processed" / "cqt"
        results: list[dict] = []
        if workers <= 1:
            results = [_process_track(t, out_dir, dataset, window, hop) for t in tracks]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_process_track, t, out_dir, dataset, window, hop)
                           for t in tracks]
                for future in as_completed(futures):
                    results.append(future.result())
        ok = [r for r in results if r.get("status") == "ok"]
        qualities: dict[str, int] = {}
        for track in tracks:
            path = out_dir / f"{track['track_id']}.npz"
            if not path.exists():
                continue
            labels = np.load(path)["labels170"]
            for label in labels:
                if int(label) < N_IDX_170:
                    quality = QUALITIES_14[int(label) // 12]
                    qualities[quality] = qualities.get(quality, 0) + 1
        report["datasets"][dataset] = {
            "tracks": len(tracks),
            "tracks_ok": len(ok),
            "windows": int(sum(r.get("windows", 0) for r in ok)),
            "n_windows": int(sum(r.get("n_windows", 0) for r in ok)),
            "bass_known": int(sum(r.get("bass_known", 0) for r in ok)),
            "splits": {s: sum(1 for r in ok if r.get("split") == s)
                       for s in ("train", "val", "test")},
            "qualities": qualities,
            "errors": [r for r in results if r.get("status") != "ok"][:5],
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", default="guitarset,egset12,idmt_smt_guitar,rwc")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--hop", type=int, default=DEFAULT_HOP)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    report = extract([d.strip() for d in args.datasets.split(",") if d.strip()],
                     workers=args.workers, limit=args.limit,
                     window=args.window, hop=args.hop)
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
