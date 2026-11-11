"""Pluggable jam-backing music generation (ACE-Step/Lyria/MRT2/bundled)."""
from __future__ import annotations

from app.music_generation.service import generate_backing
from app.music_generation.types import (
    BackingProviderError,
    BackingRequest,
    GeneratedBacking,
    ProviderTimeout,
    ProviderUnavailable,
)

__all__ = [
    "BackingProviderError",
    "BackingRequest",
    "GeneratedBacking",
    "ProviderTimeout",
    "ProviderUnavailable",
    "generate_backing",
]
