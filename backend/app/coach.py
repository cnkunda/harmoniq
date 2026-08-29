"""Anthropic-powered section coach copy with safe local fallback."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from anthropic import Anthropic

from app.schemas import CoachFocusArea, LessonSectionStub, MoodState, PlayerProfile

logger = logging.getLogger("harmoniq.coach")
logger.setLevel(logging.INFO)

MODEL_ID = os.getenv("HARMONIQ_MODEL_ID", "claude-haiku-4-5")
COACH_TIMEOUT_SECONDS = max(0.5, float(os.getenv("HARMONIQ_COACH_TIMEOUT_MS", "8000")) / 1000.0)
PRACTICE_PLAN_INTRO_TIMEOUT_SECONDS = min(8.0, COACH_TIMEOUT_SECONDS)
QUICK_FEEDBACK_TIMEOUT_SECONDS = 5.0
COACH_PROFILE_MAX_RETRIES = 2  # Maximum retry attempts beyond the initial call
COACH_PROFILE_TEMPERATURE_INITIAL = 0.5
COACH_PROFILE_TEMPERATURE_RETRY = 0.3

# Module-level executor for concurrent coach operations
# max_workers=4 allows parallel section hydration without overwhelming API
_COACH_EXECUTOR = ThreadPoolExecutor(max_workers=4)

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


@dataclass(frozen=True)
class CoachCallResult:
    note: str
    explanation: str
    fallback_reason: str | None

COACH_USER_PROMPT_TEMPLATE = """Return valid JSON with exactly three string fields:
- coach_note
- coach_explanation
- weak_focus

Generate these for this lesson section:
- section_label: {section_label}
- song_title: {song_title}
- artist: {artist}
- key: {key}
{focus_directive}

coach_note:
- 1 sentence
- specific and actionable
- focused on what to notice or try musically in this section

coach_explanation:
- 2-3 sentences
- explain why this phrase/section works musically (feel, tension, release, space)
- plain English, no unexplained theory jargon

weak_focus:
- If weak areas are listed in the player context block, this must be exactly one weak-area phrase from that list.
- If no weak areas were provided, output exactly "none".

