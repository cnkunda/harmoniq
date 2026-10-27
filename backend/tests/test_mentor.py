"""Tests for Commit 179: virtual mentor trajectory endpoint."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import mentor
from app.main import app

client = TestClient(app)


def _payload(mode: str = "plan") -> dict:
    return {
        "mode": mode,
        "generated_at": "2026-10-26T00:00:00+00:00",
        "history": {
            "days": 45,
            "session_count": 6,
            "jam_count": 1,
            "plan_count": 1,
            "correction_count": 2,
            "confidence": "medium",
        },
        "accuracy_points": [{"date": "2026-09-10T00:00:00Z", "accuracy": 0.55}],
        "skill_deltas": [
            {"id": "timing", "label": "Timing", "prior": 0.4, "recent": 0.55, "delta": 0.15}
        ],
        "weak_nodes": [{"id": "bend_accuracy", "label": "Bend accuracy", "score": 0.3}],
        "goals": {
            "experience_level": "intermediate",
            "style_focus": "play cleaner bends",
            "style_label": "blues",
            "technique_affinity": ["bending"],
            "song_candidates": ["Autumn Leaves"],
        },
        "dna": {
            "timing_feel": "behind",
            "top_pitch_classes": ["A", "C"],
            "top_positions": ["frets 0–1"],
            "technique_frequency": {"bending": 3},
        },
        "corrections": {
            "total": 2,
            "by_type": {"wrong_chord": 2},
            "most_corrected_chords": [{"chord": "G7", "count": 2}],
        },
        "plan": {
            "slot_count": 4,
            "slot_types": ["warmup", "technique", "song_section", "free_jam"],
            "target_skills": ["timing"],
            "remediation_count": 1,
            "skip_count": 0,
            "avg_slot_accuracy": 0.6,
        },
        "library_songs": [
            {
                "job_id": "job-1",
                "title": "Blue in Green",
                "artist": "Miles Davis",
                "style_label": "jazz",
                "tempo": 60.0,
                "techniques": ["bending"],
            }
        ],
        "taste_song_candidates": ["Autumn Leaves"],
    }


def _note_json() -> str:
    return json.dumps(
        {
            "headline": "A steadier month",
            "trajectory_summary": "Timing improved while bends stayed uneven.",
            "plateau_diagnosis": "Bend accuracy is flat across the last month.",
            "next_month": [
                {
                    "title": "Target timing",
                    "why": "Your recent sessions moved in the right direction.",
                    "skill_focus": "timing",
                    "mode": "plan",
                },
                {
                    "title": "Invented focus",
                    "why": "This should be dropped.",
                    "skill_focus": "quantum picking",
                    "mode": "plan",
                },
            ],
            "next_songs": [
                {
                    "title": "Blue in Green",
                    "artist": "Miles Davis",
                    "reason": "Slow changes give you room to hear your bends.",
                    "source": "library",
                },
                {
                    "title": "Autumn Leaves",
                    "artist": None,
                    "reason": "A familiar standard to test your new timing.",
                    "source": "taste",
                },
                {
                    "title": "Imaginary Song",
                    "artist": "Nobody",
                    "reason": "This should be dropped.",
                    "source": "taste",
                },
            ],
            "plan_guidance": "The plan warms up your hands before the section work.",
        }
    )


def test_mentor_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HARMONIQ_SKIP_MENTOR", raising=False)
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    res = client.post("/mentor/trajectory", json=_payload())
    assert res.status_code == 503
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_mentor_skip_env(monkeypatch):
    monkeypatch.setenv("HARMONIQ_SKIP_MENTOR", "1")
    res = client.post("/mentor/trajectory", json=_payload())
    assert res.status_code == 503
    assert "HARMONIQ_SKIP_MENTOR" in res.json()["detail"]


def test_mentor_returns_validated_note(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    monkeypatch.delenv("HARMONIQ_SKIP_MENTOR", raising=False)

    captured: list[str] = []

    def fake_call(*, api_key: str, user_prompt: str, **kwargs: object) -> str:
        assert api_key == "test-key"
        captured.append(user_prompt)
        return _note_json()

    monkeypatch.setattr(mentor.coach, "_call_claude_streaming", fake_call)
    res = client.post("/mentor/trajectory", json=_payload(mode="single"))

    assert res.status_code == 200, res.text
    note = res.json()["note"]
    assert note["headline"] == "A steadier month"
    assert note["confidence"] == "medium"
    assert len(note["next_month"]) == 1
    assert note["next_month"][0]["skill_focus"] == "timing"
    assert [song["title"] for song in note["next_songs"]] == ["Blue in Green", "Autumn Leaves"]
    assert note["next_songs"][0]["source"] == "library"
    assert note["next_songs"][1]["source"] == "taste"

    prompt = captured[-1]
    assert "<mode>single</mode>" in prompt
    assert "play cleaner bends" in prompt
    assert "Blue in Green" in prompt
    assert "Imaginary Song" not in prompt


def test_mentor_invalid_json_returns_502(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("HARMONIQ_ENABLE_COACH_IN_TESTS", "1")
    monkeypatch.delenv("HARMONIQ_SKIP_MENTOR", raising=False)
    monkeypatch.setattr(mentor.coach, "_call_claude_streaming", lambda **kwargs: "not json")

    res = client.post("/mentor/trajectory", json=_payload())
    assert res.status_code == 502
    assert "could not produce a note" in res.json()["detail"]
