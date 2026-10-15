"""Commit 156: instrument-confusion coach hedging — prompt tiers, backstop, hydration e2e."""

from __future__ import annotations

import math

from app import coach
from app.coach import (
    HEDGE_CAVEAT,
    apply_hedge_backstop,
    build_coach_user_prompt,
    hydrate_coach_copy_into_sections,
)
from app.schemas import LessonSectionStub


def _prompt(confusion):
    return build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        instrument_confusion=confusion,
    )


class TestPromptTiers:
    def test_below_trigger_matches_baseline_byte_for_byte(self):
        baseline = _prompt(None)
        assert _prompt(0.0) == baseline
        assert _prompt(0.29) == baseline
        assert "Transcription caution" not in baseline

    def test_soft_tier_boundaries(self):
        soft_030 = _prompt(0.30)
        assert "Transcription caution" in soft_030
        assert "by ear" in soft_030
        assert "approximate guide" not in soft_030
        assert "by ear" in _prompt(0.45)

    def test_strong_tier(self):
        strong = _prompt(0.8)
        assert "approximate guide" in strong
        assert "bends" in strong

    def test_out_of_range_and_nan(self):
        assert "Transcription caution" not in _prompt(-0.1)
        assert "approximate guide" in _prompt(1.5)
        assert "Transcription caution" not in _prompt(math.nan)
        assert _prompt(math.nan) == _prompt(None)


class TestBackstop:
    def test_appends_caveat_when_missing(self):
        note, explanation = apply_hedge_backstop(
            "Land the bend later.", "Hold it longer for tension.", 0.8
        )
        assert note == "Land the bend later."
        assert explanation.endswith(HEDGE_CAVEAT)

    def test_no_duplicate_when_already_hedged(self):
        note, explanation = apply_hedge_backstop(
            "Check it by ear.", "The transcription may be unreliable here.", 0.8
        )
        assert note == "Check it by ear."
        assert explanation == "The transcription may be unreliable here."

    def test_low_and_missing_confusion_untouched(self):
        assert apply_hedge_backstop("N", "E.", 0.1) == ("N", "E.")
        assert apply_hedge_backstop("N", "E.", None) == ("N", "E.")


class TestFallbackPathsHedged:
    """Hedging must survive the paths where no model ran (Commit 156 review fix)."""

    _call = dict(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
    )

    def test_missing_api_key_still_hedges(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = coach.generate_coach_fields_for_section_with_status(
            **self._call, instrument_confusion=0.8
        )
        assert result.fallback_reason == "missing_api_key"
        assert HEDGE_CAVEAT in result.explanation

    def test_parse_error_still_hedges(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(coach, "_call_claude_text", lambda **kw: "not json at all")
        result = coach.generate_coach_fields_for_section_with_status(
            **self._call, instrument_confusion=0.8
        )
        assert result.fallback_reason == "parse_error"
        assert result.explanation.endswith(HEDGE_CAVEAT)

    def test_fallback_without_confusion_untouched(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = coach.generate_coach_fields_for_section_with_status(**self._call)
        assert result.fallback_reason == "missing_api_key"
        assert HEDGE_CAVEAT not in result.explanation


def _run_hydration(monkeypatch, sections):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    prompts: list[str] = []

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        prompts.append(user_prompt)
        return '{"coach_note":"Lean into the groove.","coach_explanation":"Keep the strum relaxed and even.","weak_focus":"none"}'

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    enriched, status, _ = hydrate_coach_copy_into_sections(
        sections,
        song_title="Song",
        artist="Artist",
        key="G major",
    )
    return enriched, status, prompts


class TestHydrationEndToEnd:
    def test_stored_section_confusion_reaches_prompt(self, monkeypatch):
        """The test that would have caught the original break: a stored
        section with confusion 0.5 must produce a hedged prompt at the fake
        LLM, called exactly once."""
        sections = [LessonSectionStub(label="Verse", instrument_confusion=0.5)]
        enriched, status, prompts = _run_hydration(monkeypatch, sections)
        assert len(prompts) == 1
        assert "by ear" in prompts[0]
        assert status == "complete"
        assert enriched[0].coach_note == "Lean into the groove."

    def test_section_without_confusion_unchanged(self, monkeypatch):
        sections = [LessonSectionStub(label="Verse")]
        _, _, prompts = _run_hydration(monkeypatch, sections)
        assert len(prompts) == 1
        assert "Transcription caution" not in prompts[0]
