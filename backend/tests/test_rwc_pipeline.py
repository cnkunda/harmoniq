"""Tests for Commit 173: RWC-P download/parse/CQT pipeline."""

from __future__ import annotations

import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chord_vocab import CHORD_TO_IDX
from scripts import download_rwc
from scripts.build_chord_tflite import load_dataset_dir, load_datasets
from scripts.download_rwc import (
    _extract_annotations,
    _extract_audio,
    license_acknowledged,
    main as download_main,
)
from scripts.extract_rwc_cqt import (
    FEATURE_DIM,
    N_CHORD_IDX,
    WINDOW,
    _frame_labels_from_timeline,
    main as extract_main,
    process_song,
)
from scripts.parse_rwc import (
    _normalize_rwc_label,
    parse_all,
    parse_rwc_csv,
    save_timelines,
)


# ---------------------------------------------------------------------------
# parse_rwc unit tests
# ---------------------------------------------------------------------------

class TestNormalizeRwcLabel:
    def test_flat_minor(self):
        assert _normalize_rwc_label("Ab:min") == "G#:min"

    def test_maj6_alias(self):
        assert _normalize_rwc_label("Gb:maj6") == "F#:6"

    def test_bass_note_removed(self):
        assert _normalize_rwc_label("Eb:maj/3") == "D#:maj"

    def test_parenthesized_removed(self):
        assert _normalize_rwc_label("Bb:maj(*3)") == "A#:maj"

    def test_cb_root_alias(self):
        assert _normalize_rwc_label("Cb:maj7") == "B:maj7"

    def test_fb_root_alias(self):
        assert _normalize_rwc_label("Fb:min(*b3,*5)") == "E:min"

    def test_hdim7_mapped(self):
        assert _normalize_rwc_label("E:hdim7") == "E:dim7"

    def test_no_chord(self):
        assert _normalize_rwc_label("N") is None
        assert _normalize_rwc_label("") is None

    def test_all_outputs_in_vocab(self):
        for label in ("Ab:min", "Gb:maj6", "Eb:maj/3", "Cb:maj7", "Fb:min"):
            assert _normalize_rwc_label(label) in CHORD_TO_IDX


class TestParseRwcCsv:
    def test_parses_valid_rows_and_skips_n(self, tmp_path):
        csv_path = tmp_path / "RWC_P001.csv"
        csv_path.write_text(
            "t_start;t_end;chord\n"
            "0.0;1.0;N\n"
            "1.0;2.0;Ab:min\n"
            "2.0;3.0;Gb:maj6\n"
            "3.0;4.0;Cb:maj\n"
        )
        timeline, skipped = parse_rwc_csv(csv_path)

        assert [entry["chord"] for entry in timeline] == ["G#:min", "F#:6", "B:maj"]
        assert timeline[0]["start"] == 1.0
        assert timeline[0]["end"] == 2.0
        assert skipped == {}

    def test_skips_bad_duration(self, tmp_path):
        csv_path = tmp_path / "RWC_P002.csv"
        csv_path.write_text(
            "t_start;t_end;chord\n"
            "0.0;2.0;C:maj\n"
            "3.0;2.0;G:7\n"
        )
        timeline, skipped = parse_rwc_csv(csv_path)

        assert len(timeline) == 1
        assert skipped == {}

    def test_missing_columns(self, tmp_path):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("foo;bar;baz\n1;2;3\n")
        timeline, skipped = parse_rwc_csv(csv_path)

        assert timeline == []
        assert skipped == {}

    def test_parse_all(self, tmp_path):
        for name, chord in (("RWC_P001", "C:maj"), ("RWC_P002", "A:min")):
            (tmp_path / f"{name}.csv").write_text(
                f"t_start;t_end;chord\n0.0;1.0;{chord}\n"
            )
        songs, skipped = parse_all(tmp_path)

        assert set(songs) == {"RWC_P001", "RWC_P002"}
        assert skipped == {}

    def test_save_timelines(self, tmp_path):
        songs = {"RWC_P001": [{"start": 0.0, "end": 1.0, "chord": "C:maj"}]}
        out_dir = tmp_path / "timelines"
        save_timelines(songs, out_dir)

        saved = json.loads((out_dir / "RWC_P001.json").read_text())
        assert saved == [{"start": 0.0, "end": 1.0, "chord": "C:maj"}]


# ---------------------------------------------------------------------------
# extract_rwc_cqt tests
# ---------------------------------------------------------------------------

class TestFrameLabels:
    def test_chord_and_gap(self):
        timeline = [{"start": 0.0, "end": 0.3, "chord": "C:maj"}]
        labels = _frame_labels_from_timeline(timeline, 10)

        assert labels[0] == CHORD_TO_IDX["C:maj"]
        assert labels[4] == N_CHORD_IDX

    def test_forward_bias_at_boundary(self):
        timeline = [
            {"start": 0.0, "end": 0.5, "chord": "C:maj"},
            {"start": 0.5, "end": 1.0, "chord": "G:7"},
        ]
        labels = _frame_labels_from_timeline(timeline, 10)

        assert labels[5] == CHORD_TO_IDX["G:7"]


