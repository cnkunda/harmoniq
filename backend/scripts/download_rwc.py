"""Download RWC-P audio and chord annotations (RWC 2.0).

RWC-P is the only RWC subset with chord annotations. The dataset is
released under CC BY-NC 4.0 and requires an explicit license
acknowledgment before downloading.

Usage:
    export HARMONIQ_RWC_LICENSE_ACK=1
    python scripts/download_rwc.py                    # annotations only
    python scripts/download_rwc.py --download-audio   # + RWC-P.zip (4.1 GB)

Output:
    <data_dir>/rwc/raw/chords/RWC-P/*.csv
    <data_dir>/rwc/raw/metadata.csv
    <data_dir>/rwc/raw/LICENSE_RWC.txt
    <data_dir>/rwc/raw/audio/RWC-P/*.wav   (with --download-audio)
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tarfile
import zipfile

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ANNOTATIONS_URL = (
    "https://codeload.github.com/rwc-music/rwc-annotations/tar.gz/refs/heads/main"
)
AUDIO_URL = "https://zenodo.org/records/18656623/files/RWC-P.zip?download=1"
AUDIO_MD5 = "960a11a2d7fb603ad0dae8428f53d4f0"
AUDIO_SIZE = 4_071_840_278

RWC_CHORD_COUNT = 100

LICENSE_TEXT = """RWC Music Database (RWC 2.0) — CC BY-NC 4.0

Audio: https://zenodo.org/records/18656623
Annotations: https://github.com/rwc-music/rwc-annotations

The RWC Music Database is licensed under the Creative Commons
Attribution-NonCommercial 4.0 International license. Use is limited to
non-commercial research. Credit the original authors and publications.

References:
    M. Goto, H. Hashiguchi, T. Nishimura, and R. Oka, "RWC Music
    Database: Popular, Classical and Jazz Music Databases", ISMIR 2002.
    M. Goto, H. Hashiguchi, T. Nishimura, and R. Oka, "RWC Music
    Database: Music Genre Database and Musical Instrument Sound
    Database", ISMIR 2003.
    S. Balke, J. Zeitler, V. Arifi-Mueller, B. McFee, T. Nakano,
    M. Goto, and M. Mueller, "RWC Revisited: Towards a
    Community-Driven MIR Corpus", TISMIR 2026.
