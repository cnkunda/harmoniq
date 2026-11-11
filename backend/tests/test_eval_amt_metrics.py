"""W0 evaluation metric tests (no audio, no MT3)."""

from __future__ import annotations

import json

import pytest

from app.evaluation.ground_truth import GTChord, GTNote
from app.evaluation.metrics import (
    calibration_metrics,
    chord_event_prf,
    chord_frame_accuracy,
    match_notes,
    note_metrics,
)
from app.evaluation.report import render_comparison_markdown
from app.evaluation.verdict import (
    VerdictInput,
    compute_verdict,
    verdict_matches,
)


def _note(pitch: int, onset: float, offset: float, **kwargs) -> GTNote:
    return GTNote(pitch=pitch, onset=onset, offset=offset, **kwargs)


class TestNoteMatching:
    def test_exact_match(self):
        pairs, prf = match_notes(
            [_note(60, 1.0, 1.5)],
            [_note(60, 1.0, 1.5)],
        )
        assert pairs == [(0, 0)]
        assert prf.f1 == pytest.approx(1.0)

    def test_onset_within_50ms(self):
        pairs, _ = match_notes(
            [_note(60, 1.0, 1.5)],
            [_note(60, 1.049, 1.5)],
        )
        assert pairs == [(0, 0)]

    def test_onset_outside_50ms(self):
        pairs, prf = match_notes(
            [_note(60, 1.0, 1.5)],
            [_note(60, 1.051, 1.5)],
        )
        assert pairs == []
        assert prf.f1 == 0.0

    def test_pitch_mismatch_is_not_a_match(self):
        pairs, _ = match_notes(
            [_note(60, 1.0, 1.5)],
            [_note(61, 1.0, 1.5)],
        )
        assert pairs == []

    def test_program_requirement(self):
        ref = [_note(60, 1.0, 1.5, program=24)]
        est = [_note(60, 1.0, 1.5, program=0)]
        assert match_notes(ref, est)[0] == [(0, 0)]
        assert match_notes(ref, est, require_program=True)[0] == []

    def test_offset_tolerance_uses_duration(self):
        # Reference duration 1.0s -> offset tolerance max(0.05, 0.2) = 0.2s.
        ref = [_note(60, 1.0, 2.0)]
        est = [_note(60, 1.0, 2.19)]
        assert match_notes(ref, est, require_offset=True)[0] == [(0, 0)]
        est_far = [_note(60, 1.0, 2.21)]
        assert match_notes(ref, est_far, require_offset=True)[0] == []

    def test_one_to_one_matching(self):
        ref = [_note(60, 1.0, 1.5)]
        est = [_note(60, 1.0, 1.5), _note(60, 1.01, 1.5)]
        pairs, prf = match_notes(ref, est)
        assert len(pairs) == 1
        assert prf.fp == 1


class TestNoteMetrics:
    def test_overlap_and_dynamics(self):
        ref = [_note(60, 1.0, 2.0, velocity=80, program=24)]
        est = [_note(60, 1.0, 2.0, velocity=100, program=24)]
        result = note_metrics(ref, est)
        assert result["overlap_mean"] == pytest.approx(1.0)
        assert result["dynamics_mae"] == pytest.approx(20.0)
        assert result["instrument_exact"] == pytest.approx(1.0)
        assert result["offset_multi"]["f1"] == pytest.approx(1.0)

    def test_missing_estimates_are_zero(self):
        result = note_metrics([_note(60, 1.0, 1.5)], [])
        assert result["onset_pitch"]["f1"] == 0.0
        assert result["estimated_notes"] == 0


class TestChordMetrics:
    def test_perfect_frame_accuracy(self):
        ref = [
            GTChord(0.0, 2.0, "C:maj"),
            GTChord(2.0, 4.0, "G:maj"),
        ]
        result = chord_frame_accuracy(ref, ref)
        assert result["frame_accuracy"] == pytest.approx(1.0)

    def test_shifted_chords_lower_accuracy(self):
        ref = [GTChord(0.0, 2.0, "C:maj")]
        est = [GTChord(0.0, 2.0, "G:maj")]
        result = chord_frame_accuracy(ref, est)
        assert result["frame_accuracy"] == pytest.approx(0.0)

    def test_event_prf(self):
        ref = [GTChord(0.0, 2.0, "C:maj")]
        est = [GTChord(0.1, 1.9, "C:maj")]
        assert chord_event_prf(ref, est).f1 == pytest.approx(1.0)

    def test_ece_penalises_overconfidence(self):
        ref = [GTChord(0.0, 2.0, "C:maj")]
        est = [GTChord(0.0, 2.0, "G:maj", confidence=1.0)]
        result = calibration_metrics(ref, est)
        assert result["ece"] is not None
        assert result["ece"] > 0.5

    def test_ece_zero_when_correct_and_confident(self):
        ref = [GTChord(0.0, 2.0, "C:maj")]
        est = [GTChord(0.0, 2.0, "C:maj", confidence=1.0)]
        result = calibration_metrics(ref, est)
        assert result["ece"] == pytest.approx(0.0, abs=1e-9)


