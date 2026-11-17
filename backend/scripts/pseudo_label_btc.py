"""BTC pseudo-labels on chord-oriented mixes (Stage D).

For each Demucs chord mix:
  * 144-bin CQT windows (L1-normalised, identical geometry to training)
  * BTC 170-class teacher probabilities per frame (confidence-gated)
  * bass from the separated bass stem (RMS-gated chroma)
  * chordedness filter (>=3 salient pitch classes) and N cap
  * writes the v2 pseudo-label schema (features, labels170, bass_labels,
    confidence, split, source='pseudo_btc', teacher='btc')

Usage (GPU; Modal entrypoint in modal_chord_170.py)::

    python scripts/pseudo_label_btc.py \
        --mix-dir data/chord170/chord_mix \
        --out-dir data/chord170/pseudo_btc \
        --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import pitch_to_pitch_class  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    BASS_TO_IDX,
    BASS_VOCAB,
    BASS_X_IDX,
    N_IDX_170,
    NUM_CLASSES_170,
    QUALITIES_14,
    X_IDX_170,
)
from scripts.btc_teacher import BTC_INDEX_TO_170, BtcTeacher  # noqa: E402
from scripts.chord_data_v2 import W1_ROOT, _cap_n_windows, _decode  # noqa: E402

WINDOW = 128
HOP_FRAMES = 64
HOP_SEC = 0.1
BINS_PER_OCTAVE = 24
NUM_BINS = 144
BINS_PER_SEMITONE = BINS_PER_OCTAVE // 12


def _load_w1_splits() -> dict[str, str]:
    """Track id → W1 split (train/test), used for leakage-safe pseudo splits."""
    splits: dict[str, str] = {}
    cqt_dir = W1_ROOT / "processed" / "cqt"
    if not cqt_dir.exists():
        return splits
    for path in cqt_dir.glob("youtube_*.npz"):
        try:
            data = np.load(path)
            track_id = _decode(data["track_id"])
            splits[track_id] = _decode(data["split"]) if "split" in data.files else "train"
        except Exception:
            continue
    return splits


def _cqt_windows(audio_path: Path) -> tuple[np.ndarray, np.ndarray]:
    import librosa

    y, sr = librosa.load(str(audio_path), sr=44100, mono=True)
    hop = int(sr * HOP_SEC)
    cqt = np.abs(librosa.cqt(y=y, sr=sr, hop_length=hop, n_bins=NUM_BINS,
                             bins_per_octave=BINS_PER_OCTAVE)).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    feats = cqt / norms
    half = WINDOW // 2
    padded = np.concatenate([np.zeros((half, NUM_BINS), dtype=np.float32), feats,
                             np.zeros((half, NUM_BINS), dtype=np.float32)], axis=0)
    n_windows = max(1, int(np.ceil(len(feats) / HOP_FRAMES)))
    windows = np.zeros((n_windows, WINDOW, NUM_BINS), dtype=np.float32)
    for k in range(n_windows):
        start = k * HOP_FRAMES
        windows[k] = padded[start:start + WINDOW]
    centres = np.arange(n_windows, dtype=np.float64) * HOP_FRAMES * HOP_SEC
    return windows, centres


def _active_pitch_count(window: np.ndarray, ratio: float = 0.15) -> int:
    """Count salient pitch classes in a 144-bin CQT window."""
    chroma = np.zeros(12, dtype=np.float64)
    for bin_index in range(window.shape[1]):
        chroma[(bin_index // BINS_PER_SEMITONE) % 12] += float(window[:, bin_index].sum())
    if chroma.max() <= 0:
        return 0
    return int(np.sum(chroma >= ratio * chroma.max()))


def _bass_chroma(bass_path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (chroma [12,T], per-frame RMS) for the bass stem."""
    if not bass_path.exists():
        return None
    import librosa

    y, sr = librosa.load(str(bass_path), sr=44100, mono=True)
    if y.size == 0:
        return None
    hop = int(sr * HOP_SEC)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop, norm=None)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    n = min(chroma.shape[1], len(rms))
    return chroma[:, :n], rms[:n]


