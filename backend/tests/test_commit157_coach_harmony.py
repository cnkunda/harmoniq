"""Commit 157: section-scoped chord-tone coach context — summary, prompt, hydration e2e."""

from __future__ import annotations

from app import coach
from app.coach import (
    SectionHarmonySummary,
    build_coach_user_prompt,
    hydrate_coach_copy_into_sections,
    section_harmony_summary,
)
from app.schemas import (
    ChordToneAnalysis,
    HarmonizedSoloNote,
    HarmonizedSoloNotes,
    LessonSectionStub,
)


def _analysis(tone_type: str) -> ChordToneAnalysis:
    return ChordToneAnalysis(
        scale_degree=1,
        scale_degree_name="R",
        chord_tone_type=tone_type,
        semitone_distance=0,
    )


def _note(start: float, tone_type: str | None) -> HarmonizedSoloNote:
    return HarmonizedSoloNote(
        start_time=start,
        duration=0.25,
        pitch=64,
        velocity=90,
        chord="C:maj" if tone_type else None,
        chord_analysis=_analysis(tone_type) if tone_type else None,
    )


def _harmonized(notes: list[HarmonizedSoloNote]) -> HarmonizedSoloNotes:
    return HarmonizedSoloNotes(notes=notes, note_count=len(notes))


class TestSectionHarmonySummary:
    def test_recomputes_over_section_subset(self):
        harmonized = _harmonized(
            [
                _note(0.0, "chord_tone"),
                _note(1.0, "tension"),
                _note(2.0, "chord_tone"),
                _note(4.0, "chromatic"),
            ]
        )
        summary = section_harmony_summary(harmonized, 0.0, 3.0)
        assert summary is not None
        assert summary.analyzed_count == 3
        assert summary.chord_tone_pct == 2 / 3
        assert summary.tension_pct == 1 / 3
        assert summary.chromatic_pct == 0.0

    def test_excludes_notes_without_chord_analysis(self):
        harmonized = _harmonized([_note(0.5, None), _note(1.0, "chromatic")])
        summary = section_harmony_summary(harmonized, 0.0, 2.0)
        assert summary is not None
        assert summary.analyzed_count == 1
        assert summary.chromatic_pct == 1.0

    def test_none_harmonized_and_missing_bounds(self):
        harmonized = _harmonized([_note(0.5, "tension")])
        assert section_harmony_summary(None, 0.0, 1.0) is None
        assert section_harmony_summary(harmonized, None, 1.0) is None
        assert section_harmony_summary(harmonized, 0.0, None) is None

    def test_empty_subset_returns_none(self):
        harmonized = _harmonized([_note(5.0, "tension")])
        assert section_harmony_summary(harmonized, 0.0, 1.0) is None
        assert section_harmony_summary(_harmonized([_note(1.0, None)]), 0.0, 2.0) is None

    def test_section_boundary_inclusivity(self):
        harmonized = _harmonized([_note(1.0, "chord_tone"), _note(2.0, "tension")])
        summary = section_harmony_summary(harmonized, 1.0, 2.0)
        assert summary is not None
        assert summary.analyzed_count == 1
        assert summary.chord_tone_pct == 1.0


def _prompt(harmony_summary: SectionHarmonySummary | None = None) -> str:
    return build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        harmony_summary=harmony_summary,
    )


class TestPromptBlock:
    def test_none_matches_baseline_byte_for_byte(self):
        baseline = build_coach_user_prompt(
            section_label="Verse",
            song_title="Song",
            artist="Artist",
            key="G major",
        )
        assert _prompt(None) == baseline
        assert "<harmony_context>" not in baseline

    def test_block_contains_count_percents_and_directive(self):
        summary = SectionHarmonySummary(
            analyzed_count=100,
            chord_tone_pct=0.38,
            tension_pct=0.45,
            chromatic_pct=0.17,
        )
        prompt = _prompt(summary)
        assert "<harmony_context>" in prompt
        assert prompt.index("</section_context>") < prompt.index("<harmony_context>")
        assert "analyzes 100 notes" in prompt
        assert "chord tones 38%" in prompt
        assert "tensions 45%" in prompt
        assert "chromatic 17%" in prompt
        assert "Dominant role: tensions — coach on tension-note targeting and resolution." in prompt
        assert "</harmony_context>" in prompt


