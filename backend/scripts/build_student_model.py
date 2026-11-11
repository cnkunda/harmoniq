"""Build the W3 two-head student (shared encoder, chord + solo tokens).

Usage (from ``backend/``)::

    # Train on W1 human/weak labels + pseudo-labels
    python scripts/build_student_model.py --limit-tracks 200 --epochs 20

    # Add GuitarSet/EGSet12/IDMT human labels from the W0 manifest
    python scripts/build_student_model.py --sources w1,amt --epochs 40

    # QAT + INT8 export + latency benchmark
    python scripts/build_student_model.py --qat-only --benchmark

Data sources
------------
- ``w1``: the committed W1 manifest (human/weak labels) plus the generated
  pseudo-label JSON directory.
- ``amt``: the W0 evaluation manifest's non-test tracks (GuitarSet etc.).

The script never trains on a ``test`` track. GuitarSet follows
``split_policy.json`` (player 03 = test), *not* the stale ``split`` field in
the old ``processed/cqt`` ``.npz`` files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np  # noqa: E402

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.data_engine.features import extract_cqt_windows  # noqa: E402
from app.data_engine.manifest import (  # noqa: E402
    load_w1_manifest,
    resolve_w1_audio,
    resolve_w1_chord_label,
    resolve_w1_note_label,
)
from app.evaluation.ground_truth import load_jams_notes  # noqa: E402
from app.evaluation.manifest import (  # noqa: E402
    load_manifest,
    resolve_track_paths,
)
from app.student.targets import (  # noqa: E402
    MAX_TOKEN_SEQUENCE,
    ChordSpan,
    SoloTokenTarget,
    TargetNote,
    build_chord_frame_labels,
    build_solo_token_target,
    derive_root_labels,
    notes_from_dicts,
    pad_token_batch,
    shift_decoder_inputs,
    spans_from_dicts,
)
from app.student.vocab import BOS, EOS  # noqa: E402

_DEFAULT_W1 = _REPO_ROOT / "docs" / "eval" / "w1_dataset_manifest.json"
_DEFAULT_AMT = _REPO_ROOT / "docs" / "eval" / "amt_manifest.json"
_DEFAULT_LABELS = _BACKEND_DIR / "data" / "pseudo_label" / "w1" / "labels"
_DEFAULT_OUTPUT = _BACKEND_DIR / "data" / "models" / "student"


@dataclass
class TrackData:
    id: str
    audio: Path
    split: str
    spans: list[ChordSpan]
    notes: list[TargetNote]
    has_solo: bool


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default="w1", help="Comma list: w1,amt")
    parser.add_argument("--w1-manifest", type=Path, default=_DEFAULT_W1)
    parser.add_argument("--amt-manifest", type=Path, default=_DEFAULT_AMT)
    parser.add_argument("--pseudo-labels", type=Path, default=_DEFAULT_LABELS)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--limit-tracks", type=int, default=None)
    parser.add_argument("--max-windows-per-track", type=int, default=None)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--qat-epochs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--qat-only", action="store_true")
    parser.add_argument(
        "--force-train", action="store_true",
        help="Ignore an existing checkpoint and retrain from the cache",
    )
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument(
        "--cache-dir", type=Path, default=None,
        help="Where to cache assembled arrays (default: <output>/cache)",
    )
    parser.add_argument(
        "--prepare-only", action="store_true",
        help="Build and cache the dataset, then exit (no training)",
    )
    parser.add_argument("--report", type=Path, default=None)
    return parser.parse_args(argv)


# ---- annotation loaders ----------------------------------------------
def _spans_from_json(path: Path) -> list[ChordSpan]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("chords", [])
    if not isinstance(payload, list):
        raise ValueError(f"unsupported chord timeline format: {path}")
    return spans_from_dicts(
        [
            {
                "start": item["start"],
                "end": item.get("end", item["start"]),
                "chord": item.get("chord", "N"),
            }
            for item in payload
        ]
    )


def _notes_from_annotation(path: Path) -> list[TargetNote]:
    suffix = path.suffix.lower()
    if suffix == ".jams":
        notes = load_jams_notes(path, program=24)
        return [
            TargetNote(
                pitch=note.pitch,
                onset=note.onset,
                offset=note.offset,
                velocity=note.velocity or 80,
                program=24,
            )
            for note in notes
        ]
    if suffix in (".mid", ".midi"):
        from app.teachers.events import midi_file_to_notes

        return [
            TargetNote(
                pitch=note.pitch,
                onset=note.onset,
                offset=note.offset,
                velocity=note.velocity,
                program=note.program,
            )
            for note in midi_file_to_notes(path)
        ]
    raise ValueError(f"unsupported note annotation: {path}")


# ---- source collection ------------------------------------------------
def _load_w1_tracks(
    manifest_path: Path, pseudo_dir: Path
) -> list[TrackData]:
    manifest = load_w1_manifest(manifest_path)
    by_id = {track.id: track for track in manifest.tracks}
    tracks: list[TrackData] = []

    for track in manifest.tracks:
        if track.split == "test" or track.label_status == "none":
            continue
        try:
            audio = resolve_w1_audio(
                manifest, track, manifest_path=manifest_path
            )
        except Exception:  # noqa: BLE001 - dataset may not be staged
            print(f"[WARN] {track.id}: audio missing; skipping")
            continue
        spans: list[ChordSpan] = []
        notes: list[TargetNote] = []
        try:
            chord_path = resolve_w1_chord_label(
                manifest, track, manifest_path=manifest_path
            )
        except Exception:  # noqa: BLE001 - annotation may not be staged
            chord_path = None
        if chord_path is not None and chord_path.is_file():
            spans = _spans_from_json(chord_path)
        try:
            note_path = resolve_w1_note_label(
                manifest, track, manifest_path=manifest_path
            )
        except Exception:  # noqa: BLE001 - annotation may not be staged
            note_path = None
        if note_path is not None and note_path.is_file():
            try:
                notes = _notes_from_annotation(note_path)
            except ValueError:
                notes = []
        tracks.append(
            TrackData(
                id=track.id,
                audio=audio,
                split=track.split,
                spans=spans,
                notes=notes,
                has_solo=bool(notes) and "solo" in track.label_channels,
            )
        )

    if pseudo_dir.is_dir():
        for path in sorted(pseudo_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            track_id = payload.get("track_id")
            track = by_id.get(track_id)
            if track is None or track.split == "test":
                continue
            try:
                audio = resolve_w1_audio(
                    manifest, track, manifest_path=manifest_path
                )
            except Exception:  # noqa: BLE001 - dataset may not be staged
                print(f"[WARN] pseudo:{track_id}: audio missing; skipping")
                continue
            spans = spans_from_dicts(payload.get("chords", []))
            notes = notes_from_dicts(payload.get("notes", []))
            tracks.append(
                TrackData(
                    id=f"pseudo:{track_id}",
                    audio=audio,
                    split=track.split,
                    spans=spans,
                    notes=notes,
                    has_solo=bool(notes),
                )
            )
    return tracks


def _load_amt_tracks(manifest_path: Path) -> list[TrackData]:
    manifest = load_manifest(manifest_path)
    tracks: list[TrackData] = []
    for spec in manifest.tracks:
        if spec.split == "test" or spec.qualitative:
            continue
        try:
            audio, gt_path, chord_gt_path = resolve_track_paths(
                manifest, spec, manifest_path=manifest_path
            )
        except Exception as exc:  # noqa: BLE001 - report and skip
            print(f"[WARN] {spec.id}: cannot resolve paths: {exc}")
            continue
        spans: list[ChordSpan] = []
        notes: list[TargetNote] = []
        if chord_gt_path is not None and chord_gt_path.is_file():
            try:
                spans = _spans_from_json(chord_gt_path)
            except ValueError as exc:
                print(f"[WARN] {spec.id}: chords skipped: {exc}")
        if gt_path is not None and gt_path.is_file():
            try:
                notes = _notes_from_annotation(gt_path)
            except ValueError as exc:
                print(f"[WARN] {spec.id}: notes skipped: {exc}")
        tracks.append(
            TrackData(
                id=spec.id,
                audio=audio,
                split=spec.split,
                spans=spans,
                notes=notes,
                has_solo=bool(notes),
            )
        )
    return tracks


# ---- example building -------------------------------------------------
def _empty_target() -> SoloTokenTarget:
    return SoloTokenTarget(
        tokens=np.asarray([BOS, EOS], dtype=np.int32),
        frame_indices=np.asarray([0, 0], dtype=np.int32),
    )


def _build_track_arrays(
    track: TrackData,
    *,
    max_windows: int | None = None,
) -> tuple[
    np.ndarray, np.ndarray, np.ndarray, list[SoloTokenTarget], list[float]
]:
    windows, centers = extract_cqt_windows(track.audio)
    features: list[np.ndarray] = []
    chord_labels: list[np.ndarray] = []
    solo_targets: list[SoloTokenTarget] = []
    solo_mask: list[float] = []

    limit = len(windows) if max_windows is None else min(len(windows), max_windows)
    for index in range(limit):
        center = float(centers[index])
        features.append(windows[index])
        chord_labels.append(
            build_chord_frame_labels(track.spans, center)
        )
        if track.has_solo:
            solo_targets.append(
                build_solo_token_target(track.notes, center)
            )
            solo_mask.append(1.0)
        else:
            solo_targets.append(_empty_target())
            solo_mask.append(0.0)

    chord_array = np.stack(chord_labels).astype(np.int32)
    return (
        np.stack(features),
        chord_array,
        derive_root_labels(chord_array),
        solo_targets,
        solo_mask,
    )


def _assemble(
    tracks: list[TrackData],
    *,
    max_windows_per_track: int | None,
) -> dict[str, dict[str, np.ndarray]]:
    buckets: dict[str, dict[str, list]] = {
        "train": {"x": [], "chord": [], "root": [], "solo": [], "mask": []},
        "val": {"x": [], "chord": [], "root": [], "solo": [], "mask": []},
    }
    for track in tracks:
        if track.split not in buckets:
            continue
        try:
            x, chord, root, solo, mask = _build_track_arrays(
                track, max_windows=max_windows_per_track
            )
        except Exception as exc:  # noqa: BLE001 - surface per-track failure
            print(f"[WARN] {track.id}: skipped ({type(exc).__name__}: {exc})")
            continue
        bucket = buckets[track.split]
        bucket["x"].append(x)
        bucket["chord"].append(chord)
        bucket["root"].append(root)
        bucket["solo"].extend(solo)
        bucket["mask"].append(np.asarray(mask, dtype=np.float32))
        print(f"[data] {track.id}: {len(x)} windows split={track.split}")

    assembled: dict[str, dict[str, np.ndarray]] = {}
    for split, bucket in buckets.items():
        if not bucket["x"]:
            assembled[split] = {
                "x": np.zeros((0, 0, 0), dtype=np.float32),
                "chord": np.zeros((0, 0), dtype=np.int32),
                "root": np.zeros((0, 0), dtype=np.int32),
                "tokens": np.zeros((0, MAX_TOKEN_SEQUENCE), dtype=np.int32),
                "frames": np.zeros((0, MAX_TOKEN_SEQUENCE), dtype=np.int32),
                "token_mask": np.zeros((0, MAX_TOKEN_SEQUENCE), dtype=np.float32),
                "solo_mask": np.zeros((0,), dtype=np.float32),
            }
            continue
        tokens, frames, token_mask = pad_token_batch(bucket["solo"])
        assembled[split] = {
            "x": np.concatenate(bucket["x"], axis=0).astype(np.float32),
            "chord": np.concatenate(bucket["chord"], axis=0).astype(np.int32),
            "root": np.concatenate(bucket["root"], axis=0).astype(np.int32),
            "tokens": tokens,
            "frames": frames,
            "token_mask": token_mask,
            "solo_mask": np.concatenate(bucket["mask"], axis=0).astype(np.float32),
        }
    return assembled


def _inputs(data: dict[str, np.ndarray]) -> list[np.ndarray]:
    return [
        data["x"],
        shift_decoder_inputs(data["tokens"]).astype(np.float32),
        data["frames"].astype(np.float32),
    ]


def _targets(data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {
        "chord_probs": data["chord"],
        "root_probs": data["root"],
        "solo_probs": data["tokens"],
    }


def _sample_weights(data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    solo = (data["solo_mask"][:, np.newaxis] * data["token_mask"]).astype(
        np.float32
    )
    chord = np.ones_like(data["chord"], dtype=np.float32)
    root = np.ones_like(data["root"], dtype=np.float32)
    return {"chord_probs": chord, "root_probs": root, "solo_probs": solo}


# ---- training ---------------------------------------------------------
def _train(args: argparse.Namespace, data: dict[str, dict[str, np.ndarray]]) -> Path:
    from app.student.model import (
        MODEL_FILENAME,
        build_student_model,
        compile_student_model,
    )

    import tensorflow as tf

    tf.random.set_seed(args.seed)
    train = data["train"]
    val = data["val"]
    if len(train["x"]) == 0:
        raise SystemExit("no training windows found; check --sources/--limit")

    print(f"[train] {len(train['x'])} train / {len(val['x'])} val windows")
    model = build_student_model()
    compile_student_model(model, learning_rate=args.learning_rate)
    model.summary(print_fn=lambda line: print(f"[model] {line}"))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    best_path = args.output_dir / MODEL_FILENAME
    has_val = len(val["x"]) > 0
    monitor = "val_loss" if has_val else "loss"
    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            str(best_path), monitor=monitor, save_best_only=True, verbose=1
        )
    ]
    if has_val:
        callbacks += [
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=6, restore_best_weights=True
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=3, min_lr=1e-5
            ),
        ]

    validation = None
    if has_val:
        validation = (_inputs(val), _targets(val), _sample_weights(val))

    model.fit(
        _inputs(train),
        _targets(train),
        sample_weight=_sample_weights(train),
        validation_data=validation,
        epochs=args.epochs,
        batch_size=args.batch_size,
        callbacks=callbacks,
        shuffle=True,
        verbose=2,
    )
    model.save(str(best_path))
    print(f"[train] wrote {best_path}")
    return best_path


def _qat_and_export(
    args: argparse.Namespace,
    data: dict[str, dict[str, np.ndarray]],
    keras_path: Path,
) -> Path:
    from app.student.model import (
        TFLITE_FILENAME,
        FrameGather,
        ToInt32,
        apply_qat,
        benchmark_tflite,
        compile_student_model,
        convert_to_tflite,
    )

    import tensorflow as tf

    # Register custom layers before deserializing in a fresh process.
    FrameGather.build()
    ToInt32.build()
    model = tf.keras.models.load_model(str(keras_path), compile=False)
    qat_model = apply_qat(model)
    compile_student_model(qat_model, learning_rate=1e-4)

    train = data["train"]
    val = data["val"]
    validation = None
    if len(val["x"]) > 0:
        validation = (_inputs(val), _targets(val), _sample_weights(val))
    qat_model.fit(
        _inputs(train),
        _targets(train),
        sample_weight=_sample_weights(train),
        validation_data=validation,
        epochs=args.qat_epochs,
        batch_size=args.batch_size,
        verbose=2,
    )

    representative = val["x"] if len(val["x"]) > 0 else train["x"]
    qat_path = args.output_dir / "student_model_qat.keras"
    qat_model.save(str(qat_path))
    print(f"[qat] saved QAT checkpoint {qat_path}")

    target = args.output_dir / TFLITE_FILENAME
    try:
        tflite_path = convert_to_tflite(
            qat_model, representative, target, int8_only=True
        )
        print("[qat] exported INT8 artifact")
    except RuntimeError as exc:
        print(
            f"[qat] INT8 export unavailable ({exc}); exporting a float FP16 "
            "artifact from the base model. The QAT checkpoint is retained."
        )
        tflite_path = convert_to_tflite(model, representative, target)
    if args.benchmark:
        result = benchmark_tflite(tflite_path, representative)
        print(f"[benchmark] {json.dumps(result)}")
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    return tflite_path


def _cache_path(args: argparse.Namespace) -> Path:
    directory = args.cache_dir or (args.output_dir / "cache")
    key = f"{args.sources}_{args.limit_tracks}_{args.max_windows_per_track}"
    key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return directory / f"dataset_{key}.npz"


def _save_cache(path: Path, data: dict[str, dict[str, np.ndarray]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        f"{split}__{name}": value
        for split, block in data.items()
        for name, value in block.items()
    }
    np.savez(path, **payload)
    print(f"[cache] wrote {path}")


def _load_cache(path: Path) -> dict[str, dict[str, np.ndarray]]:
    archive = np.load(path)
    data: dict[str, dict[str, np.ndarray]] = {"train": {}, "val": {}}
    for key in archive.files:
        split, name = key.split("__", 1)
        data.setdefault(split, {})[name] = archive[key]
    for split, block in data.items():
        if "chord" in block and "root" not in block:
            block["root"] = derive_root_labels(block["chord"])
    print(f"[cache] loaded {path}")
    return data


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    np.random.seed(args.seed)

    sources = [item.strip() for item in args.sources.split(",") if item.strip()]
    tracks: list[TrackData] = []
    if "w1" in sources:
        tracks.extend(_load_w1_tracks(args.w1_manifest, args.pseudo_labels))
    if "amt" in sources:
        tracks.extend(_load_amt_tracks(args.amt_manifest))
    if not tracks:
        raise SystemExit("no tracks found for the requested sources")

    if args.limit_tracks is not None:
        tracks = tracks[: args.limit_tracks]
    print(f"[data] {len(tracks)} tracks from {sources}")

    cache_path = _cache_path(args)
    if cache_path.is_file():
        data = _load_cache(cache_path)
    else:
        data = _assemble(
            tracks, max_windows_per_track=args.max_windows_per_track
        )
        _save_cache(cache_path, data)
    if args.prepare_only:
        print("[prepare] dataset cached; exiting without training")
        return 0

    keras_path = args.output_dir / "student_model.keras"
    if args.qat_only:
        if not keras_path.is_file():
            raise SystemExit(
                f"--qat-only requires an existing checkpoint: {keras_path}"
            )
        print(f"[qat] reusing existing checkpoint {keras_path}")
    elif keras_path.is_file() and not args.force_train:
        print(f"[train] reusing existing checkpoint {keras_path}")
    else:
        keras_path = _train(args, data)

    tflite_path = _qat_and_export(args, data, keras_path)
    print(f"[done] artifacts: {keras_path}, {tflite_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
