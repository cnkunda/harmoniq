"""Commit 179: long-term mentor narrative over a compact client-built trajectory."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from app import coach
from app.schemas import (
    MentorNextMonthItem,
    MentorNote,
    MentorSongSuggestion,
    MentorTrajectoryRequest,
)

logger = logging.getLogger("harmoniq.mentor")
logger.setLevel(logging.INFO)

MODEL_ID = os.getenv("HARMONIQ_MODEL_ID", "claude-haiku-4-5-20251001")
MENTOR_TIMEOUT_SECONDS = max(1.0, float(os.getenv("HARMONIQ_MENTOR_TIMEOUT_MS", "20000")) / 1000.0)
MENTOR_MAX_TOKENS = 900

MENTOR_SYSTEM_PROMPT = """You are Harmoniq's long-term guitar mentor. You have watched this player for
months through their practice sessions, saved jams, corrections, and plans.

Speak like a trusted teacher who knows their history: warm, direct, specific. No generic praise,
no hype, no lists of everything they did wrong. Point to one or two real patterns in the supplied
data, then propose a direction for the next month.

Hard rules:
- Use only the measurements supplied in the trajectory. Never invent sessions, songs, scores, or dates.
- Never claim the plan has already changed. Everything you propose is a suggestion for the player.
- Refer to the player's declared goals when they exist, and connect the plan to those goals.
- If the evidence is thin, say so plainly instead of sounding more certain than the data.
- Return valid JSON only. No markdown inside strings."""

MENTOR_USER_PROMPT = """Build this player's monthly mentor note.

The player's current Home mode is <mode>{mode}</mode>. Emphasize that mode first, but always speak
to both modes:
- "single" means they practice one song at a time: suggest next songs to play.
- "plan" means they follow a generated practice plan: explain what that plan is building.

Use the trajectory below as the only source of truth.

<trajectory>
{trajectory_json}
</trajectory>

<allowed_songs>
{allowed_songs_json}
</allowed_songs>

<allowed_skill_focus>
{allowed_skills_json}
</allowed_skill_focus>

Return JSON with exactly these fields:
{{
  "headline": "short, specific headline (max 80 characters)",
  "trajectory_summary": "2-4 sentences on the real long-term trend, including what improved and what stalled",
  "plateau_diagnosis": "one sentence naming a plausible plateau and its evidence, or null",
  "next_month": [
    {{
      "title": "one concrete direction for the next month",
      "why": "1-2 sentences tying it to the trajectory",
      "skill_focus": "one value from allowed_skill_focus",
      "mode": "single" or "plan"
    }}
  ],
  "next_songs": [
    {{
      "title": "exact title from allowed_songs",
      "artist": "artist from allowed_songs or null",
      "reason": "1 sentence tying the song to the player's goals or weak areas",
      "source": "library" or "taste"
    }}
  ],
  "plan_guidance": "2-3 sentences explaining how the current plan (or the next plan) builds the player's playing. If there is no plan, say what the next plan should target. null only if there is no useful guidance."
}}

Rules for the arrays:
- next_month: at most 3 items. Prefer 2. Every skill_focus must exactly match one allowed_skill_focus value.
- next_songs: at most 3 items. Every title must exactly match an allowed_songs title. If allowed_songs is empty, return an empty array.
- Do not include songs or skills that are not in the allowed lists.
- No duplicate songs.
- Keep every string under 400 characters.
- If the data is too thin to support a claim, return null or omit the item rather than guessing.

