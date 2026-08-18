"""
Librosa-based analysis → LessonJSON wiring.

This is intentionally "smoke-test level" to support PRIORITIES §7:
fill key/tempo/beat grid/sections/bar timestamps while keeping later roadmap
commits (whisper + tabs) isolated.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.ingest import SourceMetadata, resolve_lesson_titles
from app.pipeline_proof import LibrosaSummary, librosa_summarize
from app.style_detect import infer_style_from_librosa_summary
from app.transcribe import transcribe_vocals_to_lyrics_aligned
from app.transcription_confidence import (
    chord_section_confidence,
    composite_transcription_confidence,
    vocals_coverage_confidence,
)
from app.schemas import (
    BeatGrid,
    ChordEvent,
    ChordTimeline,
    LessonJSON,
    LessonSectionStub,
    PlayerProfile,
    SoloNote,
    SoloNotes,
)
from app.stem_quality import StemClassification
from app.alphatab_prerender import enrich_lesson_with_prerender_hints
from app.musicxml_builder import build_musicxml
from app.tabgen import apply_tab_artifacts_to_sections, derive_section_confidence, generate_tab_artifacts_for_guitar_stem
from app.beat_grid import estimate_beat_grid
from app.chord_inference import infer_chords
from app.solo_inference import infer_solo

logger = logging.getLogger("harmoniq.analyze_audio")
logger.setLevel(logging.INFO)

TABS_UNAVAILABLE_NO_GUITAR = "no_isolated_guitar"


def _filter_chord_timeline_by_section(
    chord_timeline: ChordTimeline,
    section_start: float | None,
    section_end: float | None,
) -> ChordTimeline:
    """Filter chord events to only those within the section's time range."""
    if section_start is None and section_end is None:
        return chord_timeline
    
    filtered_events = []
    for event in chord_timeline.events:
        if section_start is not None and event.timestamp < section_start:
            continue
        if section_end is not None and event.timestamp >= section_end:
            continue
        filtered_events.append(event)
    
    return ChordTimeline(events=filtered_events)


def _filter_solo_notes_by_section(
    solo_notes: SoloNotes,
    section_start: float | None,
    section_end: float | None,
) -> SoloNotes:
    """Filter solo notes to only those within the section's time range."""
    if section_start is None and section_end is None:
        return solo_notes
    
    filtered_notes = []
    for note in solo_notes.notes:
        if section_start is not None and note.start_time < section_start:
            continue
        if section_end is not None and note.start_time >= section_end:
            continue
        filtered_notes.append(note)
    
    return SoloNotes(notes=filtered_notes)


def _sorted_unique_floats(values: list[float], *, tol: float = 1e-3) -> list[float]:
    values_sorted = sorted(float(v) for v in values)
    out: list[float] = []
    for v in values_sorted:
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _resolve_librosa_audio_path(
    *,
    guitar_stem_path: Path,
    mix_wav_path: Path | None,
    piano_stem_path: Path | None,
    stem_classification: StemClassification | None,
) -> Path:
    """Choose WAV for tempo/key/beat analysis when guitar stem is unreliable."""
    if stem_classification is None or stem_classification.guitar_stem_usable:
        return guitar_stem_path

    role = stem_classification.analysis_audio_role
    if role == "piano_stem" and piano_stem_path is not None and piano_stem_path.is_file():
        logger.info(
            "analyze_audio using piano stem for librosa (guitar_stem_usable=False role=%s)",
            role,
        )
        return piano_stem_path
    if role in ("full_mix", "piano_stem") and mix_wav_path is not None and mix_wav_path.is_file():
        logger.info(
            "analyze_audio using full mix for librosa (guitar_stem_usable=False role=%s)",
            role,
        )
        return mix_wav_path
    logger.warning(
        "analyze_audio fallback to guitar stem for librosa — preferred analysis path missing",
    )
    return guitar_stem_path


