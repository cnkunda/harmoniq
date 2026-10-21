"""Deterministic jam grading (Commit 160).

The grade is always computed here — never by the LLM. Components are scored
0-100 and normalized over the signals actually present, so legacy payloads
without intonation are not capped at 70.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import JamPhraseMetrics

COMPONENT_MAXIMA: dict[str, float] = {
    "intonation": 30.0,
    "timing": 25.0,
    "pitch_variety": 20.0,
    "melodic_range": 15.0,
    "density": 10.0,
}

GRADE_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("A", 90.0),
    ("B", 80.0),
    ("C", 70.0),
    ("D", 60.0),
)


@dataclass(frozen=True)
class PhraseScore:
    """One phrase's normalized score plus the raw component points that were present."""

    score: float
    components: dict[str, float]


@dataclass(frozen=True)
class JamGrade:
    """Deterministic grade output for a jam session."""

    grade: str
    grade_score: float
    grade_breakdown: dict[str, float]
    weakest_phrase_index: int | None
    phrase_scores: list[PhraseScore]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _intonation_component(phrase: JamPhraseMetrics) -> float | None:
    if phrase.intonation_cents is None:
        return None
    return _clamp(1.0 - abs(phrase.intonation_cents) / 50.0, 0.0, 1.0) * COMPONENT_MAXIMA["intonation"]


def _timing_component(phrase: JamPhraseMetrics) -> float | None:
    if phrase.beat_offset_std is not None:
        ratio = _clamp(1.0 - phrase.beat_offset_std / 80.0, 0.0, 1.0)
    elif phrase.beat_offset_mean is not None:
        ratio = _clamp(1.0 - abs(phrase.beat_offset_mean) / 120.0, 0.0, 1.0)
    else:
        return None
    return ratio * COMPONENT_MAXIMA["timing"]


def _pitch_variety_component(phrase: JamPhraseMetrics) -> float:
    ratio = min(phrase.unique_pitch_classes / 7.0, 1.0)
    return ratio * COMPONENT_MAXIMA["pitch_variety"]


def _melodic_range_component(phrase: JamPhraseMetrics) -> float:
    ratio = min(phrase.midi_span / 12.0, 1.0)
    return ratio * COMPONENT_MAXIMA["melodic_range"]


def _density_component(phrase: JamPhraseMetrics) -> float:
    ratio = _clamp(1.0 - abs(phrase.notes_per_second - 2.5) / 2.5, 0.0, 1.0)
    return ratio * COMPONENT_MAXIMA["density"]


def score_phrase(phrase: JamPhraseMetrics) -> PhraseScore:
    """Score one phrase 0-100, normalizing over the components present."""
    components: dict[str, float] = {
        "pitch_variety": _pitch_variety_component(phrase),
        "melodic_range": _melodic_range_component(phrase),
        "density": _density_component(phrase),
    }

    intonation = _intonation_component(phrase)
    if intonation is not None:
        components["intonation"] = intonation

    timing = _timing_component(phrase)
    if timing is not None:
        components["timing"] = timing

    denominator = sum(COMPONENT_MAXIMA[name] for name in components)
    score = (sum(components.values()) / denominator * 100.0) if denominator > 0 else 0.0
    return PhraseScore(score=score, components=components)


def grade_from_score(score: float) -> str:
    """Map a 0-100 score to an A-F letter grade."""
    for letter, threshold in GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def _weighted_average(values: list[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in values) / total_weight


def compute_jam_grade(phrases: list[JamPhraseMetrics]) -> JamGrade:
    """Compute the deterministic grade, breakdown, and weakest phrase."""
    if not phrases:
        return JamGrade(
            grade="F",
            grade_score=0.0,
            grade_breakdown={},
            weakest_phrase_index=None,
            phrase_scores=[],
        )

    phrase_scores = [score_phrase(phrase) for phrase in phrases]
    durations = [max(0.0, phrase.duration_ms) for phrase in phrases]
    total_duration = sum(durations)
    weights = durations if total_duration > 0 else [1.0 for _ in phrases]

    overall = _weighted_average(
        [(phrase_scores[i].score, weights[i]) for i in range(len(phrases))]
    )
    overall = round(overall, 2)

    weakest_index = 0
    for index in range(1, len(phrase_scores)):
        if phrase_scores[index].score < phrase_scores[weakest_index].score:
            weakest_index = index

    breakdown: dict[str, float] = {}
    for component in COMPONENT_MAXIMA:
        values = [
            (phrase_scores[i].components[component] / COMPONENT_MAXIMA[component] * 100.0, weights[i])
            for i in range(len(phrases))
            if component in phrase_scores[i].components
        ]
        if values:
            breakdown[component] = round(_weighted_average(values), 1)

    return JamGrade(
        grade=grade_from_score(overall),
        grade_score=overall,
        grade_breakdown=breakdown,
        weakest_phrase_index=weakest_index,
        phrase_scores=phrase_scores,
    )


def fallback_phrase_suggestion(phrase: JamPhraseMetrics, phrase_index: int) -> str:
    """Deterministic suggestion so the modal always has content for a phrase."""
    del phrase_index  # Keep the signature stable for callers; labels carry the index.
    if phrase.note_count == 0 and phrase.notes_per_second <= 0:
        return "Play this phrase once more so there is enough material to coach."

    if phrase.intonation_cents is not None and abs(phrase.intonation_cents) > 20:
        return (
            f"Intonation is drifting about {abs(phrase.intonation_cents):.0f} cents — "
            "slow the phrase down and aim each note into the center of the pitch."
        )

    if abs(phrase.beat_offset_mean) > 80 or phrase.beat_offset_std > 80:
        return (
            "The attacks are not landing together yet — loop this phrase at 75% speed "
            "and let every note settle on the pulse before moving on."
        )

    if phrase.notes_per_second > 3.5:
        return "You are filling every gap — leave the last note of each idea to breathe before the next entrance."

    if phrase.note_count >= 3 and (phrase.unique_pitch_classes <= 3 or phrase.midi_span <= 4):
        return "The line stays in a small melodic pocket — reach up or down once to stretch the phrase's shape."

    if phrase.notes_per_second < 1.0:
        return "Add one or two passing tones so the phrase connects to the groove instead of floating above it."

    return "Loop this phrase slowly and keep the same shape while relaxing your attack; let the timing settle."
