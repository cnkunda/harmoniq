"""Pure-logic tests for generated-backing verification and loop preparation (J3)."""
from __future__ import annotations

import numpy as np

from app.music_generation.postprocess import (
    bpm_mismatch_reason,
    key_mismatch_reason,
    normalize_requested_key,
    trim_and_envelope,
)


class TestKeyParsing:
    def test_parses_root_and_mode(self) -> None:
        assert normalize_requested_key("A minor") == ("A", "minor")
        assert normalize_requested_key("F# major") == ("F#", "major")

    def test_flats_normalized_to_sharps(self) -> None:
        assert normalize_requested_key("Bb major") == ("A#", "major")
        assert normalize_requested_key("db") == ("C#", None)

    def test_unknown_key_returns_none(self) -> None:
        assert normalize_requested_key("H lydian") == (None, None)


class TestKeyVerification:
    def test_accepts_matching_key(self) -> None:
        assert key_mismatch_reason("A minor", "A minor", 0.8) is None

    def test_rejects_confident_root_mismatch(self) -> None:
        reason = key_mismatch_reason("A minor", "C major", 0.8)
        assert reason is not None
        assert "key_mismatch" in reason

    def test_ignores_low_confidence_detection(self) -> None:
        assert key_mismatch_reason("A minor", "C major", 0.2) is None

    def test_rejects_confident_mode_mismatch(self) -> None:
        reason = key_mismatch_reason("A minor", "A major", 0.8)
        assert reason is not None
        assert "mode_mismatch" in reason

    def test_no_requested_key_no_rejection(self) -> None:
        assert key_mismatch_reason(None, "C major", 0.9) is None


class TestTempoVerification:
    def test_within_tolerance(self) -> None:
        assert bpm_mismatch_reason(70, 71.5) is None

    def test_half_and_double_time_allowed(self) -> None:
        assert bpm_mismatch_reason(70, 140.0) is None
        assert bpm_mismatch_reason(120, 60.0) is None

    def test_gross_mismatch_rejected(self) -> None:
        reason = bpm_mismatch_reason(70, 120.0)
        assert reason is not None
        assert "tempo_mismatch" in reason


class TestTrimAndEnvelope:
    def test_trims_to_last_downbeat_and_fades(self) -> None:
        sr = 1000
        samples = np.ones((2000, 2), dtype=np.float32)
        out, end = trim_and_envelope(samples, sr, [0.0, 0.5, 1.0])
        assert len(out) == 1000
        assert end == 1.0
        assert out[0, 0] < 0.1
        assert out[-1, 0] < 0.1

    def test_keeps_length_without_downbeats(self) -> None:
        samples = np.ones((800, 1), dtype=np.float32)
        out, end = trim_and_envelope(samples, 1000, [])
        assert len(out) == 800
        assert end == 0.8
