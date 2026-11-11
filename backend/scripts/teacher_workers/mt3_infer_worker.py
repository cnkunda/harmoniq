"""Worker process for the PyTorch MT3-family teachers.

Invoked by ``app.teachers.mt3_infer``. Loads the model once and transcribes a
list of audio paths, writing a JSON map of path -> notes.

This file is deliberately standalone: it can be run with a different Python
interpreter/venv via ``HARMONIQ_TEACHER_PYTHON``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_DIR))

from app.teachers.events import TeacherNote, midi_file_to_notes  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--auto-download", default="0")
    parser.add_argument("--sr", type=int, default=16000)
    return parser.parse_args()


def _notes_from_model(model, audio, sr: int, model_name: str) -> tuple[list[TeacherNote], bool]:
    """Decode notes while preserving GM programs for MR-MT3/YourMT3.

    The mt3-infer MR-MT3 MIDI decoder writes every note to channel 0 without a
    program change, which loses the instrument identity. Leakage metrics need
    the program, so use the adapter's preprocess/forward plus the vendored
    codec decoder and read ``note.program`` directly.
    """
    if model_name not in ("mr_mt3", "yourmt3"):
        return [], False
    try:
        features = model.preprocess(audio, sr)
        outputs = model.forward(features)
        tokens = outputs["tokens"]
        frame_times = outputs["frame_times"]
        predictions = []
        for batch_tokens, batch_frame_times in zip(tokens, frame_times):
            valid = batch_tokens[batch_tokens >= 0]
            if len(valid) > 0:
                predictions.append(
                    {
                        "est_tokens": valid,
                        "start_time": float(batch_frame_times[0]),
                    }
                )
        from mt3_infer.adapters import vocab_utils

        note_sequence, _, _ = vocab_utils.decode_and_combine_predictions(
            predictions, model.codec
        )
        notes = [
            TeacherNote(
                pitch=int(note.pitch),
                onset=float(note.start_time),
                offset=float(note.end_time),
                velocity=int(note.velocity),
                program=int(getattr(note, "program", 0)),
                confidence=0.9,
            )
            for note in note_sequence.notes
        ]
        return sorted(
            notes, key=lambda note: (note.onset, note.pitch, note.offset)
        ), True
    except Exception:
        traceback.print_exc()
        return [], False


def _gpu_exhausted(exc: Exception) -> bool:
    """Match CUDA memory/allocator failures worth one CPU retry."""
    text = str(exc).lower()
    return (
        "out of memory" in text
        or "outofmemory" in text
        or "cudacachingallocator" in text
        or "internal assert failed" in text
        or "cuda error" in text
    )


def _pipeline(
    model, audio, sr: int, args_model: str, midi_dir: Path, index: int
) -> tuple[list[TeacherNote], bool]:
    """Transcribe one prepared track; raises on failure (caller records it)."""
    notes, program_preserved = _notes_from_model(model, audio, sr, args_model)
    if not program_preserved:
        midi = model.transcribe(audio, sr=sr)
        midi_path = midi_dir / f"{index}.mid"
        midi.save(str(midi_path))
        notes = midi_file_to_notes(midi_path)
    return notes, program_preserved


def main() -> int:
    args = _parse_args()
    repo = os.getenv("HARMONIQ_MT3_INFER_PATH")
    if repo and repo not in sys.path:
        sys.path.insert(0, repo)

    import librosa
    from mt3_infer import __version__ as mt3_infer_version
    from mt3_infer import load_model

    audio_paths = [Path(item) for item in json.loads(Path(args.input_json).read_text())]
    if not audio_paths:
        raise SystemExit("no audio paths supplied")

    auto_download = str(args.auto_download).strip() == "1"
    print(
        f"[worker] loading {args.model} (mt3-infer {mt3_infer_version}, "
        f"device={args.device}, auto_download={auto_download})",
        flush=True,
    )
    model = load_model(
        args.model,
        device=args.device,
        auto_download=auto_download,
    )
    print("[worker] model loaded", flush=True)

    outputs: dict[str, dict] = {}
    cpu_model = None
    with tempfile.TemporaryDirectory(prefix="harmoniq_teacher_midi_") as tmp:
        tmp_dir = Path(tmp)
        for index, audio_path in enumerate(audio_paths, start=1):
            print(
                f"[worker] ({index}/{len(audio_paths)}) {audio_path.name}",
                flush=True,
            )
            started = time.perf_counter()
            try:
                audio, sr = librosa.load(
                    str(audio_path), sr=args.sr, mono=True
                )
                audio = audio.astype("float32")
                try:
                    notes, program_preserved = _pipeline(
                        model, audio, sr, args.model, tmp_dir, index
                    )
                except Exception as exc:
                    if not args.device.startswith("cuda") or not _gpu_exhausted(
                        exc
                    ):
                        raise
                    print(
                        f"[worker] CUDA OOM on {audio_path.name}; "
                        "retrying on CPU",
                        flush=True,
                    )
                    try:
                        import torch

                        torch.cuda.empty_cache()
                    except Exception as cache_exc:  # logged; cleanup is best-effort
                        print(
                            f"[worker] CUDA cache clear skipped: {cache_exc}",
                            flush=True,
                        )
                    if cpu_model is None:
                        cpu_model = load_model(
                            args.model,
                            device="cpu",
                            auto_download=False,
                        )
                        print("[worker] CPU fallback model loaded", flush=True)
                    notes, program_preserved = _pipeline(
                        cpu_model, audio, sr, args.model, tmp_dir, index
                    )
                latency_ms = (time.perf_counter() - started) * 1000.0
                outputs[str(audio_path)] = {
                    "notes": [note.as_dict() for note in notes],
                    "latency_ms": round(latency_ms, 3),
                    "model_version": f"mt3-infer:{mt3_infer_version}:{args.model}",
                    "metadata": {
                        "model": args.model,
                        "device": args.device,
                        "sample_rate": sr,
                        "audio_duration_s": round(len(audio) / sr, 3),
                        "program_preserved": program_preserved,
                    },
                }
                print(
                    f"[worker] {audio_path.name}: {len(notes)} notes "
                    f"({latency_ms:.0f} ms)",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 - reported to the adapter
                traceback.print_exc()
                outputs[str(audio_path)] = {
                    "notes": [],
                    "latency_ms": (time.perf_counter() - started) * 1000.0,
                    "model_version": f"mt3-infer:{mt3_infer_version}:{args.model}",
                    "metadata": {
                        "model": args.model,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                }

            # Flush after every track so a crash/OOM/timeout loses at most
            # the in-flight track instead of the whole batch (W2 cloud runs).
            try:
                Path(args.output).write_text(
                    json.dumps(outputs, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except OSError as flush_exc:  # logged; retry on the next track
                print(
                    f"[worker] flush failed for {audio_path.name}: {flush_exc}",
                    flush=True,
                )

    errors = sum(
        1 for entry in outputs.values() if entry.get("metadata", {}).get("error")
    )
    print(
        f"[worker] wrote {len(outputs)} output(s), errors={errors}",
        flush=True,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
