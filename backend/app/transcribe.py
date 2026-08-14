"""
Whisper transcription and alignment to Harmoniq beat grid.

This commit (PRIORITIES §8) intentionally keeps the implementation smoke-test
level and defensive:
- Prefer completing the job even when Whisper is unavailable or vocals are weak.
- Always return a monotonically non-regressing `lyrics_aligned` sequence.
"""

from __future__ import annotations

import bisect
import logging
import math
import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.transcription_confidence import vocals_coverage_confidence

logger = logging.getLogger("harmoniq.transcribe")
logger.setLevel(logging.INFO)


@dataclass(frozen=True)
class WordTimestamp:
    word: str
    start_s: float


def _wav_duration_seconds(wav_path: Path) -> float | None:
    """Return WAV duration or None if unreadable."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
        if rate <= 0:
            return None
        return float(frames) / float(rate)
    except Exception:
        return None


def _snap_time_to_nearest_grid_index(t: float, beat_grid: list[float]) -> tuple[int, float]:
    """
    Return (beat_index, snapped_time_seconds) where snapped_time is the nearest entry.
    """
    if not beat_grid:
        return 0, t

    # beat_grid is expected monotonic; rely on ordering for bisect.
    i = bisect.bisect_left(beat_grid, t)
    if i <= 0:
        return 0, float(beat_grid[0])
    if i >= len(beat_grid):
        return len(beat_grid) - 1, float(beat_grid[-1])

    prev_i = i - 1
    prev_t = float(beat_grid[prev_i])
    next_t = float(beat_grid[i])
    if abs(t - prev_t) <= abs(next_t - t):
        return prev_i, prev_t
    return i, next_t


def map_words_to_lyrics_aligned(
    words: Iterable[WordTimestamp],
    *,
    beat_grid: list[float],
    beat_periods_per_bar: int = 4,
) -> list[dict[str, Any]]:
    """
    Snap word start times to nearest `beat_grid` entry.

    Output shape:
      { word: str, time_seconds: float, bar: int, beat: int }
    """
    if not beat_grid:
        return []

    out: list[dict[str, Any]] = []
    last_time = -math.inf

    for w in words:
        snapped_idx, snapped_time = _snap_time_to_nearest_grid_index(float(w.start_s), beat_grid)

        # Never regress: if snapping lands before the previous snapped time,
        # skip to keep the overlay timeline stable.
        if snapped_time + 1e-3 < last_time:
            continue

        beat_in_bar = int(snapped_idx) % int(beat_periods_per_bar)
        bar = int(snapped_idx) // int(beat_periods_per_bar)

        out.append(
            {
                "word": w.word,
                "time_seconds": float(snapped_time),
                "bar": bar,
                "beat": beat_in_bar,
            }
        )
        last_time = snapped_time

    return out


def _estimate_transcription_confidence(*, word_count: int) -> float:
    """
    Fallback confidence heuristic in [0,1] used only when no beat grid is
    available to compute beat coverage (see ``vocals_coverage_confidence``).

    Whisper does not provide a single directly comparable "confidence" scalar
    for our use-case, so we use word availability as a proxy.
    """
    if word_count <= 0:
        return 0.1
    if word_count < 3:
        return 0.2
    if word_count < 12:
        return 0.45
    return 0.85


def transcribe_vocals_to_lyrics_aligned(
    vocals_stem_path: Path | None,
    *,
    beat_grid: list[float],
    # Kept in the signature for future improvements; mapping uses beat_grid for now.
    bar_timestamps: list[float] | None = None,
) -> tuple[list[dict[str, Any]], float]:
    """
    Run Whisper on vocals stem and snap word timestamps to the beat grid.

    Returns:
      (lyrics_aligned, transcription_confidence)
    """
    _ = bar_timestamps  # reserved for future smarter mapping

    if vocals_stem_path is None:
        return [], 0.1

    if not vocals_stem_path.exists() or vocals_stem_path.stat().st_size <= 0:
        return [], 0.1

    # Quick "vocals stem weak" guard: if the stem is extremely short, avoid Whisper.
    duration_s = _wav_duration_seconds(vocals_stem_path)
    if duration_s is not None and duration_s < 1.0:
        return [], 0.15

    # Keep unit tests fast/deterministic even if Whisper is installed.
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("HARMONIQ_SKIP_WHISPER") == "1":
        return [], 0.1

    try:
        import whisper  # type: ignore
    except Exception:
        logger.warning("Whisper import failed; returning empty lyrics_aligned", exc_info=True)
        return [], 0.1

    try:
        model = whisper.load_model(os.getenv("HARMONIQ_WHISPER_MODEL", "base"))
        # word_timestamps=True is the key output we need for snapping.
        result = model.transcribe(str(vocals_stem_path), word_timestamps=True)
    except Exception:
        logger.exception("Whisper transcription failed for %s", vocals_stem_path)
        return [], 0.1

    raw_words: list[WordTimestamp] = []
    for seg in result.get("segments", []) or []:
        for w in seg.get("words", []) or []:
            word = str(w.get("word", "")).strip()
            if not word:
                continue
            start = w.get("start", None)
            if start is None:
                continue
            raw_words.append(WordTimestamp(word=word, start_s=float(start)))

    raw_words.sort(key=lambda x: x.start_s)

    confidence = _estimate_transcription_confidence(word_count=len(raw_words))
    lyrics_aligned = map_words_to_lyrics_aligned(raw_words, beat_grid=beat_grid)
    if not lyrics_aligned:
        # Keep the confidence low when we failed to extract/match any usable word timestamps.
        confidence = min(confidence, 0.2)
    else:
        # ML Fallback milestone: beat coverage is a far better signal than the
        # raw word count (which capped at 0.7 — below the UI "uncertain" bar).
        coverage_conf = vocals_coverage_confidence(lyrics_aligned, len(beat_grid))
        if coverage_conf is not None:
            confidence = coverage_conf
    return lyrics_aligned, float(confidence)

