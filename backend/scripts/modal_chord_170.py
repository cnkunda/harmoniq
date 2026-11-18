"""Modal app: Chord 170 data preparation (Phase 2).

Phase 2 delivers the reproducible data pipeline; CQT caches and the derived
label/bass sidecars live on a Modal Volume so training runs (Phase 3) never
recompute features.

Prerequisites (once)::

    pip install modal && modal token new
    modal volume create harmoniq-chord170-data
    modal volume create harmoniq-chord170-runs

    # Upload the repo bundle (code + data/) the same way the W3 app expects it:
    tar -czf /tmp/chord170_bundle.tgz -C <repo-root> backend docs manifest.json
    modal volume put harmoniq-chord170-data /tmp/chord170_bundle.tgz /chord170

Run (from backend/)::

    modal run scripts/modal_chord_170.py::status
    modal run --detach scripts/modal_chord_170.py::prepare
    modal run --detach scripts/modal_chord_170.py::prepare --extract-rwc true
    modal volume get harmoniq-chord170-data /chord170/docs/audit/amt/chord170_phase2_dataset.json ./

Later phases extend this app with ``train``/``eval``/``sweep``/``export``
(GPU A10G/A100); Phase 2 intentionally ships only prepare + introspection.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import modal

app = modal.App("harmoniq-chord170")

# TensorFlow GPU image carries the CUDA/cuDNN stack; BTC inference needs torch
# (CPU is fine for labeling on this image) and chord-mix extraction needs
# demucs. Phase 3 training uses tensorflow (200-class CRNN student).
image = (
    modal.Image.from_registry("tensorflow/tensorflow:2.20.0-gpu")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install(
        "pydantic>=2.0",
        "numpy>=1.26",
        "scipy>=1.11",
        "librosa>=0.10.2",
        "soundfile>=0.13",
        "scikit-learn>=1.3",
        "pretty_midi>=0.2.10",
        "mir_eval>=0.8",
        "tqdm>=4.67",
        "huggingface_hub>=0.20",
        "pyyaml>=6.0",
        "tf_keras==2.20.0",
    )
    .env(
        {
            "TF_USE_LEGACY_KERAS": "1",
            "TF_CPP_MIN_LOG_LEVEL": "2",
            "PYTHONUNBUFFERED": "1",
        }
    )
)

data_volume = modal.Volume.from_name("harmoniq-chord170-data", create_if_missing=True)
runs_volume = modal.Volume.from_name("harmoniq-chord170-runs", create_if_missing=True)

btc_image = (
    modal.Image.debian_slim("3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("torch==2.5.1", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy>=1.26", "librosa>=0.10.2", "soundfile>=0.13")
    .env({"PYTHONUNBUFFERED": "1"})
)

audio_image = (
    modal.Image.debian_slim("3.11")
    .apt_install("ffmpeg", "libsndfile1")
    .pip_install("torch==2.5.1", "torchaudio==2.5.1")
    .pip_install("demucs>=4.0.1", "numpy>=1.26", "librosa>=0.10.2",
                 "soundfile>=0.13", "pretty_midi>=0.2.10", "pyyaml>=6.0",
                 "requests>=2.31", "scipy>=1.11")
    .env({"PYTHONUNBUFFERED": "1", "TORCH_HOME": "/chord170/.cache/torch"})
)

ROOT = "/chord170"
BACKEND = f"{ROOT}/backend"
REPORT_DIR = f"{ROOT}/docs/audit/amt"
RUNS = "/runs"


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
        if "chord170_bundle.tgz" in filenames:
            tarball = os.path.join(dirpath, "chord170_bundle.tgz")
            print(f"[setup] extracting {tarball}", flush=True)
            with tarfile.open(tarball) as archive:
                archive.extractall(dirpath)
            data_volume.commit()
            root = _find_bundle_root()
            if root is not None:
                _apply_root(root)
                return

    raise FileNotFoundError(
        "Chord 170 bundle not found on the Modal volume. Upload it first:\n"
        "  tar -czf /tmp/chord170_bundle.tgz -C <repo-root> backend docs\n"
        "  modal volume put harmoniq-chord170-data /tmp/chord170_bundle.tgz /chord170"
    )


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update({"PYTHONUNBUFFERED": "1", "TF_USE_LEGACY_KERAS": "1"})
    return env


def _run(command: list[str]) -> str:
    print("[run] " + " ".join(command), flush=True)
    process = subprocess.Popen(
        command, cwd=BACKEND, env=_env(), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
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
            f"command failed ({returncode}): {' '.join(command)}\n{output[-4000:]}"
        )
    return output


@app.function(
    image=image,
    cpu=8,
    memory=32768,
    timeout=8 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def prepare(extract_rwc: str = "false", datasets: str = "all") -> str:
    """Build CQT caches + label/bass sidecars + dataset card on the volume."""
    _ensure_bundle()
    output = ""
    if _truthy(extract_rwc):
        # RWC-P audio is opt-in (CC BY-NC 4.0); extraction runs on the volume.
        # Timelines (from the annotation CSVs) must exist before CQT extraction.
        output += _run(["python", "scripts/parse_rwc.py"])
        output += _run(["python", "scripts/extract_rwc_cqt.py"])
    output += _run(["python", "scripts/make_external_splits.py"])
    output += _run(["python", "scripts/chord_data_v2.py", "build-real",
                    "--dataset", datasets])
    output += _run(["python", "scripts/chord_data_v2.py", "build-pseudo",
                    "--report", os.path.join(REPORT_DIR, "chord170_phase2_pseudo_report.json")])
    output += _run(["python", "scripts/chord_data_v2.py", "card",
                    "--out", os.path.join(REPORT_DIR, "chord170_phase2_dataset.json")])
    data_volume.commit()
    for name in ("chord170_phase2_dataset.json", "chord170_phase2_pseudo_report.json"):
        path = os.path.join(REPORT_DIR, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                print(f"===== {name} =====", flush=True)
                print(handle.read(), flush=True)
    return output


@app.function(image=image, timeout=600, volumes={ROOT: data_volume, RUNS: runs_volume})
def status() -> str:
    """Cheap availability check: code bundle, datasets, and cached windows."""
    _ensure_bundle()
    script = (
        "import glob, json, os\n"
        "report = {}\n"
        "report['bundle'] = os.path.isdir(%r)\n" % BACKEND
        + "report['datasets'] = {}\n"
        "for name in ['guitarset', 'egset12', 'guitar_techs', 'idmt_smt_guitar', 'rwc']:\n"
        f"    cqt = glob.glob(os.path.join({BACKEND!r}, 'data', name, 'processed', 'cqt', '*.npz'))\n"
        f"    side = glob.glob(os.path.join({BACKEND!r}, 'data', name, 'processed', 'chord170', '*.npz'))\n"
        "    report['datasets'][name] = {'cqt': len(cqt), 'sidecars': len(side)}\n"
        f"pseudo = glob.glob(os.path.join({BACKEND!r}, 'data', 'chord170', 'pseudo_v2', 'processed', 'cqt', '*.npz'))\n"
        "report['pseudo_v2'] = len(pseudo)\n"
        "print(json.dumps(report, indent=1))\n"
    )
    completed = subprocess.run(
        ["python", "-c", script], cwd=BACKEND, env=_env(), capture_output=True, text=True,
    )
    text = completed.stdout + completed.stderr
    print(text, flush=True)
    return text


@app.function(image=image, timeout=300, volumes={ROOT: data_volume, RUNS: runs_volume})
def ls(path: str = ROOT) -> str:
    """List the volume contents (debug helper)."""
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(path):
        depth = dirpath[len(path):].count(os.sep)
        if depth >= 2:
            dirnames[:] = []
            continue
        for name in sorted(dirnames):
            lines.append(os.path.join(dirpath, name) + "/")
        for name in sorted(filenames):
            lines.append(os.path.join(dirpath, name))
    text = "\n".join(lines) or f"({path} is empty)"
    print(text, flush=True)
    return text


@app.function(
    image=image,
    gpu="A10G",
    cpu=8,
    memory=32768,
    timeout=24 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def train(
    config: str = "configs/chord170_base.yaml",
    run_name: str = "",
    extra_args: str = "",
) -> str:
    """Train the 170-class chord + bass model on an A10G.

    ``extra_args`` is appended verbatim (e.g. ``--epochs 5 --limit-train 40``)
    and is handy for smoke runs. Artifacts land in
    ``/runs/chord170/<run_name>`` on the runs volume.
    """
    import shlex

    _ensure_bundle()
    name = run_name.strip() or time.strftime("run-%Y%m%d-%H%M%S")
    out_dir = os.path.join(RUNS, "chord170", name)
    command = [
        "python", "scripts/train_chord_170.py",
        "--config", config,
        "--out-dir", out_dir,
    ]
    if extra_args.strip():
        command += shlex.split(extra_args)
    output = _run(command)
    runs_volume.commit()
    metrics_path = os.path.join(out_dir, "metrics.json")
    if os.path.isfile(metrics_path):
        with open(metrics_path, encoding="utf-8") as handle:
            print("===== metrics.json =====", flush=True)
            print(handle.read(), flush=True)
    with open(os.path.join(out_dir, "training_log.csv"), encoding="utf-8") as handle:
        print("===== training_log.csv =====", flush=True)
        print(handle.read(), flush=True)
    return output


@app.function(
    image=image,
    cpu=8,
    memory=32768,
    timeout=2 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
)
def eval_model(
    checkpoint: str,
    split: str = "test",
    sources: str = "guitarset,egset12",
    out: str = "",
    crop_window: str = "128",
    feature_stats: str = "",
    fuse_heads: str = "false",
    root_power: str = "1.0",
    quality_power: str = "1.0",
) -> str:
    """Evaluate a checkpoint on the requested split (artifacts on /runs)."""
    _ensure_bundle()
    out_path = out.strip() or os.path.join(
        RUNS, "chord170", "eval", f"{Path(checkpoint).stem}_{split}.json"
    )
    command = [
        "python", "scripts/eval_chord_170.py",
        "--checkpoint", checkpoint,
        "--split", split,
        "--sources", sources,
        "--out", out_path,
    ]
    if int(crop_window or 128) != 128:
        command += ["--crop-window", str(int(crop_window))]
    if feature_stats.strip():
        command += ["--feature-stats", feature_stats]
    if _truthy(fuse_heads):
        command += ["--fuse-heads", "--root-power", str(root_power),
                    "--quality-power", str(quality_power)]
    output = _run(command)
    runs_volume.commit()
    if os.path.isfile(out_path):
        with open(out_path, encoding="utf-8") as handle:
            print("===== eval report =====", flush=True)
            print(handle.read(), flush=True)
    return output


@app.function(
    image=image,
    gpu="A10G",
    cpu=8,
    memory=32768,
    timeout=24 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=0,
)
def sweep(epochs: str = "25", tag: str = "", suite: str = "core",
          config: str = "configs/chord170_base.yaml") -> str:
    """Run the Phase 4 ablation suite sequentially on one A10G.

    All variants share the config, seed, and epoch budget; patience equals the
    budget so every run completes (no early-stop asymmetry). Each run is
    evaluated on the held-out test split in its native label space and the
    comparison is written to ``sweeps/<tag>/summary.json``.
    """
    import shlex

    _ensure_bundle()
    stamp = tag.strip() or time.strftime("sweep-%Y%m%d-%H%M%S")
    base_out = os.path.join(RUNS, "chord170", "sweeps", stamp)
    budget = int(epochs)
    budget_args = ["--epochs", str(budget), "--patience", str(budget)]
    suites = {
        "core": [
            ("170-baseline", "170", []),
            ("170-aux", "170", ["--aux-heads"]),
            ("170-bass0.5", "170", ["--bass-loss-weight", "0.5"]),
            ("170-noaugment", "170", ["--no-augment"]),
            ("mirex25", "mirex25", ["--label-space", "mirex25"]),
            ("vocab277", "277", ["--label-space", "277"]),
            ("synth5", "170", ["--synthetic-epochs", "5", "--synthetic-limit", "1500"]),
            ("synth10", "170", ["--synthetic-epochs", "10", "--synthetic-limit", "1500"]),
        ],
        "fix": [
            ("mirex25", "mirex25", ["--label-space", "mirex25"]),
            ("vocab277", "277", ["--label-space", "277"]),
            ("170-aux-noaugment", "170", ["--aux-heads", "--no-augment"]),
        ],
        "finalists": [
            ("noaugment-seed1", "170", ["--no-augment", "--seed", "1"]),
            ("noaugment-seed2", "170", ["--no-augment", "--seed", "2"]),
            ("noaugment-seed3", "170", ["--no-augment", "--seed", "3"]),
        ],
        "finalists_aux": [
            ("aux-noaugment-seed1", "170", ["--aux-heads", "--no-augment", "--seed", "1"]),
            ("aux-noaugment-seed2", "170", ["--aux-heads", "--no-augment", "--seed", "2"]),
            ("aux-noaugment-seed3", "170", ["--aux-heads", "--no-augment", "--seed", "3"]),
        ],
        "gates": [
            ("e1-mask", "170", ["--aux-heads", "--no-augment",
                                 "--bass-inversion-weight", "1.0"]),
            ("e2-inv2", "170", ["--aux-heads", "--no-augment",
                                 "--bass-inversion-weight", "2.0"]),
            ("e3-bass1", "170", ["--aux-heads", "--no-augment",
                                  "--bass-inversion-weight", "2.0",
                                  "--bass-loss-weight", "1.0"]),
            ("e4-rare", "170", ["--aux-heads", "--no-augment",
                                 "--bass-inversion-weight", "2.0",
                                 "--chord-class-weight-tau", "0.3"]),
            ("e5-augment", "170", ["--aux-heads",
                                    "--bass-inversion-weight", "2.0"]),
        ],
        "generalization": [
            ("g1-earlystop", "170", ["--aux-heads", "--no-augment",
                                      "--aug-level", "none"]),
            ("g2-mildaug", "170", ["--aux-heads", "--aug-level", "mild"]),
            ("g3-standardize", "170", ["--aux-heads", "--no-augment",
                                        "--aug-level", "none",
                                        "--feature-standardize"]),
            ("g4-mild-stand", "170", ["--aux-heads", "--aug-level", "mild",
                                       "--feature-standardize"]),
        ],
        "stageD": [
            ("d1-control", "170", ["--aux-heads", "--no-augment",
                                    "--sources",
                                    "guitarset,guitar_techs,egset12,idmt_smt_guitar,rwc,pseudo_v2"]),
            ("d2-btc", "170", ["--aux-heads", "--no-augment",
                                "--sources",
                                "guitarset,guitar_techs,egset12,idmt_smt_guitar,rwc,pseudo_v2,pseudo_btc"]),
        ],
        "normalize": [
            ("n1-tracknorm", "170", ["--aux-heads", "--no-augment",
                                      "--feature-normalize", "track"]),
            ("n2-tracknorm-aug", "170", ["--aux-heads", "--aug-level", "mild",
                                          "--feature-normalize", "track"]),
        ],
        "stageE": [
            ("e1-control", "170", ["--aux-heads", "--no-augment",
                                    "--sources",
                                    "guitarset,guitar_techs,egset12,idmt_smt_guitar,rwc,pseudo_v2"]),
            ("e2-slakh", "170", ["--aux-heads", "--no-augment",
                                  "--sources",
                                  "guitarset,guitar_techs,egset12,idmt_smt_guitar,rwc,pseudo_v2,slakh"]),
        ],
        "context": [
            ("w64", "170", ["--aux-heads", "--no-augment", "--crop-window", "64"]),
            ("w32", "170", ["--aux-heads", "--no-augment", "--crop-window", "32"]),
        ],
        "context2": [
            ("w48", "170", ["--aux-heads", "--no-augment", "--crop-window", "48"]),
            ("w24", "170", ["--aux-heads", "--no-augment", "--crop-window", "24"]),
            ("w16", "170", ["--aux-heads", "--no-augment", "--crop-window", "16"]),
        ],
        "context3": [
            ("w8", "170", ["--aux-heads", "--no-augment", "--crop-window", "8"]),
            ("w16-slakh", "170", ["--aux-heads", "--no-augment", "--crop-window", "16",
                                   "--sources",
                                   "guitarset,guitar_techs,egset12,idmt_smt_guitar,rwc,pseudo_v2,slakh"]),
            ("w16-rare", "170", ["--aux-heads", "--no-augment", "--crop-window", "16",
                                  "--chord-class-weight-tau", "0.3"]),
        ],
        "fine": [
            ("fine-inv", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                  "--crop-window", "16", "--batch-size", "128",
                                  "--sources",
                                  "guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine,slakh"]),
            ("fine-inv-rare", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                       "--crop-window", "16", "--batch-size", "128",
                                       "--chord-class-weight-tau", "0.3",
                                       "--sources",
                                       "guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine,slakh"]),
        ],
        "inversion": [
            ("inv-w16-coarse", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                        "--crop-window", "16",
                                        "--sources",
                                        "guitarset,guitar_techs,egset12,idmt_smt_guitar,rwc,pseudo_v2,slakh"]),
            ("inv-w16-coarse-rare", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                             "--crop-window", "16",
                                             "--chord-class-weight-tau", "0.3",
                                             "--sources",
                                             "guitarset,guitar_techs,egset12,idmt_smt_guitar,rwc,pseudo_v2,slakh"]),
        ],
        "slash": [
            ("slash-inv2", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                    "--crop-window", "16", "--batch-size", "128",
                                    "--chord-inversion-weight", "2.0",
                                    "--sources",
                                    "guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine,slakh_fine"]),
            ("slash-inv2-rare", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                         "--crop-window", "16", "--batch-size", "128",
                                         "--chord-inversion-weight", "2.0",
                                         "--chord-class-weight-tau", "0.3",
                                         "--sources",
                                         "guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine,slakh_fine"]),
        ],
        "slash2": [
            ("slash2-mildaug", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                        "--crop-window", "16", "--batch-size", "128",
                                        "--chord-inversion-weight", "2.0",
                                        "--chord-class-weight-tau", "0.3",
                                        "--aug-level", "mild",
                                        "--sources",
                                        "guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine,slakh_fine"]),
            ("slash2-long", "170", ["--aux-heads", "--no-augment", "--inversion-head",
                                     "--crop-window", "16", "--batch-size", "128",
                                     "--chord-inversion-weight", "2.0",
                                     "--chord-class-weight-tau", "0.3",
                                     "--sources",
                                     "guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine,slakh_fine"]),
        ],
        "gates_finalists": [
            ("gates-seed1", "170", ["--aux-heads", "--no-augment", "--seed", "1"]),
            ("gates-seed2", "170", ["--aux-heads", "--no-augment", "--seed", "2"]),
            ("gates-seed3", "170", ["--aux-heads", "--no-augment", "--seed", "3"]),
        ],
    }
    if suite not in suites:
        raise ValueError(f"unknown suite {suite!r}; choose from {sorted(suites)}")
    variants = suites[suite]
    summary: dict = {"tag": stamp, "epochs": budget, "config": config,
                     "suite": suite, "variants": {}}
    for name, space, extra in variants:
        out_dir = os.path.join(base_out, name)
        command = [
            "python", "scripts/train_chord_170.py",
            "--config", config,
            "--out-dir", out_dir,
            "--label-space", space,
        ] + budget_args
        extra_args = list(extra)
        if "--label-space" in extra_args:
            index = extra_args.index("--label-space")
            extra_args = extra_args[:index] + extra_args[index + 2:]
        command += extra_args
        try:
            _run(command)
            eval_out = os.path.join(out_dir, "eval_test.json")
            eval_cmd = [
                "python", "scripts/eval_chord_170.py",
                "--checkpoint", os.path.join(out_dir, "best.keras"),
                "--split", "test",
                "--sources", "guitarset,egset12,idmt_smt_guitar,rwc",
                "--label-space", space,
                "--out", eval_out,
            ]
            stats_path = os.path.join(out_dir, "feature_stats.npz")
            if os.path.isfile(stats_path):
                eval_cmd += ["--feature-stats", stats_path]
            run_config = {}
            config_path = os.path.join(out_dir, "config.json")
            if os.path.isfile(config_path):
                run_config = json.load(open(config_path, encoding="utf-8"))
            if run_config.get("feature_normalize", "none") != "none":
                eval_cmd += ["--feature-normalize", run_config["feature_normalize"]]
            if int(run_config.get("crop_window", 128)) != 128:
                eval_cmd += ["--crop-window", str(int(run_config["crop_window"]))]
            config_sources = run_config.get("sources") or []
            if any(str(src).endswith("_fine") for src in config_sources):
                eval_sources = "guitarset_fine,egset12_fine,idmt_smt_guitar_fine,rwc_fine"
            else:
                eval_sources = "guitarset,egset12,idmt_smt_guitar,rwc"
            eval_cmd = [
                part if part != "guitarset,egset12,idmt_smt_guitar,rwc"
                else eval_sources
                for part in eval_cmd
            ]
            _run(eval_cmd)
            entry: dict = {"label_space": space, "args": " ".join(extra)}
            metrics_path = os.path.join(out_dir, "metrics.json")
            if os.path.isfile(metrics_path):
                entry["val"] = json.load(open(metrics_path, encoding="utf-8"))
            if os.path.isfile(eval_out):
                entry["test"] = json.load(open(eval_out, encoding="utf-8"))
            summary["variants"][name] = entry
        except Exception as exc:  # record failures instead of aborting the suite
            summary["variants"][name] = {"label_space": space, "args": " ".join(extra),
                                         "error": f"{type(exc).__name__}: {exc}"}
            print(f"[sweep] {name} FAILED: {exc}", flush=True)
        runs_volume.commit()

    summary_path = os.path.join(base_out, "summary.json")
    os.makedirs(base_out, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    runs_volume.commit()
    print(compact_sweep_table(summary), flush=True)
    return summary_path


def compact_sweep_table(summary: dict) -> str:
    lines = ["variant                space    exact   macroF1  wcsr-mirex  ece"]
    for name, entry in summary.get("variants", {}).items():
        test = entry.get("test") or {}
        if not test:
            lines.append(f"{name:22s} {entry.get('label_space',''):8s} ERROR")
            continue
        lines.append(
            f"{name:22s} {entry.get('label_space',''):8s} "
            f"{test.get('exact_accuracy', 0):.3f}   "
            f"{test.get('macro_f1', 0):.3f}    "
            f"{test.get('wcsr', {}).get('mirex', 0):.3f}       "
            f"{test.get('ece', 0):.3f}"
        )
    return "\n".join(lines)


@app.function(
    image=btc_image,
    cpu=8,
    memory=16384,
    timeout=6 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def btc_label_tracks(limit: str = "80", per_style: str = "10") -> str:
    """Run the BTC 170-class teacher over IDMT dataset4 audio.

    Writes one timeline JSON per track to
    ``/runs/chord170/teacher/btc/<track>.json`` (Teacher comparison, Phase 4).
    """
    import sys as _sys

    _ensure_bundle()
    backend_path = BACKEND
    if backend_path not in _sys.path:
        _sys.path.insert(0, backend_path)
    from scripts.btc_teacher import BtcTeacher

    base = os.path.join(BACKEND, "data", "idmt_smt_guitar", "raw", "audio", "dataset4")
    wavs = sorted(Path(base).rglob("audio/*.wav"))
    # Spread the subset across styles: keep at most ``per_style`` per style dir.
    by_style: dict[str, list] = {}
    for wav in wavs:
        style = wav.parent.parent.name
        by_style.setdefault(style, []).append(wav)
    chosen = []
    for style, files in sorted(by_style.items()):
        chosen.extend(files[: int(per_style)])
    if int(limit or 0):
        chosen = chosen[: int(limit)]
    out_dir = os.path.join(RUNS, "chord170", "teacher", "btc")
    os.makedirs(out_dir, exist_ok=True)
    teacher = BtcTeacher(device="cpu")
    written = 0
    for wav in chosen:
        rel = wav.relative_to(base).with_suffix("")
        track_id = "idmt_raw:dataset4/" + str(rel).replace(os.sep, "/")
        safe = str(rel).replace(os.sep, "_")
        try:
            timeline = teacher.predict_timeline(wav)
        except Exception as exc:
            print(f"[btc] {track_id} failed: {exc}", flush=True)
            continue
        payload = {"track_id": track_id, "teacher": "btc", "wave": str(wav),
                   "events": timeline}
        with open(os.path.join(out_dir, safe + ".json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        written += 1
        if written % 10 == 0:
            print(f"[btc] {written}/{len(chosen)} tracks labelled", flush=True)
    runs_volume.commit()
    print(f"[btc] wrote {written} timelines to {out_dir}", flush=True)
    return out_dir


@app.function(
    image=image,
    cpu=8,
    memory=16384,
    timeout=2 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
)
def calibrate(checkpoint: str, feature_stats: str = "", crop_window: str = "128", sources: str = "guitarset,guitar_techs,idmt_smt_guitar,rwc") -> str:
    """Fit post-hoc calibration on the validation split (Stage C)."""
    _ensure_bundle()
    out_dir = os.path.dirname(checkpoint)
    out_path = os.path.join(out_dir, "calibration.json")
    command = [
        "python", "scripts/calibrate_chord_170.py",
        "--checkpoint", checkpoint,
        "--split", "val",
        "--sources", sources,
        "--out", out_path,
    ]
    if feature_stats.strip():
        command += ["--feature-stats", feature_stats]
    if int(crop_window or 128) != 128:
        command += ["--crop-window", str(int(crop_window))]
    output = _run(command)
    runs_volume.commit()
    if os.path.isfile(out_path):
        with open(out_path, encoding="utf-8") as handle:
            print(handle.read(), flush=True)
    return output


@app.function(
    image=audio_image,
    gpu="A10G",
    cpu=8,
    memory=32768,
    timeout=6 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def build_mixes(limit: str = "0", force: str = "false") -> str:
    """Demucs chord-oriented mixes for unlabeled audio (Stage D)."""
    _ensure_bundle()
    command = [
        "python", "scripts/build_chord_mixes.py",
        "--audio-dir", os.path.join(BACKEND, "data", "youtube_crawl", "raw"),
        "--out-dir", os.path.join(BACKEND, "data", "chord170", "chord_mix"),
        "--device", "cuda",
    ]
    if int(limit or 0):
        command += ["--limit", str(int(limit))]
    if _truthy(force):
        command.append("--force")
    output = _run(command)
    data_volume.commit()
    return output


@app.function(
    image=audio_image,
    gpu="A10G",
    cpu=8,
    memory=32768,
    timeout=8 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def btc_pseudo(limit: str = "0", min_confidence: str = "0.6") -> str:
    """BTC pseudo-labels on the chord mixes (Stage D)."""
    _ensure_bundle()
    report_path = os.path.join(BACKEND, "data", "chord170", "pseudo_btc_report.json")
    command = [
        "python", "scripts/pseudo_label_btc.py",
        "--mix-dir", os.path.join(BACKEND, "data", "chord170", "chord_mix"),
        "--out-dir", os.path.join(BACKEND, "data", "chord170", "pseudo_btc"),
        "--device", "cuda",
        "--min-confidence", str(min_confidence),
        "--report", report_path,
    ]
    if int(limit or 0):
        command += ["--limit", str(int(limit))]
    output = _run(command)
    data_volume.commit()
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as handle:
            print(handle.read(), flush=True)
    return output


@app.function(
    image=audio_image,
    cpu=16,
    memory=65536,
    timeout=12 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def prepare_slakh(limit: str = "400", workers: str = "8") -> str:
    """Stream-extract a Slakh2100-redux subset and build CQT + labels."""
    _ensure_bundle()
    report_path = os.path.join(BACKEND, "data", "chord170", "slakh_report.json")
    command = [
        "python", "scripts/prepare_slakh.py",
        "--limit", str(int(limit)),
        "--workers", str(int(workers)),
        "--report", report_path,
    ]
    output = _run(command)
    data_volume.commit()
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as handle:
            print(handle.read(), flush=True)
    return output


@app.function(
    image=audio_image,
    cpu=16,
    memory=65536,
    timeout=12 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def prepare_fine(datasets: str = "guitarset,egset12,idmt_smt_guitar,rwc",
                 workers: str = "8", window: str = "16", hop: str = "16") -> str:
    """Fine-hop (1.6 s) feature extraction for the gate corpora."""
    _ensure_bundle()
    report_path = os.path.join(BACKEND, "data", "chord170", "fine_report.json")
    command = [
        "python", "scripts/extract_fine_windows.py",
        "--datasets", datasets,
        "--workers", str(int(workers)),
        "--window", str(int(window)),
        "--hop", str(int(hop)),
        "--report", report_path,
    ]
    output = _run(command)
    data_volume.commit()
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as handle:
            print(handle.read(), flush=True)
    return output


@app.function(
    image=audio_image,
    cpu=16,
    memory=65536,
    timeout=6 * 60 * 60,
    volumes={ROOT: data_volume, RUNS: runs_volume},
    retries=1,
)
def prepare_slakh_fine(limit: str = "400", workers: str = "8",
                       window: str = "16", hop: str = "16") -> str:
    """Fine-hop (1.6 s) Slakh features from the already-extracted subset."""
    _ensure_bundle()
    report_path = os.path.join(BACKEND, "data", "chord170", "slakh_fine_report.json")
    command = [
        "python", "scripts/prepare_slakh.py",
        "--limit", str(int(limit)),
        "--workers", str(int(workers)),
        "--window", str(int(window)),
        "--hop", str(int(hop)),
        "--skip-download",
        "--raw-dir", os.path.join(BACKEND, "data", "chord170", "slakh_raw"),
        "--out-dir", os.path.join(BACKEND, "data", "chord170", "slakh_fine"),
        "--report", report_path,
    ]
    output = _run(command)
    data_volume.commit()
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as handle:
            print(handle.read(), flush=True)
    return output


@app.local_entrypoint()
def main() -> None:
    print(status.remote())
