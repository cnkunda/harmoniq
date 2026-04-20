"""Deterministic taste → `TasteProfile` derivation (commit 68) — no network I/O."""

from __future__ import annotations

from typing import Literal

from app.schemas import QuizAnswers, SpotifyTasteProfile, TasteProfile
from app.song_seeds import SONG_CANDIDATES_BY_STYLE
from app.taste_map import ARTIST_STYLE_HINTS, GENRE_STYLE_HINTS, STYLE_LABELS


def _style_scores_from_spotify(sp: SpotifyTasteProfile) -> dict[str, float]:
    scores: dict[str, float] = {s: 0.0 for s in STYLE_LABELS}
    for g in sp.top_genres:
        gl = (g or "").strip().lower()
        if not gl:
            continue
        for sub, style, w in GENRE_STYLE_HINTS:
            if sub in gl:
                scores[style] = scores.get(style, 0.0) + w
    blob = " ".join(a.strip().lower() for a in sp.top_artists if a.strip())
    if blob:
        for sub, style, w in ARTIST_STYLE_HINTS:
            if sub in blob:
                scores[style] = scores.get(style, 0.0) + w
    return scores


def _pick_style(scores: dict[str, float]) -> str:
    best = max(scores.values()) if scores else 0.0
    if best <= 0.0:
        return "pop"
    tied = [s for s, v in scores.items() if v >= best - 1e-9]
    for label in STYLE_LABELS:
        if label in tied:
            return label
    return tied[0]


def _default_tempo_for_style(style: str) -> float:
    return {
        "blues": 92.0,
        "rock": 118.0,
        "fingerstyle": 88.0,
        "jazz": 140.0,
        "country": 100.0,
        "metal": 150.0,
        "pop": 108.0,
    }.get(style, 100.0)


def _bpm_range_from_center(center: float) -> tuple[int, int]:
    lo = int(round(center - 20.0))
    hi = int(round(center + 20.0))
    lo = max(40, min(lo, 220))
    hi = max(40, min(hi, 240))
    if hi < lo:
        lo, hi = hi, lo
    return lo, hi


def _technique_affinity(
    style: str,
    *,
    energy_avg: float,
    tempo_avg: float,
    instrumentalness_avg: float,
) -> list[str]:
    out: list[str] = []

    def add(x: str) -> None:
        if x not in out:
            out.append(x)

    if style == "blues":
        add("bending")
        add("vibrato")
    elif style == "jazz":
        add("chord extensions")
        add("jazz comping")
    elif style == "metal":
        add("alternate picking")
        add("palm muting")
    elif style == "rock":
        add("power chords")
        add("bending")
    elif style == "country":
        add("hybrid picking")
        add("bending")
    elif style == "fingerstyle":
        add("fingerpicking")
        add("chord melody")
    else:  # pop + fallback
        add("strumming")
        add("timing")

    if energy_avg > 0.65 and tempo_avg > 115.0:
        add("alternate picking")
        add("bending")
    if energy_avg < 0.45 and instrumentalness_avg < 0.35:
        add("fingerpicking")
        add("chord melody")

    return out


def _rank_song_candidates(style: str, techniques: list[str]) -> list[str]:
    raw = list(SONG_CANDIDATES_BY_STYLE.get(style, SONG_CANDIDATES_BY_STYLE["pop"]))
    tech_blob = " ".join(techniques).lower()

    def score_line(line: str) -> tuple[float, str]:
        line_l = line.lower()
        hits = sum(1 for t in techniques if t and t.lower() in line_l)
        # Secondary: rough keyword overlap with technique blob words (deterministic).
        extra = 0.1 * sum(1 for w in tech_blob.split() if len(w) > 3 and w in line_l)
        return (-(hits + extra), line)

    ranked = sorted(raw, key=score_line)
    return ranked[:8]


def derive_from_spotify(
    sp: SpotifyTasteProfile,
    *,
    source: Literal["spotify", "manual"] = "spotify",
) -> TasteProfile:
    scores = _style_scores_from_spotify(sp)
    style = _pick_style(scores)
    center = float(sp.tempo_avg) if sp.tempo_avg and sp.tempo_avg > 0.0 else _default_tempo_for_style(style)
    bpm_lo, bpm_hi = _bpm_range_from_center(center)
    tech = _technique_affinity(
        style,
        energy_avg=float(sp.energy_avg or 0.0),
        tempo_avg=float(sp.tempo_avg or center),
        instrumentalness_avg=float(sp.instrumentalness_avg or 0.0),
    )
    songs = _rank_song_candidates(style, tech)
    return TasteProfile(
        style_label=style,
        technique_affinity=tech,
        bpm_comfort_range=(bpm_lo, bpm_hi),
        song_candidates=songs,
        source=source,
    )


def _normalize_quiz_style(raw: str) -> str:
    s = (raw or "").strip().lower().replace("-", " ")
    aliases = {
        "blues": "blues",
        "rock": "rock",
        "fingerstyle": "fingerstyle",
        "finger style": "fingerstyle",
        "acoustic": "fingerstyle",
        "jazz": "jazz",
        "country": "country",
        "metal": "metal",
        "pop": "pop",
    }
    if s in aliases:
        return aliases[s]
    for label in STYLE_LABELS:
        if label in s:
            return label
    return "pop"


def _quiz_tempo_center(level: str, style: str) -> float:
    base = _default_tempo_for_style(style)
    if level == "beginner":
        return min(base, 95.0)
    if level == "advanced":
        return max(base, 120.0)
    return base


def derive_from_quiz(q: QuizAnswers) -> TasteProfile:
    style = _normalize_quiz_style(q.selected_style)
    level = (q.experience_level or "intermediate").strip().lower()
    if level not in ("beginner", "intermediate", "advanced"):
        level = "intermediate"
    center = _quiz_tempo_center(level, style)
    bpm_lo, bpm_hi = _bpm_range_from_center(center)
    energy = 0.35 if level == "beginner" else 0.55 if level == "intermediate" else 0.72
    tempo_hint = center + (10.0 if level == "advanced" else 0.0)
    instr = 0.25 if style in ("fingerstyle", "jazz", "country") else 0.4
    tech = _technique_affinity(style, energy_avg=energy, tempo_avg=tempo_hint, instrumentalness_avg=instr)
    songs = _rank_song_candidates(style, tech)
    return TasteProfile(
        style_label=style,
        technique_affinity=tech,
        bpm_comfort_range=(bpm_lo, bpm_hi),
        song_candidates=songs,
        source="quiz",
    )


def derive_taste_profile(
    *,
    spotify_profile: SpotifyTasteProfile | None = None,
    quiz_answers: QuizAnswers | None = None,
    taste_source: Literal["spotify", "manual"] | None = None,
) -> TasteProfile:
    """Dispatch derivation from Spotify-shaped taste or cold-start quiz answers."""
    if quiz_answers is not None:
        return derive_from_quiz(quiz_answers)
    if spotify_profile is not None:
        src: Literal["spotify", "manual"] = "manual" if taste_source == "manual" else "spotify"
        return derive_from_spotify(spotify_profile, source=src)
    raise ValueError("Provide spotify_profile or quiz_answers.")
