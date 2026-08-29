"""LLM-Enhanced Chord Correction & Roman Numeral Analysis (Commit 114).

Post-processes raw ChordTimeline through a lightweight LLM (Claude Haiku) to:
1. Correct improbable chord changes based on key context
2. Add Roman numeral functional labels (I, ii, V7, IV, etc.)
3. Cache results with SHA256 to avoid redundant LLM calls

Inspired by ChordMini's Gemini integration and MT3's musical reasoning.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from app.schemas import ChordEvent, ChordTimeline

logger = logging.getLogger("harmoniq.chord_enrichment")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ENRICHMENT_MODEL = os.getenv("HARMONIQ_ENRICHMENT_MODEL", "claude-haiku-4-5")
ENRICHMENT_TIMEOUT_SECONDS = max(1.0, float(os.getenv("HARMONIQ_ENRICHMENT_TIMEOUT_MS", "10000")) / 1000.0)
ENRICHMENT_MAX_RETRIES = 1
CONFIDENCE_DELTA_THRESHOLD = float(os.getenv("HARMONIQ_ENRICHMENT_DELTA", "0.15"))
RATE_LIMIT_INTERVAL = float(os.getenv("HARMONIQ_ENRICHMENT_RATE_LIMIT_S", "10.0"))

# Models to try in order when the primary model returns 404.
_ENRICHMENT_MODEL_FALLBACK: list[str] = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
]

# Module-level executor for background enrichment
_ENRICHMENT_EXECUTOR = ThreadPoolExecutor(max_workers=2)

# In-process rate limiter
_last_enrichment_call: float = 0.0

# In-process SHA256 cache: key → enriched result
_enrichment_cache: dict[str, list[dict]] = {}
_CACHE_MAX_SIZE = 256

# Roman numeral mapping: quality → Roman numeral pattern
_ROMAN_NUMERALS: dict[str, dict[str, str]] = {
    "major": {
        "I": "I", "II": "II", "III": "III", "IV": "IV", "V": "V", "VI": "VI", "VII": "VII",
    },
    "minor": {
        "I": "i", "II": "ii", "III": "iii", "IV": "iv", "V": "v", "VI": "vi", "VII": "vii",
    },
}

# Quality to chord function mapping
_QUALITY_FUNCTION: dict[str, str] = {
    "maj": "", "min": "m", "7": "7", "maj7": "maj7", "min7": "m7",
    "9": "9", "min9": "m9", "maj9": "maj9", "11": "11", "13": "13",
    "7#9": "7#9", "7b9": "7b9", "7#5": "7#5", "7b5": "7b5", "alt7": "7alt",
    "sus2": "sus2", "sus4": "sus4", "7sus4": "7sus4",
    "dim": "dim", "dim7": "dim7", "aug": "aug", "6": "6", "min6": "m6",
}

# Semitone offsets from key root to scale degrees
# Major key: I=0, ii=2, iii=4, IV=5, V=7, vi=9, vii=11
_MAJOR_SEMITONE_TO_DEGREE = {0: 1, 2: 2, 4: 3, 5: 4, 7: 5, 9: 6, 11: 7}
# Minor key: i=0, ii=2, III=3, iv=5, v=7, VI=8, VII=10
_MINOR_SEMITONE_TO_DEGREE = {0: 1, 2: 2, 3: 3, 5: 4, 7: 5, 8: 6, 10: 7}

_NOTE_TO_SEMITONE = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}

# Degree → Roman numeral (lowercase = minor quality expected in key)
_DEGREE_TO_ROMAN_MAJOR = {1: "I", 2: "ii", 3: "iii", 4: "IV", 5: "V", 6: "vi", 7: "vii"}
_DEGREE_TO_ROMAN_MINOR = {1: "i", 2: "ii", 3: "III", 4: "iv", 5: "v", 6: "VI", 7: "VII"}


# ---------------------------------------------------------------------------
# Deterministic Roman Numeral computation (no LLM needed)
# ---------------------------------------------------------------------------
def compute_roman_numeral(chord: str, key_signature: str | None) -> str | None:
    """Compute Roman numeral for a chord given the key signature.

    This is a deterministic music-theory computation, not LLM-based.
    Returns None when key is unknown or chord is "N".
    """
    if not key_signature or chord == "N":
        return None

    # Parse key: "C major" → root="C", mode="major"; "A minor" → root="A", mode="minor"
    parts = key_signature.strip().split()
    if len(parts) < 2:
        return None
    key_root = parts[0]
    mode = parts[1].lower()

    # Parse chord: "C:maj" → root="C", quality="maj"; "G:7" → root="G", quality="7"
    chord_parts = chord.split(":")
    if len(chord_parts) < 2:
        return None
    chord_root = chord_parts[0]
    quality = chord_parts[1]

    # Compute semitone offset from key root to chord root
    key_semitone = _NOTE_TO_SEMITONE.get(key_root)
    chord_semitone = _NOTE_TO_SEMITONE.get(chord_root)
    if key_semitone is None or chord_semitone is None:
        return None

    interval = (chord_semitone - key_semitone) % 12

    # Look up scale degree from semitone interval
    if mode == "minor":
        degree = _MINOR_SEMITONE_TO_DEGREE.get(interval)
        degree_map = _DEGREE_TO_ROMAN_MINOR
    else:
        degree = _MAJOR_SEMITONE_TO_DEGREE.get(interval)
        degree_map = _DEGREE_TO_ROMAN_MAJOR

    if degree is None:
        return None

    roman_base = degree_map[degree]

    # Adjust case based on actual chord quality vs expected quality in key
    # Lowercase = minor/dim quality, Uppercase = major/aug quality
    is_major_quality = quality in ("maj", "6") or quality.startswith("maj")
    is_minor_quality = quality in ("min",) or quality.startswith("min") or quality == "dim"

    if is_major_quality and roman_base[0].islower():
        roman_base = roman_base.upper()
    elif is_minor_quality and roman_base[0].isupper():
        roman_base = roman_base.lower()

    # Build suffix: only include extension/alteration part
    suffix = ""
    if quality in ("7", "9", "11", "13"):
        suffix = quality
    elif quality in ("min7", "min9"):
        suffix = "7" if quality == "min7" else "9"
    elif quality in ("maj7", "maj9"):
        suffix = "maj7" if quality == "maj7" else "maj9"
    elif quality in ("7#9", "7b9", "7#5", "7b5", "alt7", "7sus4"):
        suffix = quality
    elif quality in ("sus2", "sus4"):
        suffix = quality
    elif quality == "dim7":
        suffix = "dim7"
    elif quality == "min6":
        suffix = "6"
    elif quality == "6":
        suffix = "6"

    return f"{roman_base}{suffix}"


# ---------------------------------------------------------------------------
# SHA256 cache helpers
# ---------------------------------------------------------------------------
def _cache_key(chord_timeline: ChordTimeline, key_signature: str | None) -> str:
    """Compute SHA256 cache key from chord timeline + key."""
    payload = json.dumps({
        "chords": [(e.timestamp, e.chord, e.confidence) for e in chord_timeline.events],
        "key": key_signature,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached(cache_key: str) -> list[dict] | None:
    """Retrieve cached enrichment result."""
    return _enrichment_cache.get(cache_key)


def _set_cached(cache_key: str, result: list[dict]) -> None:
    """Store enrichment result in cache with LRU eviction."""
    if len(_enrichment_cache) >= _CACHE_MAX_SIZE:
        # Evict oldest entry
        oldest_key = next(iter(_enrichment_cache))
        del _enrichment_cache[oldest_key]
    _enrichment_cache[cache_key] = result


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
def _rate_limit_wait() -> None:
    """Block until rate limit interval has elapsed since last call."""
    global _last_enrichment_call
    elapsed = time.time() - _last_enrichment_call
    if elapsed < RATE_LIMIT_INTERVAL:
        time.sleep(RATE_LIMIT_INTERVAL - elapsed)
    _last_enrichment_call = time.time()


# ---------------------------------------------------------------------------
# LLM call (follows coach.py pattern)
# ---------------------------------------------------------------------------
def _call_llm_enrichment(prompt: str) -> str | None:
    """Call Claude Haiku for chord enrichment. Returns raw text or None on failure."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("No ANTHROPIC_API_KEY set; skipping LLM enrichment")
        return None

    _rate_limit_wait()

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        models = [ENRICHMENT_MODEL] + [m for m in _ENRICHMENT_MODEL_FALLBACK if m != ENRICHMENT_MODEL]
        last_error: Exception | None = None

        for model_id in models:
            try:
                response = client.messages.create(
                    model=model_id,
                    max_tokens=1024,
                    timeout=ENRICHMENT_TIMEOUT_SECONDS,
                    messages=[{"role": "user", "content": prompt}],
                    system=(
                        "You are a music theory expert. Given a chord progression and key, "
                        "correct improbable chord changes and add Roman numeral analysis. "
                        "Return ONLY a JSON array — no markdown, no explanation."
                    ),
                )
                text = response.content[0].text.strip()
                return text
            except Exception as exc:
                last_error = exc
                if "404" not in str(exc) and type(exc).__name__ != "NotFoundError":
                    raise
                logger.warning("enrichment model %s unavailable (404), trying fallback", model_id)
                continue

        logger.warning("LLM enrichment call failed (all models): %s", type(last_error).__name__)
        return None
    except Exception as exc:
        logger.warning("LLM enrichment call failed: %s", type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
def _build_enrichment_prompt(
    chord_events: list[ChordEvent],
    key_signature: str,
    section_start: float | None = None,
    section_end: float | None = None,
) -> str:
    """Build the LLM prompt for chord correction + Roman numeral labeling."""
    # Format chord timeline for the LLM
    chord_lines = []
    for i, ev in enumerate(chord_events):
        chord_lines.append(f"  {i}: {ev.chord} (t={ev.timestamp:.2f}s, conf={ev.confidence:.2f})")

    chord_text = "\n".join(chord_lines)

    prompt = f"""Given key={key_signature}, correct improbable chord changes in this timeline.

Chord timeline:
{chord_text}

Return a JSON array preserving original timestamps, with corrected chord
symbols and Roman numeral labels (e.g., I, ii, V7, IV).

Each element: {{"index": <int>, "corrected_chord": "<chord>", "roman_numeral": "<roman>", "confidence_delta": <float 0-1>}}

Rules:
- Only correct chords that are clearly wrong for the key (e.g., F# in key of C major → F)
- confidence_delta = how much better the corrected chord fits than the original (0 = no change)
- If a chord is fine as-is, set corrected_chord = original and confidence_delta = 0
- Roman numerals: uppercase for major (I, IV, V), lowercase for minor (ii, iii, vi)
- Return ONLY the JSON array, no other text."""

    return prompt


# ---------------------------------------------------------------------------
# Main enrichment function
# ---------------------------------------------------------------------------
def enrich_chord_timeline(
    chord_timeline: ChordTimeline,
    key_signature: str | None = None,
    section_range: tuple[float, float] | None = None,
) -> tuple[ChordTimeline, dict]:
    """Enrich chord timeline with LLM correction and Roman numeral labels.

    Args:
        chord_timeline: Raw chord timeline from Viterbi post-processing.
        key_signature: Song key (e.g., "C major"). If None, Roman numerals are skipped.
        section_range: Optional (start, end) time range to enrich.

    Returns:
        Tuple of (enriched ChordTimeline, metrics dict).
    """
    if not chord_timeline.events:
        return chord_timeline, {"enrichment_applied": 0, "llm_called": False}

    # Filter to section range if specified
    events = chord_timeline.events
    if section_range is not None:
        start, end = section_range
        events = [e for e in events if start <= e.timestamp < end]

    # Check cache
    cache_key = _cache_key(ChordTimeline(events=events), key_signature)
    cached = _get_cached(cache_key)
    if cached is not None:
        logger.debug("Cache hit for enrichment key=%s", cache_key[:12])
        enriched = _apply_enrichment(chord_timeline, events, cached, section_range)
        return enriched, {
            "enrichment_applied": sum(1 for r in cached if r.get("confidence_delta", 0) > 0),
            "llm_called": False,
            "roman_numerals_assigned": sum(1 for r in cached if r.get("roman_numeral")),
            "cache_hit": True,
        }

    # Deterministic Roman numerals (no LLM needed)
    deterministic_results = []
    for ev in events:
        roman = compute_roman_numeral(ev.chord, key_signature)
        deterministic_results.append({
            "index": events.index(ev),
            "corrected_chord": ev.chord,
            "roman_numeral": roman,
            "confidence_delta": 0.0,
        })

    # Try LLM enrichment for chord correction
    llm_called = False
    if key_signature and len(events) >= 2:
        prompt = _build_enrichment_prompt(events, key_signature)
        raw_response = _call_llm_enrichment(prompt)
        llm_called = raw_response is not None

        if raw_response:
            try:
                # Parse LLM response
                # Strip markdown code fences if present
                cleaned = raw_response.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                    cleaned = re.sub(r"\s*```$", "", cleaned)

                llm_results = json.loads(cleaned)
                if isinstance(llm_results, list):
                    # Merge LLM corrections with deterministic Roman numerals
                    for llm_item in llm_results:
                        idx = llm_item.get("index", -1)
                        if 0 <= idx < len(deterministic_results):
                            delta = llm_item.get("confidence_delta", 0.0)
                            if delta > CONFIDENCE_DELTA_THRESHOLD:
                                deterministic_results[idx]["corrected_chord"] = llm_item.get(
                                    "corrected_chord", deterministic_results[idx]["corrected_chord"]
                                )
                                deterministic_results[idx]["confidence_delta"] = delta
                            # Always use LLM Roman numeral if available
                            if llm_item.get("roman_numeral"):
                                deterministic_results[idx]["roman_numeral"] = llm_item["roman_numeral"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning("Failed to parse LLM enrichment response: %s", exc)

    # Cache the result
    _set_cached(cache_key, deterministic_results)

    return _apply_enrichment(chord_timeline, events, deterministic_results, section_range), {
        "enrichment_applied": sum(1 for r in deterministic_results if r["confidence_delta"] > 0),
        "llm_called": llm_called,
        "roman_numerals_assigned": sum(1 for r in deterministic_results if r["roman_numeral"]),
    }


def _apply_enrichment(
    original_timeline: ChordTimeline,
    events: list[ChordEvent],
    results: list[dict],
    section_range: tuple[float, float] | None,
) -> ChordTimeline:
    """Apply enrichment results back to the full chord timeline."""
    # Build lookup: timestamp → enrichment
    enrichment_by_ts: dict[float, dict] = {}
    for r in results:
        if r["index"] < len(events):
            enrichment_by_ts[events[r["index"]].timestamp] = r

    enriched_events = []
    for ev in original_timeline.events:
        enrichment = enrichment_by_ts.get(ev.timestamp)
        if enrichment:
            enriched_events.append(ChordEvent(
                timestamp=ev.timestamp,
                chord=enrichment["corrected_chord"],
                confidence=ev.confidence,
                roman_numeral=enrichment.get("roman_numeral"),
                llm_corrected_chord=enrichment["corrected_chord"] if enrichment["confidence_delta"] > 0 else None,
                correction_delta=enrichment.get("confidence_delta", 0.0),
            ))
        else:
            enriched_events.append(ev)

    return ChordTimeline(events=enriched_events)


# ---------------------------------------------------------------------------
# Background worker (called from jobs.py)
# ---------------------------------------------------------------------------
def enrich_chord_timeline_background(
    job_id: str,
    chord_timeline: ChordTimeline,
    key_signature: str | None = None,
    on_complete: Any | None = None,
) -> None:
    """Run chord enrichment in a background thread.

    Args:
        job_id: Job ID for logging.
        chord_timeline: Chord timeline to enrich.
        key_signature: Song key for Roman numeral computation.
        on_complete: Optional callback(enriched_timeline, metrics) on completion.
    """
    def _worker():
        try:
            enriched, metrics = enrich_chord_timeline(
                chord_timeline,
                key_signature=key_signature,
            )
            logger.info(
                "chord_enrichment_complete job_id=%s applied=%d llm_called=%s roman=%d",
                job_id,
                metrics.get("enrichment_applied", 0),
                metrics.get("llm_called", False),
                metrics.get("roman_numerals_assigned", 0),
            )
            if on_complete:
                on_complete(enriched, metrics)
        except Exception:
            logger.exception("chord_enrichment_failed job_id=%s", job_id)
            if on_complete:
                on_complete(chord_timeline, {"enrichment_applied": 0, "llm_called": False, "error": True})

    _ENRICHMENT_EXECUTOR.submit(_worker)
