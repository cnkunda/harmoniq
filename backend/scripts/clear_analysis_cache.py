"""Clear disk-backed analysis cache entries under data/cache/analysis."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.cache import clear_analysis_cache


def main() -> int:
    removed = clear_analysis_cache()
    if not removed:
        print("Analysis cache is already empty (removed 0 files).")
        return 0

    print(f"Removed {len(removed)} analysis cache file(s):")
    for path in sorted(removed):
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
