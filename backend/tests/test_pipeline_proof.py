"""Tests for the feasibility pipeline (PRIORITIES commit 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline_proof import (
    NoteEvent,
    build_gp5_from_note_events,
    cli_equivalents_doc,
    demucs_separate_command,
    estimate_key_literal,
    ffmpeg_normalize_command,
    find_guitar_stem,
    librosa_summarize,
    yt_dlp_download_audio_command,
)

gp = pytest.importorskip("guitarpro")


def test_demucs_separate_command_uses_htdemucs_6s():
    cmd = demucs_separate_command(Path("song.wav"), Path("out"))
    assert "-n" in cmd
    assert cmd[cmd.index("-n") + 1] == "htdemucs_6s"
    assert str(Path("song.wav")) in cmd


def test_ffmpeg_normalize_command_shape():
    cmd = ffmpeg_normalize_command(Path("in.mp3"), Path("out.wav"))
    assert cmd[0] == "ffmpeg"
    assert "-ar" in cmd
    i = cmd.index("-ar")
    assert cmd[i + 1] == "44100"
    assert "-ac" in cmd
    j = cmd.index("-ac")
    assert cmd[j + 1] == "1"


def test_yt_dlp_command_includes_expected_flags():
    cmd = yt_dlp_download_audio_command(
        "https://example.com/watch?v=abc",
        Path("%(id)s.%(ext)s"),
    )
    assert "yt-dlp" in cmd[0] or cmd[0].endswith("yt-dlp")
    assert "--extract-audio" in cmd
    assert "--audio-format" in cmd
    assert "wav" in cmd


def test_find_guitar_stem(tmp_path: Path):
    root = tmp_path / "htdemucs_6s" / "mysong"
    root.mkdir(parents=True)
    g = root / "guitar.wav"
    g.write_bytes(b"RIFF")
    found = find_guitar_stem(tmp_path / "htdemucs_6s")
    assert found == g


def test_find_guitar_stem_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        find_guitar_stem(tmp_path)


def test_estimate_key_literal_major():
    # Strong C major triad footprint in chroma (C, E, G)
    chroma = [0.0] * 12
    chroma[0] = 1.0  # C
    chroma[4] = 0.95  # E
    chroma[7] = 0.9  # G
    root, mode = estimate_key_literal(chroma)
    assert root == "C"
    assert mode == "major"


def test_cli_equivalents_doc_lists_demucs_and_ffmpeg():
    doc = cli_equivalents_doc()
    assert "ffmpeg" in doc
    assert "yt-dlp" in doc
    assert "demucs" in doc
    assert "htdemucs_6s" in doc


def test_build_gp5_from_note_events_roundtrip(tmp_path: Path):
    events = [
        NoteEvent(0.0, 0.25, 64, 1.0),  # E4 open high E string
        NoteEvent(0.5, 0.75, 67, 1.0),  # G4
    ]
    out = tmp_path / "proof.gp5"
    build_gp5_from_note_events(events, bpm=120, output_gp5=out, title="Unit test")
    song = gp.parse(str(out))
    assert song.title == "Unit test"
    beats = song.tracks[0].measures[0].voices[0].beats
    assert len(beats) == 4  # quarters including rests
    pitched = [b for b in beats if b.status.name == "normal" and b.notes]
    assert len(pitched) == 2


def test_librosa_summarize_runs(tmp_path: Path):
    """Requires librosa (reads WAV via soundfile or audioread)."""
    p = tmp_path / "tone.wav"
    # ~2s so chroma_cqt / STFT paths stay above librosa's n_fft minimum (avoids UserWarning on tiny clips).
    p.write_bytes(_mini_wav_mono_pcm16(duration_s=2.0))
    summary = librosa_summarize(p)
    assert summary.duration_s > 1.5
    assert isinstance(summary.beat_times_s, list)
    assert "major" in summary.key_name or "minor" in summary.key_name
    assert summary.tempo_bpm > 0


def _mini_wav_mono_pcm16(
    duration_s: float = 0.5,
    sr: int = 44100,
    freq: float = 440.0,
) -> bytes:
    """Tiny mono PCM WAV without extra dependencies (stdlib wave header + PCM)."""
    import math
    import struct
    import wave
    from io import BytesIO

    n = int(duration_s * sr)
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = []
        for i in range(n):
            s = 0.2 * math.sin(2 * math.pi * freq * i / sr)
            frames.append(struct.pack("<h", int(s * 32767)))
        w.writeframes(b"".join(frames))
    return buf.getvalue()
