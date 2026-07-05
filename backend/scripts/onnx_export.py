"""Export chord_model.keras to ONNX for web inference via onnxruntime-web."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ["TF_USE_LEGACY_KERAS"] = "1"
import tensorflow as tf
import tf2onnx

from scripts.build_chord_tflite import CircularCqtPad

# Load the multi-task model, then extract the chord_probs-only sub-model
keras_path = REPO_ROOT / "backend" / "app" / "chord_model.keras"
full = tf.keras.models.load_model(
    str(keras_path),
    custom_objects={"CircularCqtPad": CircularCqtPad},
    safe_mode=False,
)
print(f"Loaded full model — input: {full.input_shape}, outputs: {list(full.output_names)}")

# Build a single-output model (chord_probs head only)
model = tf.keras.Model(inputs=full.input, outputs=full.get_layer("chord_probs").output)
print(f"Single-output model — input: {model.input_shape}, output: {model.output_shape}")

# Convert to ONNX
onnx_path = REPO_ROOT / "assets" / "models" / "chord_model.onnx"
onnx_path.parent.mkdir(parents=True, exist_ok=True)

spec = (tf.TensorSpec(model.input_shape, tf.float32, name="input"),)
model_proto, _ = tf2onnx.convert.from_keras(model, input_signature=spec, output_path=str(onnx_path))
size_kb = onnx_path.stat().st_size / 1024
print(f"Saved ONNX -> {onnx_path}  ({size_kb:.1f} KB)")
