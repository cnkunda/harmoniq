"""Audio ingest: YouTube URL or uploaded file -> normalized mono WAV.

Validates input, downloads (via yt-dlp) or accepts an upload, normalizes
to a 16-bit mono WAV at the pipeline's target sample rate, and returns
the output path alongside any available source metadata.
"""


from __future__ import annotations

import logging
import os
import re
import wave
from pathlib import Path
from typing import TypedDict
from urllib.parse import parse_qs, urlparse

from app.pipeline_proof import TARGET_SR as DEFAULT_TARGET_SR
from app.pipeline_proof import ffmpeg_normalize_wav, yt_dlp_download_wav
from app.youtube_meta import extract_youtube_metadata

logger = logging.getLogger("harmoniq.ingest")


class YouTubeUrlInvalidError(ValueError):
    """Raised when `youtube_url` fails local validation."""


class IngestError(RuntimeError):
    """Raised for ingest/normalization failures."""


class AudioTooShortError(IngestError):
    """Normalized audio is shorter than ``MIN_ANALYZE_DURATION_SECONDS`` (README / MANUAL_QA)."""


# Must match `README_ERROR_COPY.audioTooShort` on the client.
MIN_ANALYZE_DURATION_SECONDS = 30.0
AUDIO_TOO_SHORT_USER_MESSAGE = (
    "That clip is too short to analyze. Try a full song or a longer section."
)


class SourceMetadata(TypedDict):
    """Display metadata from ingest (YouTube); uploads omit this until client edits."""

    song_title: str
    artist: str | None


def resolve_lesson_titles(
    source_metadata: SourceMetadata | None,
    *,
    source_url: str | None,
) -> tuple[str, str]:
    """Default ``song_title`` / ``artist`` for ``LessonJSON`` when metadata is partial or missing."""
    if source_metadata:
        title = (source_metadata.get("song_title") or "").strip()
        if not title:
            title = "Unknown title"
        ar = source_metadata.get("artist")
        artist = ar.strip() if isinstance(ar, str) and ar.strip() else "Unknown artist"
        return title, artist
    if source_url:
        return "YouTube video", "Unknown artist"
    return "Uploaded track", "Unknown artist"


def _backend_dir() -> Path:
    """Return backend root dir (backend/).

    Used only to anchor relative DATA_DIR paths.
    Preferring DATA_DIR env var over filesystem introspection.
    """
    if data_dir := os.getenv("DATA_DIR"):
        p = Path(data_dir)
        if p.is_absolute():
            return p
    # Fallback: backend/app/ingest.py -> backend/
    return Path(__file__).resolve().parents[1]


def get_data_dir() -> Path:
    """Return runtime `data/` directory (respecting `DATA_DIR` env var)."""
    raw = os.getenv("DATA_DIR", "./data")
    p = Path(raw)
    if not p.is_absolute():
        p = _backend_dir() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class JobIdInvalidError(ValueError):
    """Raised when job_id contains invalid characters (path traversal protection)."""


