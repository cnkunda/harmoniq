"""MusicFM / MIROS teacher placeholder.

MusicFM is a self-supervised encoder, not a standalone transcriber. Using it
as a teacher requires a decoder head (the 2025 AI4Musicians winner MIROS pairs
MusicFM with YourMT3+-style decoders) and weights whose licence is not
declared. W2 records this as an explicit blocker instead of pretending the
encoder is a teacher.
"""

from __future__ import annotations

from pathlib import Path

from app.teachers.events import TeacherOutput, TeacherUnavailable


class MusicFmTeacher:
    name = "musicfm"
    display_name = "MusicFM encoder (MIROS decoder required)"

    def is_available(self) -> bool:
        return False

    def unavailable_reason(self) -> str:
        return (
            "MusicFM is an encoder, not a transcriber; the MIROS/YourMT3 "
            "decoder and its weights are required, and the MIROS weight licence "
            "is not declared. Deferred until a licensed checkpoint is provided."
        )

    def transcribe(self, audio_path: Path) -> TeacherOutput:
        raise TeacherUnavailable(self.unavailable_reason())

    def transcribe_many(self, audio_paths: list[Path]) -> dict[Path, TeacherOutput]:
        raise TeacherUnavailable(self.unavailable_reason())
