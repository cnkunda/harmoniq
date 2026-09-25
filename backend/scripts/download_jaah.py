"""Download JAAH chord annotations (labs.zip) from GitHub.

JAAH (Jazz Audio Alignment of Harmonies) provides chord annotations
for 113 jazz recordings. The annotations are available as .lab files
(Harte format with interval notation) under CC-BY-NC-SA 4.0.

The corresponding audio is copyrighted by Smithsonian Folkways —
this script downloads ANNOTATIONS ONLY. Audio must be supplied
separately by the user.

Usage:
    python scripts/download_jaah.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/annotations/jaah/*.lab   — 113 chord annotation files
    <data_dir>/annotations/jaah/LICENSE — license information
"""

import zipfile
from pathlib import Path
import shutil

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANNOTATION_DIR = DATA_DIR / "annotations"
JAAH_DIR = ANNOTATION_DIR / "jaah"

JAAH_LABS_URL = "https://github.com/MTG/JAAH/raw/master/labs.zip"

LICENSE_TEXT = """JAAH Chord Annotations — CC-BY-NC-SA 4.0

Source: https://github.com/MTG/JAAH

These chord annotations are provided under the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International license.

The corresponding audio recordings are Copyright Smithsonian
Folkways Recordings and are NOT included. Users must obtain audio
separately from Smithsonian Folkways.

Reference:
    J. Pons, et al., "JAAH: Jazz Audio Alignment of Harmonies",
    ISMIR 2024.
"""


def main(data_dir: Path, force: bool = False) -> None:
    jaah_dir = data_dir / "annotations" / "jaah"
    jaah_dir.mkdir(parents=True, exist_ok=True)

    zip_path = jaah_dir / "labs.zip"

    # Download
    if zip_path.exists() and zip_path.stat().st_size > 1000 and not force:
        print(f"  [SKIP] labs.zip exists ({zip_path.stat().st_size / 1024:.0f} KB)")
    else:
        print(f"  [DOWNLOAD] JAAH labs.zip from {JAAH_LABS_URL} ...", end=" ", flush=True)
        try:
            resp = requests.get(JAAH_LABS_URL, stream=True, timeout=120)
            resp.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            print(f"done ({zip_path.stat().st_size / 1024:.0f} KB)")
        except requests.RequestException as e:
            print(f"FAILED: {e}")
            if zip_path.exists():
                zip_path.unlink()
            return

    # Extract .lab files
    existing_labs = list(jaah_dir.glob("*.lab"))
    if existing_labs and not force:
        print(f"  [SKIP] {len(existing_labs)} .lab files already extracted")
    else:
        count = 0
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                for member in z.namelist():
                    if member.endswith(".lab"):
                        name = Path(member).name
                        out_path = jaah_dir / name
                        if not out_path.exists() or force:
                            with z.open(member) as src, open(out_path, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            count += 1
        except zipfile.BadZipFile as e:
            print(f"  [ERROR] Bad zip file: {e}")
            return
        print(f"  Extracted {count} .lab files to {jaah_dir}")

    # Write license file
    license_path = jaah_dir / "LICENSE"
    if not license_path.exists():
        license_path.write_text(LICENSE_TEXT)
        print(f"  Wrote license to {license_path}")

    # Summary
    lab_count = len(list(jaah_dir.glob("*.lab")))
    print(f"\n  JAAH annotations: {lab_count} .lab files in {jaah_dir}")
    print(f"  License: CC-BY-NC-SA 4.0 (annotations only)")
    print()
    print(f"  NOTE: Audio files are NOT included. To use JAAH for training,")
    print(f"  obtain audio from Smithsonian Folkways and run:")
    print(f"    python scripts/extract_jaah_cqt.py --audio-dir <path>")

    # Cleanup zip
    if zip_path.exists():
        zip_path.unlink()
        print(f"  Removed temporary labs.zip")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Download JAAH chord annotations from GitHub")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true",
                        help="Force re-download and re-extraction")
    args = parser.parse_args()
    main(args.data_dir, args.force)
