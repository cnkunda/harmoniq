"""Tests for Commit 106: Solo Rhythm Quantization (app.rhythm_quantization).

Pure-function tests: tick math, seconds→quarter-length quantization
(plain ticks + tuplet positions), note-type inference (dots, tuplets),
grid snapping, and measure splitting.
"""

from __future__ import annotations

from fractions import Fraction

from app.rhythm_quantization import (
    nearest_grid_index,
    quantize_seconds_to_ql,
    quantize_to_note_type,
    split_note_into_measures,
    tick_to_quarter_fraction,
)

# --- tick math ---


def test_tick_to_quarter_fraction():
    assert tick_to_quarter_fraction(0.25) == Fraction(1, 4)
    assert tick_to_quarter_fraction(0.5) == Fraction(1, 2)
    assert tick_to_quarter_fraction(0.125) == Fraction(1, 8)
    assert tick_to_quarter_fraction(0.1) == Fraction(1, 10)


def test_quantize_seconds_to_ql_plain_ticks():
    # 120 BPM → quarter = 0.5 s; tick = 1/4 quarter (16th-note grid)
    quarter, tick = 0.5, Fraction(1, 4)
    assert quantize_seconds_to_ql(0.125, quarter, tick) == Fraction(1, 4)  # 16th
    assert quantize_seconds_to_ql(0.375, quarter, tick) == Fraction(3, 4)  # dotted quarter
    assert quantize_seconds_to_ql(0.5, quarter, tick) == Fraction(1)       # quarter
    assert quantize_seconds_to_ql(0.49, quarter, tick) == Fraction(1)      # rounds to tick
    assert quantize_seconds_to_ql(0.52, quarter, tick) == Fraction(1)      # 4+ ticks → 1.0


def test_quantize_seconds_to_ql_tuplet_positions():
    quarter, tick = 0.5, Fraction(1, 4)
    # Triplet eighth = 1/3 quarter = 1/6 s — not on the plain 16th grid
    assert quantize_seconds_to_ql(1 / 6, quarter, tick) == Fraction(1, 3)
    # Triplet quarter = 2/3 quarter = 1/3 s
    assert quantize_seconds_to_ql(1 / 3, quarter, tick) == Fraction(2, 3)
    # 5-in-4 quarter = 4/5 quarter = 0.4 s
    assert quantize_seconds_to_ql(0.4, quarter, tick) == Fraction(4, 5)
    # Plain-grid durations still win over tuplet candidates
    assert quantize_seconds_to_ql(0.25, quarter, tick) == Fraction(1, 2)


def test_quantize_seconds_to_ql_syncopation():
    quarter, tick = 0.5, Fraction(1, 4)
    # Offbeat / syncopated attacks land on sub-beat ticks (dotted-quarter
    # syncopation, eighth off-beat) instead of snapping to beat centers.
    assert quantize_seconds_to_ql(0.375, quarter, tick) == Fraction(3, 4)
    assert quantize_seconds_to_ql(0.125 + 0.5, quarter, tick) == Fraction(5, 4)
    # Half-beat rollover picks the nearest tick (0.49s → the 1.0 ql tick)
    assert quantize_seconds_to_ql(0.49, quarter, tick) == Fraction(1)


def test_quantize_seconds_to_ql_invalid_inputs():
    assert quantize_seconds_to_ql(0.125, 0.0, Fraction(1, 4)) == Fraction(0)
    assert quantize_seconds_to_ql(0.125, 0.5, Fraction(0)) == Fraction(0)


# --- note-type inference ---


def test_quantize_to_note_type_plain():
    cases = {
        Fraction(1, 16): ("64th", 0, None),
        Fraction(1, 8): ("32nd", 0, None),
        Fraction(1, 4): ("16th", 0, None),
        Fraction(1, 2): ("eighth", 0, None),
        Fraction(1): ("quarter", 0, None),
        Fraction(2): ("half", 0, None),
        Fraction(4): ("whole", 0, None),
    }
    for ql, (name, dots, tuplet) in cases.items():
        dur = quantize_to_note_type(ql)
        assert dur is not None
        assert dur.type == name
        assert dur.dots == dots
        assert dur.tuplet == tuplet
        assert dur.quarter_length == ql