Output only the JSON object."""


class MentorGenerationError(RuntimeError):
    """Raised when Claude cannot produce a usable mentor note."""


def _limit(value: str, max_length: int) -> str:
    text = value.strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def _allowed_song_map(request: MentorTrajectoryRequest) -> dict[str, dict[str, Any]]:
    allowed: dict[str, dict[str, Any]] = {}
    for song in request.library_songs:
        key = song.title.strip().lower()
        if not key:
            continue
        allowed[key] = {"title": song.title.strip(), "artist": song.artist, "source": "library"}
    for title in request.taste_song_candidates:
        key = title.strip().lower()
        if not key or key in allowed:
            continue
        allowed[key] = {"title": title.strip(), "artist": None, "source": "taste"}
    return allowed


def _allowed_skill_map(request: MentorTrajectoryRequest) -> dict[str, str]:
    allowed: dict[str, str] = {}

    def add(value: str) -> None:
        key = value.strip().lower()
        if key:
            allowed[key] = value.strip()

    for delta in request.skill_deltas:
        add(delta.id)
        add(delta.label)
        add(delta.id.replace("_", " "))
    for node in request.weak_nodes:
        add(node.id)
        add(node.label)
        add(node.id.replace("_", " "))
    for goal in request.goals.technique_affinity:
        add(goal)
    for value in ("timing", "phrasing", "pitch", "bending", "vibrato", "technique", "repertoire"):
        add(value)
    return allowed


def _resolve_skill_focus(raw: Any, allowed: dict[str, str]) -> str | None:
    if not isinstance(raw, str):
        return None
    return allowed.get(raw.strip().lower())


def _resolve_mode(raw: Any) -> str | None:
    if raw == "single" or raw == "plan":
        return raw
    return None


def _parse_next_month(data: dict[str, Any], allowed_skills: dict[str, str]) -> list[MentorNextMonthItem]:
    raw_items = data.get("next_month")
    if not isinstance(raw_items, list):
        return []
    out: list[MentorNextMonthItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        why = item.get("why")
        mode = _resolve_mode(item.get("mode"))
        skill_focus = _resolve_skill_focus(item.get("skill_focus"), allowed_skills)
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(why, str) or not why.strip():
            continue
        if mode is None or skill_focus is None:
            logger.info("mentor dropped next_month item title=%r mode=%r skill=%r", title, mode, skill_focus)
            continue
        out.append(
            MentorNextMonthItem(
                title=_limit(title, 120),
                why=_limit(why, 400),
                skill_focus=skill_focus,
                mode=mode,
            )
        )
        if len(out) >= 3:
            break
    return out


def _parse_next_songs(data: dict[str, Any], allowed_songs: dict[str, dict[str, Any]]) -> list[MentorSongSuggestion]:
    raw_items = data.get("next_songs")
    if not isinstance(raw_items, list):
        return []
    out: list[MentorSongSuggestion] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        raw_title = item.get("title")
        if not isinstance(raw_title, str):
            continue
        key = raw_title.strip().lower()
        match = allowed_songs.get(key)
        if match is None:
            logger.info("mentor dropped unknown song title=%r", raw_title)
            continue
        if key in seen:
            continue
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            continue
        seen.add(key)
        out.append(
            MentorSongSuggestion(
                title=str(match["title"]),
                artist=match.get("artist"),
                reason=_limit(reason, 400),
                source=str(match["source"]),
            )
        )
        if len(out) >= 3:
            break
    return out


def _parse_note(raw_text: str, request: MentorTrajectoryRequest) -> MentorNote:
    data = coach._extract_json_object(raw_text)
    if data is None:
        raise MentorGenerationError("Mentor response was not valid JSON.")

    headline = data.get("headline")
    summary = data.get("trajectory_summary")
    if not isinstance(headline, str) or not headline.strip():
        raise MentorGenerationError("Mentor response was missing a headline.")
    if not isinstance(summary, str) or not summary.strip():
        raise MentorGenerationError("Mentor response was missing a trajectory summary.")

    plateau_raw = data.get("plateau_diagnosis")
    plateau = _limit(plateau_raw, 800) if isinstance(plateau_raw, str) and plateau_raw.strip() else None
    guidance_raw = data.get("plan_guidance")
    guidance = _limit(guidance_raw, 1200) if isinstance(guidance_raw, str) and guidance_raw.strip() else None

    return MentorNote(
        headline=_limit(headline, 120),
        trajectory_summary=_limit(summary, 1200),
        confidence=request.history.confidence,
        plateau_diagnosis=plateau,
        next_month=_parse_next_month(data, _allowed_skill_map(request)),
        next_songs=_parse_next_songs(data, _allowed_song_map(request)),
        plan_guidance=guidance,
        generated_at=request.generated_at or datetime.now(timezone.utc).isoformat(),
        model=MODEL_ID,
    )


def generate_mentor_note(*, api_key: str, request: MentorTrajectoryRequest) -> MentorNote:
    """Call Claude once and validate the note against the supplied allowlists."""
    trajectory_json = json.dumps(request.model_dump(mode="json"), indent=2)
    allowed_songs_json = json.dumps(_allowed_song_map(request), indent=2)
    allowed_skills_json = json.dumps(sorted(_allowed_skill_map(request).values()), indent=2)
    user_prompt = MENTOR_USER_PROMPT.format(
        mode=request.mode,
        trajectory_json=trajectory_json,
        allowed_songs_json=allowed_songs_json,
        allowed_skills_json=allowed_skills_json,
    )
    raw_text = coach._call_claude_streaming(
        api_key=api_key,
        user_prompt=user_prompt,
        max_tokens=MENTOR_MAX_TOKENS,
        temperature=0.6,
        system_prompt=MENTOR_SYSTEM_PROMPT,
        timeout_seconds=MENTOR_TIMEOUT_SECONDS,
    )
    note = _parse_note(raw_text, request)
    logger.info(
        "mentor note generated mode=%s days=%s sessions=%s next_month=%s next_songs=%s",
        request.mode,
        request.history.days,
        request.history.session_count,
        len(note.next_month),
        len(note.next_songs),
    )
    return note
