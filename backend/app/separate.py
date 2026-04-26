"""Stem separation step for PRIORITIES §6 (Demucs htdemucs_6s).

Goal:
  - Produce six stems: guitar, bass, drums, vocals, piano, other
  - Write them under: data/jobs/{job_id}/stems/
  - Return a mapping suitable for LessonJSON.stems

Smoke-test / CI note:
  Demucs downloads model weights and can be slow. Unit tests should remain fast,
  so this module supports a default "skip demucs" mode when running under pytest.

Performance improvements:
  - HARMONIQ_FAST_STEMS=1 uses htdemucs_ft (faster transformer model)
  - HARMONIQ_SKIP_STEMS=1 skips stem separation entirely (placeholder stems)
  - Stem caching by audio hash to avoid re-running Demucs on same audio
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
import wave
from pathlib import Path

from app.ingest import get_data_dir
from app.pipeline_proof import TARGET_SR, run_demucs_htdemucs_6s

logger = logging.getLogger("harmoniq.separate")
logger.setLevel(logging.INFO)

STEM_KEYS: tuple[str, ...] = ("guitar", "bass", "drums", "vocals", "piano", "other")

# Maximum cache size in bytes (default: 5GB)
MAX_STEM_CACHE_BYTES = 5 * 1024 * 1024 * 1024


class SeparationError(RuntimeError):
    """Raised when demucs separation fails or outputs are missing/unusable."""


def _backend_root() -> Path:
    # backend/app/separate.py -> backend/
    return Path(__file__).resolve().parents[1]


def _rel_to_backend_root(path: Path) -> str:
    """Return `data/...`-style paths (forward slashes) for JSON payloads."""
    p = path.resolve()
    rel = p.relative_to(_backend_root().resolve())
    return rel.as_posix()


def _should_skip_demucs() -> bool:
    # Explicit override for devs / CI.
    if os.getenv("HARMONIQ_SKIP_DEMUCS") == "1":
        return True

    # Production override to skip stem separation entirely.
    if os.getenv("HARMONIQ_SKIP_STEMS") == "1":
        return True

    # Pytest sets this env var during tests. Keep unit tests fast and deterministic.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True

    return False


def _get_demucs_model() -> str:
    """Return faster model for dev, full model for production.
    
    htdemucs_ft: Faster transformer model (~3x faster than htdemucs_6s)
    htdemucs_6s: Six-stem hybrid model (default, higher quality)
    """
    if os.getenv("HARMONIQ_FAST_STEMS", "").strip() == "1":
        return "htdemucs_ft"
    return "htdemucs_6s"


def _get_audio_hash(song_wav_path: Path) -> str:
    """Return stable MD5 hash for caching decisions.
    
    Uses first 1MB of file for speed while maintaining uniqueness for typical audio files.
    """
    hash_obj = hashlib.md5()
    with open(song_wav_path, "rb") as f:
        # Read first 1MB for hashing - sufficient for audio uniqueness
        chunk = f.read(1024 * 1024)
        hash_obj.update(chunk)
    return hash_obj.hexdigest()


def _get_stem_cache_dir() -> Path:
    """Return the stem cache directory, creating it if needed."""
    cache_dir = get_data_dir() / "stem_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_cache_size_bytes(cache_dir: Path) -> int:
    """Return total size of cache directory in bytes."""
    total = 0
    for item in cache_dir.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _cleanup_old_cache_entries(cache_dir: Path) -> None:
    """Remove oldest cache entries if cache exceeds MAX_STEM_CACHE_BYTES."""
    current_size = _get_cache_size_bytes(cache_dir)
    if current_size <= MAX_STEM_CACHE_BYTES:
        return
    
    logger.info(
        "Cache size %.2f GB exceeds limit %.2f GB, cleaning up",
        current_size / (1024**3),
        MAX_STEM_CACHE_BYTES / (1024**3),
    )
    
    # Get all cache entries with their access times
    entries = []
    for entry_dir in cache_dir.iterdir():
        if entry_dir.is_dir():
            stat = entry_dir.stat()
            entries.append((entry_dir, stat.st_atime, stat.st_size))
    
    # Sort by access time (oldest first)
    entries.sort(key=lambda x: x[1])
    
    # Remove oldest entries until under limit
    for entry_dir, _, size in entries:
        if current_size <= MAX_STEM_CACHE_BYTES:
            break
        try:
            shutil.rmtree(entry_dir)
            current_size -= size
            logger.info("Removed cache entry: %s", entry_dir.name)
        except Exception as e:
            logger.warning("Failed to remove cache entry %s: %s", entry_dir.name, e)


def _load_cached_stems(cache_dir: Path, stems_dir: Path) -> dict[str, str]:
    """Load stems from cache directory to job stems directory.
    
    Returns mapping of stem keys to backend-relative paths.
    """
    stems_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    
    for key in STEM_KEYS:
        src = cache_dir / f"{key}.wav"
        if not src.exists():
            raise SeparationError(f"Cache missing stem {key}.wav")
        
        dest = stems_dir / f"{key}.wav"
        shutil.copyfile(src, dest)
        
        if not _is_readable_nonempty_wav(dest):
            raise SeparationError(f"Cached stem {dest} is not a valid WAV.")
        
        mapping[key] = _rel_to_backend_root(dest)
    
    return mapping


def _save_stems_to_cache(stems_dir: Path, cache_dir: Path) -> None:
    """Save stems from job directory to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    for key in STEM_KEYS:
        src = stems_dir / f"{key}.wav"
        dest = cache_dir / f"{key}.wav"
        if src.exists():
            shutil.copyfile(src, dest)
    
    # Cleanup if cache is too large
    _cleanup_old_cache_entries(_get_stem_cache_dir())


