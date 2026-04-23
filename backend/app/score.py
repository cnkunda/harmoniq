"""Session scoring for POST /score (PRIORITIES §28)."""

from __future__ import annotations

import base64
import io
import logging
import tempfile
import wave
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from app.schemas import (
    ReliabilityEnvelope,
    ScoreDiagnostics,
    ScoreRequest,
    ScoreResult,
    ScoreWaveformComparison,
)
from app.scoring_constants import (
    HIGH_CONFIDENCE_HARMONIC_RATIO,
    HIGH_CONFIDENCE_VOICED_RATIO,
    LOW_SIGNAL_RMS,
    LOW_SIGNAL_VOICED_RATIO,
    MAX_ABS_NOTE_DELTA_SECONDS,
    MAX_BEND_ERROR_CENTS,
    MIN_VALID_RMS,
    MUSICAL_TOLERANCE_MODES,
    RELIABILITY_BANDS,
    SCORE_CONTRACT_VERSION,
    clamp01,
)


TARGET_SR = 22050
logger = logging.getLogger("harmoniq.score")


def _decode_recording(request: ScoreRequest) -> tuple[np.ndarray, int]:
    try:
        raw = base64.b64decode(request.recording_wav_base64, validate=False)
    except Exception as exc:
        raise ValueError("Invalid recording_wav_base64") from exc
    if len(raw) < 256:
        raise ValueError("Recording too short")

    ext = ".wav"
    mime = (request.recording_mime_type or "").lower()
    if "webm" in mime:
        ext = ".webm"
    elif "m4a" in mime or "mp4" in mime or "aac" in mime:
        ext = ".m4a"
    elif "wav" in mime:
        ext = ".wav"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        y, sr = librosa.load(tmp_path, sr=TARGET_SR, mono=True)
    finally:
        tmp_path.unlink(missing_ok=True)

    if y.size == 0:
        raise ValueError("Decoded recording is empty")
    return y.astype(np.float32), TARGET_SR


def _pc_from_note_name(name: str | None) -> int | None:
    if not name:
        return None
    token = name.strip().upper().split()[0]
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    try:
        return names.index(token)
    except ValueError:
        return None


def _score_pitch(y: np.ndarray, sr: int, section: dict[str, Any]) -> tuple[float, float, float, float, float]:
    # Harmonicity proxy (noise suppressor): harmonic / total RMS.
    y_harm, _ = librosa.effects.hpss(y)
    total_rms = float(np.sqrt(np.mean(np.square(y))) + 1e-8)
    harm_rms = float(np.sqrt(np.mean(np.square(y_harm))) + 1e-8)
    harmonic_ratio = clamp01(harm_rms / total_rms)

    f0 = librosa.yin(y, fmin=65.0, fmax=1100.0, sr=sr, frame_length=2048, hop_length=256)
    voiced = np.isfinite(f0) & (f0 > 0)
    voiced_ratio = clamp01(float(np.mean(voiced)) if voiced.size else 0.0)

    key_pc = _pc_from_note_name(str(section.get("key") or ""))
    if key_pc is None:
        # Minor/major unknown; default to A minor / C major collection.
        scale = {0, 2, 3, 5, 7, 8, 10}
    else:
        mode = str(section.get("mode") or "").lower()
        if "major" in mode:
            intervals = [0, 2, 4, 5, 7, 9, 11]
        else:
            intervals = [0, 2, 3, 5, 7, 8, 10]
        scale = {(key_pc + i) % 12 for i in intervals}

    cents_errors: list[float] = []
    if np.any(voiced):
        midi = 69.0 + 12.0 * np.log2(np.maximum(f0[voiced], 1e-8) / 440.0)
        nearest = np.round(midi)
        cents = np.abs((midi - nearest) * 100.0)
        cents_errors = cents.tolist()
        pcs = (nearest.astype(int) % 12).tolist()
        in_key = sum(1 for pc in pcs if pc in scale)
        in_key_ratio = in_key / max(1, len(pcs))
    else:
        in_key_ratio = 0.0

    mean_cents = float(np.mean(cents_errors)) if cents_errors else 100.0
    cents_score = clamp01(1.0 - (mean_cents / 80.0))

    pitch_accuracy = clamp01(
        0.45 * voiced_ratio + 0.25 * harmonic_ratio + 0.30 * (0.6 * in_key_ratio + 0.4 * cents_score),
    )

    bend_error_cents = float(min(MAX_BEND_ERROR_CENTS, max(0.0, mean_cents)))
    signal_quality = clamp01((0.45 * harmonic_ratio) + (0.35 * voiced_ratio) + (0.2 * min(1.0, total_rms / 0.03)))
    return pitch_accuracy, bend_error_cents, voiced_ratio, harmonic_ratio, signal_quality


