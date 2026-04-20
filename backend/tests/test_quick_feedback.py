from __future__ import annotations

from app import coach


def test_quick_feedback_uses_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = coach.generate_quick_feedback(["hit", "close", "miss"])
    assert out == coach.FALLBACK_QUICK_FEEDBACK


def test_quick_feedback_empty_pattern_returns_fallback():
    assert coach.generate_quick_feedback([]) == coach.FALLBACK_QUICK_FEEDBACK


def test_quick_feedback_parses_message_json(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        assert "hit" in user_prompt or "close" in user_prompt
        assert kwargs.get("temperature") == 0.3
        return '{"message":"Lean on the clean beats and shorten pick motion."}'

    monkeypatch.setattr(coach, "_call_claude_text", fake_call)
    assert coach.generate_quick_feedback(["hit", "close"]) == "Lean on the clean beats and shorten pick motion."