Output only JSON."""

WEAK_AREA_SYNONYMS: dict[str, tuple[str, ...]] = {
    "bending": ("bend", "bends", "bent note", "intonation"),
    "vibrato": ("vibrato control", "wobble", "pitch stability"),
    "timing": ("rhythm", "time feel", "rushing", "behind the beat"),
    "phrasing": ("phrase shape", "phrase ending", "musical sentence"),
    "pitch": ("pitch control", "pitch center", "in tune", "intonation"),
}


def _player_context_block(profile_data: dict | None) -> str:
    if profile_data is None:
        return ""
    weak = profile_data.get("weak_areas") or []
    nodes = profile_data.get("skill_nodes") or []
    taste = profile_data.get("taste_profile")
    lc = profile_data.get("learning_context")
    if not weak and not nodes and not taste and not lc:
        return ""
    lines = [
        "<player_context>",
        "The player has a known skill profile — prioritize coach_note and coach_explanation toward their gaps.",
    ]
    if weak:
        lines.append("Weak areas to emphasize (plain phrases): " + ", ".join(str(w) for w in weak))
    if nodes:
        parts: list[str] = []
        for n in nodes[:12]:
            if not isinstance(n, dict):
                continue
            nid = n.get("id", "")
            sc = n.get("score")
            if sc is not None:
                try:
                    sf = float(sc)
                    parts.append(f"{nid} (score {sf:.2f})")
                except (TypeError, ValueError):
                    parts.append(str(nid))
            else:
                parts.append(str(nid))
        if parts:
            lines.append("Skill snapshot: " + "; ".join(parts))
    if isinstance(taste, dict) and taste:
        sl = str(taste.get("style_label") or "").strip()
        ta = taste.get("technique_affinity")
        bpm = taste.get("bpm_comfort_range")
        src = str(taste.get("source") or "").strip()
        bits = []
        if sl:
            bits.append(f"derived taste style: {sl}")
        if isinstance(ta, list) and ta:
            bits.append("technique affinities: " + ", ".join(str(x) for x in ta[:10] if str(x).strip()))
        if isinstance(bpm, (list, tuple)) and len(bpm) == 2:
            bits.append(f"comfortable practice tempo band (BPM): {bpm[0]}–{bpm[1]}")
        if src:
            bits.append(f"taste source: {src}")
        if bits:
            lines.append("; ".join(bits) + ".")
    if isinstance(lc, dict) and lc:
        exp = str(lc.get("experience_level") or "").strip()
        notes = str(lc.get("solo_focus_notes") or "").strip()
        bits_lc: list[str] = []
        if exp:
            bits_lc.append(f"declared experience tier: {exp}")
        if notes:
            bits_lc.append(f"player style/focus note: {notes}")
        if bits_lc:
            lines.append("; ".join(bits_lc) + ".")
    lines.append("Do not quote this block verbatim in the JSON output.")
    lines.append("</player_context>")
    return "\n".join(lines) + "\n\n"


def _profile_priority_directive(profile_data: dict | None) -> str:
    if profile_data is None:
        return ""
    weak = [str(w).strip() for w in (profile_data.get("weak_areas") or []) if str(w).strip()]
    nodes = profile_data.get("skill_nodes") or []
    taste = profile_data.get("taste_profile")
    lc = profile_data.get("learning_context")
    if not weak and not nodes and not taste and not lc:
        return ""
    if weak:
        joined = ", ".join(weak[:8])
        focus_line = (
            "Profile-priority requirement: make coach_note or the first sentence of coach_explanation "
            f"explicitly reference at least one weak-area concept ({joined}) in plain language."
        )
    elif isinstance(lc, dict) and lc:
        exp = str(lc.get("experience_level") or "").strip()
        notes = str(lc.get("solo_focus_notes") or "").strip()
        if notes:
            focus_line = (
                "Profile-priority requirement: make coach_note or the first sentence of coach_explanation "
                f"honor their stated focus ({notes[:200]}) in plain language."
            )
        elif exp:
            focus_line = (
                "Profile-priority requirement: make coach_note or the first sentence of coach_explanation "
                f"reflect their declared level ({exp}) — simpler vocabulary when beginner, finer nuance when advanced."
            )
        else:
            focus_line = (
                "Profile-priority requirement: make coach_note or the first sentence of coach_explanation "
                "explicitly reference at least one low-confidence skill area from the profile in plain language."
            )
    elif isinstance(taste, dict) and taste:
        ta_list = [str(x).strip() for x in (taste.get("technique_affinity") or []) if str(x).strip()]
        sl = str(taste.get("style_label") or "").strip()
        bits = ", ".join(ta_list[:6]) if ta_list else (sl or "their stated taste")
        focus_line = (
            "Profile-priority requirement: make coach_note or the first sentence of coach_explanation "
            f"explicitly reference the player's taste lane ({bits}) in plain language."
        )
    else:
        focus_line = (
            "Profile-priority requirement: make coach_note or the first sentence of coach_explanation "
            "explicitly reference at least one low-confidence skill area from the profile in plain language."
        )
    return (
        focus_line
        + "\nKeep it section-specific and natural; do not output this requirement text in the JSON."
        + "\n\n"
    )


def _song_style_block(style_label: str | None, technique_hints: list[str] | None) -> str:
    label = (style_label or "").strip()
    hints = [h for h in (technique_hints or []) if isinstance(h, str) and h.strip()]
    if not label and not hints:
        return ""
    lines = [
        "<song_context>",
        f"Detected musical style label: {label or 'unknown'}.",
    ]
    if hints:
        lines.append("Technique angles that often matter here: " + ", ".join(hints[:6]))
    lines.append("Let this lightly shape the coaching tone, not a theory lecture.")
    lines.append("</song_context>")
    return "\n".join(lines) + "\n\n"


def _section_context_block(section_label: str | None, key: str | None) -> str:
    section = (section_label or "Section").strip() or "Section"
    key_label = (key or "Unknown key").strip() or "Unknown key"
    return (
        "<section_context>\n"
        f"Section label: {section}\n"
        f"Musical key: {key_label}\n"
        "Write one concrete playing adjustment specific to this section's phrase shape.\n"
        "</section_context>\n\n"
    )


def _focus_area_directive(focus_area: CoachFocusArea | None) -> str:
    """Generate focus directive for coach prompt based on focus_area (commit 90)."""
    if focus_area is None:
        return ""
    directives = {
        "timing": "Focus area this session: Timing. Prioritize observations about rhythm, time feel, rushing, or dragging.",
        "vibrato": "Focus area this session: Vibrato. Prioritize observations about pitch stability, wobble control, and vibrato width.",
        "dynamics": "Focus area this session: Dynamics. Prioritize observations about volume control, articulation, and expressive touch.",
        "phrasing": "Focus area this session: Phrasing. Prioritize observations about phrase shape, breathing space, and musical sentence structure.",
        "bending": "Focus area this session: Bending. Prioritize observations about intonation, bend accuracy, and pitch center.",
        "rhythm": "Focus area this session: Rhythm. Prioritize observations about groove, subdivision accuracy, and rhythmic consistency.",
        "expression": "Focus area this session: Expression. Prioritize observations about emotional delivery, tone color, and musical intent.",
    }
    return directives.get(focus_area, "")


FOCUS_AREA_ROTATION: list[CoachFocusArea] = [
    "timing",
    "vibrato",
    "dynamics",
    "phrasing",
    "bending",
    "rhythm",
    "expression",
]


def rotate_focus_area(session_count: int) -> CoachFocusArea:
    """Determine focus area for this session based on session count (commit 90)."""
    if session_count < 0:
        logger.warning("rotate_focus_area received negative session_count=%s, clamping to 0", session_count)
        session_count = 0
    return FOCUS_AREA_ROTATION[session_count % len(FOCUS_AREA_ROTATION)]


def _normalize_for_match(value: str) -> str:
    lowered = value.lower()
    collapsed = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", collapsed).strip()


def _focus_term_variants(term: str) -> set[str]:
    base = _normalize_for_match(term)
    if not base:
        return set()
    variants = {base}
    if not base.endswith("s"):
        variants.add(f"{base}s")
    if base.endswith("ing"):
        variants.add(base[:-3])
    synonyms = WEAK_AREA_SYNONYMS.get(base)
    if synonyms:
        variants.update(_normalize_for_match(s) for s in synonyms if s)
    return {v for v in variants if v}


def _profile_focus_terms(profile: PlayerProfile | None) -> list[str]:
    if profile is None:
        return []
    weak = [str(w).strip() for w in profile.weak_areas if str(w).strip()]
    if weak:
        return weak[:8]
    low_nodes = sorted(
        [n for n in profile.skill_nodes if n.id and n.score is not None],
        key=lambda n: float(n.score or 0.0),
    )
    out: list[str] = []
    for node in low_nodes[:3]:
        label = (node.label or node.id or "").strip()
        if label:
            out.append(label)
    return out


def _coach_hits_profile_focus(*, note: str, explanation: str, weak_focus: str, focus_terms: list[str]) -> bool:
    if not focus_terms:
        return True
    combined = _normalize_for_match(f"{note} {explanation}")
    weak_focus_norm = _normalize_for_match(weak_focus)
    for term in focus_terms:
        for variant in _focus_term_variants(term):
            if variant and (variant in combined or variant == weak_focus_norm):
                return True
    return False


def _profile_retry_tail(focus_terms: list[str]) -> str:
    if not focus_terms:
        return ""
    joined = ", ".join(focus_terms)
    return (
        "\n\n<retry_requirement>"
        "\nPrevious draft did not clearly mention the player weak-area terms."
        f"\nRewrite so coach_note or the first sentence of coach_explanation explicitly names one of: {joined}."
        "\nAlso set weak_focus to exactly the matching weak-area phrase."
        "\nOutput only JSON."
        "\n</retry_requirement>"
    )


def build_coach_user_prompt(
    *,
    section_label: str | None,
    song_title: str | None,
    artist: str | None,
    key: str | None,
    player_profile: PlayerProfile | None = None,
    style_label: str | None = None,
    technique_hints: list[str] | None = None,
    focus_area: CoachFocusArea | None = None,
) -> str:
    """Assemble the user message: optional context blocks + fixed JSON contract."""
    # Dump profile once to avoid redundant serialization in helpers
    profile_data = None
    if player_profile is not None:
        profile_data = player_profile.model_dump(mode="json", exclude_none=True)

    prefix = (
        _player_context_block(profile_data)
        + _song_style_block(style_label, technique_hints)
        + _section_context_block(section_label, key)
    )
    profile_priority = _profile_priority_directive(profile_data)
    focus_directive = _focus_area_directive(focus_area)
    body = COACH_USER_PROMPT_TEMPLATE.format(
        section_label=(section_label or "Section"),
        song_title=(song_title or "Unknown song"),
        artist=(artist or "Unknown artist"),
        key=(key or "Unknown key"),
        focus_directive=focus_directive,
    )
    return prefix + profile_priority + body


FALLBACK_COACH_NOTE = "Stay relaxed and sing each phrase before you play it, then match that shape on guitar."
FALLBACK_COACH_EXPLANATION = (
    "This section sounds strong when you leave a little space between ideas. "
    "The pause creates tension, and the next note feels more intentional when it lands. "
    "Think about phrasing like a short sentence with a clear breath."
)

# Models to try in order when the primary MODEL_ID returns 404.
_MODEL_FALLBACK_CHAIN: list[str] = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
]

FALLBACK_ONBOARDING_PLACEMENT = (
    "Your placement takes give us a usable baseline for pitch, phrasing, and timing. "
    "What usually opens up first is a little more air between ideas — micro-pauses make the next note feel intentional instead of rushed. "
    "Harmoniq will weight suggestions from here; when you add a real song, the home card will line up drills with what you are working on. "
    "Keep bends relaxed and let vibrato settle before you move on — small stability wins there carry into everything else."
)


def _fallback_coach_fields() -> tuple[str, str]:
    return FALLBACK_COACH_NOTE, FALLBACK_COACH_EXPLANATION


QUICK_FEEDBACK_USER_PROMPT = """Return valid JSON with exactly one string field "message".
The guitarist just played along for several beats. Per-beat pitch accuracy (chronological, one label per beat): {pattern}

