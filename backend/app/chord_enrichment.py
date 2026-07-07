"""Chord enrichment: deterministic Roman numeral labels + LLM correction (Commit 116).

Two-layer enrichment:
  1. Deterministic Roman numeral assignment (always runs, zero latency).
  2. LLM-based improbable-chord correction (background thread, optional).

The LLM layer calls Claude Haiku to correct improbable chord changes and
refine Roman numeral labels for non-diatonic chords. It runs as a background
worker after the main analysis completes, following the same pattern as
coach hydration in jobs.py.
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

from app.chord_vocab import CHORD_INTERVALS, ROOT_NOTES
from app.schemas import ChordEvent, ChordTimeline

logger = logging.getLogger("harmoniq.chord_enrichment")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------

MODEL_ID = os.getenv("HARMONIQ_CHORD_ENRICHMENT_MODEL", "claude-haiku-4-5-20251001")
ENRICHMENT_TIMEOUT_SECONDS = max(
    0.5, float(os.getenv("HARMONIQ_CHORD_ENRICHMENT_TIMEOUT_MS", "12000")) / 1000.0
)
ENRICHMENT_RATE_LIMIT_SECONDS = 10.0
ENRICHMENT_CONFIDENCE_THRESHOLD = 0.15

_EXECUTOR = ThreadPoolExecutor(max_workers=2)

# Lazy import for anthropic (avoids hard dependency at module load time)
_Anthropic: type | None = None

# In-memory cache: SHA256(key + chord_timeline_json) → enriched timeline dict
_cache: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Deterministic Roman numeral assignment
# ---------------------------------------------------------------------------

# Diatonic degree → Roman numeral mapping (semitone offset from key root)
_MAJOR_DEGREE_ROMAN: dict[int, str] = {
    0: "I",
    2: "ii",
    4: "iii",
    5: "IV",
    7: "V",
    9: "vi",
    11: "vii°",
}

_MINOR_DEGREE_ROMAN: dict[int, str] = {
    0: "i",
    2: "ii°",
    3: "III",
    5: "iv",
    7: "v",
    8: "VI",
    10: "VII",
}

# Seventh chord quality suffixes → Roman numeral suffix
_SEVENTH_SUFFIX: dict[str, str] = {
    "7": "7",
    "maj7": "maj7",
    "min7": "7",
    "9": "9",
    "min9": "9",
    "maj9": "maj9",
    "11": "11",
    "13": "13",
    "7#9": "7#9",
    "7b9": "7b9",
    "7#5": "7#5",
    "7b5": "7b5",
    "alt7": "7alt",
    "dim7": "°7",
    "7sus4": "7sus4",
}

# Qualities that are "minor-family" (lowercase Roman numerals)
_MINOR_FAMILY = {"min", "min7", "min9", "min6", "dim", "dim7"}

# Qualities that are "major-family" (uppercase Roman numerals)
_MAJOR_FAMILY = {"maj", "maj7", "maj9", "6"}

# Qualities that are "dominant" (uppercase Roman numerals)
_DOMINANT_FAMILY = {"7", "7#9", "7b9", "7#5", "7b5", "alt7", "7sus4"}

# Suspended chords — treat as major-family for case
_SUS_FAMILY = {"sus2", "sus4"}

# Augmented — treat as major-family for case
_AUG_FAMILY = {"aug"}


def _parse_key(key: str) -> tuple[int, str]:
    """Parse key string like 'C major', 'A minor', 'C', 'A#m' → (root_semitone, mode).

    Returns (root_semitone 0-11, 'major'|'minor').
    """
    key = key.strip()
    if not key:
        return 0, "major"

    # Handle patterns: "C major", "C minor", "A minor", "Cmaj", "Amin", "C", "Am"
    m = re.match(r"^([A-G][#b]?)(.*)$", key)
    if not m:
        return 0, "major"

    root_str = m.group(1)
    mode_str = m.group(2).strip().lower()

    # Normalize root to semitone
    root_str = root_str.replace("b", "")
    if root_str not in ROOT_NOTES:
        return 0, "major"
    root_semi = ROOT_NOTES.index(root_str)

    # Determine mode
    if mode_str in ("minor", "min", "m"):
        return root_semi, "minor"
    return root_semi, "major"


def _parse_chord_symbol(chord: str) -> tuple[int, str]:
    """Parse chord symbol like 'C:maj', 'D:min7', 'G:7', 'N' → (root_semitone, quality).

    Returns (-1, 'N') for no-chord.
    """
    if chord == "N" or not chord:
        return -1, "N"

    parts = chord.split(":")
    if len(parts) != 2:
        return -1, "N"

    root_str, qual = parts
    root_str = root_str.replace("b", "")
    if root_str not in ROOT_NOTES:
        return -1, "N"

    return ROOT_NOTES.index(root_str), qual


def _root_to_degree(root_semitone: int, key_root: int) -> int:
    """Convert absolute root semitone to scale degree (0-11) relative to key root."""
    return (root_semitone - key_root) % 12


def _is_minor_quality(qual: str) -> bool:
    """Check if chord quality implies minor-family (lowercase Roman)."""
    return qual in _MINOR_FAMILY


def _is_major_quality(qual: str) -> bool:
    """Check if chord quality implies major-family (uppercase Roman)."""
    return qual in (_MAJOR_FAMILY | _DOMINANT_FAMILY | _SUS_FAMILY | _AUG_FAMILY)


def compute_roman_numeral(chord: str, key: str) -> str:
    """Compute Roman numeral label for a chord in a given key.

    Handles diatonic triads, sevenths, and non-diatonic chords.

    Examples:
        compute_roman_numeral("C:maj", "C major") → "I"
        compute_roman_numeral("D:min7", "C major") → "ii7"
        compute_roman_numeral("G:7", "C major") → "V7"
        compute_roman_numeral("F#:min", "C major") → "#IVm"
        compute_roman_numeral("N", "C major") → ""
    """
    if chord == "N" or not chord:
        return ""

    key_root, key_mode = _parse_key(key)
    root_semi, qual = _parse_chord_symbol(chord)
    if root_semi < 0:
        return ""

    degree = _root_to_degree(root_semi, key_root)

    # Build Roman numeral from degree
    base_roman = _get_base_roman(degree, key_mode, qual)

    # Add quality suffix for seventh/extended chords
    suffix = _get_quality_suffix(qual)

    return base_roman + suffix


def _get_base_roman(degree: int, key_mode: str, qual: str) -> str:
    """Get the base Roman numeral (no quality suffix) for a diatonic degree."""
    if key_mode == "minor":
        diatonic_map = _MINOR_DEGREE_ROMAN
    else:
        diatonic_map = _MAJOR_DEGREE_ROMAN

    # Check if this degree is in the diatonic map
    if degree in diatonic_map:
        base = diatonic_map[degree]
        # Adjust case based on actual chord quality
        if _is_minor_quality(qual):
            return base.lower() if base[0].isupper() else base
        if _is_major_quality(qual):
            return base.upper() if base[0].islower() else base
        return base

    # Non-diatonic: compute accidental prefix
    # Find closest diatonic degree
    diatonic_degrees = sorted(diatonic_map.keys())
    closest = min(diatonic_degrees, key=lambda d: min((degree - d) % 12, (d - degree) % 12))
    distance = (degree - closest) % 12

    base = diatonic_map[closest]

    # Build accidental prefix
    if distance <= 6:
        prefix = "#" * distance
    else:
        prefix = "b" * (12 - distance)

    # Apply case based on quality
    roman = prefix + base
    if _is_minor_quality(qual):
        return roman.lower() if roman[len(prefix)].isupper() else roman
    if _is_major_quality(qual):
        return roman.upper() if roman[len(prefix)].islower() else roman
    return roman


def _get_quality_suffix(qual: str) -> str:
    """Get the quality suffix for a Roman numeral from chord quality.

    For simple triads (maj, min, dim, aug), the base Roman numeral already
    encodes the quality via case (uppercase=major, lowercase=minor) and the
    ° symbol. Only add suffixes for seventh/extended/special qualities.
    """
    # Simple triads — no suffix needed (case + ° handle it)
    if qual in ("maj", "min", "dim", "aug"):
        return ""
    if qual in ("sus2",):
        return "sus2"
    if qual in ("sus4",):
        return "sus4"
    if qual in ("6",):
        return "6"
    if qual in ("min6",):
        return "m6"
    # Seventh/extended qualities
    return _SEVENTH_SUFFIX.get(qual, "")


def assign_roman_numerals(events: list[ChordEvent], key: str) -> list[ChordEvent]:
    """Assign deterministic Roman numeral labels to all chord events.

    Returns the same list (mutated in place) for convenience.
    """
    for event in events:
        event.roman_numeral = compute_roman_numeral(event.chord, key)
    return events


# ---------------------------------------------------------------------------
# LLM enrichment (background worker)
# ---------------------------------------------------------------------------

def _build_enrichment_prompt(
    key: str,
    chord_batch: list[dict[str, Any]],
) -> str:
    """Build the prompt for Claude Haiku chord correction."""
    chords_str = json.dumps(
        [{"timestamp": c["timestamp"], "chord": c["chord"]} for c in chord_batch],
        indent=None,
    )
    return (
        f"Given key={key}, correct improbable chord changes in this timeline. "
        f"Return a JSON array preserving original timestamps, with corrected chord "
        f"symbols and Roman numeral labels (e.g., I, ii, V7, IV). "
        f"Only correct chords that are clearly wrong for the key — if a chord is "
        f"plausible, keep the original. "
        f"Input: {chords_str}"
    )


def _call_claude_enrichment(
    *,
    api_key: str,
    key: str,
    chord_batch: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Call Claude Haiku for chord correction. Returns parsed JSON or None on failure."""
    if not api_key:
        return None

    # Kill-switch
    if os.getenv("HARMONIQ_SKIP_CHORD_ENRICHMENT", "").strip() == "1":
        return None

    # Pytest guard
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("HARMONIQ_ENABLE_ENRICHMENT_IN_TESTS") != "1":
        return None

    try:
        # Lazy import anthropic to avoid hard dependency at module load time
        global _Anthropic
        if _Anthropic is None:
            from anthropic import Anthropic as _AnthropicCls
            _Anthropic = _AnthropicCls

        client = _Anthropic(api_key=api_key)
        prompt = _build_enrichment_prompt(key, chord_batch)

        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else ""

        # Extract JSON array from response
        json_match = re.search(r"\[.*\]", text, re.DOTALL)
        if not json_match:
            logger.warning("LLM enrichment: no JSON array in response")
            return None

        parsed = json.loads(json_match.group())
        if not isinstance(parsed, list):
            logger.warning("LLM enrichment: response is not a list")
            return None

        return parsed

    except Exception:
        logger.exception("LLM enrichment call failed")
        return None


