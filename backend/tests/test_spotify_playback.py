"""Spotify playback route mapping (commit 77)."""

import pytest
from fastapi.testclient import TestClient

from app.schemas import SpotifyPlaybackState


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def test_spotify_playback_success(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    async def _fake_playback(_: str) -> SpotifyPlaybackState:
        return SpotifyPlaybackState(
            is_playing=True,
            progress_ms=12345,
            playback_rate=1.0,
            track_id="abc123",
            track_name="Slow Dancing in a Burning Room",
            artists=["John Mayer"],
        )

    monkeypatch.setattr("app.main.spotify_api.get_playback_state", _fake_playback)
    res = client.get("/spotify/playback", params={"client_session": "test-session"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["is_playing"] is True
    assert payload["progress_ms"] == 12345
    assert payload["track_name"] == "Slow Dancing in a Burning Room"


def test_spotify_playback_premium_required(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    async def _fake_playback(_: str) -> SpotifyPlaybackState:
        raise PermissionError("Spotify Premium is required for playback-follow mode.")

    monkeypatch.setattr("app.main.spotify_api.get_playback_state", _fake_playback)
    res = client.get("/spotify/playback", params={"client_session": "test-session"})
    assert res.status_code == 403
    assert "Premium" in str(res.json().get("detail", ""))


def test_spotify_playback_no_active_device(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    async def _fake_playback(_: str) -> SpotifyPlaybackState:
        raise RuntimeError("No active Spotify playback.")

    monkeypatch.setattr("app.main.spotify_api.get_playback_state", _fake_playback)
    res = client.get("/spotify/playback", params={"client_session": "test-session"})
    assert res.status_code == 409