def get_job_dir(job_id: str) -> Path:
    if not _JOB_ID_RE.match(job_id):
        raise JobIdInvalidError(f"Invalid job_id: {job_id!r}")
    job_dir = get_data_dir() / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _extract_youtube_video_id(youtube_url: str) -> str | None:
    """Extract a video id using only local URL parsing (no network)."""
    parsed = urlparse(youtube_url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        return None

    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            vid = qs.get("v", [None])[0]
            return vid
        # Support `.../embed/<id>` for convenience.
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/", 1)[1].split("/", 1)[0]
        return None

    if host.endswith("youtu.be"):
        return parsed.path.lstrip("/").split("/", 1)[0]

    return None


_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def validate_youtube_url(youtube_url: str) -> str:
    """Fail fast for malformed URLs so tests and offline usage behave predictably."""
    if not youtube_url or not youtube_url.strip():
        raise YouTubeUrlInvalidError("youtube_url missing")
    vid = _extract_youtube_video_id(youtube_url)
    if not vid or not _YOUTUBE_ID_RE.match(vid):
        raise YouTubeUrlInvalidError("youtube_url is not a full YouTube link")
    return youtube_url.strip()


def wav_file_duration_seconds(path: Path) -> float | None:
    """Public utility for callers that need duration without full ingest.

    Returns length in seconds for a PCM WAV file, or ``None`` if unreadable (e.g. not WAV).
    """
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except (wave.Error, OSError):
        return None


def _verify_wav_and_get_duration(
    wav_path: Path,
    *,
    expected_sample_rate: int = DEFAULT_TARGET_SR,
    expected_channels: int = 1,
) -> float:
    """Ensure ffmpeg output matches Harmoniq's ingest contract and return duration."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            framerate = wf.getframerate()
            if framerate <= 0:
                raise IngestError("Invalid sample rate in WAV")
            channels = wf.getnchannels()
            frames = wf.getnframes()
    except wave.Error as e:
        raise IngestError(f"Output song.wav is not a valid WAV: {e}") from e

    if framerate != expected_sample_rate:
        raise IngestError(
            f"Output song.wav has sample rate {framerate}, expected {expected_sample_rate}"
        )
    if channels != expected_channels:
        raise IngestError(f"Output song.wav has {channels} channels, expected {expected_channels}")
    return frames / float(framerate)


def _require_min_analyze_duration(duration: float) -> None:
    if duration < MIN_ANALYZE_DURATION_SECONDS:
        raise AudioTooShortError(AUDIO_TOO_SHORT_USER_MESSAGE)


def ingest_youtube_or_upload_to_wav(
    job_id: str,
    *,
    youtube_url: str | None,
    upload_path: str | None,
    target_sr: int = DEFAULT_TARGET_SR,
) -> tuple[Path, SourceMetadata | None]:
    """Write normalized ``song.wav`` to the job dir.

    Returns ``(wav_path, source_metadata)``. For YouTube, ``source_metadata`` is set when
    yt-dlp returns at least a title; for file uploads it is ``None``.
    """
    job_dir = get_job_dir(job_id)
    song_wav_path = job_dir / "song.wav"

    source_metadata: SourceMetadata | None = None

    if youtube_url:
        normalized = validate_youtube_url(youtube_url)
        try:
            song_t, artist_t = extract_youtube_metadata(normalized)
        except Exception as e:
            logger.warning("Failed to extract YouTube metadata: %s", e)
            song_t, artist_t = None, None
        if song_t:
            source_metadata = {"song_title": song_t, "artist": artist_t}
        elif artist_t:
            source_metadata = {"song_title": "Unknown title", "artist": artist_t}
        downloads_dir = job_dir / "downloads"
        logger.info("Downloading YouTube audio for job_id=%s", job_id)
        downloaded_wav_path: Path | None = None
        try:
            downloaded_wav_path = yt_dlp_download_wav(normalized, downloads_dir)
            logger.info("Normalizing downloaded wav for job_id=%s", job_id)
            ffmpeg_normalize_wav(
                downloaded_wav_path,
                song_wav_path,
                sample_rate=target_sr,
                mono=True,
            )
        except Exception as e:
            # Distinguish between invalid URL vs transient failures.
            # NOTE: These strings match yt-dlp error messages as of ~2024.x.
            # Re-verify against yt-dlp release notes on each upgrade.
            err_msg = str(e).lower()
            if any(k in err_msg for k in ("not available", "private video", "removed", "invalid", "unable to extract", "unsupported url")):
                raise YouTubeUrlInvalidError(str(e)) from None
            raise IngestError(f"YouTube download failed (possibly transient): {e}") from e
        finally:
            # Cleanup intermediate download to prevent disk accumulation
            try:
                if downloaded_wav_path is not None:
                    downloaded_wav_path.unlink(missing_ok=True)
                downloads_dir.rmdir()  # Only removes if empty
            except OSError:
                pass  # Ignore cleanup failures
    elif upload_path:
        src = Path(upload_path)
        # Security: prevent path traversal by requiring uploads to be under data dir
        # (resolve both paths to prevent symlink bypass)
        try:
            src.resolve().relative_to(get_data_dir().resolve())
        except ValueError:
            raise IngestError(f"Upload file must be within data directory: {upload_path}")
        if not src.exists():
            raise IngestError(f"Upload file missing on disk: {src}")
        logger.info("Normalizing upload for job_id=%s from %s", job_id, src)
        ffmpeg_normalize_wav(src, song_wav_path, sample_rate=target_sr, mono=True)
    else:
        raise IngestError("No youtube_url or upload file provided")

    duration = _verify_wav_and_get_duration(song_wav_path, expected_sample_rate=target_sr, expected_channels=1)
    _require_min_analyze_duration(duration)
    return song_wav_path, source_metadata

