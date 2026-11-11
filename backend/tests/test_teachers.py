"""W2 teacher framework, leakage, sample, and decision tests."""

from __future__ import annotations

import json

import pytest

from app.mt3.schemas import Mt3Event
from app.teachers.events import (
    TeacherNote,
    events_to_notes,
    notes_to_event_stream,
)
from app.teachers.leakage import aggregate_leakage, leakage_report


class TestEventConversion:
    def test_pairs_onset_and_offset(self):
        events = [
            Mt3Event(time=1.0, pitch=60, program=24, is_onset=True, confidence=0.8),
            Mt3Event(
                time=2.0,
                pitch=60,
                program=24,
                is_onset=False,
                is_offset=True,
                confidence=0.8,
            ),
        ]
        notes = events_to_notes(events, audio_duration=3.0)
        assert len(notes) == 1
        assert notes[0].pitch == 60
        assert notes[0].onset == 1.0
        assert notes[0].offset == 2.0
        assert notes[0].program == 24

    def test_unmatched_onset_is_closed(self):
        events = [
            Mt3Event(time=1.0, pitch=64, program=24, is_onset=True, confidence=0.7)
        ]
        notes = events_to_notes(events, audio_duration=4.0)
        assert notes[0].offset == 4.0

    def test_repeated_onset_closes_previous(self):
        events = [
            Mt3Event(time=1.0, pitch=60, program=24, is_onset=True),
            Mt3Event(time=1.5, pitch=60, program=24, is_onset=True),
            Mt3Event(time=2.0, pitch=60, program=24, is_onset=False, is_offset=True),
        ]
        notes = events_to_notes(events, audio_duration=3.0)
        assert len(notes) == 2
        assert notes[0].offset == 1.5

    def test_notes_to_event_stream_roundtrip(self):
        notes = [
            TeacherNote(60, 1.0, 2.0, program=24),
            TeacherNote(64, 1.5, 2.5, program=0),
        ]
        stream = notes_to_event_stream(notes, audio_duration=3.0)
        assert len(stream.events) == 4
        assert stream.num_instruments == 2
        back = events_to_notes(stream.events, audio_duration=3.0)
        assert [(note.pitch, note.onset, note.offset) for note in back] == [
            (60, 1.0, 2.0),
            (64, 1.5, 2.5),
        ]


class TestLeakage:
    def test_guitar_only_is_clean(self):
        report = leakage_report(
            [TeacherNote(60, 0, 1, program=24), TeacherNote(64, 1, 2, program=31)]
        )
        assert report["leakage_rate"] == 0.0
        assert report["non_guitar_program_share"] == 0.0

    def test_non_guitar_program_and_range_count_as_leakage(self):
        notes = [
            TeacherNote(60, 0, 1, program=24),
            TeacherNote(60, 1, 2, program=0),
            TeacherNote(30, 2, 3, program=24),
            TeacherNote(90, 3, 4, program=24),
        ]
        report = leakage_report(notes)
        assert report["notes"] == 4
        assert report["non_guitar_program_notes"] == 1
        assert report["out_of_range_notes"] == 2
        assert report["leakage_notes"] == 3
        assert report["leakage_rate"] == pytest.approx(0.75)

    def test_unknown_programs_are_excluded_from_program_share(self):
        report = leakage_report(
            [
                TeacherNote(60, 0, 1, program=None),
                TeacherNote(62, 1, 2, program=24),
            ]
        )
        assert report["known_program_notes"] == 1
        assert report["non_guitar_program_share"] == 0.0

    def test_empty(self):
        report = leakage_report([])
        assert report["notes"] == 0
        assert report["leakage_rate"] is None

    def test_aggregate(self):
        reports = [
            leakage_report([TeacherNote(60, 0, 1, program=24)]),
            leakage_report([TeacherNote(60, 0, 1, program=0)]),
        ]
        aggregate = aggregate_leakage(reports)
        assert aggregate["notes"] == 2
        assert aggregate["leakage_rate"] == pytest.approx(0.5)


