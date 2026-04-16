"""Unit tests for YouTube metadata extraction (mocked yt-dlp)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.youtube_meta import extract_youtube_metadata


def test_extract_prefers_track_and_artist_fields():
    info = {"track": "  Back in Black ", "artist": " AC/DC ", "title": "ignored"}
    with patch("yt_dlp.YoutubeDL") as ydl_cls:
        inst = MagicMock()
        ydl_cls.return_value.__enter__.return_value = inst
        inst.extract_info.return_value = info
        title, artist = extract_youtube_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert title == "Back in Black"
    assert artist == "AC/DC"


def test_extract_splits_title_when_artist_missing():
    info = {"title": "The Beatles - Yesterday"}
    with patch("yt_dlp.YoutubeDL") as ydl_cls:
        inst = MagicMock()
        ydl_cls.return_value.__enter__.return_value = inst
        inst.extract_info.return_value = info
        title, artist = extract_youtube_metadata("https://youtu.be/xyz12345")
    assert artist == "The Beatles"
    assert title == "Yesterday"


def test_extract_returns_none_on_failure():
    with patch("yt_dlp.YoutubeDL") as ydl_cls:
        inst = MagicMock()
        ydl_cls.return_value.__enter__.return_value = inst
        inst.extract_info.side_effect = RuntimeError("network")
        title, artist = extract_youtube_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert title is None
    assert artist is None
