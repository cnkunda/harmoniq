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
    subprocess.run(cmd, check=True, capture_output=True, text=True)


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
    subprocess.run(cmd, check=True)
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
    """Tempo, beat grid, crude key estimate, and one full-length segment."""
    import librosa

    y, sr = librosa.load(str(audio_path), sr=TARGET_SR, mono=True)
    duration = float(len(y) / sr)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_estimates = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
    tempo_bpm = float(tempo_estimates[0])
    _, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beat_list = [float(t) for t in beat_times]

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    root, mode = estimate_key_literal(chroma_mean)
    key_name = f"{root} {mode}"

    segments: list[dict[str, Any]] = [
        {"label": "full", "start_s": 0.0, "end_s": duration},
    ]

    return LibrosaSummary(
        duration_s=duration,
        tempo_bpm=tempo_bpm,
        beat_times_s=beat_list,
        key_name=key_name,
        mode=mode,
        segments=segments,
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
    _, _, raw_events = basic_pitch_predict(str(audio_path), **kwargs)
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
) -> None:
    """
    Map note events onto quarter-note slots (floor beat index from ``start_s``) and
    write a monophonic/tab GP5. Rests fill empty quarter slots in each 4/4 bar.

    This is intentionally simple (proof-of-concept); a production pipeline would carry
    durations from Basic Pitch and respect tuplets / pickup bars.
    """
    import guitarpro as gp

    seconds_per_quarter = 60.0 / max(bpm, 1.0)
    by_beat: dict[int, list[int]] = defaultdict(list)
    for ev in events:
        b_idx = int(ev.start_s / seconds_per_quarter)
        by_beat[b_idx].append(ev.pitch_midi)
    # One pitch per beat (monophonic lead); Basic Pitch can emit polyphony on guitar stem.
    for k in list(by_beat.keys()):
        uniq = sorted(set(by_beat[k]))
        by_beat[k] = [uniq[-1]] if uniq else []

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
