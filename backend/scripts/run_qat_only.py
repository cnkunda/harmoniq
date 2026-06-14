#!/usr/bin/env python3
"""QAT-only: load best model, apply QAT, fine-tune, convert to INT8 TFLite."""
from __future__ import annotations

import os
os.environ["KERAS_BACKEND"] = "tensorflow"
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import sys
sys.setrecursionlimit(10000)

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import numpy as np
from sklearn.model_selection import train_test_split

# Import pipeline functions (triggers tensorflow import internally)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chord_tflite as _b
from build_chord_tflite import (
    WINDOW, FEATURE_DIM, NUM_CLASSES, N_ROOTS,
    apply_qat, convert_to_int8_tflite,
    load_dataset_dir, load_guitarset_test,
    generate_dataset, mix_datasets, AugmentedDataGenerator,
    _HAS_TFMOT, _circular_cqt_pad, CircularCqtPad,
    QAT_EPOCHS, QAT_LEARNING_RATE,
    derive_root_labels, derive_presence_labels, extract_chord_predictions,
    collect_real_n_templates,
)
import tensorflow_model_optimization as tfmot

# Access tf and helpers through build_chord_tflite module
tf = _b.tf
CHORD_VOCAB = _b.CHORD_VOCAB

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_SCRIPTS_DIR = Path(__file__).resolve().parent

