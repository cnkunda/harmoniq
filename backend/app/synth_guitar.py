"""Synthetic guitar audio renderer using scipy additive synthesis.

Generates realistic guitar-like audio from chord descriptions without
requiring FluidSynth or system audio libraries. Uses additive synthesis
with guitar-like spectral shaping, amplitude envelopes, and physical
modeling characteristics (string decay, body resonance, fret buzz).

The approach:
1. Parse chord/note descriptions into MIDI note numbers
2. Generate per-string tones with guitar-like harmonics
3. Mix with realistic string noise and fret buzz
4. Apply body resonance EQ and random gain
5. Optionally apply reverb from the IR library

Usage:
    python -m app.synth_guitar --chord C:maj --output out.wav
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

TARGET_SR = 44100

# Standard guitar tuning (MIDI note numbers, low to high)
GUITAR_STRINGS = [40, 45, 50, 55, 59, 64]  # E2, A2, D3, G3, B3, E4

# Guitar-like harmonic amplitudes (fundamental + harmonics)
# Real guitar has strong fundamental, moderate 2nd/3rd, weak higher
GUITAR_HARMONICS = [1.0, 0.5, 0.3, 0.12, 0.05, 0.02, 0.01]

# Body resonance filter (bass boost, high rolloff)
BODY_RESONANCE = {
    "low_cutoff": 80,  # Hz
    "low_boost": 3.0,  # dB
    "high_cutoff": 6000,  # Hz
    "high_rolloff": -6.0,  # dB/octave
}


def _midi_to_freq(midi_note: int) -> float:
    """Convert MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def _note_to_string(midi_note: int) -> tuple[int, int]:
    """Find best string and fret for a MIDI note on a standard-tuned guitar.

    Returns (string_index, fret) where string 0 = low E, string 5 = high E.
    Prefers open strings and lower frets.
    """
    best_string = 0
    best_fret = 24

    for string_idx, open_note in enumerate(GUITAR_STRINGS):
        fret = midi_note - open_note
        if 0 <= fret <= 24 and fret < best_fret:
            best_fret = fret
            best_string = string_idx

    return best_string, best_fret


def _generate_note(
    freq: float,
    duration: float,
    sr: int = TARGET_SR,
    velocity: float = 0.8,
    is_bass: bool = False,
) -> np.ndarray:
    """Generate a single guitar-like note using additive synthesis.

    Args:
        freq: Note frequency in Hz
        duration: Note duration in seconds
        sr: Sample rate
        velocity: Note velocity (0-1)
        is_bass: Whether this is a bass note (fuller low-end)

    Returns:
        Audio array of shape (int(sr * duration),)
    """
    n_samples = max(1, int(sr * duration))
    t = np.arange(n_samples, dtype=np.float32) / sr

    # Pluck envelope: fast attack, exponential decay
    attack = 0.005  # 5ms attack
    decay = duration * np.random.uniform(0.4, 0.8)

    envelope = np.ones_like(t)
    attack_samples = min(n_samples, int(sr * attack))
    envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
    envelope[attack_samples:] = np.exp(
        -t[attack_samples:] / decay * 6.0
    )
    envelope *= velocity

    # Generate harmonics
    audio = np.zeros(n_samples, dtype=np.float32)
    for h_idx, h_amp in enumerate(GUITAR_HARMONICS):
        h_freq = freq * (h_idx + 1)
        h_amp_adj = h_amp

        # Bass notes get stronger fundamentals
        if is_bass and h_idx == 0:
            h_amp_adj *= 1.3

        # Higher harmonics decay faster
        h_decay = decay / (1.0 + h_idx * 0.5)
        h_envelope = np.exp(-t / h_decay * 6.0)
        h_envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
        h_envelope *= velocity * h_amp_adj

        # Add slight pitch drift for realism
        drift = 1.0 + 0.002 * np.sin(2 * np.pi * 3.0 * t)
        phase = 2 * np.pi * h_freq * drift * t
        audio += h_envelope * np.sin(phase)

    return audio


