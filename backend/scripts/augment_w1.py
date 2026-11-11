"""W1 cross-stem-style augmentation.

A guitar-only track (GuitarSet ``_solo`` mix) is mixed with a background
track (RWC-P full mix) at a low gain, keeping the guitar track's labels.
This approximates guitar-stem + accompaniment mixing without a Demucs pass
over the whole corpus.

True Demucs stem-swap augmentation is deferred to W3 (needs a stem cache).

Usage (from ``backend/``)::

    python scripts/augment_w1.py --limit 2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.cqt_constants import TARGET_SR  # noqa: E402
from app.data_engine.manifest import (  # noqa: E402
    W1Manifest,
    W1Track,
    load_w1_manifest,
    resolve_w1_audio,
)

logger = logging.getLogger("harmoniq.w1.augment")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

_DEFAULT_MANIFEST = _REPO_ROOT / "docs" / "eval" / "w1_dataset_manifest.json"
_DEFAULT_OUTPUT = _BACKEND_DIR / "data" / "pseudo_label" / "w1" / "augmented"
_DEFAULT_REPORT = _REPO_ROOT / "docs" / "audit" / "amt" / "w1_augmentation_report.json"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--gain", type=float, default=0.15)
    parser.add_argument("--seed", default="harmoniq-w1-aug")
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args(argv)


def _safe_id(track_id: str) -> str:
    return "".join(
        char if char.isalnum() or char in "-_." else "_" for char in track_id
    )


def _pick_background(
    guitar: W1Track, backgrounds: list[W1Track], seed: str
) -> W1Track:
    digest = hashlib.sha256(f"{seed}:{guitar.id}".encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(backgrounds)
    return backgrounds[index]


def _mix_audio(guitar_path: Path, background_path: Path, gain: float):
    import librosa
    import numpy as np

    guitar, _ = librosa.load(str(guitar_path), sr=TARGET_SR, mono=True)
    background, _ = librosa.load(str(background_path), sr=TARGET_SR, mono=True)
    if guitar.size == 0:
        raise ValueError(f"empty guitar audio: {guitar_path}")
    if background.size == 0:
        raise ValueError(f"empty background audio: {background_path}")

    repeats = int(np.ceil(guitar.size / background.size))
    background = np.tile(background, repeats)[: guitar.size]
    mix = guitar + float(gain) * background
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0.99:
        mix = mix * (0.99 / peak)
    return mix.astype(np.float32)


def _write_augmented(
    output_dir: Path,
    guitar: W1Track,
    background: W1Track,
    mix,
) -> Path:
    import soundfile as sf

    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    name = f"{_safe_id(guitar.id)}__aug_{_safe_id(background.id)}.wav"
    path = audio_dir / name
    sf.write(str(path), mix, TARGET_SR)
    return path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = load_w1_manifest(args.manifest)
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    guitars = [
        track
        for track in manifest.tracks
        if track.source == "guitarset"
        and track.id.endswith("_solo")
        and track.label_status == "human"
    ]
    backgrounds = [
        track for track in manifest.tracks if track.source == "rwc_p"
    ]
    if not guitars:
        print("[FAIL] no GuitarSet solo tracks in the manifest", file=sys.stderr)
        return 2
    if not backgrounds:
        print("[FAIL] no RWC-P background tracks in the manifest", file=sys.stderr)
        return 2

    guitars.sort(key=lambda track: track.id)
    backgrounds.sort(key=lambda track: track.id)
    limit = min(max(args.limit, 1), len(guitars))

    augmented: list[dict[str, Any]] = []
    for guitar in guitars[:limit]:
        background = _pick_background(guitar, backgrounds, args.seed)
        out_path = args.output_dir / "audio" / (
            f"{_safe_id(guitar.id)}__aug_{_safe_id(background.id)}.wav"
        )
        if out_path.is_file() and not args.refresh:
            logger.info("[%s] augmentation exists", guitar.id)
        else:
            guitar_audio = resolve_w1_audio(
                manifest, guitar, manifest_path=args.manifest
            )
            background_audio = resolve_w1_audio(
                manifest, background, manifest_path=args.manifest
            )
            mix = _mix_audio(guitar_audio, background_audio, args.gain)
            _write_augmented(args.output_dir, guitar, background, mix)
            logger.info("[%s] mixed with %s", guitar.id, background.id)

        augmented.append(
            {
                "id": f"aug:{guitar.id}+{background.id}",
                "audio_path": out_path.relative_to(_BACKEND_DIR).as_posix(),
                "source_track_id": guitar.id,
                "background_track_id": background.id,
                "split": guitar.split,
                "label_status": "human",
                "label_channels": list(guitar.label_channels),
                "chord_label_path": guitar.chord_label_path,
                "note_label_path": guitar.note_label_path,
                "gain": args.gain,
                "licence_id": "CC-BY-NC-4.0",
                "notes": (
                    "Cross-stem-style mix: GuitarSet solo + RWC-P background. "
                    "Derivative is non-commercial; do not redistribute."
                ),
            }
        )

    manifest_path = args.output_dir / "augmented_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "manifest_id": f"{manifest.manifest_id}-aug",
        "description": (
            "Cross-stem-style augmentation manifest. Labels are inherited "
            "from the guitar source track; the background only adds "
            "accompaniment energy."
        ),
        "data_root": Path(os.path.relpath(_BACKEND_DIR, args.output_dir)).as_posix(),
        "tracks": sorted(augmented, key=lambda item: item["id"]),
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    report = {
        "schema_version": 1,
        "manifest_id": manifest.manifest_id,
        "method": "cross_stem_style_audio_mix",
        "gain": args.gain,
        "seed": args.seed,
        "selected": limit,
        "augmented": len(augmented),
        "background_pool": len(backgrounds),
        "manifest_path": manifest_path.relative_to(_BACKEND_DIR).as_posix(),
        "tracks": augmented,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"[DONE] augmented={len(augmented)} report={args.report} "
        f"manifest={manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
