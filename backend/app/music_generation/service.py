"""Generation orchestration: provider chain, deadlines, honest provenance."""
from __future__ import annotations

import asyncio
import os
from typing import Protocol, Sequence

from app.jam_backing import _wav_duration_ms, build_mrt2_prompt
from app.music_generation.postprocess import prepare_generated_backing
from app.music_generation.registry import build_provider_chain
from app.music_generation.types import BackingRequest, GeneratedBacking


class BackingProviderProtocol(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def generate(self, req: BackingRequest) -> GeneratedBacking: ...


def _timeout_s() -> float:
    try:
        return max(1.0, float(os.getenv("HARMONIQ_BACKING_TIMEOUT_S", "45")))
    except ValueError:
        return 45.0


async def generate_with_providers(
    req: BackingRequest,
    providers: Sequence[BackingProviderProtocol],
    timeout_s: float | None = None,
) -> GeneratedBacking:
    """Try providers in order, returning the first success with provenance.

    Failures are recorded in ``attempts``/``fallback_reason`` rather than hidden.
    """
    deadline = timeout_s if timeout_s is not None else _timeout_s()
    attempts: list[str] = []
    for index, provider in enumerate(providers):
        name = getattr(provider, "name", type(provider).__name__)
        if not provider.is_available():
            attempts.append(f"{name}:unavailable")
            continue
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(provider.generate, req),
                timeout=deadline,
            )
            verify = getattr(provider, "verify_musical_quality", name not in {"bundled", "synth"})
            if verify:
                try:
                    prepared, analysis = await asyncio.wait_for(
                        asyncio.to_thread(
                            prepare_generated_backing,
                            result.wav_bytes,
                            musical_key=req.musical_key,
                            bpm=req.bpm,
                        ),
                        timeout=deadline,
                    )
                except ValueError as exc:
                    attempts.append(f"{name}:verify:{exc}")
                    continue
                result.wav_bytes = prepared
                result.duration_ms = _wav_duration_ms(prepared)
                result.key_label = analysis.key_label
                result.key_confidence = analysis.key_confidence
                result.bpm = analysis.bpm
                result.beat_grid = analysis.beat_grid
        except asyncio.TimeoutError:
            attempts.append(f"{name}:timeout")
            continue
        except Exception as exc:  # noqa: BLE001 - provider errors are recorded, not swallowed
            attempts.append(f"{name}:{type(exc).__name__}")
            continue
        if index > 0 and result.provider not in {"bundled", "synth"}:
            result.used_fallback = True
        result.attempts = attempts
        if attempts and result.fallback_reason is None:
            result.fallback_reason = ";".join(attempts)
        return result
    raise RuntimeError(f"No backing provider succeeded: {'; '.join(attempts) or 'chain empty'}")


async def generate_backing(req: BackingRequest) -> GeneratedBacking:
    """Build the prompt and run the configured chain."""
    prompt = build_mrt2_prompt(
        style_hint=req.style_hint or "",
        musical_key=req.musical_key,
        bpm=req.bpm,
        weak_areas=req.weak_areas,
        chord_progression=req.chord_progression,
    )
    return await generate_with_providers(
        req.with_prompt(prompt),
        build_provider_chain(req.model),
    )
