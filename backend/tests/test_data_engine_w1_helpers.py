"""W1 augmentation and pseudo-label helper tests."""

from __future__ import annotations

import json

import numpy as np
import pytest


class TestAugmentationMix:
    def _write_tone(self, path, frequency: float, seconds: float = 1.0):
        import soundfile as sf

        sr = 44100
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        audio = (0.2 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
        sf.write(str(path), audio, sr)
        return path

    def test_mix_preserves_guitar_length_and_is_finite(self, tmp_path):
        from scripts.augment_w1 import _mix_audio

        guitar = self._write_tone(tmp_path / "guitar.wav", 220.0)
        background = self._write_tone(tmp_path / "background.wav", 440.0, 0.5)
        mix = _mix_audio(guitar, background, gain=0.15)
        assert mix.ndim == 1
        assert len(mix) == 44100
        assert np.all(np.isfinite(mix))
        assert float(np.max(np.abs(mix))) <= 1.0

    def test_background_pick_is_deterministic(self):
        from app.data_engine.manifest import W1Track
        from scripts.augment_w1 import _pick_background

        guitar = W1Track(
            id="g",
            audio_path="g.wav",
            source="guitarset",
            licence_id="CC-BY-4.0",
            split="train",
            label_status="none",
            label_channels=["chord"],
        )
        backgrounds = [
            W1Track(
                id=f"b{index}",
                audio_path=f"b{index}.wav",
                source="rwc_p",
                licence_id="CC-BY-NC-4.0",
                split="train",
                label_status="none",
                label_channels=["chord"],
            )
            for index in range(5)
        ]
        first = _pick_background(guitar, backgrounds, "seed")
        second = _pick_background(guitar, backgrounds, "seed")
        assert first.id == second.id


class TestPseudoLabelHelpers:
    def test_summarize_counts(self):
        from scripts.pseudo_label_w1 import _summarize

        summary = _summarize(
            [
                {"id": "a", "source": "s", "status": "labeled", "windows_total": 10, "windows_kept": 4},
                {"id": "b", "source": "s", "status": "skipped", "reason": "x", "windows_total": 5, "windows_kept": 0},
            ]
        )
        assert summary["totals"]["selected"] == 2
        assert summary["totals"]["labeled"] == 1
        assert summary["totals"]["skipped"] == 1
        assert summary["totals"]["retention"] == pytest.approx(4 / 15, abs=1e-6)
        assert summary["sources"]["s"]["labeled"] == 1

    def test_write_npz_roundtrips(self, tmp_path):
        from app.data_engine.manifest import W1Track
        from scripts.pseudo_label_w1 import _write_npz

        track = W1Track(
            id="unit:track",
            audio_path="audio.wav",
            source="unit",
            licence_id="CC-BY-4.0",
            split="train",
            label_status="none",
            label_channels=["chord"],
        )
        features = np.zeros((2, 128, 144), dtype=np.float32)
        labels = np.array([1, 2], dtype=np.int32)
        confidence = np.array([0.9, 0.8], dtype=np.float32)
        path = _write_npz(
            tmp_path,
            track,
            features,
            labels,
            confidence,
            teacher="mt3",
            loss_weight=0.5,
            split_label="train",
        )
        data = np.load(path)
        assert data["features"].shape == (2, 128, 144)
        assert data["labels"].tolist() == [1, 2]
        assert bytes(data["split"]).decode() == "train"
        assert bytes(data["source"]).decode() == "pseudo"
        assert bytes(data["teacher"]).decode() == "mt3"


class TestResumableSelection:
    def _manifest(self):
        from app.data_engine.manifest import W1Manifest, W1Track

        return W1Manifest(
            manifest_id="unit",
            tracks=[
                W1Track(
                    id=f"t{index}",
                    audio_path=f"t{index}.wav",
                    source="unit",
                    licence_id="CC-BY-4.0",
                    split="train",
                    label_status="none",
                    label_channels=["chord"],
                )
                for index in range(1, 5)
            ],
        )

    def _args(self, **overrides):
        from types import SimpleNamespace

        payload = {
            "label_status": [],
            "include_weak": False,
            "all_splits": False,
            "split": "train",
            "source": [],
            "category": [],
            "track": [],
            "limit": 2,
            "offset": 1,
        }
        payload.update(overrides)
        return SimpleNamespace(**payload)

    def test_offset_applies_before_limit(self):
        from scripts.pseudo_label_w1 import _select_tracks

        tracks = _select_tracks(self._manifest(), self._args())
        assert [track.id for track in tracks] == ["t2", "t3"]

    def test_negative_offset_fails(self):
        from scripts.pseudo_label_w1 import _select_tracks

        with pytest.raises(SystemExit, match="--offset"):
            _select_tracks(self._manifest(), self._args(offset=-1))

    def test_existing_record_roundtrip(self, tmp_path):
        from pathlib import Path

        import numpy as np

        from scripts.pseudo_label_w1 import _existing_record, _write_npz

        track = self._manifest().tracks[0]
        features = np.zeros((3, 128, 144), dtype=np.float32)
        labels = np.array([1, 2, 3], dtype=np.int32)
        confidence = np.array([0.9, 0.8, 0.7], dtype=np.float32)
        _write_npz(
            tmp_path,
            track,
            features,
            labels,
            confidence,
            teacher="mt3",
            loss_weight=0.5,
            split_label="train",
            windows_total=5,
        )
        label_path = tmp_path / "labels" / f"{track.id}.json"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text(json.dumps({"windows_total": 5}), encoding="utf-8")

        record = _existing_record(Path(tmp_path), track)
        assert record is not None
        assert record["status"] == "labeled"
        assert record["reason"] == "existing"
        assert record["windows_total"] == 5
        assert record["windows_kept"] == 3

    def test_existing_record_requires_both_files(self, tmp_path):
        from scripts.pseudo_label_w1 import _existing_record

        track = self._manifest().tracks[0]
        assert _existing_record(tmp_path, track) is None


class TestMergeReports:
    def test_dedupes_and_prefers_actual_run(self):
        from scripts.merge_w1_reports import merge_reports

        merged = merge_reports(
            [
                {
                    "manifest_id": "m",
                    "teacher": "mt3",
                    "config": {},
                    "tracks": [
                        {
                            "id": "a",
                            "source": "s",
                            "status": "labeled",
                            "reason": "existing",
                            "windows_kept": 3,
                            "windows_total": 3,
                        },
                        {
                            "id": "b",
                            "source": "s",
                            "status": "skipped",
                            "reason": "no_confident_windows",
                            "windows_kept": 0,
                            "windows_total": 2,
                        },
                    ],
                },
                {
                    "manifest_id": "m",
                    "teacher": "mt3",
                    "config": {},
                    "tracks": [
                        {
                            "id": "a",
                            "source": "s",
                            "status": "labeled",
                            "windows_kept": 5,
                            "windows_total": 5,
                        }
                    ],
                },
            ]
        )
        assert merged["totals"]["selected"] == 2
        assert merged["totals"]["labeled"] == 1
        assert merged["totals"]["skipped"] == 1
        by_id = {record["id"]: record for record in merged["tracks"]}
        assert by_id["a"]["windows_kept"] == 5
        assert by_id["a"].get("reason") != "existing"
