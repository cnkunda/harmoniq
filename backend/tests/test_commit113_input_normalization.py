"""Commit 113: Input Normalization & Long-Track Chunking Fix tests."""

from __future__ import annotations

import subprocess
import wave
import math
import struct
from pathlib import Path
from unittest.mock import patch

import pytest

from app.pipeline_proof import ffmpeg_normalize_command, YouTubeDownloadError, yt_dlp_download_wav
from app.audio_processing import (
    AudioPreparationResult,
    _build_chunk_offsets,
    _chunk_wav_for_long_track,
    prepare_audio_input,
    stitch_wav_chunks,
)


def _write_sine_wav(path: Path, duration_s: float = 1.0, sr: int = 44100, freq: float = 440.0) -> Path:
    n = int(duration_s * sr)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(n):
            s = 0.3 * math.sin(2 * math.pi * freq * i / sr)
            w.writeframes(struct.pack("<h", int(s * 32767)))
    return path


# --- Loudness normalization ---

def test_ffmpeg_normalize_command_has_loudnorm():
    cmd = ffmpeg_normalize_command(Path("in.mp3"), Path("out.wav"))
    assert "-af" in cmd
    idx = cmd.index("-af")
    assert cmd[idx + 1] == "loudnorm=I=-16:TP=-1.5:LRA=11"
    # Still preserves resample/downmix
    assert "-ar" in cmd and "44100" in cmd
    assert "-ac" in cmd and "1" in cmd


def test_ffmpeg_normalize_command_mono_stereo():
    cmd_mono = ffmpeg_normalize_command(Path("in.wav"), Path("out.wav"), mono=True)
    assert cmd_mono[cmd_mono.index("-ac") + 1] == "1"
    cmd_stereo = ffmpeg_normalize_command(Path("in.wav"), Path("out.wav"), mono=False)
    assert cmd_stereo[cmd_stereo.index("-ac") + 1] == "2"
    # both have loudnorm
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in cmd_stereo


# --- Chunking ---

def test_chunk_wav_splits_and_offsets(tmp_path: Path):
    wav = _write_sine_wav(tmp_path / "song.wav", duration_s=10, sr=44100)
    chunk_dir = tmp_path / "chunks"
    chunks = _chunk_wav_for_long_track(wav, chunk_dir, chunk_seconds=3)
    # 10s /3 = 4 chunks (3,3,3,1)
    assert len(chunks) == 4
    offsets = _build_chunk_offsets(wav, chunks)
    assert len(offsets) == 4
    assert offsets[0] == {"chunk_index": 0, "start_seconds": 0.0, "end_seconds": pytest.approx(3.0, abs=0.01)}
    assert offsets[1]["start_seconds"] == pytest.approx(3.0, abs=0.01)
    assert offsets[3]["end_seconds"] == pytest.approx(10.0, abs=0.05)
    # monotonic
    for i in range(len(offsets) - 1):
        assert offsets[i]["end_seconds"] == pytest.approx(offsets[i + 1]["start_seconds"], abs=0.001)


def test_chunk_offset_metadata_accuracy(tmp_path: Path):
    wav = _write_sine_wav(tmp_path / "src.wav", duration_s=7, sr=22050)
    chunk_dir = tmp_path / "chunks2"
    chunks = _chunk_wav_for_long_track(wav, chunk_dir, chunk_seconds=2)
    offsets = _build_chunk_offsets(wav, chunks)
    # sum durations == 7
    assert offsets[-1]["end_seconds"] == pytest.approx(7.0, abs=0.05)
    # first chunk starts at 0
    assert offsets[0]["start_seconds"] == 0.0


