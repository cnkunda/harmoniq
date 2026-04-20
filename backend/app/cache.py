"""Disk-backed analysis cache keyed by normalized audio hash + pipeline version."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

from app.ingest import get_data_dir, get_job_dir
from app.schemas import LessonJSON, PlayerProfile

logger = logging.getLogger("harmoniq.cache")
logger.setLevel(logging.INFO)

# Bump this to invalidate all existing cache entries.
PIPELINE_VERSION = "1"


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


def load_cached_lesson_for_wav(wav_path: Path, *, player_profile: PlayerProfile | None = None) -> LessonJSON | None:
    """Return cached lesson for this audio hash/version (and profile segment), or None."""
    key = cache_key_for_wav_and_profile(wav_path, player_profile)
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


def save_cached_lesson_for_wav(
    wav_path: Path, lesson: LessonJSON, *, player_profile: PlayerProfile | None = None
) -> None:
    key = cache_key_for_wav_and_profile(wav_path, player_profile)
    p = _cache_path(key)
    payload = {
        "pipeline_version": PIPELINE_VERSION,
        "audio_sha256": key.split(":", 1)[1],
        "lesson_json": lesson.model_dump(mode="json"),
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
        return None
    wav_src = backend_root / wav_rel
    if not _copy_if_present(wav_src, target_wav):
        return None

    source_stems = cached_lesson.stems or {}
    if not source_stems:
        return None

    remapped_stems: dict[str, str] = {}
    for stem_name, stem_rel in source_stems.items():
        if not isinstance(stem_rel, str):
            return None
        src = backend_root / stem_rel
        dst = job_dir / "stems" / f"{stem_name}.wav"
        if not _copy_if_present(src, dst):
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
