"""POST /jam-score (PRIORITIES §36)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_jam_score_short_duration_coach() -> None:
    res = client.post(
        "/jam-score",
        json={"duration_seconds": 5, "scale_position_map": {}, "inferred_scale_label": None},
    )
    assert res.status_code == 200
    body = res.json()
    assert "ten seconds" in body["coach_summary"].lower()
    assert body["scale_position_map"] == {}


def test_jam_score_with_histogram_merges_focus() -> None:
    res = client.post(
        "/jam-score",
        json={
            "duration_seconds": 12,
            "scale_position_map": {"pc_A": 0.6, "pc_E": 0.4},
            "inferred_scale_label": "A minor pent.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["coach_summary"]
    assert "pc_A" in body["scale_position_map"]
    assert body["scale_position_map"]["focus_pitch_class"] == 0.6
