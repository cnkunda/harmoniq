from __future__ import annotations

from uuid import uuid4

from app.cache import cache_key_for_wav_and_profile, load_cached_lesson_for_wav, save_cached_lesson_for_wav
from app.schemas import LessonJSON, PlayerProfile, SkillNode


def _write_wav_stub(path) -> None:
    path.write_bytes(b"RIFFstub-audio")


def test_cache_key_changes_for_different_non_empty_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / f".tmp_test_data_{uuid4()}"))
    wav_path = tmp_path / "song.wav"
    _write_wav_stub(wav_path)

    p1 = PlayerProfile(weak_areas=["bending"])
    p2 = PlayerProfile(skill_nodes=[SkillNode(id="timing", score=0.2)])

    k1 = cache_key_for_wav_and_profile(wav_path, p1)
    k2 = cache_key_for_wav_and_profile(wav_path, p2)

    assert k1 != k2
    assert "|p:" in k1
    assert "|p:" in k2


def test_cache_key_treats_none_and_empty_profile_equally(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / f".tmp_test_data_{uuid4()}"))
    wav_path = tmp_path / "song.wav"
    _write_wav_stub(wav_path)

    k_none = cache_key_for_wav_and_profile(wav_path, None)
    k_empty = cache_key_for_wav_and_profile(wav_path, PlayerProfile())

    assert k_none == k_empty
    assert "|p:" not in k_none


def test_cached_lessons_are_partitioned_by_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / f".tmp_test_data_{uuid4()}"))
    wav_path = tmp_path / "song.wav"
    _write_wav_stub(wav_path)

    p1 = PlayerProfile(weak_areas=["bending"])
    p2 = PlayerProfile(weak_areas=["timing"])

    lesson1 = LessonJSON(job_id="p1", style_label="uptempo rock / lead energy")
    lesson2 = LessonJSON(job_id="p2", style_label="slow ballad / expressive phrasing")
    save_cached_lesson_for_wav(wav_path, lesson1, player_profile=p1)
    save_cached_lesson_for_wav(wav_path, lesson2, player_profile=p2)

    loaded1 = load_cached_lesson_for_wav(wav_path, player_profile=p1)
    loaded2 = load_cached_lesson_for_wav(wav_path, player_profile=p2)
    loaded_none = load_cached_lesson_for_wav(wav_path, player_profile=None)

    assert loaded1 is not None
    assert loaded2 is not None
    assert loaded1.job_id == "p1"
    assert loaded2.job_id == "p2"
    assert loaded_none is None
