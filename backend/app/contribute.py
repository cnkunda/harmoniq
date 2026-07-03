"""Contribution pipeline — validate, extract CQT, and store user-annotated audio.

Handles the flow from a corrected chord timeline to training-ready .npz files
stored in data/user_contributed/processed/cqt/.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path

from app.chord_vocab import CHORD_TO_IDX
from app.ingest import get_data_dir, get_job_dir
from app.lab_export import chord_timeline_to_lab
from app.schemas import ChordTimeline

logger = logging.getLogger("harmoniq.contribute")

MIN_NON_N_CHORDS = 3
MAX_DURATION_MISMATCH_RATIO = 0.10


class ContributionError(Exception):
    """Raised when a contribution fails validation."""


def _validate_contribution(
    timeline: ChordTimeline,
    audio_path: Path,
    job_id: str,
    manifest: dict,
) -> None:
    """Run all validation checks. Raises ContributionError on failure."""
    if not timeline.events:
        raise ContributionError("no_chord_timeline", "Chord timeline has no events")

    non_n = [ev for ev in timeline.events if ev.chord != "N"]
    if len(non_n) < MIN_NON_N_CHORDS:
        raise ContributionError(
            "insufficient_annotations",
            f"Need ≥{MIN_NON_N_CHORDS} non-N chords, got {len(non_n)}",
        )

    # Validate chord labels (no audio needed)
    for ev in timeline.events:
        if ev.chord not in CHORD_TO_IDX:
            raise ContributionError(
                "invalid_chord_labels",
                f"Unknown chord label: {ev.chord}",
            )

    # Check duplicate (before audio check)
    contributions = manifest.get("contributions", {})
    if job_id in contributions:
        raise ContributionError(
            "duplicate_contribution",
            f"Job {job_id} already contributed",
        )

    if not audio_path.exists():
        raise ContributionError("audio_not_found", f"Audio file not found: {audio_path}")

    # Check duration mismatch
    try:
        import librosa
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        audio_dur = len(y) / sr
        last_annot_end = max(ev.timestamp for ev in timeline.events) + 2.0
        if abs(audio_dur - last_annot_end) > last_annot_end * MAX_DURATION_MISMATCH_RATIO:
            raise ContributionError(
                "duration_mismatch",
                f"Audio ({audio_dur:.1f}s) vs annotations ({last_annot_end:.1f}s) mismatch >10%",
            )
    except ContributionError:
        raise
    except Exception as e:
        raise ContributionError("audio_load_failed", f"Could not load audio: {e}")


def _update_manifest(
    manifest_path: Path,
    job_id: str,
    contributor_id: str,
    license: str,
    track_id: str,
    windows: int,
    chord_count: int,
) -> None:
    """Append a contribution record to the manifest."""
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    contributions: dict = manifest.setdefault("contributions", {})
    contributions[job_id] = {
        "contributor_id": contributor_id,
        "license": license,
        "track_id": track_id,
        "contributed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "windows": windows,
        "chord_count": chord_count,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2))


def contribute_audio(
    job_id: str,
    timeline: ChordTimeline,
    contributor_id: str,
    license: str = "cc-by-4.0",
) -> dict:
    """Validate, extract CQT, and store user-contributed audio.

    Args:
        job_id: The analysis job ID.
        timeline: The corrected chord timeline.
        contributor_id: Anonymous contributor identifier.
        license: License string for the contribution.

    Returns:
        Dict with status, windows count, and track_id.

    Raises:
        ContributionError: If any validation check fails.
    """
    data_dir = get_data_dir()
    job_dir = get_job_dir(job_id)
    contributed_dir = data_dir / "user_contributed"
    cqt_dir = contributed_dir / "processed" / "cqt"
    manifest_path = contributed_dir / "manifest.json"

    # Load existing manifest for duplicate check
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    # Find the normalized WAV (song.wav) — fallback to original input.{ext}
    wav_path = job_dir / "song.wav"
    if not wav_path.exists():
        originals = list(job_dir.glob("input.*"))
        if originals:
            wav_path = originals[0]
        else:
            raise ContributionError("audio_not_found", f"No audio found in {job_dir}")

    # Validate
    _validate_contribution(timeline, wav_path, job_id, manifest)

    # Export .lab to temp file
    lab_content = chord_timeline_to_lab(timeline)
    track_id = f"user_{job_id}"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".lab", delete=False, prefix=f"{track_id}_",
    ) as f:
        f.write(lab_content)
        lab_path = Path(f.name)

    try:
        # Run CQT extraction
        from scripts.user_audio_pipeline import process_pair

        result = process_pair(wav_path, lab_path, cqt_dir)
        if result is None:
            raise ContributionError("extraction_failed", "CQT extraction returned no data")

        windows = result["windows"]

        # Count non-N chords
        chord_count = sum(1 for ev in timeline.events if ev.chord != "N")

        # Update manifest
        _update_manifest(
            manifest_path, job_id, contributor_id, license, track_id, windows, chord_count,
        )

        logger.info(
            "[Contribute] %s: %d windows, %d chords", track_id, windows, chord_count,
        )

        return {
            "status": "accepted",
            "windows": windows,
            "track_id": track_id,
        }

    finally:
        lab_path.unlink(missing_ok=True)
