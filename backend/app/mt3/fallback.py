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

from app.beat_grid import estimate_beat_grid
from app.chord_inference import get_last_inference_tier, infer_chords
from app.mt3.chord_decoder import decode_events_to_chord_timeline
from app.mt3.model_server import Mt3ModelServer, mt3_infer
from app.mt3.schemas import Mt3EventStream, TranscriptionSource
from app.mt3.solo_decoder import decode_events_to_solo_notes
from app.schemas import BeatGrid, ChordTimeline, SoloNotes

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
    mt3_events: Mt3EventStream | None = None
    fallback_reason: str | None = None
    # Commit A2.1: structured metadata tracing the full fallback chain
    transcription_metadata: dict | None = None


def get_transcription_source_label(source: TranscriptionSource) -> str:
    """Get a human-readable label for the transcription source tier."""
    labels = {
        "mt3": "MT3 (Multi-Task Multitrack Transformer)",
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
) -> TranscriptionResult:
    """Run the full fallback chain and return the best available transcription.

    Args:
        audio_path: Path to the audio file (44.1kHz mono WAV).
        beat_grid: Pre-computed beat grid for quantization.
        use_mt3: If False, skip MT3 tier entirely (for testing/CI).
        mt3_confidence_threshold: Minimum mean confidence required for
            MT3 output to be accepted.

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

    # Tier 1: MT3 — produces both chords and solo notes
    if use_mt3:
        chain_metadata["attempted_tiers"].append("mt3")
        result = _try_mt3(audio_path, beat_grid, mt3_confidence_threshold)
        if result is not None and result.source == "mt3" and len(result.chord_timeline.events) >= _MIN_CHORD_EVENTS:
            chain_metadata["tier_reasons"]["mt3"] = "success"
            chain_metadata["mean_confidence"] = result.mean_confidence
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


def _try_mt3(
    audio_path: Path,
    beat_grid: BeatGrid,
    confidence_threshold: float,
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

    if event_stream.mean_confidence < confidence_threshold:
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
    solo_notes = decode_events_to_solo_notes(event_stream, beat_grid)

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
            mt3_events=event_stream,
            fallback_reason=f"mt3_insufficient_chords:{len(chord_timeline.events)}",
        )

    logger.info(
        "MT3 transcription successful: %d chord events, %d solo notes (confidence=%.2f)",
        len(chord_timeline.events), len(solo_notes.notes), event_stream.mean_confidence,
    )
    return TranscriptionResult(
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        source="mt3",
        mean_confidence=event_stream.mean_confidence,
        mt3_events=event_stream,
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
        chord_timeline = infer_chords(audio_path, beat_grid)
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
        )
    except Exception as exc:
        logger.warning("CRNN/chroma inference failed: %s", exc)
        return None
