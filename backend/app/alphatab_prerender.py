"""AlphaTab SVG prerender via Node subprocess — PRIORITIES §59."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from app.ingest import get_data_dir, get_job_dir
from app.schemas import AlphaTabPrerenderBundle, AlphaTabPrerenderHints, LessonJSON

logger = logging.getLogger("harmoniq.alphatab_prerender")
logger.setLevel(logging.INFO)

# Bump when preset dimensions change — invalidates disk cache independently of PIPELINE_VERSION.
PRERENDER_PRESET_VERSION = "study-v1"
# Must match Harmoniq frontend `AlphaTabWeb.web.tsx` (`ALPHATAB_PKG_VERSION`).
ALPHATAB_EXPECT_VERSION = "1.6.1"


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _prerender_cache_dir() -> Path:
    p = get_data_dir() / "cache" / "alphatab_prerender"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def prerender_enabled() -> bool:
    """Off by default; enable with HARMONIQ_ENABLE_PRERENDER=1."""
    if _env_truthy("HARMONIQ_SKIP_PRERENDER"):
        return False
    return _env_truthy("HARMONIQ_ENABLE_PRERENDER")


def score_sha256_from_gp5_base64(gp5_base64: str) -> str:
    raw = __import__("base64").b64decode(gp5_base64.strip(), validate=False)
    return hashlib.sha256(raw).hexdigest()


def prerender_cache_key(score_sha256: str) -> str:
    raw = f"{ALPHATAB_EXPECT_VERSION}:{PRERENDER_PRESET_VERSION}:{score_sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_file_path(cache_key: str) -> Path:
    safe = cache_key.translate(str.maketrans({":": "__", "|": "__"}))
    return _prerender_cache_dir() / f"{safe}.json"


def _node_script_path() -> Path:
    return _backend_root() / "scripts" / "alphatab_prerender.mjs"


def _study_preset_payload() -> dict[str, float]:
    # Matches `TAB_RENDER_PRESETS.study` in `src/session/tabThemePresets.ts`.
    return {"scale": 1.1, "stretchForce": 1.0}


def _run_node_prerender(gp5_base64: str) -> dict[str, object]:
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("node binary not found on PATH")
    script = _node_script_path()
    if not script.is_file():
        raise RuntimeError(f"alphatab_prerender script missing at {script}")
    payload = json.dumps({"gp5_base64": gp5_base64, "preset": _study_preset_payload()})
    proc = subprocess.run(
        [node_bin, str(script)],
        input=payload.encode("utf-8"),
        cwd=str(_backend_root()),
        capture_output=True,
        timeout=120,
        check=False,
    )
    out_txt = proc.stdout.decode("utf-8", errors="replace").strip()
    if not out_txt:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"node prerender produced empty stdout; stderr={err!r}")
    try:
        data = json.loads(out_txt)
    except json.JSONDecodeError as e:
        logger.error("alphatab_prerender invalid JSON stdout (first 240 chars): %s", out_txt[:240])
        raise RuntimeError("node prerender stdout is not JSON") from e
    if not data.get("ok"):
        err_detail = proc.stderr.decode("utf-8", errors="replace").strip()
        msg = str(data.get("error") or "alphatab_prerender reported ok=false")
        if err_detail:
            msg = f"{msg} ({err_detail[:500]})"
        raise RuntimeError(msg)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"node prerender failed after ok: {err}")
    return data


def load_cached_bundle(cache_key: str) -> AlphaTabPrerenderBundle | None:
    p = _cache_file_path(cache_key)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return AlphaTabPrerenderBundle.model_validate(raw)
    except Exception:
        logger.exception("failed reading prerender cache path=%s", p)
        return None


def save_cached_bundle(cache_key: str, bundle: AlphaTabPrerenderBundle) -> None:
    p = _cache_file_path(cache_key)
    p.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")


def compute_prerender_bundle(gp5_base64: str, *, score_sha256: str) -> AlphaTabPrerenderBundle | None:
    """Return bundle or None on failure (caller keeps lesson usable)."""
    cache_key = prerender_cache_key(score_sha256)
    cached = load_cached_bundle(cache_key)
    if cached is not None:
        return cached.model_copy(update={"preset_version": PRERENDER_PRESET_VERSION, "score_sha256": score_sha256})

    try:
        raw = _run_node_prerender(gp5_base64)
    except Exception:
        logger.exception("alphatab_prerender subprocess failed score_sha=%s…", score_sha256[:12])
        return None

    at_ver = str(raw.get("alphatab_version") or ALPHATAB_EXPECT_VERSION)
    partials_raw = raw.get("partials") or []
    partials_dicts: list[dict[str, object]] = []
    if isinstance(partials_raw, list):
        for item in partials_raw:
            if isinstance(item, dict):
                partials_dicts.append(item)

    bundle = AlphaTabPrerenderBundle.model_validate(
        {
            "ok": True,
            "alphatab_version": at_ver,
            "preset_version": PRERENDER_PRESET_VERSION,
            "score_sha256": score_sha256,
            "master_bar_count": int(raw.get("master_bar_count") or 0),
            "total_width": int(raw.get("total_width") or 0),
            "total_height": int(raw.get("total_height") or 0),
            "partial_count": int(raw.get("partial_count") or len(partials_dicts)),
            "partials": partials_dicts,
        }
    )
    try:
        save_cached_bundle(cache_key, bundle)
    except Exception:
        logger.exception("failed saving prerender cache key=%s", cache_key[:16])
    return bundle


def enrich_lesson_with_prerender_hints(lesson: LessonJSON, *, job_id: str, gp5_base64: str) -> LessonJSON:
    """Attach hints + job-local JSON artifact when prerender succeeds; no-op if disabled or failed."""
    if not prerender_enabled():
        return lesson
    if not gp5_base64.strip():
        return lesson
    try:
        sh = score_sha256_from_gp5_base64(gp5_base64)
    except Exception:
        logger.exception("prerender: could not decode gp5 base64 for job_id=%s", job_id)
        return lesson

    ck = prerender_cache_key(sh)
    bundle = compute_prerender_bundle(gp5_base64, score_sha256=sh)
    if bundle is None or not bundle.partials:
        return lesson

    artifact_name = f"alphatab_prerender_{PRERENDER_PRESET_VERSION}.json"
    artifact_path = get_job_dir(job_id) / artifact_name
    try:
        artifact_path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    except Exception:
        logger.exception("prerender: failed writing artifact job_id=%s", job_id)
        return lesson

    backend_root = get_data_dir().parent
    artifact_rel = str(artifact_path.resolve().relative_to(backend_root.resolve()).as_posix())

    hints = AlphaTabPrerenderHints(
        alphatab_version=bundle.alphatab_version,
        preset_version=bundle.preset_version,
        score_sha256=sh,
        cache_key=ck,
        master_bar_count=bundle.master_bar_count,
        total_width=bundle.total_width,
        total_height=bundle.total_height,
        partial_count=bundle.partial_count,
        artifact_rel=artifact_rel,
    )
    return lesson.model_copy(update={"alphatab_prerender_hints": hints})
