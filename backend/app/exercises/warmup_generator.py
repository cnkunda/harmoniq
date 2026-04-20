"""Personalized 3-minute warm-up assembly (commit 73)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas import FretboardGuide, PlayerProfile, TasteProfile, WarmupExercise, WarmupPlan

_POOL_PATH = Path(__file__).resolve().parent / "warmup_pool.json"


def _load_pool() -> list[dict[str, Any]]:
    raw = _POOL_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError("warmup_pool.json must be a JSON array")
    return [x for x in data if isinstance(x, dict)]


def _norm_weak(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _rng(seed: int) -> int:
    # deterministic 32-bit LCG for stable picks in tests
    return (seed * 1103515245 + 12345) & 0x7FFFFFFF


def _pick_index(seed: int, n: int) -> int:
    if n <= 0:
        return 0
    return _rng(seed) % n


def _fretboard_guide_from_row(row: dict[str, Any]) -> FretboardGuide | None:
    raw = row.get("fretboard_guide")
    if not raw or not isinstance(raw, dict):
        return None
    return FretboardGuide.model_validate(raw)


def _style_matches(style_label: str, style_tags: list[str]) -> bool:
    if not style_tags:
        return True
    sl = (style_label or "").lower()
    if "general" in style_tags:
        return True
    return any(tag and tag.lower() in sl for tag in style_tags)


def generate_warmup(
    player_profile: PlayerProfile | None,
    taste_profile: TasteProfile | None,
    *,
    session_bpm: int | None = None,
    seed: int = 0,
) -> WarmupPlan:
    """
    Build three exercises: chromatic/spider opener, weak-area technique, style feel.
    Exercise BPM defaults to 70% of taste comfort low (or session_bpm when provided).
    """
    pool = _load_pool()
    profile = player_profile or PlayerProfile()
    taste = taste_profile or TasteProfile()
    comfort = taste.bpm_comfort_range
    low = int(comfort[0]) if comfort and len(comfort) > 0 else 80
    base_input = int(session_bpm) if session_bpm is not None else low
    exercise_bpm = max(40, min(240, int(base_input * 0.7)))

    weak_raw = (profile.weak_areas[0] if profile.weak_areas else "") or ""
    weak_key = _norm_weak(weak_raw) or "timing"

    chromatics = [x for x in pool if x.get("opener_kind") == "chromatic"]
    spiders = [x for x in pool if x.get("opener_kind") == "spider"]
    use_spider = _pick_index(seed, 2) == 0 and spiders
    opener_bucket = spiders if use_spider and spiders else chromatics or spiders or pool
    opener = opener_bucket[_pick_index(seed + 1, len(opener_bucket))]

    weak_candidates = [
        x
        for x in pool
        if not x.get("opener_kind")
        and _norm_weak(str(x.get("technique_tag") or "")) == weak_key
        and x.get("id") != opener.get("id")
    ]
    if not weak_candidates:
        weak_candidates = [
            x
            for x in pool
            if not x.get("opener_kind")
            and _norm_weak(str(x.get("technique_tag") or "")) == "timing"
            and x.get("id") != opener.get("id")
        ]
    weak_ex = weak_candidates[_pick_index(seed + 3, len(weak_candidates))]

    style_label = str(taste.style_label or "")
    style_candidates = [
        x
        for x in pool
        if not x.get("opener_kind")
        and x.get("id") not in {opener.get("id"), weak_ex.get("id")}
        and _style_matches(style_label, list(x.get("style_tags") or []))
    ]
    if not style_candidates:
        style_candidates = [
            x
            for x in pool
            if not x.get("opener_kind")
            and x.get("id") not in {opener.get("id"), weak_ex.get("id")}
        ]
    style_ex = style_candidates[_pick_index(seed + 5, len(style_candidates))]

    ordered = [opener, weak_ex, style_ex]
    exercises: list[WarmupExercise] = []
    for row in ordered:
        tab = row.get("tab_snippet_gp5_base64")
        tab_out = str(tab).strip() if isinstance(tab, str) and tab.strip() else None
        exercises.append(
            WarmupExercise(
                name=str(row.get("name") or "Warmup"),
                description=str(row.get("description") or ""),
                duration_seconds=int(row.get("duration_seconds") or 60),
                tab_snippet_gp5_base64=tab_out,
                technique_tag=_norm_weak(str(row.get("technique_tag") or "timing")),
                bpm=exercise_bpm,
                fretboard_guide=_fretboard_guide_from_row(row),
            )
        )

    total = sum(e.duration_seconds for e in exercises)
    target = 180
    lo, hi = 150, 210
    if not (lo <= total <= hi):
        scale = target / max(total, 1)
        scaled_secs: list[int] = []
        for e in exercises:
            scaled_secs.append(max(45, min(90, int(round(e.duration_seconds * scale)))))
        drift = target - sum(scaled_secs)
        scaled_secs[-1] = max(45, min(90, scaled_secs[-1] + drift))
        for i, e in enumerate(exercises):
            exercises[i] = e.model_copy(update={"duration_seconds": scaled_secs[i]})
        total = sum(e.duration_seconds for e in exercises)

    return WarmupPlan(exercises=exercises, total_duration_seconds=total)