def _compute_cache_key(key: str, events: list[ChordEvent]) -> str:
    """Compute SHA256 cache key from key + chord timeline."""
    timeline_str = json.dumps(
        [{"t": e.timestamp, "c": e.chord} for e in events],
        sort_keys=True,
    )
    raw = f"{key}|{timeline_str}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _apply_llm_corrections(
    events: list[ChordEvent],
    llm_results: list[dict[str, Any]],
    key: str,
) -> int:
    """Apply LLM corrections to events. Returns count of corrections applied."""
    # Build lookup by timestamp
    llm_by_time: dict[float, dict[str, Any]] = {}
    for item in llm_results:
        t = item.get("timestamp")
        if t is not None:
            llm_by_time[float(t)] = item

    corrected = 0
    for event in events:
        llm_item = llm_by_time.get(event.timestamp)
        if llm_item is None:
            continue

        llm_chord = llm_item.get("chord", event.chord)
        llm_roman = llm_item.get("roman_numeral")

        if llm_chord == event.chord:
            # LLM kept original — still update Roman numeral if provided
            if llm_roman:
                event.roman_numeral = llm_roman
            continue

        # Apply correction: set corrected chord and mark
        event.llm_corrected_chord = llm_chord
        event.correction_applied = True
        event.correction_delta = abs(event.confidence - 0.5)  # heuristic delta
        event.chord = llm_chord

        # Update Roman numeral from LLM or recompute
        if llm_roman:
            event.roman_numeral = llm_roman
        else:
            event.roman_numeral = compute_roman_numeral(llm_chord, key)

        corrected += 1

    return corrected


