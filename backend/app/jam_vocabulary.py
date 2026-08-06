"""Vocabulary and pattern detection for jam sessions (Commit 111).

Analyzes phrase-level metrics to identify recurring musical patterns,
motifs, sequences, and vocabulary diversity. Runs deterministically
without LLM — the Claude call consumes these results.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from typing import Any

import numpy as np

from app.schemas import JamPhraseMetrics, JamVocabularyPattern

logger = logging.getLogger("harmoniq.jam_vocabulary")

# Pattern detection thresholds
MIN_OCCURRENCES = 2
MAX_PITCH_CLASSES_IN_PATTERN = 6
SIMILARITY_THRESHOLD = 0.75  # Cosine similarity for pattern matching
DIVERSITY_BIN_COUNT = 12  # Pitch class bins


def _pitch_class_to_index(pc: str) -> int:
    """Convert pitch class string to 0-11 index."""
    mapping = {
        "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
        "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
        "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
    }
    return mapping.get(pc.strip(), -1)


def _normalize_pitch_class(pc: str) -> str:
    """Normalize pitch class to sharps (C#, D#, F#, G#, A#)."""
    flat_to_sharp = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    return flat_to_sharp.get(pc.strip(), pc.strip())


def _pattern_fingerprint(pitch_classes: list[str]) -> str:
    """Create a canonical fingerprint for a pitch class pattern.
    Uses interval sequence to be root-invariant."""
    if len(pitch_classes) < 2:
        return "|".join(sorted(pitch_classes))

    indices = sorted(_pitch_class_to_index(pc) for pc in pitch_classes if _pitch_class_to_index(pc) >= 0)
    if len(indices) < 2:
        return "|".join(sorted(pitch_classes))

    # Compute interval sequence (root-invariant)
    intervals = []
    for i in range(1, len(indices)):
        intervals.append((indices[i] - indices[i - 1]) % 12)
    # Add closing interval
    intervals.append((indices[0] - indices[-1] + 12) % 12)

    return "i".join(str(iv) for iv in intervals)


def _compute_contour(phrases: list[JamPhraseMetrics]) -> str:
    """Compute dominant melodic contour across all phrases."""
    if not phrases:
        return "mixed"

    contour_counts = Counter(p.contour for p in phrases)
    if not contour_counts:
        return "mixed"

    # Filter out 'mixed' and find dominant
    specific = {k: v for k, v in contour_counts.items() if k != "mixed"}
    if not specific:
        return "mixed"

    dominant = max(specific, key=specific.get)
    dominant_count = specific[dominant]
    total_specific = sum(specific.values())

    # Need >50% dominance to be confident
    if dominant_count / total_specific > 0.5:
        return dominant
    return "mixed"


def _compute_vocabulary_diversity(phrases: list[JamPhraseMetrics]) -> float:
    """Compute vocabulary diversity score (0=repetitive, 1=varied).

    Uses Shannon entropy of pitch class distribution across phrases,
    normalized by maximum possible entropy.
    """
    if not phrases:
        return 0.0

    # Collect all pitch classes across phrases
    all_pcs: list[str] = []
    for p in phrases:
        if p.home_pitch_class:
            all_pcs.append(_normalize_pitch_class(p.home_pitch_class))

    if not all_pcs:
        return 0.0

    counts = Counter(all_pcs)
    total = sum(counts.values())
    if total == 0:
        return 0.0

    # Shannon entropy
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * np.log2(p)

    # Normalize by max entropy (log2 of unique pitch classes)
    max_entropy = np.log2(max(len(counts), 1))
    if max_entropy == 0:
        return 0.0

    return float(min(entropy / max_entropy, 1.0))


def detect_patterns(phrases: list[JamPhraseMetrics]) -> list[JamVocabularyPattern]:
    """Detect recurring vocabulary patterns across phrases.

    Analyzes:
    - Repeated pitch class sequences (motifs)
    - Scale runs (consecutive pitch classes)
    - Arpeggio patterns (chord tone sequences)
    - Repeated note figures
    """
    if len(phrases) < MIN_OCCURRENCES:
        return []

    patterns: list[JamVocabularyPattern] = []
    pattern_counter: dict[str, dict[str, Any]] = {}

    # Extract pitch class sequences from each phrase
    for phrase_idx, phrase in enumerate(phrases):
        if not phrase.home_pitch_class:
            continue

        # Build a mini-sequence from the phrase's pitch class and contour
        pcs = [_normalize_pitch_class(phrase.home_pitch_class)]

        # Add neighboring pitch classes based on contour
        pc_idx = _pitch_class_to_index(phrase.home_pitch_class)
        if pc_idx < 0:
            continue

        if phrase.contour == "rising":
            pcs.append(_normalize_pitch_class(_index_to_pc((pc_idx + 2) % 12)))
            pcs.append(_normalize_pitch_class(_index_to_pc((pc_idx + 4) % 12)))
        elif phrase.contour == "falling":
            pcs.append(_normalize_pitch_class(_index_to_pc((pc_idx - 2) % 12)))
            pcs.append(_normalize_pitch_class(_index_to_pc((pc_idx - 4) % 12)))
        elif phrase.contour == "arch":
            pcs.append(_normalize_pitch_class(_index_to_pc((pc_idx + 3) % 12)))
            pcs.append(_normalize_pitch_class(_index_to_pc((pc_idx + 7) % 12)))
        elif phrase.contour == "static":
            # Repeated note figure
            pcs.append(_normalize_pitch_class(phrase.home_pitch_class))
            pcs.append(_normalize_pitch_class(phrase.home_pitch_class))

        # Deduplicate while preserving order
        seen = set()
        unique_pcs = []
        for pc in pcs:
            if pc not in seen:
                seen.add(pc)
                unique_pcs.append(pc)

        if len(unique_pcs) < 2:
            continue

        # Create fingerprint
        fp = _pattern_fingerprint(unique_pcs)

        if fp not in pattern_counter:
            pattern_counter[fp] = {
                "pitch_classes": unique_pcs,
                "count": 0,
                "contours": [],
                "densities": [],
            }
        pattern_counter[fp]["count"] += 1
        pattern_counter[fp]["contours"].append(phrase.contour)
        pattern_counter[fp]["densities"].append(phrase.notes_per_second)

    # Convert to JamVocabularyPattern objects
    pattern_id = 0
    for fp, data in pattern_counter.items():
        if data["count"] < MIN_OCCURRENCES:
            continue

        # Classify pattern type
        pattern_type = _classify_pattern(data["pitch_classes"], data["contours"])

        # Confidence based on occurrence count and consistency
        consistency = 1.0 - (len(set(data["contours"])) / max(len(data["contours"]), 1))
        confidence = min(0.5 + (data["count"] * 0.1) + (consistency * 0.3), 1.0)

        # Description
        desc = _describe_pattern(pattern_type, data["pitch_classes"], data["count"])

        patterns.append(JamVocabularyPattern(
            pattern_id=f"vocab_{pattern_id:03d}",
            pattern_type=pattern_type,
            pitch_classes=data["pitch_classes"],
            occurrence_count=data["count"],
            confidence=round(confidence, 3),
            description=desc,
        ))
        pattern_id += 1

    # Sort by occurrence count (most frequent first)
    patterns.sort(key=lambda p: p.occurrence_count, reverse=True)

    return patterns[:10]  # Cap at 10 patterns


def _index_to_pc(idx: int) -> str:
    """Convert 0-11 index to pitch class name."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return names[idx % 12]


def _classify_pattern(pitch_classes: list[str], contours: list[str]) -> str:
    """Classify a detected pattern into a vocabulary category."""
    if len(pitch_classes) <= 2:
        # Check for repeated note
        if len(set(pitch_classes)) == 1:
            return "repeated_note"
        return "motif"

    # Check for scale run (consecutive pitch classes)
    indices = sorted(_pitch_class_to_index(pc) for pc in pitch_classes if _pitch_class_to_index(pc) >= 0)
    if len(indices) >= 3:
        intervals = [indices[i + 1] - indices[i] for i in range(len(indices) - 1)]
        if all(1 <= iv <= 2 for iv in intervals):
            return "scale_run"

    # Check for arpeggio (intervals of 3-4 semitones)
    if len(indices) >= 3:
        intervals = [(indices[i + 1] - indices[i]) % 12 for i in range(len(indices) - 1)]
        if all(iv in (3, 4, 5, 7) for iv in intervals):
            return "arpeggio"

    # Check for bend figure (single pitch class with rising contour)
    if contours and max(set(contours), key=contours.count) == "rising":
        return "bend_figure"

    # Check for sequence (repeated pattern at different pitch levels)
    if len(set(pitch_classes)) >= 3 and len(pitch_classes) >= 4:
        return "sequence"

    return "motif"


def _describe_pattern(pattern_type: str, pitch_classes: list[str], count: int) -> str:
    """Generate human-readable description of a detected pattern."""
    pc_str = ", ".join(pitch_classes[:4])
    if len(pitch_classes) > 4:
        pc_str += f" (+{len(pitch_classes) - 4} more)"

    descriptions = {
        "motif": f"Short melodic motif using {pc_str} — appeared {count} times",
        "sequence": f"Sequential pattern across {pc_str} — repeated {count} times at different positions",
        "arpeggio": f"Arpeggio figure through {pc_str} — played {count} times",
        "scale_run": f"Scale run spanning {pc_str} — executed {count} times",
        "bend_figure": f"Bend/vibrato figure on {pc_str} — used {count} times",
        "repeated_note": f"Repeated note emphasis on {pc_str[0:2]} — featured {count} times",
    }

    return descriptions.get(pattern_type, f"Pattern using {pc_str} — {count} occurrences")


def extract_bundle_metrics(
    phrases: list[JamPhraseMetrics],
    pitch_class_weight_map: dict[str, float],
    duration_seconds: int,
) -> dict[str, Any]:
    """Extract deterministic metrics for the JamSummaryBundle.

    This runs without LLM — pure computation from phrase data.
    """
    if not phrases:
        return {
            "phrase_count": 0,
            "total_notes": 0,
            "avg_notes_per_second": 0.0,
            "dominant_contour": "mixed",
            "clarity": 0.0,
            "timing_ms": 0.0,
            "intonation_cents": {},
            "vocabulary_diversity": 0.0,
            "pitch_class_distribution": pitch_class_weight_map,
        }

    total_notes = sum(max(int(p.notes_per_second * (p.duration_ms / 1000)), 1) for p in phrases)
    avg_nps = np.mean([p.notes_per_second for p in phrases]) if phrases else 0.0
    dominant_contour = _compute_contour(phrases)

    # Clarity: based on consistency of note density and timing
    nps_values = [p.notes_per_second for p in phrases if p.notes_per_second > 0]
    if nps_values:
        nps_cv = np.std(nps_values) / max(np.mean(nps_values), 0.001)
        clarity = max(0.0, 1.0 - min(nps_cv, 1.0))
    else:
        clarity = 0.0

    # Timing: mean beat offset in milliseconds
    timing_values = [p.beat_offset_mean * (60000 / max(p.beat_offset_mean * 1000, 1)) for p in phrases]
    timing_ms = float(np.mean(timing_values)) if timing_values else 0.0

    # Intonation: placeholder (would need frequency data)
    intonation_cents: dict[str, float] = {}

    # Vocabulary diversity
    diversity = _compute_vocabulary_diversity(phrases)

    return {
        "phrase_count": len(phrases),
        "total_notes": total_notes,
        "avg_notes_per_second": round(float(avg_nps), 2),
        "dominant_contour": dominant_contour,
        "clarity": round(float(clarity), 3),
        "timing_ms": round(timing_ms, 1),
        "intonation_cents": intonation_cents,
        "vocabulary_diversity": round(diversity, 3),
        "pitch_class_distribution": pitch_class_weight_map,
    }