Write one short sentence (max 28 words) — the single most useful thing to try on the next pass.
Plain English. No markdown inside the string. Never start with "Great job" or "Nice work".
Output only JSON."""

FALLBACK_QUICK_FEEDBACK = (
    "A few beats wandered wide — lighten the grip and aim to land the target pitch a hair earlier so it settles in tune."
)


def _call_claude_streaming(
    *,
    api_key: str,
    user_prompt: str,
    max_tokens: int = 220,
    temperature: float = 1.0,
) -> str:

    start_time = time.perf_counter()
    client = Anthropic(api_key=api_key)
    chunks: list[str] = []
    first_chunk_time: float | None = None

    models_to_try = [MODEL_ID] + [m for m in _MODEL_FALLBACK_CHAIN if m != MODEL_ID]
    last_error: Exception | None = None

    for model_id in models_to_try:
        try:
            with client.messages.stream(
                model=model_id,
                max_tokens=max_tokens,
                temperature=temperature,
                system=BASE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                for evt in stream:
                    t = getattr(evt, "type", "")
                    if t != "content_block_delta":
                        continue
                    delta = getattr(evt, "delta", None)
                    text = getattr(delta, "text", None)
                    if isinstance(text, str) and text:
                        if first_chunk_time is None:
                            first_chunk_time = time.perf_counter() - start_time
                        chunks.append(text)
            total_time = time.perf_counter() - start_time
            logger.info(
                "claude_streaming timing total_ms=%.0f first_chunk_ms=%s tokens=%d model=%s",
                total_time * 1000,
                "%.0f" % (first_chunk_time * 1000) if first_chunk_time else "null",
                max_tokens,
                model_id,
            )
            return "".join(chunks).strip()
        except Exception as exc:
            last_error = exc
            error_name = getattr(exc, "__class__", type(exc)).__name__
            # Only retry on 404 (model not found) — other errors are definitive
            if "404" not in str(exc) and error_name != "NotFoundError":
                raise
            logger.warning("coach model %s unavailable (404), trying fallback", model_id)
            continue

    # All models failed — re-raise the last error
    raise last_error  # type: ignore[misc]


# Backward-compatible alias used by existing tests/mocks.
def _call_claude_text(
    *,
    api_key: str,
    user_prompt: str,
    max_tokens: int = 220,
    temperature: float = 1.0,
) -> str:
    return _call_claude_streaming(
        api_key=api_key,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def _parse_coach_json(raw_text: str) -> tuple[str, str, str] | None:
    data = _extract_json_object(raw_text)
    if data is None:
        return None
    note = data.get("coach_note")
    explanation = data.get("coach_explanation")
    if not isinstance(note, str) or not note.strip():
        return None
    if not isinstance(explanation, str) or not explanation.strip():
        return None
    weak_focus = data.get("weak_focus")
    if not isinstance(weak_focus, str) or not weak_focus.strip():
        weak_focus = "none"
    return note.strip(), explanation.strip(), weak_focus.strip()


def _extract_json_object(raw_text: str) -> dict | None:
    """Extract JSON object from text, handling markdown fences and extra prose."""
    raw = (raw_text or "").strip()
    if not raw:
        return None

    # Strip markdown fences
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()

    # Extract first object block if surrounded by prose
    if not raw.startswith("{") or not raw.endswith("}"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]

    try:
        data = json.loads(raw)
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _parse_quick_message_json(raw_text: str) -> str | None:
    data = _extract_json_object(raw_text)
    if data is None:
        return None
    msg = data.get("message")
    if not isinstance(msg, str) or not msg.strip():
        return None
    return msg.strip()


def _parse_theory_rationale_json(raw_text: str) -> str | None:
    """Parse theory annotation response looking for 'rationale' field."""
    data = _extract_json_object(raw_text)
    if data is None:
        return None
    rationale = data.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        return None
    return rationale.strip()


def generate_quick_feedback(accuracy_pattern: list[str]) -> str:
    """One-sentence coach from per-beat hit/close/miss pattern (Play step, PRIORITIES §49)."""
    if not accuracy_pattern:
        logger.info("quick_feedback fallback reason=empty_pattern")
        return FALLBACK_QUICK_FEEDBACK

    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_COACH_IN_TESTS") != "1":
        logger.info("quick_feedback fallback reason=pytest_mode")
        return FALLBACK_QUICK_FEEDBACK

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("quick_feedback fallback reason=missing_api_key")
        return FALLBACK_QUICK_FEEDBACK

    pattern_csv = ", ".join(accuracy_pattern)
    user_prompt = QUICK_FEEDBACK_USER_PROMPT.format(pattern=pattern_csv)
    future = _COACH_EXECUTOR.submit(
        _call_claude_text,
        api_key=api_key,
        user_prompt=user_prompt,
        max_tokens=110,
        temperature=0.3,
    )
    try:
        raw_text = future.result(timeout=QUICK_FEEDBACK_TIMEOUT_SECONDS)
        parsed = _parse_quick_message_json(raw_text)
        if parsed is None:
            logger.warning("quick_feedback fallback reason=parse_error")
            return FALLBACK_QUICK_FEEDBACK
        return parsed
    except FutureTimeoutError:
        future.cancel()
        logger.warning("quick_feedback fallback reason=timeout")
        return FALLBACK_QUICK_FEEDBACK
    except Exception as exc:
        logger.warning("quick_feedback fallback reason=api_error error=%s", exc.__class__.__name__)
        return FALLBACK_QUICK_FEEDBACK


def generate_coach_fields_for_section(
    *,
    section_label: str | None,
    song_title: str | None,
    artist: str | None,
    key: str | None,
    player_profile: PlayerProfile | None = None,
    style_label: str | None = None,
    technique_hints: list[str] | None = None,
    focus_area: CoachFocusArea | None = None,
) -> tuple[str, str]:
    result = generate_coach_fields_for_section_with_status(
        section_label=section_label,
        song_title=song_title,
        artist=artist,
        key=key,
        player_profile=player_profile,
        style_label=style_label,
        technique_hints=technique_hints,
        focus_area=focus_area,
    )
    return result.note, result.explanation


def generate_coach_fields_for_section_with_status(
    *,
    section_label: str | None,
    song_title: str | None,
    artist: str | None,
    key: str | None,
    player_profile: PlayerProfile | None = None,
    style_label: str | None = None,
    technique_hints: list[str] | None = None,
    focus_area: CoachFocusArea | None = None,
) -> CoachCallResult:
    """Return coach_note + coach_explanation, with timeout and dev fallback."""
    # Keep test runs deterministic and fully offline even when a real key is present.
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_COACH_IN_TESTS") != "1":
        logger.info("coach fallback reason=pytest_mode")
        note, explanation = _fallback_coach_fields()
        return CoachCallResult(note=note, explanation=explanation, fallback_reason="pytest_mode")

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("coach fallback reason=missing_api_key")
        note, explanation = _fallback_coach_fields()
        return CoachCallResult(note=note, explanation=explanation, fallback_reason="missing_api_key")

    user_prompt = build_coach_user_prompt(
        section_label=section_label,
        song_title=song_title,
        artist=artist,
        key=key,
        player_profile=player_profile,
        style_label=style_label,
        technique_hints=technique_hints,
        focus_area=focus_area,
    )
    focus_terms = _profile_focus_terms(player_profile)
    attempts = 1 + COACH_PROFILE_MAX_RETRIES if focus_terms else 1
    try:
        for attempt in range(attempts):
            prompt = user_prompt
            if attempt > 0:
                prompt = user_prompt + _profile_retry_tail(focus_terms)
            temperature = 1.0
            if focus_terms:
                temperature = (
                    COACH_PROFILE_TEMPERATURE_INITIAL
                    if attempt == 0
                    else COACH_PROFILE_TEMPERATURE_RETRY
                )
            future = _COACH_EXECUTOR.submit(
                _call_claude_text,
                api_key=api_key,
                user_prompt=prompt,
                temperature=temperature,
            )
            raw_text = future.result(timeout=COACH_TIMEOUT_SECONDS)
            parsed = _parse_coach_json(raw_text)
            if parsed is None:
                logger.warning(
                    "coach fallback reason=parse_error attempt=%s/%s",
                    attempt + 1,
                    attempts,
                )
                continue
            note, explanation, weak_focus = parsed
            if _coach_hits_profile_focus(
                note=note,
                explanation=explanation,
                weak_focus=weak_focus,
                focus_terms=focus_terms,
            ):
                return CoachCallResult(note=note, explanation=explanation, fallback_reason=None)
            logger.info(
                "coach profile_focus_retry attempt=%s/%s weak_focus=%s",
                attempt + 1,
                attempts,
                weak_focus,
            )
        logger.warning("coach fallback reason=parse_error")
        note, explanation = _fallback_coach_fields()
        return CoachCallResult(note=note, explanation=explanation, fallback_reason="parse_error")
    except FutureTimeoutError:
        logger.warning("coach fallback reason=timeout")
        note, explanation = _fallback_coach_fields()
        return CoachCallResult(note=note, explanation=explanation, fallback_reason="timeout")
    except Exception as exc:
        logger.warning("coach fallback reason=api_error error=%s", exc.__class__.__name__)
        note, explanation = _fallback_coach_fields()
        return CoachCallResult(note=note, explanation=explanation, fallback_reason="api_error")


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

    future = _COACH_EXECUTOR.submit(_call_claude_text, api_key=api_key, user_prompt=user_prompt)
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


def generate_jam_coach_summary(
    duration_seconds: int,
    inferred_scale_label: str | None,
    pitch_class_weight_map: dict[str, float],
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

    if pitch_class_weight_map:
        top_key, top_val = max(pitch_class_weight_map.items(), key=lambda kv: kv[1])
        note = top_key.replace("pc_", "").replace("_", "")
        rest = (
            f"Strongest pitch-class weight: {note} ({top_val:.0%} of hits). "
            "Use that tone as a home base and connect stepwise phrases around it."
        )
        return (lead + rest).strip()

    return (
        lead + "We did not pick up a clear pitch histogram — play a bit closer to the mic or a little louder next time."
    ).strip() or "Jam saved. Keep connecting melodic ideas to the groove."


# ---------------------------------------------------------------------------
# Commit 111: Jam Mode Summary Agent — Claude-powered post-jam analysis
# ---------------------------------------------------------------------------

JAM_SUMMARY_PERSONAS = {
    "learner": """You are a supportive guitar coach for a beginner. Use simple, encouraging language.
