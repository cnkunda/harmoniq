"""Types for pluggable jam-backing generation providers."""
from __future__ import annotations

from dataclasses import dataclass, field


class BackingProviderError(RuntimeError):
    """Base class for provider failures (never silently swallowed)."""


class ProviderUnavailable(BackingProviderError):
    """Provider is not configured/installed; skip to the next provider."""


class ProviderTimeout(BackingProviderError):
    """Provider exceeded its per-attempt deadline."""


@dataclass(frozen=True)
class BackingRequest:
    """Normalized generation request (also the future cache key)."""

    musical_key: str
    bpm: int | None = None
    style_hint: str | None = None
    weak_areas: tuple[str, ...] = ()
    chord_progression: tuple[str, ...] = ()
    duration_secs: float = 16.0
    model: str | None = None
    seed: int | None = None
    prompt: str = ""

    def with_prompt(self, prompt: str) -> "BackingRequest":
        return BackingRequest(
            musical_key=self.musical_key,
            bpm=self.bpm,
            style_hint=self.style_hint,
            weak_areas=self.weak_areas,
            chord_progression=self.chord_progression,
            duration_secs=self.duration_secs,
            model=self.model,
            seed=self.seed,
            prompt=prompt,
        )


@dataclass
class GeneratedBacking:
    """Result of a successful generation, with provenance the UI can trust."""

    wav_bytes: bytes
    duration_ms: int
    provider: str
    prompt_used: str
    used_fallback: bool = False
    fallback_reason: str | None = None
    sample_rate: int | None = None
    key_label: str | None = None
    key_confidence: float | None = None
    bpm: float | None = None
    beat_grid: dict[str, object] | None = None
    attempts: list[str] = field(default_factory=list)
