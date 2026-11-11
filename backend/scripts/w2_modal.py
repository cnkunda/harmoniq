"""Modal app: run the W2 teacher comparison on a cloud GPU.

Prerequisites (once)::

    pip install modal && modal token new
    modal volume create harmoniq-w2

    # build the bundle locally (from backend/) and upload it to the volume
    python scripts/stage_w2_cloud_bundle.py --out /tmp/w2_bundle
    modal volume put harmoniq-w2 /tmp/w2_bundle /w2

Run (from backend/)::

    # sanity check: teacher availability + cache coverage
    modal run scripts/w2_modal.py::status

    # full comparison on an A10G
    modal run scripts/w2_modal.py::compare --teachers mt3,mr_mt3,yourmt3,musicfm

    # sharded / cache-only (resumable)
    modal run scripts/w2_modal.py::compare --teachers mr_mt3
    modal run scripts/w2_modal.py::compare --teachers yourmt3
    modal run scripts/w2_modal.py::compare --teachers mt3,mr_mt3,yourmt3,musicfm --cached-only true

Fetch results::

    modal volume get harmoniq-w2 /w2/docs/audit/amt ./amt
    modal volume get harmoniq-w2 /w2/backend/data/evaluation/teacher_outputs ./teacher_outputs

The MT3 baseline is scored from the uploaded cache, so JAX/T5X is not needed.
Checkpoints are downloaded into the volume on first run (sha256-verified).
"""

from __future__ import annotations

import os
import subprocess

import modal

app = modal.App("harmoniq-w2")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libsndfile1")
    .pip_install(
        "pydantic>=2.0",
        "numpy>=1.26",
        "scipy>=1.11",
        "librosa>=0.10.2",
        "soundfile>=0.13",
        "pretty_midi>=0.2.10",
        "mido>=1.3",
        "pyyaml>=6.0",
        "tqdm>=4.67",
        "requests>=2.31",
        "packaging>=23.0",
        "einops>=0.7",
        "absl-py>=2.0",
        # Match the local environment that produced the existing cache.
        "torch==2.5.1",
        "torchaudio==2.5.1",
        # mt3-infer 0.2.0 needs T5Block.forward(past_key_values=...) (plural,
        # transformers 5.x) AND ModuleUtilsMixin.get_extended_attention_mask
        # (removed in 5.17), so 5.13.x is the compatible window.
        "transformers==5.13.0",
        "mt3-infer @ git+https://github.com/openmirlab/mt3-infer.git",
    )
)

volume = modal.Volume.from_name("harmoniq-w2", create_if_missing=True)

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

ROOT = "/w2"
BACKEND = f"{ROOT}/backend"
CHECKPOINT_DIR = f"{BACKEND}/data/models/mt3infer"
REPORT_DIR = f"{ROOT}/docs/audit/amt"


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def _find_bundle_root() -> str | None:
    """Locate the bundle root (the dir containing ``backend/``) under /w2."""
    if os.path.isdir(os.path.join(ROOT, "backend")):
        return ROOT
    try:
        entries = sorted(os.listdir(ROOT))
    except FileNotFoundError:
        return None
    for name in entries:
        candidate = os.path.join(ROOT, name)
        if os.path.isdir(os.path.join(candidate, "backend")):
            return candidate
    return None


def _apply_root(root: str) -> None:
    global BACKEND, CHECKPOINT_DIR, REPORT_DIR
    BACKEND = os.path.join(root, "backend")
    CHECKPOINT_DIR = os.path.join(BACKEND, "data", "models", "mt3infer")
    REPORT_DIR = os.path.join(root, "docs", "audit", "amt")


def _ensure_bundle() -> None:
    """Locate the uploaded bundle, extracting w2_bundle.tgz if necessary."""
    root = _find_bundle_root()
    if root is not None:
        _apply_root(root)
        return

    # Tarball fallback: accept /w2/w2_bundle.tgz or /w2/<dir>/w2_bundle.tgz.
    import tarfile

    for dirpath, dirnames, filenames in os.walk(ROOT):
        depth = dirpath[len(ROOT):].count(os.sep)
        if depth > 1:
            dirnames[:] = []
            continue
        if "w2_bundle.tgz" in filenames:
            tarball = os.path.join(dirpath, "w2_bundle.tgz")
            print(f"[setup] extracting {tarball}", flush=True)
            with tarfile.open(tarball) as archive:
                archive.extractall(dirpath)
            volume.commit()
            root = _find_bundle_root()
            if root is not None:
                _apply_root(root)
                return

    listing = "\n".join(
        os.path.join(dirpath, name)
        for dirpath, dirnames, filenames in os.walk(ROOT)
        for name in sorted(dirnames) + sorted(filenames)
    ) or "(volume /w2 is empty)"
    raise FileNotFoundError(
        "W2 bundle not found in the Modal volume. Upload it first:\n"
        "  modal volume put harmoniq-w2 /tmp/w2_bundle /w2\n"
        "  modal volume ls harmoniq-w2 /w2\n\n"
        f"Current /w2 contents:\n{listing}"
    )


