"""YouTube title/artist from yt-dlp metadata (no download)."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("harmoniq.youtube_meta")
logger.setLevel(logging.INFO)

# Best-effort: many uploads use "Artist - Song Title" in a single title field.
_ARTIST_TITLE_SPLIT = re.compile(r"^(.+?)\s-\s(.+)$")


def _clean_str(value: Any) -> str | None:
    if isinstance(value, str) and (t := value.strip()):
        return t
    return None


def extract_youtube_metadata(url: str) -> tuple[str | None, str | None]:
    """Return ``(song_title, artist)`` using yt-dlp ``extract_info(..., download=False)``.

    Mapping (best-effort):
    - Title: ``track`` or ``title``.
    - Artist: ``artist``, ``creator``, or ``uploader``.
    - If artist is still missing and the chosen title matches ``Artist - Title``, split it.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt_dlp not available; skipping YouTube metadata")
        return None, None

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.warning("youtube metadata extract failed url=%r err=%s", url, e)
        return None, None

    if not isinstance(info, dict):
        return None, None

    track = _clean_str(info.get("track"))
    title = _clean_str(info.get("title"))
    song_title = track or title

    artist = (
        _clean_str(info.get("artist"))
        or _clean_str(info.get("creator"))
        or _clean_str(info.get("uploader"))
    )

    if song_title and artist is None:
        m = _ARTIST_TITLE_SPLIT.match(song_title)
        if m:
            artist = m.group(1).strip()
            song_title = m.group(2).strip()

    return song_title, artist