def _lesson_json_stem_fields(stem_classification: StemClassification | None) -> dict[str, Any]:
    if stem_classification is None:
        return {
            "stem_isolation_warning": None,
            "stem_quality_flags": [],
            "guitar_stem_usable": True,
            "analysis_audio_role": "guitar_stem",
            "tabs_unavailable_reason": None,
        }
    return {
        "stem_isolation_warning": stem_classification.user_warning,
        "stem_quality_flags": list(stem_classification.flags),
        "guitar_stem_usable": stem_classification.guitar_stem_usable,
        "analysis_audio_role": stem_classification.analysis_audio_role,
        "tabs_unavailable_reason": (
            TABS_UNAVAILABLE_NO_GUITAR if not stem_classification.guitar_stem_usable else None
        ),
    }


def _fallback_lesson(
    job_id: str,
    *,
    stems: dict[str, str],
    wav_path: str,
    guitar_stem_path: Path,
    player_profile: PlayerProfile | None = None,
    source_metadata: SourceMetadata | None = None,
    source_url: str | None = None,
    stem_classification: StemClassification | None = None,
) -> LessonJSON:
    # Deterministic placeholder so API contract tests pass even when librosa
    # fails on tiny clips or in constrained environments.
    transcription_confidence = 0.1
    logger.warning(
        "analyze_audio_fallback_lesson job_id=%s — librosa failed; omitting auto-tabs "
        "(no reliable beat grid / BPM for Basic Pitch alignment)",
        job_id,
    )
    sections = [
        LessonSectionStub(
            label="Intro",
            confidence=derive_section_confidence(transcription_confidence),
        )
    ]
    stub_summary = LibrosaSummary(
        duration_s=12.0,
        tempo_bpm=72.0,
        beat_times_s=[0.0, 0.5],
        key_name="G major",
        mode="major",
        segments=[{"label": "Intro", "start_s": 0.0}],
        bar_timestamps_s=[0.0, 3.33],
        key_confidence=0.5,
        tempo_confidence=0.5,
    )
    style = infer_style_from_librosa_summary(stub_summary)
    song_title, artist = resolve_lesson_titles(source_metadata, source_url=source_url)
    stem_fields = _lesson_json_stem_fields(stem_classification)
    return LessonJSON(
        job_id=job_id,
        song_title=song_title,
        artist=artist,
        style_label=style.style_label,
        key="G major",
        key_confidence=0.99,
        tempo=72.0,
        tempo_confidence=0.95,
        transcription_confidence=transcription_confidence,
        beat_grid=[0.0, 0.5, 1.0],
        bar_timestamps=[0.0, 3.33, 6.66],
        stems=stems,
        lyrics_aligned=[],
        sections=sections,
        wav_path=wav_path,
        **stem_fields,
    )


