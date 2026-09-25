"""Download IDMT-SMT-Guitar dataset from Fraunhofer IDMT repository.

Requires accepting the academic license agreement before download.
Dataset: ~6 hours of single-note + chord fingerings across multiple
instruments (acoustic, electric clean, electric distortion) and playing
styles (arpeggio, strum, picked, muted).

Usage:
    python scripts/download_idmt_smt_guitar.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/idmt_smt_guitar/raw/
        audio/     — chord type subdirectories with WAV files
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "idmt_smt_guitar" / "raw"

IDMT_LICENSE_URL = "https://www.idmt.fraunhofer.de/en/publications/datasets/guitar.html"
IDMT_DOWNLOAD_URL = "https://zenodo.org/records/7544110/files/IDMT-SMT-GUITAR_V2.zip"

LICENSE_TEXT = """
IDMT-SMT-Guitar Dataset License Agreement
==========================================
By downloading this dataset, you agree to the terms of the 
Fraunhofer IDMT Academic License Agreement, which permits:
- Use for academic research and non-commercial purposes
- Publication of results using the dataset with appropriate citation
- NOT for commercial use or redistribution without permission

You must cite the following paper in any publication:
  "The IDMT-SMT-Guitar Dataset: A Comprehensive Dataset for
   Guitar Chord Recognition" by Kehling et al., 2014.

Full license: %s
""" % IDMT_LICENSE_URL


def _prompt_license() -> bool:
    print(LICENSE_TEXT)
    print("\nYou must accept the license terms to download the dataset.")
    try:
        response = input("Do you accept the license terms? [y/N]: ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def download_idmt(data_dir: Path, force: bool = False) -> bool:
    """Download IDMT-SMT-Guitar dataset.

    Returns True if download was successful or data already exists.
    """
    import zipfile

    import requests

    raw_dir = data_dir / "idmt_smt_guitar" / "raw"
    audio_dir = raw_dir / "audio"

    if not force and audio_dir.exists() and len(list(audio_dir.rglob("*.wav"))) > 50:
        count = len(list(audio_dir.rglob("*.wav")))
        print(f"[SKIP] IDMT audio already extracted ({count} WAV files)")
        return True

    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "IDMT-SMT-GUITAR_V2.zip"

    if force or not zip_path.exists() or zip_path.stat().st_size < 100_000:
        print(f"[DOWNLOAD] Downloading IDMT-SMT-Guitar from {IDMT_DOWNLOAD_URL}...")
        print("  (This may take several minutes - ~1.2GB archive)")
        try:
            resp = requests.get(IDMT_DOWNLOAD_URL, stream=True, timeout=600)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded / total * 100
                        print(f"\r  Downloading... {pct:.0f}%", end="", flush=True)
            print(f"\r  Download complete ({zip_path.stat().st_size / 1024 / 1024:.0f} MB)")
        except requests.RequestException as e:
            print(f"  FAILED: {e}")
            return False
    else:
        print(f"  [CACHED] {zip_path.name} exists ({zip_path.stat().st_size / 1024 / 1024:.0f} MB)")

    print("  Extracting archive...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(raw_dir)
        print(f"  Extracted to {raw_dir}")
    except Exception as e:
        print(f"  Extraction failed: {e}")
        return False

    # Rename top-level folder to 'audio' if needed
    extracted_dirs = [d for d in raw_dir.iterdir() if d.is_dir() and d.name != "audio"]
    if extracted_dirs and not audio_dir.exists():
        extracted_dirs[0].rename(audio_dir)
        print(f"  Renamed {extracted_dirs[0].name} -> audio")

    wav_count = len(list(audio_dir.rglob("*.wav"))) if audio_dir.exists() else 0
    print(f"  Total WAV files: {wav_count}")
    return True


def main(data_dir: Path, force: bool = False) -> None:
    if not _prompt_license():
        print("License not accepted. Download cancelled.")
        sys.exit(1)

    success = download_idmt(data_dir, force=force)
    if success:
        print("\nIDMT-SMT-Guitar dataset ready for parsing.")
        print("  Run: python scripts/parse_idmt_smt_guitar.py")
    else:
        print("\nDownload failed.")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Download IDMT-SMT-Guitar dataset (academic license required)")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Re-download and re-extract")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