class TestDominantRole:
    def _prompt_for(self, chord_tone: float, tension: float, chromatic: float) -> str:
        return _prompt(
            SectionHarmonySummary(
                analyzed_count=10,
                chord_tone_pct=chord_tone,
                tension_pct=tension,
                chromatic_pct=chromatic,
            )
        )

    def test_chord_tone_dominant(self):
        prompt = self._prompt_for(0.7, 0.2, 0.1)
        assert "Dominant role: chord tones — coach on chord-tone targeting and melodic blend." in prompt

    def test_tension_dominant(self):
        prompt = self._prompt_for(0.2, 0.7, 0.1)
        assert "Dominant role: tensions — coach on tension-note targeting and resolution." in prompt

    def test_chromatic_dominant(self):
        prompt = self._prompt_for(0.1, 0.2, 0.7)
        assert (
            "Dominant role: chromatic notes — coach on outside notes as passing tones toward resolution."
            in prompt
        )

    def test_tie_prefers_chord_tone(self):
        prompt = self._prompt_for(0.4, 0.4, 0.2)
        assert "Dominant role: chord tones" in prompt


def _run_hydration(monkeypatch, sections, harmonized_solo=None):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    prompts: list[str] = []

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        prompts.append(user_prompt)
        return (
            '{"coach_note":"Lean into the groove.","coach_explanation":'
            '"Keep the strum relaxed and even.","weak_focus":"none"}'
        )

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    enriched, status, _ = hydrate_coach_copy_into_sections(
        sections,
        song_title="Song",
        artist="Artist",
        key="G major",
        harmonized_solo=harmonized_solo,
    )
    return enriched, status, prompts


def _prompt_for_label(prompts: list[str], label: str) -> str:
    for prompt in prompts:
        if f"section_label: {label}" in prompt:
            return prompt
    raise AssertionError(f"no prompt found for section {label!r}")


SECTIONS = [
    LessonSectionStub(label="Verse", start_time_seconds=0.0, end_time_seconds=2.0),
    LessonSectionStub(label="Chorus", start_time_seconds=2.0, end_time_seconds=4.0),
    LessonSectionStub(label="Bridge", start_time_seconds=10.0, end_time_seconds=12.0),
]


class TestHydrationEndToEnd:
    def test_section_stats_scoped_to_each_window(self, monkeypatch):
        harmonized = _harmonized(
            [
                _note(0.5, "chord_tone"),
                _note(1.0, "chord_tone"),
                _note(1.5, "tension"),
                _note(2.5, "chromatic"),
                _note(3.5, "chromatic"),
            ]
        )
        _, status, prompts = _run_hydration(monkeypatch, SECTIONS, harmonized_solo=harmonized)
        assert status == "complete"
        assert len(prompts) == 3

        verse = _prompt_for_label(prompts, "Verse")
        assert "analyzes 3 notes" in verse
        assert "chord tones 67%" in verse
        assert "tensions 33%" in verse
        assert "chromatic 0%" in verse
        assert "Dominant role: chord tones" in verse

        chorus = _prompt_for_label(prompts, "Chorus")
        assert "analyzes 2 notes" in chorus
        assert "chord tones 0%" in chorus
        assert "chromatic 100%" in chorus
        assert "Dominant role: chromatic notes" in chorus

    def test_section_without_notes_in_range_gets_no_block(self, monkeypatch):
        harmonized = _harmonized([_note(0.5, "chord_tone")])
        _, _, prompts = _run_hydration(monkeypatch, SECTIONS, harmonized_solo=harmonized)
        bridge = _prompt_for_label(prompts, "Bridge")
        assert "<harmony_context>" not in bridge

    def test_all_unanalyzed_notes_produce_no_block(self, monkeypatch):
        harmonized = _harmonized([_note(0.5, None), _note(1.0, None)])
        _, _, prompts = _run_hydration(monkeypatch, SECTIONS, harmonized_solo=harmonized)
        verse = _prompt_for_label(prompts, "Verse")
        assert "<harmony_context>" not in verse
        assert "0%" not in verse

    def test_no_harmonized_solo_prompts_unchanged(self, monkeypatch):
        _, _, baseline_prompts = _run_hydration(monkeypatch, SECTIONS)
        _, _, explicit_none_prompts = _run_hydration(monkeypatch, SECTIONS, harmonized_solo=None)
        for label in ("Verse", "Chorus", "Bridge"):
            assert _prompt_for_label(baseline_prompts, label) == _prompt_for_label(
                explicit_none_prompts, label
            )
            assert "<harmony_context>" not in _prompt_for_label(baseline_prompts, label)