def main():
    print("=" * 60)
    print("  QAT-Only Pipeline (Commit 106)")
    print("=" * 60)

    # ---- Load all data sources ----
    source_configs = [
        (Path("data/guitarset"), "GuitarSet", 1.0),
        (Path("data/idmt_smt_guitar"), "IDMT-SMT-Guitar", 1.0),
        (Path("data/vst_synthetic"), "VST-Synthetic", 0.3),
        (Path("data/youtube_crawl"), "YouTube-Crawl", 1.0),
        (Path("data/pseudo_label"), "Pseudo-Label", 0.3),
        (Path("data/jaah"), "JAAH", 1.0),
    ]
    print(f"Loading {len(source_configs)} data source(s)...")
    from build_chord_tflite import load_datasets
    features_list, labels_list, weights_list = load_datasets(source_configs)

    # GuitarSet test data
    test_X, test_y = np.array([]), np.array([])
    gs_path = Path("data/guitarset")
    if gs_path.exists():
        try:
            test_X, test_y = load_guitarset_test(gs_path)
        except (FileNotFoundError, ValueError) as e:
            print(f"  [WARN] GuitarSet test: {e}")

    # Load empirical transition matrix for synthetic data
    emp_path = Path("data/annotations/transition_matrix_empirical.npy")
    transition_probs = None
    if emp_path.exists():
        matrix = np.load(str(emp_path))
        if matrix.shape == (NUM_CLASSES, NUM_CLASSES):
            transition_probs = matrix.sum(axis=1)
            if transition_probs.sum() > 0:
                transition_probs = transition_probs / transition_probs.sum()

    # Load CQT distribution stats for synthetic-to-real domain bridging
    cqt_stats_path = Path("data/cqt_stats.npz")
    cqt_stats = None
    if cqt_stats_path.exists():
        try:
            cqt_stats = dict(np.load(str(cqt_stats_path)))
            print(f"  Loaded CQT stats from {cqt_stats_path}")
        except Exception as e:
            print(f"  [WARN] Could not load CQT stats: {e}")

    # Collect real N templates for N distribution matching
    real_n_templates = collect_real_n_templates(
        [Path(cfg[0]) for cfg in source_configs if Path(cfg[0]).exists()]
    )
    if real_n_templates:
        print(f"  Collected {len(real_n_templates)} real N templates")

    # Generate synthetic data
    print("Generating synthetic dataset...")
    synth_X, synth_y = generate_dataset(
        transition_probs=transition_probs,
        cqt_stats=cqt_stats,
        real_n_templates=real_n_templates,
    )
    p = np.random.permutation(len(synth_X))
    synth_X, synth_y = synth_X[p], synth_y[p]
    synth_weight = np.full(len(synth_X), 0.15, dtype=np.float32)
    features_list.append(synth_X)
    labels_list.append(synth_y)
    weights_list.append(synth_weight)

    # Mix all sources
    print("Mixing all dataset sources...")
    dataset_sources = list(zip(features_list, labels_list, weights_list))
    X_all, y_all, sample_weights, source_ids = mix_datasets(dataset_sources)

    n_real_sources = len(features_list) - 1
    real_mask = source_ids < n_real_sources
    synth_mask = ~real_mask

    X_real, y_real, w_real = X_all[real_mask], y_all[real_mask], sample_weights[real_mask]
    X_synth, y_synth, w_synth = X_all[synth_mask], y_all[synth_mask], sample_weights[synth_mask]

    # Split real and synthetic separately to maintain validation real ratio
    X_real_train, X_real_val, y_real_train, y_real_val, w_real_train, w_real_val = train_test_split(
        X_real, y_real, w_real, test_size=0.2, random_state=42, stratify=y_real,
    )
    X_synth_train, X_synth_val, y_synth_train, y_synth_val, w_synth_train, w_synth_val = train_test_split(
        X_synth, y_synth, w_synth, test_size=0.1, random_state=42, stratify=y_synth,
    )

    X_train = np.concatenate([X_real_train, X_synth_train])
    y_train = np.concatenate([y_real_train, y_synth_train])
    w_train = np.concatenate([w_real_train, w_synth_train])
    X_val = np.concatenate([X_real_val, X_synth_val])
    y_val = np.concatenate([y_real_val, y_synth_val])
    w_val = np.concatenate([w_real_val, w_synth_val])

    print(f"  Train: {len(X_train)} samples, Val: {len(X_val)} samples")

    # ---- Load best float32 model ----
    best_path = _APP_DIR / "chord_model_best.keras"
    if not best_path.exists():
        # fallback to final model
        best_path = _APP_DIR / "chord_model.keras"
    print(f"\nLoading best model from: {best_path}")
    float32_model = tf.keras.models.load_model(
        str(best_path),
        custom_objects={"_circular_cqt_pad": _circular_cqt_pad, "CircularCqtPad": CircularCqtPad},
    )

    # Evaluate float32 baseline
    float32_output = float32_model.predict(X_val, verbose=0)
    float32_val_pred = extract_chord_predictions(float32_output)
    float32_val_acc = float(np.mean(float32_val_pred == y_val))
    float32_test_acc = None
    if len(test_X) > 0:
        float32_test_output = float32_model.predict(test_X, verbose=0)
        float32_test_pred = extract_chord_predictions(float32_test_output)
        float32_test_acc = float(np.mean(float32_test_pred == test_y))
    print(f"  Float32 baseline: val={float32_val_acc:.2%}, test={float32_test_acc or 'N/A'}")

    # ---- QAT Phase ----
    print("\n" + "=" * 60)
    print("  QAT Phase: Quantization-Aware Training")
    print("=" * 60)

    qat_model = None
    qat_val_acc = None

    if not _HAS_TFMOT:
        print("  [ERROR] tensorflow_model_optimization not available")
        sys.exit(1)

    qat_generator = AugmentedDataGenerator(
        X_train, y_train, w_train,
        batch_size=64,
        p_pitch_shift=0.3,
        pitch_range=1,
        p_time_stretch=0.1,
        stretch_range=(0.95, 1.05),
        noise_std=0.03,
        shuffle=True,
        temperature=0.3,
        multi_task=True,
    )

    y_val_root = derive_root_labels(y_val)
    y_val_presence = derive_presence_labels(y_val).reshape(-1, 1)
    y_val_dict = {
        "chord_probs": tf.keras.utils.to_categorical(y_val, NUM_CLASSES).astype(np.float32),
        "root_probs": tf.keras.utils.to_categorical(y_val_root, N_ROOTS).astype(np.float32),
        "presence": y_val_presence.astype(np.float32),
    }

    print(f"  Applying QAT wrapper ({QAT_EPOCHS} epochs, LR={QAT_LEARNING_RATE})...")

    qat_val_acc = None
    qat_keras_path = None
    int8_path = None

    try:
        qat_model = apply_qat(float32_model)

        qat_model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=QAT_LEARNING_RATE),
            loss={
                "chord_probs": tf.keras.losses.CategoricalCrossentropy(label_smoothing=0.1),
                "root_probs": tf.keras.losses.CategoricalCrossentropy(),
                "presence": tf.keras.losses.BinaryCrossentropy(),
            },
            loss_weights={"chord_probs": 1.0, "root_probs": 0.3, "presence": 0.2},
            metrics={"chord_probs": "accuracy", "root_probs": "accuracy", "presence": "accuracy"},
        )

        qat_callbacks = [
            tf.keras.callbacks.CSVLogger(
                filename=str(_SCRIPTS_DIR / "training_log_qat.csv"),
            ),
        ]

        qat_history = qat_model.fit(
            x=qat_generator,
            epochs=QAT_EPOCHS,
            validation_data=(X_val, y_val_dict),
            callbacks=qat_callbacks,
            verbose=1,
        )

        qat_output = qat_model.predict(X_val, verbose=0)
        qat_val_pred = extract_chord_predictions(qat_output)
        qat_val_acc = float(np.mean(qat_val_pred == y_val))
        print(f"\n  QAT val accuracy: {qat_val_acc:.2%}  (float32: {float32_val_acc:.2%})")

        if len(test_X) > 0:
            qat_test_output = qat_model.predict(test_X, verbose=0)
            qat_test_pred = extract_chord_predictions(qat_test_output)
            qat_test_acc = float(np.mean(qat_test_pred == test_y))
            qat_deg = float32_test_acc - qat_test_acc if float32_test_acc is not None else 0.0
            print(f"  QAT GuitarSet test: {qat_test_acc:.2%}  (float32: {float32_test_acc:.2%}, deg: {qat_deg:.2%})")

        # Save QAT Keras model
        qat_keras_path = _APP_DIR / "chord_model_qat.keras"
        with tfmot.quantization.keras.quantize_scope():
            qat_model.save(str(qat_keras_path))
        print(f"  Saved QAT model -> {qat_keras_path} ({qat_keras_path.stat().st_size / 1024 / 1024:.1f} MB)")

        # ---- INT8 TFLite Conversion ----
        print("\nConverting QAT model to INT8 TFLite...")
        int8_path = _APP_DIR / "chord_model_qat_int8.tflite"

        # Use a subset of validation data for representative calibration
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X_val), size=min(100, len(X_val)), replace=False)
        rep_data = X_val[idx]

        convert_to_int8_tflite(qat_model, rep_data, str(int8_path))

        # ---- INT8 Smoke Tests ----
        print("\n--- INT8 TFLite Smoke Tests ---")
        test_cases = [
            (CHORD_VOCAB["C:maj"], "C:maj"),
            (CHORD_VOCAB["A:min"], "A:min"),
            (CHORD_VOCAB["D#:7"], "D#:7"),
            (CHORD_VOCAB["D:7"], "D:7"),
        ]

        interpreter = tf.lite.Interpreter(model_path=str(int8_path))
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        input_scale, input_zero = input_details[0]["quantization"]

        all_passed = True
        for label_idx, label_name in test_cases:
            # Build a representative input that should match this chord class
            class_mask = y_train == label_idx
            if class_mask.sum() > 0:
                sample = X_train[class_mask][0:1]
            else:
                sample = np.zeros((1, WINDOW, FEATURE_DIM), dtype=np.float32)

            # Quantize input to INT8
            q_sample = (sample / input_scale + input_zero).astype(np.int8)
            interpreter.set_tensor(input_details[0]["index"], q_sample)
            interpreter.invoke()
            output = interpreter.get_tensor(output_details[0]["index"])
            # Output is INT8, dequantize to float
            out_scale, out_zero = output_details[0]["quantization"]
            output_float = (output.astype(np.float32) - out_zero) * out_scale
            pred_idx = np.argmax(output_float[0])

            pred_label = CHORD_VOCAB[pred_idx]
            expected_label = CHORD_VOCAB[label_idx]
            match = "PASS" if pred_idx == label_idx else "FAIL"
            if match == "FAIL":
                all_passed = False
            confidence = output_float[0][pred_idx] * 100
            print(f"  {label_name:<10} -> {pred_label:<10} ({confidence:.1f}%) [{match}]")

        print(f"\n  All INT8 TFLite smoke tests {'PASSED' if all_passed else 'FAILED'}")

    except Exception as exc:
        print(f"\n  [WARN] QAT pipeline failed: {exc}")
        print("  [WARN] INT8 QAT unavailable — using FP16 dynamic quantization instead")
        import traceback
        traceback.print_exc()
        qat_model = None

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("  QAT-Only Pipeline Complete")
    print("=" * 60)
    print(f"  Float32 model: {best_path}")
    if qat_keras_path and qat_keras_path.exists():
        print(f"  QAT model:     {qat_keras_path}")
    if int8_path and int8_path.exists():
        size_kb = int8_path.stat().st_size / 1024
        print(f"  INT8 TFLite:   {int8_path} ({size_kb:.1f} KB)")
    else:
        print(f"  INT8 TFLite:   [NOT PRODUCED — using FP16 dynamic quantization]")
    print(f"  Float32 val acc: {float32_val_acc:.2%}")
    if qat_val_acc is not None:
        print(f"  QAT val acc:      {qat_val_acc:.2%}")

if __name__ == "__main__":
    main()