Avoid music theory jargon. Focus on what the player did well and give one simple, actionable tip.
Use analogies a non-musician would understand. Keep it under 3 sentences.""",
    "intermediate": """You are a knowledgeable guitar coach for an intermediate player.
Use some technical terms but explain them briefly. Balance observation with actionable advice.
Reference specific musical concepts (scales, chord tones, phrasing). Keep it under 4 sentences.""",
    "transcriber": """You are an analytical guitar coach focused on notation and transcription decisions.
Use precise musical terminology. Discuss note choices, rhythmic placement, and harmonic context.
Suggest specific notation elements (slurs, bends, vibrato marks). Keep it under 4 sentences.""",
}

JAM_SUMMARY_USER_PROMPT = """Analyze this jam session and return a JSON object with exactly these fields:

{{
  "coach_summary": "1-3 sentence overall summary of the jam",
  "coach_strengths": ["what went well 1", "what went well 2"],
  "coach_focus_areas": ["area to work on 1", "area to work on 2"],
  "coach_next_step": "specific next practice suggestion"
}}

Jam data:
- Duration: {duration_seconds}s
- Detected scale: {scale_label} (confidence: {confidence})
- Track: {track_label} in {track_key} at {track_bpm} BPM
- Phrases played: {phrase_count}
- Note density: {avg_nps:.1f} notes/second average
- Melodic contour: {dominant_contour}
- Vocabulary diversity: {diversity:.0%}
- Pitch class weights: {pitch_weights}
- Vocabulary patterns detected: {pattern_count}
{pattern_details}
Player context:
- Skill level: {player_level}
- Previous jams: {previous_jam_count}
- Known weak areas: {weak_areas}"""


def generate_jam_summary_with_claude(
    *,
    api_key: str,
    duration_seconds: int,
    inferred_scale_label: str | None,
    inference_confidence: str | None,
    track_label: str | None,
    track_key: str | None,
    track_bpm: int | None,
    phrase_count: int,
    avg_notes_per_second: float,
    dominant_contour: str,
    vocabulary_diversity: float,
    pitch_class_weight_map: dict[str, float],
    vocabulary_pattern_count: int,
    vocabulary_pattern_details: str,
    player_level: str,
    previous_jam_count: int,
    weak_areas: list[str],
    persona: str,
) -> dict[str, str] | None:
    """Call Claude for jam summary with persona-aware prompting.

    Returns parsed JSON dict or None on failure.
    """
    system_prompt = JAM_SUMMARY_PERSONAS.get(persona, JAM_SUMMARY_PERSONAS["intermediate"])

    # Format pitch weights for readability
    pitch_weights_str = ", ".join(
        f"{k.replace('pc_', '')}: {v:.0%}"
        for k, v in sorted(pitch_class_weight_map.items(), key=lambda kv: -kv[1])[:6]
    ) or "sparse"

    weak_areas_str = ", ".join(weak_areas[:5]) if weak_areas else "none identified"

    user_prompt = JAM_SUMMARY_USER_PROMPT.format(
        duration_seconds=duration_seconds,
        scale_label=inferred_scale_label or "unknown",
        confidence=inference_confidence or "low",
        track_label=track_label or "unknown",
        track_key=track_key or "unknown",
        track_bpm=track_bpm or 0,
        phrase_count=phrase_count,
        avg_nps=avg_notes_per_second,
        dominant_contour=dominant_contour,
        diversity=vocabulary_diversity,
        pitch_weights=pitch_weights_str,
        pattern_count=vocabulary_pattern_count,
        pattern_details=vocabulary_pattern_details,
        player_level=player_level,
        previous_jam_count=previous_jam_count,
        weak_areas=weak_areas_str,
    )

    try:
        raw = _call_claude_text(
            api_key=api_key,
            user_prompt=user_prompt,
            max_tokens=350,
            temperature=0.7,
        )
        data = _extract_json_object(raw)
        if data is None:
            logger.warning("Failed to parse Claude jam summary response")
            return None

        # Validate required fields
        summary = data.get("coach_summary", "")
        if not isinstance(summary, str) or not summary.strip():
            return None

        return {
            "coach_summary": summary.strip(),
            "coach_strengths": _ensure_string_list(data.get("coach_strengths", [])),
            "coach_focus_areas": _ensure_string_list(data.get("coach_focus_areas", [])),
            "coach_next_step": str(data.get("coach_next_step", "")).strip(),
        }
    except Exception:
        logger.exception("Claude jam summary call failed")
        return None


def _ensure_string_list(value: Any) -> list[str]:
    """Ensure value is a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def generate_jam_summary_fallback(
    *,
    duration_seconds: int,
    inferred_scale_label: str | None,
    pitch_class_weight_map: dict[str, float],
    phrase_count: int,
    vocabulary_diversity: float,
    player_level: str,
) -> dict[str, str]:
    """Deterministic fallback when Claude is unavailable."""
    scale_str = (inferred_scale_label or "your scale").strip()
    if scale_str.endswith("."):
        scale_str = scale_str[:-1]

    # Find dominant pitch class
    top_note = ""
    if pitch_class_weight_map:
        top_key, top_val = max(pitch_class_weight_map.items(), key=lambda kv: kv[1])
        top_note = top_key.replace("pc_", "").replace("_", "")
        top_pct = f"{top_val:.0%}"
    else:
        top_pct = ""

    if duration_seconds < 10:
        return {
            "coach_summary": "Short jam — try playing for at least 10 seconds so we can give you a proper analysis.",
            "coach_strengths": [],
            "coach_focus_areas": ["Play longer to get meaningful feedback"],
            "coach_next_step": "Try a 30-second jam over the backing track.",
        }

    summary_parts = [f"You explored {scale_str}"]
    if top_note and top_pct:
        summary_parts.append(f"with a strong center on {top_note} ({top_pct} of notes)")
    if phrase_count > 0:
        summary_parts.append(f"across {phrase_count} phrases")
    summary = ". ".join(summary_parts) + "."

    strengths = []
    if phrase_count >= 5:
        strengths.append("Good phrase count — you're building vocabulary")
    if vocabulary_diversity > 0.6:
        strengths.append("Nice variety in your note choices")
    if top_note:
        strengths.append(f"Strong tonal center on {top_note}")

    focus_areas = []
    if vocabulary_diversity < 0.4:
        focus_areas.append("Try exploring more notes outside your comfort zone")
    if phrase_count < 3:
        focus_areas.append("Aim for more phrases to develop your ideas")

    next_step = f"Practice connecting phrases in {scale_str} — try starting each phrase on a different note."

    return {
        "coach_summary": summary,
        "coach_strengths": strengths[:3],
        "coach_focus_areas": focus_areas[:3],
        "coach_next_step": next_step,
    }


