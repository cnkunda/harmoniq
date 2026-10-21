"""Tests for Jam Mode Summary Agent (Commit 111)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import JamPhraseMetrics

client = TestClient(app)


# ---------------------------------------------------------------------------
# Vocabulary pattern detection tests
# ---------------------------------------------------------------------------

class TestVocabularyDetection:
    def test_no_patterns_with_few_phrases(self):
        from app.jam_vocabulary import detect_patterns

        phrases = [
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=3, midi_span=5,
                contour="rising", home_pitch_class="A",
            ),
        ]
        patterns = detect_patterns(phrases)
        assert patterns == []

    def test_detects_repeated_motif(self):
        from app.jam_vocabulary import detect_patterns

        phrases = [
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=3, midi_span=5,
                contour="rising", home_pitch_class="A",
            ),
            JamPhraseMetrics(
                duration_ms=1200, notes_per_second=2.5,
                unique_pitch_classes=3, midi_span=5,
                contour="rising", home_pitch_class="A",
            ),
            JamPhraseMetrics(
                duration_ms=900, notes_per_second=1.8,
                unique_pitch_classes=3, midi_span=5,
                contour="rising", home_pitch_class="A",
            ),
        ]
        patterns = detect_patterns(phrases)
        assert len(patterns) >= 1
        assert patterns[0].occurrence_count >= 2
        assert patterns[0].confidence > 0.5

    def test_detects_arpeggio_pattern(self):
        from app.jam_vocabulary import detect_patterns

        phrases = [
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=3.0,
                unique_pitch_classes=3, midi_span=7,
                contour="arch", home_pitch_class="A",
            ),
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=3.0,
                unique_pitch_classes=3, midi_span=7,
                contour="arch", home_pitch_class="A",
            ),
        ]
        patterns = detect_patterns(phrases)
        # Should detect something with A, C, E (minor arpeggio)
        assert len(patterns) >= 1

    def test_vocabulary_diversity_high(self):
        from app.jam_vocabulary import _compute_vocabulary_diversity

        phrases = [
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=5, midi_span=10,
                contour="mixed", home_pitch_class="A",
            ),
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=5, midi_span=10,
                contour="mixed", home_pitch_class="C",
            ),
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=5, midi_span=10,
                contour="mixed", home_pitch_class="E",
            ),
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=5, midi_span=10,
                contour="mixed", home_pitch_class="G",
            ),
        ]
        diversity = _compute_vocabulary_diversity(phrases)
        assert diversity > 0.5

    def test_vocabulary_diversity_low(self):
        from app.jam_vocabulary import _compute_vocabulary_diversity

        phrases = [
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=2, midi_span=3,
                contour="static", home_pitch_class="A",
            ),
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=2, midi_span=3,
                contour="static", home_pitch_class="A",
            ),
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=2, midi_span=3,
                contour="static", home_pitch_class="A",
            ),
        ]
        diversity = _compute_vocabulary_diversity(phrases)
        assert diversity < 0.3

    def test_extract_bundle_metrics(self):
        from app.jam_vocabulary import extract_bundle_metrics

        phrases = [
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=3, midi_span=5,
                contour="rising", home_pitch_class="A",
                beat_offset_mean=0.1, beat_offset_std=0.05,
            ),
            JamPhraseMetrics(
                duration_ms=1200, notes_per_second=3.0,
                unique_pitch_classes=4, midi_span=7,
                contour="falling", home_pitch_class="E",
                beat_offset_mean=0.2, beat_offset_std=0.08,
            ),
        ]
        metrics = extract_bundle_metrics(
            phrases=phrases,
            pitch_class_weight_map={"pc_A": 0.5, "pc_E": 0.3, "pc_C": 0.2},
            duration_seconds=30,
        )
        assert metrics["phrase_count"] == 2
        assert metrics["dominant_contour"] == "mixed"
        assert metrics["clarity"] > 0
        assert "pc_A" in metrics["pitch_class_distribution"]

    def test_extract_bundle_metrics_counts_notes_and_timing(self):
        from app.jam_vocabulary import extract_bundle_metrics

        phrases = [
            JamPhraseMetrics(
                duration_ms=1000, notes_per_second=2.0,
                unique_pitch_classes=3, midi_span=5,
                note_count=4, beat_offset_mean=100.0,
                intonation_cents=10.0,
            ),
            JamPhraseMetrics(
                duration_ms=2000, notes_per_second=3.0,
                unique_pitch_classes=4, midi_span=7,
                note_count=6, beat_offset_mean=200.0,
                intonation_cents=30.0,
            ),
        ]
        metrics = extract_bundle_metrics(
            phrases=phrases,
            pitch_class_weight_map={"pc_A": 1.0},
            duration_seconds=30,
        )
        assert metrics["total_notes"] == 10
        assert metrics["timing_ms"] == pytest.approx(150.0)
        assert metrics["intonation_cents"] == {"mean_abs": 20.0}


# ---------------------------------------------------------------------------
# /jam/summary endpoint tests
# ---------------------------------------------------------------------------

class TestJamSummaryEndpoint:
    def test_summary_with_phrases(self):
        payload = {
            "duration_seconds": 30,
            "pitch_class_weight_map": {"pc_A": 0.4, "pc_E": 0.3, "pc_C": 0.2, "pc_G": 0.1},
            "inferred_scale_label": "A minor pentatonic",
            "inference_confidence": "high",
            "track_label": "Blues Loop",
            "track_key": "A minor",
            "track_bpm": 80,
            "phrases": [
                {
                    "duration_ms": 1500,
                    "notes_per_second": 2.5,
                    "unique_pitch_classes": 4,
                    "midi_span": 8,
                    "contour": "arch",
                    "beat_offset_mean": 0.1,
                    "beat_offset_std": 0.05,
                    "home_pitch_class": "A",
                },
                {
                    "duration_ms": 1200,
                    "notes_per_second": 3.0,
                    "unique_pitch_classes": 3,
                    "midi_span": 5,
                    "contour": "rising",
                    "beat_offset_mean": 0.15,
                    "beat_offset_std": 0.07,
                    "home_pitch_class": "E",
                },
            ],
            "player_level": "intermediate",
            "previous_jam_count": 5,
            "weak_areas": ["bending", "vibrato"],
        }

        r = client.post("/jam/summary", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()

        bundle = data["bundle"]
        assert bundle["duration_seconds"] == 30
        assert bundle["inferred_scale_label"] == "A minor pentatonic"
        assert bundle["persona"] == "intermediate"
        assert bundle["phrase_count"] == 2
        assert bundle["clarity"] >= 0
        assert bundle["vocabulary_diversity"] >= 0
        assert isinstance(bundle["coach_summary"], str)
        assert len(bundle["coach_summary"]) > 0
        assert isinstance(bundle["coach_strengths"], list)
        assert isinstance(bundle["coach_focus_areas"], list)
        assert isinstance(bundle["coach_next_step"], str)

    def test_summary_short_jam(self):
        payload = {
            "duration_seconds": 5,
            "pitch_class_weight_map": {"pc_A": 1.0},
            "player_level": "beginner",
        }

        r = client.post("/jam/summary", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        bundle = data["bundle"]
        assert bundle["duration_seconds"] == 5
        assert bundle["phrase_count"] == 0
        # Should get fallback summary
        assert len(data["coach_summary"]) > 0

    def test_summary_no_phrases(self):
        payload = {
            "duration_seconds": 30,
            "pitch_class_weight_map": {"pc_C": 0.5, "pc_G": 0.5},
            "inferred_scale_label": "C major",
            "player_level": "advanced",
        }

        r = client.post("/jam/summary", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        bundle = data["bundle"]
        assert bundle["phrase_count"] == 0
        assert bundle["persona"] == "transcriber"

    def test_summary_learner_persona(self):
        payload = {
            "duration_seconds": 20,
            "pitch_class_weight_map": {"pc_A": 0.6, "pc_D": 0.4},
            "player_level": "beginner",
        }

        r = client.post("/jam/summary", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        bundle = data["bundle"]
        assert bundle["persona"] == "learner"

    def test_summary_explicit_persona_override(self):
        payload = {
            "duration_seconds": 20,
            "pitch_class_weight_map": {"pc_A": 0.6},
            "player_level": "beginner",
            "persona": "transcriber",
        }

        r = client.post("/jam/summary", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        bundle = data["bundle"]
        # Explicit override should win over player_level
        assert bundle["persona"] == "transcriber"

    def test_summary_returns_vocabulary_patterns(self):
        # Create enough phrases to trigger pattern detection
        phrases = [
            {
                "duration_ms": 1000,
                "notes_per_second": 2.0,
                "unique_pitch_classes": 3,
                "midi_span": 5,
                "contour": "rising",
                "beat_offset_mean": 0.1,
                "beat_offset_std": 0.05,
                "home_pitch_class": "A",
            }
            for _ in range(5)
        ]

        payload = {
            "duration_seconds": 30,
            "pitch_class_weight_map": {"pc_A": 0.8, "pc_E": 0.2},
            "inferred_scale_label": "A minor pentatonic",
            "phrases": phrases,
            "player_level": "intermediate",
        }

        r = client.post("/jam/summary", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        bundle = data["bundle"]
        assert isinstance(bundle["vocabulary_patterns"], list)
        assert bundle["vocabulary_diversity"] >= 0

    def test_summary_includes_deterministic_grade_and_phrase_feedback(self):
        phrases = [
            {
                "duration_ms": 1000,
                "notes_per_second": 2.5,
                "unique_pitch_classes": 7,
                "midi_span": 12,
                "contour": "mixed",
                "beat_offset_mean": 0,
                "beat_offset_std": 0,
                "note_count": 4,
                "intonation_cents": 0,
            },
            {
                "duration_ms": 1000,
                "notes_per_second": 0,
                "unique_pitch_classes": 1,
                "midi_span": 1,
                "contour": "static",
                "beat_offset_mean": 400,
                "beat_offset_std": 400,
                "note_count": 2,
                "intonation_cents": 50,
            },
        ]
        payload = {
            "duration_seconds": 20,
            "pitch_class_weight_map": {"pc_A": 1.0},
            "inferred_scale_label": "A minor pentatonic",
            "phrases": phrases,
            "player_level": "intermediate",
        }

        r = client.post("/jam/summary", json=payload)
        assert r.status_code == 200, r.text
        bundle = r.json()["bundle"]

        assert bundle["grade"] in {"A", "B", "C", "D", "F"}
        assert 0 <= bundle["grade_score"] <= 100
        assert bundle["grade_breakdown"]
        assert bundle["weakest_phrase_index"] == 1
        assert len(bundle["phrase_feedback"]) == 2
        assert bundle["phrase_feedback"][0]["phrase_index"] == 1
        assert all(item["suggestion"] for item in bundle["phrase_feedback"])
        assert all(0 <= item["phrase_index"] < 2 for item in bundle["phrase_feedback"])

    def test_llm_exception_returns_fallback_bundle(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        payload = {
            "duration_seconds": 30,
            "pitch_class_weight_map": {"pc_A": 1.0},
            "inferred_scale_label": "A minor pentatonic",
            "player_level": "intermediate",
        }
        with patch("app.main.generate_jam_summary_with_claude", side_effect=RuntimeError("boom")):
            r = client.post("/jam/summary", json=payload)

        assert r.status_code == 200, r.text
        bundle = r.json()["bundle"]
        assert bundle["coach_summary"]
        assert bundle["grade"] == "F"

    def test_llm_malformed_json_returns_fallback_bundle(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        payload = {
            "duration_seconds": 30,
            "pitch_class_weight_map": {"pc_A": 1.0},
            "inferred_scale_label": "A minor pentatonic",
            "player_level": "beginner",
        }
        with patch("app.coach._call_claude_text", return_value="not json at all"):
            r = client.post("/jam/summary", json=payload)

        assert r.status_code == 200, r.text
        bundle = r.json()["bundle"]
        assert bundle["coach_summary"]
        assert bundle["persona"] == "learner"

    def test_llm_output_is_capped_and_missing_suggestions_filled(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        phrases = [
            {
                "duration_ms": 1000,
                "notes_per_second": 2.0,
                "unique_pitch_classes": 3,
                "midi_span": 5,
                "contour": "mixed",
                "note_count": 3,
            }
            for _ in range(6)
        ]
        payload = {
            "duration_seconds": 30,
            "pitch_class_weight_map": {"pc_A": 1.0},
            "inferred_scale_label": "A minor pentatonic",
            "phrases": phrases,
            "player_level": "intermediate",
        }
        mocked = {
            "coach_summary": "Solid jam.",
            "coach_strengths": [f"strength {i}" for i in range(6)],
            "coach_focus_areas": [f"focus {i}" for i in range(6)],
            "coach_next_step": "Loop the weak phrase.",
            "phrase_feedback": [
                {"phrase_index": 1, "suggestion": "Claude suggestion."},
                {"phrase_index": 99, "suggestion": "Unknown index."},
                {"phrase_index": 2, "suggestion": ""},
            ],
        }
        with patch("app.main.generate_jam_summary_with_claude", return_value=mocked):
            r = client.post("/jam/summary", json=payload)

        assert r.status_code == 200, r.text
        bundle = r.json()["bundle"]
        assert len(bundle["coach_strengths"]) == 3
        assert len(bundle["coach_focus_areas"]) == 3
        assert len(bundle["phrase_feedback"]) == 5
        assert [item["phrase_index"] for item in bundle["phrase_feedback"]] == [0, 1, 2, 3, 4]
        assert bundle["phrase_feedback"][0]["suggestion"]
        assert bundle["phrase_feedback"][1]["suggestion"] == "Claude suggestion."
        assert bundle["phrase_feedback"][2]["suggestion"]


class TestPersonaPrompts:
    def _call_with_persona(self, persona: str) -> str:
        from app.coach import generate_jam_summary_with_claude

        captured: dict[str, str] = {}

        def fake_call(**kwargs):
            captured["system_prompt"] = kwargs["system_prompt"]
            return json.dumps(
                {
                    "coach_summary": "Summary.",
                    "coach_strengths": [],
                    "coach_focus_areas": [],
                    "coach_next_step": "Practice.",
                    "phrase_feedback": [],
                }
            )

        with patch("app.coach._call_claude_text", side_effect=fake_call):
            result = generate_jam_summary_with_claude(
                api_key="test-key",
                duration_seconds=30,
                inferred_scale_label="A minor",
                inference_confidence="high",
                track_label="Loop",
                track_key="A minor",
                track_bpm=80,
                phrase_count=0,
                avg_notes_per_second=2.0,
                dominant_contour="mixed",
                vocabulary_diversity=0.5,
                pitch_class_weight_map={},
                vocabulary_pattern_count=0,
                vocabulary_pattern_details="",
                phrase_table="none",
                player_level="intermediate",
                previous_jam_count=0,
                weak_areas=[],
                persona=persona,
            )

        assert result is not None
        return captured["system_prompt"]

    def test_learner_and_transcriber_use_different_system_prompts(self):
        learner = self._call_with_persona("learner")
        transcriber = self._call_with_persona("transcriber")
        assert learner != transcriber
        assert "beginner" in learner.lower()
        assert "analytical" in transcriber.lower()


# ---------------------------------------------------------------------------
# Fallback summary tests
# ---------------------------------------------------------------------------

class TestJamSummaryFallback:
    def test_fallback_short_jam(self):
        from app.coach import generate_jam_summary_fallback

        result = generate_jam_summary_fallback(
            duration_seconds=5,
            inferred_scale_label=None,
            pitch_class_weight_map={},
            phrase_count=0,
            vocabulary_diversity=0.0,
            player_level="beginner",
        )
        assert "Short jam" in result["coach_summary"]

    def test_fallback_normal_jam(self):
        from app.coach import generate_jam_summary_fallback

        result = generate_jam_summary_fallback(
            duration_seconds=30,
            inferred_scale_label="A minor pentatonic",
            pitch_class_weight_map={"pc_A": 0.5, "pc_E": 0.3, "pc_C": 0.2},
            phrase_count=8,
            vocabulary_diversity=0.7,
            player_level="intermediate",
        )
        assert "A minor pentatonic" in result["coach_summary"]
        assert len(result["coach_strengths"]) > 0
        assert len(result["coach_next_step"]) > 0
