"""Download Guitar-TECHS dataset from Zenodo.

Downloads all 9 archive files from Zenodo record 14963133, extracts them into
the expected directory structure for parse_guitar_techs.py.

Guitar-TECHS: 3 players × (chords, scales, singlenotes, techniques) + P3 music
Audio: 4 perspectives (DI, amp_mic, ego, exo). We extract all; CQT uses DI.
MIDI: per-string annotations via Fishman Triple Play Connect pickup.

Usage:
    python scripts/download_guitar_techs.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/guitar_techs/raw/
        P1_chords/      — chord recordings, player 1
        P1_scales/      — scale recordings, player 1
        P1_singlenotes/ — single notes, player 1
        P1_techniques/  — technique recordings, player 1
        P2_chords/      — chord recordings, player 2
        P2_scales/      — scale recordings, player 2
        P2_singlenotes/ — single notes, player 2
        P2_techniques/  — technique recordings, player 2
        P3_music/       — musical excerpts, player 3
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "guitar_techs" / "raw"

ZENODO_BASE = "https://zenodo.org/records/14963133/files"

FILES = [
    ("P1_chords.zip",      981_741_162, "Player 1 chord recordings"),
    ("P1_scales.zip",      453_349_723, "Player 1 scale recordings"),
    ("P1_singlenotes.zip", 108_626_613, "Player 1 single notes"),
    ("P1_techniques.zip",  326_280_863, "Player 1 technique recordings"),
    ("P2_chords.zip",    1_150_819_056, "Player 2 chord recordings"),
    ("P2_scales.zip",      471_254_783, "Player 2 scale recordings"),
    ("P2_singlenotes.zip", 116_133_457, "Player 2 single notes"),
    ("P2_techniques.zip",  395_839_610, "Player 2 technique recordings"),
    ("P3_music.zip",       129_505_089, "Player 3 musical excerpts"),
]


def _download(url: str, dest: Path, desc: str, expected_size: int) -> bool:
    if dest.exists() and dest.stat().st_size > expected_size * 0.9:
        print(f"  [SKIP] {dest.name} exists ({dest.stat().st_size / 1024 / 1024:.0f} MB)")
        return False

    print(f"  [DOWNLOAD] {desc} ...", end=" ", flush=True)
    try:
        resp = requests.get(url, stream=True, timeout=600)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = int(resp.headers.get("content-length", 0)) or expected_size
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total * 100
                    print(f"\r  [DOWNLOAD] {desc} ... {pct:.0f}%", end="", flush=True)
        print(f"\r  [DOWNLOAD] {desc} ... done ({dest.stat().st_size / 1024 / 1024:.0f} MB)")
        return True
    except requests.RequestException as e:
        print(f"\n  FAILED: {e}")
        return False


def _extract_zip(zip_path: Path, target_dir: Path) -> int:
    """Extract a zip file into target_dir, skipping __MACOSX artifacts."""
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                if member.startswith("__MACOSX") or "/._" in member:
                    continue
                parts = Path(member).parts
                if len(parts) > 1:
                    out_path = target_dir / "/".join(parts[1:])
                else:
                    out_path = target_dir / Path(member).name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if out_path.exists():
                    continue
                with zf.open(member) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
                count += 1
    except Exception as e:
        print(f"  [WARN] Extraction failed for {zip_path.name}: {e}")
    return count


def main(data_dir: Path, force: bool = False) -> None:
    raw_dir = data_dir / "guitar_techs" / "raw"

    for zip_name, expected_size, desc in FILES:
        # Determine expected extraction directory
        extract_name = Path(zip_name).stem
        extract_dir = raw_dir / extract_name

        if not force and extract_dir.exists() and len(list(extract_dir.rglob("*.wav"))) > 3:
            wav_count = len(list(extract_dir.rglob("*.wav")))
            print(f"[SKIP] {extract_name} already extracted ({wav_count} WAV files)")
            continue

        # Download
        url = f"https://zenodo.org/records/14963133/files/{zip_name}?download=1"
        zip_path = raw_dir / zip_name
        _download(url, zip_path, desc, expected_size)

        # Extract
        if zip_path.exists():
            count = _extract_zip(zip_path, extract_dir)
            print(f"  Extracted {count} files to {extract_dir}")

    # Summary
    print(f"\nGuitar-TECHS download complete:")
    for subdir in sorted(raw_dir.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("."):
            wavs = list(subdir.rglob("*.wav"))
            mids = list(subdir.rglob("*.mid"))
            print(f"  {subdir.name}: {len(wavs)} WAV files, {len(mids)} MIDI files")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download Guitar-TECHS from Zenodo")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
