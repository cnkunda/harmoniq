#!/usr/bin/env python3
"""
Smoke-test htdemucs_6s guitar stem usability: normalize → Demucs → heuristics → PASS/FAIL.

Uses several weak automated gates on purpose: no single metric is trustworthy for stem
quality, but together they catch obvious failures (silent stem, buried guitar, extreme
vocal leakage) before anyone relies on tabs/transcription.

Smoke thresholds only — not Demucs hyperparameter tuning. Exit code 1 if any track fails.

Dependencies (explicit):
  - Python: backend install per ``pyproject.toml`` (``librosa``, ``demucs``, ``numpy``).
  - System: ``ffmpeg`` on PATH (used by ``app.pipeline_proof.ffmpeg_normalize_wav``).
  - Optional: ``matplotlib`` only when passing ``--spectrograms``.

This file is run as a script, not as an installed package; the ``sys.path`` line below
makes ``app.*`` imports resolve when you ``cd backend`` and run
``python scripts/smoke_stems.py ...``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import librosa
import numpy as np

# Allow `python scripts/smoke_stems.py` from backend/ (package root on pythonpath)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.pipeline_proof import (  # noqa: E402
    TARGET_SR,
    ffmpeg_normalize_wav,
    run_demucs_htdemucs_6s,
)

# --- Derived / layout -----------------------------------------------------------------
SLUG_MAX_CHARS = 64

# --- Spectrogram STFT (visual diagnostics only; not used for pass/fail) ---------------
SPEC_N_FFT = 2048
SPEC_HOP_LENGTH = 512
SPEC_FIG_WIDTH_IN = 10
SPEC_FIG_HEIGHT_IN = 3
SPEC_PNG_DPI = 120

# --- Envelope / correlation (bleed hint vs vocals stem) -------------------------------
# ~46 ms at 44.1 kHz — wide enough to smooth onset chatter, short enough to track phrasing.
ENVELOPE_FRAME_SAMPLES = 2048
ENVELOPE_MIN_SAMPLES = 32
ENVELOPE_STD_FLOOR = 1e-12

# --- Numeric floors (avoid divide-by-zero; values below are negligible in float audio) --
RMS_MIX_FLOOR = 1e-12
SNR_ENERGY_FLOOR = 1e-20

# --- Smoke thresholds (calibrate against human checklist; not model tuning) -----------
# Reject obvious silence / junk guitar stem (float WAV typically ~0.01–0.2 RMS for music).
MIN_RMS_GUITAR = 1e-3
# Guitar should carry a modest share of full-mix energy if it is a real isolated part.
MIN_RATIO_GUITAR_TO_MIX = 0.018
# Coarse mix-minus-guitar energy ratio (see snr_proxy_db); catches “stem explains nothing.”
MIN_SNR_PROXY_DB = 2.0
# Very high guitar–vocal envelope agreement often means vocal bleed (see checklist: false positives).
MAX_VOCALS_ENVELOPE_CORR = 0.96


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x), dtype=np.float64)))


def _align_len(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = min(a.shape[0], b.shape[0])
    return a[:n], b[:n]


def snr_proxy_db(guitar: np.ndarray, mix: np.ndarray) -> float:
    """
    Decibel ratio of mean guitar energy to mean ``(mix − guitar)`` energy.

    Demucs stems are not a phase-aligned linear sum of the mix, so ``mix − guitar`` is
    not a true acoustic residual — this is only a coarse “does the guitar buffer look
    like it belongs to this mix” smoke check, not SNR engineering.
    """
    g, m = _align_len(guitar, mix)
    residual = m.astype(np.float64) - g.astype(np.float64)
    num = np.mean(np.square(g)) + SNR_ENERGY_FLOOR
    den = np.mean(np.square(residual)) + SNR_ENERGY_FLOOR
    return float(10.0 * np.log10(num / den))


def smoothed_envelope(y: np.ndarray, *, frame: int = ENVELOPE_FRAME_SAMPLES) -> np.ndarray:
    y = np.abs(y.astype(np.float64))
    fr = frame
    if y.size < fr:
        fr = max(ENVELOPE_MIN_SAMPLES, y.size // 4 or ENVELOPE_MIN_SAMPLES)
    k = np.ones(fr, dtype=np.float64) / float(fr)
    return np.convolve(y, k, mode="same")


def envelope_pearson(a: np.ndarray, b: np.ndarray) -> float:
    a, b = _align_len(a, b)
    ea = smoothed_envelope(a)
    eb = smoothed_envelope(b)
    ea = ea - ea.mean()
    eb = eb - eb.mean()
    da = float(np.std(ea))
    db = float(np.std(eb))
    if da < ENVELOPE_STD_FLOOR or db < ENVELOPE_STD_FLOOR:
        return 0.0
    return float(np.clip(np.mean((ea / da) * (eb / db)), -1.0, 1.0))


def load_mono(path: Path) -> np.ndarray:
    y, _ = librosa.load(str(path), sr=TARGET_SR, mono=True)
    return y


def optional_spectrograms(
    mix: np.ndarray,
    guitar: np.ndarray,
    out_dir: Path,
    *,
    sr: int = TARGET_SR,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, audio in ("mix", mix), ("guitar", guitar):
        plt.figure(figsize=(SPEC_FIG_WIDTH_IN, SPEC_FIG_HEIGHT_IN))
        S = np.abs(
            librosa.stft(
                audio.astype(np.float64),
                n_fft=SPEC_N_FFT,
                hop_length=SPEC_HOP_LENGTH,
            )
        )
        S_db = librosa.amplitude_to_db(S, ref=np.max)
        librosa.display.specshow(
            S_db, sr=sr, hop_length=SPEC_HOP_LENGTH, x_axis="time", y_axis="hz"
        )
        plt.colorbar(format="%+2.0f dB")
        plt.title(name)
        plt.tight_layout()
        plt.savefig(out_dir / f"{name}.png", dpi=SPEC_PNG_DPI)
        plt.close()


def _pick_stem(track_dir: Path, stem: str) -> Path | None:
    p = track_dir / f"{stem}.wav"
    return p if p.is_file() else None


def evaluate_track(
    input_audio: Path,
    work_root: Path,
    *,
    spectrograms_dir: Path | None,
) -> tuple[bool, list[str]]:
    slug = input_audio.stem.replace(" ", "_")[:SLUG_MAX_CHARS]
    song_work = work_root / slug
    song_work.mkdir(parents=True, exist_ok=True)
    normalized = song_work / "normalized.wav"
    demucs_out = song_work / "demucs_out"

    lines: list[str] = []

    lines.append(f"[{slug}] normalize → {normalized.name}")
    ffmpeg_normalize_wav(input_audio, normalized)

    lines.append(f"[{slug}] demucs → {demucs_out}")
    track_dir = run_demucs_htdemucs_6s(normalized, demucs_out)

    guitar_p = track_dir / "guitar.wav"
    if not guitar_p.is_file():
        lines.append(f"[{slug}] FAIL: missing guitar.wav under {track_dir}")
        return True, lines

    mix = load_mono(normalized)
    guitar = load_mono(guitar_p)

    r_g = _rms(guitar)
    r_m = _rms(mix)
    ratio = (r_g / r_m) if r_m > RMS_MIX_FLOOR else 0.0
    snr_db = snr_proxy_db(guitar, mix)

    lines.append(
        f"[{slug}] rms_guitar={r_g:.5f} rms_mix={r_m:.5f} ratio={ratio:.4f} snr_proxy_db={snr_db:.2f}"
    )

    reasons: list[str] = []

    if r_g < MIN_RMS_GUITAR:
        reasons.append(
            f"guitar RMS {r_g:.5f} < {MIN_RMS_GUITAR} (near silence / no guitar)"
        )
    if ratio < MIN_RATIO_GUITAR_TO_MIX:
        reasons.append(
            f"guitar/mix RMS ratio {ratio:.4f} < {MIN_RATIO_GUITAR_TO_MIX} (no guitar or buried)"
        )
    if snr_db < MIN_SNR_PROXY_DB:
        reasons.append(
            f"SNR proxy {snr_db:.2f} dB < {MIN_SNR_PROXY_DB} dB (guitar explains little of mix in this coarse sense — see script docstring)"
        )

    vocals_p = _pick_stem(track_dir, "vocals")
    if vocals_p is not None:
        vocals = load_mono(vocals_p)
        corr = abs(envelope_pearson(guitar, vocals))
        lines.append(f"[{slug}] |corr(env guitar, env vocals)|={corr:.4f}")
        if corr > MAX_VOCALS_ENVELOPE_CORR:
            reasons.append(
                f"vocal envelope correlation {corr:.4f} > {MAX_VOCALS_ENVELOPE_CORR} "
                f"(likely bleed — if guitar stem sounds clean to you, treat as false positive; confirm by ear, see checklist)"
            )

    if spectrograms_dir is not None:
        spec_out = spectrograms_dir / slug
        lines.append(f"[{slug}] spectrograms → {spec_out}")
        optional_spectrograms(mix, guitar, spec_out, sr=TARGET_SR)

    failed = bool(reasons)
    if failed:
        for r in reasons:
            lines.append(f"[{slug}] FAIL: {r}")
    else:
        lines.append(f"[{slug}] PASS")

    return failed, lines


def main() -> int:
    epilog = """
