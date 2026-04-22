from __future__ import annotations

from app import coach
from app.schemas import CoachFocusArea, LessonSectionStub, PlayerProfile


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


def test_rotate_focus_area_cycles_through_all_areas():
    """Test that rotate_focus_area cycles through all focus areas (commit 90)."""
    # Session 0 should return first focus area
    focus_0 = coach.rotate_focus_area(0)
    assert focus_0 in coach.FOCUS_AREA_ROTATION

    # Session 7 should cycle back to first focus area (7 areas total)
    focus_7 = coach.rotate_focus_area(7)
    assert focus_7 == coach.rotate_focus_area(0)

    # Session 14 should also cycle back (14 % 7 = 0)
    focus_14 = coach.rotate_focus_area(14)
    assert focus_14 == coach.rotate_focus_area(0)

    # Different sessions should return different focus areas (with wrap)
    focus_1 = coach.rotate_focus_area(1)
    focus_2 = coach.rotate_focus_area(2)
    assert focus_1 != focus_2

    # Negative session count should be treated as 0
    focus_neg = coach.rotate_focus_area(-1)
    assert focus_neg == coach.rotate_focus_area(0)


def test_focus_area_directive_generates_correct_directives():
    """Test that _focus_area_directive generates correct directives for each focus area (commit 90)."""
    # Test each focus area generates a non-empty directive
    for area in coach.FOCUS_AREA_ROTATION:
        directive = coach._focus_area_directive(area)
        assert directive
        assert f"Focus area this session: {area.capitalize()}" in directive
        assert "Prioritize observations" in directive

    # Test None returns empty string
    directive_none = coach._focus_area_directive(None)
    assert directive_none == ""

    # Test timing directive specifically
    timing_directive = coach._focus_area_directive("timing")
    assert "Timing" in timing_directive
    assert "rhythm" in timing_directive.lower() or "time feel" in timing_directive.lower()

    # Test vibrato directive specifically
    vibrato_directive = coach._focus_area_directive("vibrato")
    assert "Vibrato" in vibrato_directive
    assert "pitch stability" in vibrato_directive.lower()


def test_build_coach_prompt_includes_focus_area_directive():
    """Test that build_coach_user_prompt includes focus area directive when provided (commit 90)."""
    # With focus area
    prompt_with_focus = coach.build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        focus_area="timing",
    )
    assert "Focus area this session: Timing" in prompt_with_focus
    assert "Prioritize observations about rhythm" in prompt_with_focus

    # Without focus area (None)
    prompt_without_focus = coach.build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        focus_area=None,
    )
    assert "Focus area this session:" not in prompt_without_focus

    # Different focus areas produce different prompts
    prompt_timing = coach.build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        focus_area="timing",
    )
    prompt_vibrato = coach.build_coach_user_prompt(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        focus_area="vibrato",
    )
    assert prompt_timing != prompt_vibrato
    assert "Timing" in prompt_timing
    assert "Vibrato" in prompt_vibrato


def test_generate_coach_fields_with_focus_area(monkeypatch):
    """Test that generate_coach_fields_for_section passes focus_area through (commit 90)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    prompts: list[str] = []

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        prompts.append(user_prompt)
        return '{"coach_note":"Focus on timing.","coach_explanation":"Timing explanation here.","weak_focus":"none"}'

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    note, explanation = coach.generate_coach_fields_for_section(
        section_label="Verse",
        song_title="Song",
        artist="Artist",
        key="G major",
        focus_area="dynamics",
    )
    assert "Focus area this session: Dynamics" in prompts[0]
    assert "volume control" in prompts[0].lower()
    assert note == "Focus on timing."
    assert explanation == "Timing explanation here."
