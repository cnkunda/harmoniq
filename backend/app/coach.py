"""Anthropic-powered section coach copy with safe local fallback."""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from app.schemas import LessonSectionStub, PlayerProfile

logger = logging.getLogger("harmoniq.coach")
logger.setLevel(logging.INFO)

MODEL_ID = "claude-sonnet-4-20250514"
COACH_TIMEOUT_SECONDS = 8.0
QUICK_FEEDBACK_TIMEOUT_SECONDS = 5.0
COACH_PROFILE_RETRY_LIMIT = 2
COACH_PROFILE_TEMPERATURE_INITIAL = 0.5
COACH_PROFILE_TEMPERATURE_RETRY = 0.3

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

COACH_USER_PROMPT_TEMPLATE = """Return valid JSON with exactly three string fields:
- coach_note
- coach_explanation
- weak_focus

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


def _player_context_block(profile: PlayerProfile | None) -> str:
    if profile is None:
        return ""
    data = profile.model_dump(mode="json", exclude_none=True)
    weak = data.get("weak_areas") or []
    nodes = data.get("skill_nodes") or []
    if not weak and not nodes:
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
    lines.append("Do not quote this block verbatim in the JSON output.")
    lines.append("</player_context>")
    return "\n".join(lines) + "\n\n"


def _profile_priority_directive(profile: PlayerProfile | None) -> str:
    if profile is None:
        return ""
    data = profile.model_dump(mode="json", exclude_none=True)
    weak = [str(w).strip() for w in (data.get("weak_areas") or []) if str(w).strip()]
    nodes = data.get("skill_nodes") or []
    if not weak and not nodes:
        return ""
    if weak:
        joined = ", ".join(weak[:8])
        focus_line = (
            "Profile-priority requirement: make coach_note or the first sentence of coach_explanation "
            f"explicitly reference at least one weak-area concept ({joined}) in plain language."
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
) -> str:
    """Assemble the user message: optional context blocks + fixed JSON contract."""
    prefix = _player_context_block(player_profile) + _song_style_block(style_label, technique_hints)
    profile_priority = _profile_priority_directive(player_profile)
    body = COACH_USER_PROMPT_TEMPLATE.format(
        section_label=(section_label or "Section"),
        song_title=(song_title or "Unknown song"),
        artist=(artist or "Unknown artist"),
        key=(key or "Unknown key"),
    )
    return prefix + profile_priority + body


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


QUICK_FEEDBACK_USER_PROMPT = """Return valid JSON with exactly one string field "message".
The guitarist just played along for several beats. Per-beat pitch accuracy (chronological, one label per beat): {pattern}

Write one short sentence (max 28 words) — the single most useful thing to try on the next pass.
Plain English. No markdown inside the string. Never start with "Great job" or "Nice work".
Output only JSON."""

FALLBACK_QUICK_FEEDBACK = (
    "A few beats wandered wide — lighten the grip and aim to land the target pitch a hair earlier so it settles in tune."
)


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


def _call_claude_text(
    *,
    api_key: str,
    user_prompt: str,
    max_tokens: int = 220,
    temperature: float = 1.0,
) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=max_tokens,
        temperature=temperature,
        system=BASE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return _extract_text_from_response(response)


def _parse_coach_json(raw_text: str) -> tuple[str, str, str] | None:
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
    weak_focus = data.get("weak_focus")
    if not isinstance(weak_focus, str) or not weak_focus.strip():
        weak_focus = "none"
    return note.strip(), explanation.strip(), weak_focus.strip()


def _parse_quick_message_json(raw_text: str) -> str | None:
    import json

    raw = (raw_text or "").strip()
    if not raw:
        return None
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
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
    msg = data.get("message")
    if not isinstance(msg, str) or not msg.strip():
        return None
    return msg.strip()


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
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _call_claude_text,
        api_key=api_key,
        user_prompt=user_prompt,
        max_tokens=110,
        temperature=0.4,
    )
    try:
        raw_text = future.result(timeout=QUICK_FEEDBACK_TIMEOUT_SECONDS)
        parsed = _parse_quick_message_json(raw_text)
        if parsed is None:
            logger.warning("quick_feedback fallback reason=unparseable_response")
            return FALLBACK_QUICK_FEEDBACK
        return parsed
    except FutureTimeoutError:
        future.cancel()
        logger.warning("quick_feedback fallback reason=timeout")
        return FALLBACK_QUICK_FEEDBACK
    except Exception as exc:
        logger.warning("quick_feedback fallback reason=api_error error=%s", exc.__class__.__name__)
        return FALLBACK_QUICK_FEEDBACK
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def generate_coach_fields_for_section(
    *,
    section_label: str | None,
    song_title: str | None,
    artist: str | None,
    key: str | None,
    player_profile: PlayerProfile | None = None,
    style_label: str | None = None,
    technique_hints: list[str] | None = None,
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

    user_prompt = build_coach_user_prompt(
        section_label=section_label,
        song_title=song_title,
        artist=artist,
        key=key,
        player_profile=player_profile,
        style_label=style_label,
        technique_hints=technique_hints,
    )
    focus_terms = _profile_focus_terms(player_profile)
    attempts = 1 + (COACH_PROFILE_RETRY_LIMIT if focus_terms else 0)
    pool = ThreadPoolExecutor(max_workers=1)
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
            future = pool.submit(
                _call_claude_text,
                api_key=api_key,
                user_prompt=prompt,
                temperature=temperature,
            )
            raw_text = future.result(timeout=COACH_TIMEOUT_SECONDS)
            parsed = _parse_coach_json(raw_text)
            if parsed is None:
                logger.warning(
                    "coach unparseable_response attempt=%s/%s",
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
                return note, explanation
            logger.info(
                "coach profile_focus_retry attempt=%s/%s weak_focus=%s",
                attempt + 1,
                attempts,
                weak_focus,
            )
        logger.warning("coach fallback reason=profile_focus_not_met")
        return _fallback_coach_fields()
    except FutureTimeoutError:
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


def merge_coach_copy_into_sections(
    sections: list[LessonSectionStub],
    *,
    song_title: str | None,
    artist: str | None,
    key: str | None,
    player_profile: PlayerProfile | None = None,
    style_label: str | None = None,
    technique_hints: list[str] | None = None,
) -> list[LessonSectionStub]:
    """Populate coach fields on each section while preserving existing fields."""
    enriched: list[LessonSectionStub] = []
    for sec in sections:
        note, explanation = generate_coach_fields_for_section(
            section_label=sec.label,
            song_title=song_title,
            artist=artist,
            key=key,
            player_profile=player_profile,
            style_label=style_label,
            technique_hints=technique_hints,
        )
        payload = sec.model_dump(exclude_none=True)
        payload["coach_note"] = note
        payload["coach_explanation"] = explanation
        enriched.append(LessonSectionStub(**payload))
    return enriched
