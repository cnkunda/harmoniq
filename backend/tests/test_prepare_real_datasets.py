"""prepare_real_datasets.py unit tests (Commit 101) — no audio, no TF."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_real_datasets import (  # noqa: E402
    MIN_USABLE_FRAMES,
    PROCESSED_DIR,
    sanitize_track_id,
)


def test_sanitize_track_id_keeps_safe_chars():
    assert sanitize_track_id("00_Rock1-90-C#") == "00_Rock1-90-C_"
    assert sanitize_track_id("beatles-come-together") == "beatles-come-together"
    assert sanitize_track_id("a b.c") == "a_b_c"


def test_manifest_rebuild_is_crash_safe(tmp_path, monkeypatch):
    monkeypatch.setattr("prepare_real_datasets.PROCESSED_DIR", tmp_path)
    (tmp_path / "ok.meta.json").write_text(
        json.dumps({"track_id": "stale", "n_usable": 100, "gate_ok": True})
    )
    (tmp_path / "corrupt.meta.json").write_text("{not json")
    (tmp_path / "fine.meta.json").write_text(
        json.dumps({"track_id": "x", "n_usable": 50, "gate_ok": False})
    )
    from prepare_real_datasets import rebuild_manifest

    entries = rebuild_manifest()
    assert len(entries) == 2
    # canonical id comes from the filename, not the stale sidecar content
    ids = {e["track_id"] for e in entries}
    assert ids == {"ok", "fine"}


def _fake_tracks(n_artists=6, per_artist=2):
    return [
        {
            "track_id": f"p{i:02d}_t{j}",
            "artist": f"p{i:02d}",
            "source": "guitarset",
            "gate_ok": True,
        }
        for i in range(n_artists)
        for j in range(per_artist)
    ]


def test_split_policy_is_artist_exclusive(tmp_path, monkeypatch):
    from prepare_real_datasets import assign_splits

    tracks = _fake_tracks()
    assigned = assign_splits(tracks)
    artist_split = {}
    for track in tracks:
        split = assigned[track["track_id"]]["split"]
        artist = track["artist"]
        if artist in artist_split:
            assert artist_split[artist] == split, "artist leaked across splits"
        artist_split[artist] = split


def test_split_policy_deterministic(tmp_path, monkeypatch):
    from prepare_real_datasets import assign_splits

    tracks = [
        {"track_id": f"t{i}", "artist": f"a{i % 4}", "source": "guitarset", "gate_ok": True}
        for i in range(40)
    ]
    assert assign_splits(tracks) == assign_splits(tracks)