def merge_coach_copy_into_sections(
    sections: list[LessonSectionStub],
    *,
    song_title: str | None,
    artist: str | None,
    key: str | None,
    player_profile: PlayerProfile | None = None,
    style_label: str | None = None,
    technique_hints: list[str] | None = None,
    focus_area: CoachFocusArea | None = None,
) -> list[LessonSectionStub]:
    """Populate coach fields on each section while preserving existing fields."""
    sections_out, _, _ = hydrate_coach_copy_into_sections(
        sections,
        song_title=song_title,
        artist=artist,
        key=key,
        player_profile=player_profile,
        style_label=style_label,
        technique_hints=technique_hints,
        focus_area=focus_area,
    )
    return sections_out


def hydrate_coach_copy_into_sections(
    sections: list[LessonSectionStub],
    *,
    song_title: str | None,
    artist: str | None,
    key: str | None,
    player_profile: PlayerProfile | None = None,
    style_label: str | None = None,
    technique_hints: list[str] | None = None,
    focus_area: CoachFocusArea | None = None,
) -> tuple[list[LessonSectionStub], str, str | None]:
    """
    Populate section coach fields and report hydration status.
    Processes sections concurrently to minimize wall-clock latency.
    Returns: (sections, status: complete|fallback, fallback_reason)
    """
    if not sections:
        return [], "complete", None

    # Submit all section requests concurrently, preserving original index
    from concurrent.futures import as_completed

    futures_to_idx: dict[Any, int] = {}
    for idx, sec in enumerate(sections):
        future = _COACH_EXECUTOR.submit(
            generate_coach_fields_for_section_with_status,
            section_label=sec.label,
            song_title=song_title,
            artist=artist,
            key=key,
            player_profile=player_profile,
            style_label=style_label,
            technique_hints=technique_hints,
            focus_area=focus_area,
        )
        futures_to_idx[future] = idx

    # Collect results as they complete
    results_by_idx: dict[int, CoachCallResult] = {}
    fallback_reason: str | None = None

    for future in as_completed(futures_to_idx):
        idx = futures_to_idx[future]
        try:
            result = future.result(timeout=COACH_TIMEOUT_SECONDS)
            results_by_idx[idx] = result
            if result.fallback_reason is not None and fallback_reason is None:
                fallback_reason = result.fallback_reason
        except FutureTimeoutError:
            logger.warning("hydrate_coach_copy section=%s fallback reason=timeout", idx)
            if fallback_reason is None:
                fallback_reason = "timeout"
            # Use fallback for this section
            note, explanation = _fallback_coach_fields()
            results_by_idx[idx] = CoachCallResult(
                note=note, explanation=explanation, fallback_reason="timeout"
            )
        except Exception as exc:
            logger.warning("hydrate_coach_copy section=%s fallback reason=api_error error=%s", idx, exc.__class__.__name__)
            if fallback_reason is None:
                fallback_reason = "api_error"
            note, explanation = _fallback_coach_fields()
            results_by_idx[idx] = CoachCallResult(
                note=note, explanation=explanation, fallback_reason="api_error"
            )

    # Build enriched sections in original order
    enriched: list[LessonSectionStub] = []
    for idx, sec in enumerate(sections):
        result = results_by_idx[idx]
        payload = sec.model_dump(exclude_none=True)
        payload["coach_note"] = result.note
        payload["coach_explanation"] = result.explanation
        enriched.append(LessonSectionStub(**payload))

    return enriched, ("fallback" if fallback_reason else "complete"), fallback_reason


