"""POST /jam-score (PRIORITIES §36)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_jam_score_short_duration_coach() -> None:
    res = client.post(
        "/jam-score",
        json={"duration_seconds": 5, "pitch_class_weight_map": {}, "inferred_scale_label": None},
    )
    assert res.status_code == 200
    body = res.json()
    assert "ten seconds" in body["coach_summary"].lower()
    assert body["pitch_class_weight_map"] == {}
    assert body["scale_position_map"] == {}
    assert "signal_short_window" in body["reliability_tags"]
    assert body["reliability"]["confidence"] == "low"


def test_jam_score_with_histogram_sets_focus_fields() -> None:
    res = client.post(
        "/jam-score",
        json={
            "duration_seconds": 12,
            "pitch_class_weight_map": {"pc_A": 0.6, "pc_E": 0.4},
            "position_weight_map": {"pos1": 0.75, "pos2": 0.25},
            "inferred_scale_label": "A minor pent.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["coach_summary"]
    assert "pc_A" in body["pitch_class_weight_map"]
    assert body["focus_pitch_class_key"] == "pc_A"
    assert body["focus_pitch_class_weight"] == 0.6
    assert body["position_weight_map"]["pos1"] == 0.75
    assert body["reliability"]["score_contract_version"] == "v2"


def test_jam_score_rejects_invalid_pitch_map_key() -> None:
    res = client.post(
        "/jam-score",
        json={"duration_seconds": 12, "pitch_class_weight_map": {"focus_pitch_class": 0.6}},
    )
    assert res.status_code == 422
