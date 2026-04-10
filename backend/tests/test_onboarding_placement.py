from fastapi.testclient import TestClient

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