def enrich_chord_timeline(
    events: list[ChordEvent],
    key: str,
    *,
    api_key: str = "",
) -> tuple[list[ChordEvent], dict[str, Any]]:
    """Run LLM enrichment on a chord timeline.

    Returns (enriched_events, metrics) where metrics contains:
      - corrected_events: int
      - llm_latency_p50: float | None
      - llm_latency_p95: float | None
      - cache_hit: bool
    """
    metrics: dict[str, Any] = {
        "corrected_events": 0,
        "llm_latency_p50": None,
        "llm_latency_p95": None,
        "cache_hit": False,
    }

    if not events:
        return events, metrics

    # Always assign deterministic Roman numerals first
    assign_roman_numerals(events, key)

    # Skip LLM enrichment when no API key or kill-switch active
    if not api_key:
        return events, metrics

    if os.getenv("HARMONIQ_SKIP_CHORD_ENRICHMENT", "").strip() == "1":
        return events, metrics

    # Check cache
    cache_key = _compute_cache_key(key, events)
    if cache_key in _cache:
        cached = _cache[cache_key]
        metrics["cache_hit"] = True
        metrics["corrected_events"] = cached.get("corrected_events", 0)
        # Apply cached corrections
        _apply_llm_corrections(events, cached.get("llm_results", []), key)
        return events, metrics

    # Batch events by 30-60s windows
    batch_size = max(1, int(ENRICHMENT_RATE_LIMIT_SECONDS))
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    batch_start = events[0].timestamp

    for event in events:
        current_batch.append({"timestamp": event.timestamp, "chord": event.chord})
        if len(current_batch) >= batch_size or (event.timestamp - batch_start) >= 60.0:
            batches.append(current_batch)
            current_batch = []
            batch_start = event.timestamp
    if current_batch:
        batches.append(current_batch)

    # Call LLM for each batch with rate limiting
    all_llm_results: list[dict[str, Any]] = []
    latencies: list[float] = []

    for i, batch in enumerate(batches):
        if i > 0:
            time.sleep(ENRICHMENT_RATE_LIMIT_SECONDS)

        t0 = time.time()
        result = _call_claude_enrichment(
            api_key=api_key,
            key=key,
            chord_batch=batch,
        )
        latency = time.time() - t0
        latencies.append(latency)

        if result is not None:
            all_llm_results.extend(result)

    # Apply corrections
    corrected = _apply_llm_corrections(events, all_llm_results, key)
    metrics["corrected_events"] = corrected

    # Compute latency percentiles
    if latencies:
        sorted_lat = sorted(latencies)
        p50_idx = len(sorted_lat) // 2
        metrics["llm_latency_p50"] = sorted_lat[p50_idx]
        p95_idx = int(len(sorted_lat) * 0.95)
        metrics["llm_latency_p95"] = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]

    # Cache results
    _cache[cache_key] = {
        "llm_results": all_llm_results,
        "corrected_events": corrected,
    }

    return events, metrics


def enrich_lesson_chord_timeline(
    events: list[ChordEvent],
    key: str,
    *,
    api_key: str = "",
) -> list[ChordEvent]:
    """Convenience wrapper: assign Roman numerals + run LLM enrichment.

    Returns enriched events.
    """
    enrich_chord_timeline(events, key, api_key=api_key)
    return events
