"""Static genre → Harmoniq `style_label` hints (commit 68).

`GENRE_STYLE_HINTS` rows are `(substring, style_label, weight)` evaluated case-insensitively.
Longer substrings are listed first so e.g. "blues rock" wins over "rock" when both match.

Supported `style_label` values: blues, rock, fingerstyle, jazz, country, metal, pop.
"""

from __future__ import annotations

# (lowercase substring, style_label, weight)
GENRE_STYLE_HINTS: tuple[tuple[str, str, float], ...] = (
    ("blues rock", "blues", 3.0),
    ("rhythm and blues", "blues", 2.5),
    ("r&b", "pop", 1.0),
    ("blues", "blues", 2.5),
    ("delta blues", "blues", 3.0),
    ("electric blues", "blues", 3.0),
    ("fingerstyle", "fingerstyle", 3.0),
    ("acoustic", "fingerstyle", 1.2),
    ("singer-songwriter", "fingerstyle", 1.5),
    ("folk", "fingerstyle", 1.4),
    ("country", "country", 2.5),
    ("bluegrass", "country", 2.0),
    ("americana", "country", 1.8),
    ("jazz fusion", "jazz", 2.8),
    ("bebop", "jazz", 2.8),
    ("swing", "jazz", 2.2),
    ("jazz", "jazz", 2.5),
    ("hard rock", "rock", 2.5),
    ("classic rock", "rock", 2.5),
    ("alternative rock", "rock", 2.0),
    ("indie rock", "rock", 1.8),
    ("rock", "rock", 2.0),
    ("metal", "metal", 2.5),
    ("heavy metal", "metal", 3.0),
    ("thrash", "metal", 2.8),
    ("death metal", "metal", 2.8),
    ("progressive metal", "metal", 2.5),
    ("pop", "pop", 1.8),
    ("dance", "pop", 1.0),
    ("edm", "pop", 0.8),
)

STYLE_LABELS: tuple[str, ...] = ("blues", "rock", "fingerstyle", "jazz", "country", "metal", "pop")

# Artist name substrings → style nudge (very coarse; complements genres).
ARTIST_STYLE_HINTS: tuple[tuple[str, str, float], ...] = (
    ("bb king", "blues", 2.0),
    ("stevie ray", "blues", 2.0),
    ("clapton", "blues", 1.2),
    ("metallica", "metal", 2.0),
    ("iron maiden", "metal", 2.0),
    ("pat metheny", "jazz", 2.0),
    ("wes montgomery", "jazz", 2.0),
    ("chet atkins", "fingerstyle", 2.0),
    ("tommy emmanuel", "fingerstyle", 2.0),
    ("merle travis", "country", 1.5),
    ("johnny cash", "country", 1.5),
    ("taylor swift", "pop", 0.8),
)
