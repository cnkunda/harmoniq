"""Build chord-oriented mixes with Demucs (Stage D pre-processing).

For each unlabeled track, separates stems with htdemucs_6s and sums
bass + guitar + piano + other into a chord-oriented mix (vocals and drums
removed). Also keeps the bass and guitar stems for bass-label derivation and
the separation ablation.

Usage (runs on a GPU; Modal entrypoint in modal_chord_170.py)::

    python scripts/build_chord_mixes.py \
        --audio-dir data/youtube_crawl/raw \
        --out-dir data/chord170/chord_mix \
        --limit 10
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

CHORD_STEMS = ("bass", "guitar", "piano", "other")
KEEP_STEMS = ("bass", "guitar")


def _load_audio(path: Path, sample_rate: int = 44100):
    import soundfile as sf
    import torch
    import torchaudio.functional as AF

    data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    wav = torch.from_numpy(data.T)  # [channels, samples]
    if sr != sample_rate:
        wav = AF.resample(wav, sr, sample_rate)
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    return wav, sample_rate


def _save_stem(path: Path, tensor, sample_rate: int) -> None:
    import soundfile as sf

    arr = tensor.detach().cpu().numpy().T  # [samples, channels]
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 1.0:
        arr = arr / peak
    sf.write(str(path), arr.astype(np.float32), sample_rate)


def build_mixes(
    audio_dir: Path,
    out_dir: Path,
    *,
    limit: int = 0,
    device: str = "cuda",
    model_name: str = "htdemucs_6s",
    force: bool = False,
) -> dict:
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    wavs = sorted(Path(audio_dir).glob("*.wav"))
    if limit:
        wavs = wavs[:limit]
    model = get_model(model_name)
    model.eval()
    device = device if torch.cuda.is_available() else "cpu"
    model.to(device)
    sources = list(model.sources)
    report = {"model": model_name, "device": device, "tracks": 0, "skipped": 0,
              "sources": sources, "out_dir": str(out_dir)}
    started = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, wav_path in enumerate(wavs):
        track_dir = out_dir / wav_path.stem
        mix_path = track_dir / "chord_mix.wav"
        if mix_path.exists() and not force:
            report["skipped"] += 1
            continue
        try:
            wav, sample_rate = _load_audio(wav_path)
            with torch.no_grad():
                stems = apply_model(model, wav[None].to(device), device=device,
                                    progress=False)[0]
            by_name = {name: stems[i] for i, name in enumerate(sources)}
            chord_mix = sum(by_name.get(name, torch.zeros_like(stems[0]))
                            for name in CHORD_STEMS)
            track_dir.mkdir(parents=True, exist_ok=True)
            _save_stem(mix_path, chord_mix, sample_rate)
            for name in KEEP_STEMS:
                if name in by_name:
                    _save_stem(track_dir / f"{name}.wav", by_name[name], sample_rate)
            report["tracks"] += 1
            if report["tracks"] % 10 == 0:
                print(f"  [{report['tracks']}/{len(wavs)}] {wav_path.name} "
                      f"({time.time() - started:.0f}s)", flush=True)
        except Exception as exc:
            print(f"  [WARN] {wav_path.name}: {type(exc).__name__}: {exc}", flush=True)
    report["elapsed_s"] = round(time.time() - started, 1)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", type=Path,
                        default=_BACKEND_DIR / "data" / "youtube_crawl" / "raw")
    parser.add_argument("--out-dir", type=Path,
                        default=_BACKEND_DIR / "data" / "chord170" / "chord_mix")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    import json

    report = build_mixes(args.audio_dir, args.out_dir, limit=args.limit,
                         device=args.device, force=args.force)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