def _score_timing(
    y: np.ndarray, sr: int, section: dict[str, Any], solo_notes: Any = None, musical_tolerance_mode: str = "technique"
) -> tuple[float, float, list[float], float, float]:
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=256, units="frames")
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=256)
    
    # Use MIDI note events as reference timing if available
    reference_onsets = None
    if solo_notes and hasattr(solo_notes, 'notes') and solo_notes.notes:
        reference_onsets = np.array([note.start_time for note in solo_notes.notes])
        logger.info("score.timing using %d MIDI note events as reference", len(reference_onsets))
    
    if onset_times.size < 2:
        return 0.25, 0.25, [], 0.0, 0.0

    iois = np.diff(onset_times)
    tempo = section.get("tempo")
    if not isinstance(tempo, (int, float)) or tempo <= 0:
        est_tempo, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=256)
        tempo = float(est_tempo if np.isfinite(est_tempo) and est_tempo > 0 else 90.0)
    beat_sec = 60.0 / float(tempo)

    # Get tolerance configuration based on mode (commit 92)
    tolerance_config = MUSICAL_TOLERANCE_MODES.get(musical_tolerance_mode, MUSICAL_TOLERANCE_MODES["technique"])
    timing_tolerance_ms = tolerance_config["timing_tolerance_ms"]
    timing_tolerance_sec = timing_tolerance_ms / 1000.0

    # If MIDI reference available, compare user onsets to nearest MIDI note onsets
    if reference_onsets is not None and reference_onsets.size > 0:
        # For each user onset, find nearest MIDI note onset and compute delta
        deltas = []
        for user_onset in onset_times[:32]:
            nearest_midi = reference_onsets[np.argmin(np.abs(reference_onsets - user_onset))]
            delta = user_onset - nearest_midi
            # Use mode-specific timing tolerance for clipping
            clipped = float(np.clip(delta, -timing_tolerance_sec, timing_tolerance_sec))
            deltas.append(round(clipped, 4))
        
        if deltas:
            residual = np.array(deltas)
        else:
            residual = np.array([])
    else:
        # Fallback to beat grid comparison
        nearest_grid = np.round(iois / beat_sec) * beat_sec
        residual = iois - nearest_grid
        # Use mode-specific timing tolerance for clipping
        clipped = np.clip(residual, -timing_tolerance_sec, timing_tolerance_sec)
        deltas = [float(round(v, 4)) for v in clipped[:32].tolist()]

    abs_resid = np.abs(residual) if residual.size > 0 else np.array([])
    # Adjust phrasing scoring based on tolerance mode (commit 92)
    # Expressive mode is more lenient, technique mode is stricter
    if musical_tolerance_mode == "expressive":
        phrasing_denominator = max(0.12, beat_sec * 0.5)  # More lenient denominator
    else:
        phrasing_denominator = max(0.08, beat_sec * 0.35)  # Stricter denominator
    phrasing_score = clamp01(1.0 - float(np.mean(abs_resid)) / phrasing_denominator) if abs_resid.size > 0 else 0.25
    rushing_ratio = float(np.mean(residual < 0)) if residual.size > 0 else 0.5
    rushing_score = clamp01(1.0 - rushing_ratio)

    if not deltas:
        clipped = np.clip(residual, -timing_tolerance_sec, timing_tolerance_sec) if residual.size > 0 else np.array([])
        deltas = [float(round(v, 4)) for v in clipped[:32].tolist()]
    
    p50_ms = float(np.quantile(abs_resid, 0.5) * 1000.0) if abs_resid.size else 0.0
    p95_ms = float(np.quantile(abs_resid, 0.95) * 1000.0) if abs_resid.size else 0.0
    return phrasing_score, rushing_score, deltas, p50_ms, p95_ms


