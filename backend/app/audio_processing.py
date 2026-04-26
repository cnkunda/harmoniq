"""Audio preparation: normalize input to mono WAV and split long tracks into chunks.

Accepts a YouTube URL or uploaded file path, delegates ingest/normalization
to app.ingest, and optionally chunks the result for long recordings.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from app.ingest import (
    AudioTooShortError,
    IngestError,
    SourceMetadata,
    YouTubeUrlInvalidError,
    get_job_dir,
    ingest_youtube_or_upload_to_wav,
    wav_file_duration_seconds,
)
from app.pipeline_proof import TARGET_SR

# Keep chunk windows reasonably small for long recordings (memory + inspectability).
LONG_TRACK_CHUNK_TRIGGER_SECONDS = 15 * 60
LONG_TRACK_CHUNK_SECONDS = 5 * 60


class AudioPreparationError(RuntimeError):
    """Raised when audio ingest/normalization/chunking fails."""


@dataclass(frozen=True)
class AudioPreparationResult:
    """Prepared normalized audio and optional chunk artifacts for long tracks."""

    job_id: str
    job_dir: Path
    normalized_wav_path: Path
    source_metadata: SourceMetadata | None
    duration_seconds: float
    chunk_paths: tuple[Path, ...]


def _chunk_wav_for_long_track(
    wav_path: Path,
    chunk_dir: Path,
    *,
    chunk_seconds: int = LONG_TRACK_CHUNK_SECONDS,
) -> tuple[Path, ...]:
    """Split PCM WAV into fixed-size chunks. Returns absolute chunk paths."""
    if chunk_seconds <= 0:
        raise AudioPreparationError("chunk_seconds must be positive")
    chunk_dir.mkdir(parents=True, exist_ok=True)

    try:
        with wave.open(str(wav_path), "rb") as src:
            channels = src.getnchannels()
            sample_width = src.getsampwidth()
            sample_rate = src.getframerate()
            total_frames = src.getnframes()
            if sample_rate <= 0:
                raise AudioPreparationError("Invalid sample rate in normalized WAV")

            frames_per_chunk = int(chunk_seconds * sample_rate)
            # chunk_seconds > 0 and sample_rate > 0 validated above, so frames_per_chunk is always positive

            out: list[Path] = []
            cursor = 0
            index = 0
            while cursor < total_frames:
                frames_to_read = min(frames_per_chunk, total_frames - cursor)
                src.setpos(cursor)
                raw = src.readframes(frames_to_read)
                if not raw:
                    break
                chunk_path = chunk_dir / f"chunk_{index:03d}.wav"
                with wave.open(str(chunk_path), "wb") as dst:
                    dst.setnchannels(channels)
                    dst.setsampwidth(sample_width)
                    dst.setframerate(sample_rate)
                    dst.writeframes(raw)
                out.append(chunk_path)
                cursor += frames_to_read
                index += 1
            return tuple(out)
    except wave.Error as exc:
        raise AudioPreparationError(f"Chunking failed: invalid WAV ({exc})") from exc
    except OSError as exc:
        raise AudioPreparationError(f"Chunking failed: {exc}") from exc


def prepare_audio_input(
    job_id: str,
    *,
    youtube_url: str | None,
    upload_path: str | None,
    target_sr: int = TARGET_SR,
) -> AudioPreparationResult:
    """Normalize user input to `song.wav` and chunk only when tracks are long."""
    job_dir = get_job_dir(job_id)
    try:
        wav_path, source_metadata = ingest_youtube_or_upload_to_wav(
            job_id,
            youtube_url=youtube_url,
            upload_path=upload_path,
            target_sr=target_sr,
        )
    # AudioTooShortError is a subclass of IngestError — listed explicitly for readability
    except (IngestError, YouTubeUrlInvalidError):
        raise  # already structured, let them through
    except Exception as exc:
        raise AudioPreparationError(f"Unexpected error: {exc}") from exc

    # NOTE: ingest_youtube_or_upload_to_wav already calls _verify_wav_and_get_duration
    # internally. The duration check here on the same file is a redundant third wave.open().
    # Short-term: acceptable given the None guard is needed anyway.
    # Long-term: consider returning duration from ingest_youtube_or_upload_to_wav.
    duration = wav_file_duration_seconds(wav_path)
    if duration is None:
        raise AudioPreparationError("Could not read normalized WAV duration")

    chunk_paths: tuple[Path, ...] = ()
    if duration >= LONG_TRACK_CHUNK_TRIGGER_SECONDS:
        chunk_paths = _chunk_wav_for_long_track(
            wav_path,
            job_dir / "chunks",
            chunk_seconds=LONG_TRACK_CHUNK_SECONDS,
        )

    return AudioPreparationResult(
        job_id=job_id,
        job_dir=job_dir,
        normalized_wav_path=wav_path,
        source_metadata=source_metadata,
        duration_seconds=duration,  # already float after None check
        chunk_paths=chunk_paths,
    )
