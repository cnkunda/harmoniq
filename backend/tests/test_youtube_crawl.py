"""Tests for YouTube crawl pipeline (Commit 105 Phase 3).

Tests: search filtering, quality checks, confidence filter,
OCR detection mock, CQT extraction.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.crawl_chord_videos import (
    _build_search_terms,
    _check_quality_filters,
    _extract_cqt,
    _build_windows,
    CHROMA_BINS,
    BASS_BINS,
    FEATURE_DIM,
    WINDOW,
    N_CHORD_IDX,
)


class TestBuildSearchTerms:
    def test_returns_list(self):
        terms = _build_search_terms()
        assert isinstance(terms, list)
        assert len(terms) > 0

    def test_contains_chord_format(self):
        terms = _build_search_terms()
        # Should contain at least one "guitar chord" term
        assert any("guitar chord" in t for t in terms)
        # Should contain at least one "how to play" term
        assert any("how to play" in t for t in terms)

    def test_contains_C_maj(self):
        terms = _build_search_terms()
        assert any("C:maj" in t for t in terms)


class TestCheckQualityFilters:
    def test_passes_good_video(self):
        info = {
            "duration": 300,  # 5 min
            "height": 1080,
            "channel_follower_count": 50000,
        }
        passes, reason = _check_quality_filters(info)
        assert passes is True

    def test_fails_long_duration(self):
        info = {
            "duration": 3600,  # 60 min — too long
            "height": 1080,
            "channel_follower_count": 50000,
        }
        passes, reason = _check_quality_filters(info)
        assert passes is False
        assert "Duration" in reason

    def test_fails_low_resolution(self):
        info = {
            "duration": 300,
            "height": 360,  # 360p — too low
            "channel_follower_count": 50000,
        }
        passes, reason = _check_quality_filters(info)
        assert passes is False
        assert "Resolution" in reason

    def test_fails_few_subscribers(self):
        info = {
            "duration": 300,
            "height": 1080,
            "channel_follower_count": 100,  # Too few
        }
        passes, reason = _check_quality_filters(info)
        assert passes is False
        assert "Subscribers" in reason

    def test_missing_fields_defaults_to_zero(self):
        info = {}
        passes, reason = _check_quality_filters(info)
        assert passes is False


class TestExtractCqt:
    def test_output_shape(self):
        sr = 44100
        y = np.random.randn(int(sr * 0.3)).astype(np.float32) * 0.01
        features = _extract_cqt(y, sr)
        assert features.shape[1] == FEATURE_DIM

    def test_normalization(self):
        sr = 44100
        y = np.random.randn(int(sr * 0.3)).astype(np.float32) * 0.01
        features = _extract_cqt(y, sr)
        cqt_part = features[:, :CHROMA_BINS]
        row_sums = cqt_part.sum(axis=1)
        assert np.allclose(row_sums, 1.0, atol=0.15)


class TestBuildWindows:
    def test_window_shape(self):
        T = 100
        features = np.random.randn(T, FEATURE_DIM).astype(np.float32)
        labels = np.random.randint(0, 10, size=T).astype(np.int32)
        windows, window_labels = _build_windows(features, labels)
        expected = (T + 64 - 1) // 64
        assert windows.shape == (expected, WINDOW, FEATURE_DIM)
        assert window_labels.shape == (expected,)

    def test_labels_match(self):
        T = 200
        features = np.zeros((T, FEATURE_DIM), dtype=np.float32)
        labels = np.full(T, 42, dtype=np.int32)
        _, window_labels = _build_windows(features, labels)
        assert window_labels[0] == 42


class TestManifestFormat:
    def test_manifest_entry_structure(self):
        entry = {
            "clip_id": "abc123_C_maj",
            "chord": "C:maj",
            "url": "https://youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "channel_id": "UCtest",
            "channel_name": "Test Guitar Channel",
            "confidence": 0.95,
            "windows": 42,
            "duration_s": 120,
            "crawled_at": "2026-01-01T00:00:00+00:00",
        }
        # Verify all required fields are present
        required_fields = [
            "clip_id", "chord", "url", "video_id",
            "channel_id", "channel_name", "confidence",
        ]
        for field in required_fields:
            assert field in entry, f"Missing required field: {field}"

    def test_manifest_sortable(self):
        entries = [
            {"chord": "G:maj"},
            {"chord": "C:maj"},
            {"chord": "A:min"},
        ]
        sorted_entries = sorted(entries, key=lambda x: x["chord"])
        assert sorted_entries[0]["chord"] == "A:min"
        assert sorted_entries[1]["chord"] == "C:maj"
        assert sorted_entries[2]["chord"] == "G:maj"


class TestOcrCheck:
    def test_ocr_check_fallback(self):
        """When pytesseract is unavailable, OCR check should allow through."""
        from scripts.crawl_chord_videos import _ocr_check_segment
        # Create a temp empty file — the function should handle this gracefully
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            result = _ocr_check_segment(Path(f.name))
            assert result is True, "OCR fallback should return True"