def template_practice_plan_intros(
    slots_meta: list[dict[str, Any]],
    player_profile: PlayerProfile | None,
    *,
    mood: MoodState | None = None,
) -> list[str]:
    """Deterministic one-liners when Claude is unavailable or skipped (commit 70)."""
    _ = player_profile
    mood_prefix = ""
    if mood == "tired":
        mood_prefix = "Keep this gentle and compact. "
    elif mood == "on_fire":
        mood_prefix = "Great spark today — lean into it. "
    elif mood == "focused":
        mood_prefix = "Stay precise and deliberate. "
    elif mood == "loose":
        mood_prefix = "Keep this relaxed and musical. "
    out: list[str] = []
    for m in slots_meta:
        st = str(m.get("slot_type") or "")
        title = str(m.get("title") or "this slot").strip() or "this slot"
        if st == "warmup":
            wp = m.get("warmup_plan")
            if isinstance(wp, dict):
                ex = wp.get("exercises")
                if isinstance(ex, list) and ex:
                    names = []
                    for item in ex[:3]:
                        if isinstance(item, dict):
                            n = str(item.get("name") or "").strip()
                            if n:
                                names.append(n)
                    if names:
                        joined = ", then ".join(names)
                        out.append(
                            f"{mood_prefix}Open with {joined} — small motions, even pulse, and no death grip on the neck.",
                        )
                        continue
            out.append(f"{mood_prefix}Ease into {title} with tiny motions and an even pulse — no death grip on the neck.")
        elif st == "technique":
            tf = str(m.get("technique_focus") or "technique").replace("_", " ")
            out.append(f"{mood_prefix}Loop a small cell slowly and let the click expose rushing on {tf} before you add speed.")
        elif st == "song_section":
            song = str(m.get("song_title") or "the tune").strip() or "the tune"
            out.append(
                f"{mood_prefix}Stay inside one phrase of {song} at a time — sing it once, then match the shape on guitar."
            )
        else:
            out.append(f"{mood_prefix}Follow your ear in free play — keep dynamics conversational and leave space between ideas.")
    return out


