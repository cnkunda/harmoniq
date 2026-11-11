"""Modal app: run the W5 calibration/quality evaluation on a cloud GPU.

Prerequisites (once)::

    pip install modal && modal token new
    modal volume create harmoniq-w5

    # from backend/: build a bundle and upload it
    python scripts/stage_w5_cloud_bundle.py --out /tmp/w5_bundle
    tar -C /tmp/w5_bundle -czf w5_bundle.tgz .
    modal volume put harmoniq-w5 w5_bundle.tgz /w5

Run (from backend/)::

    # 1-track GPU smoke first (JAX/T5X + CUDA)
    modal run scripts/w5_modal.py::smoke

    # full MT3 calibration, sharded by source, detached
    modal run --detach scripts/w5_modal.py::evaluate --source guitarset
    modal run --detach scripts/w5_modal.py::evaluate --source egset12
    modal run --detach scripts/w5_modal.py::evaluate --source idmt_smt_guitar
    modal run --detach scripts/w5_modal.py::evaluate --source guitar_techs
    modal run --detach scripts/w5_modal.py::evaluate --source rwc_p

    # aggregate calibration + quality gate
    modal run scripts/w5_modal.py::aggregate

Fetch artifacts::

    modal volume get harmoniq-w5 /w5/docs/audit/amt ./amt

The MT3 event confidence is a placeholder, so only chord-template confidence
is calibrated. Long runs are resumable through the prediction cache on the
volume; use ``--refresh true`` after changing the decoder.
"""

from __future__ import annotations

import os
import subprocess

import modal

app = modal.App("harmoniq-w5")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "libsndfile1", "build-essential")
    .pip_install(
        "tensorflow[and-cuda]==2.20.0",
        "tf_keras==2.20.1",
        "pydantic>=2.0",
        "numpy>=1.26,<3",
        "scipy>=1.11",
        "librosa>=0.10.2",
        "soundfile>=0.13",
        "scikit-learn>=1.3",
        "tqdm>=4.67",
        "tensorboard",
        "mt3 @ git+https://github.com/magenta/mt3.git",
        "jax[cuda12]>=0.4.20",
    )
    .env(
        {
            "TF_CPP_MIN_LOG_LEVEL": "3",
            "PYTHONUNBUFFERED": "1",
        }
    )
)

volume = modal.Volume.from_name("harmoniq-w5", create_if_missing=True)
# Reuse the datasets already staged by W2 (50-track sample, all sources) and
# W3 (full GuitarSet / EGSet12 / IDMT audio). This avoids a 10 GB re-upload
# while covering every source. Tracks not present in either volume are
# reported as skipped by the merged manifest helper.
w2_volume = modal.Volume.from_name("harmoniq-w2", create_if_missing=True)
w3_volume = modal.Volume.from_name("harmoniq-w3", create_if_missing=True)

ROOT = "/w5"
BACKEND = f"{ROOT}/backend"
REPORT_DIR = f"{ROOT}/docs/audit/amt"
SOURCES = ("guitarset", "egset12", "idmt_smt_guitar", "guitar_techs", "rwc_p")

_DATA_ROOTS = (
    "/w3/w3/backend",
    "/w3/backend",
    "/w2/w2/backend",
    "/w2/backend",
    "/w5/w5/backend",
    "/w5/backend",
)


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def _find_bundle_root() -> str | None:
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
    global BACKEND, REPORT_DIR
    BACKEND = os.path.join(root, "backend")
    REPORT_DIR = os.path.join(root, "docs", "audit", "amt")


