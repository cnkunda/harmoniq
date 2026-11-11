"""Target construction for the W3 two-head student.

Two target types are built from a CQT window:

- **Framewise chords** — a 277-class label per 100 ms frame, derived from
  chord intervals (teacher labels or ground truth).
- **Solo event tokens** — a frame-synchronous MT3-style token stream,
  restricted to the guitar vocabulary and guitar-range pitches.

The builder is pure NumPy so it can be unit-tested without TensorFlow or
audio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from app.chord_vocab import CHORD_TO_IDX, NUM_CLASSES
from app.cqt_constants import HOP_SEC, WINDOW
from app.student import vocab

NO_CHORD_INDEX = NUM_CLASSES - 1  # 276
MAX_TOKEN_SEQUENCE = 384
NUM_ROOT_CLASSES = 13  # 12 pitch classes + N
NO_ROOT_INDEX = NUM_ROOT_CLASSES - 1


@dataclass(frozen=True)
class ChordSpan:
    """A chord covering a half-open interval in seconds."""

    start: float
    end: float
    chord: str


@dataclass(frozen=True)
class TargetNote:
    """A note used to build solo token targets."""

    pitch: int
    onset: float
    offset: float
    velocity: int = 80
    program: int | None = 24

    @property
    def duration(self) -> float:
        return max(0.0, self.offset - self.onset)


@dataclass(frozen=True)
class SoloTokenTarget:
    """Token targets for one window."""

    tokens: np.ndarray
    frame_indices: np.ndarray
    dropped_out_of_range: int = 0
    dropped_non_guitar: int = 0
    truncated: bool = False


def spans_from_dicts(items: Iterable[dict]) -> list[ChordSpan]:
    """Convert ``{start, end, chord}`` dicts to :class:`ChordSpan`."""
    spans: list[ChordSpan] = []
    for item in items:
        start = float(item["start"])
        end = float(item.get("end", start))
        if end <= start:
            continue
        spans.append(ChordSpan(start=start, end=end, chord=str(item["chord"])))
    return sorted(spans, key=lambda span: (span.start, span.end))


def notes_from_dicts(items: Iterable[dict]) -> list[TargetNote]:
    """Convert teacher note dicts to :class:`TargetNote`."""
    notes: list[TargetNote] = []
    for item in items:
        start = float(item["start_time"])
        duration = float(item.get("duration", 0.0))
        notes.append(
            TargetNote(
                pitch=int(item["pitch"]),
                onset=start,
                offset=start + max(duration, HOP_SEC),
                velocity=int(item.get("velocity", 80)),
                program=(
                    int(item["program"]) if item.get("program") is not None else 24
                ),
            )
        )
    return notes


def window_start(center_time_s: float, *, window: int = WINDOW,
                 hop_s: float = HOP_SEC) -> float:
    """Absolute start time of a window centred on ``center_time_s``."""
    return float(center_time_s) - (window // 2) * hop_s


def derive_root_labels(chord_labels: np.ndarray) -> np.ndarray:
    """Map framewise 277-class chord labels to 13-class root labels.

    The 277-class vocabulary is ``(quality, root)`` with index
    ``quality * 12 + root`` and ``N`` as the final class; the root is
    therefore ``index % 12`` (and ``NO_ROOT_INDEX`` for N).
    """
    labels = np.asarray(chord_labels, dtype=np.int32)
    roots = labels % 12
    roots = np.where(labels == NO_CHORD_INDEX, NO_ROOT_INDEX, roots)
    return roots.astype(np.int32)


def build_chord_frame_labels(
    spans: Sequence[ChordSpan],
    center_time_s: float,
    *,
    window: int = WINDOW,
    hop_s: float = HOP_SEC,
) -> np.ndarray:
    """Return ``(window,)`` 277-class chord indices for one window."""
    start = window_start(center_time_s, window=window, hop_s=hop_s)
    labels = np.full(window, NO_CHORD_INDEX, dtype=np.int32)
    if not spans:
        return labels

    ordered = sorted(spans, key=lambda span: span.start)
    for index in range(window):
        time_s = start + index * hop_s
        label = NO_CHORD_INDEX
        for span in ordered:
            if span.start <= time_s < span.end:
                label = CHORD_TO_IDX.get(span.chord, NO_CHORD_INDEX)
                break
        labels[index] = label
    return labels


def build_solo_token_target(
    notes: Sequence[TargetNote],
    center_time_s: float,
    *,
    window: int = WINDOW,
    hop_s: float = HOP_SEC,
    max_tokens: int = MAX_TOKEN_SEQUENCE,
) -> SoloTokenTarget:
    """Build a frame-synchronous token stream for one window.

    Notes outside the guitar pitch range or GM guitar programs are dropped
    and counted. Events are ordered by frame, then onset-before-offset.
    """
    start = window_start(center_time_s, window=window, hop_s=hop_s)
    events: list[tuple[int, int, int, int]] = []
    dropped_range = 0
    dropped_program = 0

    for note in notes:
        if note.program is not None and int(note.program) not in vocab.GUITAR_PROGRAMS:
            dropped_program += 1
            continue
        if not vocab.in_guitar_range(note.pitch):
            dropped_range += 1
            continue

        onset_frame = int(round((note.onset - start) / hop_s))
        offset_frame = int(round((note.offset - start) / hop_s))
        if 0 <= onset_frame < window:
            events.append(
                (
                    onset_frame,
                    0,
                    vocab.onset_token(note.pitch),
                    vocab.velocity_token(vocab.velocity_bin(note.velocity)),
                )
            )
        if 0 <= offset_frame < window:
            events.append((offset_frame, 1, vocab.offset_token(note.pitch), -1))

    events.sort(key=lambda item: (item[0], item[1], item[2]))

    tokens: list[int] = [vocab.BOS]
    frame_indices: list[int] = [0]
    current_frame = 0
    truncated = False

    for frame, _order, first_token, second_token in events:
        while current_frame < frame:
            if len(tokens) + 2 >= max_tokens:
                truncated = True
                break
            tokens.append(vocab.TIME_SHIFT)
            frame_indices.append(current_frame)
            current_frame += 1
        if truncated:
            break
        tokens.append(first_token)
        frame_indices.append(current_frame)
        if second_token >= 0:
            tokens.append(second_token)
            frame_indices.append(current_frame)

    if len(tokens) < max_tokens:
        tokens.append(vocab.EOS)
        frame_indices.append(current_frame)
    else:
        truncated = True

    tokens_arr = np.asarray(tokens[:max_tokens], dtype=np.int32)
    frames_arr = np.asarray(frame_indices[:max_tokens], dtype=np.int32)
    return SoloTokenTarget(
        tokens=tokens_arr,
        frame_indices=frames_arr,
        dropped_out_of_range=dropped_range,
        dropped_non_guitar=dropped_program,
        truncated=truncated,
    )


def pad_token_batch(
    targets: Sequence[SoloTokenTarget],
    *,
    max_tokens: int = MAX_TOKEN_SEQUENCE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pad token targets into ``(tokens, frames, mask)`` arrays.

    ``tokens`` and ``frames`` are right-padded with ``PAD`` / ``0``;
    ``mask`` is 1 for real positions (including BOS/EOS).
    """
    batch = len(targets)
    tokens = np.zeros((batch, max_tokens), dtype=np.int32)
    frames = np.zeros((batch, max_tokens), dtype=np.int32)
    mask = np.zeros((batch, max_tokens), dtype=np.float32)
    for row, target in enumerate(targets):
        length = min(len(target.tokens), max_tokens)
        tokens[row, :length] = target.tokens[:length]
        frames[row, :length] = target.frame_indices[:length]
        mask[row, :length] = 1.0
    return tokens, frames, mask


def shift_decoder_inputs(tokens: np.ndarray) -> np.ndarray:
    """Shift token ids right for teacher forcing (prepend BOS)."""
    shifted = np.full_like(tokens, vocab.PAD)
    shifted[:, 1:] = tokens[:, :-1]
    shifted[:, 0] = vocab.BOS
    return shifted
