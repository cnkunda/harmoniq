"""Generate a librosa CQT parity fixture for the on-device TypeScript CQT.

Produces a JSON fixture consumed by `src/chord/computeCqt.test.ts` to verify the
client-side `computeCqt.ts` stays close to the training-time features produced by
`librosa.cqt` (see backend/app/chord_inference.py). The TS test regenerates the
same deterministic sine signals and compares selected frames (L1-normalized) via
cosine similarity and dominant-bin agreement.

Run inside the backend env (where librosa is installed):

    python backend/scripts/gen_cqt_fixture.py

Output:
    src/chord/__fixtures__/cqt_parity.json
"""

import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cqt_constants import TARGET_SR, HOP_SEC, BINS_PER_OCTAVE, CHROMA_BINS  # noqa: E402

FMIN_C1 = 32.70319566257483  # librosa.note_to_hz('C1')

OUT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "chord" / "__fixtures__" / "cqt_parity.json"
)


def _sine(freq: float, n: int, sr: int) -> np.ndarray:
    # Must match sine() in computeCqt.test.ts exactly.
    return np.sin(2 * np.pi * freq * np.arange(n) / sr).astype(np.float32)


def _cqt_frames(y: np.ndarray, sr: int) -> np.ndarray:
    """144-bin L1-normalized magnitude CQT, matching chord_inference.py."""
    import librosa

    hop = int(sr * HOP_SEC)
    cqt = librosa.cqt(
        y=y, sr=sr, hop_length=hop, n_bins=CHROMA_BINS,
        bins_per_octave=BINS_PER_OCTAVE, fmin=FMIN_C1,
    )
    cqt = np.abs(cqt).T.astype(np.float32)
    norms = cqt.sum(axis=1, keepdims=True).clip(1e-8, None)
    return cqt / norms


def main() -> None:
    sr = TARGET_SR
    # Bin centres for a few well-separated pitches (bins 48/72/96 in the vocab grid).
    cases_spec = [
        ("sine_bin48", FMIN_C1 * 2 ** (48 / BINS_PER_OCTAVE)),
        ("sine_bin72", FMIN_C1 * 2 ** (72 / BINS_PER_OCTAVE)),
        ("sine_bin96", FMIN_C1 * 2 ** (96 / BINS_PER_OCTAVE)),
    ]
    num_samples = sr  # 1 second
    frame_indices = [4, 7]

    cases = []
    for name, freq in cases_spec:
        y = _sine(freq, num_samples, sr)
        frames = _cqt_frames(y, sr)
        picked = [frames[i].tolist() for i in frame_indices]
        cases.append({
            "name": name,
            "kind": "sine",
            "freq": float(freq),
            "num_samples": int(num_samples),
            "frame_indices": frame_indices,
            "frames": picked,
        })

    fixture = {
        "sample_rate": int(sr),
        "hop": int(sr * HOP_SEC),
        "n_bins": int(CHROMA_BINS),
        "bins_per_octave": int(BINS_PER_OCTAVE),
        "cases": cases,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(fixture, indent=2))
    print(f"Wrote {OUT_PATH} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