def _confidence_from_signal(signal_quality: float, voiced_ratio: float, harmonic_ratio: float) -> str:
    if signal_quality <= RELIABILITY_BANDS.low_max:
        return "low"
    if (
        signal_quality >= RELIABILITY_BANDS.medium_max
        and voiced_ratio >= HIGH_CONFIDENCE_VOICED_RATIO
        and harmonic_ratio >= HIGH_CONFIDENCE_HARMONIC_RATIO
    ):
        return "high"
    return "medium"


def _waveform_preview_b64(y: np.ndarray, sr: int) -> str:
    # 8s mono preview WAV; enough for UI shell plotting.
    max_len = min(len(y), sr * 8)
    preview = y[:max_len]
    return _wav_b64_from_float(preview, sr)


def _reference_click_b64(section: dict[str, Any], duration_s: float, sr: int, solo_notes: Any = None) -> str:
    # Generate reference waveform from MIDI notes if available, otherwise use beat grid clicks
    if solo_notes and hasattr(solo_notes, 'notes') and solo_notes.notes:
        n = max(1, int(sr * min(duration_s, 8.0)))
        ref = np.zeros(n, dtype=np.float32)
        
        for note in solo_notes.notes:
            if not hasattr(note, 'start_time') or not hasattr(note, 'pitch') or not hasattr(note, 'duration'):
                continue
            start_sample = int(float(note.start_time) * sr)
            if start_sample < 0 or start_sample >= n:
                continue
            
            duration_samples = int(float(note.duration) * sr)
            end_sample = min(n, start_sample + duration_samples)
            
            # Synthesize a simple tone at the MIDI pitch
            if hasattr(note, 'pitch'):
                midi_pitch = int(note.pitch)
                frequency = 440.0 * (2.0 ** ((midi_pitch - 69) / 12.0))
                t = np.arange(end_sample - start_sample) / sr
                tone = 0.3 * np.sin(2 * np.pi * frequency * t)
                
                # Apply simple envelope
                envelope = np.exp(-3.0 * t / (duration_samples / sr if duration_samples > 0 else 0.1))
                ref[start_sample:end_sample] += tone * envelope.astype(np.float32)
        
        logger.info("score.reference generated waveform from %d MIDI notes", len(solo_notes.notes))
        return _wav_b64_from_float(ref, sr)
    
    # Fallback to beat grid clicks
    beat_grid = section.get("beat_grid")
    if not isinstance(beat_grid, list) or len(beat_grid) == 0:
        return ""
    n = max(1, int(sr * min(duration_s, 8.0)))
    ref = np.zeros(n, dtype=np.float32)
    click_len = int(sr * 0.01)
    for t in beat_grid:
        if not isinstance(t, (int, float)):
            continue
        i = int(float(t) * sr)
        if 0 <= i < n:
            end = min(n, i + click_len)
            ref[i:end] += np.linspace(0.8, 0.0, end - i, dtype=np.float32)
    return _wav_b64_from_float(ref, sr)


def _wav_b64_from_float(y: np.ndarray, sr: int) -> str:
    pcm16 = np.clip(y, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())
    return base64.b64encode(bio.getvalue()).decode("ascii")


def _coach_paragraph_from_score(
    pitch_accuracy: float,
    phrasing_score: float,
    rushing_score: float,
    confidence: str,
    reliability_flags: list[str],
    musical_tolerance_mode: str = "technique",
) -> str:
    p = int(round(pitch_accuracy * 100))
    ph = int(round(phrasing_score * 100))
    rt = int(round(rushing_score * 100))
    parts: list[str] = []
    
    # Mode-specific feedback (commit 92)
    if musical_tolerance_mode == "expressive":
        parts.append("Expressive mode: timing drag/push is allowed for musical feel.")
    else:
        parts.append("Technique mode: strict timing for precision practice.")
    
    if pitch_accuracy >= 0.85 and phrasing_score >= 0.8:
        parts.append(f"Solid take—pitch near {p}% and phrasing near {ph}%.")
    elif pitch_accuracy < 0.55:
        parts.append(f"Pitch is the main gap today ({p}%); match the reference in smaller chunks.")
    else:
        parts.append(f"Pitch {p}%, phrasing {ph}%.")

    if rushing_score < 0.55:
        if musical_tolerance_mode == "expressive":
            parts.append(f"Timing has room for feel ({rt}%); focus on groove over strict alignment.")
        else:
            parts.append(f"Timing wants more pocket ({rt}%); subdivide with the click or backing.")
    elif rushing_score >= 0.85:
        if musical_tolerance_mode == "expressive":
            parts.append("Your timing has great musical flow.")
        else:
            parts.append("Timing is locking in nicely.")

    if "timing_unstable" in reliability_flags:
        parts.append("We saw uneven timing residuals—shorter phrases usually help.")
    if any(f in reliability_flags for f in ("signal_low", "signal_near_silence", "voiced_sparse")):
        parts.append("Signal was light—move closer to the mic on the next pass.")
    if confidence == "low":
        parts.append("Confidence is low on this capture, so treat these numbers as directional.")
    return " ".join(parts).strip()


