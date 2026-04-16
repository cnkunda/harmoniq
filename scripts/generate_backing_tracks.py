#!/usr/bin/env python3
"""
Regenerate bundled Jam offline loops (stereo MP3, ~24s, 44.1kHz).

Requires: numpy, ffmpeg on PATH.

These are original programmatic compositions (not recordings of commercial songs):
multi-layer bass, chord pads / arpeggios, and simple drum patterns — suitable as
practice beds and for repo distribution per assets/backing-tracks/SOURCES.md.
"""

from __future__ import annotations

import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
DURATION_SEC = 24.0
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "backing-tracks"


def midi_to_hz(m: float) -> float:
    return 440.0 * (2.0 ** ((m - 69.0) / 12.0))


def soft_clip(x: np.ndarray, drive: float = 1.15) -> np.ndarray:
    y = np.tanh(drive * x)
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def envelope_adsr(n: int, attack: int, decay: int, sustain: float, release: int) -> np.ndarray:
    """Linear ADSR length n samples."""
    out = np.ones(n, dtype=np.float32)
    a = min(attack, n // 4)
    d = min(decay, n // 4)
    r = min(release, n // 4)
    if a > 0:
        out[:a] = np.linspace(0.0, 1.0, a, endpoint=False, dtype=np.float32)
    if d > 0 and a + d < n:
        out[a : a + d] = np.linspace(1.0, sustain, d, endpoint=False, dtype=np.float32)
    if r > 0:
        out[-r:] = np.linspace(float(out[-r - 1]), 0.0, r, dtype=np.float32)
    return out


def noise_burst(n: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n).astype(np.float32) * 0.35


def drum_kit(t: np.ndarray, bpm: float, swing: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Mono kick + snare+hihat mix (stereo applied later). swing in [0,0.2] shifts offbeats."""
    beat = 60.0 / bpm
    n = t.size
    kick = np.zeros(n, dtype=np.float32)
    snare = np.zeros(n, dtype=np.float32)
    hat = np.zeros(n, dtype=np.float32)
    for i in range(int(t[-1] * bpm / 60.0) + 4):
        t0 = i * beat + (swing * beat if i % 2 == 1 else 0.0)
        if t0 >= t[-1]:
            break
        idx = int(t0 * SR)
        if idx < 0 or idx >= n:
            continue
        # kick on 1 and 3 (i % 4 in 0,2)
        if i % 4 in (0, 2):
            wn = min(800, n - idx)
            env = envelope_adsr(wn, 4, 120, 0.0, 80)
            ph = np.linspace(0.0, 55.0 * 2 * math.pi * wn / SR, wn, dtype=np.float32)
            kick[idx : idx + wn] += 0.55 * env * np.sin(ph, dtype=np.float32) * np.exp(-np.linspace(0, 8, wn, dtype=np.float32))
        # snare on 2 and 4
        if i % 4 in (1, 3):
            wn = min(2200, n - idx)
            env = envelope_adsr(wn, 2, 40, 0.25, 180)
            body = noise_burst(wn, seed=i)
            snare[idx : idx + wn] += 0.42 * env * body
        # closed hat every 8th (2 per beat)
        for sub in (0.0, 0.5):
            t1 = t0 + sub * beat
            j = int(t1 * SR)
            if 0 <= j < n - 400:
                wn = 320
                env = envelope_adsr(wn, 1, 30, 0.0, 40)
                nbuf = noise_burst(wn, seed=1000 + i + int(sub * 10))
                hp = nbuf - np.mean(nbuf)
                hat[j : j + wn] += 0.12 * env * hp
    drums = kick + snare + hat
    return kick * 0.9, drums


def sine_stack(freqs: list[float], t: np.ndarray, amps: list[float] | None = None) -> np.ndarray:
    if amps is None:
        amps = [1.0 / max(1, len(freqs))] * len(freqs)
    out = np.zeros_like(t, dtype=np.float32)
    phase = 2.0 * math.pi * t
    for f, a in zip(freqs, amps, strict=True):
        out += a * np.sin(phase * f, dtype=np.float32)
    return out


def arpeggio(notes: list[float], t: np.ndarray, bpm: float, order: list[int], gate: float = 0.42) -> np.ndarray:
    """Round-robin arpeggio: order indexes into notes."""
    beat = 60.0 / bpm
    eighth = beat / 2.0
    out = np.zeros_like(t, dtype=np.float32)
    step = 0
    pos = 0.0
    while pos < t[-1]:
        m = notes[order[step % len(order)]]
        f = midi_to_hz(m)
        nxt = pos + eighth * gate
        i0 = int(pos * SR)
        i1 = int(nxt * SR)
        if i0 >= 0 and i1 < t.size and i1 > i0 and nxt > pos + 1e-6:
            seg = t[i0:i1] - pos
            span = float(nxt - pos)
            bell = 0.5 - 0.5 * np.cos((seg / span) * math.pi, dtype=np.float32)
            env = np.clip(bell, 0.0, 1.0) ** 0.7
            out[i0:i1] += 0.22 * env * np.sin(2.0 * math.pi * f * seg, dtype=np.float32)
        pos += eighth
        step += 1
    return out


def chord_pad_progression(
    t: np.ndarray,
    bpm: float,
    bars: list[tuple[float, list[float]]],
) -> np.ndarray:
    """bars: (duration_in_beats, midi_notes); cycles until `t` duration is covered."""
    beat = 60.0 / bpm
    out = np.zeros_like(t, dtype=np.float32)
    cursor = 0.0
    bi = 0
    while cursor * beat < t[-1]:
        dur_beats, midi_notes = bars[bi % len(bars)]
        bi += 1
        t0 = cursor * beat
        t1 = min(t[-1], (cursor + dur_beats) * beat)
        i0 = max(0, int(t0 * SR))
        i1 = min(t.size, int(t1 * SR))
        if i1 <= i0:
            cursor += dur_beats
            continue
        seg_t = t[i0:i1] - t0
        freqs = [midi_to_hz(m) for m in midi_notes]
        layer = sine_stack(freqs, seg_t, amps=[0.11 / len(freqs)] * len(freqs))
        trem = 0.92 + 0.08 * np.sin(2.0 * math.pi * 0.25 * seg_t, dtype=np.float32)
        out[i0:i1] += layer * trem
        cursor += dur_beats
    return out


def bass_step_pattern(t: np.ndarray, bpm: float, eighth_freqs_hz: list[float]) -> np.ndarray:
    """One bar = 8 eighth-notes; `eighth_freqs_hz` length 8, repeated."""
    eighth = (60.0 / bpm) / 2.0
    out = np.zeros_like(t, dtype=np.float32)
    step = 0
    pos = 0.0
    while pos < t[-1]:
        mod = step % 8
        f = eighth_freqs_hz[mod % len(eighth_freqs_hz)]
        nxt = pos + eighth * 0.85
        i0 = int(pos * SR)
        i1 = int(nxt * SR)
        if i0 >= 0 and i1 < t.size and i1 > i0 and nxt > pos + 1e-6:
            seg = t[i0:i1] - pos
            span = float(nxt - pos)
            bell = 0.5 - 0.5 * np.cos((seg / span) * math.pi, dtype=np.float32)
            env = (np.clip(bell, 0.0, 1.0) ** 1.2) * 0.38
            out[i0:i1] += env * np.sin(2.0 * math.pi * f * seg, dtype=np.float32)
        pos += eighth
        step += 1
    return out


def build_am_blues(t: np.ndarray) -> np.ndarray:
    bpm = 70.0
    # A minor blues progression (28 beats @ 70 BPM = 24 s loop)
    root = [57, 60, 64]  # Am
    dm = [50, 53, 57]
    e7 = [52, 56, 59, 62]
    bars: list[tuple[float, list[float]]] = [
        (4, root),
        (2, dm),
        (2, root),
        (2, e7),
        (2, root),
        (4, root),
        (4, dm),
        (4, root),
        (4, e7),
    ]
    pad = chord_pad_progression(t, bpm, bars)
    # walking-ish bass on roots
    hz_pat = [
        midi_to_hz(45),
        midi_to_hz(48),
        midi_to_hz(50),
        midi_to_hz(52),
        midi_to_hz(43),
        midi_to_hz(45),
        midi_to_hz(47),
        midi_to_hz(50),
    ]
    bass = bass_step_pattern(t, bpm, hz_pat)
    _, drums = drum_kit(t, bpm, swing=0.06)
    shuf = 0.12 * sine_stack([midi_to_hz(64), midi_to_hz(67)], t, [0.04, 0.035])
    shuf *= 0.5 + 0.5 * np.sin(2.0 * math.pi * (bpm / 60.0) * 1.5 * t, dtype=np.float32) ** 2
    mono = pad + bass + drums + shuf
    return soft_clip(mono * 1.05)


def build_am_drone(t: np.ndarray) -> np.ndarray:
    # Rich A minor cluster + slow fifth motion
    f1 = [midi_to_hz(45), midi_to_hz(57), midi_to_hz(60), midi_to_hz(64), midi_to_hz(72)]
    base = sine_stack(f1, t, amps=[0.14, 0.09, 0.1, 0.08, 0.05])
    lfo = 0.75 + 0.25 * np.sin(2.0 * math.pi * 0.07 * t, dtype=np.float32)
    shimmer = 0.06 * sine_stack([midi_to_hz(81), midi_to_hz(84)], t)
    wide = base * lfo + shimmer
    st = np.stack([wide, wide * 0.97 + 0.03 * shimmer], axis=-1)
    return np.tanh(1.12 * st).astype(np.float32)


def build_g_finger(t: np.ndarray) -> np.ndarray:
    bpm = 80.0
    gmaj = [55, 59, 62, 67]  # G B D G
    arp = arpeggio(gmaj, t, bpm, [0, 1, 2, 3, 2, 1], gate=0.38)
    pad = chord_pad_progression(t, bpm, [(8, [55, 59, 62])])
    # G2 / passing tones — two-bar feel
    full = [
        midi_to_hz(43),
        midi_to_hz(43),
        midi_to_hz(41),
        midi_to_hz(43),
        midi_to_hz(40),
        midi_to_hz(43),
        midi_to_hz(38),
        midi_to_hz(43),
    ]
    bass = bass_step_pattern(t, bpm, full)
    _, drums = drum_kit(t, bpm, swing=0.04)
    mono = pad * 0.65 + arp + bass * 1.1 + drums * 0.85
    return soft_clip(mono * 1.08)


def build_em_vamp(t: np.ndarray) -> np.ndarray:
    bpm = 90.0
    em = [52, 55, 59]
    b7 = [47, 51, 54, 58]  # B7 shell
    bars = [(2, em), (2, b7)]
    pad = chord_pad_progression(t, bpm, bars)
    e2 = midi_to_hz(40)
    b1 = midi_to_hz(35)
    pat = [e2, e2, e2, e2, b1, b1, b1, b1]
    bass = bass_step_pattern(t, bpm, pat)
    _, drums = drum_kit(t, bpm, swing=0.05)
    mono = pad + bass + drums
    return soft_clip(mono * 1.1)


def build_g_ballad(t: np.ndarray) -> np.ndarray:
    bpm = 65.0
    gm = [55, 59, 62, 66]  # Gmaj7
    pad = chord_pad_progression(t, bpm, [(4, gm)])
    hz = [midi_to_hz(43), midi_to_hz(43), midi_to_hz(45), midi_to_hz(43), midi_to_hz(47), midi_to_hz(45), midi_to_hz(43), midi_to_hz(41)]
    bass = bass_step_pattern(t, bpm, hz) * 1.05
    _, drums = drum_kit(t, bpm, swing=0.0)
    mono = pad * 1.1 + bass + drums * 0.55
    # gentle movement
    mono *= 0.92 + 0.08 * np.sin(2.0 * math.pi * 0.12 * t, dtype=np.float32)
    return soft_clip(mono)


def to_stereo(mono: np.ndarray) -> np.ndarray:
    if mono.ndim == 2:
        return np.tanh(1.12 * mono).astype(np.float32)
    delay = int(0.012 * SR)
    l = mono
    r = np.roll(mono, delay)
    r[:delay] = 0.0
    st = np.stack([l * 0.92, r * 0.92], axis=-1) * 0.95
    return np.tanh(1.12 * st).astype(np.float32)


def render_wav(path: Path, stereo: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = stereo.shape[0]
    clean = np.nan_to_num(np.clip(stereo, -1.0, 1.0), nan=0.0, posinf=1.0, neginf=-1.0)
    pcm = (clean * 32767.0).astype(np.int16)
    inter = np.empty(n * 2, dtype=np.int16)
    inter[0::2] = pcm[:, 0]
    inter[1::2] = pcm[:, 1]
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(inter.tobytes())


def encode_mp3(wav_path: Path, mp3_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(mp3_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main() -> int:
    t = np.arange(0.0, DURATION_SEC, 1.0 / SR, dtype=np.float32)
    builders = {
        "am-blues-70bpm.mp3": build_am_blues,
        "am-drone-ambient.mp3": build_am_drone,
        "g-major-fingerpicking-80bpm.mp3": build_g_finger,
        "em-two-chord-90bpm.mp3": build_em_vamp,
        "g-major-ballad-65bpm.mp3": build_g_ballad,
    }
    tmp = Path(__file__).resolve().parent / "_tmp_backing.wav"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in builders.items():
        print("Rendering", name, flush=True)
        raw = fn(t)
        stereo = to_stereo(raw) if raw.ndim == 1 else raw
        render_wav(tmp, stereo)
        out_mp3 = OUT_DIR / name
        encode_mp3(tmp, out_mp3)
    tmp.unlink(missing_ok=True)
    print("Done. Wrote", len(builders), "files to", OUT_DIR, flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print("ffmpeg failed:", e, file=sys.stderr)
        raise SystemExit(1) from e