class TestProcessSong:
    def _write_audio(self, path: Path) -> None:
        import soundfile as sf

        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration))
        y = np.sin(2 * np.pi * 440 * t) * 0.1
        sf.write(str(path), y, sr)

    def test_writes_npz_without_loss_weight(self, tmp_path):
        audio_path = tmp_path / "RWC_P001.wav"
        self._write_audio(audio_path)

        timeline_path = tmp_path / "timelines" / "RWC_P001.json"
        timeline_path.parent.mkdir()
        timeline_path.write_text(json.dumps([
            {"start": 0.0, "end": 1.5, "chord": "C:maj"},
        ]))
        cqt_dir = tmp_path / "cqt"

        result = process_song(audio_path, timeline_path, cqt_dir)

        assert result is not None
        assert result["status"] == "processed"
        data = np.load(cqt_dir / "RWC_P001.npz")
        assert data["features"].shape[1:] == (WINDOW, FEATURE_DIM)
        assert len(data["labels"]) == len(data["features"])
        assert str(data["split"]) == "train"
        assert str(data["track_id"]) == "RWC_P001"
        assert "loss_weight" not in data

    def test_caching_no_force(self, tmp_path):
        audio_path = tmp_path / "RWC_P001.wav"
        self._write_audio(audio_path)

        timeline_path = tmp_path / "timelines" / "RWC_P001.json"
        timeline_path.parent.mkdir()
        timeline_path.write_text(json.dumps([
            {"start": 0.0, "end": 1.5, "chord": "C:maj"},
        ]))
        cqt_dir = tmp_path / "cqt"

        process_song(audio_path, timeline_path, cqt_dir)
        second = process_song(audio_path, timeline_path, cqt_dir)

        assert second is not None
        assert second["status"] == "cached"

    def test_missing_timeline(self, tmp_path):
        audio_path = tmp_path / "RWC_P001.wav"
        self._write_audio(audio_path)

        result = process_song(audio_path, tmp_path / "missing.json", tmp_path / "cqt")

        assert result is None

    def test_extract_main_clean_skip(self, tmp_path, capsys):
        extract_main(tmp_path)
        captured = capsys.readouterr()

        assert "Required directories not found" in captured.out


# ---------------------------------------------------------------------------
# download_rwc tests
# ---------------------------------------------------------------------------

class TestDownloader:
    def test_license_acknowledged(self, monkeypatch):
        monkeypatch.setenv("HARMONIQ_RWC_LICENSE_ACK", "1")
        assert license_acknowledged()

        monkeypatch.setenv("HARMONIQ_RWC_LICENSE_ACK", "0")
        assert not license_acknowledged()

    def test_clean_skip_without_license(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("HARMONIQ_RWC_LICENSE_ACK", raising=False)

        def _fail(*args, **kwargs):
            raise AssertionError("network must not be used without license ack")

        monkeypatch.setattr(download_rwc.requests, "get", _fail)
        download_main(tmp_path)

        captured = capsys.readouterr()
        assert "HARMONIQ_RWC_LICENSE_ACK" in captured.out
        assert not (tmp_path / "rwc").exists()

    def test_extract_annotations(self, tmp_path):
        tar_path = tmp_path / "annotations.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            for name, payload in (
                ("rwc-annotations-main/01_annotations_preprocessed/chords/RWC-P/RWC_P001.csv",
                 b"t_start;t_end;chord\n0;1;C:maj\n"),
                ("rwc-annotations-main/01_annotations_preprocessed/chords/RWC-P/RWC_P002.csv",
                 b"t_start;t_end;chord\n0;1;A:min\n"),
                ("rwc-annotations-main/metadata.csv", b"RWCID;CollID\nRWC_P001;P\n"),
                ("rwc-annotations-main/README.md", b"# ignored\n"),
            ):
                data = payload
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))

        raw_dir = tmp_path / "raw"
        count = _extract_annotations(tar_path, raw_dir)

        assert count == 2
        assert (raw_dir / "chords" / "RWC-P" / "RWC_P001.csv").exists()
        assert (raw_dir / "metadata.csv").exists()
        assert not (raw_dir / "README.md").exists()

    def test_extract_audio(self, tmp_path):
        zip_path = tmp_path / "RWC-P.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("RWC-P/", b"")
            zf.writestr("RWC-P/RWC_P001.wav", b"RIFF")

        raw_dir = tmp_path / "raw"
        count = _extract_audio(zip_path, raw_dir)

        assert count == 1
        assert (raw_dir / "audio" / "RWC-P" / "RWC_P001.wav").exists()

    def test_annotations_only_skips_audio(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HARMONIQ_RWC_LICENSE_ACK", "1")

        def _fake_download(url, dest, desc, expected_size=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake")
            return True

        monkeypatch.setattr(download_rwc, "_download", _fake_download)
        monkeypatch.setattr(download_rwc, "_extract_annotations",
                            lambda tar_path, raw_dir: 100)

        download_main(tmp_path, download_audio=False)

        captured = capsys.readouterr()
        assert "RWC audio not requested" in captured.out
        assert not (tmp_path / "rwc" / "raw" / "audio").exists()


# ---------------------------------------------------------------------------
# Training integration
# ---------------------------------------------------------------------------

class TestLossWeightPlumbing:
    def _write_npz(self, cqt_dir: Path) -> None:
        cqt_dir.mkdir(parents=True)
        np.savez_compressed(
            cqt_dir / "RWC_P001.npz",
            features=np.zeros((4, WINDOW, FEATURE_DIM), dtype=np.float32),
            labels=np.array([0, 1, 2, 3], dtype=np.int32),
            track_id="RWC_P001",
            split="train",
        )

    def test_npz_without_loss_weight_uses_cli_default(self, tmp_path):
        rwc_dir = tmp_path / "rwc"
        self._write_npz(rwc_dir / "processed" / "cqt")

        X, y, loss_weight, recording_ids = load_dataset_dir(rwc_dir)
        assert loss_weight is None
        assert X.shape == (4, WINDOW, FEATURE_DIM)
        assert set(recording_ids) == {"rwc_RWC_P001"}

        features, labels, weights, rec_ids = load_datasets([(rwc_dir, "RWC-P", 0.5)])
        assert len(features) == 1
        assert len(labels) == 1
        assert np.all(weights[0] == 0.5)
        assert set(rec_ids[0]) == {"rwc_RWC_P001"}