def build_pseudo_labels(
    mix_dir: Path,
    out_dir: Path,
    *,
    teacher: BtcTeacher | None = None,
    limit: int = 0,
    min_confidence: float = 0.6,
    min_pitches: int = 3,
    n_cap: float = 0.20,
    bass_rms_floor_db: float = -45.0,
) -> dict:
    teacher = teacher or BtcTeacher(device="cpu")
    splits = _load_w1_splits()
    out_cqt = out_dir / "processed" / "cqt"
    out_cqt.mkdir(parents=True, exist_ok=True)
    track_dirs = sorted(p for p in Path(mix_dir).iterdir() if p.is_dir())
    if limit:
        track_dirs = track_dirs[:limit]

    pending = []
    report = {"tracks": 0, "tracks_skipped": 0, "windows_in": 0, "windows_out": 0,
              "dropped_low_confidence": 0, "dropped_low_pitch": 0, "n_out": 0,
              "bass_known": 0, "inversions": 0, "qualities": {},
              "source": "pseudo_btc", "teacher": "btc"}
    for track_dir in track_dirs:
        mix_path = track_dir / "chord_mix.wav"
        if not mix_path.exists():
            report["tracks_skipped"] += 1
            continue
        track_id = f"youtube:{track_dir.name}"
        try:
            probs, time_unit = teacher.predict_frame_probs(mix_path)
            if len(probs) == 0:
                report["tracks_skipped"] += 1
                continue
            windows, centres = _cqt_windows(mix_path)
            bass_data = _bass_chroma(track_dir / "bass.wav")
        except Exception as exc:
            print(f"  [WARN] {track_id}: {type(exc).__name__}: {exc}", flush=True)
            report["tracks_skipped"] += 1
            continue

        rms_floor = 0.0
        if bass_data is not None:
            _chroma, rms = bass_data
            if rms.size:
                peak = float(np.percentile(rms, 99))
                if peak > 0:
                    rms_floor = peak * (10 ** (bass_rms_floor_db / 20.0))

        labels, confidences, bass_labels, kept_centres = [], [], [], []
        for window, centre in zip(windows, centres):
            frame = int(round(centre / time_unit))
            if frame >= len(probs):
                continue
            frame_probs = probs[frame]
            btc_index = int(np.argmax(frame_probs))
            confidence = float(frame_probs[btc_index])
            label = int(BTC_INDEX_TO_170[btc_index])
            if confidence < min_confidence:
                report["dropped_low_confidence"] += 1
                continue
            if label != N_IDX_170 and label != X_IDX_170:
                if _active_pitch_count(window) < min_pitches:
                    report["dropped_low_pitch"] += 1
                    continue
            bass_index = BASS_X_IDX
            if bass_data is not None:
                chroma, rms = bass_data
                frame_bass = int(round(centre / HOP_SEC))
                if 0 <= frame_bass < chroma.shape[1] and rms[frame_bass] > rms_floor:
                    bass_pc = int(np.argmax(chroma[:, frame_bass]))
                    if chroma[bass_pc, frame_bass] > 0:
                        bass_index = BASS_TO_IDX[BASS_VOCAB[bass_pc % 12]]
            labels.append(label)
            confidences.append(confidence)
            bass_labels.append(bass_index)
            kept_centres.append(centre)

        if not labels:
            report["tracks_skipped"] += 1
            continue
        kept_idx = np.asarray(
            [int(round(c / (HOP_FRAMES * HOP_SEC))) for c in kept_centres],
            dtype=np.int64,
        )
        pending.append({
            "track_id": track_id,
            "features": windows[kept_idx],
            "labels": np.asarray(labels, dtype=np.int64),
            "confidence": np.asarray(confidences, dtype=np.float32),
            "bass": np.asarray(bass_labels, dtype=np.int64),
            "centres": np.asarray(kept_centres, dtype=np.float32),
        })
        report["windows_in"] += len(windows)

    if not pending:
        return {**report, "status": "no_tracks"}

    all_labels = np.concatenate([item["labels"] for item in pending])
    all_conf = np.concatenate([item["confidence"] for item in pending])
    keep_mask = _cap_n_windows(all_labels, all_conf, n_cap)

    offset = 0
    for item in pending:
        size = len(item["labels"])
        track_keep = keep_mask[offset:offset + size]
        offset += size
        if not track_keep.any():
            continue
        labels = item["labels"][track_keep]
        track_id = item["track_id"]
        np.savez_compressed(
            out_cqt / f"{track_id.replace(':', '_')}.npz",
            features=item["features"][track_keep].astype(np.float32),
            labels170=labels,
            bass_labels=item["bass"][track_keep],
            confidence=item["confidence"][track_keep],
            center_times=item["centres"][track_keep],
            track_id=np.bytes_(track_id.encode()),
            split=np.bytes_(splits.get(track_id, "train").encode()),
            source=np.bytes_(b"pseudo_btc"),
            teacher=np.bytes_(b"btc"),
            loss_weight=np.float64(0.5),
            schema_version=np.int64(2),
        )
        report["tracks"] += 1
        report["windows_out"] += int(track_keep.sum())
        report["n_out"] += int(np.sum(labels == N_IDX_170))
        report["bass_known"] += int(np.sum(item["bass"][track_keep] != BASS_X_IDX))
        roots = np.array([
            int(c) % 12 if int(c) < N_IDX_170 else -1 for c in labels
        ])
        report["inversions"] += int(np.sum(
            (item["bass"][track_keep] != BASS_X_IDX) & (roots >= 0)
            & (item["bass"][track_keep] != roots)
        ))
        for label in labels:
            if label < N_IDX_170:
                quality = QUALITIES_14[int(label) // 12]
                report["qualities"][quality] = report["qualities"].get(quality, 0) + 1

    report["status"] = "ok"
    report["out_dir"] = str(out_dir)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mix-dir", type=Path,
                        default=_BACKEND_DIR / "data" / "chord170" / "chord_mix")
    parser.add_argument("--out-dir", type=Path,
                        default=_BACKEND_DIR / "data" / "chord170" / "pseudo_btc")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--min-pitches", type=int, default=3)
    parser.add_argument("--n-cap", type=float, default=0.20)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    teacher = BtcTeacher(device=args.device)
    report = build_pseudo_labels(
        args.mix_dir, args.out_dir, teacher=teacher, limit=args.limit,
        min_confidence=args.min_confidence, min_pitches=args.min_pitches,
        n_cap=args.n_cap,
    )
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
