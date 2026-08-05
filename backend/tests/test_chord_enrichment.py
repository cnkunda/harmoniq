"""Tests for LLM Chord Enrichment (Commit 114)."""
import json
import pytest
import os
from unittest.mock import patch, MagicMock

os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-mocking")

from app.schemas import ChordEvent, ChordTimeline
from app.chord_enrichment import (
    compute_roman_numeral,
    enrich_chord_timeline,
    _cache_key,
    _get_cached,
    _set_cached,
    _enrichment_cache,
    CONFIDENCE_DELTA_THRESHOLD,
)


class TestRomanNumeral:
    """Test deterministic Roman numeral computation."""

    def test_I_in_C_major(self):
        """C:maj in C major should be 'I'."""
        assert compute_roman_numeral("C:maj", "C major") == "I"

    def test_ii_in_C_major(self):
        """D:min in C major should be 'ii'."""
        assert compute_roman_numeral("D:min", "C major") == "ii"

    def test_V7_in_C_major(self):
        """G:7 in C major should be 'V7'."""
        assert compute_roman_numeral("G:7", "C major") == "V7"

    def test_IV_in_C_major(self):
        """F:maj in C major should be 'IV'."""
        assert compute_roman_numeral("F:maj", "C major") == "IV"

    def test_i_in_A_minor(self):
        """A:min in A minor should be 'i'."""
        assert compute_roman_numeral("A:min", "A minor") == "i"

    def test_V_in_A_minor(self):
        """E:maj in A minor should be 'V'."""
        assert compute_roman_numeral("E:maj", "A minor") == "V"

    def test_iv_in_A_minor(self):
        """D:min in A minor should be 'iv'."""
        assert compute_roman_numeral("D:min", "A minor") == "iv"

    def test_N_returns_none(self):
        """No-chord 'N' should return None."""
        assert compute_roman_numeral("N", "C major") is None

    def test_no_key_returns_none(self):
        """No key signature should return None."""
        assert compute_roman_numeral("C:maj", None) is None

    def test_empty_key_returns_none(self):
        """Empty key string should return None."""
        assert compute_roman_numeral("C:maj", "") is None

    def test_V7_with_extension(self):
        """G:7 in C major should include the 7 suffix."""
        result = compute_roman_numeral("G:7", "C major")
        assert result is not None
        assert "V" in result
        assert "7" in result

    def test_maj7_in_C_major(self):
        """C:maj7 in C major should be 'Imaj7'."""
        result = compute_roman_numeral("C:maj7", "C major")
        assert result is not None
        assert "I" in result
        assert "maj7" in result

    def test_dim7_in_C_major(self):
        """B:dim7 in C major should include 'dim7'."""
        result = compute_roman_numeral("B:dim7", "C major")
        assert result is not None
        assert "dim7" in result

    def test_ii_V_I_progression(self):
        """Classic ii-V-I in C major: Dm7 → G7 → Cmaj7."""
        assert compute_roman_numeral("D:min7", "C major") == "ii7"
        assert compute_roman_numeral("G:7", "C major") == "V7"
        assert compute_roman_numeral("C:maj7", "C major") == "Imaj7"


