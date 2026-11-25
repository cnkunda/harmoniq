"""Concrete backing providers: remote GPU, local MRT2, bundled loops, synth last resort."""
from __future__ import annotations

import base64
import json
import os
from typing import Any
from urllib.parse import urlparse

import httpx

from app.jam_backing import (
    Mrt2BackingGenerator,
    _synthetic_wav_fallback,
    _wav_duration_ms,
    load_bundled_track_wav,
    select_bundled_track,
)
from app.music_generation.types import (
    BackingRequest,
    GeneratedBacking,
    ProviderUnavailable,
)

_MAX_REMOTE_BYTES = 32 * 1024 * 1024


class RemoteBackingProvider:
    """Calls a warm cloud endpoint (Modal/Cerebrium/Lyria proxy) over HTTP.

    Contract: POST JSON ``{prompt, musical_key, bpm, duration_secs, seed, model}``.
    Response must be raw ``audio/wav`` bytes or JSON ``{"audio_base64": ...}``.
    """

    verify_musical_quality = True

    def __init__(self, name: str, url_env: str, token_env: str | None = None) -> None:
        self.name = name
        self._url_env = url_env
        self._token_env = token_env

    def is_available(self) -> bool:
        url = os.getenv(self._url_env, "").strip()
        return bool(url) and urlparse(url).scheme in {"http", "https"}

    def generate(self, req: BackingRequest) -> GeneratedBacking:
        url = os.getenv(self._url_env, "").strip()
        if not url:
            raise ProviderUnavailable(f"{self.name}: {self._url_env} is not set")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token_env:
            token = os.getenv(self._token_env, "").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        payload = {
            "prompt": req.prompt,
            "musical_key": req.musical_key,
            "bpm": req.bpm,
            "duration_secs": req.duration_secs,
            "seed": req.seed,
            "model": req.model or self.name,
        }
        timeout_s = float(os.getenv("HARMONIQ_BACKING_TIMEOUT_S", "45"))
        with httpx.Client(timeout=timeout_s) as client:
            res = client.post(url, json=payload, headers=headers)
        if res.status_code != 200:
            raise ProviderUnavailable(f"{self.name}: HTTP {res.status_code}")
        if len(res.content) > _MAX_REMOTE_BYTES:
            raise ProviderUnavailable(f"{self.name}: response exceeds {_MAX_REMOTE_BYTES} bytes")
        content_type = res.headers.get("content-type", "")
        if "application/json" in content_type:
            body: dict[str, Any] = json.loads(res.content)
            raw_b64 = body.get("audio_base64")
            if not isinstance(raw_b64, str) or not raw_b64:
                raise ProviderUnavailable(f"{self.name}: JSON response missing audio_base64")
            raw = base64.b64decode(raw_b64)
        elif "audio" in content_type or res.content[:4] == b"RIFF":
            raw = res.content
        else:
            raise ProviderUnavailable(f"{self.name}: unexpected content-type {content_type!r}")
        return GeneratedBacking(
            wav_bytes=raw,
            duration_ms=_wav_duration_ms(raw),
            provider=self.name,
            prompt_used=req.prompt,
            sample_rate=48000,
        )


class Mrt2BackingProvider:
    """Local Magenta RealTime 2 (CPU) — slow but zero external dependencies."""

    name = "mrt2"
    verify_musical_quality = True

    def __init__(self) -> None:
        self._generator = Mrt2BackingGenerator()

    def is_available(self) -> bool:
        return True

    def generate(self, req: BackingRequest) -> GeneratedBacking:
        result = self._generator.generate(
            prompt=req.prompt,
            duration_secs=max(1, int(round(req.duration_secs))),
        )
        if result is None:
            raise ProviderUnavailable("mrt2: generation returned no audio")
        raw, duration_ms = result
        return GeneratedBacking(
            wav_bytes=raw,
            duration_ms=duration_ms,
            provider=self.name,
            prompt_used=req.prompt,
            sample_rate=48000,
        )


class BundledBackingProvider:
    """Bundled practice loops — always available, honest fallback metadata."""

    name = "bundled"
    verify_musical_quality = False

    def is_available(self) -> bool:
        return True

    def generate(self, req: BackingRequest) -> GeneratedBacking:
        track = select_bundled_track(
            musical_key=req.musical_key,
            bpm=req.bpm,
            style_hint=req.style_hint,
        )
        raw, duration_ms = load_bundled_track_wav(track)
        return GeneratedBacking(
            wav_bytes=raw,
            duration_ms=duration_ms,
            provider=self.name,
            prompt_used=f"{req.prompt} [fallback_track={track.filename}]",
            used_fallback=True,
            sample_rate=44100,
        )


class SynthBackingProvider:
    """Emergency sine-bed used only when even bundled assets fail."""

    name = "synth"
    verify_musical_quality = False

    def is_available(self) -> bool:
        return True

    def generate(self, req: BackingRequest) -> GeneratedBacking:
        raw = _synthetic_wav_fallback()
        return GeneratedBacking(
            wav_bytes=raw,
            duration_ms=_wav_duration_ms(raw),
            provider=self.name,
            prompt_used=req.prompt,
            used_fallback=True,
            fallback_reason="bundled assets unavailable",
            sample_rate=44100,
        )