class TestTeacherSample:
    def _track(self, source, index, split):
        from app.evaluation.manifest import TrackSpec

        return TrackSpec(
            id=f"{source}:{index:02d}",
            audio_path=f"{source}/{index}.wav",
            gt_format="notes_json",
            gt_path=f"{source}/{index}.notes.json",
            source=source,
            split=split,
        )

    def test_selects_requested_quotas_and_prefers_test(self):
        from scripts.build_teacher_sample import select_sample

        tracks = []
        for source, total in (
            ("guitarset", 12),
            ("idmt_smt_guitar", 12),
            ("guitar_techs", 12),
            ("egset12", 6),
            ("rwc_p", 18),
        ):
            for index in range(total):
                split = "test" if index < 3 else ("val" if index < 6 else "train")
                tracks.append(self._track(source, index, split))
        selected = select_sample(
            tracks,
            quotas={
                "guitarset": 2,
                "idmt_smt_guitar": 2,
                "guitar_techs": 2,
                "egset12": 1,
                "rwc_p": 2,
            },
            total=9,
        )
        assert len(selected) == 9
        assert all(track.split == "test" for track in selected)


class TestDecision:
    def _summary(self, **overrides):
        payload = {
            "tracks": 10,
            "completed": 10,
            "chord_frame_accuracy": 0.5,
            "onset_f1": 0.5,
            "onset_pitch_f1": 0.5,
            "offset_f1": 0.4,
            "guitar_retention": 1.0,
            "leakage_rate": 0.1,
            "ece": 0.2,
            "rtf": 1.0,
            "runtime_ms_mean": 1000.0,
        }
        payload.update(overrides)
        return payload

    def test_go_when_candidate_improves_without_leakage(self):
        from scripts.compare_teachers import _decide

        decision = _decide(
            {
                "mt3": self._summary(),
                "mr_mt3": self._summary(chord_frame_accuracy=0.6, rtf=1.5),
            },
            {
                "mt3": {"available": True},
                "mr_mt3": {"available": True},
            },
            accuracy_tolerance=0.02,
            leakage_tolerance=0.02,
            max_rtf_ratio=3.0,
            min_guitar_retention=0.2,
        )
        assert decision["status"] == "go"
        assert decision["recommended_teacher"] == "mr_mt3"

    def test_no_go_without_accuracy_gain(self):
        from scripts.compare_teachers import _decide

        decision = _decide(
            {"mt3": self._summary(), "mr_mt3": self._summary()},
            {
                "mt3": {"available": True},
                "mr_mt3": {"available": True},
            },
            accuracy_tolerance=0.02,
            leakage_tolerance=0.02,
            max_rtf_ratio=3.0,
            min_guitar_retention=0.2,
        )
        assert decision["status"] == "no-go"

    def test_blocked_when_no_other_teacher_available(self):
        from scripts.compare_teachers import _decide

        decision = _decide(
            {"mt3": self._summary()},
            {
                "mt3": {"available": True},
                "mr_mt3": {"available": False},
            },
            accuracy_tolerance=0.02,
            leakage_tolerance=0.02,
            max_rtf_ratio=3.0,
            min_guitar_retention=0.2,
        )
        assert decision["status"] == "blocked"

    def test_cached_teacher_is_candidate_without_runtime(self):
        from scripts.compare_teachers import _decide

        decision = _decide(
            {
                "mt3": self._summary(),
                "mr_mt3": self._summary(chord_frame_accuracy=0.6, rtf=1.5),
            },
            {
                "mt3": {"available": True},
                "mr_mt3": {"available": False},
            },
            accuracy_tolerance=0.02,
            leakage_tolerance=0.02,
            max_rtf_ratio=3.0,
            min_guitar_retention=0.2,
        )
        assert decision["status"] == "go"
        assert decision["recommended_teacher"] == "mr_mt3"

    def test_go_requires_guitar_filter_when_leakage_is_high(self):
        from scripts.compare_teachers import _decide

        decision = _decide(
            {
                "mt3": self._summary(),
                "mr_mt3": self._summary(
                    chord_frame_accuracy=0.6,
                    onset_pitch_f1=0.8,
                    leakage_rate=0.5,
                    guitar_retention=0.4,
                ),
            },
            {
                "mt3": {"available": True},
                "mr_mt3": {"available": True},
            },
            accuracy_tolerance=0.02,
            leakage_tolerance=0.02,
            max_rtf_ratio=3.0,
            min_guitar_retention=0.2,
        )
        assert decision["status"] == "go"
        assert decision["recommended_teacher"] == "mr_mt3"
        assert decision["checks"]["mr_mt3"]["requires_guitar_filter"] is True


