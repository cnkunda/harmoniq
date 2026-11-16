"""BTC 170-class chord teacher (Phase 2 teacher availability + inference).

BTC (Park et al., ISMIR 2019 — "A Bi-Directional Transformer for Musical
Chord Recognition") ships a 170-class large-vocabulary checkpoint whose
class set is identical to the Chord 170 vocabulary:

    root in C..B (12) × quality in
    [min, maj, dim, aug, min6, maj6, min7, minmaj7, maj7, 7, dim7, hdim7,
     sus2, sus4] (14)  →  index = root * 14 + quality
    168 = X (unknown), 169 = N (no chord)

Our vocabulary is the same set re-ordered (quality-major, 12 roots inner,
N = 168, X = 169), so the teacher mapping is a pure permutation — see
:func:`map_btc_index_to_170`. Round-trip is verified in tests.

Model loading bypasses the HF wrapper's ``transformers`` import (it costs
minutes on this WSL mount); the vendored ``btc_src`` (torch + librosa) is
used directly and the wrapper's ``predict`` loop is replicated.

Licence: the BTC source code is MIT, but the released 170-class weights are
trained on Isophonics / Robbie Williams / UsPop2002 and are distributed as
**CC-BY-NC-SA 4.0 (non-commercial)**. Confirmed acceptable for this
research project by the project owner; must not ship in a commercial build.

Usage (from backend/)::

    python scripts/btc_teacher.py --check
    python scripts/btc_teacher.py --audio data/guitarset/raw/audio_mono-mix/00_BN1-129-Eb_comp_mix.wav
    python scripts/btc_teacher.py --audio song.wav --json /tmp/btc.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.chord_labels import normalize_quality, pitch_class_from_name  # noqa: E402
from app.chord_vocab_170 import (  # noqa: E402
    CHORD_TO_IDX_170,
    N_IDX_170,
    ROOTS_12,
    X_IDX_170,
)

BTC_MODEL_DIR = _BACKEND_DIR / "data" / "models" / "btc"
BTC_CHECKPOINT = "btc_model_large_voca.pt"

# Vendored BTC vocabulary (btc_src/features.py idx2voca_chord()).
BTC_ROOT_ORDER = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
BTC_QUALITY_ORDER = [
    "min", "maj", "dim", "aug", "min6", "maj6", "min7", "minmaj7",
    "maj7", "7", "dim7", "hdim7", "sus2", "sus4",
]
BTC_NUM_CHORDS = 168
BTC_X_IDX = 168
BTC_N_IDX = 169

# BTC hyperparameters (from the original run_config.yaml).
_MODEL_CFG = dict(
    feature_size=144, timestep=108,
    input_dropout=0.2, layer_dropout=0.2, attention_dropout=0.2, relu_dropout=0.2,
    num_layers=8, num_heads=4, hidden_size=128,
    total_key_depth=128, total_value_depth=128, filter_size=128,
    loss="ce", probs_out=False, num_chords=170,
)
_TIMESTEP = 108
_SONG_HZ = 22050
_INST_LEN = 10.0
_HOP = 2048


def btc_label(idx: int) -> str | None:
    """Return the BTC vocabulary label for a class index (our 170 format)."""
    if idx == BTC_N_IDX:
        return "N"
    if idx == BTC_X_IDX:
        return "X"
    if not 0 <= idx < BTC_NUM_CHORDS:
        raise ValueError(f"BTC index out of range: {idx}")
    root = BTC_ROOT_ORDER[idx // 14]
    quality = BTC_QUALITY_ORDER[idx % 14]
    return f"{root}:{quality}"


def map_btc_index_to_170(idx: int) -> int:
    """Map a BTC class index to our 170-class index (pure permutation)."""
    label = btc_label(idx)
    assert label is not None
    return CHORD_TO_IDX_170[label]


BTC_INDEX_TO_170: np.ndarray = np.array(
    [map_btc_index_to_170(i) for i in range(170)], dtype=np.int64
)


def btc_chord_to_170(label: str) -> str | None:
    """Normalize a BTC timeline chord label to our 170 label format.

    BTC emits bare roots for major chords (``C``) and ``root:quality``
    otherwise. Returns None for unparseable labels.
    """
    label = label.strip()
    if label in ("N", "X"):
        return label
    root, _, quality = label.partition(":")
    if root not in ROOTS_12:
        return None
    normalized = normalize_quality(quality)
    if normalized is None:
        return None
    return f"{root}:{normalized}"


class BtcTeacher:
    """Thin BTC inference wrapper (torch + librosa, no transformers import)."""

    def __init__(self, model_dir: Path = BTC_MODEL_DIR, device: str = "cpu"):
        import importlib
        import torch

        self._torch = torch
        self._device = device
        repo = Path(model_dir).resolve()
        checkpoint = repo / BTC_CHECKPOINT
        if not checkpoint.exists():
            raise FileNotFoundError(
                f"BTC checkpoint missing: {checkpoint}\n"
                "Download with: python -c \"from huggingface_hub import "
                "snapshot_download; snapshot_download('puar-playground/btc-chord', "
                f"local_dir='{repo}')\""
            )
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        btc_model_module = importlib.import_module("btc_src.btc_model")
        self._features = importlib.import_module("btc_src.features")
        self._model = btc_model_module.BTC_model(config=_MODEL_CFG).to(device)
        state = torch.load(str(checkpoint), map_location=device, weights_only=False)
        self._model.load_state_dict(state["model"])
        self._model.eval()
        self._mean = state["mean"]
        self._std = state["std"]

    def predict_timeline(self, audio_path: str | Path) -> list[dict]:
        """Return ``[{start, end, chord}, ...]`` with BTC labels."""
        torch = self._torch
        feat = self._features.audio_to_features(
            str(audio_path), sr_target=_SONG_HZ, inst_len=_INST_LEN,
            n_bins=144, bins_per_octave=24, hop_length=_HOP,
        )
        feat = feat.T
        feat = (feat - self._mean) / self._std
        time_unit = _INST_LEN / _TIMESTEP
        n = _TIMESTEP
        pad = n - (feat.shape[0] % n)
        feat = np.pad(feat, ((0, pad), (0, 0)), mode="constant", constant_values=0)
        n_instances = feat.shape[0] // n

        x = torch.tensor(feat, dtype=torch.float32).unsqueeze(0).to(self._device)
        idx_to_chord = self._features.idx2voca_chord()
        lines: list[dict] = []
        start_time = 0.0
        prev = None
        with torch.no_grad():
            for t in range(n_instances):
                attn_out, _ = self._model.self_attn_layers(x[:, n * t:n * (t + 1), :])
                pred, _ = self._model.output_layer(attn_out)
                pred = pred.squeeze()
                for i in range(n):
                    if t == 0 and i == 0:
                        prev = int(pred[i].item())
                        continue
                    cur = int(pred[i].item())
                    if cur != prev:
                        end = time_unit * (n * t + i)
                        lines.append({"start": round(start_time, 3),
                                      "end": round(end, 3),
                                      "chord": idx_to_chord[prev]})
                        start_time = end
                        prev = cur
                    if t == n_instances - 1 and i + pad == n:
                        end = time_unit * (n * t + i)
                        if start_time != end:
                            lines.append({"start": round(start_time, 3),
                                          "end": round(end, 3),
                                          "chord": idx_to_chord[prev]})
                        break
        return lines


def check_mapping() -> dict:
    """Bijection check between BTC and 170 vocabularies (no model load)."""
    labels_btc = [btc_label(i) for i in range(170)]
    mapped = sorted(map_btc_index_to_170(i) for i in range(170))
    return {
        "btc_classes": len(labels_btc),
        "unique_mapped_indices": len(set(mapped)),
        "is_bijection": mapped == list(range(170)),
        "n_is_our_index": map_btc_index_to_170(BTC_N_IDX) == N_IDX_170,
        "x_is_our_index": map_btc_index_to_170(BTC_X_IDX) == X_IDX_170,
        "sample": {i: btc_label(i) for i in (0, 1, 14, 27, 167, 168, 169)},
        "checkpoint_present": (BTC_MODEL_DIR / BTC_CHECKPOINT).exists(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the vocabulary mapping")
    parser.add_argument("--audio", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None, help="write the timeline JSON here")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)

    if args.check:
        print(json.dumps(check_mapping(), indent=2))
        if args.audio is None:
            return 0

    if args.audio is None:
        return 0

    teacher = BtcTeacher(device=args.device)
    timeline = teacher.predict_timeline(args.audio)
    mapped = [
        {**line, "chord170": btc_chord_to_170(line["chord"])}
        for line in timeline
    ]
    payload = {"audio": str(args.audio), "teacher": "btc", "events": mapped}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"wrote {args.json}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
