from __future__ import annotations

from app import coach
from app.schemas import LessonSectionStub, PlayerProfile


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

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        assert api_key == "test-key"
        assert "section_label: Chorus" in user_prompt
        return '{"coach_note":"Try landing the bend slightly later.","coach_explanation":"Holding the bend longer builds tension. The delayed release gives the line a stronger resolution.","weak_focus":"none"}'

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


def test_generate_coach_fields_includes_weak_areas_in_prompt(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    prompts: list[str] = []

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        prompts.append(user_prompt)
        return '{"coach_note":"Custom note.","coach_explanation":"Custom explanation here.","weak_focus":"bending"}'

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    profile = PlayerProfile(weak_areas=["bending"])
    note, explanation = coach.generate_coach_fields_for_section(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        player_profile=profile,
        style_label="uptempo rock / lead energy",
        technique_hints=["muting"],
    )
    assert "bending" in prompts[0]
    assert "<player_context>" in prompts[0]
    assert "Profile-priority requirement:" in prompts[0]
    assert "explicitly reference at least one weak-area concept" in prompts[0]
    assert "weak_focus" in prompts[0]
    assert "uptempo" in prompts[0]
    assert note == "Custom note."
    assert explanation.startswith("Custom explanation")


def test_generate_coach_fields_empty_profile_omits_player_block(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    prompts: list[str] = []

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        prompts.append(user_prompt)
        return '{"coach_note":"N","coach_explanation":"E.","weak_focus":"none"}'

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    coach.generate_coach_fields_for_section(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        player_profile=PlayerProfile(),
    )
    assert "<player_context>" not in prompts[0]
    assert "Profile-priority requirement:" not in prompts[0]


def test_build_coach_prompt_differs_between_profile_and_no_profile():
    with_profile = coach.build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        player_profile=PlayerProfile(weak_areas=["bending"]),
    )
    without_profile = coach.build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        player_profile=None,
    )
    assert with_profile != without_profile
    assert "<player_context>" in with_profile
    assert "bending" in with_profile
    assert "Profile-priority requirement:" in with_profile
    assert "<player_context>" not in without_profile
    assert "Profile-priority requirement:" not in without_profile


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


def test_generate_coach_fields_retries_until_profile_focus_hit(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    calls: list[dict[str, object]] = []
    responses = [
        '{"coach_note":"Play with steadier release.","coach_explanation":"This phrase lands better when the sustain breathes.","weak_focus":"none"}',
        '{"coach_note":"Keep the bend centered before release.","coach_explanation":"The line resolves cleaner when your bend intonation settles first.","weak_focus":"bending"}',
    ]

    def fake_call(*, api_key: str, user_prompt: str, temperature: float = 1.0, **kwargs: object) -> str:
        calls.append({"prompt": user_prompt, "temperature": temperature, "api_key": api_key})
        return responses[len(calls) - 1]

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    note, explanation = coach.generate_coach_fields_for_section(
        section_label="Bridge",
        song_title="Song",
        artist="Artist",
        key="G major",
        player_profile=PlayerProfile(weak_areas=["bending"]),
    )
    assert len(calls) == 2
    assert calls[0]["temperature"] == coach.COACH_PROFILE_TEMPERATURE_INITIAL
    assert calls[1]["temperature"] == coach.COACH_PROFILE_TEMPERATURE_RETRY
    assert "retry_requirement" in str(calls[1]["prompt"])
    assert "bending" in note.lower() or "bending" in explanation.lower() or "bend" in note.lower()


def test_generate_coach_fields_accepts_synonym_for_weak_area(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        return '{"coach_note":"Hold the bend in tune a beat longer.","coach_explanation":"That tiny delay builds tension before release.","weak_focus":"bend"}'

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    note, explanation = coach.generate_coach_fields_for_section(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="E minor",
        player_profile=PlayerProfile(weak_areas=["bending"]),
    )
    assert note
    assert explanation
    assert note != coach.FALLBACK_COACH_NOTE
