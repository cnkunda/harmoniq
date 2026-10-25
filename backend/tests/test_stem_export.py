"""Tests for Commit 172: stem export endpoint."""

from __future__ import annotations

import io
import json
import zipfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.ingest import get_data_dir
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))


def _job_dir():
    job_id = str(uuid4())
    job_dir = get_data_dir() / "jobs" / job_id
    stems_dir = job_dir / "stems"
    stems_dir.mkdir(parents=True)
    return job_id, job_dir, stems_dir


def _write_stem(stems_dir, key: str, payload: bytes) -> None:
    (stems_dir / f"{key}.wav").write_bytes(payload)


def test_zip_contains_all_available_stems():
    job_id, job_dir, stems_dir = _job_dir()
    (job_dir / "lesson.json").write_text(json.dumps({"song_title": "My Song / Take 2"}))
    _write_stem(stems_dir, "guitar", b"guitar-bytes")
    _write_stem(stems_dir, "drums", b"drums-bytes")

    response = client.get(f"/jobs/{job_id}/stems")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert ".zip" in response.headers["content-disposition"]
    assert "/" not in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["guitar.wav", "drums.wav"]
        assert archive.read("guitar.wav") == b"guitar-bytes"
        assert archive.read("drums.wav") == b"drums-bytes"


def test_single_stem_returns_wav():
    job_id, _job_dir_path, stems_dir = _job_dir()
    _write_stem(stems_dir, "guitar", b"guitar-bytes")
    _write_stem(stems_dir, "drums", b"drums-bytes")

    response = client.get(f"/jobs/{job_id}/stems", params={"stem": "guitar"})

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"guitar-bytes"
    assert 'filename="guitar.wav"' in response.headers["content-disposition"]


def test_missing_job_returns_clear_404():
    response = client.get(f"/jobs/{uuid4()}/stems")

    assert response.status_code == 404
    assert "no longer available" in response.json()["detail"]


def test_job_without_stems_returns_clear_404():
    job_id = str(uuid4())
    (get_data_dir() / "jobs" / job_id).mkdir(parents=True)

    response = client.get(f"/jobs/{job_id}/stems")

    assert response.status_code == 404
    assert "no longer available" in response.json()["detail"]


def test_unknown_stem_returns_404():
    job_id, _job_dir_path, stems_dir = _job_dir()
    _write_stem(stems_dir, "guitar", b"guitar-bytes")

    response = client.get(f"/jobs/{job_id}/stems", params={"stem": "banjo"})

    assert response.status_code == 404
    assert "Unknown stem" in response.json()["detail"]


def test_missing_selected_stem_returns_404():
    job_id, _job_dir_path, stems_dir = _job_dir()
    _write_stem(stems_dir, "guitar", b"guitar-bytes")

    response = client.get(f"/jobs/{job_id}/stems", params={"stem": "piano"})

    assert response.status_code == 404
    assert "no longer available" in response.json()["detail"]


def test_invalid_job_id_returns_404():
    response = client.get("/jobs/bad id/stems")

    assert response.status_code == 404
    assert "no longer available" in response.json()["detail"]
