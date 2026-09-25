"""Reverb impulse response (IR) management for training data augmentation.

Downloads and manages IRs from OpenAIR (University of York) and EchoThief
public datasets. Applies convolution reverb to synthetic audio during
VST pipeline rendering to simulate diverse recording environments.

Usage:
    python -m app.reverb_ir [--download] [--list]

Data directory: data/ir/
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

IR_DIR = Path(__file__).resolve().parent.parent / "data" / "ir"

# OpenAIR impulse responses (mono, 44.1kHz, various room types)
OPENAIR_IRS: dict[str, str] = {
    "small_room": "https://www.openairlib.net/sites/default/files/impulse_responses/small_room.wav",
    "medium_hall": "https://www.openairlib.net/sites/default/files/impulse_responses/medium_hall.wav",
    "large_hall": "https://www.openairlib.net/sites/default/files/impulse_responses/large_hall.wav",
    "plate": "https://www.openairlib.net/sites/default/files/impulse_responses/plate_reverb.wav",
    "spring": "https://www.openairlib.net/sites/default/files/impulse_responses/spring_reverb.wav",
}


def get_available_irs() -> list[str]:
    """List available impulse response files."""
    if not IR_DIR.exists():
        return []
    return sorted([f.stem for f in IR_DIR.glob("*.wav")])


def load_ir(name: str, sr: int = 44100) -> Optional[np.ndarray]:
    """Load an impulse response file.

    Args:
        name: IR name (without extension), e.g. 'small_room'
        sr: Target sample rate (IRs are resampled if needed)

    Returns:
        Mono IR array, or None if not found.
    """
    import soundfile as sf

    ir_path = IR_DIR / f"{name}.wav"
    if not ir_path.exists():
        return None

    ir, ir_sr = sf.read(str(ir_path))
    if ir.ndim > 1:
        ir = ir.mean(axis=1)

    if ir_sr != sr:
        from scipy import signal
        ratio = sr / ir_sr
        new_len = int(len(ir) * ratio)
        ir = signal.resample(ir, new_len)

    return ir.astype(np.float32)


def apply_reverb(
    audio: np.ndarray,
    ir: np.ndarray,
    mix: float = 0.3,
) -> np.ndarray:
    """Apply convolution reverb to audio.

    Args:
        audio: Mono audio array (N,)
        ir: Impulse response array (M,)
        mix: Wet/dry mix (0 = dry, 1 = fully wet)

    Returns:
        Processed audio same length as input.
    """
    from scipy.signal import fftconvolve

    wet = fftconvolve(audio, ir, mode="same")
    wet = wet / (np.max(np.abs(wet)) + 1e-10)
    wet = wet * np.max(np.abs(audio))

    output = (1.0 - mix) * audio + mix * wet
    return output.astype(np.float32)


def apply_random_reverb(
    audio: np.ndarray,
    sr: int = 44100,
    mix_range: tuple[float, float] = (0.1, 0.4),
) -> np.ndarray:
    """Apply a random reverb IR from the available collection.

    Falls back to a simple synthetic reverb if no IRs are available.

    Args:
        audio: Mono audio array
        sr: Sample rate
        mix_range: (min_mix, max_mix) wet/dry mix range

    Returns:
        Reverberated audio.
    """
    available = get_available_irs()
    mix = np.random.uniform(*mix_range)

    if available:
        name = np.random.choice(available)
        ir = load_ir(name, sr)
        if ir is not None:
            return apply_reverb(audio, ir, mix)

    # Fallback: synthetic exponential decay reverb
    decay_time = np.random.uniform(0.1, 0.8)
    n_ir = int(sr * decay_time)
    t = np.linspace(0, decay_time, n_ir)
    ir = np.exp(-t * 8.0) * np.random.randn(n_ir).astype(np.float32)
    ir[0] = 1.0
    ir = ir / np.sum(np.abs(ir))

    return apply_reverb(audio, ir, mix)


def download_irs(data_dir: Path | None = None) -> int:
    """Download impulse responses from OpenAIR and EchoThief.

    Returns number of successfully downloaded IRs.
    """
    import requests

    ir_dir = Path(data_dir) / "ir" if data_dir else IR_DIR
    ir_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for name, url in OPENAIR_IRS.items():
        out_path = ir_dir / f"{name}.wav"
        if out_path.exists():
            print(f"  [SKIP] {name}.wav exists")
            count += 1
            continue

        print(f"  [DOWNLOAD] {name}...", end=" ", flush=True)
        try:
            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            print("done")
            count += 1
        except requests.RequestException as e:
            print(f"failed: {e}")

    return count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reverb IR manager")
    parser.add_argument("--download", action="store_true",
                        help="Download IRs from OpenAIR")
    parser.add_argument("--list", action="store_true",
                        help="List available IRs")
    args = parser.parse_args()

    if args.list:
        irs = get_available_irs()
        if irs:
            print("Available IRs:")
            for ir in irs:
                print(f"  {ir}")
        else:
            print("No IRs found. Use --download to fetch them.")
    elif args.download:
        count = download_irs()
        print(f"Downloaded {count} IRs")
    else:
        print("Use --download to fetch IRs or --list to see available ones")