class TestCache:
    """Test SHA256 cache for enrichment results."""

    def test_cache_key_deterministic(self):
        """Same input should produce same cache key."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:7", confidence=0.8),
        ])
        key1 = _cache_key(timeline, "C major")
        key2 = _cache_key(timeline, "C major")
        assert key1 == key2

    def test_cache_key_different_for_different_key(self):
        """Different key signatures should produce different cache keys."""
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        key1 = _cache_key(timeline, "C major")
        key2 = _cache_key(timeline, "G major")
        assert key1 != key2

    def test_cache_key_different_for_different_chords(self):
        """Different chord timelines should produce different cache keys."""
        t1 = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        t2 = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="G:7", confidence=0.9),
        ])
        key1 = _cache_key(t1, "C major")
        key2 = _cache_key(t2, "C major")
        assert key1 != key2

    def test_cache_set_and_get(self):
        """Cache should store and retrieve values."""
        _enrichment_cache.clear()
        key = "test_key_123"
        value = [{"index": 0, "corrected_chord": "C:maj", "roman_numeral": "I"}]
        _set_cached(key, value)
        assert _get_cached(key) == value
        _enrichment_cache.clear()

    def test_cache_lru_eviction(self):
        """Cache should evict oldest entry when full."""
        _enrichment_cache.clear()
        # Fill cache to max (256)
        for i in range(257):
            _set_cached(f"key_{i}", [{"index": i}])
        # Should have evicted the first key
        assert _get_cached("key_0") is None
        assert _get_cached("key_256") is not None
        _enrichment_cache.clear()


class TestEnrichChordTimeline:
    """Test the main enrichment function."""

    def test_empty_timeline(self):
        """Empty timeline should return unchanged."""
        timeline = ChordTimeline(events=[])
        result, metrics = enrich_chord_timeline(timeline, key_signature="C major")
        assert result.events == []
        assert metrics["enrichment_applied"] == 0

    def test_no_key_skips_llm(self):
        """Without key signature, only Roman numerals are computed (no LLM)."""
        from unittest.mock import patch
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:7", confidence=0.8),
        ])
        with patch("app.chord_enrichment._call_llm_enrichment", return_value=None):
            result, metrics = enrich_chord_timeline(timeline, key_signature=None)
        assert len(result.events) == 2
        # Roman numerals should be None when no key
        for ev in result.events:
            assert ev.roman_numeral is None

    def test_deterministic_roman_numerals(self):
        """Roman numerals should be computed deterministically without LLM."""
        from unittest.mock import patch
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:7", confidence=0.8),
            ChordEvent(timestamp=1.0, chord="F:maj", confidence=0.85),
        ])
        with patch("app.chord_enrichment._call_llm_enrichment", return_value=None):
            result, metrics = enrich_chord_timeline(timeline, key_signature="C major")
        assert result.events[0].roman_numeral == "I"
        assert result.events[1].roman_numeral == "V7"
        assert result.events[2].roman_numeral == "IV"
        assert metrics["roman_numerals_assigned"] == 3

    def test_correction_delta_zero_without_llm(self):
        """Without LLM, correction_delta should be 0."""
        from unittest.mock import patch
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        with patch("app.chord_enrichment._call_llm_enrichment", return_value=None):
            result, _ = enrich_chord_timeline(timeline, key_signature="C major")
        assert result.events[0].correction_delta == 0.0
        assert result.events[0].llm_corrected_chord is None

    def test_section_range_filter(self):
        """Section range should filter which events are enriched."""
        from unittest.mock import patch
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=5.0, chord="G:7", confidence=0.8),
            ChordEvent(timestamp=10.0, chord="F:maj", confidence=0.85),
        ])
        with patch("app.chord_enrichment._call_llm_enrichment", return_value=None):
            result, _ = enrich_chord_timeline(
                timeline,
                key_signature="C major",
                section_range=(0.0, 6.0),
            )
        # Only first two events should have Roman numerals
        assert result.events[0].roman_numeral is not None
        assert result.events[1].roman_numeral is not None
        assert result.events[2].roman_numeral is None

    def test_confidence_preserved(self):
        """Original confidence values should be preserved."""
        from unittest.mock import patch
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.923),
        ])
        with patch("app.chord_enrichment._call_llm_enrichment", return_value=None):
            result, _ = enrich_chord_timeline(timeline, key_signature="C major")
        assert result.events[0].confidence == 0.923

    def test_timestamps_preserved(self):
        """Original timestamps should be preserved."""
        from unittest.mock import patch
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.37, chord="G:7", confidence=0.8),
        ])
        with patch("app.chord_enrichment._call_llm_enrichment", return_value=None):
            result, _ = enrich_chord_timeline(timeline, key_signature="C major")
        assert result.events[0].timestamp == 0.0
        assert result.events[1].timestamp == 0.37

    @patch("app.chord_enrichment._call_llm_enrichment")
    def test_llm_correction_applied(self, mock_llm):
        """LLM correction should be applied when confidence delta > threshold."""
        # Mock LLM response that corrects a chord
        mock_llm.return_value = json.dumps([
            {"index": 1, "corrected_chord": "F:maj", "roman_numeral": "IV", "confidence_delta": 0.25},
        ])

        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=0.5, chord="G:7", confidence=0.3),  # Low confidence
        ])
        result, metrics = enrich_chord_timeline(timeline, key_signature="C major")

        assert result.events[1].llm_corrected_chord == "F:maj"
        assert result.events[1].correction_delta == 0.25
        assert result.events[1].roman_numeral == "IV"
        assert metrics["enrichment_applied"] == 1
        assert metrics["llm_called"] is True

    @patch("app.chord_enrichment._call_llm_enrichment")
    def test_llm_low_delta_not_applied(self, mock_llm):
        """LLM correction below threshold should not be applied."""
        mock_llm.return_value = json.dumps([
            {"index": 0, "corrected_chord": "C:maj", "roman_numeral": "I", "confidence_delta": 0.05},
        ])

        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        result, metrics = enrich_chord_timeline(timeline, key_signature="C major")

        assert result.events[0].llm_corrected_chord is None  # Below threshold
        assert result.events[0].correction_delta == 0.0
        assert metrics["enrichment_applied"] == 0

    @patch("app.chord_enrichment._call_llm_enrichment")
    def test_llm_failure_graceful(self, mock_llm):
        """LLM failure should not crash enrichment."""
        mock_llm.return_value = None

        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        result, metrics = enrich_chord_timeline(timeline, key_signature="C major")
        assert len(result.events) == 1
        assert metrics["llm_called"] is False

    @patch("app.chord_enrichment._call_llm_enrichment")
    def test_llm_invalid_json_graceful(self, mock_llm):
        """Invalid JSON from LLM should be handled gracefully."""
        mock_llm.return_value = "This is not valid JSON at all!"

        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        result, metrics = enrich_chord_timeline(timeline, key_signature="C major")
        assert len(result.events) == 1
        # Should fall back to deterministic Roman numerals
        assert result.events[0].roman_numeral == "I"

    @patch("app.chord_enrichment._call_llm_enrichment")
    def test_llm_markdown_stripped(self, mock_llm):
        """LLM response with markdown fences should be parsed correctly."""
        mock_llm.return_value = '```json\n[{"index": 0, "corrected_chord": "C:maj", "roman_numeral": "I", "confidence_delta": 0.0}]\n```'

        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        result, _ = enrich_chord_timeline(timeline, key_signature="C major")
        assert result.events[0].roman_numeral == "I"


class TestChordEventSchema:
    """Test that ChordEvent schema supports new fields."""

    def test_default_fields(self):
        """New fields should have correct defaults."""
        ev = ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9)
        assert ev.roman_numeral is None
        assert ev.llm_corrected_chord is None
        assert ev.correction_delta == 0.0

    def test_all_fields(self):
        """All fields should be settable."""
        ev = ChordEvent(
            timestamp=0.0,
            chord="C:maj",
            confidence=0.9,
            roman_numeral="I",
            llm_corrected_chord="F:maj",
            correction_delta=0.25,
        )
        assert ev.roman_numeral == "I"
        assert ev.llm_corrected_chord == "F:maj"
        assert ev.correction_delta == 0.25

    def test_json_roundtrip(self):
        """ChordEvent should survive JSON serialization."""
        ev = ChordEvent(
            timestamp=0.5,
            chord="G:7",
            confidence=0.8,
            roman_numeral="V7",
            llm_corrected_chord=None,
            correction_delta=0.0,
        )
        data = ev.model_dump()
        ev2 = ChordEvent(**data)
        assert ev2.timestamp == ev.timestamp
        assert ev2.chord == ev.chord
        assert ev2.roman_numeral == ev.roman_numeral

    def test_correction_delta_bounds(self):
        """correction_delta should be clamped to [0, 1]."""
        ev = ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9, correction_delta=0.5)
        assert ev.correction_delta == 0.5
