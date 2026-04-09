"""Session scoring for POST /score (PRIORITIES §28)."""

from __future__ import annotations

import base64
import io
import tempfile
import wave
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from app.schemas import ScoreRequest, ScoreResult, ScoreWaveformComparison


TARGET_SR = 22050


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


def _score_pitch(y: np.ndarray, sr: int, section: dict[str, Any]) -> tuple[float, float]:
    # Harmonicity proxy (noise suppressor): harmonic / total RMS.
    y_harm, _ = librosa.effects.hpss(y)
    total_rms = float(np.sqrt(np.mean(np.square(y))) + 1e-8)
    harm_rms = float(np.sqrt(np.mean(np.square(y_harm))) + 1e-8)
    harmonic_ratio = max(0.0, min(1.0, harm_rms / total_rms))

    f0 = librosa.yin(y, fmin=65.0, fmax=1100.0, sr=sr, frame_length=2048, hop_length=256)
    voiced = np.isfinite(f0) & (f0 > 0)
    voiced_ratio = float(np.mean(voiced)) if voiced.size else 0.0

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
    cents_score = max(0.0, 1.0 - (mean_cents / 80.0))

    pitch_accuracy = max(
        0.0,
        min(1.0, 0.45 * voiced_ratio + 0.25 * harmonic_ratio + 0.30 * (0.6 * in_key_ratio + 0.4 * cents_score)),
    )

    bend_error_cents = float(min(120.0, max(0.0, mean_cents)))
    return pitch_accuracy, bend_error_cents


def _score_timing(y: np.ndarray, sr: int, section: dict[str, Any]) -> tuple[float, float, list[float]]:
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=256, units="frames")
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=256)
    if onset_times.size < 2:
        return 0.25, 0.25, []

    iois = np.diff(onset_times)
    tempo = section.get("tempo")
    if not isinstance(tempo, (int, float)) or tempo <= 0:
        est_tempo, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=256)
        tempo = float(est_tempo if np.isfinite(est_tempo) and est_tempo > 0 else 90.0)
    beat_sec = 60.0 / float(tempo)

    nearest_grid = np.round(iois / beat_sec) * beat_sec
    residual = iois - nearest_grid

    abs_resid = np.abs(residual)
    phrasing_score = max(0.0, min(1.0, 1.0 - float(np.mean(abs_resid)) / max(0.08, beat_sec * 0.35)))
    rushing_ratio = float(np.mean(residual < 0))
    rushing_score = max(0.0, min(1.0, 1.0 - rushing_ratio))

    clipped = np.clip(residual, -0.25, 0.25)
    deltas = [float(round(v, 4)) for v in clipped[:32].tolist()]
    return phrasing_score, rushing_score, deltas


def _waveform_preview_b64(y: np.ndarray, sr: int) -> str:
    # 8s mono preview WAV; enough for UI shell plotting.
    max_len = min(len(y), sr * 8)
    preview = y[:max_len]
    return _wav_b64_from_float(preview, sr)


def _reference_click_b64(section: dict[str, Any], duration_s: float, sr: int) -> str:
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


def score_recording(payload: ScoreRequest) -> ScoreResult:
    y, sr = _decode_recording(payload)
    section = payload.section if isinstance(payload.section, dict) else {}

    pitch_accuracy, bend_error_cents = _score_pitch(y, sr, section)
    phrasing_score, rushing_score, note_duration_deltas = _score_timing(y, sr, section)

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

    return ScoreResult(
        pitch_accuracy=round(float(pitch_accuracy), 3),
        note_duration_deltas=note_duration_deltas,
        phrasing_score=round(float(phrasing_score), 3),
        bend_pitch_error_cents=round(float(bend_error_cents), 1),
        rushing_score=round(float(rushing_score), 3),
        node_scores=node_scores,
        waveform_comparison=ScoreWaveformComparison(
            user_wav_base64=_waveform_preview_b64(y, sr),
            reference_wav_base64=_reference_click_b64(section, duration_s=len(y) / sr, sr=sr),
        ),
    )
