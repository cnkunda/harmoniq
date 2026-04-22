"""Server-side tab export (GP5 → MIDI / MusicXML; PDF/PNG not available in this build)."""

from __future__ import annotations

import base64
import os
import re

from app.gp_export_midi import gp5_bytes_to_midi
from app.gp_export_musicxml import gp5_bytes_to_musicxml
from app.musicxml_builder import build_musicxml # NEW
from app.schemas import BeatGrid, ChordTimeline, SoloNotes # NEW

ALLOWED_FORMATS = frozenset({"midi", "musicxml", "pdf", "png"})
# ~16MB binary after base64 decode
_MAX_GP5_BINARY = 16 * 1024 * 1024
_MIN_GP5_BINARY = 32

_ANSI_FILE = re.compile(r"[^A-Za-z0-9._-]+")


class ExportDisabledError(Exception):
    """Raised when HARMONIQ_SKIP_EXPORT=1."""


class ExportUnsupportedError(Exception):
    """Format is whitelisted but not implemented on this server."""


def _safe_filename_stem(name: str) -> str:
    s = (name or "harmoniq").strip() or "harmoniq"
    s = _ANSI_FILE.sub("_", s)[:64]
    return s or "harmoniq"


def export_gp5_base64(
    gp5_base64: str,
    export_format: str,
    *,
    title_hint: str | None = None,
) -> tuple[bytes, str, str, str]:
    """
    Return (raw bytes, media type, file extension, download filename base (no ext)).
    """
    if os.getenv("HARMONIQ_SKIP_EXPORT", "").strip() == "1":
        raise ExportDisabledError("Export is disabled on this server (HARMONIQ_SKIP_EXPORT=1).")

    b64 = re.sub(r"\s+", "", gp5_base64)
    raw = base64.b64decode(b64, validate=True)
    if len(raw) < _MIN_GP5_BINARY:
        raise ValueError("GP5 payload is too small or corrupt.")
    if len(raw) > _MAX_GP5_BINARY:
        raise ValueError("GP5 payload exceeds the maximum allowed size.")

    fmt = export_format.strip().lower()
    if fmt not in ALLOWED_FORMATS:
        raise ValueError(f"Unsupported export format (allowed: {', '.join(sorted(ALLOWED_FORMATS))}).")

    stem = _safe_filename_stem(title_hint or "")

    if fmt == "midi":
        data = gp5_bytes_to_midi(raw)
        return data, "audio/midi", ".mid", stem
    if fmt == "musicxml":
        data = gp5_bytes_to_musicxml(raw)
        return data, "application/vnd.recordare.musicxml+xml", ".musicxml", stem
    if fmt == "pdf":
        raise ExportUnsupportedError("PDF export is not available on this server.")
    raise ExportUnsupportedError("PNG export is not available on this server.")

def export_musicxml_from_json(
    beat_grid: BeatGrid,
    chord_timeline: ChordTimeline,
    solo_notes: SoloNotes,
    title: str = "Harmoniq Score",
    artist: str = "Harmoniq AI",
    key_signature: str | None = None,
) -> tuple[bytes, str, str, str]:
    """
    Generate MusicXML from Harmoniq JSON artifacts.
    Return (raw bytes, media type, file extension, download filename base (no ext)).
    """
    musicxml_str = build_musicxml(
        beat_grid=beat_grid,
        chord_timeline=chord_timeline,
        solo_notes=solo_notes,
        title=title,
        artist=artist,
        key_signature=key_signature,
    )
    # musicxml_builder returns a UTF-8 string, so encode it to bytes
    data = musicxml_str.encode("utf-8")
    stem = _safe_filename_stem(title)
    return data, "application/vnd.recordare.musicxml+xml", ".musicxml", stem