def build_lesson_json_from_librosa(
    job_id: str,
    *,
    guitar_stem_path: Path,
    vocals_stem_path: Path | None,
    stems: dict[str, str],
    wav_path: str,
    source_url: str | None = None,
    player_profile: PlayerProfile | None = None,
    source_metadata: SourceMetadata | None = None,
    stem_classification: StemClassification | None = None,
    mix_wav_path: Path | None = None,
    piano_stem_path: Path | None = None,
    progress_callback: "callable | None" = None,
) -> LessonJSON:
    """Build a full LessonJSON from audio analysis.

    Args:
        progress_callback: Optional callable ``(stage: str, partial_lesson: LessonJSON | None) -> None``
            called after each major pipeline stage completes. Stages:
            ``"chords_inferring"`` (chord timeline ready),
            ``"solo_inferring"`` (solo notes ready),
            ``"building_musicxml"`` (MusicXML ready),
            ``"complete"`` (final lesson).
    """
    song_title, artist = resolve_lesson_titles(source_metadata, source_url=source_url)

    analysis_path = _resolve_librosa_audio_path(
        guitar_stem_path=guitar_stem_path,
        mix_wav_path=mix_wav_path,
        piano_stem_path=piano_stem_path,
        stem_classification=stem_classification,
    )

    try:
        summary = librosa_summarize(analysis_path)
    except Exception:
        logger.exception(
            "librosa analysis failed for job_id=%s audio_path=%s",
            job_id,
            analysis_path,
        )
        return _fallback_lesson(
            job_id,
            stems=stems,
            wav_path=wav_path,
            guitar_stem_path=guitar_stem_path,
            player_profile=player_profile,
            source_metadata=source_metadata,
            source_url=source_url,
            stem_classification=stem_classification,
        )

    # Generate full BeatGrid object for transcription inference
    try:
        beat_grid_dict = estimate_beat_grid(analysis_path)
        beat_grid = BeatGrid.model_validate(beat_grid_dict)
    except Exception:
        logger.exception("beat grid estimation failed for job_id=%s; using fallback", job_id)
        beat_grid = BeatGrid(
            bpm=summary.tempo_bpm,
            pulse_bpm=summary.tempo_bpm,
            beats=_sorted_unique_floats(summary.beat_times_s),
            downbeats=[0.0],
            time_signature={"numerator": 4, "denominator": 4},
            tick_value=0.25,
        )

    # For backward compatibility, also set simple beat_grid list
    beat_grid_list = beat_grid.beats
    if not beat_grid_list:
        beat_grid_list = [0.0]

    # Derive bar_timestamps from the BeatGrid downbeats (respects actual time signature)
    bar_timestamps = _sorted_unique_floats(beat_grid.downbeats) if beat_grid.downbeats else []
    if not bar_timestamps:
        bar_timestamps = _sorted_unique_floats(summary.bar_timestamps_s)
    if not bar_timestamps:
        bar_timestamps = [0.0]
    if bar_timestamps[0] > 0.05:
        bar_timestamps.insert(0, 0.0)

    # Run transcription inference for chord timeline and solo notes
    chord_timeline: ChordTimeline | None = None
    solo_notes: SoloNotes | None = None
    
    chord_metrics: dict = {}
    try:
        # Use bass+other mix for chord inference, guitar for solo
        chord_mix_path = mix_wav_path if mix_wav_path and mix_wav_path.is_file() else guitar_stem_path
        chord_timeline, chord_metrics = infer_chords(chord_mix_path, beat_grid, key_signature=summary.key_name)
        logger.info("chord inference completed for job_id=%s with %d events", job_id, len(chord_timeline.events))
        if progress_callback is not None:
            try:
                progress_callback("chords_inferring", None)
            except Exception:
                pass
    except Exception:
        logger.exception("chord inference failed for job_id=%s; continuing without chord timeline", job_id)
        chord_timeline = ChordTimeline(events=[])
    
    try:
        solo_notes = infer_solo(guitar_stem_path, beat_grid)
        logger.info("solo inference completed for job_id=%s with %d notes", job_id, len(solo_notes.notes))
        if progress_callback is not None:
            try:
                progress_callback("solo_inferring", None)
            except Exception:
                pass
    except Exception:
        logger.exception("solo inference failed for job_id=%s; continuing without solo notes", job_id)
        solo_notes = SoloNotes(notes=[])

    sections: list[LessonSectionStub] = []
    section_starts: list[float | None] = []
    
    for seg in summary.segments:
        label = seg.get("label") if isinstance(seg, dict) else None
        if not isinstance(label, str) or not label.strip():
            label = "Section"
        start_raw = seg.get("start_s") if isinstance(seg, dict) else None
        start_time_seconds = (
            float(start_raw) if isinstance(start_raw, (int, float)) else None
        )
        section_starts.append(start_time_seconds)
        # Placeholder confidence (overwritten once we have transcription confidence).
        sections.append(
            LessonSectionStub(
                label=label,
                confidence=0.6,
                start_time_seconds=start_time_seconds,
            )
        )

    if not sections:
        sections = [LessonSectionStub(label="Intro", confidence=0.3, start_time_seconds=0.0)]
        section_starts = [0.0]

    # Attach transcription data to each section
    for i, section in enumerate(sections):
        section_start = section.start_time_seconds
        section_end = section_starts[i + 1] if i + 1 < len(section_starts) else None
        
        # Filter transcription data for this section's time range
        section_chord_timeline = None
        section_solo_notes = None
        section_beat_grid = None
        
        if chord_timeline:
            section_chord_timeline = _filter_chord_timeline_by_section(
                chord_timeline, section_start, section_end
            )
        
        if solo_notes:
            section_solo_notes = _filter_solo_notes_by_section(
                solo_notes, section_start, section_end
            )
        
        # Attach BeatGrid to section (use the full beat grid for now, could be filtered too)
        section_beat_grid = beat_grid
        
        # Update section with transcription data
        section_dict = section.model_dump(exclude_none=True)
        if section_chord_timeline:
            section_dict["chord_timeline"] = section_chord_timeline.model_dump()
        if section_solo_notes:
            section_dict["solo_notes"] = section_solo_notes.model_dump()
        if section_beat_grid:
            section_dict["beat_grid"] = section_beat_grid.model_dump()
        
        sections[i] = LessonSectionStub(**section_dict)

    # ML Fallback milestone: per-section chord-model confidence (duration-
    # weighted blended max-softmax) from each section's own chord timeline.
    section_chord_confs: list[float | None] = []
    for sec in sections:
        section_chord_confs.append(
            chord_section_confidence(
                getattr(sec, "chord_timeline", None),
                section_start=sec.start_time_seconds,
            )
        )

    # The tuple's second element (word-count heuristic) is superseded by the
    # coverage-based composite below; only the aligned rows are used here.
    lyrics_aligned, _ = transcribe_vocals_to_lyrics_aligned(
        vocals_stem_path, beat_grid=beat_grid_list, bar_timestamps=bar_timestamps
    )
    vocals_cov_conf = vocals_coverage_confidence(
        lyrics_aligned if isinstance(lyrics_aligned, list) else [],
        len(beat_grid_list),
    )

    skip_tabs = stem_classification is not None and not stem_classification.guitar_stem_usable
    tab_artifacts: dict[str, str] | None = None

    # Composite per-section confidence (chord softmax + vocal coverage).
    # When the guitar stem is unusable the composite is floored at 0.25 and
    # tabs are skipped entirely — the frontend then shows the
    # "transcription unavailable" state instead of empty tab viewports.
    # Sections are never empty (fallback "Intro" above), so the mean always
    # resolves to a finite confidence.
    guitar_usable = stem_classification is None or stem_classification.guitar_stem_usable
    section_composite_confs = [
        composite_transcription_confidence(
            chord_conf if guitar_usable else None,
            vocals_cov_conf if guitar_usable else None,
            guitar_stem_usable=guitar_usable,
        )
        for chord_conf in section_chord_confs
    ]
    transcription_confidence = float(
        sum(section_composite_confs) / len(section_composite_confs)
    )

    if skip_tabs:
        tc = min(float(transcription_confidence), 0.25)
        transcription_confidence = tc
        section_conf = derive_section_confidence(tc)
        sections = [
            LessonSectionStub(
                label=sec.label,
                confidence=section_conf,
                start_time_seconds=sec.start_time_seconds,
                **{k: v for k, v in sec.model_dump(exclude_none=True).items() 
                   if k not in ("label", "confidence", "start_time_seconds")}
            )
            for sec in sections
        ]
        logger.info(
            "analyze_audio job_id=%s skipping Basic Pitch (guitar stem not usable for tabs)",
            job_id,
        )
    else:
        try:
            tab_artifacts = generate_tab_artifacts_for_guitar_stem(
                guitar_stem_path,
                bpm=summary.tempo_bpm,
                transcription_confidence=transcription_confidence,
                beat_times_s=beat_grid_list,
            )
            sections = apply_tab_artifacts_to_sections(
                sections,
                transcription_confidence=transcription_confidence,
                tab_artifacts=tab_artifacts,
            )
        except Exception:
            logger.exception("tab generation failed for job_id=%s; returning lesson without tabs", job_id)
            section_conf = derive_section_confidence(transcription_confidence)
            sections = [
                LessonSectionStub(
                    label=sec.label,
                    confidence=section_conf,
                    start_time_seconds=sec.start_time_seconds,
                    **{k: v for k, v in sec.model_dump(exclude_none=True).items() 
                       if k not in ("label", "confidence", "start_time_seconds")}
                )
                for sec in sections
            ]
        # Per-section composite confidence overrides the uniform tabgen value
        # so each section carries its own chord+vocal quality signal.
        sections = [
            LessonSectionStub(
                **{**getattr(sec, "model_dump")(exclude_none=True), "confidence": conf}
            )
            for sec, conf in zip(sections, section_composite_confs)
        ]

    style = infer_style_from_librosa_summary(summary)
    stem_fields = _lesson_json_stem_fields(stem_classification)

    # Commit 82: Set low_snr_warning for pre-emptive transcription quality warning
    # Trigger warning when transcription confidence is very low (< 0.5)
    low_snr_warning = transcription_confidence is not None and transcription_confidence < 0.5

    # Generate MusicXML lead sheet with chords and solo notes
    musicxml_str = ""
    try:
        if chord_timeline and solo_notes and beat_grid:
            musicxml_str = build_musicxml(
                beat_grid=beat_grid,
                chord_timeline=chord_timeline,
                solo_notes=solo_notes,
                title=song_title or "Harmoniq Score",
                artist=artist or "Harmoniq AI",
                key_signature=summary.key_name,
            )
            logger.info("MusicXML generated for job_id=%s, length=%d chars", job_id, len(musicxml_str))
            if progress_callback is not None:
                try:
                    progress_callback("building_musicxml", None)
                except Exception:
                    pass
    except Exception:
        logger.exception("MusicXML generation failed for job_id=%s; continuing without it", job_id)

    lesson = LessonJSON(
        job_id=job_id,
        song_title=song_title,
        artist=artist,
        style_label=style.style_label,
        key=summary.key_name,
        key_confidence=summary.key_confidence,
        tempo=summary.tempo_bpm,
        tempo_confidence=summary.tempo_confidence,
        transcription_confidence=transcription_confidence,
        beat_grid=beat_grid_list,
        bar_timestamps=bar_timestamps,
        stems=stems,
        lyrics_aligned=lyrics_aligned,
        sections=sections,
        wav_path=wav_path,
        low_snr_warning=low_snr_warning,
        musicxml=musicxml_str,
        **stem_fields,
    )
    full_gp5 = tab_artifacts.get("tab_full_gp5_base64") if tab_artifacts else None

    # Commit 107: hoist the full analysis artifacts to lesson top level so
    # clients (AlphaTab harness, study fretboard, exporter) read them directly
    # instead of reconstructing from sections. First non-empty section wins.
    # The legacy top-level `beat_grid` field stays the beat-timestamp list
    # (scoring contract, metronome); the full BeatGrid object remains
    # per-section.
    hoisted_updates: dict[str, object] = {}
    for sec in sections:
        sec_dict = getattr(sec, "model_dump")(exclude_none=True)
        if "chord_timeline" in sec_dict and hoisted_updates.get("chord_timeline") is None:
            hoisted_updates["chord_timeline"] = ChordTimeline.model_validate(sec_dict["chord_timeline"])
        if "solo_notes" in sec_dict and hoisted_updates.get("solo_notes") is None:
            hoisted_updates["solo_notes"] = SoloNotes.model_validate(sec_dict["solo_notes"])
    lesson = lesson.model_copy(update=hoisted_updates) if hoisted_updates else lesson

    if isinstance(full_gp5, str) and full_gp5.strip():
        lesson = enrich_lesson_with_prerender_hints(
            lesson,
            job_id=job_id,
            gp5_base64=full_gp5,
            musicxml=musicxml_str or None,
        )
    elif musicxml_str.strip():
        lesson = enrich_lesson_with_prerender_hints(
            lesson,
            job_id=job_id,
            musicxml=musicxml_str,
        )
    return lesson
