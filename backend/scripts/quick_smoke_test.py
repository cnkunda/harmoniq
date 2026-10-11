"""Quick smoke test: runs the full pipeline on bundled test audio.

Usage:
    python scripts/quick_smoke_test.py
    python scripts/quick_smoke_test.py --path /path/to/test_song.wav

Checks:
  - Backend is reachable
  - Upload + analyze completes
  - LessonJSON has chord_timeline and solo_notes
  - At least one section has non-zero confidence
  - Fallback chain tier is reported

Returns exit code 0 on pass, 1 on fail.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_API = "http://localhost:8000"
DEFAULT_TIMEOUT = 900  # 15 minutes — MT3 on CPU takes ~10 min for a 30s clip


def main() -> None:
    parser = argparse.ArgumentParser(description="Harmoniq quick smoke test")
    parser.add_argument("--api", default=DEFAULT_API, help="Backend API base URL")
    parser.add_argument(
        "--path",
        type=Path,
        help="Path to test audio file (WAV/MP3). If omitted, uses bundled test audio.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Max seconds to wait for the pipeline (default: %(default)s)",
    )
    args = parser.parse_args()

    # Health check
    try:
        resp = urllib.request.urlopen(f"{args.api}/health")
        assert resp.status == 200, f"Health check failed: {resp.status}"
        print(f"[PASS] Backend reachable at {args.api}")
    except Exception as e:
        print(f"[FAIL] Backend unreachable at {args.api}: {e}")
        sys.exit(1)

    # Use bundled test audio or provided path
    audio_path = args.path
    if audio_path is None:
        candidates = [
            HERE.parent / "data" / "test_audio" / "test_audio.wav",
            HERE.parents[1] / "assets" / "demo-lesson" / "reggae_clean_30s.wav",
        ]
        for candidate in candidates:
            if candidate.is_file():
                audio_path = candidate
                break
        else:
            print("[FAIL] No --path provided and no bundled test audio found.")
            print(f"      Place a test WAV at {candidates[0]} or pass --path.")
            sys.exit(1)

    if not audio_path.is_file():
        print(f"[FAIL] Audio file not found: {audio_path}")
        sys.exit(1)

    # Upload
    print(f"Uploading {audio_path.name}...")
    try:
        import requests
    except ImportError:
        print("[FAIL] requests not installed. Run: pip install requests")
        sys.exit(1)

    boundary = "----smoke-test-boundary-42"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + audio_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()

    resp = requests.post(
        f"{args.api}/analyze",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if resp.status_code != 200:
        print(f"[FAIL] Upload failed (HTTP {resp.status_code}): {resp.text[:200]}")
        sys.exit(1)

    job = resp.json()
    job_id = job.get("job_id")
    if not job_id:
        print(f"[FAIL] No job_id in response: {job}")
        sys.exit(1)
    print(f"[PASS] Upload accepted. Job ID: {job_id}")

    # Poll for completion
    max_wait = args.timeout
    poll_interval = 5
    deadline = time.time() + max_wait
    lesson = None

    while time.time() < deadline:
        time.sleep(poll_interval)
        resp = requests.get(f"{args.api}/analyze/{job_id}")
        if resp.status_code != 200:
            print(f"[WARN] Poll returned {resp.status_code}, retrying...")
            continue

        data = resp.json()
        status = data.get("status", "unknown")
        if status == "complete":
            lesson = data.get("result", data)
            print(f"[PASS] Pipeline completed in ~{max_wait - (deadline - time.time()):.0f}s")
            break
        elif status == "failed":
            print(f"[FAIL] Pipeline failed: {data.get('error', 'unknown error')}")
            sys.exit(1)
        elif time.time() > deadline - 30:
            print(f"[WARN] Still processing... (elapsed: {max_wait - (deadline - time.time()):.0f}s)")
    else:
        print(f"[FAIL] Pipeline did not complete within {max_wait}s")
        sys.exit(1)

    # Validate LessonJSON
    errors = []

    if not lesson:
        errors.append("LessonJSON is empty")
    else:
        sections = lesson.get("sections") or []
        if not sections:
            errors.append("No sections in LessonJSON")

        has_chords = any(
            s.get("chord_timeline") or s.get("chords") for s in sections
        )
        if not has_chords:
            errors.append("No chord timeline in any section")

        has_notes = any(
            s.get("solo_notes") or s.get("notes") for s in sections
        )
        if not has_notes:
            errors.append("No solo notes in any section")

        has_confidence = any(
            s.get("confidence", 0) > 0 for s in sections
        )
        if not has_confidence:
            errors.append("No section has confidence > 0")

        tier = lesson.get("chord_tier") or lesson.get("chord_source")
        print(f"  Chord tier: {tier or 'unknown'}")

    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        sys.exit(1)

    print(f"[PASS] LessonJSON has {len(sections)} sections with valid output")
    print(f"[PASS] Quick smoke test passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