def _ensure_checkpoint(rel: str, url: str, sha256: str) -> None:
    import hashlib
    import urllib.request

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
    volume.commit()


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


def _summaries_text() -> str:
    import json

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


@app.function(image=image, gpu="A10G", timeout=6 * 60 * 60, volumes={ROOT: volume})
def compare(
    teachers: str = "mt3,mr_mt3,yourmt3,musicfm",
    refresh: str = "false",
    offset: str = "0",
    limit: str = "0",
    cached_only: str = "false",
) -> str:
    """Run the W2 comparison and return the Markdown report."""
    _ensure_bundle()
    _ensure_checkpoints()
    os.makedirs(REPORT_DIR, exist_ok=True)

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
    if int(offset or 0):
        command += ["--offset", str(int(offset))]
    if int(limit or 0):
        command += ["--limit", str(int(limit))]
    if _truthy(refresh):
        command.append("--refresh")
    if _truthy(cached_only):
        command.append("--cached-only")
    else:
        command += ["--device", "cuda"]

    print("[run] " + " ".join(command), flush=True)
    subprocess.run(command, cwd=BACKEND, env=_env(), check=True)
    volume.commit()

    with open(
        os.path.join(REPORT_DIR, "w2_teacher_comparison.md"), encoding="utf-8"
    ) as handle:
        markdown = handle.read()
    print("[run] " + _summaries_text(), flush=True)
    return markdown


@app.function(image=image, timeout=600, volumes={ROOT: volume})
def status() -> str:
    """Teacher availability + cache coverage (CPU only, cheap)."""
    _ensure_bundle()
    _ensure_checkpoints()
    script = (
        "import json;"
        "from app.teachers import teacher_statuses;"
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
    import json

    caches = {}
    for teacher in ("mt3", "mr_mt3", "yourmt3"):
        path = os.path.join(
            BACKEND, "data", "evaluation", "teacher_outputs", teacher
        )
        caches[teacher] = len(os.listdir(path)) if os.path.isdir(path) else 0
    text = result.stdout + "\ncache files: " + json.dumps(caches)
    print(text, flush=True)
    return text


@app.function(image=image, timeout=300, volumes={ROOT: volume})
def ls() -> str:
    """List the volume contents under /w2 (debug helper)."""
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        depth = dirpath[len(ROOT):].count(os.sep)
        if depth >= 2:
            dirnames[:] = []
            continue
        for name in sorted(dirnames):
            lines.append(os.path.join(dirpath, name) + "/")
        for name in sorted(filenames):
            lines.append(os.path.join(dirpath, name))
    text = "\n".join(lines) or "(volume /w2 is empty)"
    print(text, flush=True)
    return text


@app.function(image=image, timeout=600, volumes={ROOT: volume})
def diagnose() -> str:
    """Print runtime versions and the first per-track teacher errors."""
    import glob
    import json
    import sys

    _ensure_bundle()
    lines = [f"bundle backend: {BACKEND}", f"python: {sys.version.split()[0]}"]

    def _try(label: str, fn):
        try:
            lines.append(fn())
        except Exception as exc:  # reported, not raised
            lines.append(f"{label} failed: {type(exc).__name__}: {exc}")

    def _torch():
        import torch

        cuda = torch.cuda.is_available()
        name = torch.cuda.get_device_name(0) if cuda else "-"
        return f"torch {torch.__version__} cuda={cuda} device={name}"

    def _mt3_infer():
        import mt3_infer

        return f"mt3_infer {mt3_infer.__version__}"

    def _transformers():
        import transformers

        return f"transformers {transformers.__version__}"

    _try("torch", _torch)
    _try("mt3_infer", _mt3_infer)
    _try("transformers", _transformers)

    for teacher in ("mr_mt3", "yourmt3"):
        directory = os.path.join(
            BACKEND, "data", "evaluation", "teacher_outputs", teacher
        )
        files = sorted(glob.glob(os.path.join(directory, "*.json")))
        errors = 0
        for path in files:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            error = payload.get("metadata", {}).get("error")
            if not error:
                continue
            errors += 1
            if errors <= 3:
                lines.append(f"[{teacher}] {os.path.basename(path)}: {error[:700]}")
        lines.append(f"[{teacher}] cache_files={len(files)} error_files={errors}")
    text = "\n".join(lines)
    print(text, flush=True)
    return text


@app.function(image=image, timeout=600, volumes={ROOT: volume})
def purge_errors(teachers: str = "mr_mt3,yourmt3") -> str:
    """Delete cached teacher outputs that recorded an error, so they re-run."""
    import glob
    import json

    _ensure_bundle()
    removed: dict[str, int] = {}
    for teacher in [name.strip() for name in teachers.split(",") if name.strip()]:
        directory = os.path.join(
            BACKEND, "data", "evaluation", "teacher_outputs", teacher
        )
        count = 0
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if payload.get("metadata", {}).get("error"):
                os.remove(path)
                count += 1
        removed[teacher] = count
    volume.commit()
    text = "removed error caches: " + json.dumps(removed)
    print(text, flush=True)
    return text


@app.local_entrypoint()
def main() -> None:
    print(status.remote())
