"""Ordered provider registry for jam-backing generation."""
from __future__ import annotations

import os

from app.music_generation.providers import (
    BundledBackingProvider,
    Mrt2BackingProvider,
    RemoteBackingProvider,
    SynthBackingProvider,
)

DEFAULT_PROVIDER_SPEC = "ace_step_modal,lyria,mrt2,bundled"

# Provider name -> zero-arg factory. Remote entries are inert until their URL env is set.
_FACTORIES = {
    "ace_step_modal": lambda: RemoteBackingProvider(
        name="ace_step_modal",
        url_env="HARMONIQ_ACE_STEP_BACKING_URL",
        token_env="HARMONIQ_MODAL_TOKEN",
    ),
    "lyria": lambda: RemoteBackingProvider(
        name="lyria",
        url_env="HARMONIQ_LYRIA_BACKING_URL",
        token_env="GEMINI_API_KEY",
    ),
    "mrt2": Mrt2BackingProvider,
    "bundled": BundledBackingProvider,
    "synth": SynthBackingProvider,
}


def provider_names(model: str | None = None) -> list[str]:
    """Resolve the ordered chain; ``model`` may pin a provider first."""
    raw = os.getenv("HARMONIQ_BACKING_PROVIDERS", DEFAULT_PROVIDER_SPEC)
    names = [part.strip() for part in raw.split(",") if part.strip()]
    names = [name for name in names if name in _FACTORIES]
    if model:
        requested = model.strip().lower()
        if requested in _FACTORIES:
            names = [requested] + [name for name in names if name != requested]
    # Guarantee a last resort so the practice flow never dead-ends.
    if "synth" not in names:
        names.append("synth")
    return names


def build_provider_chain(model: str | None = None) -> list[object]:
    """Instantiate providers in order (callers use the protocol methods)."""
    return [_FACTORIES[name]() for name in provider_names(model)]