def _generate_string_noise(
    n_samples: int,
    sr: int = TARGET_SR,
) -> np.ndarray:
    """Generate realistic string noise (pick scrape, fret slide).

    Returns low-level noise burst with spectral shaping.
    """
    # Pink noise
    white = np.random.randn(n_samples).astype(np.float32)
    fft = np.fft.rfft(white)
    bins = np.arange(len(fft)) + 1
    fft = fft / np.sqrt(bins)
    noise = np.fft.irfft(fft, n=n_samples)

    # Amplitude envelope: short burst at start
    duration = n_samples / sr
    t = np.linspace(0, duration, n_samples)
    envelope = np.exp(-t * 40.0) * 0.03
    noise *= envelope

    return noise.astype(np.float32)


def _generate_fret_buzz(
    n_samples: int,
    freq: float,
    sr: int = TARGET_SR,
    probability: float = 0.05,
) -> np.ndarray:
    """Generate subtle fret buzz at low probability.

    Returns a short burst of high-frequency distortion.
    """
    if np.random.random() >= probability:
        return np.zeros(n_samples, dtype=np.float32)

    duration = n_samples / sr
    t = np.arange(n_samples, dtype=np.float32) / sr

    # High-frequency buzz at 2x the note frequency
    buzz_freq = freq * np.random.uniform(2, 4)
    buzz = np.sin(2 * np.pi * buzz_freq * t)

    # Very short, quiet burst
    envelope = np.exp(-t * 100.0) * 0.02
    return (buzz * envelope).astype(np.float32)


def apply_body_resonance(
    audio: np.ndarray,
    sr: int = TARGET_SR,
    strength: float = 0.3,
) -> np.ndarray:
    """Apply guitar body resonance EQ curve via FFT.

    Applies spectral shaping in the frequency domain:
    - Low-mid boost (~200-400Hz) for body warmth
    - High-frequency rolloff (~4kHz+) for darkness
    """
    n = len(audio)
    spectrum = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)

    # Warmth bump at 200-400Hz
    warm_mask = (freqs >= 100) & (freqs <= 600)
    warm_bump = 1.0 + strength * 0.8 * np.exp(
        -((freqs - 250) / 200) ** 2
    )

    # High rolloff above 3000Hz
    high_mask = freqs >= 3000
    rolloff = np.ones_like(freqs)
    rolloff[high_mask] = np.exp(
        -((freqs[high_mask] - 3000) / 3000) * strength * 2.0
    )

    filter_curve = warm_bump * rolloff
    spectrum = spectrum * filter_curve

    processed = np.fft.irfft(spectrum, n=n).astype(np.float32)

    peak = np.max(np.abs(processed))
    if peak > 0:
        processed = processed / peak * np.max(np.abs(audio))

    return processed


def apply_random_gain_shift(
    audio: np.ndarray,
    db_range: tuple[float, float] = (-3.0, 3.0),
) -> np.ndarray:
    """Apply random gain shift in dB."""
    db = np.random.uniform(*db_range)
    gain = 10.0 ** (db / 20.0)
    return (audio * gain).astype(np.float32)


def apply_random_eq_shift(
    audio: np.ndarray,
    sr: int = TARGET_SR,
) -> np.ndarray:
    """Apply random EQ shift to simulate different recording conditions."""
    from scipy import signal

    # Random low-shelf filter
    gain_db = np.random.uniform(-3.0, 3.0)
    freq = np.random.uniform(200, 800)
    gain = 10.0 ** (gain_db / 20.0)

    # Simple first-order shelving filter
    w0 = 2 * np.pi * freq / sr
    alpha = np.sin(w0) / 2.0

    b = np.array([gain * (1.0 + alpha), -gain * (1.0 - alpha)])
    a = np.array([1.0 + alpha, -(1.0 - alpha)])

    processed = signal.lfilter(b, a, audio)

    # Normalize
    peak = np.max(np.abs(processed))
    if peak > 0:
        processed = processed / peak * np.max(np.abs(audio))

    return processed.astype(np.float32)


