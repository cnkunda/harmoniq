"""MRT2 (Magenta RealTime 2) music generation + bundled fallback for Jam practice beds."""

from __future__ import annotations

import io
import logging
import math
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import wave

import numpy as np

logger = logging.getLogger("harmoniq.jam_backing")
logger.setLevel(logging.INFO)

BACKING_DURATION_SECS = 16

class Mrt2BackingError(RuntimeError):
    """MRT2 generation failure."""

@dataclass(frozen=True)
class BundledBackingTrack:
    filename: str
    key_label: str
    bpm: int | None
    tags: tuple[str, ...]

_BUNDLED_TRACKS: tuple[BundledBackingTrack, ...] = (
    BundledBackingTrack(
        filename="am-blues-70bpm.mp3",
        key_label="A minor",
        bpm=70,
        tags=("blues", "shuffle", "timing", "groove"),
    ),
    BundledBackingTrack(
        filename="am-drone-ambient.mp3",
        key_label="A minor",
        bpm=None,
        tags=("ambient", "drone", "vibrato", "sustain"),
    ),
    BundledBackingTrack(
        filename="g-major-fingerpicking-80bpm.mp3",
        key_label="G major",
        bpm=80,
        tags=("fingerpicking", "acoustic", "phrasing"),
    ),
    BundledBackingTrack(
        filename="em-two-chord-90bpm.mp3",
        key_label="E minor",
        bpm=90,
        tags=("rock", "indie", "two-chord", "energy"),
    ),
    BundledBackingTrack(
        filename="g-major-ballad-65bpm.mp3",
        key_label="G major",
        bpm=65,
        tags=("ballad", "slow", "pitch", "soulful"),
    ),
)
_WAV_CACHE: dict[str, tuple[bytes, int]] = {}

# ---- MRT2 Backing Generator (singleton) ----

class Mrt2BackingGenerator:
    """MRT2-based backing track generator. Singleton, lazy-loaded on first use."""

    _instance: Mrt2BackingGenerator | None = None

    def __new__(cls) -> Mrt2BackingGenerator:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _lazy_init(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self.available = False
        self.model_type: str | None = None
        self._system: Any = None
        try:
            self._system = self._try_load()
            self.available = True
        except Exception as exc:
            logger.warning("Mrt2BackingGenerator unavailable: %s", exc)

    def _try_load(self) -> Any:
        from magenta_rt import MagentaRT2Jax

        system = MagentaRT2Jax(size="mrt2_small", temperature=1.3, top_k=40, cfg_musiccoca=3.0)
        self.model_type = "mrt2_small"
        return system

    def generate(
        self,
        *,
        prompt: str,
        duration_secs: int = BACKING_DURATION_SECS,
    ) -> tuple[bytes, int] | None:
        """Generate a backing track from a text prompt.

        Returns (wav_bytes, duration_ms) or None if unavailable.
        """
        self._lazy_init()
        if not self.available or self._system is None:
            return None

        try:
            style = self._system.embed_style(prompt)
            num_frames = duration_secs * 25
            wav, _state = self._system.generate(style=style, frames=num_frames)

            buf = io.BytesIO()
            _write_wav(buf, wav.samples, wav.sample_rate)
            wav_bytes = buf.getvalue()
            duration_ms = duration_secs * 1000
            return wav_bytes, duration_ms
        except Exception as exc:
            logger.warning("MRT2 generation failed: %s", exc)
            return None


def _write_wav(buf: io.BytesIO, samples: np.ndarray, sample_rate: int) -> None:
    """Write float32 numpy samples to a WAV file in BytesIO."""
    if samples.ndim == 1:
        samples = samples[:, None]
    num_channels = samples.shape[1]
    int_samples = np.clip(samples * 32767, -32768, 32767).astype("<i2")
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int_samples.tobytes())


# ---- Prompt building ----


def build_mrt2_prompt(style_hint: str, musical_key: str, bpm: int | None) -> str:
    """Build a text prompt for MRT2 from the user's practice preferences."""
    parts: list[str] = [
        style_hint.strip() if style_hint else "Instrumental guitar practice backing track",
        f"Key: {musical_key}",
    ]
    if bpm is not None:
        parts.append(f"Tempo: approximately {bpm} BPM, consistent tempo")
    parts.extend([
        "Rhythm section: drums, bass, comping guitar, optional light keys",
        "Steady loop-friendly groove, no vocals",
        "Clean mix, moderate dynamics",
    ])
    return ", ".join(parts)


# ---- Bundled fallback ----


def _backing_tracks_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "assets" / "backing-tracks"


def select_bundled_track(musical_key: str, bpm: int | None, style_hint: str | None) -> BundledBackingTrack:
    key_norm = (musical_key or "").strip().lower()
    style_norm = (style_hint or "").strip().lower()

    def score_track(track: BundledBackingTrack) -> tuple[int, int, int]:
        key_score = 2 if track.key_label.lower() == key_norm else (1 if track.key_label.lower() in key_norm else 0)
        style_score = sum(1 for tag in track.tags if tag in style_norm)
        if bpm is None or track.bpm is None:
            bpm_score = 0
        else:
            bpm_score = -abs(track.bpm - bpm)
        return (key_score, style_score, bpm_score)

    return max(_BUNDLED_TRACKS, key=score_track)


def _wav_duration_ms(raw_wav: bytes) -> int:
    with wave.open(io.BytesIO(raw_wav), "rb") as wf:
        frame_rate = wf.getframerate() or 44100
        frames = wf.getnframes()
    return int(round((frames / float(frame_rate)) * 1000))


def _ffmpeg_mp3_to_wav_bytes(path: Path) -> bytes:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg not found on PATH")
    proc = subprocess.run(
        [
            ffmpeg_bin,
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "wav",
            "-ar",
            "44100",
            "-ac",
            "2",
            "pipe:1",
        ],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        stderr = proc.stderr.decode("utf-8", errors="ignore").strip()[:300]
        raise RuntimeError(f"ffmpeg conversion failed: {stderr}")
    return proc.stdout


def _synthetic_wav_fallback(duration_sec: float = 16.0) -> bytes:
    sr = 44100
    total = int(duration_sec * sr)
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(total):
            t = i / float(sr)
            sample = (
                0.35 * math.sin(2 * math.pi * 110.0 * t)
                + 0.18 * math.sin(2 * math.pi * 138.59 * t)
                + 0.16 * math.sin(2 * math.pi * 164.81 * t)
            )
            sample_i = int(max(-1.0, min(1.0, sample)) * 32767)
            frame = struct.pack("<hh", sample_i, sample_i)
            wf.writeframesraw(frame)
    return out.getvalue()


def load_bundled_track_wav(track: BundledBackingTrack) -> tuple[bytes, int]:
    cached = _WAV_CACHE.get(track.filename)
    if cached is not None:
        return cached

    path = _backing_tracks_root() / track.filename
    if not path.is_file():
        raise RuntimeError(f"Bundled backing track not found: {path}")
    try:
        wav_bytes = _ffmpeg_mp3_to_wav_bytes(path)
    except Exception:
        wav_bytes = _synthetic_wav_fallback()
    duration_ms = _wav_duration_ms(wav_bytes)
    _WAV_CACHE[track.filename] = (wav_bytes, duration_ms)
    return wav_bytes, duration_ms
