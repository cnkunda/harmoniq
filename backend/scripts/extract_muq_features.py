"""Extract MuQ representations for the fine-window tracks.

MuQ (OpenMuQ/MuQ-large-msd-iter) is a 25 Hz, 1024-d music encoder. This
script runs it on the original audio for each fine source, resamples the
features to the 10 Hz chord grid, projects 1024→128 with a fixed Gaussian
projection, and writes the same window schema as the CQT cache so the existing
trainer/evaluator can consume it.

MuQ weights are CC-BY-NC 4.0; this representation is research-only.

Usage (from backend/, on Modal)::

    python scripts/extract_muq_features.py --datasets guitarset --limit-tracks 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import resample

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab_170 import BASS_X_IDX, N_IDX_170  # noqa: E402
from scripts.chord_data_v2 import DATA_ROOT  # noqa: E402
from scripts.extract_fine_windows import _dataset_tracks, _load_splits  # noqa: E402

FINE_ROOT = DATA_ROOT / "chord170" / "fine"
OUT_ROOT = DATA_ROOT / "chord170" / "muq"
PROJECTION_DIM = 128
MUQ_SR = 24000
TARGET_SR = 44100
HOP_SEC = 0.1
WINDOW = 16
CHUNK_SECONDS = 30.0


def _load_audio(path: Path) -> np.ndarray:
    import librosa

    audio, _ = librosa.load(str(path), sr=MUQ_SR, mono=True)
    return audio.astype(np.float32)


def _muq_features(model, audio: np.ndarray, layer: int = 6) -> np.ndarray:
    import torch

    device = next(model.parameters()).device
    chunk = int(MUQ_SR * CHUNK_SECONDS)
    pieces = []
    with torch.no_grad():
        for start in range(0, len(audio), chunk):
            segment = audio[start:start + chunk]
            if len(segment) < int(MUQ_SR * 1.0):
                continue
            tensor = torch.from_numpy(segment).unsqueeze(0).to(device)
            output = model(tensor, output_hidden_states=True)
            if layer >= 0 and output.hidden_states is not None:
                hidden = output.hidden_states[layer]
            else:
                hidden = output.last_hidden_state
            pieces.append(hidden[0].detach().cpu().numpy())
    if not pieces:
        return np.zeros((0, 1024), dtype=np.float32)
    return np.concatenate(pieces, axis=0).astype(np.float32)


def _projection() -> np.ndarray:
    rng = np.random.default_rng(12345)
    return rng.normal(0.0, 1.0 / np.sqrt(1024.0), size=(1024, PROJECTION_DIM)
                      ).astype(np.float32)


def _frame_labels(fine_path: Path) -> tuple[np.ndarray, np.ndarray, str, str]:
    with np.load(fine_path) as data:
        labels = data["frame_labels"].reshape(-1).astype(np.int64)
        bass = data["frame_bass"].reshape(-1).astype(np.int64)
        split = (bytes(data["split"]).decode() if "split" in data.files else "train")
        track_id = (bytes(data["track_id"]).decode()
                    if "track_id" in data.files else fine_path.stem)
    return labels, bass, split, track_id


def process_track(model, track: dict, dataset: str, projection: np.ndarray,
                  out_dir: Path, layer: int = 6, force: bool = False) -> dict:
    fine_path = FINE_ROOT / dataset / "processed" / "cqt" / f"{track['track_id']}.npz"
    if not fine_path.exists():
        return {"track": track["track_id"], "status": "missing_fine"}
    out_path = out_dir / f"{track['track_id']}.npz"
    if out_path.exists() and not force:
        return {"track": track["track_id"], "status": "cached"}
    audio_path = Path(track["audio"])
    if not audio_path.exists():
        return {"track": track["track_id"], "status": "missing_audio"}
    labels_fine, bass_fine, split, track_id = _frame_labels(fine_path)
    audio = _load_audio(audio_path)
    features25 = _muq_features(model, audio, layer=layer)
    if len(features25) == 0:
        return {"track": track["track_id"], "status": "empty_features"}
    target_len = max(1, int(round(features25.shape[0] / 2.5)))
    features10 = resample(features25, target_len, axis=0).astype(np.float32)
    features10 = features10 @ projection
    scale = float(features10.std()) + 1e-6
    features10 = (features10 / scale).astype(np.float16)

    # Fine global frame g is centred at (g - 8) * 0.1 s; MuQ frame t at t * 0.1 s.
    n_frames = len(features10)
    labels = np.full(n_frames, N_IDX_170, dtype=np.int64)
    bass = np.full(n_frames, BASS_X_IDX, dtype=np.int64)
    offset = WINDOW // 2
    for t in range(n_frames):
        g = t + offset
        if 0 <= g < len(labels_fine):
            labels[t] = labels_fine[g]
            bass[t] = bass_fine[g]

    n_windows = max(1, (n_frames - WINDOW) // WINDOW + 1)
    windows = np.zeros((n_windows, WINDOW, PROJECTION_DIM), dtype=np.float16)
    frame_labels = np.full((n_windows, WINDOW), N_IDX_170, dtype=np.int64)
    frame_bass = np.full((n_windows, WINDOW), BASS_X_IDX, dtype=np.int64)
    center_labels = np.full(n_windows, N_IDX_170, dtype=np.int64)
    center_bass = np.full(n_windows, BASS_X_IDX, dtype=np.int64)
    for k in range(n_windows):
        start = k * WINDOW
        end = start + WINDOW
        available = min(end, n_frames)
        windows[k, :available - start] = features10[start:available]
        frame_labels[k, :available - start] = labels[start:available]
        frame_bass[k, :available - start] = bass[start:available]
        center = start + WINDOW // 2
        if center < n_frames:
            center_labels[k] = labels[center]
            center_bass[k] = bass[center]
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        features=windows,
        labels170=center_labels,
        bass_labels=center_bass,
        frame_labels=frame_labels,
        frame_bass=frame_bass,
        confidence=np.ones(n_windows, dtype=np.float32),
        center_times=(np.arange(n_windows) * WINDOW * HOP_SEC).astype(np.float32),
        track_id=np.bytes_(track_id.encode()),
        split=np.bytes_(split.encode()),
        source=np.bytes_(f"muq_{dataset}".encode()),
        teacher=np.bytes_(b"muq"),
        loss_weight=np.float64(1.0),
        schema_version=np.int64(2),
        frame_version=np.int64(1),
    )
    return {"track": track["track_id"], "status": "ok", "windows": int(n_windows)}


def extract(datasets: list[str], limit_tracks: int = 0, layer: int = 6,
            force: bool = False, report_path: Path | None = None) -> dict:
    import torch
    from muq import MuQ

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = MuQ.from_pretrained("OpenMuQ/MuQ-large-msd-iter").to(device).eval()
    projection = _projection()
    splits = _load_splits()
    report: dict = {"datasets": {}}
    for dataset in datasets:
        tracks = _dataset_tracks(dataset, splits)
        if limit_tracks:
            tracks = tracks[:limit_tracks]
        out_dir = OUT_ROOT / dataset / "processed" / "cqt"
        results = [process_track(model, track, dataset, projection, out_dir,
                                 layer=layer, force=force)
                   for track in tracks]
        ok = [r for r in results if r.get("status") == "ok"]
        report["datasets"][dataset] = {
            "tracks": len(tracks),
            "ok": len(ok),
            "cached": sum(1 for r in results if r.get("status") == "cached"),
            "windows": int(sum(r.get("windows", 0) for r in ok)),
            "errors": [r for r in results if r.get("status", "").startswith("error")][:5],
        }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets",
                        default="guitarset,egset12,idmt_smt_guitar,rwc,guitar_techs,idmt_chords")
    parser.add_argument("--limit-tracks", type=int, default=0)
    parser.add_argument("--layer", type=int, default=6)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    report = extract([d.strip() for d in args.datasets.split(",") if d.strip()],
                     args.limit_tracks, args.layer, args.force, args.report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
