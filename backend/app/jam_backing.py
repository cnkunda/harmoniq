"""Gemini/Lyria music generation + local fallback for Jam practice beds."""

from __future__ import annotations

import base64
import io
import math
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import wave

import httpx

DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_LYRIA_MODEL = "lyria-realtime-exp"
DEFAULT_OUTPUT_SAMPLE_RATE = 44100


class LyriaProviderError(RuntimeError):
    """Provider-level failure with coarse error classification."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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


def build_instrumental_prompt(
    musical_key: str,
    bpm: int | None,
    weak_areas: list[str],
    style_hint: str | None,
) -> str:
    """Deterministic Lyria prompt with strongly instrumental constraints."""
    parts: list[str] = [
        "Create a cohesive instrumental guitar practice backing track with no vocals or spoken words.",
        "Rhythm section only: drums, bass, comping guitar, optional light keys — steady loop-friendly groove.",
        f"Musical key: {musical_key}.",
    ]
    if bpm is not None:
        parts.append(f"Approximately {bpm} BPM, consistent tempo.")
    if weak_areas:
        joined = ", ".join(weak_areas)
        parts.append(f"Player focus areas: {joined}.")
        lowered = {a.lower() for a in weak_areas}
        if "timing" in lowered:
            parts.append("Emphasize clear downbeats and a locked drum kit for timing practice.")
        if "pitch" in lowered or "bending" in lowered:
            parts.append("Consonant harmony, simple changes, easy to hear intonation.")
        if "phrasing" in lowered:
            parts.append("Spacious comping with breathing room between chord stabs.")
        if "vibrato" in lowered:
            parts.append("Warm pads and smooth harmonic rhythm suitable for sustained notes.")
    parts.append("Production: clean mix, moderate dynamics, no clipping, smooth transitions.")
    if style_hint and style_hint.strip():
        parts.append(style_hint.strip())
    text = " ".join(parts).strip()
    return text[:2000]


def _decode_b64_audio(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise LyriaProviderError("invalid_response", "Gemini response audio bytes were invalid base64.") from exc


def _parse_lyria_audio(body: dict[str, Any]) -> tuple[bytes, int | None]:
    """Parse common Gemini/Lyria response shapes into raw audio bytes."""
    generated = body.get("generatedMusic")
    if isinstance(generated, dict):
        encoded = generated.get("audioBytes")
        if isinstance(encoded, str) and encoded.strip():
            raw = _decode_b64_audio(encoded.strip())
            duration_ms = generated.get("durationMs")
            return raw, duration_ms if isinstance(duration_ms, int) else None

    candidates = body.get("candidates")
    if isinstance(candidates, list):
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            content = cand.get("content") or {}
            parts = content.get("parts") or []
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                inline = part.get("inlineData")
                if not isinstance(inline, dict):
                    continue
                encoded = inline.get("data")
                if isinstance(encoded, str) and encoded.strip():
                    raw = _decode_b64_audio(encoded.strip())
                    return raw, None

    raise LyriaProviderError("invalid_response", "Gemini/Lyria response did not include audio data.")


def _classify_provider_status(status_code: int) -> str:
    if status_code in (401, 403):
        return "auth"
    if status_code == 429:
        return "rate_limit"
    if status_code in (402,):
        return "quota"
    return "unavailable"


async def call_gemini_lyria_instrumental(
    *,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[bytes, int | None]:
    """Call Gemini/Lyria and return raw audio bytes."""
    clean_model = model.strip().strip("/")
    url = f"{base_url.rstrip('/')}/models/{clean_model}:generateContent?key={api_key}"
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "temperature": 0.8,
            "topP": 0.9,
            "audioTimestamp": True,
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "none"}},
            },
        },
    }
    headers = {
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(120.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code >= 400:
        text = (resp.text or "").strip()[:500]
        code = _classify_provider_status(resp.status_code)
        raise LyriaProviderError(code, f"Gemini/Lyria HTTP {resp.status_code}: {text}")

    try:
        body = resp.json()
    except ValueError as exc:
        raise LyriaProviderError("invalid_response", "Gemini/Lyria returned a non-JSON response.") from exc

    return _parse_lyria_audio(body)


def gemini_lyria_config() -> tuple[str | None, str, str]:
    """API key, base URL, model name."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    base = os.getenv("GEMINI_API_BASE", DEFAULT_GEMINI_BASE).strip() or DEFAULT_GEMINI_BASE
    model = os.getenv("LYRIA_MODEL", DEFAULT_LYRIA_MODEL).strip() or DEFAULT_LYRIA_MODEL
    return (key or None), base, model


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
        frame_rate = wf.getframerate() or DEFAULT_OUTPUT_SAMPLE_RATE
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
            str(DEFAULT_OUTPUT_SAMPLE_RATE),
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
    sr = DEFAULT_OUTPUT_SAMPLE_RATE
    total = int(duration_sec * sr)
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(total):
            t = i / float(sr)
            # Soft triad-like blend for emergency fallback only.
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
