"""Tab catalog provider selection (env-driven stub for development)."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field


class TabSearchHit(BaseModel):
    id: str
    title: str
    artist: str | None = None
    source: str = "stub"


class TabSearchResponse(BaseModel):
    hits: list[TabSearchHit] = Field(default_factory=list)
    provider: str


def get_tab_catalog_mode() -> str:
    raw = (os.getenv("HARMONIQ_TAB_CATALOG") or "stub").strip().lower()
    if raw in {"stub", "none"}:
        return raw
    return "stub"


def search_tabs(query: str) -> TabSearchResponse:
    """Return catalog search hits. ``none`` yields an empty list; ``stub`` returns deterministic demo rows."""
    mode = get_tab_catalog_mode()
    if mode == "none":
        return TabSearchResponse(hits=[], provider="none")

    q = query.strip()
    if not q:
        return TabSearchResponse(hits=[], provider="stub")

    demo: list[dict[str, Any]] = [
        {
            "id": "harmoniq-stub-1",
            "title": f"Example match: {q[:48]}{'…' if len(q) > 48 else ''}",
            "artist": "Stub catalog (replace with licensed provider)",
            "source": "stub",
        },
        {
            "id": "harmoniq-stub-2",
            "title": "Second demo row — GP5 download not implemented yet",
            "artist": None,
            "source": "stub",
        },
    ]
    return TabSearchResponse(hits=[TabSearchHit.model_validate(h) for h in demo], provider="stub")
