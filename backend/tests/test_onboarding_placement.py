from fastapi.testclient import TestClient

from app import coach
from app.main import app


def test_onboarding_placement_returns_paragraph():
    client = TestClient(app)
    res = client.post(
        "/onboarding-placement",
        json={
            "pitch_avg": 0.75,
            "phrasing_avg": 0.4,
            "timing_avg": 0.85,
            "bend_error_cents_avg": 22.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "coach_paragraph" in data
    assert isinstance(data["coach_paragraph"], str)
    assert len(data["coach_paragraph"]) > 40
    assert data["coach_source"] == "template"


def test_generate_onboarding_placement_summary_marks_ai_source(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    monkeypatch.setattr(coach, "_call_claude_text", lambda **_kwargs: "x" * 80)

    result = coach.generate_onboarding_placement_summary(
        pitch_avg=0.7,
        phrasing_avg=0.5,
        timing_avg=0.6,
        bend_error_cents_avg=18.0,
    )

    assert result.source == "ai"
    assert result.text == "x" * 80
