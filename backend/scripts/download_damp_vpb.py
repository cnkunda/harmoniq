"""Download DAMP-VPB dataset from Zenodo (Google Research).

DAMP - Vocal Performance Behaviors subset with pitch files.
Contains ~2700h of mobile device recordings with CREPE-based f0 annotations.
We filter for "guitar" and "ukulele" instrument-tagged segments.

**Status: UNAVAILABLE** — Zenodo record 11957226 returned 410 Gone.
The DAMP vocal datasets have been withdrawn by the rights holder (Smule).
See https://ccrma.stanford.edu/damp/ for current status.

The training pipeline handles this gracefully — DAMP-VPB is skipped
with a warning and the remaining 4 datasets (GuitarSet, IDMT-SMT-Guitar,
VST-Synthetic, YouTube-Crawl) are used instead.

Usage:
    python scripts/download_damp_vpb.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/damp_vpb/raw/
        audio/     — device-recorded WAV files
        pitch/     — CREPE f0 annotation files
        metadata/  — per-file instrument labels
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "damp_vpb" / "raw"

# DAMP-VPB subset on Zenodo
# This is the "Vocal Performance Behaviors" subset with pitch annotations
ZENODO_RECORD = "11957226"
ZENODO_BASE = f"https://zenodo.org/records/{ZENODO_RECORD}/files"

# Files to download (just the instrument-tagged subset for guitar/ukulele)
FILES = {
    "damp_vpb_guitar_subset.zip": {
        "extract_to": "",
        "description": "DAMP-VPB guitar/ukulele subset (~2 GB, compressed)",
    },
}


def download_damp(data_dir: Path, force: bool = False) -> bool:
    """Download DAMP-VPB guitar subset.

    Returns True if successful or already exists.
    """
    import zipfile

    import requests

    raw_dir = data_dir / "damp_vpb" / "raw"

    # Check if already extracted
    audio_dir = raw_dir / "audio"
    if not force and audio_dir.exists() and len(list(audio_dir.rglob("*.wav"))) > 100:
        count = len(list(audio_dir.rglob("*.wav")))
        print(f"[SKIP] DAMP-VPB already extracted ({count} WAV files)")
        return True

    # Check if Zenodo record is reachable
    try:
        resp = requests.head(
            f"https://zenodo.org/records/{ZENODO_RECORD}", timeout=15
        )
        if resp.status_code == 410:
            print(
                f"  [UNAVAILABLE] Zenodo record {ZENODO_RECORD} has been withdrawn "
                "(410 Gone)."
            )
            print(
                "  The DAMP vocal datasets are no longer distributed by Smule. "
                "See https://ccrma.stanford.edu/damp/"
            )
            print(
                "  The training pipeline will skip DAMP-VPB gracefully. "
                "No action needed."
            )
            return False
    except requests.RequestException:
        pass  # Network issue — try the download anyway below

    raw_dir.mkdir(parents=True, exist_ok=True)

    for zip_name, info in FILES.items():
        extract_dir = raw_dir / info["extract_to"]
        zip_path = raw_dir / zip_name

        # Download
        if force or not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
            url = f"{ZENODO_BASE}/{zip_name}"
            print(f"[DOWNLOAD] {info['description']}...")
            try:
                resp = requests.get(url, stream=True, timeout=1200)
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = downloaded / total * 100
                            print(f"\r  {pct:.0f}%", end="", flush=True)
                print(f"\r  Done ({zip_path.stat().st_size / 1024 / 1024:.0f} MB)")
            except requests.RequestException as e:
                print(f"  FAILED: {e}")
                return False
        else:
            print(f"  [CACHED] {zip_name} ({zip_path.stat().st_size / 1024 / 1024:.0f} MB)")

        # Extract
        print("  Extracting...")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            print(f"  Extracted to {extract_dir}")
        except Exception as e:
            print(f"  Extraction failed: {e}")
            return False

    # Print summary
    audio_files = list(raw_dir.rglob("*.wav"))
    pitch_files = list(raw_dir.rglob("*.csv")) + list(raw_dir.rglob("*.f0"))
    print(f"\nDAMP-VPB download complete:")
    print(f"  Audio files: {len(audio_files)}")
    print(f"  Pitch annotation files: {len(pitch_files)}")
    return True


def main(data_dir: Path, force: bool = False) -> None:
    success = download_damp(data_dir, force=force)
    if success:
        print("\nDAMP-VPB dataset ready for extraction.")
        print("  Run: python scripts/extract_damp_vpb.py")
    else:
        print("\nNote: DAMP-VPB is optional — the training pipeline skips it gracefully.")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Download DAMP-VPB dataset from Zenodo (Google Research)")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-download existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