def test_stitch_wav_round_trip(tmp_path: Path):
    wav = _write_sine_wav(tmp_path / "original.wav", duration_s=5, sr=44100)
    chunk_dir = tmp_path / "chunks"
    chunks = _chunk_wav_for_long_track(wav, chunk_dir, chunk_seconds=2)
    stitched = tmp_path / "stitched.wav"
    stitch_wav_chunks(list(chunks), stitched)
    # Compare frames
    with wave.open(str(wav), "rb") as a, wave.open(str(stitched), "rb") as b:
        assert a.getnframes() == b.getnframes()
        assert a.getframerate() == b.getframerate()
        assert a.readframes(a.getnframes()) == b.readframes(b.getnframes())
    # Also test audio_processing stitch
    from app.audio_processing import stitch_wav_chunks as stitch2
    stitched2 = tmp_path / "stitched2.wav"
    stitch2(chunks, stitched2)
    with wave.open(str(stitched2), "rb") as b2, wave.open(str(wav), "rb") as a2:
        assert b2.getnframes() == a2.getnframes()


def test_stitch_mismatched_format_raises(tmp_path: Path):
    w1 = _write_sine_wav(tmp_path / "w1.wav", duration_s=1, sr=44100)
    w2 = _write_sine_wav(tmp_path / "w2.wav", duration_s=1, sr=22050)
    with pytest.raises(Exception):
        stitch_wav_chunks([w1, w2], tmp_path / "out.wav")


def test_prepare_audio_chunk_offsets_integration(tmp_path: Path, monkeypatch):
    # Use small trigger for testing
    monkeypatch.setattr("app.audio_processing.LONG_TRACK_CHUNK_TRIGGER_SECONDS", 5)
    monkeypatch.setattr("app.audio_processing.LONG_TRACK_CHUNK_SECONDS", 2)
    monkeypatch.setattr("app.ingest.MIN_ANALYZE_DURATION_SECONDS", 0.01)
    # Create upload under DATA_DIR job
    import uuid
    monkeypatch.setenv("DATA_DIR", str(tmp_path / f"data_{uuid.uuid4()}"))
    # Write a 6s wav as upload file inside DATA_DIR
    from app.ingest import get_data_dir
    data_dir = get_data_dir()
    upload = data_dir / "upload.wav"
    _write_sine_wav(upload, duration_s=6, sr=44100)
    result = prepare_audio_input("test_job_123", youtube_url=None, upload_path=str(upload))
    assert len(result.chunk_paths) >= 2
    assert len(result.chunk_offsets) == len(result.chunk_paths)
    assert result.chunk_offsets[0]["chunk_index"] == 0
    assert result.chunk_offsets[0]["start_seconds"] == 0.0
    assert result.chunk_offsets[-1]["end_seconds"] == pytest.approx(6.0, abs=0.05)
    # Check stitch reproduces same frames as normalized
    stitched = tmp_path / "stitched_full.wav"
    stitch_wav_chunks(list(result.chunk_paths), stitched)
    with wave.open(str(result.normalized_wav_path), "rb") as a, wave.open(str(stitched), "rb") as b:
        assert a.getnframes() == b.getnframes()


