"""
Heuristic stem isolation and classification after Demucs htdemucs_6s.

Detects piano-led mixes, near-silent / buried guitar stems, and drives analysis path:
librosa can run on full mix or piano stem when the guitar stem is not trustworthy.

Thresholds aligned with scripts/smoke_stems.py (smoke tests, not model tuning).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

try:
    import librosa
except ImportError:
    librosa = None  # pragma: no cover

from app.pipeline_proof import TARGET_SR

# --- Floors (scripts/smoke_stems.py) -------------------------------------------------
MIN_STEM_RMS = 5e-5
MIN_RMS_GUITAR = 1e-3
RMS_MIX_FLOOR = 1e-12
MIN_RATIO_GUITAR_TO_MIX = 0.018

# Piano vs guitar (existing)
PIANO_DOMINATES_RATIO = 2.35
MAX_GUITAR_PIANO_ENVELOPE_CORR = 0.88

_ENVELOPE_FRAME_SAMPLES = 2048
_ENVELOPE_MIN_SAMPLES = 32
_ENVELOPE_STD_FLOOR = 1e-12

AnalysisAudioRole = Literal["guitar_stem", "full_mix", "piano_stem"]


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def _align_len(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = min(a.shape[0], b.shape[0])
    return a[:n], b[:n]


def _smoothed_envelope(y: np.ndarray, *, frame: int = _ENVELOPE_FRAME_SAMPLES) -> np.ndarray:
    y = np.abs(y.astype(np.float64))
    fr = frame
    if y.size < fr:
        fr = max(_ENVELOPE_MIN_SAMPLES, y.size // 4 or _ENVELOPE_MIN_SAMPLES)
    k = np.ones(fr, dtype=np.float64) / float(fr)
    return np.convolve(y, k, mode="same")


def _envelope_pearson(a: np.ndarray, b: np.ndarray) -> float:
    a, b = _align_len(a, b)
    ea = _smoothed_envelope(a)
    eb = _smoothed_envelope(b)
    ea = ea - ea.mean()
    eb = eb - eb.mean()
    da = float(np.std(ea))
    db = float(np.std(eb))
    if da < _ENVELOPE_STD_FLOOR or db < _ENVELOPE_STD_FLOOR:
        return 0.0
    return float(np.clip(np.mean((ea / da) * (eb / db)), -1.0, 1.0))


def _load_mono(path: Path) -> np.ndarray | None:
    if librosa is None or not path.is_file():
        return None
    try:
        y, _ = librosa.load(str(path), sr=TARGET_SR, mono=True)
        return y
    except Exception:
        return None


USER_WARNING_PIANO = (
    "This recording sounds piano-led. The isolated guitar stem may carry keyboard bleed. "
    "Harmoniq used the piano stem (or full mix) for tempo and beat structure and skipped "
    "guitar tab generation. Try a mix with clear guitar parts."
)
USER_WARNING_SILENT = (
    "The isolated guitar stem is very quiet. Harmoniq analyzed the full mix for tempo "
    "and beats and skipped guitar tabs. Try a source with an audible guitar part."
)
USER_WARNING_BURIED = (
    "The guitar stem carries little energy compared to the full mix. Harmoniq analyzed "
    "the full mix for structure and skipped guitar tabs."
)


@dataclass(frozen=True)
class StemClassification:
    """Post-separation classification for lesson analysis and tab generation."""

    guitar_stem_usable: bool
    analysis_audio_role: AnalysisAudioRole
    flags: tuple[str, ...]
    user_warning: str | None


def stem_isolation_flags_from_metrics(r_g: float, r_p: float, corr_abs: float) -> list[str]:
    """Piano-heavy / envelope collision (unit-tested without WAV I/O)."""
    flags: list[str] = []
    guitar_floor = max(r_g, MIN_STEM_RMS)
    if r_p >= PIANO_DOMINATES_RATIO * guitar_floor and r_p > MIN_STEM_RMS * 20:
        flags.append("piano_dominates_guitar")
    if corr_abs >= MAX_GUITAR_PIANO_ENVELOPE_CORR and r_p >= 0.85 * max(r_g, MIN_STEM_RMS):
        flags.append("guitar_piano_envelope_collision")
    return flags


def collect_stem_quality_flags(r_m: float, r_g: float, r_p: float, corr_abs: float) -> list[str]:
    """All quality flags including guitar silence / bury vs mix."""
    flags: list[str] = []

    if r_g < MIN_RMS_GUITAR:
        flags.append("guitar_near_silent")

    ratio = (r_g / r_m) if r_m > RMS_MIX_FLOOR else 0.0
    if r_m > RMS_MIX_FLOOR and ratio < MIN_RATIO_GUITAR_TO_MIX and r_g >= MIN_STEM_RMS:
        flags.append("guitar_buried_in_mix")

    flags.extend(stem_isolation_flags_from_metrics(r_g, r_p, corr_abs))
    # De-duplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _pick_user_warning(flags: list[str]) -> str | None:
    if "piano_dominates_guitar" in flags or "guitar_piano_envelope_collision" in flags:
        return USER_WARNING_PIANO
    if "guitar_near_silent" in flags:
        return USER_WARNING_SILENT
    if "guitar_buried_in_mix" in flags:
        return USER_WARNING_BURIED
    return None


def _pick_analysis_role(flags: list[str], *, r_p: float) -> AnalysisAudioRole:
    piano_led = "piano_dominates_guitar" in flags or "guitar_piano_envelope_collision" in flags
    needs_mix = "guitar_near_silent" in flags or "guitar_buried_in_mix" in flags

    if piano_led:
        if r_p > MIN_STEM_RMS * 20:
            return "piano_stem"
        return "full_mix"
    if needs_mix:
        return "full_mix"
    return "guitar_stem"


def classify_stems_for_lesson(mix_wav: Path, stem_paths: dict[str, Path]) -> StemClassification:
    """
    Full classification for analyze pipeline.

    ``stem_paths`` maps stem names to absolute WAV paths (post-separation).
    On missing data or librosa unavailable, returns guitar-usable defaults.
    """
    if librosa is None:
        return StemClassification(
            guitar_stem_usable=True,
            analysis_audio_role="guitar_stem",
            flags=(),
            user_warning=None,
        )

    g_path = stem_paths.get("guitar")
    p_path = stem_paths.get("piano")
    if g_path is None:
        return StemClassification(True, "guitar_stem", (), None)

    mix = _load_mono(mix_wav)
    guitar = _load_mono(g_path)
    piano = _load_mono(p_path) if p_path else None

    if guitar is None:
        return StemClassification(True, "guitar_stem", (), None)

    r_g = _rms(guitar)
    r_m = _rms(mix) if mix is not None else 0.0
    r_p = _rms(piano) if piano is not None else 0.0

    if r_g < MIN_STEM_RMS and r_p < MIN_STEM_RMS and r_m < MIN_STEM_RMS:
        return StemClassification(True, "guitar_stem", (), None)

    corr = abs(_envelope_pearson(guitar, piano)) if piano is not None else 0.0
    flags = collect_stem_quality_flags(r_m, r_g, r_p, corr)

    unusable = any(
        f in flags
        for f in (
            "piano_dominates_guitar",
            "guitar_piano_envelope_collision",
            "guitar_near_silent",
            "guitar_buried_in_mix",
        )
    )
    role = _pick_analysis_role(flags, r_p=r_p) if unusable else "guitar_stem"
    warning = _pick_user_warning(flags) if unusable else None

    return StemClassification(
        guitar_stem_usable=not unusable,
        analysis_audio_role=role,
        flags=tuple(flags),
        user_warning=warning,
    )


# Back-compat alias for older call sites / tests
def assess_stem_isolation(mix_wav: Path, stem_paths: dict[str, Path]) -> StemClassification:
    """Deprecated: use classify_stems_for_lesson."""
    return classify_stems_for_lesson(mix_wav, stem_paths)
