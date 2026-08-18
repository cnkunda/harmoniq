"""Generate the AlphaTab edge-case MusicXML corpus (Commit 107).

Produces deterministic MusicXML 3.1 Partwise files into
`tests/fixtures/musicxml-corpus/` covering the semantic edge cases the
AlphaTab importer must survive: irregular time signatures, nested tuplets,
polyrhythms, extreme tempo changes, multi-voice staves, syncopation, and
compound meters. The corpus is committed to the repo so CI renders it
without needing music21 at test time.

Usage:
    python scripts/generate_musicxml_corpus.py [--out DIR] [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# music21 is a heavy import; only needed at generation time.
import music21  # noqa: E402
from music21 import clef, duration as m21duration, key, meter, note, stream  # noqa: E402

CORPUS_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "musicxml-corpus"

# (id, title, builder) — builder(score) appends a part then returns it.
_CASES: list[tuple[str, str, callable]] = []


def _case(case_id: str, title: str):
    def register(fn):
        _CASES.append((case_id, title, fn))
        return fn
    return register


def _new_score(title: str) -> stream.Score:
    score = stream.Score()
    score.metadata = music21.metadata.Metadata()
    score.metadata.title = title
    return score


def _part(name: str = "Lead") -> stream.Part:
    part = stream.Part()
    part.partName = name
    part.id = "P1"
    return part


def _add_measure(part: stream.Part, number: int, ts: str | None = None,
                 ks: key.Key | None = None, notes=("quarter", "quarter", "quarter", "quarter")) -> None:
    m = stream.Measure(number=number)
    if ts:
        m.timeSignature = meter.TimeSignature(ts)
    if ks:
        m.keySignature = ks
    m.clef = clef.TrebleClef()
    for i, dur in enumerate(notes):
        if dur.startswith("dotted-"):
            base = dur[len("dotted-"):]
            n = note.Note(60 + (i % 7), type=base)
            n.duration.dots = 1
        else:
            n = note.Note(60 + (i % 7), type=dur)
        m.append(n)
    part.append(m)


@_case("irregular-5-4", "Irregular 5/4 meter")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    _add_measure(p, 1, "5/4", notes=("whole",))
    _add_measure(p, 2, "5/4", notes=("half", "quarter", "half"))
    _add_measure(p, 3, "5/4", notes=("eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth"))
    return p


@_case("irregular-7-8", "Irregular 7/8 meter")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    _add_measure(p, 1, "7/8", notes=("eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth"))
    _add_measure(p, 2, "7/8", notes=("half", "eighth", "eighth", "eighth"))
    _add_measure(p, 3, "7/8", notes=("quarter", "eighth", "quarter", "eighth"))
    return p


@_case("irregular-9-8-compound", "Compound 9/8 meter")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    _add_measure(p, 1, "9/8", notes=("eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth", "eighth"))
    _add_measure(p, 2, "9/8", notes=("quarter", "quarter", "quarter", "eighth", "eighth", "eighth"))
    _add_measure(p, 3, "9/8", notes=("dotted-quarter", "dotted-quarter", "dotted-quarter"))
    return p


@_case("meter-change-4-4-to-3-4", "Meter change 4/4 → 3/4 → 4/4")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    _add_measure(p, 1, "4/4")
    _add_measure(p, 2, "3/4", notes=("half", "quarter"))
    _add_measure(p, 3, "4/4")
    _add_measure(p, 4, "3/4", notes=("quarter", "quarter", "quarter"))
    return p


@_case("nested-tuplets", "Nested tuplets (triplet inside triplet)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    outer = m21duration.Tuplet(3, 2)
    for pitch in (60, 62, 64):
        inner = m21duration.Tuplet(3, 2)
        n = note.Note(pitch, type="eighth", tuplet=inner)
        n.duration.tuplets = [inner, outer]
        m1.append(n)
    m1.append(note.Note(67, type="half"))
    p.append(m1)
    return p


@_case("quintuplet-septuplet", "Quintuplet + septuplet")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    quint = m21duration.Tuplet(5, 4)
    for pitch in (60, 62, 64, 65, 67):
        n = note.Note(pitch, type="eighth", tuplet=quint)
        n.duration.tuplets = [quint]
        m1.append(n)
    m2 = stream.Measure(number=2)
    m2.timeSignature = meter.TimeSignature("4/4")
    sept = m21duration.Tuplet(7, 4)
    for pitch in (60, 61, 62, 63, 64, 65, 67):
        n = note.Note(pitch, type="eighth", tuplet=sept)
        n.duration.tuplets = [sept]
        m2.append(n)
    p.append(m1)
    p.append(m2)
    return p


@_case("polyrhythm-3-2", "Polyrhythm 3-over-2 (two voices)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    # Voice 1: three half-note triplets over two beats worth of dotted halves
    for pitch in (60, 64, 67):
        t = m21duration.Tuplet(3, 2)
        n = note.Note(pitch, type="quarter", tuplet=t)
        n.duration.tuplets = [t]
        n.voice = 1
        m1.insert(n)
    for pitch in (48, 55):
        n = note.Note(pitch, type="half")
        n.voice = 2
        m1.insert(n)
    p.append(m1)
    return p


@_case("polyrhythm-4-3", "Polyrhythm 4-over-3 (two voices)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    t4 = m21duration.Tuplet(4, 3)
    for pitch in (60, 62, 64, 67):
        n = note.Note(pitch, type="eighth", tuplet=t4)
        n.duration.tuplets = [t4]
        n.voice = 1
        m1.insert(n)
    t3 = m21duration.Tuplet(3, 2)
    for pitch in (48, 52, 55):
        n = note.Note(pitch, type="eighth", tuplet=t3)
        n.duration.tuplets = [t3]
        n.voice = 2
        m1.insert(n)
    p.append(m1)
    return p


@_case("tempo-change-60-to-240", "Extreme tempo change 60 → 240 BPM")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    for num, bpm in ((1, 60), (2, 240), (3, 30)):
        m = stream.Measure(number=num)
        m.timeSignature = meter.TimeSignature("4/4")
        m.clef = clef.TrebleClef()
        mm = music21.tempo.MetronomeMark(number=bpm)
        m.append(mm)
        m.append(note.Note(60 + num, type="quarter"))
        m.append(note.Note(64 + num, type="quarter"))
        m.append(note.Note(67 + num, type="half"))
        p.append(m)
    return p


@_case("multi-voice-staff", "Multi-voice staff (melody + harmony)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    for i, pitch in enumerate((72, 74, 76, 79)):
        n = note.Note(pitch, type="quarter")
        n.voice = 1
        m1.insert(n)
    for i, pitch in enumerate((60, 62, 64, 67)):
        n = note.Note(pitch, type="quarter")
        n.voice = 2
        m1.insert(n)
    for i, pitch in enumerate((48, 52, 55, 59)):
        n = note.Note(pitch, type="quarter")
        n.voice = 3
        m1.insert(n)
    p.append(m1)
    return p


@_case("syncopation", "Heavy syncopation (off-beat entrances)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    m1.append(note.Rest(type="eighth"))
    for pitch in (60, 62, 64, 65, 67, 69, 71):
        n = note.Note(pitch, type="eighth")
        m1.append(n)
    p.append(m1)
    return p


@_case("key-signature-fsharp-minor", "Key signature F# minor (3 sharps)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    ks = key.Key("F#", "minor")
    _add_measure(p, 1, "4/4", ks=ks, notes=("quarter", "quarter", "quarter", "quarter"))
    _add_measure(p, 2, "4/4", ks=ks, notes=("half", "quarter", "quarter"))
    return p


@_case("key-signature-eb-major", "Key signature Eb major (3 flats)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    ks = key.Key("E-", "major")
    _add_measure(p, 1, "4/4", ks=ks, notes=("quarter", "quarter", "quarter", "quarter"))
    _add_measure(p, 2, "4/4", ks=ks, notes=("half", "quarter", "quarter"))
    return p


@_case("accidentals-alter", "Accidentals (<alter> across octaves)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    for pitch, dur in ((60, "quarter"), (61, "quarter"), (63, "quarter"), (66, "quarter")):
        n = note.Note(pitch, type=dur)
        n.pitch.accidental = music21.pitch.Accidental("sharp")
        m1.append(n)
    m2 = stream.Measure(number=2)
    m2.timeSignature = meter.TimeSignature("4/4")
    for pitch, dur in ((60, "half"), (63, "half")):
        n = note.Note(pitch, type=dur)
        n.pitch.accidental = music21.pitch.Accidental("flat")
        m2.append(n)
    p.append(m1)
    p.append(m2)
    return p


@_case("ties-and-slurs", "Long ties + slurs across measures")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    n = note.Note(60, type="half")
    n.tie = music21.tie.Tie("start")
    m1.append(n)
    d4 = note.Note(62, type="half")
    m1.append(d4)
    m2 = stream.Measure(number=2)
    m2.timeSignature = meter.TimeSignature("4/4")
    n2 = note.Note(60, type="half")
    n2.tie = music21.tie.Tie("stop")
    m2.append(n2)
    e4 = note.Note(64, type="half")
    m2.append(e4)
    slur = music21.spanner.Slur()
    slur.addSpannedElements([d4, e4])
    p.append(m1)
    p.append(m2)
    p.append(slur)
    return p


@_case("dots-and-32nds", "Dotted rhythms + 32nd note runs")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    m1.append(note.Note(60, type="half", dots=1))
    m1.append(note.Note(64, type="eighth"))
    m2 = stream.Measure(number=2)
    m2.timeSignature = meter.TimeSignature("4/4")
    for i in range(16):
        m2.append(note.Note(60 + (i % 7), type="32nd"))
    p.append(m1)
    p.append(m2)
    return p


@_case("rest-heavy", "Rest-heavy phrase")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    m1.append(note.Rest(type="quarter"))
    m1.append(note.Note(60, type="quarter"))
    m1.append(note.Rest(type="eighth"))
    m1.append(note.Note(62, type="eighth"))
    m1.append(note.Note(64, type="half"))
    p.append(m1)
    return p


@_case("pickup-measure", "Pickup (anacrusis) measure")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m0 = stream.Measure(number=0)
    m0.timeSignature = meter.TimeSignature("4/4")
    m0.clef = clef.TrebleClef()
    m0.padAsAnacrusis = True
    m0.append(note.Note(67, type="eighth"))
    m0.append(note.Note(69, type="eighth"))
    p.append(m0)
    _add_measure(p, 1, "4/4")
    _add_measure(p, 2, "4/4")
    return p


@_case("wide-range-lead", "Wide pitch range (MIDI 36 → 96)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    for pitch, dur in ((36, "quarter"), (48, "quarter"), (60, "quarter"), (72, "quarter")):
        m1.append(note.Note(pitch, type=dur))
    m2 = stream.Measure(number=2)
    m2.timeSignature = meter.TimeSignature("4/4")
    for pitch, dur in ((84, "quarter"), (96, "quarter"), (60, "half")):
        m2.append(note.Note(pitch, type=dur))
    p.append(m1)
    p.append(m2)
    return p


@_case("single-note-score", "Minimal single-note score")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    m1.append(note.Note(60, type="whole"))
    p.append(m1)
    return p


@_case("empty-measure-rests", "Empty measures (full-measure rests)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    for num in (1, 2, 3):
        m = stream.Measure(number=num)
        m.timeSignature = meter.TimeSignature("4/4")
        m.clef = clef.TrebleClef()
        m.append(note.Rest(type="whole"))
        p.append(m)
    return p


@_case("multi-measure-rest", "Multi-measure rest (measure style)")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    m1.append(note.Note(60, type="quarter"))
    m1.append(note.Rest(type="half", dots=1))
    p.append(m1)
    _add_measure(p, 2, "4/4")
    return p


@_case("tuplet-across-beats", "Tuplet spanning beats")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    t = m21duration.Tuplet(3, 2)
    n = note.Note(60, type="half", tuplet=t)
    n.duration.tuplets = [t]
    n.duration.dots = 1
    m1.append(n)
    m1.append(note.Note(64, type="quarter"))
    p.append(m1)
    return p


@_case("grace-notes", "Grace notes")
def _(s: stream.Score) -> stream.Part:
    p = _part()
    m1 = stream.Measure(number=1)
    m1.timeSignature = meter.TimeSignature("4/4")
    m1.clef = clef.TrebleClef()
    g1 = note.Note(64)
    g1.duration = m21duration.GraceDuration()
    g2 = note.Note(62)
    g2.duration = m21duration.GraceDuration()
    main = note.Note(60, type="quarter")
    m1.append([g1, g2, main])
    m1.append(note.Note(62, type="quarter", dots=1))
    m1.append(note.Note(64, type="half"))
    p.append(m1)
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=CORPUS_DIR)
    parser.add_argument("--force", action="store_true", help="overwrite existing corpus files")
    args = parser.parse_args()

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("*.musicxml"))
    if existing and not args.force:
        print(f"corpus already exists ({len(existing)} files); pass --force to regenerate")
        return 0

    for case_id, title, builder in _CASES:
        score = _new_score(title)
        part = builder(score)
        score.append(part)
        dest = out_dir / f"{case_id}.musicxml"
        score.write(fp=dest, fmt="musicxml")
        print(f"wrote {dest.name} ({title})")

    print(f"\n{len(_CASES)} corpus files written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())