class TestVerdict:
    def test_pass(self):
        verdict = compute_verdict(
            VerdictInput(
                completed=True,
                error=None,
                has_chords=True,
                mean_chord_confidence=0.8,
                expects_notes=True,
                has_notes=True,
                mean_note_confidence=0.8,
            )
        )
        assert verdict == "pass"

    def test_low_confidence_warns(self):
        verdict = compute_verdict(
            VerdictInput(
                completed=True,
                error=None,
                has_chords=True,
                mean_chord_confidence=0.4,
                expects_notes=False,
                has_notes=False,
                mean_note_confidence=None,
            )
        )
        assert verdict == "warn"

    def test_missing_chords_fails(self):
        verdict = compute_verdict(
            VerdictInput(
                completed=True,
                error=None,
                has_chords=False,
                mean_chord_confidence=None,
                expects_notes=False,
                has_notes=False,
                mean_note_confidence=None,
            )
        )
        assert verdict == "fail"

    def test_missing_expected_notes_fails(self):
        verdict = compute_verdict(
            VerdictInput(
                completed=True,
                error=None,
                has_chords=True,
                mean_chord_confidence=0.9,
                expects_notes=True,
                has_notes=False,
                mean_note_confidence=None,
            )
        )
        assert verdict == "fail"

    def test_track_error_fails(self):
        verdict = compute_verdict(
            VerdictInput(
                completed=False,
                error="boom",
                has_chords=True,
                mean_chord_confidence=1.0,
                expects_notes=False,
                has_notes=False,
                mean_note_confidence=None,
            )
        )
        assert verdict == "fail"

    def test_verdict_matches(self):
        assert verdict_matches("pass", "pass") is True
        assert verdict_matches("warn", "pass") is False
        assert verdict_matches(None, "pass") is None


class TestReportDeterminism:
    def test_json_serialization_is_stable(self):
        payload = {"b": 2, "a": 1}
        first = json.dumps(payload, indent=2, sort_keys=True)
        second = json.dumps(payload, indent=2, sort_keys=True)
        assert first == second


class TestComparisonReport:
    def test_renders_every_tier(self):
        comparison = {
            "manifest_id": "unit",
            "tiers": {
                "chroma": {
                    "aggregates": {
                        "tracks": 2,
                        "chord_frame_accuracy": 0.5,
                        "ece": 0.2,
                        "runtime_ms_mean": 10.0,
                        "notes": {"onset_multi": {"f1": 0.0}, "offset_multi": {"f1": 0.0}},
                    },
                    "verdicts": {"warn": 2},
                    "failures": [],
                },
                "full": {
                    "aggregates": {
                        "tracks": 2,
                        "chord_frame_accuracy": 0.7,
                        "ece": 0.1,
                        "runtime_ms_mean": 100.0,
                        "notes": {
                            "onset_multi": {"f1": 0.5},
                            "offset_multi": {"f1": 0.4},
                        },
                    },
                    "verdicts": {"pass": 2},
                    "failures": [],
                },
            },
        }
        markdown = render_comparison_markdown(comparison)
        assert "| chroma |" in markdown
        assert "| full |" in markdown
        assert "unit" in markdown


class TestTrackEvaluation:
    def _spec(self):
        from app.evaluation.manifest import TrackSpec

        return TrackSpec(
            id="t1",
            audio_path="audio.wav",
            gt_format="chord_timeline",
            chord_gt_path="timeline.json",
            source="unit",
            expects_notes=True,
        )

    def test_chord_only_tier_is_not_failed_for_missing_solo(self):
        from app.evaluation.ground_truth import GroundTruth
        from app.evaluation.report import Prediction, evaluate_track

        result = evaluate_track(
            self._spec(),
            Prediction(
                chords=[GTChord(0.0, 1.0, "C:maj", confidence=0.8)],
                tier="chroma",
            ),
            GroundTruth(chords=[GTChord(0.0, 1.0, "C:maj")]),
        )
        assert result.verdict != "fail"

    def test_full_tier_without_solo_fails_when_notes_expected(self):
        from app.evaluation.ground_truth import GroundTruth
        from app.evaluation.report import Prediction, evaluate_track

        result = evaluate_track(
            self._spec(),
            Prediction(
                chords=[GTChord(0.0, 1.0, "C:maj", confidence=0.8)],
                tier="full",
            ),
            GroundTruth(chords=[GTChord(0.0, 1.0, "C:maj")]),
        )
        assert result.verdict == "fail"


class TestQualitativeEvaluation:
    def _manifest(self):
        from app.evaluation.manifest import EvalManifest, TrackSpec

        spec = TrackSpec(
            id="external:ood:kora",
            audio_path="audio.wav",
            gt_format="none",
            source="external",
            qualitative=True,
        )
        return EvalManifest(manifest_id="external", tracks=[spec])

    def test_qualitative_track_is_unscored(self):
        from app.evaluation.ground_truth import GroundTruth
        from app.evaluation.report import Prediction, evaluate_track

        manifest = self._manifest()
        result = evaluate_track(
            manifest.tracks[0],
            Prediction(
                notes=[GTNote(60, 1.0, 1.5)],
                chords=[GTChord(1.0, 1.5, "C:maj", confidence=0.9)],
                tier="full",
            ),
            GroundTruth(),
        )
        assert result.verdict is None
        assert result.metrics == {}

    def test_qualitative_failure_is_still_fail(self):
        from app.evaluation.ground_truth import GroundTruth
        from app.evaluation.report import Prediction, evaluate_track

        manifest = self._manifest()
        result = evaluate_track(
            manifest.tracks[0],
            Prediction(completed=False, error="crash", tier="full"),
            GroundTruth(),
        )
        assert result.verdict == "fail"

    def test_report_counts_unscored(self):
        from app.evaluation.ground_truth import GroundTruth
        from app.evaluation.report import Prediction, build_report, evaluate_track

        manifest = self._manifest()
        result = evaluate_track(
            manifest.tracks[0],
            Prediction(tier="full"),
            GroundTruth(),
        )
        report = build_report(manifest, "full", [result])
        assert report["verdicts"]["unscored"] == 1
        assert report["tracks"][0]["qualitative"] is True
