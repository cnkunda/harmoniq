"""Tests for app.audio_mix — Commit 111 stem mixing utility."""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from app.audio_mix import mix_stems, resolve_chord_stems, resolve_solo_stem, wav_rms


def _write_stem(path, samples, sr=44100):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), samples.astype(np.float32), sr)


def test_wav_rms_silent_returns_zero(tmp_path):
    path = tmp_path / "silent.wav"
    _write_stem(path, np.zeros(4096))
    assert wav_rms(path) == 0.0


def test_wav_rms_sine_wave(tmp_path):
    path = tmp_path / "tone.wav"
    sr = 44100
    t = np.linspace(0, 1.0, sr)
    samples = 0.5 * np.sin(2 * np.pi * 440 * t)
    _write_stem(path, samples, sr=sr)
    rms = wav_rms(path)
    # RMS of A=0.5 sine ≈ 0.5 / sqrt(2) ≈ 0.3535
    assert 0.3 < rms < 0.4


def test_wav_rms_missing_file_returns_zero(tmp_path):
    assert wav_rms(tmp_path / "nope.wav") == 0.0


def test_mix_two_stems_normalizes_to_peak_under_one(tmp_path):
    sr = 44100
    rng = np.random.default_rng(42)
    a = (0.8 * rng.uniform(-1, 1, sr)).astype(np.float32)
    b = (0.8 * rng.uniform(-1, 1, sr)).astype(np.float32)
    p_a, p_b = tmp_path / "a.wav", tmp_path / "b.wav"
    _write_stem(p_a, a, sr=sr)
    _write_stem(p_b, b, sr=sr)

    out = tmp_path / "mix.wav"
    result_path = mix_stems([p_a, p_b], out)

    assert result_path == out
    assert out.is_file()
    data, out_sr = sf.read(str(out))
    assert out_sr == sr
    peak = float(np.max(np.abs(data)))
    # float32 WAV round-trip can push the peak slightly above 0.9 (e.g. 0.900024);
    # allow a tiny epsilon to absorb quantization noise. The mix is still
    # normalized to the 0.9 headroom target.
    assert 0.0 < peak <= 0.901, f"peak {peak} exceeds 0.9 headroom"


def test_mix_three_stems(tmp_path):
    sr = 44100
    rng = np.random.default_rng(43)
    stems = [(0.5 * rng.uniform(-1, 1, sr)).astype(np.float32) for _ in range(3)]
    paths = []
    for i, s in enumerate(stems):
        p = tmp_path / f"s{i}.wav"
        _write_stem(p, s, sr=sr)
        paths.append(p)
    out = tmp_path / "mix3.wav"
    mix_stems(paths, out)
    data, _ = sf.read(str(out))
    peak = float(np.max(np.abs(data)))
    assert peak <= 0.901


def test_mix_silent_stem_alone_yields_silence(tmp_path):
    sr = 44100
    silent = np.zeros(sr, dtype=np.float32)
    p = tmp_path / "silent.wav"
    _write_stem(p, silent, sr=sr)
    out = tmp_path / "mix_silent.wav"
    mix_stems([p], out)
    data, _ = sf.read(str(out))
    assert np.max(np.abs(data)) == 0.0


def test_mix_silent_with_loud_normalizes_loud(tmp_path):
    sr = 44100
    rng = np.random.default_rng(44)
    loud = (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)
    silent = np.zeros(sr, dtype=np.float32)
    p_loud, p_silent = tmp_path / "loud.wav", tmp_path / "sil.wav"
    _write_stem(p_loud, loud, sr=sr)
    _write_stem(p_silent, silent, sr=sr)
    out = tmp_path / "mix.wav"
    mix_stems([p_loud, p_silent], out)
    data, _ = sf.read(str(out))
    assert np.max(np.abs(data)) <= 0.901
    # Loud stem should be at peak headroom (since silent contributes nothing)
    assert np.max(np.abs(data)) > 0.5


def test_mix_handles_length_mismatch(tmp_path):
    sr = 44100
    rng = np.random.default_rng(45)
    short = (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)        # 1.0s
    long = (0.3 * rng.uniform(-1, 1, sr * 2)).astype(np.float32)     # 2.0s
    p_short, p_long = tmp_path / "s.wav", tmp_path / "l.wav"
    _write_stem(p_short, short, sr=sr)
    _write_stem(p_long, long, sr=sr)
    out = tmp_path / "mix_len.wav"
    mix_stems([p_short, p_long], out)
    data, out_sr = sf.read(str(out))
    assert out_sr == sr
    assert len(data) == sr * 2  # padded to longest


