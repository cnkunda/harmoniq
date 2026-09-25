"""
Notebook / feasibility pipeline: normalize audio → Demucs htdemucs_6s → Librosa
summary → Basic Pitch note events → Guitar Pro 5.

This module backs `research/pipeline_proof.ipynb` and future API steps. Heavy steps
(Demucs, Basic Pitch) are subprocess / optional imports; see backend README for
platform notes (Basic Pitch + TensorFlow on Windows/Linux Python 3.11+).
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
import wave
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

logger = logging.getLogger("harmoniq.pipeline_proof")

# --- Constants aligned with README / PRIORITIES --------------------------------

DEMUCS_MODEL = os.getenv("HARMONIQ_DEMUCS_MODEL", "htdemucs_6s")
TARGET_SR = 44100

# Demucs stem separation optimization (Commit 111a)
# Segment size and overlap to prevent OOM on long tracks, matching Hybrid Demucs tutorial
DEMUCS_SEGMENT_SIZE = 7  # seconds (htdemucs_6s max is 7.8s)
DEMUCS_OVERLAP = 0.1  # fraction of segment (0.1 = 1 second overlap per side)

# Long-running CLIs may print a lot of stderr; only the tail is attached to failures.
_SUBPROCESS_FAIL_SNIP = 8000


class YouTubeDownloadError(RuntimeError):
    """Raised when yt-dlp download fails or times out."""


def _run_subprocess_checked(cmd: list[str], *, what: str, timeout: int | None = None) -> None:
    """Run a command; on failure raise RuntimeError with stderr/stdout (truncated), not a bare exit code."""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode == 0:
        return
    out = ((p.stderr or "").strip() + "\n" + (p.stdout or "").strip()).strip()
    if len(out) > _SUBPROCESS_FAIL_SNIP:
        out = "…\n" + out[-_SUBPROCESS_FAIL_SNIP :]
    if not out:
        out = f"(no stderr/stdout, exit {p.returncode})"
    raise RuntimeError(f"{what} failed (exit {p.returncode}): {out}") from None


# Krumhansl–Schmuckler major / minor key profiles (C rotated in estimator)
_KS_MAJOR = [
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
]
_KS_MINOR = [
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
]
_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def ffmpeg_normalize_command(
    input_path: Path,
    output_path: Path,
    *,
    sample_rate: int = TARGET_SR,
    mono: bool = True,
) -> list[str]:
    """Argv for `ffmpeg` to normalize to ``sample_rate`` Hz and channel layout with EBU R128 loudness normalization.

    Applies loudnorm targeting -16 LUFS integrated (EBU R128 standard) while
    preserving existing resampling (44.1kHz) and downmix (mono) behavior.
    """
    ac = "1" if mono else "2"
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        str(sample_rate),
        "-ac",
        ac,
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        str(output_path),
    ]


def ffmpeg_normalize_wav(
    input_path: Path,
    output_path: Path,
    *,
    sample_rate: int = TARGET_SR,
    mono: bool = True,
) -> None:
    """Resample, downmix, and apply EBU R128 loudness normalization (-16 LUFS) via ffmpeg.

    Produces 44.1 kHz mono WAV with loudnorm filter applied, per Harmoniq README and Commit 115.
    """
    cmd = ffmpeg_normalize_command(input_path, output_path, sample_rate=sample_rate, mono=mono)
    _run_subprocess_checked(cmd, what="ffmpeg")


def concatenate_wavs(
    input_paths: Sequence[Path],
    output_path: Path,
    *,
    channels: int = 1,
    sample_width: int = 2,
    sample_rate: int = TARGET_SR,
) -> Path:
    """Concatenate multiple PCM WAV files into a single file.

    All inputs must share the same format (sample rate, channels, sample width).
    Uses stdlib ``wave`` module for consistency with ``_chunk_wav_for_long_track``.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with wave.open(str(output_path), "wb") as dst:
            dst.setnchannels(channels)
            dst.setsampwidth(sample_width)
            dst.setframerate(sample_rate)
            for inp in input_paths:
                with wave.open(str(inp), "rb") as src:
                    dst.writeframes(src.readframes(src.getnframes()))
        return output_path
    except (wave.Error, OSError) as exc:
        raise RuntimeError(f"WAV concatenation failed: {exc}") from exc