def score_recording(payload: ScoreRequest) -> ScoreResult:
    y, sr = _decode_recording(payload)
    section = payload.section if isinstance(payload.section, dict) else {}

    pitch_accuracy, bend_error_cents, voiced_ratio, harmonic_ratio, signal_quality = _score_pitch(y, sr, section)
    phrasing_score, rushing_score, note_duration_deltas, timing_p50_ms, timing_p95_ms = _score_timing(
        y, sr, section, payload.solo_notes, payload.musical_tolerance_mode
    )
    reliability_flags: list[str] = []
    rms = float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0
    if rms < MIN_VALID_RMS:
        reliability_flags.append("signal_near_silence")
    if rms < LOW_SIGNAL_RMS:
        reliability_flags.append("signal_low")
    if voiced_ratio < LOW_SIGNAL_VOICED_RATIO:
        reliability_flags.append("voiced_sparse")
    if timing_p95_ms > 185:
        reliability_flags.append("timing_unstable")
    confidence = _confidence_from_signal(signal_quality, voiced_ratio, harmonic_ratio)
    if reliability_flags:
        logger.info(
            "score.reliability flags=%s confidence=%s signal_quality=%.3f voiced_ratio=%.3f",
            ",".join(reliability_flags),
            confidence,
            signal_quality,
            voiced_ratio,
        )

    # Slightly favor phrasing in overall technique nodes for this stage.
    node_scores = {
        "pitch_accuracy": round(float(pitch_accuracy), 3),
        "phrasing": round(float(phrasing_score), 3),
        "timing": round(float(rushing_score), 3),
    }
    for node in payload.skill_nodes:
        if node not in node_scores:
            # Deterministic fallback projection from base metrics.
            node_scores[node] = round(float((pitch_accuracy + phrasing_score + rushing_score) / 3.0), 3)

    coach_paragraph = _coach_paragraph_from_score(
        float(pitch_accuracy),
        float(phrasing_score),
        float(rushing_score),
        confidence,
        reliability_flags,
        payload.musical_tolerance_mode,
    )

    return ScoreResult(
        pitch_accuracy=round(float(pitch_accuracy), 3),
        note_duration_deltas=note_duration_deltas,
        phrasing_score=round(float(phrasing_score), 3),
        bend_pitch_error_cents=round(float(bend_error_cents), 1),
        rushing_score=round(float(rushing_score), 3),
        coach_paragraph=coach_paragraph,
        node_scores=node_scores,
        waveform_comparison=ScoreWaveformComparison(
            user_wav_base64=_waveform_preview_b64(y, sr),
            reference_wav_base64=_reference_click_b64(section, duration_s=len(y) / sr, sr=sr, solo_notes=payload.solo_notes),
        ),
        diagnostics=ScoreDiagnostics(
            signal_quality=round(signal_quality, 3),
            voiced_ratio=round(voiced_ratio, 3),
            harmonic_ratio=round(harmonic_ratio, 3),
            timing_residual_p50_ms=round(timing_p50_ms, 1),
            timing_residual_p95_ms=round(timing_p95_ms, 1),
            reliability_flags=reliability_flags,
        ),
        reliability=ReliabilityEnvelope(
            score_contract_version=SCORE_CONTRACT_VERSION,
            confidence=confidence,
            signal_quality=round(signal_quality, 3),
            reliability_flags=reliability_flags,
        ),
    )
