"""Validated W1 dataset manifest.

A W1 track records where the audio came from, what licence applies, which
label channels are available (chord / solo), and whether the labels are
human, weak, teacher-generated, or absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.manifest import resolve_manifest_path

LabelStatus = Literal["human", "weak", "teacher", "none"]
LabelChannel = Literal["chord", "solo"]
RecordingType = Literal["studio", "live", "home", "ood", "synthetic", "unknown"]


class W1Track(BaseModel):
    """One real-audio track in the W1 data engine."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    audio_path: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    licence_id: str = Field(..., min_length=1)
    split: Literal["train", "val", "test"]
    label_status: LabelStatus
    label_channels: list[LabelChannel] = Field(..., min_length=1)
    chord_label_path: str | None = None
    note_label_path: str | None = None
    category: str | None = None
    recording_type: RecordingType = "unknown"
    instrument_count: int = Field(default=1, ge=1, le=16)
    notes: str | None = None

    @model_validator(mode="after")
    def _labels_are_consistent(self) -> "W1Track":
        has_labels = bool(self.chord_label_path or self.note_label_path)
        if self.label_status in ("human", "weak", "teacher") and not has_labels:
            raise ValueError(
                f"track {self.id!r}: label_status={self.label_status!r} "
                "requires chord_label_path or note_label_path"
            )
        if self.label_status == "none" and has_labels:
            raise ValueError(
                f"track {self.id!r}: label_status='none' must not set label paths"
            )
        return self


class W1Manifest(BaseModel):
    """Versioned manifest for the W1 data engine."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    manifest_id: str = Field(..., min_length=1)
    description: str | None = None
    data_root: str | None = None
    tracks: list[W1Track] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "W1Manifest":
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


def load_w1_manifest(path: Path | str) -> W1Manifest:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ValueError(f"W1 manifest not found: {manifest_path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"W1 manifest is not valid JSON: {manifest_path}: {exc}") from exc
    try:
        return W1Manifest.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"W1 manifest schema error in {manifest_path}: {exc}") from exc


def resolve_w1_audio(
    manifest: W1Manifest,
    track: W1Track,
    *,
    manifest_path: Path | str,
) -> Path:
    return resolve_manifest_path(
        track.audio_path,
        manifest_path=manifest_path,
        data_root=manifest.data_root,
    )


def resolve_w1_chord_label(
    manifest: W1Manifest,
    track: W1Track,
    *,
    manifest_path: Path | str,
) -> Path | None:
    if not track.chord_label_path:
        return None
    return resolve_manifest_path(
        track.chord_label_path,
        manifest_path=manifest_path,
        data_root=manifest.data_root,
    )


def resolve_w1_note_label(
    manifest: W1Manifest,
    track: W1Track,
    *,
    manifest_path: Path | str,
) -> Path | None:
    if not track.note_label_path:
        return None
    return resolve_manifest_path(
        track.note_label_path,
        manifest_path=manifest_path,
        data_root=manifest.data_root,
    )
