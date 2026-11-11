"""Confidence-Adaptive Fallback Chain Orchestrator.

Implements the tiered inference pipeline:
  1. MT3 (primary) — run full event stream, decode to chords + solo
  2. CRNN TFLite (fallback) — existing chord_inference.py for chords
  3. Chroma matching (tertiary) — pure librosa template matching

Each tier evaluates confidence. If MT3 confidence is below threshold or
MT3 server is unavailable, falls back to the next tier. The orchestrator
tracks which tier produced the result for observability and records
chain metadata (attempted tiers, reasons) for downstream consumption.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.chord_inference import get_last_inference_tier, infer_chords
from app.confidence_thresholds import (
    MT3_GATE_CHORD_CONFIDENCE_MIN,
    confidence_gate_enabled,
)
from app.mt3.chord_decoder import decode_events_to_chord_timeline
from app.mt3.model_server import Mt3ModelServer, mt3_infer
from app.mt3.schemas import Mt3EventStream, TranscriptionSource
from app.mt3.solo_decoder import decode_events_to_solo_notes
from app.schemas import BeatGrid, ChordTimeline, SoloNotes
from app.transcription_confidence import chord_section_confidence

logger = logging.getLogger("harmoniq.mt3.fallback")

# Minimum mean confidence for MT3 output to be accepted
_MT3_CONFIDENCE_THRESHOLD = 0.7

# Minimum chord event count to consider MT3 output valid
_MIN_CHORD_EVENTS = 3

@dataclass
class TranscriptionResult:
    """Result of a full transcription run through the fallback chain.

    Contains both chord and solo outputs from whichever tier succeeded,
    along with metadata about the tier and confidence.
    """

    chord_timeline: ChordTimeline = field(default_factory=lambda: ChordTimeline(events=[]))
    solo_notes: SoloNotes = field(default_factory=lambda: SoloNotes(notes=[]))
    source: TranscriptionSource = "none"
    mean_confidence: float = 0.0
    chord_mean_confidence: float | None = None
    mt3_events: Mt3EventStream | None = None
    solo_leakage_ratio: float | None = None
    fallback_reason: str | None = None
    # Commit A2.1: structured metadata tracing the full fallback chain
    transcription_metadata: dict | None = None

def get_transcription_source_label(source: TranscriptionSource) -> str:
    """Get a human-readable label for the transcription source tier."""
    labels = {
        "mt3": "MT3 (Multi-Task Multitrack Transformer)",
        "student": "Harmoniq two-head student (W3)",
        "crnn": "CRNN TFLite Chord Model",
        "chroma": "Librosa Chroma Template Matching",
        "none": "No transcription available",
    }
    return labels.get(source, "Unknown transcription source")

def transcribe_with_fallback(
    audio_path: Path | str,
    beat_grid: BeatGrid,
    *,
    use_mt3: bool = True,
    mt3_confidence_threshold: float = _MT3_CONFIDENCE_THRESHOLD,
    solo_audio_path: Path | str | None = None,
    guitar_only_solo: bool = True,
) -> TranscriptionResult:
    """Run the full fallback chain and return the best available transcription.

    Args:
        audio_path: Path to the audio file (44.1kHz mono WAV).
        beat_grid: Pre-computed beat grid for quantization.
        use_mt3: If False, skip MT3 tier entirely (for testing/CI).
        mt3_confidence_threshold: Minimum mean confidence required for
            MT3 output to be accepted.
        solo_audio_path: Optional guitar stem. When provided (and different from
            ``audio_path``), the solo branch decodes a separate MT3 pass over the
            guitar stem instead of reusing the chord-mix event stream.
        guitar_only_solo: Restrict solo decoding to GM guitar programs (24-31).

    Returns:
        TranscriptionResult with the best available chord and solo data,
        plus transcription_metadata tracing the fallback chain.
    """
    audio_path = Path(audio_path)

    chain_metadata: dict = {
        "attempted_tiers": [],
        "tier_reasons": {},
        "mean_confidence": 0.0,
    }

    if not audio_path.is_file():
        logger.error("transcribe_with_fallback: audio file not found: %s", audio_path)
        chain_metadata["tier_reasons"]["none"] = "audio_file_not_found"
        return TranscriptionResult(
            source="none",
            fallback_reason="audio_file_not_found",
            transcription_metadata=chain_metadata,
        )

    # Tier 0 (opt-in): the W3 student. Enabled with HARMONIQ_STUDENT_ENABLED=1.
    # It replaces the expensive MT3 primary when present; any failure falls
    # through to the unchanged MT3 → CRNN → chroma chain.
    student_result = _try_student(audio_path, beat_grid)
    if student_result is not None:
        chain_metadata["attempted_tiers"].append("student")
        if len(student_result.chord_timeline.events) >= _MIN_CHORD_EVENTS:
            chain_metadata["tier_reasons"]["student"] = "success"
            chain_metadata["mean_confidence"] = student_result.mean_confidence
            chain_metadata["chord_mean_confidence"] = student_result.chord_mean_confidence
            student_result.transcription_metadata = chain_metadata
            logger.info(
                "Fallback chain result: source=student confidence=%.3f chain=%s",
                student_result.mean_confidence,
                chain_metadata["attempted_tiers"],
            )
            return student_result
        chain_metadata["tier_reasons"]["student"] = (
            f"student_insufficient_chords:{len(student_result.chord_timeline.events)}"
        )
        logger.info(
            "Student produced %d chord events (minimum %d); falling back",
            len(student_result.chord_timeline.events),
            _MIN_CHORD_EVENTS,
        )

    # Tier 1: MT3 — produces both chords and solo notes
    if use_mt3:
        chain_metadata["attempted_tiers"].append("mt3")
        result = _try_mt3(
            audio_path,
            beat_grid,
            mt3_confidence_threshold,
            solo_audio_path=solo_audio_path,
            guitar_only_solo=guitar_only_solo,
        )
        if result is not None and result.source == "mt3" and len(result.chord_timeline.events) >= _MIN_CHORD_EVENTS:
            chain_metadata["tier_reasons"]["mt3"] = "success"
            chain_metadata["mean_confidence"] = result.mean_confidence
            chain_metadata["chord_mean_confidence"] = result.chord_mean_confidence
            result.transcription_metadata = chain_metadata
            logger.info(
                "Fallback chain result: source=%s confidence=%.3f chain=%s reasons=%s",
                result.source, result.mean_confidence,
                chain_metadata["attempted_tiers"], chain_metadata["tier_reasons"],
            )
            return result
        chain_metadata["tier_reasons"]["mt3"] = result.fallback_reason if result else "mt3_server_unavailable"
    else:
        chain_metadata["tier_reasons"]["mt3"] = "skipped (use_mt3=False)"

    # Tier 2: CRNN TFLite (with internal fallback to chroma)
    chain_metadata["attempted_tiers"].append("crnn")
    result = _try_crnn(audio_path, beat_grid)
    if result is not None and len(result.chord_timeline.events) > 0:
        chain_metadata["tier_reasons"][result.source] = "success"
        chain_metadata["mean_confidence"] = result.mean_confidence
        result.transcription_metadata = chain_metadata
        logger.info(
            "Fallback chain result: source=%s confidence=%.3f chain=%s reasons=%s",
            result.source, result.mean_confidence,
            chain_metadata["attempted_tiers"], chain_metadata["tier_reasons"],
        )
        return result
    chain_metadata["tier_reasons"]["crnn"] = result.fallback_reason if result else "crnn_inference_failed"

    # All tiers failed
    chain_metadata["tier_reasons"]["none"] = "all_tiers_failed"
    logger.error(
        "All transcription tiers failed for %s chain=%s reasons=%s",
        audio_path, chain_metadata["attempted_tiers"], chain_metadata["tier_reasons"],
    )
    return TranscriptionResult(
        source="none",
        fallback_reason="all_tiers_failed",
        transcription_metadata=chain_metadata,
    )


def _try_student(
    audio_path: Path,
    beat_grid: BeatGrid,
) -> TranscriptionResult | None:
    """Attempt the opt-in W3 student.

    Returns ``None`` when the flag is off, the artifact is missing, or the
    inference fails — the caller then continues with the existing chain.
    """
    from app.student.inference import StudentModel, student_enabled

    if not student_enabled():
        return None

    model = StudentModel()
    if not model.is_available():
        logger.warning(
            "Student enabled but unavailable (%s); using MT3 chain",
            model.unavailable_reason(),
        )
        return None

    try:
        logger.info("Tier 0: attempting student transcription for %s", audio_path)
        timeline, solo_notes, metadata = model.transcribe(audio_path, beat_grid)
    except Exception as exc:  # noqa: BLE001 - report and fall back
        logger.warning("Student inference failed for %s: %s", audio_path, exc)
        return None

    confidences = [event.confidence for event in timeline.events]
    mean_confidence = (
        float(np.mean(confidences)) if confidences else 0.0
    )
    return TranscriptionResult(
        chord_timeline=timeline,
        solo_notes=solo_notes,
        source="student",
        mean_confidence=mean_confidence,
        chord_mean_confidence=chord_section_confidence(timeline),
        transcription_metadata={"student": metadata},
    )


_GUITAR_PROGRAMS = set(range(24, 32))


def _solo_leakage_ratio(stream: Mt3EventStream) -> float | None:
    """Share of onset events that are not guitar programs (0 = pure guitar)."""
    onsets = [event for event in stream.events if getattr(event, "is_onset", False)]
    if not onsets:
        return None
    non_guitar = sum(1 for event in onsets if event.program not in _GUITAR_PROGRAMS)
    return non_guitar / len(onsets)


def _try_mt3(
    audio_path: Path,
    beat_grid: BeatGrid,
    confidence_threshold: float,
    *,
    solo_audio_path: Path | str | None = None,
    guitar_only_solo: bool = True,
) -> TranscriptionResult | None:
    """Attempt MT3 transcription.

    Returns None if MT3 is unavailable or confidence is below threshold.
    """
    logger.info("Tier 1: Attempting MT3 transcription for %s", audio_path)

    server = Mt3ModelServer()
    if not server.is_available():
        logger.warning("MT3 model unavailable; skipping Tier 1")
        return None

    event_stream = mt3_infer(str(audio_path))
    if not event_stream.events:
        logger.warning("MT3 produced no events for %s", audio_path)
        return TranscriptionResult(
            source="mt3",
            mean_confidence=0.0,
            mt3_events=event_stream,
            fallback_reason="mt3_no_events",
        )

    gate_enabled = confidence_gate_enabled()
    if not gate_enabled and event_stream.mean_confidence < confidence_threshold:
        logger.info(
            "MT3 confidence %.2f below threshold %.2f; falling back",
            event_stream.mean_confidence, confidence_threshold,
        )
        return TranscriptionResult(
            chord_timeline=ChordTimeline(events=[]),
            solo_notes=SoloNotes(notes=[]),
            source="mt3",
            mean_confidence=event_stream.mean_confidence,
            mt3_events=event_stream,
            fallback_reason=f"mt3_low_confidence:{event_stream.mean_confidence:.2f}",
        )

    chord_timeline = decode_events_to_chord_timeline(event_stream, beat_grid)

    # Solo branch: prefer a separate guitar-stem pass over reusing the chord mix.
    solo_stream = event_stream
    if solo_audio_path is not None:
        solo_path = Path(solo_audio_path)
        if solo_path.is_file() and solo_path.resolve() != Path(audio_path).resolve():
            try:
                logger.info("MT3 solo pass on guitar stem: %s", solo_path)
                solo_stream = mt3_infer(str(solo_path))
            except Exception:
                logger.exception(
                    "MT3 solo pass failed for %s; reusing chord-mix events", solo_path
                )
                solo_stream = event_stream
        elif solo_path.resolve() == Path(audio_path).resolve():
            logger.info("Solo source equals chord mix; decoding one MT3 pass for both")
    allowed_programs = _GUITAR_PROGRAMS if guitar_only_solo else None
    solo_notes = decode_events_to_solo_notes(
        solo_stream,
        beat_grid,
        allowed_programs=allowed_programs,
    )
    solo_leakage = _solo_leakage_ratio(solo_stream)
    chord_mean_confidence = chord_section_confidence(chord_timeline)

    if len(chord_timeline.events) < _MIN_CHORD_EVENTS:
        logger.warning(
            "MT3 chord decoder produced only %d events (minimum %d); falling back",
            len(chord_timeline.events), _MIN_CHORD_EVENTS,
        )
        return TranscriptionResult(
            chord_timeline=chord_timeline,
            solo_notes=solo_notes,
            source="mt3",
            mean_confidence=event_stream.mean_confidence,
            chord_mean_confidence=chord_mean_confidence,
            mt3_events=event_stream,
            solo_leakage_ratio=solo_leakage,
            fallback_reason=f"mt3_insufficient_chords:{len(chord_timeline.events)}",
        )

    if gate_enabled and (
        chord_mean_confidence is None
        or chord_mean_confidence < MT3_GATE_CHORD_CONFIDENCE_MIN
    ):
        observed = (
            f"{chord_mean_confidence:.2f}"
            if chord_mean_confidence is not None
            else "none"
        )
        logger.info(
            "MT3 calibrated gate rejected: chord confidence %s < %.2f; falling back",
            observed, MT3_GATE_CHORD_CONFIDENCE_MIN,
        )
        return TranscriptionResult(
            chord_timeline=ChordTimeline(events=[]),
            solo_notes=SoloNotes(notes=[]),
            source="mt3",
            mean_confidence=event_stream.mean_confidence,
            chord_mean_confidence=chord_mean_confidence,
            mt3_events=event_stream,
            fallback_reason=f"mt3_gate_low_chord_confidence:{observed}",
        )

    logger.info(
        "MT3 transcription successful: %d chord events, %d solo notes "
        "(event confidence=%.2f, chord confidence=%s, gate=%s)",
        len(chord_timeline.events),
        len(solo_notes.notes),
        event_stream.mean_confidence,
        f"{chord_mean_confidence:.2f}" if chord_mean_confidence is not None else "none",
        "on" if gate_enabled else "off",
    )
    return TranscriptionResult(
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        source="mt3",
        mean_confidence=event_stream.mean_confidence,
        chord_mean_confidence=chord_mean_confidence,
        mt3_events=event_stream,
        solo_leakage_ratio=solo_leakage,
    )


def _try_crnn(audio_path: Path, beat_grid: BeatGrid) -> TranscriptionResult | None:
    """Attempt CRNN TFLite chord inference with chroma fallback detection.

    Calls ``infer_chords`` (which internally tries Keras → TFLite → Chroma),
    then uses ``get_last_inference_tier()`` from chord_inference to determine
    whether the actual inference was CRNN or chroma template matching.

    Returns None if inference fails entirely.
    """
    logger.info("Tier 2: Attempting CRNN (with chroma fallback) for %s", audio_path)

    try:
        chord_timeline = infer_chords(audio_path, beat_grid, detect_bass=True, detect_voicing=True)
        if chord_timeline is None:
            chord_timeline = ChordTimeline(events=[])

        mean_conf = (
            float(np.mean([e.confidence for e in chord_timeline.events]))
            if chord_timeline.events else 0.0
        )

        # Detect which tier actually ran inside infer_chords
        actual_tier = get_last_inference_tier()
        source: TranscriptionSource = actual_tier  # type: ignore[assignment]

        logger.info(
            "CRNN/chroma transcription: source=%s events=%d mean_conf=%.2f",
            source, len(chord_timeline.events), mean_conf,
        )
        return TranscriptionResult(
            chord_timeline=chord_timeline,
            solo_notes=SoloNotes(notes=[]),
            source=source,
            mean_confidence=mean_conf,
            chord_mean_confidence=chord_section_confidence(chord_timeline),
        )
    except Exception as exc:
        logger.warning("CRNN/chroma inference failed: %s", exc)
        return None