def _resolve_demucs_device() -> str:
    """Pick the torch device for the Demucs subprocess.

    Default is ``cpu`` because the WSL2 dev box's GTX 1050 (4GB) cannot
    reliably hold htdemucs_6s + the Keras chord model + basic-pitch at
    once, and torch's CUDA context can survive across subprocesses and
    fail mid-load with ``No CUDA GPUs are available``. Set
    ``HARMONIQ_DEMUCS_DEVICE=cuda`` to opt in on hardware with a real
    GPU (>=8GB VRAM recommended).
    """
    override = os.getenv("HARMONIQ_DEMUCS_DEVICE", "").strip().lower()
    if override in ("cpu", "cuda", "mps"):
        return override
    return "cpu"


def demucs_separate_command(
    input_wav: Path,
    out_dir: Path,
    *,
    model: str = DEMUCS_MODEL,
    python_executable: str | None = None,
) -> list[str]:
    """Argv to run Demucs with the ``htdemucs_6s`` six-stem checkpoint.

    Includes optimization flags (Commit 111a):
    - --segment: process in chunks to prevent OOM on long tracks
    - --overlap: overlap ratio for smooth boundaries
    - --device: explicit CUDA/CPU selection (default CPU; see _resolve_demucs_device)
    """
    py = python_executable or sys.executable
    device = _resolve_demucs_device()

    return [
        py,
        "-m",
        "demucs",
        "-n",
        model,
        "--segment",
        str(DEMUCS_SEGMENT_SIZE),
        "--overlap",
        str(DEMUCS_OVERLAP),
        "--device",
        device,
        "--out",
        str(out_dir),
        str(input_wav),
    ]


def normalize_audio_for_demucs(input_wav: Path, output_wav: Path) -> tuple[float, float]:
    """Normalize audio (mean/std) before Demucs separation for improved quality.
    
    Optimization (Commit 111a): Following the Hybrid Demucs tutorial, normalize the waveform
    by subtracting its mean and dividing by its standard deviation. This centers the audio
    around zero and scales it to unit variance, which can improve the model's input quality.
    
    Args:
        input_wav: Path to input WAV file (44.1 kHz mono from ingest)
        output_wav: Path where normalized WAV will be written
        
    Returns:
        Tuple of (mean, std) for denormalization after Demucs separation
    """
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        raise RuntimeError(f"normalize_audio_for_demucs requires numpy and soundfile: {e}")
    
    # Load audio
    waveform, sr = sf.read(str(input_wav))
    
    # Ensure mono
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    
    # Compute mean and std
    mean = float(np.mean(waveform))
    std = float(np.std(waveform))
    
    # Avoid division by zero
    if std < 1e-8:
        std = 1.0
    
    # Normalize: (waveform - mean) / std
    normalized = (waveform - mean) / std
    
    # Write normalized WAV
    sf.write(str(output_wav), normalized, sr)
    
    return mean, std


def denormalize_stems(
    stems_dir: Path,
    mean: float,
    std: float,
    stem_keys: Sequence[str] = ("guitar", "bass", "drums", "vocals", "piano", "other"),
) -> None:
    """Denormalize stems after Demucs separation to restore original scale.
    
    Optimization (Commit 111a): After Demucs has processed the normalized audio,
    denormalize the output stems by reversing the normalization:
    stems * std + mean
    
    Args:
        stems_dir: Directory containing the separated stems
        mean: Mean value used for normalization
        std: Std value used for normalization
        stem_keys: Names of stem files to denormalize
    """
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        raise RuntimeError(f"denormalize_stems requires numpy and soundfile: {e}")
    
    for stem_key in stem_keys:
        stem_path = stems_dir / f"{stem_key}.wav"
        if not stem_path.exists():
            continue
        
        # Load stem
        waveform, sr = sf.read(str(stem_path))
        
        # Denormalize: stems * std + mean
        denormalized = waveform * std + mean

        # Clip to float32 WAV range to avoid encoding artifacts
        clipped = np.clip(denormalized, -1.0, 1.0).astype(np.float32)
        clipped_count = int(np.sum(np.abs(denormalized) > 1.0))
        if clipped_count > 0:
            logger.warning(
                "Clipped %d samples in %s (max=%.4f)",
                clipped_count, stem_key, float(np.max(np.abs(denormalized))),
            )

        # Write back
        sf.write(str(stem_path), clipped, sr)


