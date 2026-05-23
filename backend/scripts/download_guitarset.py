"""Download GuitarSet dataset from Zenodo.

Downloads audio (mono-pickup-mix) and annotation files, extracts them into
the expected directory structure for parse_guitarset.py and extract_guitarset_cqt.py.

Usage:
    python scripts/download_guitarset.py [--data-dir DATA_DIR] [--force]

Output:
    <data_dir>/guitarset/raw/
        audio_mono-mix/  — mono pickup mix WAV files
        annotation/      — JAMS annotation files
"""

from pathlib import Path
import zipfile
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "guitarset" / "raw"

ZENODO_BASE = "https://zenodo.org/records/3371780/files"

FILES = {
    "audio_mono-pickup_mix.zip": {
        "extract_to": "audio_mono-mix",
        "description": "GuitarSet mono pickup mix audio (~683 MB)",
    },
    "annotation.zip": {
        "extract_to": "annotation",
        "description": "GuitarSet JAMS annotations (~39 MB)",
    },
}


def _download(url: str, dest: Path, desc: str) -> bool:
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"  [SKIP] {dest.name} exists ({dest.stat().st_size / 1024 / 1024:.0f} MB)")
        return False

    print(f"  [DOWNLOAD] {desc} ...", end=" ", flush=True)
    try:
        resp = requests.get(url, stream=True, timeout=300)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = int(resp.headers.get("content-length", 0))
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
    """Extract a zip file into target_dir, preserving inner directory structure."""
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                # Skip directories
                if member.endswith("/"):
                    continue
                # Determine output path - strip top-level directory if present
                parts = Path(member).parts
                if len(parts) > 1:
                    out_path = target_dir / "/".join(parts[1:])
                else:
                    out_path = target_dir / Path(member).name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if not out_path.exists():
                    with zf.open(member) as src, open(out_path, "wb") as dst:
                        dst.write(src.read())
                    count += 1
    except Exception as e:
        print(f"  [WARN] Extraction failed for {zip_path.name}: {e}")
    return count


def main(data_dir: Path, force: bool = False) -> None:
    raw_dir = data_dir / "guitarset" / "raw"

    for zip_name, info in FILES.items():
        extract_dir = raw_dir / info["extract_to"]

        # Check if already extracted
        if not force and extract_dir.exists() and len(list(extract_dir.rglob("*"))) > 5:
            file_count = len(list(extract_dir.rglob("*")))
            print(f"[SKIP] {info['extract_to']} already extracted ({file_count} files)")
            continue

        # Download
        url = f"{ZENODO_BASE}/{zip_name}"
        zip_path = raw_dir / zip_name
        _download(url, zip_path, info["description"])

        # Extract
        if zip_path.exists():
            count = _extract_zip(zip_path, extract_dir)
            print(f"  Extracted {count} files to {extract_dir}")

    # Summary
    audio_dir = raw_dir / "audio_mono-mix"
    annot_dir = raw_dir / "annotation"
    audio_files = list(audio_dir.rglob("*.wav")) if audio_dir.exists() else []
    annot_files = list(annot_dir.rglob("*.jams")) + list(annot_dir.rglob("*.json")) if annot_dir.exists() else []
    print(f"\nGuitarSet download complete:")
    print(f"  Audio files: {len(audio_files)}")
    print(f"  Annotation files: {len(annot_files)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download GuitarSet from Zenodo")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args()
    main(args.data_dir, force=args.force)
