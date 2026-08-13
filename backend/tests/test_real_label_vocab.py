"""Vocabulary + annotation label mapping tests (Commit 101)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from real_label_vocab import (  # noqa: E402
    CHORD_CLASS_MAP,
    CHORD_INTERVALS,
    CHORD_VOCAB,
    NO_CHORD_IDX,
    NUM_CLASSES,
    QUALITY_GROUP_MASKS,
    QUALITY_GROUPS,
    ROOT_NOTES,
    annotation_to_class_index,
    nearest_quality,
    parse_annotation_label,
)


# ---------------------------------------------------------------------------
# Vocabulary structure
# ---------------------------------------------------------------------------


def test_vocab_is_23_qualities_x_12_roots_plus_no_chord():
    assert len(CHORD_INTERVALS) == 23
    assert NUM_CLASSES == 277
    assert CHORD_VOCAB[-1] == "N"
    assert CHORD_CLASS_MAP[-1] == (-1, "N")
    assert len(CHORD_VOCAB) == len(CHORD_CLASS_MAP) == NUM_CLASSES


def test_vocab_ordering_quality_major_root_minor():
    # Order is: for each quality (dict order), roots C..B
    assert CHORD_VOCAB[0] == "C:maj"
    assert CHORD_VOCAB[11] == "B:maj"
    assert CHORD_VOCAB[12] == "C:min"
    assert CHORD_VOCAB[14] == "D:min"
    assert CHORD_VOCAB[26] == "D:7"
    assert CHORD_VOCAB[57] == "A:min7"
    assert CHORD_VOCAB[276] == "N"


def test_class_map_covers_every_quality_root_combo():
    seen = {(root, quality) for root, quality in CHORD_CLASS_MAP[:-1]}
    expected = {
        (root, quality) for quality in CHORD_INTERVALS for root in range(12)
    }
    assert seen == expected


def test_quality_groups_partition_the_vocabulary():
    members = set()
    for group, mask in QUALITY_GROUP_MASKS.items():
        assert mask, f"group {group} is empty"
        members |= mask
        for idx in mask:
            assert CHORD_CLASS_MAP[idx][1] in QUALITY_GROUPS[group]
    assert members == set(range(NUM_CLASSES))


# ---------------------------------------------------------------------------
# Annotation label parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,expected",
    [
        ("C", (0, "maj")),
        ("G", (7, "maj")),
        ("D:maj", (2, "maj")),
        ("A:min7", (9, "min7")),
        ("Bb:7", (10, "7")),
        ("F#min7", (6, "min7")),
        ("Ebmaj7", (3, "maj7")),
        ("Bb:maj7", (10, "maj7")),
        ("Amaj9", (9, "maj9")),
        ("G/B", (7, "maj")),          # slash chords drop the bass note
        ("C:9(*3)", (0, "9")),         # omission hint resolves to plain 9
        ("E:hdim7", (4, "dim")),       # half-diminished -> closest class
        ("D:7(#9)", (2, "7#9")),
        ("C:sus4(b7)", (0, "7sus4")),
        ("G:7sus4", (7, "7sus4")),
        ("Ab:alt7", (8, "alt7")),
        ("A:dim7", (9, "dim7")),
        ("C:(3,5,b7,b9)", (0, "7b9")),
    ],
)
def test_parse_annotation_label(label, expected):
    assert parse_annotation_label(label) == expected


@pytest.mark.parametrize(
    "label",
    ["N", "NC", "n", "verse", "intro", "silence", "", "   ", "section_x"],
)
def test_no_chord_and_section_labels_resolve_to_none(label):
    assert parse_annotation_label(label) is None
    assert annotation_to_class_index(label) == NO_CHORD_IDX


def test_annotation_class_index_matches_map():
    for label, (root, quality) in [
        ("C", (0, "maj")),
        ("A:min7", (9, "min7")),
        ("Ab:alt7", (8, "alt7")),
    ]:
        idx = annotation_to_class_index(label)
        assert CHORD_CLASS_MAP[idx] == (root, quality)


def test_nearest_quality_prefers_exact():
    assert nearest_quality({0, 4, 7}) == "maj"
    assert nearest_quality({0, 3, 6}) == "dim"
    assert nearest_quality({0, 4, 7, 10}) == "7"
    assert nearest_quality({0, 5, 7, 10}) == "7sus4"