"""Shared CAGED shape definitions for voicing detection.

Defines the five CAGED guitar chord shapes (E, A, C, D, G) used by both
the MT3 voicing recognizer and the CRNN fallback path. Keeping them in
one place prevents silent divergence between the two detection engines.
"""

from __future__ import annotations

CAGED_SHAPES: dict[str, dict] = {
    "E": {
        "strings": [1, 2, 3, 4, 5, 6],
        "pattern": [0, 0, 1, 2, 2, 0],
        "shiftable": True,
    },
    "A": {
        "strings": [1, 2, 3, 4, 5],
        "pattern": [0, 2, 2, 2, 0],
        "shiftable": True,
    },
    "C": {
        "strings": [1, 2, 3, 4, 5],
        "pattern": [0, 1, 0, 2, 3],
        "shiftable": False,
    },
    "D": {
        "strings": [1, 2, 3, 4],
        "pattern": [2, 3, 2, 0],
        "shiftable": False,
    },
    "G": {
        "strings": [1, 2, 3, 4, 5, 6],
        "pattern": [3, 3, 0, 0, 2, 3],
        "shiftable": False,
    },
}