class TestMt3Availability:
    def _checkpoint(self, root, *, with_gin: bool = True):
        checkpoint_dir = root / "mt3_t5_small"
        checkpoint_dir.mkdir()
        (checkpoint_dir / "checkpoint").write_text("stub")
        if with_gin:
            (checkpoint_dir / "model.gin").write_text("stub")
            (checkpoint_dir / "mt3.gin").write_text("stub")

    def test_available_with_checkpoint_and_deps(self, tmp_path, monkeypatch):
        self._checkpoint(tmp_path)
        import app.mt3.model_server as model_server

        monkeypatch.setattr(model_server, "_MODEL_CACHE_DIR", tmp_path)
        from app.teachers.mt3 import Mt3Teacher

        # Must not load the JAX/T5X model server (cheap probe only).
        assert Mt3Teacher().is_available() is True

    def test_unavailable_without_checkpoint(self, tmp_path, monkeypatch):
        import app.mt3.model_server as model_server

        monkeypatch.setattr(model_server, "_MODEL_CACHE_DIR", tmp_path)
        from app.teachers.mt3 import Mt3Teacher

        assert Mt3Teacher().is_available() is False

    def test_unavailable_without_gin_configs(self, tmp_path, monkeypatch):
        self._checkpoint(tmp_path, with_gin=False)
        import app.mt3.model_server as model_server

        monkeypatch.setattr(model_server, "_MODEL_CACHE_DIR", tmp_path)
        from app.teachers.mt3 import Mt3Teacher

        assert Mt3Teacher().is_available() is False

    def test_unavailable_without_deps(self, tmp_path, monkeypatch):
        self._checkpoint(tmp_path)
        import app.mt3.model_server as model_server
        import app.teachers as teachers

        monkeypatch.setattr(model_server, "_MODEL_CACHE_DIR", tmp_path)
        monkeypatch.setattr(
            teachers.mt3,
            "_MT3_DEPS",
            ("gin", "jax", "seqio", "tensorflow", "t5x", "mt3", "no_such_pkg_wxyz"),
        )
        from app.teachers.mt3 import Mt3Teacher

        assert Mt3Teacher().is_available() is False


class TestCachedOnlyLoad:
    def _fake_teacher(self, note: TeacherNote):
        from app.teachers.events import TeacherOutput

        class FakeTeacher:
            name = "fake"

            def transcribe_many(self, paths):  # pragma: no cover - must not run
                raise AssertionError("cached-only runs must not call inference")

        return FakeTeacher(), TeacherOutput(
            notes=[note],
            latency_ms=100.0,
            model_version="fake:v1",
            metadata={"audio_duration_s": 10.0},
        )

    def test_cached_only_returns_cached_without_inference(self, tmp_path):
        from scripts.compare_teachers import _cache_path, _load_teacher_outputs

        audio_cached = tmp_path / "a.wav"
        audio_missing = tmp_path / "b.wav"
        audio_cached.write_bytes(b"stub")
        audio_missing.write_bytes(b"stub")
        teacher, output = self._fake_teacher(
            TeacherNote(pitch=60, onset=0.0, offset=1.0)
        )
        cache_dir = tmp_path / "cache"
        cache = _cache_path(cache_dir, teacher.name, audio_cached)
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps(output.as_dict()))

        got = _load_teacher_outputs(
            teacher,
            [audio_cached, audio_missing],
            cache_dir,
            refresh=False,
            cached_only=True,
        )
        assert list(got) == [audio_cached]
        assert got[audio_cached].model_version == "fake:v1"

    def test_load_without_cached_only_invokes_inference(self, tmp_path):
        import json

        from scripts.compare_teachers import _load_teacher_outputs

        audio_missing = tmp_path / "b.wav"
        audio_missing.write_bytes(b"stub")

        class FakeTeacher:
            name = "fake2"

            def transcribe_many(self, paths):
                from app.teachers.events import TeacherOutput

                return {
                    path: TeacherOutput(
                        notes=[],
                        latency_ms=1.0,
                        model_version="fake2:v1",
                        metadata={"audio_duration_s": 1.0},
                    )
                    for path in paths
                }

        teacher = FakeTeacher()
        outputs = _load_teacher_outputs(
            teacher,
            [audio_missing],
            tmp_path / "cache",
            refresh=False,
            cached_only=False,
        )
        assert audio_missing in outputs
        assert (tmp_path / "cache" / "fake2").is_dir()
