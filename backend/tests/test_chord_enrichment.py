"""Tests for Commit 116: LLM-Enhanced Chord Correction & Roman Numeral Analysis."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.chord_enrichment import (
    _apply_llm_corrections,
    _compute_cache_key,
    _parse_key,
    assign_roman_numerals,
    compute_roman_numeral,
    enrich_chord_timeline,
)
from app.schemas import ChordEvent


# ---------------------------------------------------------------------------
# Deterministic Roman numeral tests
# ---------------------------------------------------------------------------


class TestParseKey:
    def test_major(self):
        assert _parse_key("C major") == (0, "major")

    def test_minor(self):
        assert _parse_key("A minor") == (9, "minor")

    def test_sharp_root(self):
        assert _parse_key("G# minor") == (8, "minor")

    def test_abbreviated_minor(self):
        assert _parse_key("Am") == (9, "minor")

    def test_bare_root_defaults_major(self):
        assert _parse_key("C") == (0, "major")

    def test_empty_defaults(self):
        assert _parse_key("") == (0, "major")


class TestComputeRomanNumeral:
    """Test deterministic Roman numeral computation for common progressions."""

    def test_I_in_C_major(self):
        assert compute_roman_numeral("C:maj", "C major") == "I"

    def test_ii_in_C_major(self):
        assert compute_roman_numeral("D:min", "C major") == "ii"

    def test_iii_in_C_major(self):
        assert compute_roman_numeral("E:min", "C major") == "iii"

    def test_IV_in_C_major(self):
        assert compute_roman_numeral("F:maj", "C major") == "IV"

    def test_V_in_C_major(self):
        assert compute_roman_numeral("G:maj", "C major") == "V"

    def test_vi_in_C_major(self):
        assert compute_roman_numeral("A:min", "C major") == "vi"

    def test_vii_dim_in_C_major(self):
        assert compute_roman_numeral("B:dim", "C major") == "vii°"

    def test_V7_in_C_major(self):
        assert compute_roman_numeral("G:7", "C major") == "V7"

    def test_ii7_in_C_major(self):
        assert compute_roman_numeral("D:min7", "C major") == "ii7"

    def test_I_maj7(self):
        assert compute_roman_numeral("C:maj7", "C major") == "Imaj7"

    def test_V9(self):
        assert compute_roman_numeral("G:9", "C major") == "V9"

    def test_no_chord(self):
        assert compute_roman_numeral("N", "C major") == ""

    def test_i_in_A_minor(self):
        assert compute_roman_numeral("A:min", "A minor") == "i"

    def test_iv_in_A_minor(self):
        assert compute_roman_numeral("D:min", "A minor") == "iv"

    def test_V_in_A_minor(self):
        assert compute_roman_numeral("E:min", "A minor") == "v"

    def test_VII_in_A_minor(self):
        assert compute_roman_numeral("G:maj", "A minor") == "VII"

    def test_VI_in_A_minor(self):
        assert compute_roman_numeral("F:maj", "A minor") == "VI"

    def test_III_in_A_minor(self):
        assert compute_roman_numeral("C:maj", "A minor") == "III"

    def test_ii_dim_in_A_minor(self):
        assert compute_roman_numeral("B:dim", "A minor") == "ii°"

    def test_sus4_chord(self):
        result = compute_roman_numeral("G:sus4", "C major")
        assert "sus4" in result

    def test_aug_chord(self):
        result = compute_roman_numeral("F#:aug", "C major")
        assert "#" in result

    def test_dim7_chord(self):
        result = compute_roman_numeral("B:dim7", "C major")
        assert "°" in result

    def test_altered_dominant(self):
        result = compute_roman_numeral("G:7#9", "C major")
        assert "7#9" in result

    def test_non_diatonic_sharp_iv(self):
        result = compute_roman_numeral("F#:min", "C major")
        assert "#" in result
        assert "iv" in result.lower()

    def test_empty_chord(self):
        assert compute_roman_numeral("", "C major") == ""


class TestAssignRomanNumerals:
    def test_ii_V_I_progression(self):
        events = [
            ChordEvent(timestamp=0.0, chord="D:min7", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:7", confidence=0.85),
            ChordEvent(timestamp=4.0, chord="C:maj7", confidence=0.95),
        ]
        result = assign_roman_numerals(events, "C major")
        assert result[0].roman_numeral == "ii7"
        assert result[1].roman_numeral == "V7"
        assert result[2].roman_numeral == "Imaj7"

    def test_empty_events(self):
        result = assign_roman_numerals([], "C major")
        assert result == []

    def test_nochord_events(self):
        events = [ChordEvent(timestamp=0.0, chord="N", confidence=0.5)]
        result = assign_roman_numerals(events, "C major")
        assert result[0].roman_numeral == ""


# ---------------------------------------------------------------------------
# LLM enrichment tests (with mocked Anthropic)
# ---------------------------------------------------------------------------


class TestApplyLLMCorrections:
    def test_correction_applied(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="F#:min", confidence=0.4),
            ChordEvent(timestamp=4.0, chord="G:maj", confidence=0.85),
        ]
        llm_results = [
            {"timestamp": 0.0, "chord": "C:maj"},
            {"timestamp": 2.0, "chord": "F:maj", "roman_numeral": "IV"},
            {"timestamp": 4.0, "chord": "G:7"},
        ]
        corrected = _apply_llm_corrections(events, llm_results, "C major")
        # 2 corrections: F#:min→F:maj and G:maj→G:7
        assert corrected == 2
        assert events[0].chord == "C:maj"
        assert events[0].correction_applied is False
        assert events[1].chord == "F:maj"
        assert events[1].correction_applied is True
        assert events[1].roman_numeral == "IV"
        assert events[2].chord == "G:7"
        assert events[2].correction_applied is True

    def test_no_corrections(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ]
        llm_results = [{"timestamp": 0.0, "chord": "C:maj"}]
        corrected = _apply_llm_corrections(events, llm_results, "C major")
        assert corrected == 0
        assert events[0].correction_applied is False

    def test_empty_llm_results(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ]
        corrected = _apply_llm_corrections(events, [], "C major")
        assert corrected == 0


class TestComputeCacheKey:
    def test_same_input_same_key(self):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        key1 = _compute_cache_key("C major", events)
        key2 = _compute_cache_key("C major", events)
        assert key1 == key2

    def test_different_key_different_hash(self):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        key1 = _compute_cache_key("C major", events)
        key2 = _compute_cache_key("G major", events)
        assert key1 != key2

    def test_different_events_different_hash(self):
        events1 = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        events2 = [ChordEvent(timestamp=0.0, chord="G:maj", confidence=0.9)]
        key1 = _compute_cache_key("C major", events1)
        key2 = _compute_cache_key("C major", events2)
        assert key1 != key2


class TestEnrichChordTimeline:
    def test_empty_events(self):
        events, metrics = enrich_chord_timeline([], "C major", api_key="")
        assert events == []
        assert metrics["corrected_events"] == 0

    @patch("app.chord_enrichment._call_claude_enrichment")
    def test_skips_when_no_api_key(self, mock_call: MagicMock):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        enriched, metrics = enrich_chord_timeline(events, "C major", api_key="")
        mock_call.assert_not_called()
        assert enriched[0].roman_numeral == "I"

    @patch("app.chord_enrichment._call_claude_enrichment")
    def test_skips_when_kill_switch(self, mock_call: MagicMock):
        events = [ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)]
        with patch.dict(os.environ, {"HARMONIQ_SKIP_CHORD_ENRICHMENT": "1"}):
            enriched, metrics = enrich_chord_timeline(events, "C major", api_key="test-key")
        mock_call.assert_not_called()
        assert enriched[0].roman_numeral == "I"


class TestEndToEnd:
    """Integration test: ii-V-I in C major is correctly labeled."""

    def test_ii_V_I_labeling(self):
        events = [
            ChordEvent(timestamp=0.0, chord="D:min7", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="G:7", confidence=0.85),
            ChordEvent(timestamp=4.0, chord="C:maj7", confidence=0.95),
        ]
        assign_roman_numerals(events, "C major")
        assert events[0].roman_numeral == "ii7"
        assert events[1].roman_numeral == "V7"
        assert events[2].roman_numeral == "Imaj7"

    def test_I_IV_V_progression(self):
        events = [
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="F:maj", confidence=0.85),
            ChordEvent(timestamp=4.0, chord="G:maj", confidence=0.9),
        ]
        assign_roman_numerals(events, "C major")
        assert events[0].roman_numeral == "I"
        assert events[1].roman_numeral == "IV"
        assert events[2].roman_numeral == "V"

    def test_minor_key_progression(self):
        events = [
            ChordEvent(timestamp=0.0, chord="A:min", confidence=0.9),
            ChordEvent(timestamp=2.0, chord="D:min", confidence=0.85),
            ChordEvent(timestamp=4.0, chord="E:min", confidence=0.9),
            ChordEvent(timestamp=6.0, chord="A:min", confidence=0.95),
        ]
        assign_roman_numerals(events, "A minor")
        assert events[0].roman_numeral == "i"
        assert events[1].roman_numeral == "iv"
        assert events[2].roman_numeral == "v"
        assert events[3].roman_numeral == "i"
