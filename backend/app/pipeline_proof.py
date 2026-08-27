"""
Notebook / feasibility pipeline: normalize audio → Demucs htdemucs_6s → Librosa
summary → Basic Pitch note events → Guitar Pro 5.

This module backs `research/pipeline_proof.ipynb` and future API steps. Heavy steps
(Demucs, Basic Pitch) are subprocess / optional imports; see backend README for
platform notes (Basic Pitch + TensorFlow on Windows/Linux Python 3.11+).
"""

from __future__ import annotations

import math
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# --- Constants aligned with README / PRIORITIES --------------------------------

DEMUCS_MODEL = "htdemucs_6s"
TARGET_SR = 44100

# Long-running CLIs may print a lot of stderr; only the tail is attached to failures.
_SUBPROCESS_FAIL_SNIP = 8000


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
    """Argv for `ffmpeg` to normalize to ``sample_rate`` Hz and channel layout."""
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
        str(output_path),
    ]


def ffmpeg_normalize_wav(
    input_path: Path,
    output_path: Path,
    *,
    sample_rate: int = TARGET_SR,
    mono: bool = True,
) -> None:
    """Resample / downmix via ffmpeg (44.1 kHz mono per Harmoniq README)."""
    cmd = ffmpeg_normalize_command(input_path, output_path, sample_rate=sample_rate, mono=mono)
    _run_subprocess_checked(cmd, what="ffmpeg")


def demucs_separate_command(
    input_wav: Path,
    out_dir: Path,
    *,
    model: str = DEMUCS_MODEL,
    python_executable: str | None = None,
) -> list[str]:
    """Argv to run Demucs with the ``htdemucs_6s`` six-stem checkpoint."""
    py = python_executable or sys.executable
    return [
        py,
        "-m",
        "demucs",
        "-n",
        model,
        "--out",
        str(out_dir),
        str(input_wav),
    ]


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
        "--js-runtimes",
        "node",
        "-o",
        str(output_template),
        url,
    ]


def yt_dlp_download_wav(url: str, work_dir: Path) -> Path:
    """
    Download audio to ``work_dir``; return path to the produced ``.wav``.
    Caller should run :func:`ffmpeg_normalize_wav` for strict 44.1 kHz mono.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    template = work_dir / "yt_%(id)s.%(ext)s"
    cmd = yt_dlp_download_audio_command(url, template)
    subprocess.run(cmd, check=True, cwd=str(work_dir))
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


def librosa_summarize(audio_path: Path, *, time_signature: str | None = None) -> LibrosaSummary:
    """
    Extract lightweight structure features from an audio file.

    Outputs are intended to be:
    - simple and robust (smoke-test level)
    - consistent with schema wiring for the frontend (bar timestamps + section labels)

    Args:
        time_signature: Optional time signature string (e.g. "4/4", "6/8").
            When provided, bar timestamps are derived from the actual time signature
            instead of hardcoding beats_per_bar=4.
    """
    import librosa
    import numpy as np

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
    labels = ["Intro", "Verse", "Chorus", "Solo", "Bridge", "Outro"]
    segments: list[dict[str, Any]] = []
    for i in range(len(boundaries) - 1):
        start_s = float(boundaries[i])
        end_s = float(boundaries[i + 1])
        if end_s - start_s < 0.2:
            continue
        segments.append(
            {
                "label": labels[i % len(labels)],
                "start_s": start_s,
                "end_s": end_s,
            }
        )

    if not segments:
        segments = [{"label": "full", "start_s": 0.0, "end_s": duration}]

    # --- Bar timestamps (derive beats_per_bar from time signature) -----------------------
    # beat_grid in schema is "quarter-note" timestamps; bar_timestamps are every N beats.
    # For compound meters (e.g. 6/8), beats_per_bar = numerator * 4 / denominator
    # because beat_list contains quarter-note timestamps, not pulse timestamps.
    from app.beat_grid import parse_time_signature
    try:
        ts_numerator, ts_denominator = parse_time_signature(time_signature)
        beats_per_bar = ts_numerator * 4 // ts_denominator
    except Exception:
        beats_per_bar = 4  # fallback to 4/4
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
    )


# --- Basic Pitch ----------------------------------------------------------------

@dataclass
class NoteEvent:
    start_s: float
    end_s: float
    pitch_midi: int
    amplitude: float = 0.0


def basic_pitch_predict_events(
    audio_path: Path,
    *,
    midi_tempo: float | None = None,
) -> list[NoteEvent]:
    """
    Run Spotify Basic Pitch on an audio file; return typed note events.

    Requires ``pip install -e ".[basicpitch]"`` (see ``pyproject.toml``). On some
    platforms Python/TensorFlow wheels are not available — the notebook documents this.
    """
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
    try:
        _, _, raw_events = basic_pitch_predict(str(audio_path), **kwargs)
    except Exception as default_err:
        import basic_pitch as basic_pitch_pkg

        tflite_path = Path(basic_pitch_pkg.__file__).resolve().parent / "saved_models" / "icassp_2022" / "nmp.tflite"
        if not tflite_path.exists():
            raise
        _, _, raw_events = basic_pitch_predict(str(audio_path), model_or_model_path=tflite_path, **kwargs)
    out: list[NoteEvent] = []
    for row in raw_events:
        # (start_s, end_s, pitch_midi, amplitude, pitch_bends?)
        start_s = float(row[0])
        end_s = float(row[1])
        pitch = int(round(float(row[2])))
        amp = float(row[3])
        out.append(NoteEvent(start_s=start_s, end_s=end_s, pitch_midi=pitch, amplitude=amp))
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
