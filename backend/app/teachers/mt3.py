"""MT3 (JAX/T5X) teacher adapter."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

from app.mt3.model_server import mt3_infer
from app.teachers.events import (
    TeacherOutput,
    TeacherUnavailable,
    events_to_notes,
)

# Cheap availability probe: the full model-server load (JAX + T5X + TF)
# takes minutes on a Windows-mounted filesystem, so status checks that do
# not need the model must not trigger it (W2 comparison harness).
_MT3_DEPS = ("gin", "jax", "seqio", "tensorflow", "t5x", "mt3")


class Mt3Teacher:
    """The existing production MT3 teacher."""

    name = "mt3"
    display_name = "MT3 (T5-small, JAX)"

    def is_available(self) -> bool:
        try:
            from app.mt3.model_server import _MODEL_CACHE_DIR

            checkpoint_dir = _MODEL_CACHE_DIR / "mt3_t5_small"
            if not (checkpoint_dir / "checkpoint").is_file():
                return False
            if not all(
                (checkpoint_dir / name).is_file()
                for name in ("model.gin", "mt3.gin")
            ):
                return False
            return all(
                importlib.util.find_spec(dep) is not None for dep in _MT3_DEPS
            )
        except Exception:
            return False

    def unavailable_reason(self) -> str | None:
        if self.is_available():
            return None
        return (
            "MT3 unavailable: install the mt3 extra and download the checkpoint "
            "(pip install -e '.[mt3]' && python scripts/download_mt3_checkpoint.py)"
        )

    def transcribe(self, audio_path: Path) -> TeacherOutput:
        if not self.is_available():
            raise TeacherUnavailable(self.unavailable_reason() or "MT3 unavailable")
        start = time.perf_counter()
        stream = mt3_infer(str(audio_path))
        latency_ms = (time.perf_counter() - start) * 1000.0
        notes = events_to_notes(
            stream.events, audio_duration=stream.audio_duration_s
        )
        return TeacherOutput(
            notes=notes,
            latency_ms=latency_ms,
            model_version=stream.model_version,
            metadata={
                "events": len(stream.events),
                "mean_confidence": stream.mean_confidence,
                "num_instruments": stream.num_instruments,
                "audio_duration_s": stream.audio_duration_s,
            },
        )

    def transcribe_many(self, audio_paths: list[Path]) -> dict[Path, TeacherOutput]:
        return {path: self.transcribe(path) for path in audio_paths}
