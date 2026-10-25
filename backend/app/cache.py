"""Disk-backed analysis cache keyed by normalized audio hash + pipeline version."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from app.ingest import get_data_dir, get_job_dir
from app.schemas import LessonJSON, PlayerProfile

if TYPE_CHECKING:
    from app.audio_fingerprint import AudioFingerprint

logger = logging.getLogger("harmoniq.cache")
logger.setLevel(logging.INFO)

# Bump this to invalidate all existing cache entries.
PIPELINE_VERSION = "1"
FINGERPRINT_SIDECAR_SUFFIX = ".fingerprint.json"


@dataclass(frozen=True)
class CacheLookupResult:
    """Outcome of one cache lookup (SHA first, then fingerprint)."""

    lesson: LessonJSON | None
    kind: Literal["sha_hit", "fingerprint_hit", "miss"]
    similarity: float
    matched_hashes: int
    cache_key: str | None
    fingerprint: AudioFingerprint | None = None


def _backend_root() -> Path:
    return get_data_dir().parent


def _cache_dir() -> Path:
    p = get_data_dir() / "cache" / "analysis"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path(cache_key: str) -> Path:
    # Keep human-readable cache files while remaining valid on Windows paths.
    safe = cache_key.translate(str.maketrans({":": "__", "|": "__"}))
    return _cache_dir() / f"{safe}.json"


def _fingerprint_path(cache_key: str) -> Path:
    return _cache_path(cache_key).with_suffix(FINGERPRINT_SIDECAR_SUFFIX)


def _record_cache_lookup(result: str) -> None:
    """Best-effort Prometheus counter; cache must keep working without metrics."""
    try:
        from app.metrics import analysis_cache_lookups_total
    except ImportError:
        logger.debug("cache lookup metrics unavailable")
        return
    analysis_cache_lookups_total.labels(result=result).inc()


def audio_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def cache_key_for_audio_hash(audio_hash: str) -> str:
    return f"{PIPELINE_VERSION}:{audio_hash}"


def _profile_cache_suffix(profile: PlayerProfile | None) -> str:
    """Differentiate cache entries when coach output is personalized by profile."""
    if profile is None:
        return ""
    data = profile.model_dump(mode="json", exclude_none=True)
    weak = data.get("weak_areas") or []
    nodes = data.get("skill_nodes") or []
    taste = data.get("taste_profile")
    lc = data.get("learning_context")
    if not weak and not nodes and not taste and not lc:
        return ""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    short = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"|p:{short}"


def cache_key_for_wav_and_profile(wav_path: Path, profile: PlayerProfile | None) -> str:
    base = cache_key_for_audio_hash(audio_sha256(wav_path))
    return base + _profile_cache_suffix(profile)


def _load_cached_lesson_for_key(key: str) -> LessonJSON | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        lesson_payload = payload.get("lesson_json")
        if not isinstance(lesson_payload, dict):
            return None
        lesson = LessonJSON.model_validate(lesson_payload)
        if not (lesson.style_label or "").strip():
            lesson = lesson.model_copy(update={"style_label": "general"})
        return lesson
    except Exception:
        logger.exception("Failed to read analysis cache entry path=%s", p)
        return None


def load_cached_lesson_for_wav(wav_path: Path, *, player_profile: PlayerProfile | None = None) -> LessonJSON | None:
    """Return cached lesson for this audio hash/version (and profile segment), or None."""
    key = cache_key_for_wav_and_profile(wav_path, player_profile)
    return _load_cached_lesson_for_key(key)


def save_cached_lesson_for_wav(
    wav_path: Path,
    lesson: LessonJSON,
    *,
    player_profile: PlayerProfile | None = None,
    fingerprint: AudioFingerprint | None = None,
) -> None:
    key = cache_key_for_wav_and_profile(wav_path, player_profile)
    p = _cache_path(key)
    payload = {
        "pipeline_version": PIPELINE_VERSION,
        "audio_sha256": key.split(":", 1)[1],
        "lesson_json": lesson.model_dump(mode="json"),
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if fingerprint is not None and fingerprint.hashes.size:
        sidecar = {
            "fingerprint_version": fingerprint.version,
            "cache_key": key,
            "pipeline_version": PIPELINE_VERSION,
            "profile_suffix": _profile_cache_suffix(player_profile),
            "audio_sha256": key.split(":", 1)[1],
            **fingerprint.to_payload(),
        }
        try:
            _fingerprint_path(key).write_text(
                json.dumps(sidecar, separators=(",", ":")),
                encoding="utf-8",
            )
            logger.info(
                "fingerprint saved key=%s hashes=%d",
                key.split(":", 1)[1][:8],
                fingerprint.hashes.size,
            )
        except OSError:
            # Fingerprinting is an optimization; a sidecar write failure must
            # not fail a job whose lesson cache was already saved.
            logger.exception("Failed to write fingerprint sidecar key=%s", key[:16])


def _find_fingerprint_match(
    fingerprint: AudioFingerprint,
    *,
    player_profile: PlayerProfile | None,
) -> tuple[LessonJSON, float, int, str] | None:
    from app.audio_fingerprint import (
        FINGERPRINT_MIN_MATCHED_HASHES,
        FINGERPRINT_SIMILARITY_THRESHOLD,
        AudioFingerprint as FingerprintType,
        compare_fingerprints,
    )

    profile_suffix = _profile_cache_suffix(player_profile)
    best: tuple[LessonJSON, float, int, str] | None = None

    for sidecar_path in _cache_dir().glob(f"{PIPELINE_VERSION}__*{FINGERPRINT_SIDECAR_SUFFIX}"):
        try:
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if payload.get("pipeline_version") != PIPELINE_VERSION:
                continue
            if payload.get("profile_suffix", "") != profile_suffix:
                continue
            candidate = FingerprintType.from_payload(payload)
            if candidate.version != fingerprint.version:
                continue
            similarity, matched = compare_fingerprints(fingerprint, candidate)
            if matched < FINGERPRINT_MIN_MATCHED_HASHES:
                continue
            if similarity < FINGERPRINT_SIMILARITY_THRESHOLD:
                continue
            cache_key = payload.get("cache_key")
            if not isinstance(cache_key, str):
                logger.warning("fingerprint sidecar missing cache_key path=%s", sidecar_path)
                continue
            lesson = _load_cached_lesson_for_key(cache_key)
            if lesson is None:
                continue
            if best is None or (similarity, matched) > (best[1], best[2]):
                best = (lesson, similarity, matched, cache_key)
        except Exception:
            logger.warning("Failed to read fingerprint sidecar path=%s", sidecar_path, exc_info=True)

    return best


def lookup_cached_lesson(
    wav_path: Path,
    *,
    player_profile: PlayerProfile | None = None,
) -> CacheLookupResult:
    """Look up a cached lesson by SHA-256 first, then by landmark fingerprint."""
    key = cache_key_for_wav_and_profile(wav_path, player_profile)
    lesson = _load_cached_lesson_for_key(key)
    if lesson is not None:
        _record_cache_lookup("sha_hit")
        return CacheLookupResult(
            lesson=lesson,
            kind="sha_hit",
            similarity=1.0,
            matched_hashes=0,
            cache_key=key,
            fingerprint=None,
        )

    try:
        from app.audio_fingerprint import compute_fingerprint

        fingerprint = compute_fingerprint(wav_path)
    except Exception:
        logger.exception("fingerprint computation failed path=%s; SHA-only fallback", wav_path)
        _record_cache_lookup("miss")
        return CacheLookupResult(
            lesson=None,
            kind="miss",
            similarity=0.0,
            matched_hashes=0,
            cache_key=None,
            fingerprint=None,
        )

    match = _find_fingerprint_match(fingerprint, player_profile=player_profile)
    if match is not None:
        matched_lesson, similarity, matched_hashes, matched_key = match
        _record_cache_lookup("fingerprint_hit")
        return CacheLookupResult(
            lesson=matched_lesson,
            kind="fingerprint_hit",
            similarity=similarity,
            matched_hashes=matched_hashes,
            cache_key=matched_key,
            fingerprint=fingerprint,
        )

    _record_cache_lookup("miss")
    return CacheLookupResult(
        lesson=None,
        kind="miss",
        similarity=0.0,
        matched_hashes=0,
        cache_key=None,
        fingerprint=fingerprint,
    )


def invalidate_cache_key(cache_key: str) -> bool:
    """Remove one analysis cache entry and its fingerprint sidecar."""
    removed = False
    for path in (_cache_path(cache_key), _fingerprint_path(cache_key)):
        if path.exists():
            path.unlink()
            removed = True
    if removed:
        logger.info("cache invalidated for hash=%s", cache_key.split(":", 1)[1][:8])
    return removed


def invalidate_cache_for_wav(wav_path: Path, *, player_profile: PlayerProfile | None = None) -> bool:
    """Remove analysis cache entry for this audio hash/profile. Returns True if removed."""
    key = cache_key_for_wav_and_profile(wav_path, player_profile)
    return invalidate_cache_key(key)


def clear_analysis_cache() -> list[Path]:
    """
    Delete all analysis cache entry files and return removed paths.

    This only clears `data/cache/analysis/*.json` and does not touch job
    directories (including reused wav/stem artifacts under `data/jobs/`).
    """
    cache_dir = _cache_dir()
    removed: list[Path] = []
    for entry in cache_dir.glob("*.json"):
        try:
            entry.unlink()
            removed.append(entry)
        except FileNotFoundError:
            # Ignore races / already-deleted entries for idempotence.
            continue
    return removed


def _copy_if_present(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def reuse_cached_artifacts_into_job(cached_lesson: LessonJSON, *, job_id: str) -> LessonJSON | None:
    """
    Copy wav/stems referenced by cached lesson into this job directory.

    Returns a job-scoped LessonJSON when all required artifacts are present.
    Returns None if any required artifact is missing, which signals recompute.
    """
    backend_root = _backend_root()
    job_dir = get_job_dir(job_id)
    target_wav = job_dir / "song.wav"

    wav_rel = getattr(cached_lesson, "wav_path", None)
    if not isinstance(wav_rel, str):
        logger.warning("cache_reuse missing wav_path in cached lesson for job=%s", job_id)
        return None
    wav_src = backend_root / wav_rel
    if not _copy_if_present(wav_src, target_wav):
        logger.warning("cache_reuse source wav missing src=%s job=%s", wav_src, job_id)
        return None

    source_stems = cached_lesson.stems or {}
    if not source_stems:
        logger.warning("cache_reuse no stems in cached lesson for job=%s", job_id)
        return None

    remapped_stems: dict[str, str] = {}
    for stem_name, stem_rel in source_stems.items():
        if not isinstance(stem_rel, str):
            logger.warning("cache_reuse non-string stem rel for stem=%s job=%s", stem_name, job_id)
            return None
        src = backend_root / stem_rel
        dst = job_dir / "stems" / f"{stem_name}.wav"
        if not _copy_if_present(src, dst):
            logger.warning("cache_reuse source stem missing src=%s stem=%s job=%s", src, stem_name, job_id)
            return None
        remapped_stems[stem_name] = str(dst.relative_to(backend_root).as_posix())

    lesson_payload = cached_lesson.model_dump(mode="json")
    lesson_payload["job_id"] = job_id
    lesson_payload["wav_path"] = str(target_wav.relative_to(backend_root).as_posix())
    lesson_payload["stems"] = remapped_stems

    hints_raw = lesson_payload.get("alphatab_prerender_hints")
    if isinstance(hints_raw, dict):
        art_rel = hints_raw.get("artifact_rel")
        if isinstance(art_rel, str) and art_rel.strip():
            src_a = (backend_root / art_rel.replace("\\", "/")).resolve()
            root_r = backend_root.resolve()
            if str(src_a).startswith(str(root_r)) and src_a.is_file():
                dst_a = job_dir / src_a.name
                shutil.copyfile(src_a, dst_a)
                lesson_payload["alphatab_prerender_hints"] = {
                    **hints_raw,
                    "artifact_rel": str(dst_a.relative_to(root_r).as_posix()),
                }
            else:
                lesson_payload.pop("alphatab_prerender_hints", None)
        else:
            lesson_payload.pop("alphatab_prerender_hints", None)

    return LessonJSON.model_validate(lesson_payload)