def _ensure_bundle() -> None:
    root = _find_bundle_root()
    if root is not None:
        _apply_root(root)
        return

    import tarfile

    for dirpath, dirnames, filenames in os.walk(ROOT):
        depth = dirpath[len(ROOT):].count(os.sep)
        if depth > 1:
            dirnames[:] = []
            continue
        if "w5_bundle.tgz" in filenames:
            tarball = os.path.join(dirpath, "w5_bundle.tgz")
            print(f"[setup] extracting {tarball}", flush=True)
            with tarfile.open(tarball) as archive:
                archive.extractall(dirpath)
            volume.commit()
            root = _find_bundle_root()
            if root is not None:
                _apply_root(root)
                return

    # Large bundles are uploaded in chunks (the Modal client can drop a
    # multi-GB single-file upload on slow links). Join the parts first.
    chunk_dir = os.path.join(ROOT, "chunks")
    if os.path.isdir(chunk_dir):
        parts = sorted(
            os.path.join(chunk_dir, name)
            for name in os.listdir(chunk_dir)
            if name.startswith("w5_bundle.tgz.part-")
        )
        if parts:
            tarball = os.path.join(ROOT, "w5_bundle.tgz")
            print(f"[setup] joining {len(parts)} bundle chunks", flush=True)
            with open(tarball, "wb") as output:
                for part in parts:
                    with open(part, "rb") as handle:
                        while True:
                            block = handle.read(64 * 1024 * 1024)
                            if not block:
                                break
                            output.write(block)
            print(f"[setup] extracting {tarball}", flush=True)
            with tarfile.open(tarball) as archive:
                archive.extractall(ROOT)
            for part in parts:
                os.remove(part)
            os.remove(tarball)
            volume.commit()
            root = _find_bundle_root()
            if root is not None:
                _apply_root(root)
                return

    raise FileNotFoundError(
        "W5 bundle not found in the Modal volume. Upload it first:\n"
        "  python scripts/stage_w5_cloud_bundle.py --out /tmp/w5_bundle\n"
        "  tar -C /tmp/w5_bundle -czf w5_bundle.tgz .\n"
        "  modal volume put harmoniq-w5 w5_bundle.tgz /w5"
    )


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": BACKEND,
            "PYTHONUNBUFFERED": "1",
            "JAX_PLATFORMS": "cuda",
            "CUDA_VISIBLE_DEVICES": "0",
            "XLA_PYTHON_CLIENT_MEM_FRACTION": ".9",
            "TF_CPP_MIN_LOG_LEVEL": "3",
        }
    )
    return env


def _run(command: list[str]) -> str:
    print("[run] " + " ".join(command), flush=True)
    process = subprocess.Popen(
        command,
        cwd=BACKEND,
        env=_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    returncode = process.wait()
    output = "".join(lines)
    if returncode != 0:
        raise RuntimeError(
            f"command failed ({returncode}): {' '.join(command)}\n"
            f"{output[-4000:]}"
        )
    return output


def _manifest_path() -> str:
    root = os.path.dirname(BACKEND)
    return os.path.join(root, "docs", "eval", "amt_manifest.json")


def _merged_manifest_path() -> str:
    """Rewrite the committed manifest against the data available on volumes.

    W3 carries full GuitarSet / EGSet12 / IDMT audio; W2 carries the fixed
    50-track sample (including Guitar-TECHS and RWC-P). Tracks missing from
    both are skipped and counted in the report metadata.
    """
    import json

    source = _manifest_path()
    payload = json.loads(open(source, encoding="utf-8").read())
    merged: list[dict] = []
    skipped: list[str] = []
    for track in payload["tracks"]:
        resolved: dict[str, str] | None = None
        for root in _DATA_ROOTS:
            audio = os.path.join(root, track["audio_path"])
            if not os.path.isfile(audio):
                continue
            candidate = dict(track)
            candidate["audio_path"] = audio
            if candidate.get("gt_path"):
                gt = os.path.join(root, candidate["gt_path"])
                if not os.path.isfile(gt):
                    continue
                candidate["gt_path"] = gt
            if candidate.get("chord_gt_path"):
                chord = os.path.join(root, candidate["chord_gt_path"])
                if not os.path.isfile(chord):
                    continue
                candidate["chord_gt_path"] = chord
            resolved = candidate
            break
        if resolved is None:
            skipped.append(track["id"])
        else:
            merged.append(resolved)

    if not merged:
        raise FileNotFoundError(
            "No manifest tracks found on the W2/W3 volumes; mount the staged "
            "datasets or upload a full W5 bundle."
        )
    payload["tracks"] = merged
    payload["manifest_id"] = "amt-eval-v1+volumes"
    payload["description"] = (
        "W5 merged manifest: W0 tracks resolved against the staged W2/W3 "
        "volumes. Tracks missing from both volumes are skipped."
    )
    payload.pop("data_root", None)
    out = "/tmp/w5_manifest_merged.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    print(
        f"[manifest] {len(merged)} tracks resolved, {len(skipped)} skipped "
        f"from W2/W3 volumes",
        flush=True,
    )
    if skipped:
        print("[manifest] skipped: " + ", ".join(skipped[:10]) + ("..." if len(skipped) > 10 else ""), flush=True)
    return out


@app.function(
    image=image,
    gpu="A10G",
    timeout=30 * 60,
    volumes={ROOT: volume, "/w2": w2_volume, "/w3": w3_volume},
)
def smoke() -> str:
    """Validate the JAX/T5X + CUDA path on one track."""
    _ensure_bundle()
    os.makedirs(REPORT_DIR, exist_ok=True)
    command = [
        "python",
        "scripts/eval_amt.py",
        "--manifest",
        _merged_manifest_path(),
        "--tier",
        "mt3",
        "--source",
        "egset12",
        "--limit",
        "1",
        "--report",
        os.path.join(REPORT_DIR, "w5_smoke_mt3.json"),
        "--fail-on-track-error",
    ]
    output = _run(command)
    volume.commit()
    return output


