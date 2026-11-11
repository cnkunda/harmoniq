"""Guitar-vocabulary event tokens for the W3 two-head student.

The solo head predicts a sequence of event tokens rather than raw MIDI
notes. The vocabulary is deliberately restricted to the physical guitar
range (E2-C7), so the model is structurally incapable of emitting notes
outside that range — the "guitar-vocabulary" property required by W3.

Encoding (frame-synchronous, MT3-style event stream)::

    BOS, [TIME_SHIFT]*, event, [event]*, ..., EOS

``TIME_SHIFT`` advances one 100 ms frame. An onset is two tokens
(``ONSET(pitch)`` followed by ``VELOCITY(bin)``); an offset is one token.

No GM program token exists: every event is guitar by construction, which
is the leakage-hardening mechanism described in the roadmap.
"""

from __future__ import annotations

from dataclasses import dataclass

# Standard-tuning guitar range, conservative (24 frets + a little headroom
# for bends / harmonics). Notes outside this range are dropped at target
# build time and can never be produced at inference time.
GUITAR_PITCH_MIN = 40  # E2
GUITAR_PITCH_MAX = 96  # C7
NUM_GUITAR_PITCHES = GUITAR_PITCH_MAX - GUITAR_PITCH_MIN + 1

# GM guitar family (programs 24-31). All teacher notes outside it are
# filtered out before tokenization.
GUITAR_PROGRAMS = tuple(range(24, 32))

NUM_VELOCITY_BINS = 8

# Special tokens
PAD = 0
BOS = 1
EOS = 2
TIME_SHIFT = 3

# Token blocks
ONSET_BASE = 4
OFFSET_BASE = ONSET_BASE + NUM_GUITAR_PITCHES
VELOCITY_BASE = OFFSET_BASE + NUM_GUITAR_PITCHES
VOCAB_SIZE = VELOCITY_BASE + NUM_VELOCITY_BINS


def in_guitar_range(pitch: int) -> bool:
    """Whether a MIDI pitch is inside the student's guitar vocabulary."""
    return GUITAR_PITCH_MIN <= int(pitch) <= GUITAR_PITCH_MAX


def onset_token(pitch: int) -> int:
    if not in_guitar_range(pitch):
        raise ValueError(f"pitch {pitch} outside guitar range")
    return ONSET_BASE + (int(pitch) - GUITAR_PITCH_MIN)


def offset_token(pitch: int) -> int:
    if not in_guitar_range(pitch):
        raise ValueError(f"pitch {pitch} outside guitar range")
    return OFFSET_BASE + (int(pitch) - GUITAR_PITCH_MIN)


def velocity_token(bin_index: int) -> int:
    if not 0 <= int(bin_index) < NUM_VELOCITY_BINS:
        raise ValueError(f"velocity bin {bin_index} out of range")
    return VELOCITY_BASE + int(bin_index)


def is_onset(token: int) -> bool:
    return ONSET_BASE <= token < OFFSET_BASE


def is_offset(token: int) -> bool:
    return OFFSET_BASE <= token < VELOCITY_BASE


def is_velocity(token: int) -> bool:
    return VELOCITY_BASE <= token < VOCAB_SIZE


def token_pitch(token: int) -> int:
    if is_onset(token):
        return GUITAR_PITCH_MIN + (token - ONSET_BASE)
    if is_offset(token):
        return GUITAR_PITCH_MIN + (token - OFFSET_BASE)
    raise ValueError(f"token {token} does not carry a pitch")


def velocity_bin(velocity: int | None) -> int:
    """Map a MIDI velocity (0-127) to ``NUM_VELOCITY_BINS`` buckets."""
    value = 64 if velocity is None else max(0, min(127, int(velocity)))
    return min(NUM_VELOCITY_BINS - 1, (value * NUM_VELOCITY_BINS) // 128)


def velocity_from_bin(bin_index: int) -> int:
    """Return a representative MIDI velocity for a bucket."""
    bin_index = max(0, min(NUM_VELOCITY_BINS - 1, int(bin_index)))
    return int(((bin_index + 0.5) * 128) / NUM_VELOCITY_BINS)


@dataclass(frozen=True)
class DecodedNote:
    """A note recovered from a token sequence."""

    pitch: int
    onset: float
    offset: float
    velocity: int


def decode_tokens(
    tokens: list[int] | tuple[int, ...],
    *,
    window_start_s: float = 0.0,
    frame_hop_s: float = 0.1,
) -> list[DecodedNote]:
    """Decode an event token sequence into notes.

    Unclosed notes are closed at the final frame so malformed output is
    still visible rather than silently dropped.
    """
    frame = 0
    active: dict[int, tuple[float, int]] = {}
    pending_onset: int | None = None
    notes: list[DecodedNote] = []
    last_frame = 0

    def _close(pitch: int, end_time: float) -> None:
        value = active.pop(pitch, None)
        if value is None:
            return
        start, velocity = value
        notes.append(
            DecodedNote(
                pitch=pitch,
                onset=start,
                offset=max(end_time, start + frame_hop_s),
                velocity=velocity,
            )
        )

    for token in tokens:
        token = int(token)
        if token == EOS:
            break
        if token == PAD or token == BOS:
            continue
        if token == TIME_SHIFT:
            frame += 1
            last_frame = max(last_frame, frame)
            continue
        if is_onset(token):
            pitch = token_pitch(token)
            if pitch in active:
                _close(pitch, window_start_s + frame * frame_hop_s)
            pending_onset = pitch
            last_frame = max(last_frame, frame)
            continue
        if is_velocity(token):
            if pending_onset is not None:
                velocity = velocity_from_bin(token - VELOCITY_BASE)
                active[pending_onset] = (
                    window_start_s + frame * frame_hop_s,
                    velocity,
                )
                pending_onset = None
            last_frame = max(last_frame, frame)
            continue
        if is_offset(token):
            pitch = token_pitch(token)
            _close(pitch, window_start_s + frame * frame_hop_s)
            last_frame = max(last_frame, frame)
            continue
        raise ValueError(f"unknown token id: {token}")

    end_time = window_start_s + (last_frame + 1) * frame_hop_s
    for pitch in list(active):
        _close(pitch, end_time)

    return sorted(notes, key=lambda note: (note.onset, note.pitch, note.offset))
