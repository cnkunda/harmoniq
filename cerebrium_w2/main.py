"""Cerebrium entrypoint — W2 teacher comparison on a cloud GPU.

The fixed 50-track W2 bundle (audio, ground truth, and the existing teacher
cache) lives in Cerebrium persistent storage, not in the deployment image:

    cerebrium cp /tmp/w2_bundle.tgz w2_bundle.tgz

The first run extracts it to /persistent-storage/w2 and downloads the
PyTorch teacher checkpoints (sha256-verified); later runs reuse both.

Usage (from this directory)::

    cerebrium run main.py::run --teachers mt3,mr_mt3,yourmt3,musicfm
    cerebrium run main.py::status            # teacher availability + cache counts
    cerebrium run main.py::run --teachers mr_mt3 --offset 0 --limit 10
    cerebrium run main.py::run --teachers mt3,mr_mt3,yourmt3,musicfm --cached-only true

Results are written to /persistent-storage/w2/docs/audit/amt/ and the teacher
cache to /persistent-storage/w2/backend/data/evaluation/teacher_outputs/.
Download them with::

    cerebrium download w2/docs/audit/amt/w2_teacher_comparison.md
    cerebrium download w2/docs/audit/amt/w2_teacher_comparison.json
    cerebrium download w2/backend/data/evaluation/teacher_outputs
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import urllib.request

STORAGE = "/persistent-storage"
BUNDLE_TGZ = os.path.join(STORAGE, "w2_bundle.tgz")
ROOT = os.path.join(STORAGE, "w2")
BACKEND = os.path.join(ROOT, "backend")
CHECKPOINT_DIR = os.path.join(BACKEND, "data", "models", "mt3infer")
REPORT_DIR = os.path.join(ROOT, "docs", "audit", "amt")

MR_MT3_URL = "https://huggingface.co/gudgud1014/MR-MT3/resolve/main/mt3.pth"
MR_MT3_SHA = "b8a3807ed265059abd25ad7f68142c06c35e8f6144dcaa45bd55946a3745398f"
YOURMT3_REL = (
    "yourmt3/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops"
    "/last.ckpt"
)
YOURMT3_URL = (
    "https://huggingface.co/spaces/mimbres/YourMT3/resolve/main/amt/logs/2024/"
    "mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops/"
    "checkpoints/last.ckpt"
)
YOURMT3_SHA = "ae38e415c79efd5592dcb9b658cdb99ddb11d4c4e1eaa364cab04a052473fc25"


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def _extract_bundle() -> None:
    if os.path.isdir(BACKEND):
        return
    if not os.path.isfile(BUNDLE_TGZ):
        raise FileNotFoundError(
            f"{BUNDLE_TGZ} not found. Upload the bundle first:\n"
            "  cerebrium cp /tmp/w2_bundle.tgz w2_bundle.tgz"
        )
    print(f"[setup] extracting {BUNDLE_TGZ} -> {ROOT}", flush=True)
    os.makedirs(ROOT, exist_ok=True)
    with tarfile.open(BUNDLE_TGZ) as archive:
        try:
            archive.extractall(ROOT, filter="data")
        except TypeError:  # Python < 3.11.4 has no extraction filter
            archive.extractall(ROOT)
    print("[setup] bundle extracted", flush=True)


def _ensure_checkpoint(rel: str, url: str, sha256: str) -> None:
    dest = os.path.join(CHECKPOINT_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest):
        digest = hashlib.sha256()
        with open(dest, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() == sha256:
            print(f"[checkpoint] present: {rel}", flush=True)
            return
        print(f"[checkpoint] checksum mismatch, re-downloading: {rel}", flush=True)
        os.remove(dest)
    print(f"[checkpoint] downloading {rel}", flush=True)
    tmp = dest + ".tmp"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)


def _ensure_checkpoints() -> None:
    _ensure_checkpoint("mr_mt3/mt3.pth", MR_MT3_URL, MR_MT3_SHA)
    _ensure_checkpoint(YOURMT3_REL, YOURMT3_URL, YOURMT3_SHA)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HARMONIQ_MT3_CHECKPOINT_DIR": CHECKPOINT_DIR,
            "HARMONIQ_TEACHER_DEVICE": "cuda",
            "HARMONIQ_TEACHER_TIMEOUT_S": "14400",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def _compare_command(
    teachers: str,
    refresh: bool,
    offset: int,
    limit: int,
    cached_only: bool,
) -> list[str]:
    command = [
        "python",
        "scripts/compare_teachers.py",
        "--teachers",
        teachers,
        "--report",
        os.path.join(REPORT_DIR, "w2_teacher_comparison.json"),
        "--markdown",
        os.path.join(REPORT_DIR, "w2_teacher_comparison.md"),
    ]
    if offset:
        command += ["--offset", str(offset)]
    if limit:
        command += ["--limit", str(limit)]
    if refresh:
        command.append("--refresh")
    if cached_only:
        command.append("--cached-only")
    else:
        command += ["--device", "cuda"]
    return command


def _summaries_text() -> str:
    path = os.path.join(REPORT_DIR, "w2_teacher_comparison.json")
    if not os.path.isfile(path):
        return "(no report yet)"
    with open(path, encoding="utf-8") as handle:
        report = json.load(handle)
    lines = [f"decision: {report['decision']['status']}"]
    if report["decision"].get("recommended_teacher"):
        lines.append(f"recommended: {report['decision']['recommended_teacher']}")
    for name, summary in report["summaries"].items():
        lines.append(
            f"{name}: {summary.get('completed', 0)}/{summary.get('tracks', 0)} "
            f"completed, chord_acc={summary.get('chord_frame_accuracy')}, "
            f"onset_f1={summary.get('onset_f1')}, "
            f"leakage={summary.get('leakage_rate')}, rtf={summary.get('rtf')}"
        )
    return "\n".join(lines)


def run(
    teachers: str = "mt3,mr_mt3,yourmt3,musicfm",
    refresh: str = "false",
    offset: str = "0",
    limit: str = "0",
    cached_only: str = "false",
) -> str:
    """Run the W2 comparison and return the Markdown report."""
    _extract_bundle()
    _ensure_checkpoints()
    os.makedirs(REPORT_DIR, exist_ok=True)

    command = _compare_command(
        teachers=teachers,
        refresh=_truthy(refresh),
        offset=int(offset or 0),
        limit=int(limit or 0),
        cached_only=_truthy(cached_only),
    )
    print("[run] " + " ".join(command), flush=True)
    subprocess.run(command, cwd=BACKEND, env=_env(), check=True)

    report_path = os.path.join(REPORT_DIR, "w2_teacher_comparison.md")
    with open(report_path, encoding="utf-8") as handle:
        markdown = handle.read()
    print("[run] " + _summaries_text(), flush=True)
    return markdown


def status() -> str:
    """Print teacher availability and cache coverage (sanity check)."""
    _extract_bundle()
    _ensure_checkpoints()
    script = (
        "import json;"
        "from app.teachers import teacher_statuses;"
        "from app.evaluation.manifest import load_manifest;"
        "from app.evaluation.manifest import resolve_track_paths;"
        "print(json.dumps(teacher_statuses(), indent=1))"
    )
    result = subprocess.run(
        ["python", "-c", script],
        cwd=BACKEND,
        env=_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    caches = {}
    for teacher in ("mt3", "mr_mt3", "yourmt3"):
        path = os.path.join(
            BACKEND, "data", "evaluation", "teacher_outputs", teacher
        )
        caches[teacher] = len(os.listdir(path)) if os.path.isdir(path) else 0
    return result.stdout + "\ncache files: " + json.dumps(caches)
