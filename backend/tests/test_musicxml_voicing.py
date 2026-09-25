"""Tests for Commit B9: MusicXML chord diagrams with voicing info."""
from __future__ import annotations

import pytest

from app.musicxml_builder import _compute_chord_voicing, _CAGED_VOICING_SHAPES


class TestMusicXmlVoicing:

    def test_voicing_shape_in_diagram(self):
        """E-shape voicing produces correct (string, fret) pairs."""
        voicing = _compute_chord_voicing("C:maj", voicing_shape="E", voicing_position=8)
        # E-shape at fret 8 (C barre): pattern [0,0,1,2,2,0] + 8
        # Expected: (1,8), (2,8), (3,9), (4,10), (5,10), (6,8)
        assert voicing == [(1, 8), (2, 8), (3, 9), (4, 10), (5, 10), (6, 8)], f"Got {voicing}"

    def test_open_position_no_first_fret_needed(self):
        """Open position chord (voicing_position=0) gives correct frets."""
        voicing = _compute_chord_voicing("E:maj", voicing_shape="E", voicing_position=0)
        # Open E: pattern [0,0,1,2,2,0]
        assert voicing == [(1, 0), (2, 0), (3, 1), (4, 2), (5, 2), (6, 0)], f"Got {voicing}"

    def test_barre_voicing_first_fret(self):
        """Barre chord at position 5 produces correct frets."""
        voicing = _compute_chord_voicing("A:maj", voicing_shape="A", voicing_position=5)
        # A-shape barre at fret 5 (D): strings [1,2,3,4,5], pattern [0,2,2,2,0] + 5
        # Expected: (1,5), (2,7), (3,7), (4,7), (5,5)
        assert voicing == [(1, 5), (2, 7), (3, 7), (4, 7), (5, 5)], f"Got {voicing}"

    def test_no_voicing_falls_back(self):
        """Chord without voicing info uses current fallback algorithm (non-empty)."""
        voicing = _compute_chord_voicing("C:maj")
        # Fallback should produce some voicing, not empty
        assert len(voicing) >= 3, f"Fallback voicing too short: {voicing}"

    def test_g_shape_voicing(self):
        """G-shape at position 0 (open G)."""
        voicing = _compute_chord_voicing("G:maj", voicing_shape="G", voicing_position=0)
        # G-shape: strings [1,2,3,4,5,6], pattern [3,3,0,0,2,3]
        assert voicing == [(1, 3), (2, 3), (3, 0), (4, 0), (5, 2), (6, 3)], f"Got {voicing}"

    def test_d_shape_voicing(self):
        """D-shape at position 0 (open D)."""
        voicing = _compute_chord_voicing("D:maj", voicing_shape="D", voicing_position=0)
        # D-shape: strings [1,2,3,4], pattern [2,3,2,0]
        assert voicing == [(1, 2), (2, 3), (3, 2), (4, 0)], f"Got {voicing}"

    def test_c_shape_voicing(self):
        """C-shape at position 0 (open C)."""
        voicing = _compute_chord_voicing("C:maj", voicing_shape="C", voicing_position=0)
        # C-shape: strings [1,2,3,4,5], pattern [0,1,0,2,3]
        assert voicing == [(1, 0), (2, 1), (3, 0), (4, 2), (5, 3)], f"Got {voicing}"

    def test_invalid_shape_uses_fallback(self):
        """Unknown shape name falls back gracefully."""
        voicing = _compute_chord_voicing("G:maj", voicing_shape="Z", voicing_position=0)
        assert len(voicing) >= 3
