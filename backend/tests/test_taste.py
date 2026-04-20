"""Taste derivation (commit 68)."""

import time

import pytest
from fastapi.testclient import TestClient

from app.schemas import QuizAnswers, SpotifyTasteProfile
from app.taste import derive_from_quiz, derive_from_spotify, derive_taste_profile
from app.taste_map import STYLE_LABELS


def test_blues_spotify_fixture_has_bending_and_vibrato() -> None:
    sp = SpotifyTasteProfile(
        top_genres=["blues", "blues rock"],
        top_artists=["Stevie Ray Vaughan"],
        energy_avg=0.55,
        tempo_avg=100.0,
        instrumentalness_avg=0.2,
    )
    tp = derive_from_spotify(sp, source="spotify")
    assert tp.style_label == "blues"
    assert "bending" in tp.technique_affinity
    assert "vibrato" in tp.technique_affinity


@pytest.mark.parametrize(
    "genres",
    [
        ["blues rock"],
        ["classic rock"],
        ["fingerstyle"],
        ["jazz fusion"],
        ["country"],
        ["heavy metal"],
        ["pop"],
    ],
)
def test_song_candidates_at_least_three(genres: list[str]) -> None:
    sp = SpotifyTasteProfile(
        top_genres=genres,
        top_artists=[],
        energy_avg=0.5,
        tempo_avg=110.0,
        instrumentalness_avg=0.3,
    )
    tp = derive_from_spotify(sp)
    assert len(tp.song_candidates) >= 3


def test_quiz_source_spotify_vs_quiz() -> None:
    sp = SpotifyTasteProfile(top_genres=["blues"], top_artists=[], energy_avg=0.5, tempo_avg=90.0, instrumentalness_avg=0.2)
    a = derive_taste_profile(spotify_profile=sp, quiz_answers=None, taste_source=None)
    assert a.source == "spotify"

    b = derive_taste_profile(spotify_profile=sp, quiz_answers=None, taste_source="manual")
    assert b.source == "manual"

    q = QuizAnswers(selected_artists=["Pat Metheny"], selected_style="jazz", experience_level="intermediate")
    c = derive_from_quiz(q)
    assert c.source == "quiz"


def test_derivation_fast_no_network() -> None:
    sp = SpotifyTasteProfile(
        top_genres=["metal", "thrash"],
        top_artists=["Metallica"],
        energy_avg=0.9,
        tempo_avg=180.0,
        instrumentalness_avg=0.5,
    )
    t0 = time.perf_counter()
    for _ in range(50):
        derive_from_spotify(sp)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"50 derivations took {elapsed:.3f}s (expected <<1s, no I/O)"


def test_skip_taste_derive_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARMONIQ_SKIP_TASTE_DERIVE", "1")
    from app.main import app

    c = TestClient(app)
    body = {
        "spotify_profile": {
            "top_genres": ["blues"],
            "top_artists": [],
            "energy_avg": 0.5,
            "tempo_avg": 90.0,
            "instrumentalness_avg": 0.2,
        }
    }
    assert c.post("/taste/derive", json=body).status_code == 503


def test_quiz_stevie_ray_vaughan_plus_blues_style() -> None:
    """PRIORITIES §69 acceptance — artist + vibe quiz path."""
    q = QuizAnswers(
        selected_artists=["Stevie Ray Vaughan"],
        selected_style="blues",
        experience_level="intermediate",
    )
    tp = derive_from_quiz(q)
    assert tp.style_label == "blues"
    assert tp.source == "quiz"


def test_all_supported_styles_reachable() -> None:
    """Each canonical style_label appears from at least one seeded genre list."""
    hints: dict[str, list[str]] = {
        "blues": ["delta blues"],
        "rock": ["indie rock"],
        "fingerstyle": ["folk"],
        "jazz": ["bebop"],
        "country": ["bluegrass"],
        "metal": ["death metal"],
        "pop": ["dance"],
    }
    seen = set()
    for style, genres in hints.items():
        tp = derive_from_spotify(SpotifyTasteProfile(top_genres=genres, top_artists=[], energy_avg=0.5, tempo_avg=100.0, instrumentalness_avg=0.3))
        seen.add(tp.style_label)
        assert tp.style_label == style
    assert seen == set(STYLE_LABELS)
