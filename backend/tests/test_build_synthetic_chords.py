"""Tests for the synthetic guitar chord corpus builder."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_vocab_170 import CHORD_TO_IDX_170  # noqa: E402
from scripts.build_synthetic_chords import (  # noqa: E402
    _hash_split,
    parse_segments,
    read_lab,
    select_balanced,
)


class TestLabParsing:
    def test_read_lab_handles_spaces_and_tabs(self, tmp_path):
        path = tmp_path / "x.lab"
        path.write_text("0 1.6 C:maj\n2.0\t3.7\tA:min\n")
        rows = read_lab(path)
        assert rows == [(0.0, 1.6, "C:maj"), (2.0, 3.7, "A:min")]

    def test_parse_segments_skips_noise_and_altered(self, tmp_path):
        root = tmp_path / "isophonics"
        root.mkdir()
        (root / "x.lab").write_text(
            "0 2.0 C:maj\n2.0 4.0 N\n4.0 6.0 F:(b3,5,b7,11)\n"
            "6.0 7.0 D:7/Gb\n7.0 7.5 G\n"
        )
        segments = parse_segments(tmp_path)
        labels = {s["label"] for s in segments}
        assert CHORD_TO_IDX_170["C:maj"] in labels
        assert CHORD_TO_IDX_170["D:7"] in labels
        assert len(segments) == 3
        slash = [s for s in segments if s["label"] == CHORD_TO_IDX_170["D:7"]][0]
        assert slash["bass"] == 6


class TestSelection:
    def test_caps_are_respected(self):
        segments = []
        for index in range(200):
            segments.append({"label": index % 10, "bass": index % 3,
                             "duration": 2.0, "source": "x",
                             "track": str(index), "start": 0.0})
        selected = select_balanced(segments, limit=30, seed=0)
        assert len(selected) == 30
        counts = {}
        for segment in selected:
            counts[segment["label"]] = counts.get(segment["label"], 0) + 1
        assert max(counts.values()) <= max(20, int(np.ceil(30 / 120)))

    def test_short_segments_are_skipped(self):
        segments = [{"label": 0, "bass": 0, "duration": 1.0,
                     "source": "x", "track": "a", "start": 0.0}]
        assert select_balanced(segments, limit=10) == []


class TestSplit:
    def test_hash_split_is_deterministic(self):
        values = {_hash_split(f"synthetic_{i:06d}") for i in range(50)}
        assert values <= {"train", "val", "test"}
        assert _hash_split("synthetic_000001") == _hash_split("synthetic_000001")
