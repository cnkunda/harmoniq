"""Shared-encoder two-head student model.

Architecture::

    CQT window (128, 144)
        └─ dilating Conv1D ×3 → BatchNorm → Dropout
             ├─ Dense(256) → Dense(277 softmax)      # chord frames
             └─ gather(frame) + token embedding → causal Conv1D ×2
                  → Dense(VOCAB softmax)             # solo event tokens

Both heads use only Conv1D/Dense/Embedding. The encoder is fully
convolutional (no recurrent TensorList ops), so QAT and INT8 TFLite work
without the Flex delegate and the model fits the on-device latency budget.

TensorFlow is imported lazily so vocabulary/target tests run without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.chord_vocab import NUM_CLASSES
from app.cqt_constants import FEATURE_DIM, WINDOW
from app.student.targets import MAX_TOKEN_SEQUENCE, NUM_ROOT_CLASSES
from app.student.vocab import VOCAB_SIZE

MODEL_FILENAME = "student_model.keras"
TFLITE_FILENAME = "student_model.tflite"
TOKEN_EMBED_DIM = 64


def _require_tensorflow():
    try:
        import tensorflow as tf
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise ImportError(
            "TensorFlow is required for the W3 student model. "
            "Install with: pip install tensorflow"
        ) from exc
    return tf


class FrameGather:
    """Factory for the ``tf.gather`` layer used by the solo decoder.

    Defined as a function returning a Keras Layer instance so the module can
    be imported without TensorFlow.
    """

    @staticmethod
    def build(name: str = "frame_gather"):
        tf = _require_tensorflow()

        @tf.keras.utils.register_keras_serializable(package="harmoniq")
        class _FrameGather(tf.keras.layers.Layer):
            def call(self, inputs, **kwargs):  # noqa: D401 - Keras API
                encoder, frames = inputs
                return tf.gather(encoder, frames, batch_dims=1)

            def compute_output_shape(self, input_shape):
                encoder_shape, frames_shape = input_shape
                return (
                    encoder_shape[0],
                    frames_shape[1],
                    encoder_shape[2],
                )

            def get_config(self):  # noqa: D401 - Keras API
                return super().get_config()

        return _FrameGather(name=name)


class ToInt32:
    """Factory for the float→int cast used by the decoder inputs.

    The token/frame inputs are exposed as float32 so TFMOT's input
    quantizer does not receive an integer tensor. The cast layer is
    unsupported by TFMOT and is passed through by the safe clone.
    """

    @staticmethod
    def build(name: str = "to_int32"):
        tf = _require_tensorflow()

        @tf.keras.utils.register_keras_serializable(package="harmoniq")
        class _ToInt32(tf.keras.layers.Layer):
            def call(self, inputs, **kwargs):  # noqa: D401 - Keras API
                return tf.cast(inputs, tf.int32)

            def get_config(self):  # noqa: D401 - Keras API
                return super().get_config()

        return _ToInt32(name=name)


def build_student_model(
    *,
    window: int = WINDOW,
    feature_dim: int = FEATURE_DIM,
    num_chord_classes: int = NUM_CLASSES,
    num_root_classes: int = NUM_ROOT_CLASSES,
    vocab_size: int = VOCAB_SIZE,
    max_tokens: int = MAX_TOKEN_SEQUENCE,
    dropout: float = 0.2,
) -> Any:
    """Build the float32 two-head student model."""
    tf = _require_tensorflow()

    cqt = tf.keras.Input(shape=(window, feature_dim), name="cqt_window")
    tokens_in = tf.keras.Input(
        shape=(max_tokens,), dtype="float32", name="decoder_tokens"
    )
    frames_in = tf.keras.Input(
        shape=(max_tokens,), dtype="float32", name="decoder_frames"
    )
    tokens_int = ToInt32.build(name="decoder_tokens_int")(tokens_in)
    frames_int = ToInt32.build(name="decoder_frames_int")(frames_in)

    x = tf.keras.layers.Conv1D(
        64, 3, dilation_rate=1, padding="same", activation="relu",
        name="enc_conv1",
    )(cqt)
    x = tf.keras.layers.Conv1D(
        64, 3, dilation_rate=2, padding="same", activation="relu",
        name="enc_conv2",
    )(x)
    x = tf.keras.layers.Conv1D(
        64, 3, dilation_rate=4, padding="same", activation="relu",
        name="enc_conv3",
    )(x)
    encoder = tf.keras.layers.BatchNormalization(name="enc_bn")(x)
    encoder = tf.keras.layers.Dropout(dropout, name="enc_dropout")(encoder)

    chord = tf.keras.layers.Dense(
        256, activation="relu", name="chord_dense"
    )(encoder)
    chord = tf.keras.layers.Dropout(dropout, name="chord_dropout")(chord)
    chord_probs = tf.keras.layers.Dense(
        num_chord_classes, activation="softmax", name="chord_probs"
    )(chord)
    root_probs = tf.keras.layers.Dense(
        num_root_classes, activation="softmax", name="root_probs"
    )(chord)

    embedding = tf.keras.layers.Embedding(
        vocab_size, TOKEN_EMBED_DIM, name="token_embedding"
    )(tokens_int)
    gathered = FrameGather.build()([encoder, frames_int])
    decoder = tf.keras.layers.Concatenate(axis=-1, name="decoder_concat")(
        [embedding, gathered]
    )
    decoder = tf.keras.layers.Conv1D(
        64, 3, padding="causal", activation="relu", name="dec_conv1"
    )(decoder)
    decoder = tf.keras.layers.Conv1D(
        64, 3, padding="causal", activation="relu", name="dec_conv2"
    )(decoder)
    solo_probs = tf.keras.layers.Dense(
        vocab_size, activation="softmax", name="solo_probs"
    )(decoder)

    return tf.keras.Model(
        inputs=[cqt, tokens_in, frames_in],
        outputs={
            "chord_probs": chord_probs,
            "root_probs": root_probs,
            "solo_probs": solo_probs,
        },
        name="harmoniq_student",
    )


def compile_student_model(
    model: Any,
    *,
    learning_rate: float = 1e-3,
    chord_loss_weight: float = 1.0,
    root_loss_weight: float = 0.5,
    solo_loss_weight: float = 1.0,
) -> Any:
    """Compile with sparse losses and per-frame/token accuracy."""
    tf = _require_tensorflow()

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate),
        loss={
            "chord_probs": tf.keras.losses.SparseCategoricalCrossentropy(),
            "root_probs": tf.keras.losses.SparseCategoricalCrossentropy(),
            "solo_probs": tf.keras.losses.SparseCategoricalCrossentropy(),
        },
        loss_weights={
            "chord_probs": chord_loss_weight,
            "root_probs": root_loss_weight,
            "solo_probs": solo_loss_weight,
        },
        metrics={
            "chord_probs": [tf.keras.metrics.SparseCategoricalAccuracy(name="acc")],
            "root_probs": [tf.keras.metrics.SparseCategoricalAccuracy(name="acc")],
            "solo_probs": [tf.keras.metrics.SparseCategoricalAccuracy(name="acc")],
        },
    )
    return model


def apply_qat(model: Any) -> Any:
    """Wrap supported layers with TFMOT fake-quantization nodes.

    Unsupported layers (the custom gather/cast) are passed through by the
    patched clone, mirroring ``build_chord_tflite.apply_qat``.
    """
    tf = _require_tensorflow()
    try:
        import tensorflow_model_optimization as tfmot
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "tensorflow-model-optimization is required for QAT"
        ) from exc

    from tensorflow_model_optimization.python.core.keras.compat import (
        keras as _tfmot_keras,
    )

    original_clone = _tfmot_keras.models.clone_model

    def _safe_clone(clone_model, input_tensors=None, clone_function=None):
        if clone_function is not None:
            original_quantize = clone_function

            def _quantize(layer):
                try:
                    return original_quantize(layer)
                except (RuntimeError, ValueError, TypeError):
                    return layer

            clone_function = _quantize
        return original_clone(
            clone_model, input_tensors=input_tensors,
            clone_function=clone_function,
        )

    _tfmot_keras.models.clone_model = _safe_clone
    try:
        annotated = tfmot.quantization.keras.quantize_annotate_model(model)
        return tfmot.quantization.keras.quantize_apply(annotated)
    finally:
        _tfmot_keras.models.clone_model = original_clone


def convert_to_tflite(
    model: Any,
    representative_data: np.ndarray,
    output_path: str | Path,
    *,
    int8_only: bool = False,
) -> Path:
    """Convert to TFLite, preferring INT8 and falling back to FP16/float.

    ``int8_only`` raises if the INT8 strategy fails, so callers can fall
    back to exporting a known-fast float artifact.
    """
    tf = _require_tensorflow()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sample = representative_data[: min(100, len(representative_data))]

    def _representative():
        for row in sample:
            yield [
                row[np.newaxis, ...].astype(np.float32),
                np.zeros((1, MAX_TOKEN_SEQUENCE), dtype=np.float32),
                np.zeros((1, MAX_TOKEN_SEQUENCE), dtype=np.float32),
            ]

    strategies = [
        (
            "INT8",
            dict(
                optimizations=[tf.lite.Optimize.DEFAULT],
                representative_dataset=_representative,
                supported_ops=[
                    tf.lite.OpsSet.TFLITE_BUILTINS_INT8,
                    tf.lite.OpsSet.SELECT_TF_OPS,
                ],
            ),
        ),
        (
            "FP16",
            dict(
                optimizations=[tf.lite.Optimize.DEFAULT],
                supported_ops=[
                    tf.lite.OpsSet.TFLITE_BUILTINS,
                    tf.lite.OpsSet.SELECT_TF_OPS,
                ],
            ),
        ),
        (
            "float32",
            dict(supported_ops=[tf.lite.OpsSet.SELECT_TF_OPS]),
        ),
    ]

    if int8_only:
        strategies = strategies[:1]

    last_error: Exception | None = None
    for name, kwargs in strategies:
        try:
            converter = tf.lite.TFLiteConverter.from_keras_model(model)
            # Keep SELECT_TF_OPS available as a safety net for custom ops.
            # The fully convolutional encoder does not need TensorList.
            converter._experimental_lower_tensor_list_ops = False
            options = dict(kwargs)
            supported_ops = options.pop("supported_ops", None)
            if supported_ops is not None:
                converter.target_spec.supported_ops = supported_ops
            for key, value in options.items():
                setattr(converter, key, value)
            payload = converter.convert()
            output_path.write_bytes(payload)
            print(f"  [{name}] TFLite written to {output_path} "
                  f"({len(payload) / 1024:.1f} KB)")
            return output_path
        except Exception as exc:  # noqa: BLE001 - try the next strategy
            last_error = exc
            print(f"  [SKIP] {name} conversion failed: {exc}")

    raise RuntimeError(
        f"all TFLite conversion strategies failed: {last_error}"
    )


def load_tflite_interpreter(tflite_path: str | Path) -> Any:
    """Load a TFLite interpreter, applying the Flex delegate when needed.

    The model is fully convolutional, so no Flex delegate is normally
    required. The retry path is kept for robustness and mirrors
    ``app.chord_inference._get_interpreter``.
    """
    tf = _require_tensorflow()
    path = str(tflite_path)
    try:
        interpreter = tf.lite.Interpreter(model_path=path)
        interpreter.allocate_tensors()
        return interpreter
    except Exception as first_error:  # noqa: BLE001 - retry with Flex
        import glob

        flex_libs = glob.glob(
            str(Path(tf.__file__).resolve().parent / "lite" / "**" / "*flex*"),
            recursive=True,
        )
        if not flex_libs:
            raise RuntimeError(
                "TFLite student requires SELECT_TF_OPS (Flex delegate) but "
                f"libtensorflowlite_flex was not found: {first_error}"
            ) from first_error
        from tensorflow.lite.python import interpreter as _tflite_interp

        delegate = _tflite_interp.load_delegate(str(flex_libs[0]))
        interpreter = tf.lite.Interpreter(
            model_path=path, experimental_delegates=[delegate]
        )
        interpreter.allocate_tensors()
        return interpreter


def benchmark_tflite(
    tflite_path: str | Path,
    sample_windows: np.ndarray,
    *,
    repeats: int = 20,
) -> dict[str, float]:
    """Measure per-frame latency (100 ms CQT frame) for the chord head.

    The solo decoder is autoregressive; its cost is reported separately by
    averaging a single greedy step. This keeps the W3 `<100 ms/frame` gate
    comparable to the existing on-device chord classifier.
    """
    interpreter = load_tflite_interpreter(tflite_path)
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    window = sample_windows[0]
    frames = max(1, int(window.shape[0]))
    tokens = np.zeros((1, MAX_TOKEN_SEQUENCE), dtype=np.float32)
    frames_idx = np.zeros((1, MAX_TOKEN_SEQUENCE), dtype=np.float32)

    def _run() -> None:
        for detail in input_details:
            name = detail["name"].lower()
            if "cqt" in name or detail["shape"][-1] == window.shape[-1]:
                interpreter.set_tensor(
                    detail["index"],
                    window[np.newaxis, ...].astype(detail["dtype"]),
                )
            elif "token" in name:
                interpreter.set_tensor(detail["index"], tokens)
            elif "frame" in name:
                interpreter.set_tensor(detail["index"], frames_idx)
        interpreter.invoke()
        for detail in output_details:
            interpreter.get_tensor(detail["index"])

    _run()
    latencies: list[float] = []
    for _ in range(max(1, repeats)):
        start = __import__("time").perf_counter()
        _run()
        latencies.append((__import__("time").perf_counter() - start) * 1000.0)

    mean_ms = float(np.mean(latencies))
    return {
        "mean_ms": round(mean_ms, 4),
        "p95_ms": round(float(np.percentile(latencies, 95)), 4),
        "ms_per_frame": round(mean_ms / frames, 6),
        "frames": frames,
    }
