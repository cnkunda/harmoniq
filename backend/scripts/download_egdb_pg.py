"""Download EGDB-PG (Electric Guitar Database — Positive Grid Render) from Zenodo.

EGDB-PG is a massive expansion of EGDB: all EGDB DI recordings re-rendered
through the Positive Grid BiasFX2 plugin with 256 unique amp presets
(16 heads × 16 cabinets) across low-gain, crunch, and high-gain categories.

Zenodo: 19789500 (CC BY 4.0)
Total size: ~135.4 GB (FLAC bundle) / 514 hours audio

WARNING: This is a VERY large download (135+ GB). Ensure you have sufficient
disk space before proceeding. The FLAC bundle must also be decompressed.

EGDB-PG annotations are inherited from EGDB (onset/pitch labels from Guitar
Pro tablature). A future script will handle parse + CQT extraction.

Usage:
    python scripts/download_egdb_pg.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/egdb_pg/raw/
        EGDB_FLAC_bundle.zip       — FLAC audio (135.4 GB)
        random_presets_json.rar    — preset metadata (10.6 kB)
"""

from __future__ import annotations

from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "egdb_pg" / "raw"

FILES = [
    ("EGDB_FLAC_bundle.zip", 135_406_622_188, "FLAC audio bundle (135.4 GB)"),
    ("random_presets_json.rar", 10_645, "Preset metadata JSON (10.6 kB)"),
]


def _download(url: str, dest: Path, desc: str, expected_size: int) -> bool:
    if dest.exists() and dest.stat().st_size > expected_size * 0.9:
        size_gb = dest.stat().st_size / (1024 ** 3)
        print(f"  [SKIP] {dest.name} exists ({size_gb:.1f} GB)"
              if size_gb > 1 else
              f"  [SKIP] {dest.name} exists ({dest.stat().st_size / 1024:.0f} KB)")
        return False

    print(f"  [DOWNLOAD] {desc} ...", end=" ", flush=True)
    try:
        resp = requests.get(url, stream=True, timeout=3600)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = int(resp.headers.get("content-length", 0)) or expected_size
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192 * 1024):  # 8 MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total * 100
                    gb_dl = downloaded / (1024 ** 3)
                    gb_total = total / (1024 ** 3)
                    print(f"\r  [DOWNLOAD] {desc} ... {pct:.1f}% ({gb_dl:.1f}/{gb_total:.1f} GB)",
                          end="", flush=True)
        size_gb = dest.stat().st_size / (1024 ** 3)
        print(f"\r  [DOWNLOAD] {desc} ... done ({size_gb:.1f} GB)"
              if size_gb > 1 else
              f"\r  [DOWNLOAD] {desc} ... done")
        return True
    except requests.RequestException as e:
        print(f"\n  FAILED: {e}")
        return False


def main(data_dir: Path, force: bool = False) -> None:
    raw_dir = data_dir / "egdb_pg" / "raw"

    print("=" * 70)
    print("EGDB-PG DOWNLOAD — WARNING")
    print("=" * 70)
    print("This dataset is ~135.4 GB (FLAC) / 514 hours of audio.")
    print("Ensure you have at least 275 GB free disk space (download + extract).")
    print("Downloading the full bundle may take hours.")
    print("=" * 70)
    print()

    for filename, expected_size, desc in FILES:
        url = f"https://zenodo.org/records/19789500/files/{filename}?download=1"
        dest = raw_dir / filename
        _download(url, dest, desc, expected_size)

    # Summary
    print(f"\nEGDB-PG download complete:")
    for f in raw_dir.iterdir():
        if f.is_file() and not f.name.startswith("."):
            size_gb = f.stat().st_size / (1024 ** 3)
            print(f"  {f.name}: {size_gb:.1f} GB" if size_gb > 1
                  else f"  {f.name}: {f.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Download EGDB-PG from Zenodo (135+ GB — use with care)")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
