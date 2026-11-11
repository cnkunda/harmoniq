"""Tests for T1/T2: solo branch uses the guitar stem and stays guitar-only."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from app.audio_mix import resolve_solo_stem
from app.mt3 import fallback
from app.mt3.schemas import Mt3Event, Mt3EventStream
from app.schemas import BeatGrid, TimeSignature


def _beat_grid() -> BeatGrid:
    return BeatGrid(
        bpm=120.0,
        pulse_bpm=120.0,
        beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
        downbeats=[0.0, 2.0],
        time_signature=TimeSignature(numerator=4, denominator=4),
        tick_value=0.25,
    )


def _chord_stream() -> Mt3EventStream:
    events = []
    for pitch in (60, 64, 67):
        events.append(Mt3Event(time=0.0, pitch=pitch, velocity=100, program=24, is_onset=True, confidence=0.95))
        events.append(Mt3Event(time=1.0, pitch=pitch, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9))
    return Mt3EventStream(events=events, audio_duration_s=2.0, mean_confidence=0.95, num_instruments=1)


def _solo_stream() -> Mt3EventStream:
    events = [
        # Guitar lead note (kept).
        Mt3Event(time=0.0, pitch=69, velocity=100, program=24, is_onset=True, confidence=0.9),
        Mt3Event(time=1.0, pitch=69, velocity=0, program=24, is_onset=False, is_offset=True, confidence=0.9),
        # Piano bleed (filtered out of the guitar solo stream).
        Mt3Event(time=0.5, pitch=72, velocity=90, program=0, is_onset=True, confidence=0.9),
        Mt3Event(time=1.0, pitch=72, velocity=0, program=0, is_onset=False, is_offset=True, confidence=0.9),
    ]
    return Mt3EventStream(events=events, audio_duration_s=2.0, mean_confidence=0.9, num_instruments=2)


class _FakeServer:
    def is_available(self) -> bool:
        return True


def test_solo_branch_decodes_from_guitar_stem(monkeypatch, tmp_path: Path) -> None:
    chord_path = tmp_path / "chord_mix.wav"
    solo_path = tmp_path / "guitar.wav"
    chord_path.write_bytes(b"x")
    solo_path.write_bytes(b"y")

    calls: list[str] = []

    def fake_infer(path: str) -> Mt3EventStream:
        calls.append(path)
        return _chord_stream() if path == str(chord_path) else _solo_stream()

    monkeypatch.setattr(fallback, "mt3_infer", fake_infer)
    monkeypatch.setattr(fallback, "Mt3ModelServer", _FakeServer)
    monkeypatch.setattr(fallback, "confidence_gate_enabled", lambda: False)

    result = fallback._try_mt3(
        chord_path,
        _beat_grid(),
        0.5,
        solo_audio_path=solo_path,
        guitar_only_solo=True,
    )

    assert result is not None
    assert calls == [str(chord_path), str(solo_path)]
    pitches = {note.pitch for note in result.solo_notes.notes}
    assert 69 in pitches
    assert 72 not in pitches  # piano bleed filtered
    # Two onsets in the solo stream; one is piano -> 0.5 leakage.
    assert result.solo_leakage_ratio == 0.5


def test_solo_reuses_chord_stream_when_paths_match(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "same.wav"
    path.write_bytes(b"x")
    calls: list[str] = []
    monkeypatch.setattr(fallback, "mt3_infer", lambda p: calls.append(p) or _chord_stream())
    monkeypatch.setattr(fallback, "Mt3ModelServer", _FakeServer)
    monkeypatch.setattr(fallback, "confidence_gate_enabled", lambda: False)

    result = fallback._try_mt3(path, _beat_grid(), 0.5, solo_audio_path=path)
    assert result is not None
    assert calls == [str(path)]


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((samples * 32767).astype("<i2").tobytes())


def test_resolve_solo_stem_never_returns_vocals(tmp_path: Path) -> None:
    guitar = tmp_path / "guitar.wav"
    vocals = tmp_path / "vocals.wav"
    _write_wav(guitar, np.zeros(800))
    _write_wav(vocals, 0.5 * np.sin(np.linspace(0, 200, 800)))

    stems = {"guitar": guitar, "vocals": vocals}
    path, chosen = resolve_solo_stem(stems, "guitar", allow_vocals=False)
    assert path == guitar
    assert chosen == "default_guitar"

    path_allowed, chosen_allowed = resolve_solo_stem(stems, "vocals", allow_vocals=True)
    assert path_allowed == vocals
    assert chosen_allowed == "vocals"
