from __future__ import annotations

import json
from uuid import uuid4

from app import jobs
from app.cache import _cache_path, cache_key_for_wav_and_profile, load_cached_lesson_for_wav
def _write_wav_stub(path) -> None:
    path.write_bytes(b"RIFFstub-audio")


def test_stub_lesson_includes_style_label():
    lesson = jobs._stub_lesson(
        "job-stub",
        None,
        wav_path="jobs/x/song.wav",
        stems={"guitar": "jobs/x/stems/g.wav"},
        source_metadata={"song_title": "T", "artist": "A"},
    )
    assert lesson.style_label == "general"
    assert lesson.style_label.strip()


def test_load_cached_lesson_defaults_missing_style_label(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / f".tmp_test_data_{uuid4()}"))
    wav_path = tmp_path / "song.wav"
    _write_wav_stub(wav_path)

    key = cache_key_for_wav_and_profile(wav_path, None)
    cache_file = _cache_path(key)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pipeline_version": "1",
        "audio_sha256": key.split(":", 1)[1],
        "lesson_json": {
            "job_id": "legacy-no-style",
            "song_title": "S",
            "artist": "A",
        },
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_cached_lesson_for_wav(wav_path, player_profile=None)
    assert loaded is not None
    assert loaded.style_label == "general"
