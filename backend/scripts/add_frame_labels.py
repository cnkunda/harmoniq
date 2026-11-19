"""Add per-frame chord/bass labels to the fine 1.6 s window caches.

The fine window extractor stores one label per window (the annotation at the
window centre). Frame-level supervision needs the label of every CQT frame
inside the window. Window ``k`` starts at frame ``k*hop - window//2``, so
frame ``i`` is centred at ``(k*hop - window//2 + i) * 0.1 s``. This script
reads that geometry from the existing npz, re-queries the dataset timeline
(or the Slakh/IDMT MIDI notes) at each frame, and rewrites the npz with two
extra arrays:

  * ``frame_labels`` — ``(N, window)`` uint8 170-class labels.
  * ``frame_bass``   — ``(N, window)`` uint8 13-class bass labels.

No CQT is recomputed and no other array is modified.

Usage (from backend/)::

    python scripts/add_frame_labels.py --datasets guitarset,egset12,idmt_smt_guitar,rwc,guitar_techs,idmt_chords
    python scripts/add_frame_labels.py --datasets slakh --workers 16
"""

from __future__ import annotations

import argparse
import json
import os
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
    MAP_277_TO_170_TABLE,
    N_IDX_170,
)
from scripts.chord_data_v2 import DATA_ROOT  # noqa: E402
from scripts.extract_fine_windows import (  # noqa: E402
    HOP_SEC,
    OUT_ROOT,
    _chord_from_notes,
    _dataset_tracks,
    _load_splits,
)
from scripts.prepare_slakh import _note_events  # noqa: E402

_MAP_TABLE = np.asarray(MAP_277_TO_170_TABLE, dtype=np.int64)
SLAKH_FINE_DIR = DATA_ROOT / "chord170" / "slakh_fine"
SLAKH_RAW_DIR = DATA_ROOT / "chord170" / "slakh_raw"
REAL_DATASETS = ("guitarset", "egset12", "idmt_smt_guitar", "rwc",
                 "guitar_techs", "idmt_chords")
FRAME_VERSION = 1


