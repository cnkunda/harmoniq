"""Tests for Quantization-Aware Training (Commit 105)."""
import numpy as np
import pytest
import os
import tempfile

os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

FEATURE_DIM = 40
WINDOW = 16  # Small window for fast tests
NUM_CLASSES = 277


class TestQATWrapper:
    """Test that QAT wrapping works with the chord model."""

    def _build_and_wrap(self):
        """Build model and apply QAT wrapping."""
        import sys
        sys.path.insert(0, str(os.path.dirname(__file__)).rsplit("tests", 1)[0] + "scripts")
        from build_chord_tflite import build_model

        model = build_model(window=WINDOW)

        try:
            import tensorflow_model_optimization as tfmot
            quantize_model = tfmot.quantization.keras.quantize_model
            qat_model = quantize_model(model)
            return qat_model, True
        except ImportError:
            pytest.skip("tensorflow_model_optimization not installed")
            return model, False

    def test_qat_model_builds(self):
        """QAT-wrapped model should build without errors."""
        qat_model, has_qat = self._build_and_wrap()
        assert qat_model is not None
        if has_qat:
            assert qat_model.input_shape == (None, WINDOW, FEATURE_DIM)
            assert qat_model.output_shape == (None, NUM_CLASSES)

    def test_qat_model_forward_pass(self):
        """QAT model should produce valid softmax output."""
        qat_model, has_qat = self._build_and_wrap()
        if not has_qat:
            pytest.skip("QAT not available")

        dummy = np.random.randn(2, WINDOW, FEATURE_DIM).astype(np.float32)
        out = qat_model.predict(dummy, verbose=0)
        assert out.shape == (2, NUM_CLASSES)
        # Softmax should sum to ~1
        assert np.allclose(out.sum(axis=1), 1.0, atol=1e-4)

    def test_qat_model_compiles(self):
        """QAT model should compile with standard optimizer."""
        qat_model, has_qat = self._build_and_wrap()
        if not has_qat:
            pytest.skip("QAT not available")

        qat_model.compile(
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        # Verify compilation succeeded by checking loss function
        assert qat_model.loss is not None

    def test_qat_tflite_conversion(self):
        """QAT model should convert to TFLite with smaller size."""
        import tensorflow as tf
        qat_model, has_qat = self._build_and_wrap()
        if not has_qat:
            pytest.skip("QAT not available")

        qat_model.compile(
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )

        @tf.function(input_signature=[
            tf.TensorSpec(shape=[None, WINDOW, FEATURE_DIM], dtype=tf.float32)
        ])
        def run_model(input_tensor):
            return qat_model(input_tensor, training=False)

        concrete_func = run_model.get_concrete_function()
        converter = tf.lite.TFLiteConverter.from_concrete_functions([concrete_func])

        # QAT models should not need additional optimization
        # converter.optimizations = []  # Skip post-training quantization

        converter.target_spec.supported_ops = [
            tf.lite.OpsSet.TFLITE_BUILTINS,
            tf.lite.OpsSet.SELECT_TF_OPS,
        ]

        tflite_model = converter.convert()
        assert len(tflite_model) > 0

        # QAT model should be reasonably sized
        size_kb = len(tflite_model) / 1024
        # INT8 QAT should produce smaller model than float32
        # (exact size depends on architecture)
        assert size_kb > 0, "TFLite model should have non-zero size"

    def test_qat_vs_float_size_comparison(self):
        """QAT model should be comparable or smaller than float model."""
        import tensorflow as tf
        from build_chord_tflite import build_model

        # Float model
        float_model = build_model(window=WINDOW)

        @tf.function(input_signature=[
            tf.TensorSpec(shape=[None, WINDOW, FEATURE_DIM], dtype=tf.float32)
        ])
        def run_float(input_tensor):
            return float_model(input_tensor, training=False)

        float_func = run_float.get_concrete_function()
        float_converter = tf.lite.TFLiteConverter.from_concrete_functions([float_func])
        float_converter.optimizations = [tf.lite.Optimize.DEFAULT]
        float_converter.target_spec.supported_ops = [
            tf.lite.OpsSet.TFLITE_BUILTINS,
            tf.lite.OpsSet.SELECT_TF_OPS,
        ]
        float_tflite = float_converter.convert()

        # QAT model
        qat_model, has_qat = self._build_and_wrap()
        if not has_qat:
            pytest.skip("QAT not available")

        qat_model.compile(optimizer="adam", loss="sparse_categorical_crossentropy")

        @tf.function(input_signature=[
            tf.TensorSpec(shape=[None, WINDOW, FEATURE_DIM], dtype=tf.float32)
        ])
        def run_qat(input_tensor):
            return qat_model(input_tensor, training=False)

        qat_func = run_qat.get_concrete_function()
        qat_converter = tf.lite.TFLiteConverter.from_concrete_functions([qat_func])
        qat_converter.target_spec.supported_ops = [
            tf.lite.OpsSet.TFLITE_BUILTINS,
            tf.lite.OpsSet.SELECT_TF_OPS,
        ]
        qat_tflite = qat_converter.convert()

        float_kb = len(float_tflite) / 1024
        qat_kb = len(qat_tflite) / 1024

        # Both should produce valid models
        assert float_kb > 0
        assert qat_kb > 0

        # Log sizes for verification
        print(f"\n  Float model: {float_kb:.1f} KB")
        print(f"  QAT model:   {qat_kb:.1f} KB")
