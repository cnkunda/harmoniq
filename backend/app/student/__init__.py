"""W3 two-head student: shared encoder, chord frames, guitar solo tokens.

TensorFlow is only imported by :mod:`app.student.model` and
:mod:`app.student.inference`; importing this package is dependency-light so
the vocabulary and target builders can be tested without TF.
"""

from app.student.targets import (
    ChordSpan,
    SoloTokenTarget,
    TargetNote,
    build_chord_frame_labels,
    build_solo_token_target,
    derive_root_labels,
    notes_from_dicts,
    pad_token_batch,
    shift_decoder_inputs,
    spans_from_dicts,
)
from app.student.vocab import (
    BOS,
    EOS,
    GUITAR_PITCH_MAX,
    GUITAR_PITCH_MIN,
    GUITAR_PROGRAMS,
    PAD,
    TIME_SHIFT,
    VOCAB_SIZE,
    DecodedNote,
    decode_tokens,
    in_guitar_range,
    onset_token,
    offset_token,
    velocity_bin,
)

__all__ = [
    "BOS",
    "ChordSpan",
    "DecodedNote",
    "EOS",
    "GUITAR_PITCH_MAX",
    "GUITAR_PITCH_MIN",
    "GUITAR_PROGRAMS",
    "PAD",
    "SoloTokenTarget",
    "TIME_SHIFT",
    "TargetNote",
    "VOCAB_SIZE",
    "build_chord_frame_labels",
    "build_solo_token_target",
    "derive_root_labels",
    "decode_tokens",
    "in_guitar_range",
    "notes_from_dicts",
    "onset_token",
    "offset_token",
    "pad_token_batch",
    "shift_decoder_inputs",
    "spans_from_dicts",
    "velocity_bin",
]
