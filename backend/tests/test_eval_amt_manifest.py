"""W0 manifest validation/resolution tests."""

from __future__ import annotations

import json

import pytest

from app.evaluation.manifest import (
    EvalManifest,
    ManifestError,
    TrackSpec,
    load_manifest,
    resolve_manifest_path,
    resolve_track_paths,
)


def _track(**overrides) -> dict:
    payload = {
        "id": "t1",
        "audio_path": "audio.wav",
        "gt_format": "notes_json",
        "gt_path": "notes.json",
        "source": "unit",
        "split": "test",
        "instrument_count": 1,
    }
    payload.update(overrides)
    return payload


def _write_manifest(path, tracks) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_id": "unit-manifest",
                "data_root": ".",
                "tracks": tracks,
            }
        ),
        encoding="utf-8",
    )


class TestManifestValidation:
    def test_loads_valid_manifest(self, tmp_path):
        (tmp_path / "audio.wav").write_bytes(b"audio")
        (tmp_path / "notes.json").write_text("[]", encoding="utf-8")
        path = tmp_path / "manifest.json"
        _write_manifest(path, [_track()])
        manifest = load_manifest(path)
        assert manifest.manifest_id == "unit-manifest"
        assert manifest.tracks[0].id == "t1"

    def test_rejects_duplicate_ids(self, tmp_path):
        path = tmp_path / "manifest.json"
        _write_manifest(path, [_track(), _track()])
        with pytest.raises(ManifestError, match="duplicate track ids"):
            load_manifest(path)

    def test_rejects_unknown_fields(self, tmp_path):
        path = tmp_path / "manifest.json"
        _write_manifest(path, [_track(unexpected=True)])
        with pytest.raises(ManifestError, match="schema error"):
            load_manifest(path)

    def test_rejects_missing_note_gt_path(self, tmp_path):
        with pytest.raises(ValueError, match="requires gt_path"):
            TrackSpec(
                id="t1",
                audio_path="audio.wav",
                gt_format="notes_json",
                source="unit",
            )

    def test_chord_only_track_requires_timeline(self, tmp_path):
        with pytest.raises(ValueError, match="chord_timeline requires chord_gt_path"):
            TrackSpec(
                id="t1",
                audio_path="audio.wav",
                gt_format="chord_timeline",
                source="unit",
            )

    def test_missing_file_raises(self, tmp_path):
        path = tmp_path / "manifest.json"
        _write_manifest(path, [_track()])
        manifest = load_manifest(path)
        with pytest.raises(ManifestError, match="file not found"):
            resolve_track_paths(manifest, manifest.tracks[0], manifest_path=path)

    def test_resolve_audio_and_gt(self, tmp_path):
        audio = tmp_path / "audio.wav"
        gt = tmp_path / "notes.json"
        audio.write_bytes(b"audio")
        gt.write_text("[]", encoding="utf-8")
        path = tmp_path / "manifest.json"
        _write_manifest(path, [_track()])
        manifest = load_manifest(path)
        resolved_audio, resolved_gt, resolved_chord = resolve_track_paths(
            manifest, manifest.tracks[0], manifest_path=path
        )
        assert resolved_audio == audio.resolve()
        assert resolved_gt == gt.resolve()
        assert resolved_chord is None

    def test_absolute_path_is_used(self, tmp_path):
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"audio")
        resolved = resolve_manifest_path(
            str(audio), manifest_path=tmp_path / "manifest.json"
        )
        assert resolved == audio.resolve()

    def test_data_root_override(self, tmp_path):
        root = tmp_path / "data"
        root.mkdir()
        (root / "audio.wav").write_bytes(b"audio")
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "manifest_id": "m",
                    "tracks": [
                        {
                            "id": "t1",
                            "audio_path": "audio.wav",
                            "gt_format": "chord_timeline",
                            "chord_gt_path": "audio.wav",
                            "source": "unit",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        manifest = load_manifest(manifest_path)
        resolved, _, _ = resolve_track_paths(
            manifest,
            manifest.tracks[0],
            manifest_path=manifest_path,
            data_root_override=root,
        )
        assert resolved == (root / "audio.wav").resolve()


class TestQualitativeManifest:
    def test_qualitative_track_accepts_no_ground_truth(self):
        spec = TrackSpec(
            id="external:ood:kora",
            audio_path="audio.wav",
            gt_format="none",
            source="external",
            qualitative=True,
        )
        assert spec.qualitative is True
        assert spec.gt_path is None
        assert spec.chord_gt_path is None

    def test_qualitative_track_rejects_ground_truth_paths(self):
        with pytest.raises(ValueError, match="must not set ground truth paths"):
            TrackSpec(
                id="external:ood:kora",
                audio_path="audio.wav",
                gt_format="none",
                gt_path="notes.json",
                source="external",
                qualitative=True,
            )

    def test_qualitative_track_rejects_expected_verdict(self):
        with pytest.raises(ValueError, match="cannot have an expected verdict"):
            TrackSpec(
                id="external:ood:kora",
                audio_path="audio.wav",
                gt_format="none",
                source="external",
                qualitative=True,
                expected_verdict="pass",
            )