Dependencies:
  Install backend per backend/README.md (Python venv with librosa, demucs, numpy).
  ffmpeg must be on PATH. Optional PNGs need: pip install matplotlib
"""
    parser = argparse.ArgumentParser(
        description="Smoke-test htdemucs_6s guitar stems.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="One or more mixed audio files (formats supported by ffmpeg + librosa).",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=_BACKEND_ROOT / "data" / "smoke_stems",
        help="Working directory for normalized wav and Demucs output (default: backend/data/smoke_stems).",
    )
    parser.add_argument(
        "--spectrograms",
        action="store_true",
        help="Write mix/guitar PNGs under artifacts/stem_smoke/<slug>/ (requires matplotlib).",
    )
    args = parser.parse_args()

    if len(args.inputs) < 2:
        print(
            "smoke_stems: warning: this gate is intended for ≥2 mixes (one easy, one dense per "
            "docs/STEM_QUALITY_CHECKLIST.md); single-file runs are for quick debug only.",
            file=sys.stderr,
        )

    spectrograms_dir: Path | None = None
    if args.spectrograms:
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            print(
                "smoke_stems: --spectrograms requires matplotlib (`pip install matplotlib`).",
                file=sys.stderr,
            )
            return 2
        repo_root = _BACKEND_ROOT.parent
        spectrograms_dir = repo_root / "artifacts" / "stem_smoke"

    args.work_dir.mkdir(parents=True, exist_ok=True)

    any_failed = False
    for inp in args.inputs:
        inp = inp.expanduser().resolve()
        if not inp.is_file():
            print(f"smoke_stems: not a file: {inp}", file=sys.stderr)
            any_failed = True
            continue
        try:
            failed, lines = evaluate_track(inp, args.work_dir, spectrograms_dir=spectrograms_dir)
        except Exception as e:
            failed = True
            lines = [f"[{inp.name}] FAIL ({type(e).__name__}): {e}"]
        any_failed = any_failed or failed
        for line in lines:
            print(line)

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
