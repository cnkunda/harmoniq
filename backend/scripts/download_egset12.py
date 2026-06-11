"""Download EGSet12 dataset from Zenodo.

EGSet12: 12 original solo electric guitar performances (~32s each, 379.8s total)
with JAMS chord annotations, Guitar Pro tablature, and audio recordings.

Zenodo: 11406378 (CC BY 4.0)

Downloads individual files (12 WAV + 12 JAMS + 12 GP + 1 model checkpoint)
and organizes them for parse_egset12.py.

Usage:
    python scripts/download_egset12.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/egset12/raw/
        01.wav .. 12.wav   — audio recordings (48kHz, mono via stereo copy)
        01.jams .. 12.jams — JAMS chord/tab annotations
        01.gp .. 12.gp     — Guitar Pro tablature files
"""

from __future__ import annotations

from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "egset12" / "raw"

ZENODO_BASE = "https://zenodo.org/records/11406378/files"

FILES = []
for i in range(1, 13):
    num = f"{i:02d}"
    FILES.append((f"{num}.wav", f"Audio track {num}"))
    FILES.append((f"{num}.jams", f"JAMS annotations {num}"))
    FILES.append((f"{num}.gp", f"Guitar Pro {num}"))


def _download(url: str, dest: Path, desc: str) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  [SKIP] {dest.name} exists ({dest.stat().st_size / 1024:.0f} KB)")
        return False

    print(f"  [DOWNLOAD] {desc} ...", end=" ", flush=True)
    try:
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        print(f"done ({dest.stat().st_size / 1024:.0f} KB)" if dest.stat().st_size < 1024 * 1024
              else f"done ({dest.stat().st_size / 1024 / 1024:.0f} MB)")
        return True
    except requests.RequestException as e:
        print(f"\n  FAILED: {e}")
        return False


def main(data_dir: Path, force: bool = False) -> None:
    raw_dir = data_dir / "egset12" / "raw"

    if not force and raw_dir.exists():
        wavs = list(raw_dir.glob("*.wav"))
        jams = list(raw_dir.glob("*.jams"))
        if len(wavs) >= 12 and len(jams) >= 12:
            print(f"[SKIP] EGSet12 already downloaded ({len(wavs)} WAV, {len(jams)} JAMS)")
            return

    raw_dir.mkdir(parents=True, exist_ok=True)

    for filename, desc in FILES:
        url = f"{ZENODO_BASE}/{filename}?download=1"
        dest = raw_dir / filename
        _download(url, dest, desc)

    # Summary
    wavs = sorted(raw_dir.glob("*.wav"))
    jams = sorted(raw_dir.glob("*.jams"))
    gps = sorted(raw_dir.glob("*.gp"))
    total_mb = sum(f.stat().st_size for f in wavs) / (1024 * 1024)

    print(f"\nEGSet12 download complete:")
    print(f"  Audio: {len(wavs)} files ({total_mb:.0f} MB)")
    print(f"  JAMS:  {len(jams)} files")
    print(f"  GP:    {len(gps)} files")
    print(f"  Output: {raw_dir}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download EGSet12 from Zenodo")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