def test_quantize_to_note_type_dotted():
    dur = quantize_to_note_type(Fraction(3, 4))  # dotted eighth
    assert dur.type == "eighth"
    assert dur.dots == 1
    assert dur.tuplet is None

    dur = quantize_to_note_type(Fraction(3, 2))  # dotted quarter
    assert dur.type == "quarter"
    assert dur.dots == 1

    dur = quantize_to_note_type(Fraction(3, 8))  # dotted 16th
    assert dur.type == "16th"
    assert dur.dots == 1

    dur = quantize_to_note_type(Fraction(7, 8))  # double-dotted eighth
    assert dur.type == "eighth"
    assert dur.dots == 2


def test_quantize_to_note_type_tuplets():
    dur = quantize_to_note_type(Fraction(1, 3))
    assert dur.type == "eighth"
    assert dur.tuplet == (3, 2)  # triplet, not 6-in-4

    dur = quantize_to_note_type(Fraction(2, 3))
    assert dur.type == "quarter"
    assert dur.tuplet == (3, 2)

    dur = quantize_to_note_type(Fraction(4, 5))
    assert dur.type == "quarter"
    assert dur.tuplet == (5, 4)

    dur = quantize_to_note_type(Fraction(1, 6))
    assert dur.type == "16th"
    assert dur.tuplet == (3, 2)  # triplet 16th (simpler than 6-in-4)

    dur = quantize_to_note_type(Fraction(1, 12))
    assert dur.type == "32nd"
    assert dur.tuplet == (3, 2)


def test_quantize_to_note_type_tolerance():
    assert quantize_to_note_type(Fraction(24, 50)) is None  # no exact candidate
    dur = quantize_to_note_type(Fraction(24, 50), tolerance_ql=Fraction(1, 50))
    assert dur is not None
    assert dur.type == "eighth"  # 0.48 is closest to 1/2

    # Tolerance is strict: a slightly-off duration stays rejected
    assert quantize_to_note_type(Fraction(24, 50), tolerance_ql=Fraction(1, 100)) is None


def test_quantize_to_note_type_invalid():
    assert quantize_to_note_type(Fraction(0)) is None
    assert quantize_to_note_type(Fraction(-1)) is None
    assert quantize_to_note_type(None) is None  # type: ignore[arg-type]


# --- grid snapping ---


def test_nearest_grid_index():
    grid = [0.0, 0.5, 1.0]
    assert nearest_grid_index(0.49, grid) == 1
    assert nearest_grid_index(0.51, grid) == 1
    assert nearest_grid_index(0.01, grid) == 0
    assert nearest_grid_index(2.0, grid) == 2
    assert nearest_grid_index(0.5, grid) == 1
    assert nearest_grid_index(0.25, []) == 0


# --- measure splitting ---


def test_split_note_into_measures_within_measure():
    assert split_note_into_measures(Fraction(1, 2), Fraction(1), Fraction(4)) == [
        (Fraction(1, 2), Fraction(1))
    ]


def test_split_note_into_measures_crossing_barline():
    assert split_note_into_measures(Fraction(7, 2), Fraction(1), Fraction(4)) == [
        (Fraction(7, 2), Fraction(1, 2)),
        (Fraction(0), Fraction(1, 2)),
    ]


def test_split_note_into_measures_multiple_bars():
    assert split_note_into_measures(Fraction(1, 2), Fraction(8), Fraction(4)) == [
        (Fraction(1, 2), Fraction(7, 2)),
        (Fraction(0), Fraction(4)),
        (Fraction(0), Fraction(1, 2)),
    ]


def test_split_note_into_measures_compound_meter():
    # 3/4 measure: note starts at beat 2 of the first measure, spans 2.0 ql
    assert split_note_into_measures(Fraction(2), Fraction(2), Fraction(3)) == [
        (Fraction(2), Fraction(1)),
        (Fraction(0), Fraction(1)),
    ]


def test_split_note_into_measures_invalid():
    assert split_note_into_measures(Fraction(0), Fraction(0), Fraction(4)) == []
    assert split_note_into_measures(Fraction(1), Fraction(0), Fraction(4)) == []
    assert split_note_into_measures(Fraction(1), Fraction(1), Fraction(0)) == []