def run_demucs_htdemucs_6s(
    input_wav: Path,
    out_dir: Path,
    *,
    model: str = DEMUCS_MODEL,
    python_executable: str | None = None,
) -> Path:
    """
    Run Demucs; return the directory that contains ``guitar.wav`` (track folder).

    Layout: ``out_dir / model_name / <stem_name> / *.wav`` (Demucs 4.x).
    """
    cmd = demucs_separate_command(
        input_wav, out_dir, model=model, python_executable=python_executable
    )
    _run_subprocess_checked(cmd, what="demucs", timeout=7200)
    # Typical: out_dir/htdemucs_6s/<track>/guitar.wav
    stems_root = out_dir / model
    if not stems_root.is_dir():
        raise FileNotFoundError(f"Expected Demucs output folder missing: {stems_root}")
    guitar = find_guitar_stem(stems_root)
    return guitar.parent


def find_guitar_stem(separated_model_root: Path) -> Path:
    """Return ``guitar.wav`` under a Demucs ``htdemucs_6s`` output tree."""
    matches = list(separated_model_root.glob("**/guitar.wav"))
    if not matches:
        raise FileNotFoundError(
            f"No guitar.wav under {separated_model_root} — check Demucs model and input."
        )
    if len(matches) > 1:
        matches.sort(key=lambda p: len(p.parts))
    return matches[0]


def yt_dlp_download_audio_command(
    url: str,
    output_template: Path,
    *,
    audio_format: str = "wav",
) -> list[str]:
    """
    argv to fetch best audio as WAV. Template should end in ``.%(ext)s``; when
    using ``audio_format wav``, ext is ``wav``.
    """
    # README: yt-dlp --extract-audio --audio-format wav --audio-quality 0
    return [
        "yt-dlp",
        "--no-playlist",
        "--extract-audio",
        "--audio-format",
        audio_format,
        "--audio-quality",
        "0",
        "-o",
        str(output_template),
        url,
    ]