"""


def license_acknowledged() -> bool:
    """Return True when the user has acknowledged the CC BY-NC 4.0 terms."""
    return os.getenv("HARMONIQ_RWC_LICENSE_ACK", "").strip() == "1"


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, desc: str,
              expected_size: int | None = None) -> bool:
    """Stream a file to disk. Returns False on failure."""
    if dest.exists():
        size = dest.stat().st_size
        if expected_size is not None:
            if size == expected_size:
                print(f"  [SKIP] {dest.name} exists ({size / 1024 / 1024:.0f} MB)")
                return True
            if size > 0:
                print(f"  [WARN] Removing partial {dest.name} ({size / 1024 / 1024:.0f} MB)")
                dest.unlink()
        elif size > 1000:
            print(f"  [SKIP] {dest.name} exists ({size / 1024:.0f} KB)")
            return True

    print(f"  [DOWNLOAD] {desc} ...", end=" ", flush=True)
    try:
        resp = requests.get(url, stream=True, timeout=300)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0 and downloaded % (50 * 1024 * 1024) < 1024 * 1024:
                    pct = downloaded / total * 100
                    print(f"\r  [DOWNLOAD] {desc} ... {pct:.0f}%", end="", flush=True)
        print(f"\r  [DOWNLOAD] {desc} ... done ({dest.stat().st_size / 1024 / 1024:.0f} MB)")
        return True
    except requests.RequestException as e:
        print(f"\n  [FAILED] {e}")
        if dest.exists():
            dest.unlink()
        return False


def _extract_annotations(tar_path: Path, raw_dir: Path) -> int:
    """Extract RWC-P chord CSVs and metadata.csv from the repo tarball."""
    chords_dir = raw_dir / "chords" / "RWC-P"
    chords_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with tarfile.open(tar_path, "r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                parts = Path(member.name).parts
                if len(parts) < 2:
                    continue
                if (
                    "chords" in parts
                    and "RWC-P" in parts
                    and member.name.endswith(".csv")
                ):
                    src = tf.extractfile(member)
                    if src is None:
                        continue
                    out_path = chords_dir / Path(member.name).name
                    with open(out_path, "wb") as dst:
                        dst.write(src.read())
                    count += 1
                elif parts[-1] == "metadata.csv":
                    src = tf.extractfile(member)
                    if src is None:
                        continue
                    with open(raw_dir / "metadata.csv", "wb") as dst:
                        dst.write(src.read())
    except (tarfile.TarError, OSError) as e:
        print(f"  [FAILED] Could not extract annotations: {e}")
        return 0
    return count


def _extract_audio(zip_path: Path, raw_dir: Path) -> int:
    """Extract WAVs from RWC-P.zip into raw/audio/RWC-P/."""
    audio_dir = raw_dir / "audio" / "RWC-P"
    audio_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member.endswith("/") or not member.endswith(".wav"):
                    continue
                out_path = audio_dir / Path(member).name
                if out_path.exists():
                    continue
                with zf.open(member) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
                count += 1
    except (zipfile.BadZipFile, OSError) as e:
        print(f"  [FAILED] Could not extract audio: {e}")
        return 0
    return count


def main(data_dir: Path, download_audio: bool = False,
         force: bool = False) -> None:
    if not license_acknowledged():
        print(
            "RWC-P is licensed CC BY-NC 4.0 (non-commercial research).\n"
            "Acknowledge the license before downloading:\n"
            "    export HARMONIQ_RWC_LICENSE_ACK=1\n"
            "Skipping RWC download."
        )
        return

    raw_dir = data_dir / "rwc" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "LICENSE_RWC.txt").write_text(LICENSE_TEXT)

    chords_dir = raw_dir / "chords" / "RWC-P"
    existing_csvs = list(chords_dir.glob("*.csv")) if chords_dir.exists() else []
    if len(existing_csvs) >= RWC_CHORD_COUNT and not force:
        print(f"[SKIP] RWC-P annotations already extracted ({len(existing_csvs)} CSVs)")
    else:
        tar_path = raw_dir / "rwc-annotations-main.tar.gz"
        if force or not tar_path.exists():
            if not _download(ANNOTATIONS_URL, tar_path, "RWC annotations (~tens of MB)"):
                return
        count = _extract_annotations(tar_path, raw_dir)
        print(f"  Extracted {count} chord CSVs to {chords_dir}")

    annotation_count = len(list(chords_dir.glob("*.csv")))
    if annotation_count < RWC_CHORD_COUNT:
        print(f"  [WARN] Expected {RWC_CHORD_COUNT} RWC-P CSVs, found {annotation_count}")

    if not (raw_dir / "metadata.csv").exists():
        print(f"  [WARN] metadata.csv missing from {raw_dir}")

    if not download_audio:
        print(
            "\n[SKIP] RWC audio not requested (4.1 GB).\n"
            "  Re-run with --download-audio to fetch RWC-P.zip."
        )
        return

    audio_dir = raw_dir / "audio" / "RWC-P"
    existing_wavs = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
    if len(existing_wavs) >= RWC_CHORD_COUNT and not force:
        print(f"[SKIP] RWC-P audio already extracted ({len(existing_wavs)} WAVs)")
    else:
        zip_path = raw_dir / "RWC-P.zip"
        if not _download(AUDIO_URL, zip_path, "RWC-P audio", AUDIO_SIZE):
            return
        actual_md5 = _md5(zip_path)
        if actual_md5 != AUDIO_MD5:
            print(f"  [FAILED] MD5 mismatch: {actual_md5} != {AUDIO_MD5}")
            zip_path.unlink()
            return
        count = _extract_audio(zip_path, raw_dir)
        print(f"  Extracted {count} WAVs to {audio_dir}")

    audio_count = len(list(audio_dir.glob("*.wav")))
    if audio_count < RWC_CHORD_COUNT:
        print(f"  [WARN] Expected {RWC_CHORD_COUNT} RWC-P WAVs, found {audio_count}")

    print("\nRWC-P download complete:")
    print(f"  Chords: {len(list(chords_dir.glob('*.csv')))} CSVs")
    print(f"  Audio:  {len(list(audio_dir.glob('*.wav')))} WAVs")
    print(f"  Output: {raw_dir}/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download RWC-P (RWC 2.0)")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="Data directory root")
    parser.add_argument("--download-audio", action="store_true",
                        help="Download RWC-P.zip (4.1 GB); default is annotations only")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args()
    main(args.data_dir, download_audio=args.download_audio, force=args.force)