def _is_readable_nonempty_wav(path: Path) -> bool:
    """Return True if `path` is a non-empty readable WAV file."""
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return False
        with wave.open(str(path), "rb") as wf:
            _ = wf.getnframes()
            return True
    except wave.Error:
        return False


def _find_stem_file(stems_track_dir: Path, stem_name: str) -> Path:
    matches = list(stems_track_dir.glob(f"**/{stem_name}.wav"))
    if not matches:
        raise FileNotFoundError(
            f"Missing demucs stem {stem_name}.wav under {stems_track_dir} (htdemucs_6s expected)."
        )
    # Prefer the shallowest match for stability across demucs versions.
    matches.sort(key=lambda p: len(p.parts))
    return matches[0]


def _write_placeholder_stems(song_wav_path: Path, stems_dir: Path) -> dict[str, str]:
    stems_dir.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    for key in STEM_KEYS:
        dest = stems_dir / f"{key}.wav"
        shutil.copyfile(song_wav_path, dest)
        # Placeholders are derived from ingest's normalized contract; enforce
        # sr/channels so downstream steps don't silently inherit bad audio.
        if not _is_readable_nonempty_wav(dest):
            raise SeparationError(f"Placeholder stem {dest} is not a valid {TARGET_SR}Hz mono WAV.")
        with wave.open(str(dest), "rb") as wf:
            if wf.getframerate() != TARGET_SR or wf.getnchannels() != 1:
                raise SeparationError(f"Placeholder stem {dest} must be {TARGET_SR}Hz mono.")
        mapping[key] = _rel_to_backend_root(dest)
    return mapping


def separate_song_to_stems(
    song_wav_path: Path,
    job_dir: Path,
    *,
    cleanup_demucs_outputs: bool = True,
) -> dict[str, str]:
    """Separate `song_wav_path` into six stems and return JSON-ready relative paths.
    
    Performance features:
    - Checks stem cache by audio hash to avoid re-running Demucs
    - Uses htdemucs_ft when HARMONIQ_FAST_STEMS=1 (faster but lower quality)
    - Skips separation when HARMONIQ_SKIP_STEMS=1 (placeholder stems)
    """
    if not song_wav_path.exists():
        raise SeparationError(f"Input song.wav missing: {song_wav_path}")

    stems_dir = job_dir / "stems"
    model = _get_demucs_model()

    if _should_skip_demucs():
        skip_reason = (
            "HARMONIQ_SKIP_STEMS" if os.getenv("HARMONIQ_SKIP_STEMS") == "1" 
            else "HARMONIQ_SKIP_DEMUCS" if os.getenv("HARMONIQ_SKIP_DEMUCS") == "1"
            else "pytest"
        )
        logger.info("Skipping demucs (%s) for job_dir=%s", skip_reason, job_dir)
        return _write_placeholder_stems(song_wav_path, stems_dir)

    # Check cache first
    audio_hash = _get_audio_hash(song_wav_path)
    cache_dir = _get_stem_cache_dir() / audio_hash
    
    if cache_dir.exists():
        logger.info("Stem cache hit for hash=%s (job_dir=%s)", audio_hash[:8], job_dir)
        try:
            # Update access time for LRU cleanup
            cache_dir.touch()
            return _load_cached_stems(cache_dir, stems_dir)
        except Exception as e:
            logger.warning("Cache hit but failed to load stems: %s. Re-running separation.", e)
            shutil.rmtree(cache_dir, ignore_errors=True)

    demucs_out_dir = job_dir / "_demucs"
    logger.info(
        "Running Demucs model=%s for job_dir=%s (cache miss: hash=%s)",
        model,
        job_dir,
        audio_hash[:8],
    )
    
    start_time = time.time()
    try:
        stems_track_dir = run_demucs_htdemucs_6s(song_wav_path, demucs_out_dir, model=model)
        elapsed = time.time() - start_time
        logger.info("Demucs separation completed in %.2fs (model=%s)", elapsed, model)

        stems_dir.mkdir(parents=True, exist_ok=True)
        mapping: dict[str, str] = {}
        for key in STEM_KEYS:
            src = _find_stem_file(stems_track_dir, key)
            dest = stems_dir / f"{key}.wav"
            shutil.copyfile(src, dest)
            if not _is_readable_nonempty_wav(dest):
                raise SeparationError(f"Demucs output {dest} is missing or not a readable WAV.")
            mapping[key] = _rel_to_backend_root(dest)
        
        # Save to cache for future runs
        try:
            _save_stems_to_cache(stems_dir, cache_dir)
            logger.info("Stems cached for hash=%s", audio_hash[:8])
        except Exception as e:
            logger.warning("Failed to cache stems: %s", e)
        
        return mapping
    except Exception as e:
        # Provide an actionable error for end users.
        msg = (
            "Demucs stem separation failed. Try a studio recording or a different upload. "
            "If this keeps happening, check that demucs model weights are available."
        )
        raise SeparationError(msg) from e
    finally:
        if cleanup_demucs_outputs:
            shutil.rmtree(demucs_out_dir, ignore_errors=True)