def yt_dlp_download_wav(url: str, work_dir: Path) -> Path:
    """
    Download audio to ``work_dir``; return path to the produced ``.wav``.
    Caller should run :func:`ffmpeg_normalize_wav` for strict 44.1 kHz mono.

    Raises:
        YouTubeDownloadError: If the subprocess times out after 10 minutes.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    template = work_dir / "yt_%(id)s.%(ext)s"
    cmd = yt_dlp_download_audio_command(url, template)
    try:
        subprocess.run(cmd, check=True, timeout=600, cwd=str(work_dir))
    except subprocess.TimeoutExpired:
        raise YouTubeDownloadError(
            "Download timed out after 10 minutes. Try a shorter clip or a different source."
        )
    wavs = sorted(work_dir.glob("yt_*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not wavs:
        raise FileNotFoundError(f"yt-dlp did not produce a wav in {work_dir}")
    return wavs[0]


# --- Librosa analysis -----------------------------------------------------------


@dataclass
class LibrosaSummary:
    duration_s: float
    tempo_bpm: float
    beat_times_s: list[float]
    key_name: str
    mode: str  # "major" | "minor"
    segments: list[dict[str, Any]]
    bar_timestamps_s: list[float]
    key_confidence: float
    tempo_confidence: float
    # Commit 117: raw curves for section refinement (numpy arrays, optional for
    # backward compatibility with callers that construct LibrosaSummary manually).
    onset_novelty: Any = None
    rms_curve: Any = None
    times: Any = None
    # Commit 118: chroma CQT for repeat detection (12, n_frames)
    chroma: Any = None
    # Commit 119: spectral centroid curve for section classification
    spectral_centroid: Any = None


# ---- Section Features & Classifier (Commit 119) -----------------------------


@dataclass
class SectionFeatures:
    """Per-section audio features for semantic label classification."""
    mean_energy: float = 0.0
    energy_variance: float = 0.0
    spectral_centroid_mean: float | None = None
    chord_density: float = 0.0
    harmonic_stability: float | None = None
    energy_trend: float = 0.0
    relative_duration: float = 0.0
    position: str = "middle"
    duration: float = 0.0
    is_repeated: bool = False


_INTRO_MAX_DURATION: float = 15.0
_INTRO_ENERGY_THRESHOLD: float = 0.35
_CHORUS_ENERGY_THRESHOLD: float = 0.6
_SOLO_CENTROID_THRESHOLD: float = 0.7
_SOLO_MAX_CHORD_DENSITY: float = 1.5
_BRIDGE_HARMONIC_SHIFT_THRESHOLD: float = 0.15
_PRECHORUS_MAX_DURATION: float = 10.0
_PRECHORUS_ENERGY_RISE_THRESHOLD: float = 0.1


def classify_section(features: SectionFeatures) -> tuple[str, float]:
    """Rule-based section label classifier using per-section audio features.

    Returns (label, confidence) where confidence is 0-1.
    Rules follow PRIORITIES.md Commit 119 pseudocode with pre-chorus additions.
    """
    if features.position in ("first", "only") and features.duration < _INTRO_MAX_DURATION and features.mean_energy < _INTRO_ENERGY_THRESHOLD:
        return ("Intro", 0.85)

    if features.position == "last" and features.energy_trend < 0:
        return ("Outro", 0.80)

    if features.is_repeated and features.mean_energy > _CHORUS_ENERGY_THRESHOLD:
        return ("Chorus", 0.75)

    if (
        not features.is_repeated
        and features.harmonic_stability is not None
        and features.harmonic_stability < _BRIDGE_HARMONIC_SHIFT_THRESHOLD
    ):
        return ("Bridge", 0.70)

    if (
        features.spectral_centroid_mean is not None
        and features.spectral_centroid_mean > _SOLO_CENTROID_THRESHOLD
        and features.chord_density < _SOLO_MAX_CHORD_DENSITY
    ):
        return ("Solo", 0.70)

    return ("Verse", 0.50)


def compute_section_features(
    segments: list[dict[str, Any]],
    song_duration: float,
    rms_curve: np.ndarray,
    times: np.ndarray,
    spectral_centroid_curve: np.ndarray | None,
    chroma: np.ndarray | None,
    chord_events: list[tuple[float, str]],
) -> list[dict[str, Any]]:
    """Compute per-section audio features and classify each segment.

    Enriches each segment dict with ``features`` (SectionFeatures) and
    updates ``label`` / ``label_confidence`` via :func:`classify_section`.
    """
    if not segments:
        return segments

    for i, seg in enumerate(segments):
        start_t = seg.get("start_s", seg.get("start", 0.0))
        end_t = seg.get("end_s", seg.get("end", song_duration))
        duration = end_t - start_t

        if duration <= 0:
            seg["label"] = "Section"
            seg["label_confidence"] = 0.0
            continue

        rms_mask = (times >= start_t) & (times < end_t)
        section_rms = rms_curve[rms_mask] if rms_mask.any() else np.array([0.0])
        mean_energy = float(section_rms.mean())
        energy_variance = float(section_rms.var()) if len(section_rms) > 1 else 0.0

        energy_trend = 0.0
        if rms_mask.sum() >= 4:
            energy_trend = float(np.polyfit(times[rms_mask], section_rms, 1)[0])

        sc_mean: float | None = None
        if spectral_centroid_curve is not None and rms_mask.any():
            sc_values = spectral_centroid_curve[rms_mask]
            if len(sc_values) > 0:
                sc_mean = float(sc_values.mean())

        harmonic_stability: float | None = None
        if chroma is not None:
            c_mask = (times >= start_t) & (times < end_t)
            if c_mask.any():
                section_chroma = chroma[:, c_mask]
                if section_chroma.shape[1] >= 2:
                    per_pitch_var = float(np.var(section_chroma, axis=1).mean())
                    harmonic_stability = max(0.0, 1.0 - min(1.0, per_pitch_var * 5.0))
                else:
                    harmonic_stability = 0.5

        section_chords = [c for t, c in chord_events if start_t <= t < end_t]
        if len(section_chords) >= 2 and duration > 0:
            changes = sum(1 for j in range(1, len(section_chords)) if section_chords[j] != section_chords[j - 1])
            chord_density = changes / duration
        else:
            chord_density = 0.0

        if len(segments) == 1:
            position = "only"
        elif i == 0:
            position = "first"
        elif i == len(segments) - 1:
            position = "last"
        else:
            position = "middle"

        is_repeated = seg.get("is_repeated", False)

        features = SectionFeatures(
            mean_energy=mean_energy,
            energy_variance=energy_variance,
            spectral_centroid_mean=sc_mean,
            chord_density=chord_density,
            harmonic_stability=harmonic_stability,
            energy_trend=energy_trend,
            relative_duration=duration / song_duration if song_duration > 0 else 0.0,
            position=position,
            duration=duration,
            is_repeated=is_repeated,
        )
        seg["features"] = features

    _detect_pre_chorus(segments)

    for seg in segments:
        features: SectionFeatures = seg.get("features")
        if features is None:
            seg["label"] = "Verse"
            seg["label_confidence"] = 0.5
            continue
        label, confidence = classify_section(features)
        seg["label"] = label
        seg["label_confidence"] = confidence

    return segments


def _detect_pre_chorus(segments: list[dict[str, Any]]) -> None:
    """Two-pass pre-chorus detection between Verse and Chorus."""
    for i in range(1, len(segments) - 1):
        prev = segments[i - 1]
        curr = segments[i]
        nxt = segments[i + 1]
        f: SectionFeatures | None = curr.get("features")
        if f is None:
            continue
        prev_label = prev.get("label", "")
        next_label = nxt.get("label", "")
        if (
            f.duration < _PRECHORUS_MAX_DURATION
            and f.energy_trend > _PRECHORUS_ENERGY_RISE_THRESHOLD
            and prev_label == "Verse"
            and next_label in ("Chorus", "Solo")
        ):
            curr["label"] = "Pre-Chorus"
            curr["label_confidence"] = 0.70


def estimate_key_literal(chroma_mean: Sequence[float]) -> tuple[str, str]:
    """Return (key_name e.g. 'G', mode 'major'|'minor') using KS correlation."""
    chroma = list(chroma_mean)
    if len(chroma) != 12:
        raise ValueError("chroma_mean must have length 12")

    best_corr = -math.inf
    best: tuple[int, str] = (0, "major")

    for mode, profile in [("major", _KS_MAJOR), ("minor", _KS_MINOR)]:
        for shift in range(12):
            rotated = profile[shift:] + profile[:shift]
            c = sum(a * b for a, b in zip(chroma, rotated))
            if c > best_corr:
                best_corr = c
                best = (shift, mode)

    root = _PITCH_NAMES[best[0]]
    return root, best[1]


def librosa_summarize(audio_path: Path) -> LibrosaSummary:
    """
    Extract lightweight structure features from an audio file.

    Outputs are intended to be:
    - simple and robust (smoke-test level)
    - consistent with schema wiring for the frontend (bar timestamps + section labels)
    """
    import librosa

    y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    duration = float(len(y) / sr)

    # librosa's feature pipelines (chroma_cqt, onset + RMS) can be fragile on very
    # short clips. For API smoke-tests we fall back to deterministic placeholders.
    if duration < 1.0:
        return LibrosaSummary(
            duration_s=duration,
            tempo_bpm=60.0,
            beat_times_s=[0.0],
            key_name="C major",
            mode="major",
            segments=[{"label": "Intro", "start_s": 0.0, "end_s": duration}],
            bar_timestamps_s=[0.0],
            key_confidence=0.1,
            tempo_confidence=0.1,
        )

    hop_length = 512

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    tempo_estimates = librosa.feature.tempo(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
    tempo_bpm = float(tempo_estimates[0])
    _, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=hop_length)

    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
    beat_list = [float(t) for t in beat_times if t >= 0.0]
    beat_list.sort()

    # librosa feature extraction assumes enough signal length. If chroma fails, we still
    # return tempo/beat info.
    chroma = None
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
        chroma_mean = chroma.mean(axis=1)
        root, mode = estimate_key_literal(chroma_mean)
        key_name = f"{root} {mode}"
    except Exception:
        mode = "major"
        key_name = "C major"

    # --- Simple onset + energy segmentation into rough sections ---------------
    rms_frames = librosa.feature.rms(y=y, hop_length=hop_length)[0]

    # Commit 119: compute spectral centroid curve for Solo/instrumental detection
    spectral_centroid_curve: np.ndarray | None = None
    try:
        spectral_centroid_curve = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
    except Exception:
        pass

    def _norm(a: np.ndarray) -> np.ndarray:
        a = a.astype(float)
        mn = float(a.min(initial=0.0))
        mx = float(a.max(initial=0.0))
        return (a - mn) / (mx - mn + 1e-9)

    onset_n = _norm(onset_env)
    energy_n = _norm(rms_frames)
    novelty = 0.65 * onset_n + 0.35 * energy_n

    if duration < 6.0:
        n_segments = 2
    elif duration < 15.0:
        n_segments = 3
    else:
        n_segments = 4

    n_boundaries = n_segments - 1
    n_frames = int(len(novelty))
    edge_margin = max(1, int(0.05 * n_frames))
    valid = np.arange(edge_margin, max(edge_margin + 1, n_frames - edge_margin))

    boundary_times: list[float] = []
    if n_boundaries > 0 and len(valid) >= n_boundaries:
        k = n_boundaries
        top_rel_idx = np.argpartition(novelty[valid], -k)[-k:]
        top_frames = valid[top_rel_idx]
        top_times = librosa.frames_to_time(top_frames, sr=sr, hop_length=hop_length)
        top_times = [float(t) for t in top_times if 0.0 < t < duration]
        top_times.sort()

        # Deduplicate boundaries that are too close together.
        min_gap_s = max(0.5, duration / 20.0)
        for t in top_times:
            if boundary_times and t - boundary_times[-1] < min_gap_s:
                continue
            boundary_times.append(t)
            if len(boundary_times) >= n_boundaries:
                break

    boundaries = [0.0] + boundary_times[:n_boundaries] + [duration]
    segments: list[dict[str, Any]] = []
    for i in range(len(boundaries) - 1):
        start_s = float(boundaries[i])
        end_s = float(boundaries[i + 1])
        if end_s - start_s < 0.2:
            continue
        segments.append(
            {
                "start_s": start_s,
                "end_s": end_s,
            }
        )

    if not segments:
        segments = [{"start_s": 0.0, "end_s": duration}]

    # Commit 117: compute frame times for raw curves (used by section refinement)
    frame_times = librosa.frames_to_time(
        np.arange(len(onset_env)), sr=sr, hop_length=hop_length
    )

    # Commit 119: classify segments using audio features (replaces cyclic labels)
    chord_events: list[tuple[float, str]] = []
    segments = compute_section_features(
        segments=segments,
        song_duration=duration,
        rms_curve=rms_frames,
        times=frame_times,
        spectral_centroid_curve=spectral_centroid_curve,
        chroma=chroma,
        chord_events=chord_events,
    )

    # --- Bar timestamps (assume 4/4; derive from beat grid) -----------------------
    # beat_grid in schema is "quarter-note" timestamps; bar_timestamps are every 4 beats.
    beats_per_bar = 4
    bar_from_beats = [beat_list[i] for i in range(0, len(beat_list), beats_per_bar)]
    bar_from_beats = [float(t) for t in bar_from_beats if t >= 0.0]
    bar_from_beats.sort()

    # Ensure monotonic and include a bar at/near t=0.
    bar_timestamps_s: list[float] = []
    for t in bar_from_beats:
        if not bar_timestamps_s or t - bar_timestamps_s[-1] > 1e-3:
            bar_timestamps_s.append(float(t))
    if not bar_timestamps_s or bar_timestamps_s[0] > 0.05:
        bar_timestamps_s.insert(0, 0.0)
    else:
        bar_timestamps_s[0] = 0.0

    seconds_per_bar = None
    if tempo_bpm > 0.0:
        seconds_per_bar = (60.0 / tempo_bpm) * beats_per_bar

    if seconds_per_bar and seconds_per_bar > 0.0:
        # Extend to cover (roughly) the whole duration.
        while bar_timestamps_s[-1] + seconds_per_bar <= duration + seconds_per_bar * 0.25:
            bar_timestamps_s.append(bar_timestamps_s[-1] + seconds_per_bar)

    # Placeholder confidence values (heuristic thresholds for basic sanity).
    tempo_confidence = 0.9 if 40.0 <= tempo_bpm <= 200.0 else 0.6
    key_confidence = 0.85

    return LibrosaSummary(
        duration_s=duration,
        tempo_bpm=tempo_bpm,
        beat_times_s=beat_list,
        key_name=key_name,
        mode=mode,
        segments=segments,
        bar_timestamps_s=bar_timestamps_s,
        key_confidence=key_confidence,
        tempo_confidence=tempo_confidence,
        onset_novelty=novelty,
        rms_curve=rms_frames,
        times=frame_times,
        chroma=chroma,
        spectral_centroid=spectral_centroid_curve,
    )


# --- Basic Pitch ----------------------------------------------------------------

@dataclass
class NoteEvent:
    start_s: float
    end_s: float
    pitch_midi: int
    amplitude: float = 0.0


_BASIC_PITCH_CACHE: dict[str, list[NoteEvent]] = {}


def basic_pitch_predict_events(
    audio_path: Path,
    *,
    model_path: Path | None = None,
    midi_tempo: float | None = None,
) -> list[NoteEvent]:
    """
    Run Spotify Basic Pitch on an audio file; return typed note events.

    Results are cached by audio path so repeated calls (e.g. solo inference
    + tab generation) reuse the same model output.

    Requires ``pip install -e ".[basicpitch]"`` (see ``pyproject.toml``). On some
    platforms Python/TensorFlow wheels are not available — the notebook documents this.
    """
    cache_key = f"{audio_path}::{midi_tempo}::{model_path}"
    cached = _BASIC_PITCH_CACHE.get(cache_key)
    if cached is not None:
        logger.info("Reusing cached Basic Pitch result for %s", audio_path)
        return cached

    try:
        from basic_pitch.inference import predict as basic_pitch_predict
    except ImportError as e:
        raise ImportError(
            "basic-pitch is not installed. On macOS try: pip install -e \".[basicpitch]\" "
            "from the backend directory. On Windows/Linux with Python 3.11+, Basic Pitch "
            "may need a conda env or separate Python — see backend README."
        ) from e

    kwargs: dict[str, Any] = {}
    if midi_tempo is not None:
        kwargs["midi_tempo"] = float(midi_tempo)
    if model_path is not None:
        kwargs["model_or_model_path"] = str(model_path)
    try:
        _, _, raw_events = basic_pitch_predict(str(audio_path), **kwargs)
    except Exception as default_err:
        import basic_pitch as basic_pitch_pkg

        tflite_path = Path(basic_pitch_pkg.__file__).resolve().parent / "saved_models" / "icassp_2022" / "nmp.tflite"
        if not tflite_path.exists():
            raise
        kwargs.pop("model_or_model_path", None)
        _, _, raw_events = basic_pitch_predict(str(audio_path), model_or_model_path=tflite_path, **kwargs)
    out: list[NoteEvent] = []
    for row in raw_events:
        # (start_s, end_s, pitch_midi, amplitude, pitch_bends?)
        start_s = float(row[0])
        end_s = float(row[1])
        pitch = int(round(float(row[2])))
        amp = float(row[3])
        out.append(NoteEvent(start_s=start_s, end_s=end_s, pitch_midi=pitch, amplitude=amp))
    _BASIC_PITCH_CACHE[cache_key] = out
    return out


# --- MIDI-like → Guitar Pro 5 ---------------------------------------------------


def beat_slot_index_for_time(
    start_s: float,
    beat_times: Sequence[float] | None,
    *,
    bpm: float,
) -> int:
    """
    Map wall-clock seconds to a monotonically increasing beat slot index.

    When ``beat_times`` has at least two finite samples (e.g. librosa beat grid),
    assign each note to the beat interval ``[t[i], t[i+1])`` containing ``start_s``,
    and extrapolate linearly past the last beat using the final inter-beat spacing.
    Otherwise fall back to uniform quarter spacing from ``bpm``.
    """
    s = float(start_s)
    if not math.isfinite(s) or s < 0:
        return 0
    if beat_times is None:
        beat_times = []
    t_sorted = sorted(float(x) for x in beat_times if math.isfinite(float(x)))
    if len(t_sorted) < 2:
        spq = 60.0 / max(bpm, 1.0)
        return max(0, int(s / spq))
    if s <= t_sorted[0]:
        return 0
    for i in range(len(t_sorted) - 1):
        if t_sorted[i] <= s < t_sorted[i + 1]:
            return i
    span = max(t_sorted[-1] - t_sorted[-2], 1e-3)
    extra = max(0, int((s - t_sorted[-1]) / span))
    return len(t_sorted) - 1 + extra


def _best_tab_slot(midi_pitch: int, track_strings: Sequence[Any]) -> tuple[int, int] | None:
    """
    Pick (string_number 1..6, fret) for ``midi_pitch`` given ``track.strings``.
    Prefers lower fret, then thinner string (smaller string number).
    """
    candidates: list[tuple[int, int, int]] = []
    for idx, gs in enumerate(track_strings):
        s_num = idx + 1
        fret = midi_pitch - int(gs.value)
        if 0 <= fret <= 24:
            candidates.append((fret, s_num, idx))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[2]))
    fret, s_num, _ = candidates[0]
    return s_num, fret


def build_gp5_from_note_events(
    events: Sequence[NoteEvent],
    bpm: float,
    output_gp5: Path,
    *,
    title: str = "Harmoniq proof",
    artist: str = "",
    beat_times_s: Sequence[float] | None = None,
) -> None:
    """
    Map note events onto quarter-note slots and write a monophonic/tab GP5.
    Rests fill empty quarter slots in each 4/4 bar.

    When ``beat_times_s`` is provided (e.g. librosa ``beat_grid``), each note is
    quantized to the detected beat interval instead of a uniform ``60/bpm`` grid.
    Multiple notes in the same slot: keep the one with highest ``amplitude``, then
    highest MIDI as tie-breaker.

    This is intentionally simple (proof-of-concept); a production pipeline would carry
    durations from Basic Pitch and respect tuplets / pickup bars.
    """
    import guitarpro as gp

    by_slot: dict[int, list[NoteEvent]] = defaultdict(list)
    for ev in events:
        b_idx = beat_slot_index_for_time(float(ev.start_s), beat_times_s, bpm=bpm)
        by_slot[b_idx].append(ev)
    # One pitch per beat slot: prefer strongest amplitude (Basic Pitch polyphony).
    by_beat: dict[int, list[int]] = {}
    for k, evs in by_slot.items():
        if not evs:
            continue
        best = max(
            evs,
            key=lambda e: (float(e.amplitude), int(e.pitch_midi)),
        )
        by_beat[k] = [int(best.pitch_midi)]

    max_beat = max(by_beat, default=-1)
    n_measures = max_beat // 4 + 1 if max_beat >= 0 else 1

    song = gp.Song(
        title=title,
        artist=artist,
        tempo=int(round(bpm)),
        tempoName="Moderate",
    )
    track = song.tracks[0]
    track.name = "Guitar"

    # Reset factory measure: rebuild headers and measures for n_measures
    song.measureHeaders.clear()
    track.measures.clear()
    for _ in range(n_measures):
        header = gp.MeasureHeader()
        song.measureHeaders.append(header)
        measure = gp.Measure(track, header)
        track.measures.append(measure)

    for mi in range(n_measures):
        measure = track.measures[mi]
        voice = measure.voices[0]
        for slot in range(4):
            b = mi * 4 + slot
            if b in by_beat and by_beat[b]:
                beat = gp.Beat(
                    voice=voice,
                    duration=gp.Duration(gp.Duration.quarter),
                    status=gp.BeatStatus.normal,
                )
                for midi_pitch in by_beat[b]:
                    tab = _best_tab_slot(midi_pitch, track.strings)
                    if tab is None:
                        continue
                    s_num, fret = tab
                    note = gp.Note(
                        beat=beat,
                        string=s_num,
                        value=fret,
                        type=gp.NoteType.normal,
                    )
                    beat.notes.append(note)
                if beat.notes:
                    voice.beats.append(beat)
                else:
                    rest_beat = gp.Beat(
                        voice=voice,
                        duration=gp.Duration(gp.Duration.quarter),
                        status=gp.BeatStatus.rest,
                    )
                    voice.beats.append(rest_beat)
            else:
                rest_beat = gp.Beat(
                    voice=voice,
                    duration=gp.Duration(gp.Duration.quarter),
                    status=gp.BeatStatus.rest,
                )
                voice.beats.append(rest_beat)

    output_gp5.parent.mkdir(parents=True, exist_ok=True)
    gp.write(song, str(output_gp5))


def cli_equivalents_doc() -> str:
    """Exact command shapes for README / CI (no shell-specific quotes)."""
    lines = [
        "=== Harmoniq notebook pipeline — CLI equivalents ===",
        "",
        "# 1) Normalize to 44.1 kHz mono",
        " ".join(ffmpeg_normalize_command(Path('input.mp3'), Path('song.wav'))),
        "",
        "# 2) Optional: YouTube → wav (then normalize as above)",
        " ".join(
            yt_dlp_download_audio_command(
                "https://www.youtube.com/watch?v=VIDEO_ID",
                Path('downloads/yt_%(id)s.%(ext)s'),
            )
        ),
        "",
        "# 3) Demucs six stems (guitar isolated)",
        " ".join(demucs_separate_command(Path('song.wav'), Path('demucs_out'))),
        "",
        "# 4) Python: librosa_summarize, basic_pitch_predict_events, build_gp5_from_note_events",
        "#    (see app.pipeline_proof)",
        "",
    ]
    return "\n".join(lines)
