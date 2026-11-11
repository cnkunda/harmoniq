"""W0 external recording intake tests."""

from __future__ import annotations

import json

from scripts.ingest_eval_recordings import build_external_manifest


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not-real-audio")
    return path


class TestExternalIntake:
    def test_annotated_and_qualitative_tracks(self, tmp_path):
        _touch(tmp_path / "live" / "foo.wav")
        (tmp_path / "live" / "foo.notes.json").write_text("[]", encoding="utf-8")
        _touch(tmp_path / "ood" / "bar.wav")

        manifest = build_external_manifest(tmp_path, out_dir=tmp_path)
        by_id = {track.id: track for track in manifest.tracks}

        live = by_id["external:live:foo"]
        assert live.gt_format == "notes_json"
        assert live.qualitative is False
        assert live.recording_type == "live"

        ood = by_id["external:ood:bar"]
        assert ood.gt_format == "none"
        assert ood.qualitative is True
        assert ood.recording_type == "ood"

    def test_chords_only_track(self, tmp_path):
        _touch(tmp_path / "home" / "blues.wav")
        (tmp_path / "home" / "blues.chords.json").write_text("[]", encoding="utf-8")

        manifest = build_external_manifest(tmp_path, out_dir=tmp_path)
        track = manifest.tracks[0]
        assert track.gt_format == "chord_timeline"
        assert track.chord_gt_path is not None
        assert track.qualitative is False

    def test_metadata_override(self, tmp_path):
        _touch(tmp_path / "live" / "foo.wav")
        metadata = {
            "tracks": [
                {
                    "audio": "live/foo.wav",
                    "id": "external:live:custom",
                    "recording_type": "home",
                    "instrument_count": 2,
                    "instruments": [24, 32],
                    "tuning": "drop-d",
                    "notes": "custom",
                }
            ]
        }
        (tmp_path / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        manifest = build_external_manifest(tmp_path, out_dir=tmp_path)
        track = manifest.tracks[0]
        assert track.id == "external:live:custom"
        assert track.recording_type == "home"
        assert track.instrument_count == 2
        assert track.instruments == [24, 32]
        assert track.tuning == "drop-d"

    def test_merge_into_base_manifest(self, tmp_path):
        base = tmp_path / "base.json"
        base.write_text(
            json.dumps(
                {
                    "manifest_id": "base",
                    "tracks": [
                        {
                            "id": "base:1",
                            "audio_path": "data/base.wav",
                            "gt_format": "notes_json",
                            "gt_path": "data/base.notes.json",
                            "source": "base",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        _touch(tmp_path / "live" / "foo.wav")

        manifest = build_external_manifest(
            tmp_path, merge_into=base, out_dir=tmp_path
        )
        ids = {track.id for track in manifest.tracks}
        assert ids == {"base:1", "external:live:foo"}
