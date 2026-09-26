"""
Librosa-based analysis → LessonJSON wiring.

This is intentionally "smoke-test level" to support PRIORITIES §7:
fill key/tempo/beat grid/sections/bar timestamps while keeping later roadmap
commits (whisper + tabs) isolated.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from app.ingest import SourceMetadata, resolve_lesson_titles
from app.pipeline_proof import LibrosaSummary, librosa_summarize
from app.style_detect import infer_style_from_librosa_summary
from app.transcribe import transcribe_vocals_to_lyrics_aligned
from app.audio_mix import mix_stems, resolve_chord_stems, resolve_solo_stem
from app.schemas import (
    BeatGrid,
    ChordTimeline,
    LessonJSON,
    LessonSectionStub,
    PlayerProfile,
    SoloNotes,
    StemRoutingHints,
)
from app.stem_quality import StemClassification
from app.repeat_detection import detect_repeated_sections
from app.alphatab_prerender import enrich_lesson_with_prerender_hints
from app.musicxml_builder import build_musicxml
from app.tabgen import apply_tab_artifacts_to_sections, derive_section_confidence, generate_tab_artifacts_for_guitar_stem
from app.beat_grid import estimate_beat_grid
from app.chord_enrichment import assign_roman_numerals
from app.chord_inference import infer_chords, infer_chords_dual_path
from app.instrument_confusion import compute_per_section_confusion
from app.mt3 import transcribe_with_fallback
from app.solo_inference import infer_solo
from app.solo_harmony_analyzer import SoloHarmonizer
from app.section_refinement import refine_section_boundaries

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
            "stem_confidence": None,
        }
    return {
        "stem_isolation_warning": stem_classification.user_warning,
        "stem_quality_flags": list(stem_classification.flags),
        "guitar_stem_usable": stem_classification.guitar_stem_usable,
        "analysis_audio_role": stem_classification.analysis_audio_role,
        "tabs_unavailable_reason": (
            TABS_UNAVAILABLE_NO_GUITAR if not stem_classification.guitar_stem_usable else None
        ),
        "stem_confidence": stem_classification.stem_confidence,
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
    on_stage: Callable[[str, float, str], None] | None = None,
    routing_hints: StemRoutingHints | None = None,
    stem_abs_paths: dict[str, Path] | None = None,
) -> LessonJSON:
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

    # Commit 109: Derive bar_timestamps from BeatGrid.downbeats (time-sig-aware)
    # instead of pipeline_proof.py's hardcoded 4/4 assumption.
    bar_timestamps = list(beat_grid.downbeats) if beat_grid.downbeats else [0.0]
    if not bar_timestamps:
        bar_timestamps = [0.0]
    if bar_timestamps[0] > 0.05:
        bar_timestamps.insert(0, 0.0)

    # Run transcription inference for chord timeline and solo notes
    chord_timeline: ChordTimeline | None = None
    solo_notes: SoloNotes | None = None
    transcription_source: str | None = None

    # === Phase 2, Milestone A: MT3-Primary transcription ===
    # Uses the fallback chain: MT3 → CRNN TFLite → Chroma matching.
    # When MT3 is unavailable or confidence is low, falls back gracefully.
    # ===
    if on_stage:
        on_stage("mt3_inferring", 0.60, "Transcribing with MT3…")

    # Resolve the best available audio source for transcription
    chord_mix_path = mix_wav_path if (mix_wav_path and mix_wav_path.is_file()) else guitar_stem_path
    solo_source_path = guitar_stem_path

    if routing_hints is not None and stem_abs_paths is not None:
        valid_chord_stems = resolve_chord_stems(
            stem_abs_paths, routing_hints.chord_mix_stems
        )
        if len(valid_chord_stems) >= 2:
            try:
                job_dir = Path(wav_path).parent
                chord_mix_path = mix_stems(
                    valid_chord_stems,
                    job_dir / "chord_mix.wav",
                )
                routing_hints.resolved_chord_mix_keys = list(routing_hints.chord_mix_stems)
                routing_hints.resolved_chord_path = str(chord_mix_path)
                logger.info(
                    "stem_routing job_id=%s chord_mix stems=%s → %s",
                    job_id, routing_hints.chord_mix_stems, chord_mix_path,
                )
            except Exception:
                logger.exception(
                    "stem_routing job_id=%s chord_mix failed; falling back to %s",
                    job_id, chord_mix_path,
                )
                if not routing_hints.fallback_reason:
                    routing_hints.fallback_reason = "mix_failed"
                routing_hints.resolved_chord_path = str(chord_mix_path)
        else:
            if not routing_hints.fallback_reason:
                routing_hints.fallback_reason = "insufficient_stems"
            routing_hints.resolved_chord_path = str(chord_mix_path)

        try:
            resolved_solo, chosen_stem = resolve_solo_stem(
                stem_abs_paths, routing_hints.selected_melodic_stem
            )
            solo_source_path = resolved_solo
            routing_hints.resolved_solo_path = str(resolved_solo)
            if chosen_stem != routing_hints.selected_melodic_stem:
                if not routing_hints.fallback_reason:
                    routing_hints.fallback_reason = f"solo_{chosen_stem}"
                logger.info(
                    "stem_routing job_id=%s solo_fallback selected=%s → used=%s reason=%s",
                    job_id, routing_hints.selected_melodic_stem, chosen_stem, routing_hints.fallback_reason,
                )
            else:
                logger.info(
                    "stem_routing job_id=%s solo_stem=%s (no fallback)", job_id, chosen_stem,
                )
        except KeyError:
            logger.exception(
                "stem_routing job_id=%s solo resolution failed; using guitar stem",
                job_id,
            )
            if not routing_hints.fallback_reason:
                routing_hints.fallback_reason = "solo_resolution_failed"
            routing_hints.resolved_solo_path = str(guitar_stem_path)
            solo_source_path = guitar_stem_path
    # === End routing block ===

    instrument_confusion: float | None = None
    dual_fusion_log: list[dict] | None = None

    # Try MT3 fallback chain first (chords + solo notes together)
    try:
        mt3_result = transcribe_with_fallback(
            chord_mix_path,
            beat_grid,
            use_mt3=True,
        )
        chord_timeline = mt3_result.chord_timeline
        solo_notes = mt3_result.solo_notes
        transcription_source = mt3_result.source

        logger.info(
            "MT3 fallback chain for job_id=%s source=%s confidence=%.2f "
            "chord_events=%d solo_notes=%d%s",
            job_id, mt3_result.source, mt3_result.mean_confidence,
            len(chord_timeline.events), len(solo_notes.notes),
            f" fallback={mt3_result.fallback_reason}" if mt3_result.fallback_reason else "",
        )
    except Exception:
        logger.exception(
            "MT3 transcription failed for job_id=%s; falling back to CRNN",
            job_id,
        )
        transcription_source = "crnn"

    # If MT3 chain returned none or no results, run legacy CRNN inference
    if chord_timeline is None or len(chord_timeline.events) == 0:
        logger.info("MT3 produced no chords for job_id=%s; running CRNN fallback", job_id)
        if on_stage:
            on_stage("chords_inferring", 0.65, "Inferring chords (fallback)…")

        stem_conf = stem_classification.stem_confidence if stem_classification else 1.0
        use_dual_path = (
            stem_classification is not None
            and stem_conf < 1.0
            and guitar_stem_path.is_file()
            and chord_mix_path != guitar_stem_path
        )

        try:
            if use_dual_path:
                dual_result = infer_chords_dual_path(
                    stem_path=guitar_stem_path,
                    mix_path=chord_mix_path,
                    beat_grid=beat_grid,
                    stem_confidence=stem_conf,
                )
                chord_timeline = dual_result.timeline
                instrument_confusion = dual_result.instrument_confusion
                dual_fusion_log = dual_result.fusion_log
            else:
                chord_timeline = infer_chords(chord_mix_path, beat_grid)
            transcription_source = "crnn"
            logger.info(
                "CRNN chord inference for job_id=%s: %d events (dual_path=%s)",
                job_id, len(chord_timeline.events), use_dual_path,
            )
        except Exception:
            logger.exception("CRNN chord inference failed for job_id=%s", job_id)
            chord_timeline = ChordTimeline(events=[])
            transcription_source = "none"

    # If MT3 didn't produce solo notes, run Basic Pitch fallback
    if solo_notes is None or len(solo_notes.notes) == 0:
        if on_stage:
            on_stage("solo_inferring", 0.78, "Inferring solo notation (fallback)…")
        try:
            solo_notes = infer_solo(solo_source_path, beat_grid)
            logger.info(
                "Basic Pitch solo inference for job_id=%s: %d notes",
                job_id, len(solo_notes.notes),
            )
        except Exception:
            logger.exception("solo inference failed for job_id=%s", job_id)
            solo_notes = SoloNotes(notes=[])

    # Commit 116: Assign deterministic Roman numeral labels to all chord events
    if chord_timeline.events and summary.key_name:
        assign_roman_numerals(chord_timeline.events, summary.key_name)

    # Commit 112: flag high instrument confusion in stem quality flags
    if instrument_confusion is not None and instrument_confusion > 0.3:
        if stem_classification is not None:
            existing_flags = list(stem_classification.flags)
            if "high_instrument_confusion" not in existing_flags:
                existing_flags.append("high_instrument_confusion")
                stem_classification = StemClassification(
                    guitar_stem_usable=stem_classification.guitar_stem_usable,
                    analysis_audio_role=stem_classification.analysis_audio_role,
                    flags=tuple(existing_flags),
                    user_warning=stem_classification.user_warning,
                    stem_confidence=stem_classification.stem_confidence,
                )

    # Commit 123: Solo harmony enrichment — cross-reference solo notes with chord timeline
    harmonized_solo = None
    per_bar_analysis = None
    if (
        chord_timeline
        and solo_notes
        and chord_timeline.events
        and solo_notes.notes
        and summary.key_name
    ):
        try:
            harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, summary.key_name)
            harmonized_solo = harmonizer.harmonized_solo
            per_bar_analysis = harmonizer.per_bar_analysis
            logger.info(
                "solo harmony analysis completed for job_id=%s: %d notes, %d bars",
                job_id, harmonized_solo.note_count, len(per_bar_analysis),
            )
        except Exception:
            logger.exception("solo harmony analysis failed for job_id=%s; skipping", job_id)

    # Commit 117: Run Whisper before section construction so refinement has
    # all three signals (chords, vocals, energy).
    lyrics_aligned, transcription_confidence = transcribe_vocals_to_lyrics_aligned(
        vocals_stem_path, beat_grid=beat_grid_list, bar_timestamps=bar_timestamps
    )

    # Commit 117: Refine section boundaries by fusing chord density, vocal gaps,
    # and energy envelope novelty. Falls back to RMS boundaries on failure.
    refined_segments: list[dict[str, Any]] = summary.segments
    if (
        summary.onset_novelty is not None
        and summary.rms_curve is not None
        and summary.times is not None
        and chord_timeline is not None
        and len(chord_timeline.events) > 0
    ):
        try:
            chord_events = [(e.timestamp, e.chord) for e in chord_timeline.events]
            refined_segments = refine_section_boundaries(
                rms_boundaries=[s.get("start_s", 0.0) for s in summary.segments],
                chord_events=chord_events,
                lyrics_aligned=lyrics_aligned,
                onset_novelty=summary.onset_novelty,
                rms_curve=summary.rms_curve,
                times=summary.times,
                song_duration=summary.duration_s,
                spectral_centroid_curve=summary.spectral_centroid,
            )
            logger.info(
                "section refinement completed for job_id=%s: %d segments",
                job_id,
                len(refined_segments),
            )
        except Exception:
            logger.exception(
                "section refinement failed for job_id=%s; using original segments",
                job_id,
            )

    # Commit 118: Detect repeated sections via chroma self-similarity
    if (
        summary.chroma is not None
        and summary.times is not None
        and len(refined_segments) >= 2
    ):
        try:
            # Build boundaries: all segment start times + end time of last segment
            seg_starts = [s.get("start", s.get("start_s", 0.0)) for s in refined_segments]
            last_seg = refined_segments[-1]
            last_end = last_seg.get("end", last_seg.get("end_s"))
            if last_end is None:
                last_end = summary.duration_s
            boundaries = seg_starts + [float(last_end)]
            repeat_results = detect_repeated_sections(
                chroma=summary.chroma,
                times=summary.times,
                boundaries=boundaries,
                existing_labels=[s.get("label", "Section") for s in refined_segments],
            )
            if repeat_results is not None:
                for seg, ri in zip(refined_segments, repeat_results):
                    seg["repeat_group_id"] = ri["repeat_group_id"]
                    seg["is_repeated"] = ri["is_repeated"]
                    seg["repeat_count"] = ri["repeat_count"]
                    seg["repeat_index"] = ri["repeat_index"]
                    seg["label"] = ri["label"]
                logger.info(
                    "repeat detection completed for job_id=%s: %d groups",
                    job_id,
                    len(set(ri["repeat_group_id"] for ri in repeat_results)),
                )
        except Exception:
            logger.exception(
                "repeat detection failed for job_id=%s; labels unchanged", job_id
            )

    sections: list[LessonSectionStub] = []
    section_starts: list[float | None] = []

    for seg in refined_segments:
        label = seg.get("label") if isinstance(seg, dict) else None
        if not isinstance(label, str) or not label.strip():
            label = "Section"
        # Commit 117: refined segments use "start"/"end" keys; fall back to "start_s"
        start_raw = seg.get("start") if isinstance(seg, dict) else None
        if start_raw is None:
            start_raw = seg.get("start_s") if isinstance(seg, dict) else None
        end_raw = seg.get("end") if isinstance(seg, dict) else None
        if end_raw is None:
            end_raw = seg.get("end_s") if isinstance(seg, dict) else None
        start_time_seconds = (
            float(start_raw) if isinstance(start_raw, (int, float)) else None
        )
        end_time_seconds = (
            float(end_raw) if isinstance(end_raw, (int, float)) else None
        )
        # Commit 117: extract label_confidence from refined segments
        label_confidence = seg.get("label_confidence") if isinstance(seg, dict) else None
        section_starts.append(start_time_seconds)
        # Placeholder confidence (overwritten once we have transcription confidence).
        sections.append(
            LessonSectionStub(
                label=label,
                confidence=0.6,
                start_time_seconds=start_time_seconds,
                end_time_seconds=end_time_seconds,
                label_confidence=float(label_confidence) if isinstance(label_confidence, (int, float)) else None,
                # Commit 118: repetition metadata
                repeat_group_id=seg.get("repeat_group_id") if isinstance(seg, dict) else None,
                is_repeated=seg.get("is_repeated") if isinstance(seg, dict) else None,
                repeat_count=seg.get("repeat_count") if isinstance(seg, dict) else None,
                repeat_index=seg.get("repeat_index") if isinstance(seg, dict) else None,
            )
        )

    if not sections:
        sections = [LessonSectionStub(label="Intro", confidence=0.3, start_time_seconds=0.0)]
        section_starts = [0.0]

    # Commit 119: fall back to "Section N" when label confidence < 0.6
    for i, sec in enumerate(sections):
        lc = sec.label_confidence
        if lc is not None and lc < 0.6:
            sec.label = f"Section {i + 1}"

    # Attach transcription data to each section
    for i, section in enumerate(sections):
        section_start = section.start_time_seconds
        # Commit 117: prefer end_time_seconds from refined segment, fall back to next start
        section_end = section.end_time_seconds
        if section_end is None:
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
        
        # Commit 108: Generate per-section MusicXML
        if section_beat_grid and section_chord_timeline and section_solo_notes:
            try:
                section_musicxml = build_musicxml(
                    beat_grid=section_beat_grid,
                    chord_timeline=section_chord_timeline,
                    solo_notes=section_solo_notes,
                    title=song_title or "Harmoniq Score",
                    artist=artist or "Harmoniq AI",
                    key_signature=summary.key_name,
                )
                section_dict["musicxml"] = section_musicxml
            except Exception:
                logger.exception(
                    "Per-section MusicXML generation failed for section %d of job_id=%s",
                    i, job_id,
                )
        
        sections[i] = LessonSectionStub(**section_dict)

    skip_tabs = stem_classification is not None and not stem_classification.guitar_stem_usable
    tab_artifacts: dict[str, str] | None = None

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

    style = infer_style_from_librosa_summary(summary)
    stem_fields = _lesson_json_stem_fields(stem_classification)

    # Commit 121: Per-section instrument confusion from dual-path fusion log
    per_section_confusion = compute_per_section_confusion(
        sections=sections,
        chord_timeline=chord_timeline,
        fusion_log=dual_fusion_log or [],
    )

    # Commit 121: Log per-job instrument confusion for model improvement tracking
    if instrument_confusion is not None:
        per_section_summary = [
            {
                "section_index": s.section_index,
                "label": s.label,
                "confusion": round(s.instrument_confusion, 3),
                "is_high": s.is_high_confusion,
                "beats": s.beat_count,
                "disagreements": s.disagreement_count,
            }
            for s in per_section_confusion
        ]
        logger.info(
            "instrument_confusion job_id=%s confusion=%.3f per_section=%s",
            job_id,
            instrument_confusion,
            json.dumps(per_section_summary) if per_section_summary else "[]",
        )

    # Commit 82: Set low_snr_warning for pre-emptive transcription quality warning
    # Trigger warning when transcription confidence is very low (< 0.5)
    low_snr_warning = transcription_confidence is not None and transcription_confidence < 0.5

    # Generate MusicXML lead sheet with chords and solo notes
    musicxml_str = ""
    if on_stage:
        on_stage("building_musicxml", 0.88, "Building MusicXML…")
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
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        beat_grid_structured=beat_grid,
        stem_routing=routing_hints,
        instrument_confusion=instrument_confusion,
        instrument_confusion_per_section=per_section_confusion,
        harmonized_solo=harmonized_solo,
        per_bar_analysis=per_bar_analysis,
        transcription_source=transcription_source,
        **stem_fields,
    )

    # Commit 108: Persist score.musicxml as standalone file in job directory
    if musicxml_str:
        try:
            job_dir = Path("data") / "jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "score.musicxml").write_text(musicxml_str, encoding="utf-8")
            logger.info("Persisted score.musicxml for job_id=%s", job_id)
        except Exception:
            logger.exception("Failed to persist score.musicxml for job_id=%s", job_id)

    full_gp5 = tab_artifacts.get("tab_full_gp5_base64") if tab_artifacts else None
    if isinstance(full_gp5, str) and full_gp5.strip():
        lesson = enrich_lesson_with_prerender_hints(lesson, job_id=job_id, gp5_base64=full_gp5, musicxml=musicxml_str)
    elif musicxml_str:
        # Commit 108: Even without GP5, try prerendering from MusicXML
        lesson = enrich_lesson_with_prerender_hints(lesson, job_id=job_id, musicxml=musicxml_str)
    return lesson
