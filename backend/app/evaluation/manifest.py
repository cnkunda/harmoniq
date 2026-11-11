"""Validated evaluation manifest for Commit 1 / W0.

A manifest is a committed, deterministic list of tracks. Audio and
annotation files are referenced by paths relative to ``data_root`` so the
same manifest works on a laptop, in CI, and on a GPU host.

Paths are resolved in this order:

1. absolute paths are used as-is;
2. relative to ``data_root`` (when present);
3. relative to the manifest file's directory;
4. relative to the current working directory.

If none exists, ``ManifestError`` is raised. Missing files are never
silently skipped during an evaluation run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RecordingType = Literal["studio", "live", "home", "ood", "synthetic", "unknown"]
SplitName = Literal["train", "val", "test"]
VerdictLabel = Literal["pass", "warn", "fail"]

#: Annotation formats understood by :mod:`app.evaluation.ground_truth`.
GroundTruthFormat = Literal[
    "guitarset_jams",
    "egset12_jams",
    "guitar_techs_midi",
    "chord_timeline",
    "midi",
    "notes_json",
    "none",
]


class ManifestError(ValueError):
    """Raised when a manifest is invalid or a referenced file is missing."""


class TrackSpec(BaseModel):
    """One evaluation track.

    ``audio_path`` is always required. ``gt_path`` carries note-level
    ground truth (JAMS/MIDI/JSON); ``chord_gt_path`` carries the chord
    timeline. A track may have either or both, but at least one.

    Qualitative tracks (live/home/OOD recordings without annotations) set
    ``qualitative=True`` and ``gt_format="none"``. They are evaluated for
    completion, runtime, and produced output, but not scored.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Stable unique track id")
    audio_path: str = Field(..., min_length=1)
    gt_format: GroundTruthFormat = "none"
    gt_path: str | None = None
    chord_gt_path: str | None = None
    source: str = Field(..., min_length=1, description="Dataset/source name")
    recording_type: RecordingType = "unknown"
    split: SplitName = "test"
    instrument_count: int = Field(default=1, ge=1, le=16)
    instruments: list[int] = Field(
        default_factory=lambda: [24],
        description="General MIDI programs expected in this track",
    )
    tuning: str = "standard"
    capo: int = Field(default=0, ge=0, le=12)
    stratum: str | None = None
    expected_verdict: VerdictLabel | None = None
    expects_notes: bool = True
    qualitative: bool = Field(
        default=False,
        description="Evaluate completion/runtime only; no ground truth or verdict",
    )
    notes: str | None = None

    @model_validator(mode="after")
    def _require_ground_truth(self) -> "TrackSpec":
        if self.qualitative:
            if self.gt_format != "none":
                raise ValueError(
                    f"track {self.id!r}: qualitative tracks must use gt_format='none'"
                )
            if self.gt_path or self.chord_gt_path:
                raise ValueError(
                    f"track {self.id!r}: qualitative tracks must not set ground truth paths"
                )
            if self.expected_verdict is not None:
                raise ValueError(
                    f"track {self.id!r}: qualitative tracks cannot have an expected verdict"
                )
            return self

        if self.gt_format == "none" and not self.chord_gt_path:
            raise ValueError(
                f"track {self.id!r}: gt_format='none' requires chord_gt_path"
            )
        if self.gt_format not in ("none", "chord_timeline") and not self.gt_path:
            raise ValueError(
                f"track {self.id!r}: gt_format={self.gt_format!r} requires gt_path"
            )
        if self.gt_format == "chord_timeline" and not self.chord_gt_path:
            raise ValueError(
                f"track {self.id!r}: chord_timeline requires chord_gt_path"
            )
        return self


class EvalManifest(BaseModel):
    """A versioned evaluation manifest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    manifest_id: str = Field(..., min_length=1)
    description: str | None = None
    data_root: str | None = Field(
        default=None,
        description="Base directory for relative track paths",
    )
    tracks: list[TrackSpec] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_track_ids(self) -> "EvalManifest":
        seen: set[str] = set()
        duplicates: list[str] = []
        for track in self.tracks:
            if track.id in seen:
                duplicates.append(track.id)
            seen.add(track.id)
        if duplicates:
            raise ValueError(
                "duplicate track ids: " + ", ".join(sorted(set(duplicates)))
            )
        return self


def load_manifest(path: Path | str) -> EvalManifest:
    """Load and validate a manifest JSON file.

    Raises:
        ManifestError: file missing, invalid JSON, or schema violation.
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError(f"manifest not found: {manifest_path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"manifest is not valid JSON: {manifest_path}: {exc}"
        ) from exc
    try:
        return EvalManifest.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        raise ManifestError(
            f"manifest schema error in {manifest_path}: {exc}"
        ) from exc


def resolve_manifest_path(
    path: str | Path,
    *,
    manifest_path: Path | str,
    data_root: str | Path | None = None,
) -> Path:
    """Resolve a track path against the manifest/data-root locations.

    Raises:
        ManifestError: the path cannot be resolved to an existing file.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        if candidate.is_file():
            return candidate
        raise ManifestError(f"file not found: {candidate}")

    manifest_dir = Path(manifest_path).resolve().parent
    roots: list[Path] = []
    if data_root is not None:
        root = Path(data_root)
        if not root.is_absolute():
            root = (manifest_dir / root).resolve()
        roots.append(root)
    roots.append(manifest_dir)
    roots.append(Path.cwd())

    tried: list[Path] = []
    for root in roots:
        resolved = (root / candidate).resolve()
        tried.append(resolved)
        if resolved.is_file():
            return resolved

    tried_text = "\n  ".join(str(item) for item in tried)
    raise ManifestError(
        f"file not found for {path!r}; tried:\n  {tried_text}"
    )


def resolve_track_paths(
    manifest: EvalManifest,
    track: TrackSpec,
    *,
    manifest_path: Path | str,
    data_root_override: str | Path | None = None,
) -> tuple[Path, Path | None, Path | None]:
    """Resolve audio, note ground truth, and chord ground truth for a track."""
    data_root = data_root_override if data_root_override is not None else manifest.data_root
    audio = resolve_manifest_path(
        track.audio_path, manifest_path=manifest_path, data_root=data_root
    )
    gt = (
        resolve_manifest_path(
            track.gt_path, manifest_path=manifest_path, data_root=data_root
        )
        if track.gt_path
        else None
    )
    chord_gt = (
        resolve_manifest_path(
            track.chord_gt_path, manifest_path=manifest_path, data_root=data_root
        )
        if track.chord_gt_path
        else None
    )
    return audio, gt, chord_gt