@app.function(
    image=image,
    gpu="A10G",
    timeout=12 * 60 * 60,
    volumes={ROOT: volume, "/w2": w2_volume, "/w3": w3_volume},
    retries=1,
)
def evaluate(
    source: str = "guitarset",
    tier: str = "mt3",
    limit: str = "0",
    offset: str = "0",
    refresh: str = "false",
) -> str:
    """Run one tier for one source shard and write a per-source report."""
    _ensure_bundle()
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}; expected one of {SOURCES}")
    if tier not in ("mt3", "full", "crnn", "chroma"):
        raise ValueError(f"unsupported tier {tier!r}")
    os.makedirs(REPORT_DIR, exist_ok=True)
    suffix = f"-{source}"
    if int(offset or 0):
        suffix += f"-o{int(offset)}"
    report = os.path.join(REPORT_DIR, f"w5_eval_{tier}{suffix}.json")
    command = [
        "python",
        "scripts/eval_amt.py",
        "--manifest",
        _merged_manifest_path(),
        "--tier",
        tier,
        "--source",
        source,
        "--report",
        report,
        "--fail-on-track-error",
    ]
    if int(limit or 0):
        command += ["--limit", str(int(limit))]
    if int(offset or 0):
        command += ["--offset", str(int(offset))]
    if _truthy(refresh):
        command.append("--refresh")
    output = _run(command)
    volume.commit()
    return output


@app.function(
    image=image,
    cpu=8,
    memory=16384,
    timeout=4 * 60 * 60,
    volumes={ROOT: volume, "/w2": w2_volume, "/w3": w3_volume},
)
def aggregate(tier: str = "mt3", skip_quality: str = "false") -> str:
    """Pool calibration bins and evaluate the recording-quality gate."""
    _ensure_bundle()
    import glob

    reports = sorted(
        glob.glob(os.path.join(REPORT_DIR, f"w5_eval_{tier}-*.json"))
    )
    if not reports:
        raise FileNotFoundError(
            f"no {tier} reports found under {REPORT_DIR}; run evaluate first"
        )
    os.makedirs(REPORT_DIR, exist_ok=True)
    command = [
        "python",
        "scripts/eval_calibration_quality.py",
        "--manifest",
        _merged_manifest_path(),
        "--tier",
        tier,
        "--out-json",
        os.path.join(REPORT_DIR, "w5_calibration.json"),
        "--out-md",
        os.path.join(REPORT_DIR, "w5_calibration.md"),
    ]
    for report in reports:
        command += ["--eval-report", report]
    if _truthy(skip_quality):
        command.append("--skip-quality")
    output = _run(command)
    volume.commit()
    return output


@app.function(
    image=image,
    timeout=600,
    volumes={ROOT: volume, "/w2": w2_volume, "/w3": w3_volume},
)
def status() -> str:
    """Cheap availability probe: bundle, MT3 imports, GPU, checkpoint."""
    _ensure_bundle()
    script = (
        "import glob, json, os\n"
        "report = {}\n"
        "try:\n"
        "    import tensorflow as tf\n"
        "    report['tensorflow'] = tf.__version__\n"
        "    report['gpu'] = bool(tf.config.list_physical_devices('GPU'))\n"
        "except Exception as exc:\n"
        "    report['tensorflow_error'] = f'{type(exc).__name__}: {exc}'\n"
        "try:\n"
        "    import jax\n"
        "    report['jax'] = jax.__version__\n"
        "    report['jax_devices'] = [str(d) for d in jax.devices()]\n"
        "except Exception as exc:\n"
        "    report['jax_error'] = f'{type(exc).__name__}: {exc}'\n"
        "for name in ('mt3', 't5x', 'note_seq', 'seqio'):\n"
        "    try:\n"
        "        mod = __import__(name)\n"
        "        report[name] = getattr(mod, '__version__', 'ok')\n"
        "    except Exception as exc:\n"
        "        report[name + '_error'] = f'{type(exc).__name__}: {exc}'\n"
        f"report['checkpoint'] = os.path.isdir('{BACKEND}/data/models/mt3/mt3_t5_small')\n"
        f"report['manifest'] = os.path.isfile('{_manifest_path()}')\n"
        "print(json.dumps(report, indent=1))\n"
    )
    completed = subprocess.run(
        ["python", "-c", script],
        cwd=BACKEND,
        env=_env(),
        capture_output=True,
        text=True,
    )
    print(completed.stdout)
    if completed.returncode != 0:
        print(completed.stderr)
        raise RuntimeError("status probe failed")
    return completed.stdout


def _list_sources() -> str:
    return ", ".join(SOURCES)


if __name__ == "__main__":
    print(f"Sources: {_list_sources()}")
