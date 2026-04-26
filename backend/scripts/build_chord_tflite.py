"""
build_chord_tflite.py
=====================
Final Version: Uses Concrete Function tracing to bypass Keras 3 / Python 3.12 
serialization bugs.

Vocabulary: 12 Major + 12 Minor + 1 No-Chord (25 total)
Architecture: Circular Chroma Convolution with Harmonic Templates
"""

import os

# Force TensorFlow backend and CPU mode
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np
import tensorflow as tf

# ---------------------------------------------------------------------------
# 1. Constants & Vocabulary
# ---------------------------------------------------------------------------
CHORD_VOCAB = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
    "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm",
    "N",
]
NUM_CLASSES  = len(CHORD_VOCAB)
WINDOW       = 9
CHROMA_BINS  = 12

MAJOR_INTERVALS = [0, 4, 7]
MINOR_INTERVALS = [0, 3, 7]

# ---------------------------------------------------------------------------
# 2. Data Generation (Harmonic Overtones)
# ---------------------------------------------------------------------------
def make_chroma_template(root: int, quality: str = "major") -> np.ndarray:
    chroma = np.zeros(CHROMA_BINS, dtype=np.float32)
    intervals = MAJOR_INTERVALS if quality == "major" else MINOR_INTERVALS
    for interval in intervals:
        note = (root + interval) % CHROMA_BINS
        chroma[note] += 1.0                    # Fundamental
        chroma[(note + 7) % CHROMA_BINS] += 0.5 # 5th overtone (dominant)
        chroma[note] += 0.3                    # Octave
    total = chroma.sum()
    return chroma / total if total > 0 else chroma

def make_window(center_chroma: np.ndarray, noise_std: float = 0.12) -> np.ndarray:
    frames = [np.clip(center_chroma + np.random.randn(CHROMA_BINS).astype(np.float32) * noise_std, 0, 1) 
              for _ in range(WINDOW)]
    return np.stack(frames, axis=0)

def generate_dataset(samples_per_class: int = 1500):
    X, y, templates = [], [], []
    for q in ["major", "minor"]:
        for r in range(12):
            templates.append(make_chroma_template(r, q))
    templates.append(np.full(CHROMA_BINS, 1.0 / CHROMA_BINS, dtype=np.float32))

    for idx, template in enumerate(templates):
        for _ in range(samples_per_class):
            std = 0.08 + np.random.uniform(0, 0.12)
            X.append(make_window(template, std))
            y.append(idx)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)

# ---------------------------------------------------------------------------
# 3. Architecture
# ---------------------------------------------------------------------------
def build_model() -> tf.keras.Model:
    inputs = tf.keras.Input(shape=(WINDOW, CHROMA_BINS), name="chroma_window")

    # Circular Padding via Lambda (Cleaner for TFLite Graph Tracing)
    # Wraps axis-2: [batch, window, 12] -> [batch, window, 14]
    padded = tf.keras.layers.Lambda(
        lambda x: tf.concat([x[:, :, -1:], x, x[:, :, :1]], axis=-1),
        name="circular_pad"
    )(inputs)

    # Permute to treat chroma bins as the "sequence" steps for Conv1D
    x = tf.keras.layers.Permute((2, 1))(padded) 
    
    x = tf.keras.layers.Conv1D(64, kernel_size=3, padding="valid", activation="relu")(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.Conv1D(128, kernel_size=3, padding="same", activation="relu")(x)

    # Flatten preserves the temporal attack/decay profile across the 9 frames
    x = tf.keras.layers.Flatten()(x)
    
    x = tf.keras.layers.Dense(128, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    outputs = tf.keras.layers.Dense(NUM_CLASSES, activation="softmax", name="chord_probs")(x)

    return tf.keras.Model(inputs=inputs, outputs=outputs)

# ---------------------------------------------------------------------------
# 4. Training and the Concrete Conversion Fix
# ---------------------------------------------------------------------------
def run_pipeline():
    print("Generating dataset...")
    X, y = generate_dataset()
    p = np.random.permutation(len(X))
    X, y = X[p], y[p]
    
    model = build_model()
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    
    print("\nTraining...")
    model.fit(X, y, epochs=12, batch_size=256, validation_split=0.15, verbose=1)

    print("\nTracing model to Concrete Function (Bypassing Keras serialization)...")
    
    # 1. Trace the model call into a static graph
    @tf.function(input_signature=[tf.TensorSpec(shape=[None, WINDOW, CHROMA_BINS], dtype=tf.float32)])
    def run_model(input_tensor):
        return model(input_tensor, training=False)

    concrete_func = run_model.get_concrete_function()

    print("Converting to TFLite...")
    # 2. Convert from the concrete function directly
    converter = tf.lite.TFLiteConverter.from_concrete_functions([concrete_func])
    
    # Enable Dynamic Range Quantization for mobile performance
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    
    # Target standard TFLite ops but allow TF ops if needed for the padding
    converter.target_spec.supported_ops = [
        tf.lite.OpsSet.TFLITE_BUILTINS,
        tf.lite.OpsSet.SELECT_TF_OPS
    ]
    
    try:
        tflite_model = converter.convert()
        with open("chord_model.tflite", "wb") as f:
            f.write(tflite_model)
        print(f"\nSuccess! Saved chord_model.tflite ({len(tflite_model)/1024:.1f} KB)")
    except Exception as e:
        print(f"\nConversion failed: {e}")
        return

    # 5. Smoke Test
    print("\nRunning TFLite Inference Test...")
    interp = tf.lite.Interpreter(model_path="chord_model.tflite")
    interp.allocate_tensors()
    input_details = interp.get_input_details()[0]
    output_details = interp.get_output_details()[0]
    
    # Test D Major (root 2)
    test_input = make_window(make_chroma_template(2, "major"), 0.05)[np.newaxis]
    interp.set_tensor(input_details['index'], test_input)
    interp.invoke()
    res = interp.get_tensor(output_details['index'])[0]
    
    top_idx = np.argmax(res)
    print(f"Result: Predicted {CHORD_VOCAB[top_idx]} ({res[top_idx]:.1%})")

if __name__ == "__main__":
    run_pipeline()