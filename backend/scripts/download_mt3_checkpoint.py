"""Download MT3 ismir2022_small checkpoint from GCS to local mt3_t5_small.

Usage: python scripts/download_mt3_checkpoint.py
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from urllib.request import Request, urlopen

GCS_API = "https://www.googleapis.com/storage/v1/b/mt3/o"
DL_BASE = "https://storage.googleapis.com/mt3/checkpoints/ismir2022_small"
TARGET = Path(__file__).resolve().parent.parent / "data" / "models" / "mt3" / "mt3_t5_small"


def main() -> None:
    # 1. Wipe old zero-byte stubs
    if TARGET.exists():
        print(f"Removing old checkpoint at {TARGET}")
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    print(f"Created {TARGET}")

    # 2. List remote files
    t0 = time.time()
    print("Listing GCS bucket contents...")
    resp = urlopen(f"{GCS_API}?prefix=checkpoints/ismir2022_small/&maxResults=2000")
    items = json.loads(resp.read())["items"]
    total_size = sum(int(item["size"]) for item in items)
    print(f"Found {len(items)} files ({total_size / 1_000_000:.1f} MB)")

    # Collect dir markers so we can skip conflicting bare entries
    dir_markers: set[str] = set()
    leaf_items: list[dict] = []
    for item in items:
        name = item["name"]
        rel = name.removeprefix("checkpoints/ismir2022_small/")
        # Skip root directory marker and GCS _$folder$ markers
        if not rel or rel.endswith("_$folder$"):
            continue
        # Record as dir marker if other items have it as a prefix
        if "/" in rel:
            parent = rel[: rel.rfind("/")]
            dir_markers.add(str(TARGET / parent))
        leaf_items.append(item)

    if leaf_items:
        for sample in leaf_items[:3]:
            print(f"  sample: {sample['name']} ({sample['size']}B)")
    print(f"Downloading {len(leaf_items)} leaf files (after filtering)")

    # 3. Download each file
    downloaded = 0
    for i, item in enumerate(leaf_items):
        rel = item["name"].removeprefix("checkpoints/ismir2022_small/")
        dest = TARGET / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        # If dest itself is a directory marker path, skip writing to it
        if str(dest) in dir_markers:
            continue

        url = f"{DL_BASE}/{rel}"
        req = Request(url, headers={"Accept-Encoding": "identity"})
        data = urlopen(req).read()
        dest.write_bytes(data)
        downloaded += len(data)

        elapsed = time.time() - t0
        rate = downloaded / elapsed / 1_000_000 if elapsed > 0 else 0
        if (i + 1) % 50 == 0:
            print(
                f"  [{i+1}/{len(leaf_items)}] {downloaded / 1_000_000:.1f} MB "
                f"({rate:.1f} MB/s)"
            )

    elapsed = time.time() - t0
    final = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file())
    print(f"\nDone in {elapsed:.0f}s — {final / 1_000_000:.1f} MB downloaded to {TARGET}")


if __name__ == "__main__":
    main()
