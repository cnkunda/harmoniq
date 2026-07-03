"""MT3 model loading, inference, and event stream decoding.

Architecture:
  The MT3 model server is a lazily-initialized singleton that loads the
  T5-small checkpoint on first inference call. If the MT3 dependencies
  (JAX, note_seq, mt3) are not installed, inference returns an empty
  Mt3EventStream and is_available() returns False. This allows the
  fallback chain to degrade gracefully.

  The actual MT3 inference pipeline:
    1. Load audio at 16kHz mono (resampling from 44.1kHz guitar stem)
    2. Compute log-mel spectrogram (256 bins, 128 hop, 512 window)
    3. Run T5-small encoder-decoder to produce token logits
    4. Greedy-decode logits to token sequence
    5. Parse token sequence into Mt3Event objects
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from app.mt3.schemas import Mt3Event, Mt3EventStream

logger = logging.getLogger("harmoniq.mt3.model_server")

_MODEL_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "mt3"
_MT3_SAMPLE_RATE = 16000
_MT3_FFT_SIZE = 512
_MT3_HOP_SIZE = 128
_MT3_NUM_MEL_BINS = 256

_PERCUSSION_PROGRAM = 128  # GM percussion map


class Mt3ModelServer:
    """Singleton MT3 inference server.

    Loads the model on first call to infer(). If dependencies are missing,
    logs a warning and returns empty results rather than crashing.
    """

    _instance: Mt3ModelServer | None = None
    _model = None
    _vocab = None
    _note_processor = None
    _loaded = False
    _load_error: str | None = None

    def __new__(cls) -> Mt3ModelServer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def is_available(self) -> bool:
        """Check if the MT3 model is loaded and ready for inference."""
        if not self._loaded:
            self._try_load()
        return self._loaded

    def _try_load(self) -> bool:
        """Attempt to load MT3 dependencies and checkpoint.

        Returns True on success, False with logged warning on failure.
        The model weights download to _MODEL_CACHE_DIR on first load.
        """
        if self._loaded:
            return True
        if self._load_error is not None:
            return False

        try:
            import note_seq  # noqa: F401
            from mt3 import note_sequences, run_length_encoder
            from mt3.models import get_model
            from mt3.config import CONFIG_MAP
            from mt3.vocabularies import build_vocabularies

            _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

            model_name = "mt3"
            if model_name not in CONFIG_MAP:
                logger.warning("MT3 config '%s' not found; available: %s", model_name, list(CONFIG_MAP.keys()))
                self._load_error = f"Config '{model_name}' not found"
                return False

            config = CONFIG_MAP[model_name]
            self._vocab = build_vocabularies(config)
            self._note_processor = note_sequences.NoteProcessor()

            model = get_model(config, self._vocab)
            checkpoint_path = str(_MODEL_CACHE_DIR / "mt3_t5_small")
            model.load_weights(checkpoint_path)

            self._model = model
            self._loaded = True
            logger.info(
                "MT3 model loaded from %s (vocab_size=%d)",
                checkpoint_path, len(self._vocab),
            )
            return True

        except ImportError as exc:
            missing = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
            logger.warning(
                "MT3 dependencies not available (missing: %s). "
                "Install with: pip install -e '.[mt3]' "
                "Falling back to CRNN TFLite pipeline.",
                missing,
            )
            self._load_error = f"Missing dependency: {missing}"
            return False

        except Exception as exc:
            logger.warning(
                "MT3 model loading failed: %s. "
                "Falling back to CRNN TFLite pipeline.",
                exc,
            )
            self._load_error = str(exc)
            return False

    def infer(self, audio_path: str | Path) -> Mt3EventStream:
        """Run MT3 inference on an audio file.

        Args:
            audio_path: Path to a WAV file (44.1kHz mono recommended;
                        will be resampled to 16kHz internally).

        Returns:
            Mt3EventStream containing all detected note events across
            all instruments, or an empty stream if inference fails.
        """
        audio_path = Path(audio_path)
        if not audio_path.is_file():
            logger.error("MT3 inference failed: audio file not found: %s", audio_path)
            return Mt3EventStream(audio_duration_s=0.0)

        if not self.is_available():
            return Mt3EventStream(
                audio_duration_s=0.0,
                inference_time_ms=0.0,
            )

        start_time = time.time()

        try:
            import librosa
            from mt3 import note_sequences
            from mt3.run_length_encoder import RunLengthEncoder

            audio, sr = librosa.load(str(audio_path), sr=_MT3_SAMPLE_RATE, mono=True)
            audio_duration = len(audio) / _MT3_SAMPLE_RATE

            spectrogram = _compute_log_mel_spectrogram(audio)

            spectrogram_batch = np.expand_dims(spectrogram, axis=0)

            tokens = self._model.generate(
                spectrogram_batch,
                vocab=self._vocab,
                max_length=2048,
            )

            if tokens is None or len(tokens) == 0:
                logger.warning("MT3 generated no tokens for %s", audio_path)
                return Mt3EventStream(
                    audio_duration_s=audio_duration,
                    inference_time_ms=(time.time() - start_time) * 1000,
                )

            token_sequence = tokens[0].numpy()
            event_predictions = self._vocab.decode_event_predictions(token_sequence)

            note_sequence = note_sequences.NoteProcessor().process(
                event_predictions,
                self._vocab,
                onset_only=True,
            )

            events = _convert_note_sequence_to_events(
                note_sequence, audio_duration
            )

            mean_conf = (
                float(np.mean([e.confidence for e in events]))
                if events else 0.0
            )
            instrument_count = len(set(e.program for e in events if not self._is_percussion(e.program)))

            inference_ms = (time.time() - start_time) * 1000
            logger.info(
                "MT3 inference complete: %s → %d events across %d instruments "
                "(%.1fms, mean_conf=%.2f)",
                audio_path.name, len(events), instrument_count,
                inference_ms, mean_conf,
            )

            return Mt3EventStream(
                events=events,
                audio_duration_s=audio_duration,
                model_version="mt3-t5-small",
                inference_time_ms=inference_ms,
                mean_confidence=mean_conf,
                num_instruments=instrument_count,
            )

        except Exception as exc:
            inference_ms = (time.time() - start_time) * 1000
            logger.exception(
                "MT3 inference failed for %s after %.1fms: %s",
                audio_path, inference_ms, exc,
            )
            return Mt3EventStream(
                audio_duration_s=0.0,
                inference_time_ms=inference_ms,
            )

    def warm_start(self) -> bool:
        """Eagerly load the model on server boot.

        Returns True if the model loaded successfully, False if dependencies
        are missing or loading failed. Safe to call multiple times — subsequent
        calls are no-ops if already loaded or if loading already failed.
        """
        return self.is_available()

    def load_error(self) -> str | None:
        """Return the error message from the last failed load attempt, if any."""
        return self._load_error

    @staticmethod
    def _is_percussion(program: int) -> bool:
        """Check if a GM program number corresponds to percussion."""
        return program == _PERCUSSION_PROGRAM



def _compute_log_mel_spectrogram(audio: np.ndarray) -> np.ndarray:
    """Compute log-mel spectrogram for MT3 input.

    Uses the same parameters as the MT3 preprocessing pipeline:
    - 256 mel bins
    - 512 FFT size
    - 128 hop size
    - 16kHz sample rate

    Returns:
        Array of shape (time_steps, 256) with log-mel magnitudes.
    """
    import librosa

    mel_spec = librosa.feature.melspectrogram(
        y=audio,
        sr=_MT3_SAMPLE_RATE,
        n_fft=_MT3_FFT_SIZE,
        hop_length=_MT3_HOP_SIZE,
        n_mels=_MT3_NUM_MEL_BINS,
        fmin=30.0,
        fmax=_MT3_SAMPLE_RATE / 2,
    )
    log_mel = librosa.power_to_db(mel_spec, ref=1.0, top_db=80.0)
    return log_mel.T  # (time, bins)


def _convert_note_sequence_to_events(
    note_sequence,  # note_seq.NoteSequence
    audio_duration: float,
) -> list[Mt3Event]:
    """Convert a NoteSequence proto to structured Mt3Event objects.

    Args:
        note_sequence: The output from MT3's note processor.
        audio_duration: Duration of the input audio for clamping.

    Returns:
        List of Mt3Event objects, one per note in the sequence.
    """
    events: list[Mt3Event] = []

    for note in note_sequence.notes:
        program = getattr(note, "program", 24)
        confidence = getattr(note, "confidence", 0.9)

        events.append(Mt3Event(
            time=float(note.start_time),
            pitch=int(note.pitch),
            velocity=int(min(note.velocity, 127)) if hasattr(note, "velocity") else 80,
            program=int(program),
            is_onset=True,
            is_offset=False,
            confidence=float(confidence),
        ))

        end_time = min(float(note.end_time), audio_duration)
        if end_time > float(note.start_time):
            events.append(Mt3Event(
                time=end_time,
                pitch=int(note.pitch),
                velocity=0,
                program=int(program),
                is_onset=False,
                is_offset=True,
                confidence=float(confidence),
            ))

    events.sort(key=lambda e: (e.time, e.pitch, 0 if e.is_onset else 1))
    return events


def mt3_infer(audio_path: str | Path) -> Mt3EventStream:
    """Convenience function for single-shot MT3 inference.

    Uses the singleton model server. Returns empty Mt3EventStream
    if MT3 is unavailable.
    """
    server = Mt3ModelServer()
    if not server.is_available():
        logger.info("MT3 unavailable; returning empty event stream")
        return Mt3EventStream(audio_duration_s=0.0)
    return server.infer(audio_path)
