"""Download Isophonics and McGill Billboard chord annotation datasets.

Downloads .lab annotation files from:
  - Isophonics: Beatles (180), Queen (51), Zweieck (18), Carole King (7)
  - McGill Billboard: 890 annotated slots, 740 songs

Usage:
    python scripts/download_annotations.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/annotations/
        isophonics/beatles/*.lab
        isophonics/queen/*.lab
        isophonics/zweieck/*.lab
        isophonics/carole_king/*.lab
        billboard/*.lab
        download_metadata.json  — download log
"""

import io
import json
import tarfile
import zipfile
from pathlib import Path
import shutil
from urllib.parse import quote

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANNOTATION_DIR = DATA_DIR / "annotations"

ISOPHONICS_BASE = "http://isophonics.net/files/annotations"
ISOPHONICS_SOURCES = {
    "beatles": f"{ISOPHONICS_BASE}/{quote('The Beatles Annotations.tar.gz')}",
    "queen": f"{ISOPHONICS_BASE}/{quote('Queen Annotations.tar.gz')}",
    "zweieck": f"{ISOPHONICS_BASE}/{quote('Zweieck Annotations.tar.gz')}",
    "carole_king": f"{ISOPHONICS_BASE}/{quote('Carole King Annotations.tar.gz')}",
}

BILLBOARD_LAB_URL = "https://www.dropbox.com/s/ep41gwy28vo3wxy/billboard-2.0.1-lab.tar.gz?dl=1"


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
        print(f"done ({dest.stat().st_size / 1024:.0f} KB)")
        return True
    except requests.RequestException as e:
        print(f"FAILED: {e}")
        return False


def _extract_tar(tar_path: Path, target_dir: Path, lab_subdir: str = "chordlab") -> int:
    """Extract .lab files from a tar.gz archive into target_dir.

    Looks for files in a `chordlab/` subdirectory within the archive,
    or falls back to any .lab file.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            lab_files = [m for m in tar.getmembers()
                         if m.name.endswith(".lab") and "/" + lab_subdir + "/" in m.name.replace("\\", "/")]
            if not lab_files:
                lab_files = [m for m in tar.getmembers() if m.name.endswith(".lab")]

            for member in lab_files:
                name = Path(member.name).name
                out = target_dir / name
                if not out.exists():
                    with tar.extractfile(member) as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    count += 1
    except Exception as e:
        print(f"  [WARN] Extraction failed for {tar_path.name}: {e}")
    return count


def _extract_billboard(tar_path: Path, target_dir: Path) -> int:
    """Extract Billboard .lab files."""
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".lab"):
                    name = Path(member.name).name
                    out = target_dir / name
                    if not out.exists():
                        with tar.extractfile(member) as src, open(out, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        count += 1
    except Exception as e:
        print(f"  [WARN] Billboard extraction failed: {e}")
    return count


def main(data_dir: Path) -> None:
    annot_dir = data_dir / "annotations"
    annot_dir.mkdir(parents=True, exist_ok=True)

    meta = {}

    # --- Isophonics ---
    iso_dir = annot_dir / "isophonics"
    for source, url in ISOPHONICS_SOURCES.items():
        src_dir = iso_dir / source
        if src_dir.exists() and any(src_dir.glob("*.lab")):
            print(f"[SKIP] Isophonics/{source} already extracted ({len(list(src_dir.glob('*.lab')))} .lab files)")
            meta[f"isophonics/{source}"] = {"status": "cached", "count": len(list(src_dir.glob("*.lab")))}
            continue

        tar_path = annot_dir / f"isophonics_{source}.tar.gz"
        _download(url, tar_path, f"Isophonics {source}")

        if tar_path.exists():
            count = _extract_tar(tar_path, src_dir)
            print(f"  Extracted {count} .lab files to {src_dir}")
            meta[f"isophonics/{source}"] = {"status": "downloaded", "count": count}

    # --- Billboard ---
    bb_dir = annot_dir / "billboard"
    existing = list(bb_dir.glob("*.lab")) if bb_dir.exists() else []
    if existing:
        print(f"[SKIP] Billboard already extracted ({len(existing)} .lab files)")
        meta["billboard"] = {"status": "cached", "count": len(existing)}
    else:
        tar_path = annot_dir / "billboard-lab.tar.gz"
        _download(BILLBOARD_LAB_URL, tar_path, "Billboard .lab files")
        if tar_path.exists():
            count = _extract_billboard(tar_path, bb_dir)
            print(f"  Extracted {count} .lab files to {bb_dir}")
            meta["billboard"] = {"status": "downloaded", "count": count}

    # Save metadata
    meta_path = annot_dir / "download_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nMetadata saved to {meta_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download Isophonics + Billboard annotation datasets")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    args = parser.parse_args()
    main(args.data_dir)