def frame_times(centres: np.ndarray, window: int) -> np.ndarray:
    """Return ``(N, window)`` frame times for ordered window centres."""
    centres = np.asarray(centres, dtype=np.float64)
    offsets = (np.arange(window, dtype=np.float64) - window // 2) * HOP_SEC
    return centres[:, None] + offsets[None, :]


def _label_at(timeline: list[dict], time_s: float) -> int:
    for item in timeline:
        if float(item["start"]) <= time_s < float(item["end"]):
            return CHORD_TO_IDX.get(str(item["chord"]), NUM_CLASSES - 1)
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


def _frame_labels_for_meta(meta: dict, centres: np.ndarray, window: int
                           ) -> tuple[np.ndarray, np.ndarray]:
    times = frame_times(centres, window)
    labels = np.full(times.shape, N_IDX_170, dtype=np.uint8)
    bass = np.full(times.shape, BASS_X_IDX, dtype=np.uint8)
    timeline = (json.loads(Path(meta["timeline"]).read_text())
                if meta.get("timeline") else None)
    notes = meta.get("notes")
    intervals = meta.get("intervals")
    from_notes = bool(meta.get("labels_from_notes"))
    for index in range(times.shape[0]):
        for frame in range(window):
            time_s = float(times[index, frame])
            if from_notes:
                labels[index, frame] = _chord_from_notes(notes, time_s)
            else:
                label_277 = _label_at(timeline, time_s)
                labels[index, frame] = (_MAP_TABLE[label_277]
                                        if label_277 < NUM_CLASSES - 1 else N_IDX_170)
            if notes:
                pc = bass_pitch_class_from_notes(notes, time_s)
                if pc is not None:
                    bass[index, frame] = BASS_TO_IDX[BASS_VOCAB[pc % 12]]
            elif intervals:
                bass[index, frame] = _bass_from_intervals(intervals, time_s)
    return labels, bass


def _rewrite_npz(path: Path, labels: np.ndarray, bass: np.ndarray) -> None:
    with np.load(path) as data:
        payload = {key: data[key] for key in data.files}
    payload["frame_labels"] = labels.astype(np.uint8)
    payload["frame_bass"] = bass.astype(np.uint8)
    payload["frame_version"] = np.int64(FRAME_VERSION)
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(tmp, **payload)
    os.replace(tmp, path)


def process_real(args: tuple[str, dict, Path, bool]) -> dict:
    _dataset, meta, path, overwrite = args
    try:
        with np.load(path) as data:
            if "frame_labels" in data.files and not overwrite:
                return {"track": meta["track_id"], "status": "skipped"}
            centres = (np.asarray(data["center_times"], dtype=np.float64)
                       if "center_times" in data.files
                       else np.arange(data["features"].shape[0]) * HOP_SEC)
            stored_window = int(data["features"].shape[1])
        window = stored_window
        labels, bass = _frame_labels_for_meta(meta, centres, window)
        _rewrite_npz(path, labels, bass)
        return {"track": meta["track_id"], "status": "ok",
                "windows": int(len(centres)),
                "frame_n": int(np.sum(labels == N_IDX_170))}
    except Exception as exc:
        return {"track": meta["track_id"],
                "status": f"error:{type(exc).__name__}: {exc}"}


def process_slakh(args: tuple[Path, Path, bool]) -> dict:
    path, raw_dir, overwrite = args
    try:
        with np.load(path) as data:
            if "frame_labels" in data.files and not overwrite:
                return {"track": path.stem, "status": "skipped"}
            track_id = (bytes(data["track_id"]).decode()
                        if "track_id" in data.files else path.stem)
            centres = (np.asarray(data["center_times"], dtype=np.float64)
                       if "center_times" in data.files
                       else np.arange(data["features"].shape[0]) * HOP_SEC)
            window = int(data["features"].shape[1])
        midi_path = raw_dir / track_id / "all_src.mid"
        if not midi_path.exists():
            return {"track": track_id, "status": "missing_midi"}
        notes = _note_events(midi_path)
        labels, bass = _frame_labels_for_meta({"notes": notes}, centres, window)
        _rewrite_npz(path, labels, bass)
        return {"track": track_id, "status": "ok", "windows": int(len(centres))}
    except Exception as exc:
        return {"track": path.stem, "status": f"error:{type(exc).__name__}: {exc}"}


def _real_jobs(datasets: list[str], workers: int, overwrite: bool) -> dict:
    splits = _load_splits()
    report: dict = {"datasets": {}}
    for dataset in datasets:
        tracks = _dataset_tracks(dataset, splits)
        cqt_dir = OUT_ROOT / dataset / "processed" / "cqt"
        jobs = []
        for meta in tracks:
            path = cqt_dir / f"{meta['track_id']}.npz"
            if not path.exists():
                continue
            jobs.append((dataset, meta, path, overwrite))
        results: list[dict] = []
        if workers <= 1:
            results = [process_real(job) for job in jobs]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(process_real, job) for job in jobs]
                for future in as_completed(futures):
                    results.append(future.result())
        ok = [r for r in results if r.get("status") == "ok"]
        report["datasets"][dataset] = {
            "tracks": len(jobs),
            "ok": len(ok),
            "skipped": sum(1 for r in results if r.get("status") == "skipped"),
            "windows": int(sum(r.get("windows", 0) for r in ok)),
            "frame_n": int(sum(r.get("frame_n", 0) for r in ok)),
            "errors": [r for r in results if r.get("status", "").startswith("error")][:5],
        }
    return report


def _slakh_jobs(workers: int, limit: int, overwrite: bool) -> dict:
    cqt_dir = SLAKH_FINE_DIR / "processed" / "cqt"
    paths = sorted(cqt_dir.glob("*.npz"))
    if limit:
        paths = paths[:limit]
    jobs = [(path, SLAKH_RAW_DIR, overwrite) for path in paths]
    results: list[dict] = []
    if workers <= 1:
        results = [process_slakh(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(process_slakh, job) for job in jobs]
            for future in as_completed(futures):
                results.append(future.result())
    ok = [r for r in results if r.get("status") == "ok"]
    return {
        "datasets": {"slakh": {
            "tracks": len(jobs),
            "ok": len(ok),
            "skipped": sum(1 for r in results if r.get("status") == "skipped"),
            "windows": int(sum(r.get("windows", 0) for r in ok)),
            "errors": [r for r in results if r.get("status", "").startswith("error")][:5],
        }}
    }


def add_frame_labels(datasets: list[str], workers: int = 8, limit: int = 0,
                     overwrite: bool = False, report_path: Path | None = None) -> dict:
    real = [name for name in datasets if name in REAL_DATASETS]
    report: dict = {"frame_version": FRAME_VERSION, "datasets": {}}
    if real:
        real_report = _real_jobs(real, workers, overwrite)
        report["datasets"].update(real_report["datasets"])
    if "slakh" in datasets:
        slakh_report = _slakh_jobs(workers, limit, overwrite)
        report["datasets"].update(slakh_report["datasets"])
    unknown = [name for name in datasets
               if name not in REAL_DATASETS and name != "slakh"]
    if unknown:
        raise SystemExit(f"unknown datasets: {', '.join(unknown)}")
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", default=",".join(REAL_DATASETS) + ",slakh")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    report = add_frame_labels(
        [name.strip() for name in args.datasets.split(",") if name.strip()],
        workers=args.workers, limit=args.limit, overwrite=args.overwrite,
        report_path=args.report,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
