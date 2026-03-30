from __future__ import annotations

from app import coach
from app.schemas import LessonSectionStub


def test_generate_coach_fields_uses_fallback_when_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    note, explanation = coach.generate_coach_fields_for_section(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
    )
    assert note == coach.FALLBACK_COACH_NOTE
    assert explanation == coach.FALLBACK_COACH_EXPLANATION


def test_generate_coach_fields_uses_api_output_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")

    def fake_call(*, api_key: str, user_prompt: str) -> str:
        assert api_key == "test-key"
        assert "section_label: Chorus" in user_prompt
        return '{"coach_note":"Try landing the bend slightly later.","coach_explanation":"Holding the bend longer builds tension. The delayed release gives the line a stronger resolution."}'

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    note, explanation = coach.generate_coach_fields_for_section(
        section_label="Chorus",
        song_title="Song",
        artist="Artist",
        key="E minor",
    )
    assert note == "Try landing the bend slightly later."
    assert explanation.startswith("Holding the bend longer")
    assert note != coach.FALLBACK_COACH_NOTE


def test_merge_coach_copy_into_sections_adds_fields(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = coach.merge_coach_copy_into_sections(
        [LessonSectionStub(label="Intro", confidence=0.5)],
        song_title="Song",
        artist="Artist",
        key="A major",
    )
    assert len(out) == 1
    sec = out[0].model_dump()
    assert sec["label"] == "Intro"
    assert sec["coach_note"]
    assert sec["coach_explanation"]
