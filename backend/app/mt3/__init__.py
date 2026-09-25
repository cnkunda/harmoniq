"""MT3-Primary AMT Pipeline (Phase 2, Milestone A).

Google's Multi-Task Multitrack Transformer as the primary transcription engine.
Produces both chord timeline and solo notes simultaneously from a single
inference pass on the guitar stem.

Fallback chain: MT3 → CRNN TFLite → Chroma template matching.
"""

from __future__ import annotations

from app.mt3.schemas import Mt3Event, Mt3EventStream, TranscriptionSource
from app.mt3.model_server import Mt3ModelServer, mt3_infer
from app.mt3.chord_decoder import decode_events_to_chord_timeline
from app.mt3.solo_decoder import decode_events_to_solo_notes
from app.mt3.fallback import (
    TranscriptionResult,
    transcribe_with_fallback,
    get_transcription_source_label,
)

__all__ = [
    "Mt3Event",
    "Mt3EventStream",
    "TranscriptionSource",
    "Mt3ModelServer",
    "mt3_infer",
    "decode_events_to_chord_timeline",
    "decode_events_to_solo_notes",
    "TranscriptionResult",
    "transcribe_with_fallback",
    "get_transcription_source_label",
]
