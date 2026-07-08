"""MT3 model loading, inference, and event stream decoding.

Architecture:
  The MT3 model server is a lazily-initialized singleton that loads the
  T5-small checkpoint on first inference call. If the MT3 dependencies
  (JAX, note_seq, mt3) are not installed, inference returns an empty
  Mt3EventStream and is_available() returns False. This allows the
  fallback chain to degrade gracefully.

  The inference pipeline follows the official MT3 colab:
    1. Load audio at 16kHz mono
    2. Split into frames and compute log-mel spectrograms (mt3.spectrograms)
    3. Run T5-small encoder-decoder via T5X predict_batch_with_aux
    4. Decode token sequence to NoteSequence via metrics_utils
    5. Convert NoteSequence to Mt3EventStream for downstream decoders
"""

from __future__ import annotations

import functools
import logging
import time
from pathlib import Path

import numpy as np

from app.mt3.schemas import Mt3Event, Mt3EventStream

logger = logging.getLogger("harmoniq.mt3.model_server")

_MODEL_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "mt3"
_MT3_SAMPLE_RATE = 16000
_PERCUSSION_PROGRAM = 128


class Mt3ModelServer:
    """Singleton MT3 inference server.

    Loads the model on first call to infer(). If dependencies are missing,
    logs a warning and returns empty results rather than crashing.
    """

    _instance: Mt3ModelServer | None = None
    _model = None
    _vocab = None
    _loaded = False
    _load_error: str | None = None

    def __new__(cls) -> Mt3ModelServer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def is_available(self) -> bool:
        if not self._loaded:
            self._try_load()
        return self._loaded

    def _try_load(self) -> bool:
        """Attempt to load MT3 dependencies, GIN configs, and checkpoint.

        Returns True on success, False with logged warning on failure.
        """
        if self._loaded:
            return True
        if self._load_error is not None:
            return False

        try:
            import gin
            import jax
            import seqio
            import tensorflow as tf
            import t5x

            from mt3 import (
                metrics_utils,
                models,
                network,
                note_sequences,
                preprocessors,
                spectrograms,
                vocabularies,
            )

            checkpoint_dir = _MODEL_CACHE_DIR / "mt3_t5_small"
            if not (checkpoint_dir / "checkpoint").is_file():
                logger.warning(
                    "MT3 checkpoint not found at %s; MT3 unavailable", checkpoint_dir
                )
                self._load_error = f"Checkpoint not found at {checkpoint_dir}"
                return False

            gin_files = [str(checkpoint_dir / "model.gin"), str(checkpoint_dir / "mt3.gin")]

            self._num_velocity_bins = 1
            self._encoding_spec = note_sequences.NoteEncodingWithTiesSpec
            self._inputs_length = 256
            self._outputs_length = 1024
            self._batch_size = 8
            self._sequence_length = {
                "inputs": self._inputs_length,
                "targets": self._outputs_length,
            }

            self._partitioner = t5x.partitioning.PjitPartitioner(num_partitions=1)
            self._partition_spec = t5x.partitioning.PartitionSpec

            self._spectrogram_config = spectrograms.SpectrogramConfig()
            self._codec = vocabularies.build_codec(
                vocab_config=vocabularies.VocabularyConfig(
                    num_velocity_bins=self._num_velocity_bins
                )
            )
            self._vocabulary = vocabularies.vocabulary_from_codec(self._codec)
            self._output_features = {
                "inputs": seqio.ContinuousFeature(dtype=tf.float32, rank=2),
                "targets": seqio.Feature(vocabulary=self._vocabulary),
            }

            # Parse GIN configs — must happen before model construction
            gin_bindings = [
                "from __gin__ import dynamic_registration",
                "from mt3 import vocabularies",
                "VOCAB_CONFIG=@vocabularies.VocabularyConfig()",
                f"vocabularies.VocabularyConfig.num_velocity_bins={self._num_velocity_bins}",
            ]
            with gin.unlock_config():
                gin.parse_config_files_and_bindings(
                    gin_files, gin_bindings, finalize_config=False
                )

            # Build T5X model from GIN-registered classes
            model_config = gin.get_configurable(network.T5Config)()
            module = network.Transformer(config=model_config)
            self._model = models.ContinuousInputsEncoderDecoderModel(
                module=module,
                input_vocabulary=self._output_features["inputs"].vocabulary,
                output_vocabulary=self._output_features["targets"].vocabulary,
                optimizer_def=t5x.adafactor.Adafactor(decay_rate=0.8, step_offset=0),
                input_depth=spectrograms.input_depth(self._spectrogram_config),
            )

            # Restore checkpoint via T5X TrainStateInitializer
            train_state_initializer = t5x.utils.TrainStateInitializer(
                optimizer_def=self._model.optimizer_def,
                init_fn=self._model.get_initial_variables,
                input_shapes={
                    "encoder_input_tokens": (self._batch_size, self._inputs_length),
                    "decoder_input_tokens": (self._batch_size, self._outputs_length),
                },
                partitioner=self._partitioner,
            )

            restore_cfg = t5x.utils.RestoreCheckpointConfig(
                path=str(checkpoint_dir), mode="specific", dtype="float32"
            )

            train_state_axes = train_state_initializer.train_state_axes
            self._predict_fn = self._get_predict_fn(train_state_axes)
            self._train_state = train_state_initializer.from_checkpoint_or_scratch(
                [restore_cfg], init_rng=jax.random.PRNGKey(0)
            )

            self._loaded = True
            logger.info("MT3 model loaded from %s", checkpoint_dir)
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

    def _get_predict_fn(self, train_state_axes):
        """Generate a partitioned prediction function for decoding.

        Follows the official MT3 colab pattern:
        wraps model.predict_batch_with_aux into a partitioned function.
        """

        def partial_predict_fn(params, batch, decode_rng):
            return self._model.predict_batch_with_aux(
                params, batch, decoder_params={"decode_rng": None}
            )

        return self._partitioner.partition(
            partial_predict_fn,
            in_axis_resources=(
                train_state_axes.params,
                self._partition_spec("data"),
                None,
            ),
            out_axis_resources=self._partition_spec("data"),
        )

    def _predict_tokens(self, batch, seed=0):
        """Run greedy decoding on a batch, return decoded tokens."""
        import jax

        prediction, _ = self._predict_fn(
            self._train_state.params, batch, jax.random.PRNGKey(seed)
        )
        return self._vocabulary.decode_tf(prediction).numpy()

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
            return Mt3EventStream(audio_duration_s=0.0, inference_time_ms=0.0)

        start_time = time.time()

        try:
            import librosa

            audio, sr = librosa.load(str(audio_path), sr=_MT3_SAMPLE_RATE, mono=True)
            audio_duration = len(audio) / _MT3_SAMPLE_RATE

            est_ns = self._run_inference(audio)

            if not est_ns or not est_ns.notes:
                logger.warning("MT3 generated no notes for %s", audio_path)
                return Mt3EventStream(
                    audio_duration_s=audio_duration,
                    inference_time_ms=(time.time() - start_time) * 1000,
                )

            events = self._note_sequence_to_events(est_ns, audio_duration)

            mean_conf = (
                float(np.mean([e.confidence for e in events])) if events else 0.0
            )
            instrument_count = len(
                set(e.program for e in events if not self._is_percussion(e.program))
            )

            inference_ms = (time.time() - start_time) * 1000
            logger.info(
                "MT3 inference complete: %s -> %d events across %d instruments "
                "(%.1fms, mean_conf=%.2f)",
                audio_path.name,
                len(events),
                instrument_count,
                inference_ms,
                mean_conf,
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
                audio_path,
                inference_ms,
                exc,
            )
            return Mt3EventStream(audio_duration_s=0.0, inference_time_ms=inference_ms)

    def _run_inference(self, audio: np.ndarray):
        """Run the full MT3 inference pipeline on audio samples.

        Follows the official colab's InferenceModel.__call__ method:
          1. Create TF Dataset of spectrogram frames
          2. Apply preprocessing chain (split_to_inputs_length, add_dummy, compute_spectrograms)
          3. Convert features and batch
          4. Greedy-decode via T5X predict_batch_with_aux
          5. Convert event predictions to NoteSequence
        """
        import tensorflow as tf
        from mt3 import metrics_utils, preprocessors, spectrograms

        ds = self._audio_to_dataset(audio)
        ds = self._preprocess(ds)

        model_ds = self._model.FEATURE_CONVERTER_CLS(pack=False)(
            ds, task_feature_lengths=self._sequence_length
        )
        model_ds = model_ds.batch(self._batch_size)

        inferences = (
            tokens
            for batch in model_ds.as_numpy_iterator()
            for tokens in self._predict_tokens(batch)
        )

        predictions = []
        for example, tokens in zip(ds.as_numpy_iterator(), inferences):
            predictions.append(self._postprocess(tokens, example))

        result = metrics_utils.event_predictions_to_ns(
            predictions,
            codec=self._codec,
            encoding_spec=self._encoding_spec,
        )
        return result["est_ns"]

    def _audio_to_dataset(self, audio: np.ndarray):
        """Create a TF Dataset of spectrogram frames from input audio."""
        import tensorflow as tf
        from mt3 import spectrograms

        frame_size = self._spectrogram_config.hop_width
        padding = [0, frame_size - len(audio) % frame_size]
        audio = np.pad(audio, padding, mode="constant")
        frames = spectrograms.split_audio(audio, self._spectrogram_config)
        num_frames = len(audio) // frame_size
        times = np.arange(num_frames) / self._spectrogram_config.frames_per_second
        return tf.data.Dataset.from_tensors({
            "inputs": frames,
            "input_times": times,
        })

    def _preprocess(self, ds):
        """Apply MT3 preprocessing chain to the dataset."""
        import functools as ft
        import t5 as _t5
        from mt3 import preprocessors

        pp_chain = [
            ft.partial(
                _t5.data.preprocessors.split_tokens_to_inputs_length,
                sequence_length=self._sequence_length,
                output_features=self._output_features,
                feature_key="inputs",
                additional_feature_keys=["input_times"],
            ),
            preprocessors.add_dummy_targets,
            ft.partial(
                preprocessors.compute_spectrograms,
                spectrogram_config=self._spectrogram_config,
            ),
        ]
        for pp in pp_chain:
            ds = pp(ds)
        return ds

    def _postprocess(self, tokens, example):
        """Post-process decoded tokens into a prediction dict."""
        from mt3 import vocabularies

        tokens = self._trim_eos(tokens)
        start_time = example["input_times"][0]
        start_time -= start_time % (1 / self._codec.steps_per_second)
        return {
            "est_tokens": tokens,
            "start_time": start_time,
            "raw_inputs": [],
        }

    @staticmethod
    def _trim_eos(tokens):
        """Trim end-of-sequence token from decoded token array."""
        from mt3 import vocabularies

        tokens = np.array(tokens, np.int32)
        if vocabularies.DECODED_EOS_ID in tokens:
            tokens = tokens[: np.argmax(tokens == vocabularies.DECODED_EOS_ID)]
        return tokens

    def warm_start(self) -> bool:
        """Eagerly load the model on server boot.

        Returns True if the model loaded successfully, False if dependencies
        are missing or loading failed. Safe to call multiple times.
        """
        return self.is_available()

    def load_error(self) -> str | None:
        """Return the error message from the last failed load attempt, if any."""
        return self._load_error

    @staticmethod
    def _is_percussion(program: int) -> bool:
        """Check if a GM program number corresponds to percussion."""
        return program == _PERCUSSION_PROGRAM

    def _note_sequence_to_events(
        self, ns, audio_duration: float
    ) -> list[Mt3Event]:
        """Convert a NoteSequence proto to structured Mt3Event objects.

        Args:
            ns: The output NoteSequence from MT3 inference.
            audio_duration: Duration of the input audio for clamping.

        Returns:
            List of Mt3Event objects, one onset + one offset per note.
        """
        events: list[Mt3Event] = []

        for note in ns.notes:
            program = getattr(note, "program", 24)
            confidence = getattr(note, "confidence", 0.9)

            events.append(
                Mt3Event(
                    time=float(note.start_time),
                    pitch=int(note.pitch),
                    velocity=int(min(note.velocity, 127))
                    if hasattr(note, "velocity")
                    else 80,
                    program=int(program),
                    is_onset=True,
                    confidence=float(confidence),
                )
            )

            end_time = min(float(note.end_time), audio_duration)
            if end_time > float(note.start_time):
                events.append(
                    Mt3Event(
                        time=end_time,
                        pitch=int(note.pitch),
                        velocity=0,
                        program=int(program),
                        is_onset=False,
                        is_offset=True,
                        confidence=float(confidence),
                    )
                )

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
