"""Load and run the W3 student, producing chord and solo output.

The loader prefers a TFLite artifact (the deployable form) and falls back to
the Keras checkpoint. Both backends are imported lazily so importing this
module costs nothing when the flag is off.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from app.chord_vocab import CHORD_VOCAB, NUM_CLASSES
from app.cqt_constants import FEATURE_DIM, HOP_SEC, TARGET_SR, WINDOW
from app.data_engine.features import FeatureExtractionError, extract_cqt_windows
from app.schemas import BeatGrid, ChordEvent, ChordTimeline, SoloNote, SoloNotes
from app.student import vocab
from app.student.model import MODEL_FILENAME, TFLITE_FILENAME
from app.student.targets import MAX_TOKEN_SEQUENCE, NUM_ROOT_CLASSES

logger = logging.getLogger("harmoniq.student")

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_MODEL_DIR = _BACKEND_DIR / "data" / "models" / "student"
MAX_SOLO_TOKENS = 192


def model_dir() -> Path:
    raw = os.getenv("HARMONIQ_STUDENT_MODEL_DIR")
    return Path(raw) if raw else _DEFAULT_MODEL_DIR


def student_enabled() -> bool:
    return os.getenv("HARMONIQ_STUDENT_ENABLED", "").strip() == "1"


def solo_enabled() -> bool:
    return os.getenv("HARMONIQ_STUDENT_SOLO", "1").strip() != "0"


class StudentUnavailable(RuntimeError):
    """The student artifact or runtime is missing."""


class StudentModel:
    """A loaded student model plus the decode logic around it."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory else model_dir()
        self._tflite_path = self.directory / TFLITE_FILENAME
        self._keras_path = self.directory / MODEL_FILENAME
        self._interpreter: Any = None
        self._keras_model: Any = None
        self._backend: str | None = None

    # ---- availability -------------------------------------------------
    def is_available(self) -> bool:
        return self._tflite_path.is_file() or self._keras_path.is_file()

    def unavailable_reason(self) -> str | None:
        if self.is_available():
            return None
        return (
            f"student model not found under {self.directory}; expected "
            f"{TFLITE_FILENAME} or {MODEL_FILENAME}"
        )

    def warmup(self) -> None:
        """Load the artifact once so per-track timings exclude load cost."""
        self._load()

    # ---- loading ------------------------------------------------------
    def _load(self) -> None:
        if self._backend is not None:
            return
        if self._tflite_path.is_file():
            self._interpreter = _load_tflite(self._tflite_path)
            self._backend = "tflite"
            logger.info("student: loaded TFLite %s", self._tflite_path)
            return
        if self._keras_path.is_file():
            self._keras_model = _load_keras(self._keras_path)
            self._backend = "keras"
            logger.info("student: loaded Keras %s", self._keras_path)
            return
        raise StudentUnavailable(self.unavailable_reason() or "student unavailable")

    # ---- forward pass -------------------------------------------------
    def _run(
        self, windows: np.ndarray, tokens: np.ndarray, frames: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self._interpreter is not None:
            return _run_tflite(self._interpreter, windows, tokens, frames)
        if self._keras_model is not None:
            outputs = self._keras_model.predict(
                [windows, tokens, frames], verbose=0
            )
            return (
                outputs["chord_probs"],
                outputs["solo_probs"],
                outputs["root_probs"],
            )
        raise StudentUnavailable("student model is not loaded")

    # ---- public API ---------------------------------------------------
    def transcribe(
        self,
        audio_path: Path | str,
        beat_grid: BeatGrid | None = None,
        *,
        include_solo: bool | None = None,
    ) -> tuple[ChordTimeline, SoloNotes, dict[str, Any]]:
        """Transcribe one audio file into chords and (optionally) solo notes."""
        self._load()
        start = time.perf_counter()
        try:
            windows, center_times = extract_cqt_windows(Path(audio_path))
        except FeatureExtractionError as exc:
            raise StudentUnavailable(f"student feature extraction failed: {exc}") from exc

        interpret_solo = solo_enabled() if include_solo is None else include_solo
        chord_timeline = self._chords(windows, center_times)
        solo_notes = (
            self._solo(windows, center_times) if interpret_solo else SoloNotes(notes=[])
        )
        runtime_ms = (time.perf_counter() - start) * 1000.0
        metadata = {
            "backend": self._backend,
            "windows": int(len(windows)),
            "runtime_ms": round(runtime_ms, 3),
            "sample_rate": TARGET_SR,
            "solo": interpret_solo,
            "beat_grid_used": beat_grid is not None,
        }
        return chord_timeline, solo_notes, metadata

    # ---- chord decoding ----------------------------------------------
    def _chords(
        self, windows: np.ndarray, center_times: np.ndarray
    ) -> ChordTimeline:
        batch_tokens = np.zeros((len(windows), MAX_TOKEN_SEQUENCE), dtype=np.float32)
        batch_frames = np.zeros((len(windows), MAX_TOKEN_SEQUENCE), dtype=np.float32)
        chord_probs, _, root_probs = self._run(
            windows, batch_tokens, batch_frames
        )

        chord_sums: dict[int, np.ndarray] = {}
        root_sums: dict[int, np.ndarray] = {}
        counts: dict[int, int] = {}
        for row, center in enumerate(center_times):
            center_frame = int(round(float(center) / HOP_SEC))
            base = center_frame - WINDOW // 2
            for offset in range(min(WINDOW, chord_probs.shape[1])):
                frame_index = base + offset
                if frame_index < 0:
                    continue
                chord_value = chord_probs[row, offset]
                root_value = root_probs[row, offset]
                if frame_index in chord_sums:
                    chord_sums[frame_index] += chord_value
                    root_sums[frame_index] += root_value
                    counts[frame_index] += 1
                else:
                    chord_sums[frame_index] = (
                        chord_value.astype(np.float64).copy()
                    )
                    root_sums[frame_index] = (
                        root_value.astype(np.float64).copy()
                    )
                    counts[frame_index] = 1

        if not chord_sums:
            return ChordTimeline(events=[])

        events: list[ChordEvent] = []
        last_chord: str | None = None
        for frame_index in sorted(chord_sums):
            probs = chord_sums[frame_index] / max(counts[frame_index], 1)
            roots = root_sums[frame_index] / max(counts[frame_index], 1)
            root_index = int(np.argmax(roots))
            if root_index >= 12:
                best = len(CHORD_VOCAB) - 1
            else:
                candidates = probs.copy()
                root_mask = (np.arange(len(candidates)) % 12) != root_index
                candidates[root_mask] = -1.0
                best = int(np.argmax(candidates))
            chord = CHORD_VOCAB[best] if best < len(CHORD_VOCAB) else "N"
            confidence = float(np.clip(probs[best], 0.0, 1.0))
            if chord != last_chord:
                events.append(
                    ChordEvent(
                        timestamp=round(frame_index * HOP_SEC, 4),
                        chord=chord,
                        confidence=round(confidence, 6),
                    )
                )
                last_chord = chord
        return ChordTimeline(events=events)

    # ---- solo decoding ------------------------------------------------
    def _solo(
        self, windows: np.ndarray, center_times: np.ndarray
    ) -> SoloNotes:
        notes: list[SoloNote] = []
        seen: dict[tuple[int, int], SoloNote] = {}
        for row, center in enumerate(center_times):
            window = windows[row : row + 1]
            start_s = float(center) - (WINDOW // 2) * HOP_SEC
            tokens = self._greedy_tokens(window)
            decoded = vocab.decode_tokens(
                tokens, window_start_s=start_s, frame_hop_s=HOP_SEC
            )
            for item in decoded:
                key = (item.pitch, int(round(item.onset / HOP_SEC)))
                note = SoloNote(
                    start_time=round(item.onset, 4),
                    duration=round(max(item.offset - item.onset, HOP_SEC), 4),
                    pitch=int(item.pitch),
                    velocity=int(item.velocity),
                    confidence=0.5,
                )
                existing = seen.get(key)
                if existing is None or note.duration > existing.duration:
                    seen[key] = note

        notes = sorted(seen.values(), key=lambda n: (n.start_time, n.pitch))
        return SoloNotes(notes=notes)

    def _greedy_tokens(self, window: np.ndarray) -> list[int]:
        tokens = np.zeros((1, MAX_TOKEN_SEQUENCE), dtype=np.float32)
        frames = np.zeros((1, MAX_TOKEN_SEQUENCE), dtype=np.float32)
        output: list[int] = []
        frame = 0
        for step in range(MAX_SOLO_TOKENS):
            tokens[0, step] = vocab.BOS if step == 0 else output[-1]
            frames[0, step] = min(frame, WINDOW - 1)
            _, solo_probs, _ = self._run(window, tokens, frames)
            probs = solo_probs[0, step]
            token = int(np.argmax(probs))
            if token in (vocab.PAD, vocab.BOS):
                token = vocab.EOS
            output.append(token)
            if token == vocab.EOS:
                break
            if token == vocab.TIME_SHIFT:
                frame += 1
                if frame >= WINDOW:
                    output.append(vocab.EOS)
                    break
        return output


# ---- backend helpers --------------------------------------------------
def _load_tflite(path: Path) -> Any:
    from app.student.model import load_tflite_interpreter

    return load_tflite_interpreter(path)


def _load_keras(path: Path) -> Any:
    try:
        import tensorflow as tf
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise StudentUnavailable("TensorFlow is required to load the Keras student") from exc
    from app.student.model import FrameGather, ToInt32

    # Register the custom layers before loading a saved Keras model.
    FrameGather.build()
    ToInt32.build()
    try:
        return tf.keras.models.load_model(str(path), compile=False)
    except Exception as exc:  # noqa: BLE001 - surface the real reason
        raise StudentUnavailable(f"could not load student Keras model: {exc}") from exc


def _input_index(details: list[dict], *, kind: str) -> int:
    for detail in details:
        name = str(detail["name"]).lower()
        shape = detail.get("shape", [])
        if kind == "cqt":
            if "cqt" in name or (len(shape) == 3 and int(shape[-1]) == FEATURE_DIM):
                return int(detail["index"])
        elif kind == "tokens":
            if "token" in name:
                return int(detail["index"])
        elif kind == "frames":
            if "frame" in name:
                return int(detail["index"])
    raise StudentUnavailable(f"TFLite student has no {kind} input")


def _output_index(details: list[dict], *, kind: str) -> int:
    if kind == "chord":
        expected = NUM_CLASSES
    elif kind == "root":
        expected = NUM_ROOT_CLASSES
    else:
        expected = vocab.VOCAB_SIZE
    for detail in details:
        name = str(detail["name"]).lower()
        shape = detail.get("shape", [])
        if kind in name:
            return int(detail["index"])
        if len(shape) == 3 and int(shape[-1]) == expected:
            return int(detail["index"])
    raise StudentUnavailable(f"TFLite student has no {kind} output")


def _run_tflite(
    interpreter: Any,
    windows: np.ndarray,
    tokens: np.ndarray,
    frames: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    inputs = interpreter.get_input_details()
    outputs = interpreter.get_output_details()
    cqt_index = _input_index(inputs, kind="cqt")
    token_index = _input_index(inputs, kind="tokens")
    frame_index = _input_index(inputs, kind="frames")
    chord_index = _output_index(outputs, kind="chord")
    root_index = _output_index(outputs, kind="root")
    solo_index = _output_index(outputs, kind="solo")

    chord_rows: list[np.ndarray] = []
    solo_rows: list[np.ndarray] = []
    root_rows: list[np.ndarray] = []
    token_rows = tokens.reshape(len(windows), -1)
    frame_rows = frames.reshape(len(windows), -1)
    for row in range(len(windows)):
        interpreter.set_tensor(
            cqt_index, windows[row][np.newaxis, ...].astype(np.float32)
        )
        interpreter.set_tensor(
            token_index, token_rows[row][np.newaxis, ...].astype(np.float32)
        )
        interpreter.set_tensor(
            frame_index, frame_rows[row][np.newaxis, ...].astype(np.float32)
        )
        interpreter.invoke()
        chord_rows.append(interpreter.get_tensor(chord_index)[0])
        solo_rows.append(interpreter.get_tensor(solo_index)[0])
        root_rows.append(interpreter.get_tensor(root_index)[0])
    return (
        np.stack(chord_rows),
        np.stack(solo_rows),
        np.stack(root_rows),
    )
