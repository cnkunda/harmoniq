"""Anthropic-powered section coach copy with safe local fallback."""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from app.schemas import LessonSectionStub

logger = logging.getLogger("harmoniq.coach")
logger.setLevel(logging.INFO)

MODEL_ID = "claude-sonnet-4-20250514"
COACH_TIMEOUT_SECONDS = 8.0

# README "AI Coach — Prompt Design" base prompt; keep this literal for reviewability.
BASE_SYSTEM_PROMPT = """You are a warm, musical guitar coach — somewhere between a patient session musician
and a good friend who plays really well. You speak in plain English, never in music
theory jargon unless you explain it immediately. You never say "wrong note."
You talk about feel, space, tension, and where the music wants to go.
You give one specific, actionable observation per response — never a list.
You sound like a person, not an app.
Keep responses under 4 sentences. Never start with "Great job," "Nice work,"
or any generic praise opener. Lead with the observation.
The encouragement, if any, comes last and must be specific — never generic."""

COACH_USER_PROMPT_TEMPLATE = """Return valid JSON with exactly two string fields:
- coach_note
- coach_explanation

Generate these for this lesson section:
- section_label: {section_label}
- song_title: {song_title}
- artist: {artist}
- key: {key}

coach_note:
- 1 sentence
- specific and actionable
- focused on what to notice or try musically in this section

coach_explanation:
- 2-3 sentences
- explain why this phrase/section works musically (feel, tension, release, space)
- plain English, no unexplained theory jargon

Output only JSON."""

FALLBACK_COACH_NOTE = "Stay relaxed and sing each phrase before you play it, then match that shape on guitar."
FALLBACK_COACH_EXPLANATION = (
    "This section sounds strong when you leave a little space between ideas. "
    "The pause creates tension, and the next note feels more intentional when it lands. "
    "Think about phrasing like a short sentence with a clear breath."
)

FALLBACK_ONBOARDING_PLACEMENT = (
    "Your placement takes give us a usable baseline for pitch, phrasing, and timing. "
    "What usually opens up first is a little more air between ideas — micro-pauses make the next note feel intentional instead of rushed. "
    "Harmoniq will weight suggestions from here; when you add a real song, the home card will line up drills with what you are working on. "
    "Keep bends relaxed and let vibrato settle before you move on — small stability wins there carry into everything else."
)


def _fallback_coach_fields() -> tuple[str, str]:
    return FALLBACK_COACH_NOTE, FALLBACK_COACH_EXPLANATION


def _extract_text_from_response(response: object) -> str:
    content = getattr(response, "content", None)
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _call_claude_text(*, api_key: str, user_prompt: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=220,
        system=BASE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return _extract_text_from_response(response)


def _parse_coach_json(raw_text: str) -> tuple[str, str] | None:
    import json

    raw = (raw_text or "").strip()
    if not raw:
        return None

    # Claude may wrap valid JSON in markdown fences. Strip common wrappers first.
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()

    # If extra prose appears around JSON, try the first object block.
    if not raw.startswith("{") or not raw.endswith("}"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]

    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    note = data.get("coach_note")
    explanation = data.get("coach_explanation")
    if not isinstance(note, str) or not note.strip():
        return None
    if not isinstance(explanation, str) or not explanation.strip():
        return None
    return note.strip(), explanation.strip()


def generate_coach_fields_for_section(
    *,
    section_label: str | None,
    song_title: str | None,
    artist: str | None,
    key: str | None,
) -> tuple[str, str]:
    """Return coach_note + coach_explanation, with timeout and dev fallback."""
    # Keep test runs deterministic and fully offline even when a real key is present.
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_COACH_IN_TESTS") != "1":
        logger.info("coach fallback reason=pytest_mode")
        return _fallback_coach_fields()

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("coach fallback reason=missing_api_key")
        return _fallback_coach_fields()

    user_prompt = COACH_USER_PROMPT_TEMPLATE.format(
        section_label=(section_label or "Section"),
        song_title=(song_title or "Unknown song"),
        artist=(artist or "Unknown artist"),
        key=(key or "Unknown key"),
    )
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_call_claude_text, api_key=api_key, user_prompt=user_prompt)
    try:
        raw_text = future.result(timeout=COACH_TIMEOUT_SECONDS)
        parsed = _parse_coach_json(raw_text)
        if parsed is None:
            logger.warning("coach fallback reason=unparseable_response")
            return _fallback_coach_fields()
        return parsed
    except FutureTimeoutError:
        future.cancel()
        logger.warning("coach fallback reason=timeout")
        return _fallback_coach_fields()
    except Exception as exc:
        logger.warning("coach fallback reason=api_error error=%s", exc.__class__.__name__)
        return _fallback_coach_fields()
    finally:
        # Don't let hung network calls pin the caller after timeout fallback.
        pool.shutdown(wait=False, cancel_futures=True)