def render_chord(
    root_midi: int,
    intervals: list[int],
    duration: float = 2.0,
    sr: int = TARGET_SR,
    velocity: float = 0.8,
    add_noise: bool = True,
    style: str = "strum",
) -> np.ndarray:
    """Render a chord as guitar audio.

    Args:
        root_midi: MIDI note number for the root
        intervals: List of semitone intervals from root
        duration: Duration in seconds
        sr: Sample rate
        velocity: Note velocity (0-1)
        add_noise: Whether to add string noise
        style: 'strum' (sequential strings) or 'block' (all at once)

    Returns:
        Audio array
    """
    n_samples = int(sr * duration)
    audio = np.zeros(n_samples, dtype=np.float32)

    # Convert intervals to MIDI note numbers
    notes = [root_midi + interval for interval in intervals]

    # Strum delay (ms between strings for strum style)
    strum_delay = 0.0
    strum_ms = 30.0 if style == "strum" else 0.0

    for i, midi_note in enumerate(notes):
        freq = _midi_to_freq(midi_note)
        note_dur = duration - strum_delay
        is_bass = midi_note <= 55  # Below G3

        note_audio = _generate_note(
            freq, max(note_dur, 0.1), sr,
            velocity=velocity * np.random.uniform(0.8, 1.0),
            is_bass=is_bass,
        )

        # Add strum delay
        delay_samples = int(sr * strum_delay)
        if delay_samples > 0:
            note_audio = np.pad(
                note_audio,
                (delay_samples, 0),
                mode="constant",
            )[:n_samples]

        audio += note_audio[:n_samples]

        strum_delay += strum_ms / 1000.0

    # Add string noise
    if add_noise:
        audio += _generate_string_noise(n_samples, sr)

    # Add fret buzz on random notes
    for midi_note in notes:
        freq = _midi_to_freq(midi_note)
        audio += _generate_fret_buzz(n_samples, freq, sr)

    # Apply body resonance
    audio = apply_body_resonance(audio, sr)

    # Normalize
    peak = np.max(np.abs(audio))
    if peak > 0.001:
        audio = audio / peak * 0.95

    return audio.astype(np.float32)


def render_melody_note(
    midi_note: int,
    duration: float = 0.5,
    sr: int = TARGET_SR,
    velocity: float = 0.9,
) -> np.ndarray:
    """Render a single melody note (picked style)."""
    freq = _midi_to_freq(midi_note)
    audio = _generate_note(freq, duration, sr, velocity=velocity)

    # Picked notes have brighter attack
    audio = apply_body_resonance(audio, sr, strength=0.15)

    peak = np.max(np.abs(audio))
    if peak > 0.001:
        audio = audio / peak * 0.95

    return audio.astype(np.float32)


def render_to_wav(
    audio: np.ndarray,
    output_path: Path,
    sr: int = TARGET_SR,
) -> None:
    """Write audio array to WAV file."""
    import soundfile as sf
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), audio, sr)


if __name__ == "__main__":
    import argparse

    from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES

    parser = argparse.ArgumentParser(
        description="Render synthetic guitar audio")
    parser.add_argument("--chord", type=str, default="C:maj",
                        help="Chord to render (e.g. C:maj, G:7)")
    parser.add_argument("--root-midi", type=int, default=48,
                        help="Root MIDI note (C3=48)")
    parser.add_argument("--duration", type=float, default=2.0,
                        help="Duration in seconds")
    parser.add_argument("--style", choices=["strum", "block"], default="strum",
                        help="Playing style")
    parser.add_argument("--output", type=str, default="/tmp/synth_chord.wav",
                        help="Output WAV path")
    args = parser.parse_args()

    # Parse chord
    if ":" in args.chord:
        root_name, quality = args.chord.split(":")
    elif args.chord == "N":
        root_name, quality = "C", "maj"
    else:
        root_name, quality = args.chord[0], args.chord[1:]

    if root_name in ROOT_NOTES:
        root_idx = ROOT_NOTES.index(root_name)
        root_midi = args.root_midi + root_idx
    else:
        root_midi = args.root_midi

    intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])

    print(f"Rendering {args.chord} (root={root_midi}, intervals={intervals})")
    audio = render_chord(root_midi, intervals, args.duration, style=args.style)
    render_to_wav(audio, Path(args.output))
    print(f"Saved to {args.output} ({len(audio)} samples, "
          f"duration={len(audio)/TARGET_SR:.1f}s)")
