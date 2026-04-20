"""Spotify routes when HARMONIQ_SKIP_SPOTIFY=1 (commit 67)."""

import pytest
from fastapi.testclient import TestClient


def test_spotify_routes_skip_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARMONIQ_SKIP_SPOTIFY", "1")
    from app.main import app

    c = TestClient(app)
    assert c.get("/auth/spotify", params={"client_session": "test-session"}).status_code == 503
    assert c.get("/auth/spotify/callback", params={"code": "x", "state": "y"}).status_code == 503
    assert c.get("/taste/spotify", params={"client_session": "test-session"}).status_code == 503
    assert c.delete("/auth/spotify", params={"client_session": "test-session"}).status_code == 503