def generate_onboarding_placement_summary(
    *,
    pitch_avg: float,
    phrasing_avg: float,
    timing_avg: float,
    bend_error_cents_avg: float,
) -> str:
    """Single plain-text paragraph for placement results; never JSON."""
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_COACH_IN_TESTS") != "1":
        logger.info("onboarding placement coach fallback reason=pytest_mode")
        return FALLBACK_ONBOARDING_PLACEMENT

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("onboarding placement coach fallback reason=missing_api_key")
        return FALLBACK_ONBOARDING_PLACEMENT

    user_prompt = f"""The guitarist just finished a Harmoniq placement session: three very short phrases recorded back-to-back.
Aggregated scores (0–1 scale): pitch {pitch_avg:.2f}, phrasing {phrasing_avg:.2f}, timing {timing_avg:.2f}.
Mean bend intonation error across takes: {bend_error_cents_avg:.1f} cents (lower is tighter).

Write exactly one paragraph, 3–4 sentences, plain English. No bullet points, no JSON, no markdown.
Follow README coach rules: one specific observation about their baseline, one actionable priority to work first, end with specific encouragement (not generic praise).
Never start with "Great job" or "Nice work"."""

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_call_claude_text, api_key=api_key, user_prompt=user_prompt)
    try:
        raw_text = future.result(timeout=COACH_TIMEOUT_SECONDS)
        text = (raw_text or "").strip()
        if len(text) < 50:
            logger.warning("onboarding placement coach fallback reason=short_response")
            return FALLBACK_ONBOARDING_PLACEMENT
        return text
    except FutureTimeoutError:
        future.cancel()
        logger.warning("onboarding placement coach fallback reason=timeout")
        return FALLBACK_ONBOARDING_PLACEMENT
    except Exception as exc:
        logger.warning(
            "onboarding placement coach fallback reason=api_error error=%s",
            exc.__class__.__name__,
        )
        return FALLBACK_ONBOARDING_PLACEMENT
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def generate_jam_coach_summary(
    duration_seconds: int,
    inferred_scale_label: str | None,
    scale_position_map: dict[str, float],
) -> str:
    """Local jam summary (PRIORITIES §36 — incremental; no LLM yet)."""
    if duration_seconds < 10:
        return (
            "Short jam — try at least ten seconds next time so we can summarize your pitch tendencies against the loop."
        )
    label = (inferred_scale_label or "").strip()
    lead = ""
    if label and label != "—":
        if not label.endswith("."):
            label = f"{label}."
        lead = f"You were leaning toward {label} "

    if scale_position_map:
        top_key, top_val = max(scale_position_map.items(), key=lambda kv: kv[1])
        note = top_key.replace("pc_", "").replace("_", "")
        rest = (
            f"Strongest pitch-class weight: {note} ({top_val:.0%} of hits). "
            "Use that tone as a home base and connect stepwise phrases around it."
        )
        return (lead + rest).strip()

    return (
        lead + "We did not pick up a clear pitch histogram — play a bit closer to the mic or a little louder next time."
    ).strip() or "Jam saved. Keep connecting melodic ideas to the groove."


def merge_coach_copy_into_sections(
    sections: list[LessonSectionStub],
    *,
    song_title: str | None,
    artist: str | None,
    key: str | None,
) -> list[LessonSectionStub]:
    """Populate coach fields on each section while preserving existing fields."""
    enriched: list[LessonSectionStub] = []
    for sec in sections:
        note, explanation = generate_coach_fields_for_section(
            section_label=sec.label,
            song_title=song_title,
            artist=artist,
            key=key,
        )
        payload = sec.model_dump(exclude_none=True)
        payload["coach_note"] = note
        payload["coach_explanation"] = explanation
        enriched.append(LessonSectionStub(**payload))
    return enriched
