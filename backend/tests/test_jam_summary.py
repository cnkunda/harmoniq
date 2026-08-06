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