def test_mix_raises_on_no_valid_paths(tmp_path):
    out = tmp_path / "out.wav"
    with pytest.raises(FileNotFoundError):
        mix_stems([], out)
    with pytest.raises(FileNotFoundError):
        mix_stems([tmp_path / "nope1.wav", tmp_path / "nope2.wav"], out)


def test_mix_raises_on_sample_rate_mismatch(tmp_path):
    p1 = tmp_path / "s1.wav"
    p2 = tmp_path / "s2.wav"
    _write_stem(p1, np.zeros(44100, dtype=np.float32), sr=44100)
    _write_stem(p2, np.zeros(22050, dtype=np.float32), sr=22050)
    out = tmp_path / "out.wav"
    with pytest.raises(ValueError, match="Sample rate"):
        mix_stems([p1, p2], out)


def test_mix_stereo_to_mono(tmp_path):
    sr = 44100
    # 2-channel: left=0.3 sine, right=0.6 sine
    t = np.linspace(0, 1.0, sr)
    stereo = np.stack([0.3 * np.sin(2 * np.pi * 440 * t),
                       0.6 * np.sin(2 * np.pi * 440 * t)], axis=1)
    p = tmp_path / "stereo.wav"
    sf.write(str(p), stereo.astype(np.float32), sr)
    out = tmp_path / "mono.wav"
    mix_stems([p], out)
    data, _ = sf.read(str(out))
    assert data.ndim == 1, "Expected mono output"
    assert np.max(np.abs(data)) <= 0.901


def test_resolve_chord_stems_returns_only_audible(tmp_path):
    sr = 44100
    rng = np.random.default_rng(46)
    a_loud = (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)
    a_silent = np.zeros(sr, dtype=np.float32)
    p_loud = tmp_path / "loud.wav"
    p_silent = tmp_path / "silent.wav"
    _write_stem(p_loud, a_loud, sr=sr)
    _write_stem(p_silent, a_silent, sr=sr)
    paths = {"bass": p_loud, "other": p_silent, "drums": p_loud}
    result = resolve_chord_stems(paths, ["bass", "other"])
    assert result == [p_loud]


def test_resolve_chord_stems_drops_missing_keys(tmp_path):
    sr = 44100
    rng = np.random.default_rng(47)
    sig = (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)
    p = tmp_path / "bass.wav"
    _write_stem(p, sig, sr=sr)
    paths = {"bass": p}  # "other" missing
    result = resolve_chord_stems(paths, ["bass", "other"])
    assert result == [p]


def test_resolve_solo_stem_prefers_selected(tmp_path):
    sr = 44100
    rng = np.random.default_rng(48)
    sig = (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)
    p = tmp_path / "selected.wav"
    _write_stem(p, sig, sr=sr)
    result_path, name = resolve_solo_stem({"selected": p, "guitar": p}, "selected")
    assert result_path == p
    assert name == "selected"


def test_resolve_solo_stem_falls_back_to_guitar(tmp_path):
    sr = 44100
    rng = np.random.default_rng(49)
    sig = (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)
    p_sel = tmp_path / "sel_silent.wav"
    p_gtr = tmp_path / "gtr.wav"
    _write_stem(p_sel, np.zeros(sr, dtype=np.float32), sr=sr)
    _write_stem(p_gtr, sig, sr=sr)
    result_path, name = resolve_solo_stem({"selected": p_sel, "guitar": p_gtr}, "selected")
    assert result_path == p_gtr
    assert name == "guitar"


def test_resolve_solo_stem_falls_back_to_vocals(tmp_path):
    sr = 44100
    rng = np.random.default_rng(50)
    sig = (0.3 * rng.uniform(-1, 1, sr)).astype(np.float32)
    p_gtr = tmp_path / "gtr_silent.wav"
    p_voc = tmp_path / "voc.wav"
    _write_stem(p_gtr, np.zeros(sr, dtype=np.float32), sr=sr)
    _write_stem(p_voc, sig, sr=sr)
    result_path, name = resolve_solo_stem(
        {"selected": p_gtr, "guitar": p_gtr, "vocals": p_voc}, "selected"
    )
    assert result_path == p_voc
    assert name == "vocals"
