"""Musical verification + loop preparation for generated backing audio (J3).

A generated bed is only useful for practice if it matches the requested key/tempo
and loops cleanly. This module analyzes the clip, rejects confident mismatches,
trims to the last downbeat, and applies a short click-free loop envelope.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np

from app.key_detection import PITCH_NAMES, estimate_key_from_chroma

_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
_KEY_CONFIDENCE_FOR_REJECT = 0.5
_BPM_TOLERANCE = 0.06
_SEAM_FADE_MS = 25


@dataclass
class BackingAnalysis:
    key_label: str | None = None
    key_confidence: float = 0.0
    bpm: float | None = None
    beat_grid: dict[str, object] | None = None
    notes: list[str] = field(default_factory=list)


def normalize_requested_key(musical_key: str) -> tuple[str | None, str | None]:
    """Parse ``"A minor"``/``"F# major"``/``"Bb"`` into ``(root, mode)``."""
    match = re.match(r"^\s*([A-Ga-g][#b]?)(?:\s*(major|minor|maj|min))?", musical_key)
    if not match:
        return None, None
    root = match.group(1)
    root = root[0].upper() + root[1:]
    root = _FLAT_TO_SHARP.get(root, root)
    if root not in PITCH_NAMES:
        return None, None
    raw_mode = (match.group(2) or "").lower()
    if raw_mode in {"major", "maj"}:
        mode = "major"
    elif raw_mode in {"minor", "min"}:
        mode = "minor"
    else:
        mode = None
    return root, mode


def key_mismatch_reason(
    requested_key: str | None,
    detected_key: str | None,
    confidence: float,
) -> str | None:
    """Return a reason when a *confident* detected key contradicts the request."""
    if not requested_key or not detected_key or confidence < _KEY_CONFIDENCE_FOR_REJECT:
        return None
    requested_root, requested_mode = normalize_requested_key(requested_key)
    detected_root, detected_mode = normalize_requested_key(detected_key)
    if requested_root is None or detected_root is None:
        return None
    if requested_root != detected_root:
        return f"key_mismatch: requested {requested_root}, detected {detected_root} (conf {confidence:.2f})"
    if requested_mode and detected_mode and requested_mode != detected_mode:
        return f"mode_mismatch: requested {requested_root} {requested_mode}, detected {detected_root} {detected_mode} (conf {confidence:.2f})"
    return None


def bpm_mismatch_reason(requested_bpm: int | None, detected_bpm: float | None) -> str | None:
    """Reject only gross tempo errors; half/double-time feels are legitimate."""
    if not requested_bpm or not detected_bpm or detected_bpm <= 0:
        return None
    ratio = detected_bpm / float(requested_bpm)
    for candidate in (ratio, ratio * 2.0, ratio / 2.0):
        if abs(candidate - 1.0) <= _BPM_TOLERANCE:
            return None
    return f"tempo_mismatch: requested {requested_bpm} BPM, detected {detected_bpm:.1f} BPM"


def trim_and_envelope(
    samples: np.ndarray,
    sample_rate: int,
    downbeats: list[float],
) -> tuple[np.ndarray, float | None]:
    """Trim to the last downbeat and apply a short fade at the loop seam.

    ``samples`` is float32/float64 shaped ``(frames, channels)`` or ``(frames,)``.
    Returns the prepared samples and the trimmed end time (seconds).
    """
    mono = samples[:, 0] if samples.ndim > 1 else samples
    end_time: float | None = None
    if downbeats and len(downbeats) >= 2:
        candidate = float(downbeats[-1])
        if 0.25 * len(mono) / sample_rate < candidate <= len(mono) / sample_rate:
            end_time = candidate
    end = len(mono) if end_time is None else min(len(mono), int(end_time * sample_rate))
    if end < 2:
        return samples, None
    out = np.array(samples[:end], copy=True)
    fade = min(int(sample_rate * _SEAM_FADE_MS / 1000), end // 2)
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        if out.ndim > 1:
            out[:fade] *= ramp[:, None]
            out[-fade:] *= ramp[::-1][:, None]
        else:
            out[:fade] *= ramp
            out[-fade:] *= ramp[::-1]
    return out, (end_time if end_time is not None else end / sample_rate)


def analyze_wav(wav_bytes: bytes) -> BackingAnalysis:
    """Detect key, tempo, and beat grid for a WAV clip."""
    import librosa
    import soundfile as sf
    import tempfile
    from pathlib import Path

    from app.beat_grid import estimate_beat_grid

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_bytes)
        path = Path(tmp.name)
    try:
        grid = estimate_beat_grid(path)
        y, sr = librosa.load(str(path), sr=22050, mono=True)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
        root, mode, confidence = estimate_key_from_chroma(chroma.tolist())
    finally:
        path.unlink(missing_ok=True)
    return BackingAnalysis(
        key_label=f"{PITCH_NAMES[root]} {mode}",
        key_confidence=float(confidence),
        bpm=float(grid.get("pulse_bpm") or grid.get("bpm") or 0.0) or None,
        beat_grid=grid,
    )


def prepare_generated_backing(
    wav_bytes: bytes,
    *,
    musical_key: str,
    bpm: int | None,
) -> tuple[bytes, BackingAnalysis]:
    """Analyze, reject mismatches, trim/envelope, and re-encode a generated bed.

    Raises ``ValueError`` when the clip contradicts the requested key/tempo.
    """
    import soundfile as sf

    analysis = analyze_wav(wav_bytes)
    reason = key_mismatch_reason(musical_key, analysis.key_label, analysis.key_confidence)
    if reason is None:
        reason = bpm_mismatch_reason(bpm, analysis.bpm)
    if reason is not None:
        raise ValueError(reason)

    data, sr = sf.read(io.BytesIO(wav_bytes), always_2d=True)
    downbeats = list(analysis.beat_grid.get("downbeats", [])) if analysis.beat_grid else []
    prepared, _end = trim_and_envelope(data, sr, [float(t) for t in downbeats])
    buf = io.BytesIO()
    sf.write(buf, prepared, sr, format="WAV")
    return buf.getvalue(), analysis
