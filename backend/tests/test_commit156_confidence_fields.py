"""Commit 156: confidence exposure — schema fields, API presence, compat, dead-export gate."""

from __future__ import annotations

import ast
import math
from pathlib import Path

from fastapi.testclient import TestClient

from app.confidence_thresholds import (
    confidence_band,
    hedge_tier,
    normalize_confusion,
)
from app.instrument_confusion import heuristic_mt3_section_confusion
from app.jobs import jobs
from app.main import app
from app.schemas import JobStatus, LessonJSON, LessonSectionStub
from app.transcription_confidence import (
    EVALUATION_ONLY,
    composite_transcription_confidence,
)

client = TestClient(app)


class TestThresholdHelpers:
    def test_hedge_tier_boundaries(self):
        assert hedge_tier(None) == "none"
        assert hedge_tier(0.0) == "none"
        assert hedge_tier(0.2999) == "none"
        assert hedge_tier(0.3) == "soft"
        assert hedge_tier(0.5999) == "soft"
        assert hedge_tier(0.6) == "strong"
        assert hedge_tier(1.0) == "strong"

    def test_normalize_clamps_and_nans(self):
        assert normalize_confusion(-0.1) == 0.0
        assert normalize_confusion(1.5) == 1.0
        assert normalize_confusion(math.nan) is None
        assert normalize_confusion(None) is None
        assert normalize_confusion("0.5") is None

    def test_confidence_band_cutoffs(self):
        assert confidence_band(None) is None
        assert confidence_band(math.nan) is None
        assert confidence_band(0.1) == "low"
        assert confidence_band(0.4999) == "low"
        assert confidence_band(0.5) == "medium"
        assert confidence_band(0.7499) == "medium"
        assert confidence_band(0.75) == "high"
        assert confidence_band(0.95) == "high"


class TestLessonFields:
    def test_new_fields_round_trip(self):
        lesson = LessonJSON(
            job_id="job-1",
            transcription_confidence=0.82,
            confidence_band="high",
            instrument_confusion=0.1,
            sections=[
                LessonSectionStub(
                    label="Verse",
                    instrument_confusion=0.5,
                    leakage_risk=0.5,
                    chord_confidence=0.9,
                )
            ],
        )
        dumped = lesson.model_dump(mode="json")
        assert dumped["confidence_band"] == "high"
        assert dumped["sections"][0]["instrument_confusion"] == 0.5
        assert dumped["sections"][0]["leakage_risk"] == 0.5
        assert dumped["sections"][0]["chord_confidence"] == 0.9

    def test_old_payload_still_validates(self):
        """Pre-156 fixture payloads (no new fields) validate with None defaults."""
        old = {
            "job_id": "job-old",
            "song_title": "Gravity",
            "transcription_confidence": 0.4,
            "sections": [{"label": "Verse", "confidence": 0.4}],
        }
        lesson = LessonJSON.model_validate(old)
        assert lesson.confidence_band is None
        assert lesson.instrument_confusion is None
        assert lesson.instrument_confusion_per_section is None
        assert lesson.sections[0].instrument_confusion is None
        assert lesson.sections[0].leakage_risk is None
        assert lesson.sections[0].chord_confidence is None

    def test_fallback_tier_produces_valid_score_and_band(self):
        """CRNN/chroma-tier results (chords only) still score and band validly."""
        value = composite_transcription_confidence(0.7, None)
        assert 0.05 <= value <= 1.0
        assert confidence_band(value) in ("low", "medium", "high")

    def test_get_job_result_contains_fields(self):
        """Catches response_model stripping: new fields must survive GET."""
        jobs.clear()
        jobs["job-156"] = JobStatus(
            status="complete",
            result=LessonJSON(
                job_id="job-156",
                transcription_confidence=0.82,
                confidence_band="high",
                instrument_confusion=0.1,
                sections=[LessonSectionStub(label="V", instrument_confusion=0.5)],
            ),
            error=None,
        )
        try:
            r = client.get("/analyze/job-156")
            assert r.status_code == 200, r.text
            result = r.json()["result"]
            assert result["transcription_confidence"] == 0.82
            assert result["confidence_band"] == "high"
            assert result["instrument_confusion"] == 0.1
            assert result["sections"][0]["instrument_confusion"] == 0.5
        finally:
            jobs.pop("job-156", None)


class TestMt3Proxy:
    def test_proxy_scores_low_confidence_share(self):
        from app.schemas import ChordEvent, ChordTimeline

        sections = [LessonSectionStub(label="V", start_time_seconds=0.0)]
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
            ChordEvent(timestamp=1.0, chord="G:maj", confidence=0.2),
            ChordEvent(timestamp=2.0, chord="N", confidence=1.0),
        ])
        scores = heuristic_mt3_section_confusion(sections, timeline)
        assert len(scores) == 1
        assert scores[0].instrument_confusion == 0.5

    def test_proxy_skips_empty_sections(self):
        from app.schemas import ChordEvent, ChordTimeline

        sections = [LessonSectionStub(label="V", start_time_seconds=99.0)]
        timeline = ChordTimeline(events=[
            ChordEvent(timestamp=0.0, chord="C:maj", confidence=0.9),
        ])
        assert heuristic_mt3_section_confusion(sections, timeline) == []
        assert heuristic_mt3_section_confusion(sections, None) == []


class TestNoDeadExports:
    def test_every_public_name_is_wired_or_declared_eval_only(self):
        """AST gate: each public name in transcription_confidence.py must be
        referenced by non-test code under app/ or listed in EVALUATION_ONLY."""
        module_path = Path(__file__).resolve().parent.parent / "app" / "transcription_confidence.py"
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        public = sorted({
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith("_")
        } | {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id.isupper()
            and node.id != "EVALUATION_ONLY"
        })
        # Collect every name referenced anywhere under app/ (excluding tests/).
        referenced: set[str] = set()
        app_root = module_path.parent
        for path in sorted(app_root.rglob("*.py")):
            if "tests" in path.parts:
                continue
            try:
                ref_tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(ref_tree):
                if isinstance(node, ast.Name):
                    referenced.add(node.id)
                elif isinstance(node, ast.Attribute):
                    referenced.add(node.attr)
        unwired = [n for n in public if n not in referenced and n not in EVALUATION_ONLY]
        assert not unwired, f"unwired transcription_confidence exports: {unwired}"
