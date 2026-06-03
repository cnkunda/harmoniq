"""Demucs htdemucs_6s stem separation and routing hints (commit 78)."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import soundfile as sf

from app.audio_mix import wav_rms as _wav_rms
from app.pipeline_proof import DEMUCS_MODEL, run_demucs_htdemucs_6s

STEM_KEYS: tuple[str, ...] = ("guitar", "bass", "drums", "vocals", "piano", "other")

logger = logging.getLogger("harmoniq.demucs_engine")
logger.setLevel(logging.INFO)


class DemucsEngineError(RuntimeError):
    """Raised when Demucs fails or required stems are missing."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _rel_to_backend(path: Path) -> str:
    return path.resolve().relative_to(_backend_root().resolve()).as_posix()


def _should_skip_demucs() -> bool:
    return os.getenv("HARMONIQ_SKIP_DEMUCS", "").strip() == "1" or bool(os.getenv("PYTEST_CURRENT_TEST"))


def _find_stem_file(stems_track_dir: Path, stem_name: str) -> Path:
    matches = list(stems_track_dir.glob(f"**/{stem_name}.wav"))
    if not matches:
        raise DemucsEngineError(f"Missing stem {stem_name}.wav in Demucs output.")
    matches.sort(key=lambda p: len(p.parts))
    return matches[0]


def _write_placeholder_stems(song_wav_path: Path, stems_dir: Path) -> dict[str, str]:
    stems_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for stem in STEM_KEYS:
        out = stems_dir / f"{stem}.wav"
        shutil.copyfile(song_wav_path, out)
        mapping[stem] = _rel_to_backend(out)
    return mapping


def separate_with_demucs(song_wav_path: Path, job_dir: Path) -> dict[str, str]:
    """Run `htdemucs_6s` and return backend-relative stem paths."""
    if not song_wav_path.is_file():
        raise DemucsEngineError(f"Input WAV missing: {song_wav_path}")
    stems_dir = job_dir / "stems"
    if _should_skip_demucs():
        return _write_placeholder_stems(song_wav_path, stems_dir)

    demucs_out = job_dir / "_demucs_prepare"
    try:
        track_dir = run_demucs_htdemucs_6s(song_wav_path, demucs_out, model=DEMUCS_MODEL)
        stems_dir.mkdir(parents=True, exist_ok=True)
        out: dict[str, str] = {}
        for stem in STEM_KEYS:
            src = _find_stem_file(track_dir, stem)
            dst = stems_dir / f"{stem}.wav"
            shutil.copyfile(src, dst)
            out[stem] = _rel_to_backend(dst)
        return out
    except Exception as exc:
        raise DemucsEngineError(f"Demucs separation failed: {exc}") from exc
    finally:
        shutil.rmtree(demucs_out, ignore_errors=True)


def build_stem_routing_hints(
    stem_abs_paths: dict[str, Path],
    *,
    stem_classification: "object | None" = None,
) -> dict[str, object]:
    """Provide deterministic routing order for commit 79 handoff.

    Pre-calculates RMS values once to minimize disk I/O.
    Raises DemucsEngineError if all stems are silent.

    Commit 111: accepts an optional ``stem_classification`` (a
    ``StemClassification`` from ``app.stem_quality``) and, when present,
    demotes the guitar stem in the melodic preference order if it is
    flagged as near-silent or buried in the mix. Returns a
    ``fallback_reason`` string in that case so downstream logs can
    surface the demotion.
    """
    # Pre-calculate RMS for all stems to minimize disk I/O
    rms_cache: dict[str, float] = {}
    for stem in STEM_KEYS:
        p = stem_abs_paths.get(stem)
        rms_cache[stem] = _wav_rms(p) if p is not None and p.is_file() else 0.0

    # Sort fallback candidates by RMS (loudest first)
    fallback_candidates = [s for s in STEM_KEYS if s not in {"guitar", "vocals"}]
    fallback_candidates.sort(key=lambda name: rms_cache.get(name, 0.0), reverse=True)
    melodic_preference_order = ["guitar", "vocals", *fallback_candidates]

    # Commit 111: Stem quality flag influence on routing.
    # If guitar is flagged as near-silent / buried / unusable, move it to
    # the end of the preference order so other candidates are tried first.
    fallback_reason: str | None = None
    classification_flags: tuple[str, ...] = ()
    guitar_usable = True
    if stem_classification is not None:
        classification_flags = tuple(getattr(stem_classification, "flags", ()) or ())
        if getattr(stem_classification, "guitar_stem_usable", True) is False:
            guitar_usable = False
        elif any(f in classification_flags for f in ("guitar_near_silent", "guitar_buried_in_mix")):
            guitar_usable = False

    if not guitar_usable:
        triggering_flag = next(
            (f for f in classification_flags if f in ("guitar_near_silent", "guitar_buried_in_mix")),
            "guitar_stem_usable_false",
        )
        fallback_reason = triggering_flag
        logger.info(
            "build_stem_routing_hints: guitar demoted, flags=%s, preference=%s",
            triggering_flag,
            melodic_preference_order,
        )
        if "guitar" in melodic_preference_order:
            melodic_preference_order.remove("guitar")
        melodic_preference_order.append("guitar")

    # Select the first stem with non-zero audio
    selected: str | None = None
    for stem in melodic_preference_order:
        if rms_cache.get(stem, 0.0) > 0.0:
            selected = stem
            break

    # All stems are silent - raise an error instead of silently defaulting
    if selected is None:
        raise DemucsEngineError(
            "No stems contain detectable audio. All stems are silent or missing."
        )

    return {
        "chord_mix_stems": ["bass", "other"],
        "melodic_preference_order": melodic_preference_order,
        "selected_melodic_stem": selected,
        "fallback_reason": fallback_reason,
    }