def _parse_practice_plan_intros_json(raw_text: str, expected: int) -> list[str] | None:
    data = _extract_json_object(raw_text)
    if data is None:
        return None
    intros = data.get("intros")
    if not isinstance(intros, list) or len(intros) != expected:
        return None
    out: list[str] = []
    for item in intros:
        if not isinstance(item, str) or not item.strip():
            return None
        out.append(item.strip())
    return out


def generate_practice_plan_intros(
    slots_meta: list[dict[str, Any]],
    player_profile: PlayerProfile | None,
    *,
    mood: MoodState | None = None,
) -> list[str]:
    """Batch Claude call: one sentence per slot; strict length match to slot list."""
    if not slots_meta:
        return []
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_COACH_IN_TESTS") != "1":
        return template_practice_plan_intros(slots_meta, player_profile, mood=mood)

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.info("practice_plan_intros fallback reason=missing_api_key")
        return template_practice_plan_intros(slots_meta, player_profile, mood=mood)

    lines: list[str] = []
    for i, m in enumerate(slots_meta, 1):
        ds = int(m.get("duration_seconds") or 300)
        dm = max(1, ds // 60)
        lines.append(
            f"{i}. type={m.get('slot_type')} title={m.get('title')} ~{dm} min",
        )
    n = len(slots_meta)
    mood_line = (
        "Mood state for this session: unknown/default.\n"
        if mood is None
        else f"Mood state for this session: {mood}.\n"
    )
    user_prompt = (
        "Return JSON with exactly one key \"intros\" whose value is a JSON array of strings.\n"
        f"There must be exactly {n} strings, in the same order as the slots listed.\n"
        "Each string is exactly one short sentence (max 22 words), warm guitar-coach tone, plain English, actionable.\n"
        "Coach tone by mood: tired=gentle/reassuring, on_fire=energetic/celebratory, focused=precise/direct, loose=playful/low-pressure.\n"
        "No markdown fences inside strings.\n\n"
        + mood_line
        + "\n"
        "Slots:\n"
        + "\n".join(lines)
        + "\n\n"
        + _player_context_block(
            player_profile.model_dump(mode="json", exclude_none=True) if player_profile else None
        ).strip()
        + "\nOutput only JSON."
    )
    future = _COACH_EXECUTOR.submit(
        _call_claude_text,
        api_key=api_key,
        user_prompt=user_prompt,
        max_tokens=min(280, 55 * n),
        temperature=0.35,
    )
    try:
        raw_text = future.result(timeout=PRACTICE_PLAN_INTRO_TIMEOUT_SECONDS)
        parsed = _parse_practice_plan_intros_json(raw_text, n)
        if parsed is not None:
            return parsed
        logger.warning("practice_plan_intros fallback reason=parse_error")
    except FutureTimeoutError:
        logger.warning("practice_plan_intros fallback reason=timeout")
    except Exception as exc:
        logger.warning("practice_plan_intros fallback reason=api_error error=%s", exc.__class__.__name__)
    return template_practice_plan_intros(slots_meta, player_profile, mood=mood)


# Commit 84: Orient phase annotation

def generate_orient_annotation(
    style_label: str | None,
    technique: str | None,
    key: str | None,
    bpm: float | None,
) -> str:
    """
    Generate 2-3 sentences telling the user what to listen for in the orient clip.

    TODO: This is currently a template stub. Production should use Claude for
    dynamic generation based on style, technique, key, and BPM.
    Issue: Currently returns deterministic copy without AI inference.

    Args:
        style_label: Musical style (e.g., "rock", "blues", "jazz")
        technique: Target technique (e.g., "bend", "hammer-on", "slide")
        key: Musical key (e.g., "C major", "A minor")
        bpm: Tempo in beats per minute

    Returns:
        Annotation string telling the user what to listen for
    """
    # Template annotation for now - production would use Claude for dynamic generation
    style = style_label or "this style"
    tech = technique or "the technique"

    return f"Listen for how {tech} is used in this {style} example. Pay attention to the timing and how it fits with the rhythm section. Notice the subtle variations in sound quality and phrasing."


THEORY_ANNOTATION_USER_PROMPT = """Return valid JSON with exactly one string field "rationale".

Generate a plain-language theory explanation for this musical context:
- key: {key}
- chord: {chord}
- chord_function: {chord_function}

Explain in 1-2 sentences why this chord functions this way in the key. Use plain English — avoid jargon unless you immediately explain it.
Focus on how the chord feels (home base, tension, departure, return) and what it sets up next.
Output only JSON."""

FALLBACK_THEORY_RATIONALE = "This chord creates tension that wants to resolve back to the home key. Listen for how it pulls the ear toward the next chord."


def generate_theory_annotation(
    *,
    key: str | None,
    chord: str | None,
    chord_function: str | None,
) -> str:
    """
    Generate a plain-language theory rationale for a chord in a key context (PRIORITIES §85).

    Args:
        key: Musical key (e.g., "C major", "A minor")
        chord: Chord symbol (e.g., "C:maj", "D:min")
        chord_function: Roman numeral function (e.g., "I", "IV", "V")

    Returns:
        Rationale string explaining the chord's function in plain language
    """
    # Check kill-switch
    if os.getenv("HARMONIQ_SKIP_THEORY_ANNOTATE", "").strip() == "1":
        logger.info("theory_annotation fallback reason=HARMONIQ_SKIP_THEORY_ANNOTATE=1")
        return FALLBACK_THEORY_RATIONALE

    # Keep test runs deterministic and fully offline
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_COACH_IN_TESTS") != "1":
        logger.info("theory_annotation fallback reason=pytest_mode")
        return FALLBACK_THEORY_RATIONALE

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("theory_annotation fallback reason=missing_api_key")
        return FALLBACK_THEORY_RATIONALE

    user_prompt = THEORY_ANNOTATION_USER_PROMPT.format(
        key=key or "Unknown key",
        chord=chord or "Unknown chord",
        chord_function=chord_function or "Unknown function",
    )

    future = _COACH_EXECUTOR.submit(
        _call_claude_text,
        api_key=api_key,
        user_prompt=user_prompt,
        max_tokens=150,
        temperature=0.5,
    )

    try:
        raw_text = future.result(timeout=QUICK_FEEDBACK_TIMEOUT_SECONDS)
        parsed = _parse_theory_rationale_json(raw_text)
        if parsed is None:
            logger.warning("theory_annotation fallback reason=parse_error")
            return FALLBACK_THEORY_RATIONALE
        return parsed
    except FutureTimeoutError:
        future.cancel()
        logger.warning("theory_annotation fallback reason=timeout")
        return FALLBACK_THEORY_RATIONALE
    except Exception as exc:
        logger.warning("theory_annotation fallback reason=api_error error=%s", exc.__class__.__name__)
        return FALLBACK_THEORY_RATIONALE
