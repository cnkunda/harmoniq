from __future__ import annotations

from app import jobs
from app.coach import merge_coach_copy_into_sections


def test_stub_lesson_enriched_with_coach_fields():
    """D3: no-guitar stub path must populate coach_note / coach_explanation like the full pipeline."""
    stub = jobs._stub_lesson(
        "job-d3",
        None,
        wav_path="jobs/x/song.wav",
        stems={"drums": "jobs/x/stems/d.wav"},
        source_metadata={"song_title": "Stub Song", "artist": "Artist"},
    )
    assert stub.sections
    sec0 = stub.sections[0].model_dump()
    assert "coach_note" not in sec0 or not str(sec0.get("coach_note") or "").strip()

    enriched = merge_coach_copy_into_sections(
        list(stub.sections),
        song_title=stub.song_title,
        artist=stub.artist,
        key=stub.key,
        player_profile=None,
        style_label=stub.style_label,
        technique_hints=[],
    )
    assert len(enriched) == 1
    out = enriched[0].model_dump()
    assert isinstance(out.get("coach_note"), str)
    assert out["coach_note"].strip()
    assert isinstance(out.get("coach_explanation"), str)
    assert out["coach_explanation"].strip()
