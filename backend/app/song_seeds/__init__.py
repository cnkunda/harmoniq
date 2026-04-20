"""Curated per-style song title seeds for `TasteProfile.song_candidates` (commit 68)."""

from __future__ import annotations

# Minimum 3+ titles per style_label (PRIORITIES §68 acceptance).
SONG_CANDIDATES_BY_STYLE: dict[str, list[str]] = {
    "blues": [
        "Stevie Ray Vaughan — Pride and Joy",
        "B.B. King — The Thrill Is Gone",
        "Albert King — Born Under a Bad Sign",
        "Freddie King — Going Down",
        "Buddy Guy — Damn Right, I've Got the Blues",
    ],
    "rock": [
        "Led Zeppelin — Black Dog",
        "AC/DC — Back in Black",
        "Queen — Bohemian Rhapsody",
        "Foo Fighters — Everlong",
        "Deep Purple — Smoke on the Water",
    ],
    "fingerstyle": [
        "Tommy Emmanuel — Classical Gas",
        "Chet Atkins — Mr. Sandman",
        "Leo Kottke — Vaseline Machine Gun",
        "Michael Hedges — Aerial Boundaries",
        "Andy McKee — Drifting",
    ],
    "jazz": [
        "Miles Davis — So What",
        "John Coltrane — Giant Steps",
        "Wes Montgomery — Four on Six",
        "Herbie Hancock — Cantaloupe Island",
        "Pat Metheny — Bright Size Life",
    ],
    "country": [
        "Johnny Cash — Folsom Prison Blues",
        "Merle Haggard — Mama Tried",
        "Brad Paisley — Mud on the Tires",
        "Willie Nelson — On the Road Again",
        "Alison Krauss — When You Say Nothing at All",
    ],
    "metal": [
        "Metallica — Master of Puppets",
        "Iron Maiden — The Trooper",
        "Black Sabbath — Paranoid",
        "Megadeth — Tornado of Souls",
        "Judas Priest — Breaking the Law",
    ],
    "pop": [
        "Michael Jackson — Billie Jean",
        "Prince — Kiss",
        "Fleetwood Mac — The Chain",
        "The Weeknd — Blinding Lights",
        "Dua Lipa — Levitating",
    ],
}
