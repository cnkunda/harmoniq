"""Tests for analysis correction endpoints (Commit 109/110)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analysis_store import save_corrections, load_corrections
from app import jobs as jobs_mod
from app.main import app
from app.schemas import TimeSignature

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    jobs_mod._jobs_memory.clear()
    yield
    jobs_mod._jobs_memory.clear()


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", f"./.tmp_test_data_{uuid4()}")
    yield


def _create_stub_job() -> str:
    """Insert a stub job with chord timeline and solo notes for correction tests."""
    job_id = str(uuid4())

    from app.schemas import (
        BeatGrid,
        ChordEvent,
        ChordTimeline,
        LessonJSON,
        LessonSectionStub,
        SoloNote,
        SoloNotes,
    )

    # Chord timeline with 4 beats
    chords = [
        ChordEvent(timestamp=0.0, chord="Cmaj", confidence=0.9),
        ChordEvent(timestamp=0.5, chord="Gmin", confidence=0.85),
        ChordEvent(timestamp=1.0, chord="Am7", confidence=0.8),
        ChordEvent(timestamp=1.5, chord="Fmaj7", confidence=0.75),
    ]
    ct = ChordTimeline(events=chords)

    # Solo notes
    notes = [
        SoloNote(pitch=60, start_time=0.1, duration=0.2, velocity=80),
        SoloNote(pitch=62, start_time=0.6, duration=0.15, velocity=75),
        SoloNote(pitch=64, start_time=1.1, duration=0.25, velocity=85),
    ]
    sn = SoloNotes(notes=notes)

    lesson = LessonJSON(
        job_id=job_id,
        song_title="Test Song",
        artist="Test Artist",
        key="C major",
        key_confidence=0.9,
        tempo=120.0,
        tempo_confidence=0.9,
        transcription_confidence=0.8,
        beat_grid=[0.0, 0.5, 1.0, 1.5, 2.0],
        bar_timestamps=[0.0, 2.0],
        stems={},
        lyrics_aligned=[],
        sections=[LessonSectionStub(label="Verse", confidence=0.9)],
        chord_timeline=ct,
        solo_notes=sn,
    )

    from app.analysis_store import (
        save_beat_grid,
        save_chord_timeline,
        save_lesson,
        save_solo_notes,
    )

    save_lesson(job_id, lesson)
    save_chord_timeline(job_id, ct)
    save_solo_notes(job_id, sn)
    save_beat_grid(job_id, BeatGrid(
        beats=[0.0, 0.5, 1.0, 1.5, 2.0],
        bpm=120.0,
        pulse_bpm=120.0,
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.5,
    ))

    # Also register in in-memory jobs dict
    from app.jobs import _set_job
    from app.schemas import JobStatus
    _set_job(job_id, JobStatus(status="complete", job_id=job_id))

    return job_id


# ---------------------------------------------------------------------------
# PATCH /analyze/{job_id}/chord/{beat_index}
# ---------------------------------------------------------------------------

class TestChordCorrection:
    def test_correct_chord_success(self):
        job_id = _create_stub_job()
        r = client.patch(
            f"/analyze/{job_id}/chord/0",
            json={"chord": "Dmin7", "reason": "Better voicing"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["correction_type"] == "chord"
        assert data["index"] == 0
        assert data["corrected_value"]["chord"] == "Dmin7"
        assert data["reason"] == "Better voicing"
        assert "applied_at" in data

    def test_correct_chord_updates_chord_timeline(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/1", json={"chord": "Bdim"})

        # Verify the chord timeline was updated
        from app.analysis_store import load_chord_timeline
        ct = load_chord_timeline(job_id)
        assert ct is not None
        assert ct.events[1].chord == "Bdim"

    def test_correct_chord_out_of_range(self):
        job_id = _create_stub_job()
        r = client.patch(
            f"/analyze/{job_id}/chord/99",
            json={"chord": "C"},
        )
        assert r.status_code == 400, r.text

    def test_correct_chord_nonexistent_job(self):
        r = client.patch(
            "/analyze/nonexistent/chord/0",
            json={"chord": "C"},
        )
        assert r.status_code == 404

    def test_correct_chord_persists_history(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/0", json={"chord": "Dmin"})
        client.patch(f"/analyze/{job_id}/chord/1", json={"chord": "Edim"})

        corrections = load_corrections(job_id)
        assert len(corrections) == 2
        assert corrections[0]["correction_type"] == "chord"
        assert corrections[0]["corrected_value"]["chord"] == "Dmin"
        assert corrections[1]["corrected_value"]["chord"] == "Edim"


# ---------------------------------------------------------------------------
# PATCH /analyze/{job_id}/solo-note/{note_index}
# ---------------------------------------------------------------------------

class TestSoloNoteCorrection:
    def test_correct_solo_note_pitch(self):
        job_id = _create_stub_job()
        r = client.patch(
            f"/analyze/{job_id}/solo-note/0",
            json={"pitch": 64, "reason": "Wrong fret"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["correction_type"] == "solo_note"
        assert data["index"] == 0
        assert data["corrected_value"]["pitch"] == 64

    def test_correct_solo_note_out_of_range(self):
        job_id = _create_stub_job()
        r = client.patch(
            f"/analyze/{job_id}/solo-note/99",
            json={"pitch": 60},
        )
        assert r.status_code == 400, r.text

    def test_correct_solo_note_nonexistent_job(self):
        r = client.patch(
            "/analyze/nonexistent/solo-note/0",
            json={"pitch": 60},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /analyze/{job_id}/voicing/{beat_index}
# ---------------------------------------------------------------------------

class TestVoicingOverride:
    def test_override_voicing(self):
        job_id = _create_stub_job()
        r = client.patch(
            f"/analyze/{job_id}/chord/0/voicing",
            json={"voicing_shape": "E-shape"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["correction_type"] == "voicing"
        assert data["index"] == 0


# ---------------------------------------------------------------------------
# POST /analyze/{job_id}/corrections/revert
# ---------------------------------------------------------------------------

class TestRevertCorrection:
    def test_revert_chord_correction(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/0", json={"chord": "Dmin"})

        # Revert
        r = client.post(
            f"/analyze/{job_id}/corrections/revert",
            json={"correction_index": 0},
        )
        assert r.status_code == 200, r.text

        # Verify history is empty
        corrections = load_corrections(job_id)
        assert len(corrections) == 0

    def test_revert_restores_original_chord(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/0", json={"chord": "Dmin"})
        client.post(f"/analyze/{job_id}/corrections/revert", json={"correction_index": 0})

        from app.analysis_store import load_chord_timeline
        ct = load_chord_timeline(job_id)
        assert ct is not None
        assert ct.events[0].chord == "Cmaj"  # original value restored

    def test_revert_invalid_index(self):
        job_id = _create_stub_job()
        r = client.post(
            f"/analyze/{job_id}/corrections/revert",
            json={"correction_index": 99},
        )
        assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# POST /analyze/{job_id}/corrections/export
# ---------------------------------------------------------------------------

class TestExportCorrections:
    def test_export_json(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/0", json={"chord": "Dmin"})
        client.patch(f"/analyze/{job_id}/solo-note/0", json={"pitch": 64})

        r = client.post(
            f"/analyze/{job_id}/corrections/export",
            json={"format": "json", "include_solo_notes": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["format"] == "json"
        assert data["count"] == 2

    def test_export_csv(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/0", json={"chord": "Dmin"})

        r = client.post(
            f"/analyze/{job_id}/corrections/export",
            json={"format": "csv"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["format"] == "csv"
        assert "correction_type" in data["data"]  # CSV header present

    def test_export_filters_by_type(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/0", json={"chord": "Dmin"})
        client.patch(f"/analyze/{job_id}/solo-note/0", json={"pitch": 64})

        # Export only chords (exclude solo notes)
        r = client.post(
            f"/analyze/{job_id}/corrections/export",
            json={"format": "json", "include_solo_notes": False},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 1
        assert data["data"][0]["correction_type"] == "chord"

    def test_export_nonexistent_job(self):
        r = client.post(
            "/analyze/nonexistent/corrections/export",
            json={"format": "json"},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /analyze/{job_id}/corrections (history)
# ---------------------------------------------------------------------------

class TestCorrectionHistory:
    def test_get_correction_history(self):
        job_id = _create_stub_job()
        client.patch(f"/analyze/{job_id}/chord/0", json={"chord": "Dmin"})
        client.patch(f"/analyze/{job_id}/chord/1", json={"chord": "Edim"})

        r = client.get(f"/analyze/{job_id}/corrections")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["job_id"] == job_id
        assert data["correction_count"] == 2
        assert len(data["corrections"]) == 2
        assert data["correction_coverage"] > 0

    def test_get_correction_history_empty(self):
        job_id = _create_stub_job()
        r = client.get(f"/analyze/{job_id}/corrections")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["correction_count"] == 0
        assert data["correction_coverage"] == 0.0

    def test_get_correction_history_nonexistent_job(self):
        r = client.get("/analyze/nonexistent/corrections")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Retraining data preparation
# ---------------------------------------------------------------------------

class TestRetrainingDataPrep:
    def test_prepare_retraining_data_script(self, tmp_path):
        """Verify the retraining script runs without errors."""
        import subprocess
        import sys

        corrections = [
            {
                "correction_type": "chord",
                "index": 0,
                "original_value": {"chord": "Cmaj"},
                "corrected_value": {"chord": "Dmin7"},
                "applied_at": "2025-01-01T00:00:00Z",
            },
            {
                "correction_type": "chord",
                "index": 1,
                "original_value": {"chord": "G"},
                "corrected_value": {"chord": "Am7"},
                "applied_at": "2025-01-01T00:00:01Z",
            },
            {
                "correction_type": "solo_note",
                "index": 0,
                "original_value": {"pitch": 60},
                "corrected_value": {"pitch": 62},
                "applied_at": "2025-01-01T00:00:02Z",
            },
        ]

        input_file = tmp_path / "corrections.json"
        input_file.write_text(json.dumps({"format": "json", "data": corrections}))

        output_dir = tmp_path / "retraining"

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parent.parent / "scripts" / "prepare_retraining_data.py"),
                "--corrections-file", str(input_file),
                "--output-dir", str(output_dir),
                "--augment",
                "--augment-factor", "3",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert (output_dir / "retraining_X.npy").exists()
        assert (output_dir / "retraining_y.npy").exists()
        assert (output_dir / "metadata.json").exists()

        import numpy as np
        X = np.load(output_dir / "retraining_X.npy")
        y = np.load(output_dir / "retraining_y.npy")
        assert X.shape[1] == 36  # N_BINS
        assert len(X) == len(y)
        assert len(X) > 0
