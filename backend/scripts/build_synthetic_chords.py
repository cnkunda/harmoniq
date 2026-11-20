"""Render a balanced synthetic guitar chord corpus from local .lab annotations.

The source annotations are the Isophonics / Billboard / JAAH `.lab` files under
``data/annotations``. Only labels that map cleanly to the 170 vocabulary are
used; altered/parenthesised labels are skipped to avoid label noise. Each
segment is rendered as a 1.6 s additive-synthesis guitar chord with a chosen
bass/inversion, then converted to the same 144-bin CQT used by the fine cache.

This is training data only: the external gate test never includes synthetic
windows. The annotations are CC BY 4.0 except JAAH (CC BY-NC-SA 4.0); the
resulting synthetic corpus is research-only if JAAH is included.

Usage (from backend/)::

    python scripts/build_synthetic_chords.py --limit 8000 --workers 8 \
        --report data/chord170/synthetic_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import parse_annotation_label, pitch_class_from_name  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    BASS_TO_IDX,
    BASS_VOCAB,
    CHORD_TO_IDX_170,
    QUALITIES_14,
    QUALITY_INTERVALS_170,
)

DATA_ROOT = _BACKEND_DIR / "data"
ANNOTATION_ROOT = DATA_ROOT / "annotations"
OUT_ROOT = DATA_ROOT / "chord170" / "synthetic_guitar" / "processed" / "cqt"
TARGET_SR = 44100
HOP_SEC = 0.1
NUM_BINS = 144
BINS_PER_OCTAVE = 24
CLIP_SECONDS = 1.7
WINDOW = 16


def _hash_split(track_id: str) -> str:
    score = int(hashlib.sha256(f"synthetic:{track_id}".encode()).hexdigest(), 16) % 100
    if score < 5:
        return "test"
    if score < 10:
        return "val"
    return "train"


def read_lab(path: Path) -> list[tuple[float, float, str]]:
    """Read ``start end label`` lines from a .lab file."""
    rows: list[tuple[float, float, str]] = []
    try:
        for line in path.read_text(errors="replace").splitlines():
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            try:
                start, end = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            label = parts[2].strip()
            if end > start and label:
                rows.append((start, end, label))
    except OSError:
        pass
    return rows


def parse_segments(annotation_root: Path) -> list[dict]:
    """Extract usable (label170, bass, duration, source) chord segments."""
    segments: list[dict] = []
    for path in sorted(annotation_root.rglob("*.lab")):
        source = path.parent.name
        for start, end, raw in read_lab(path):
            if "(" in raw or "*" in raw or raw == "N":
                continue
            parsed = parse_annotation_label(raw)
            if parsed is None:
                continue
            root, quality, bass = parsed
            if quality not in QUALITIES_14:
                continue
            root_pc = pitch_class_from_name(root)
            if root_pc is None:
                continue
            label = CHORD_TO_IDX_170.get(f"{root}:{quality}")
            if label is None:
                continue
            bass_pc = bass if bass is not None else root_pc
            segments.append({
                "label": int(label),
                "bass": int(bass_pc) % 12,
                "duration": float(end - start),
                "source": source,
                "track": path.stem,
                "start": float(start),
            })
    return segments


def select_balanced(segments: list[dict], limit: int, seed: int = 0) -> list[dict]:
    """Rarest-first selection with per-class and per-bass caps."""
    rng = np.random.default_rng(seed)
    class_counts: dict[int, int] = {}
    bass_counts: dict[int, int] = {}
    for segment in segments:
        class_counts[segment["label"]] = class_counts.get(segment["label"], 0) + 1
        bass_counts[segment["bass"]] = bass_counts.get(segment["bass"], 0) + 1
    order = sorted(
        range(len(segments)),
        key=lambda i: (
            class_counts[segments[i]["label"]],
            rng.random(),
        ),
    )
    per_class_cap = max(20, int(np.ceil(limit / 120)))
    per_bass_cap = max(200, int(np.ceil(limit / 4)))
    selected_classes: dict[int, int] = {}
    selected_bass: dict[int, int] = {}
    selected: list[dict] = []
    for index in order:
        segment = segments[index]
        if segment["duration"] < WINDOW * HOP_SEC:
            continue
        if selected_classes.get(segment["label"], 0) >= per_class_cap:
            continue
        if selected_bass.get(segment["bass"], 0) >= per_bass_cap:
            continue
        selected.append(segment)
        selected_classes[segment["label"]] = selected_classes.get(segment["label"], 0) + 1
        selected_bass[segment["bass"]] = selected_bass.get(segment["bass"], 0) + 1
        if len(selected) >= limit:
            break
    return selected


def synth_clip(segment: dict, index: int) -> tuple[np.ndarray, int]:
    """Additive guitar-like synthesis for one chord segment."""
    rng = np.random.default_rng(9000 + index)
    label = int(segment["label"])
    quality = QUALITIES_14[label // 12]
    root_pc = label % 12
    bass_pc = int(segment["bass"]) % 12
    intervals = QUALITY_INTERVALS_170[quality]
    chord_pcs = [(root_pc + interval) % 12 for interval in intervals]
    bass_midi = 40 + bass_pc
    notes = [bass_midi]
    for pc in chord_pcs:
        if pc == bass_pc:
            continue
        midi = bass_midi + ((pc - bass_pc) % 12)
        if midi < bass_midi + 4:
            midi += 12
        notes.append(midi)
    if rng.random() < 0.5:
        notes.append(bass_midi + 12)

    sr = TARGET_SR
    n_samples = int(sr * CLIP_SECONDS)
    t = np.arange(n_samples, dtype=np.float32) / sr
    wave = np.zeros(n_samples, dtype=np.float32)
    for note_index, midi in enumerate(notes):
        frequency = 440.0 * 2.0 ** ((midi - 69.0) / 12.0)
        onset = int(sr * note_index * rng.uniform(0.008, 0.030))
        if onset >= n_samples:
            continue
        length = n_samples - onset
        tt = t[:length]
        decay = rng.uniform(2.2, 4.5)
        envelope = np.exp(-decay * tt).astype(np.float32)
        tone = np.zeros(length, dtype=np.float32)
        for harmonic in range(1, 7):
            amplitude = (1.0 / harmonic ** rng.uniform(1.0, 2.0)) * rng.uniform(0.4, 1.0)
            phase = rng.uniform(0.0, 2.0 * np.pi)
            tone += (amplitude * np.sin(
                2.0 * np.pi * frequency * harmonic * tt + phase)).astype(np.float32)
        transient = int(0.015 * sr)
        if transient > 0:
            noise = rng.normal(0.0, 0.25, transient).astype(np.float32)
            noise *= np.exp(-np.arange(transient) / (0.004 * sr)).astype(np.float32)
            tone[:transient] += noise
        wave[onset:] += tone * envelope
    peak = float(np.max(np.abs(wave)))
    if peak > 0:
        wave /= peak
    wave *= rng.uniform(0.25, 0.75)
    wave += rng.normal(0.0, 0.004, wave.shape).astype(np.float32)
    return np.clip(wave, -1.0, 1.0), bass_pc


def windows_for_clip(audio: np.ndarray) -> np.ndarray:
    import librosa

    cqt = np.abs(librosa.cqt(
        y=audio, sr=TARGET_SR, hop_length=int(TARGET_SR * HOP_SEC),
        n_bins=NUM_BINS, bins_per_octave=BINS_PER_OCTAVE)).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    frames = cqt / norms
    if len(frames) < WINDOW:
        pad = np.zeros((WINDOW - len(frames), NUM_BINS), dtype=np.float32)
        frames = np.concatenate([frames, pad], axis=0)
    if len(frames) > WINDOW:
        start = (len(frames) - WINDOW) // 2
        frames = frames[start:start + WINDOW]
    return frames[None, :, :].astype(np.float32)


def process_segment(args: tuple[dict, int, Path]) -> dict:
    segment, index, out_dir = args
    try:
        audio, bass_pc = synth_clip(segment, index)
        features = windows_for_clip(audio)
        label = int(segment["label"])
        bass_idx = BASS_TO_IDX[BASS_VOCAB[bass_pc % 12]]
        track_id = f"synthetic_{index:06d}"
        split = _hash_split(track_id)
        np.savez_compressed(
            out_dir / f"{track_id}.npz",
            features=features,
            labels170=np.array([label], dtype=np.int64),
            bass_labels=np.array([bass_idx], dtype=np.int64),
            frame_labels=np.full((1, WINDOW), label, dtype=np.int64),
            frame_bass=np.full((1, WINDOW), bass_idx, dtype=np.int64),
            confidence=np.ones(1, dtype=np.float32),
            center_times=np.array([(WINDOW // 2) * HOP_SEC], dtype=np.float32),
            track_id=np.bytes_(track_id.encode()),
            split=np.bytes_(split.encode()),
            source=np.bytes_(b"synthetic_guitar"),
            teacher=np.bytes_(b"additive"),
            loss_weight=np.float64(1.0),
            schema_version=np.int64(2),
            frame_version=np.int64(1),
        )
        return {"index": index, "label": label, "bass": bass_pc, "split": split,
                "status": "ok"}
    except Exception as exc:
        return {"index": index, "status": f"error:{type(exc).__name__}: {exc}"}


def build(annotation_root: Path = ANNOTATION_ROOT, out_dir: Path = OUT_ROOT,
          limit: int = 8000, workers: int = 8, seed: int = 0,
          clips_per_segment: int = 1, force: bool = False,
          report_path: Path | None = None) -> dict:
    segments = parse_segments(annotation_root)
    selected = select_balanced(segments, limit, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    if force:
        for path in out_dir.glob("synthetic_*.npz"):
            path.unlink()
    jobs = []
    index = 0
    for segment in selected:
        repeats = max(1, min(int(clips_per_segment),
                             int(segment["duration"] // (WINDOW * HOP_SEC))))
        for _ in range(repeats):
            jobs.append((segment, index, out_dir))
            index += 1
    results: list[dict] = []
    if workers <= 1:
        results = [process_segment(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(process_segment, job) for job in jobs]
            for future in as_completed(futures):
                results.append(future.result())
    ok = [r for r in results if r.get("status") == "ok"]
    labels = [r["label"] for r in ok]
    bass = [r["bass"] for r in ok]
    report = {
        "segments_available": len(segments),
        "selected_segments": len(selected),
        "rendered": len(ok),
        "splits": {split: sum(1 for r in ok if r["split"] == split)
                   for split in ("train", "val", "test")},
        "unique_classes": len(set(labels)),
        "unique_bass": len(set(bass)),
        "class_counts": {str(k): int(v) for k, v in
                         zip(*np.unique(labels, return_counts=True))} if labels else {},
        "bass_counts": {str(k): int(v) for k, v in
                        zip(*np.unique(bass, return_counts=True))} if bass else {},
        "errors": [r for r in results if r.get("status") != "ok"][:5],
        "out_dir": str(out_dir),
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-root", type=Path, default=ANNOTATION_ROOT)
    parser.add_argument("--out-dir", type=Path, default=OUT_ROOT)
    parser.add_argument("--limit", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--clips-per-segment", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build(args.annotation_root, args.out_dir, args.limit, args.workers,
                   args.seed, args.clips_per_segment, args.force, args.report)
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("class_counts", "bass_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