def test_prepare_audio_no_chunk_for_short(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.audio_processing.LONG_TRACK_CHUNK_TRIGGER_SECONDS", 15 * 60)
    monkeypatch.setattr("app.ingest.MIN_ANALYZE_DURATION_SECONDS", 0.01)
    import uuid
    monkeypatch.setenv("DATA_DIR", str(tmp_path / f"data2_{uuid.uuid4()}"))
    from app.ingest import get_data_dir
    data_dir = get_data_dir()
    upload = data_dir / "short.wav"
    _write_sine_wav(upload, duration_s=2, sr=44100)
    result = prepare_audio_input("short_job", youtube_url=None, upload_path=str(upload))
    assert result.chunk_paths == ()
    assert result.chunk_offsets == ()


def test_audio_preparation_result_backward_compat():
    r = AudioPreparationResult("j", Path("/tmp"), Path("/tmp/a.wav"), None, 10.0, ())
    assert r.chunk_offsets == ()
    assert r.chunk_paths == ()


# --- yt-dlp timeout ---

def test_yt_dlp_timeout_raises_user_friendly(tmp_path: Path):
    with patch("app.pipeline_proof.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["yt-dlp"], timeout=600)):
        with pytest.raises(YouTubeDownloadError, match="timed out after 10 minutes"):
            yt_dlp_download_wav("https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path)


def test_yt_dlp_uses_timeout_600(tmp_path: Path):
    captured = {}

    def fake_run(cmd, check=True, cwd=None, timeout=None):
        captured["timeout"] = timeout
        captured["cmd"] = cmd
        raise subprocess.CalledProcessError(1, cmd, "error")

    with patch("app.pipeline_proof.subprocess.run", side_effect=fake_run):
        with pytest.raises(YouTubeDownloadError):
            yt_dlp_download_wav("https://www.youtube.com/watch?v=dQw4w9WgXcQ", tmp_path)
    assert captured["timeout"] == 600


# --- separate chunked stems ---

def test_separate_chunked_stitching_placeholder(tmp_path: Path, monkeypatch):
    """Chunk → separate (placeholder) → stitch produces identical audio to full-file placeholder."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    from app.separate import separate_song_to_stems

    # Create a 6s mono wav pretending to be a long track (lower trigger)
    wav = _write_sine_wav(tmp_path / "jobs" / "test_chunk_stitch" / "song.wav", duration_s=6, sr=44100)
    wav.parent.mkdir(parents=True, exist_ok=True)
    # Create chunks manually (2s each → 3 chunks)
    from app.audio_processing import _chunk_wav_for_long_track
    chunk_dir = wav.parent / "chunks"
    chunks = _chunk_wav_for_long_track(wav, chunk_dir, chunk_seconds=2)
    job_dir = wav.parent
    # Chunk-aware separation
    mapping_chunked = separate_song_to_stems(wav, job_dir)
    # Now remove chunks and separate without chunking
    import shutil
    shutil.rmtree(chunk_dir)
    # Need separate job dir for non-chunked run to avoid overwrite confusion
    job_dir2 = tmp_path / "jobs" / "test_no_chunk"
    job_dir2.mkdir(parents=True, exist_ok=True)
    wav2 = job_dir2 / "song.wav"
    shutil.copyfile(wav, wav2)
    mapping_full = separate_song_to_stems(wav2, job_dir2)

    # Compare each stem (placeholder copies are copies of original)
    for stem in ("guitar", "bass", "drums", "vocals", "piano", "other"):
        # mapping values are backend-relative; resolve
        from app.separate import _backend_root
        p_chunked = _backend_root().resolve() / mapping_chunked[stem]
        p_full = _backend_root().resolve() / mapping_full[stem]
        # If running in backend's temp root, fallback to stems_dir
        if not p_chunked.exists():
            p_chunked = job_dir / "stems" / f"{stem}.wav"
        if not p_full.exists():
            p_full = job_dir2 / "stems" / f"{stem}.wav"
        with wave.open(str(p_chunked), "rb") as a, wave.open(str(p_full), "rb") as b:
            assert a.getnframes() == b.getnframes(), f"{stem} frame mismatch"
            assert a.readframes(a.getnframes()) == b.readframes(b.getnframes()), f"{stem} data mismatch"


def test_demucs_engine_chunked_placeholder(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    from app.demucs_engine import separate_with_demucs

    import shutil
    job_dir = tmp_path / "job_demucs_chunk"
    job_dir.mkdir(parents=True, exist_ok=True)
    wav = _write_sine_wav(job_dir / "song.wav", duration_s=6, sr=44100)
    from app.audio_processing import _chunk_wav_for_long_track
    chunk_dir = job_dir / "chunks"
    _chunk_wav_for_long_track(wav, chunk_dir, chunk_seconds=2)
    mapping = separate_with_demucs(wav, job_dir)
    # Should have created stems via chunk path
    assert len(mapping) == 6
    for stem, rel in mapping.items():
        p = Path(rel)
        # backend-relative; may not exist at that rel if DATA_DIR default not used
        # check stems dir exists
        assert (job_dir / "stems" / f"{stem}.wav").exists()
