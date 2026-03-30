from __future__ import annotations

from app.transcribe import WordTimestamp, map_words_to_lyrics_aligned


def test_map_words_to_lyrics_aligned_snaps_to_nearest_beat():
    beat_grid = [0.0, 0.5, 1.0, 1.5]
    bar_timestamps = [0.0]  # 4/4, one bar in this toy grid
    _ = bar_timestamps  # mapping uses beat_grid; bar_timestamps is reserved for future

    words = [
        WordTimestamp(word="hello", start_s=0.49),  # nearest beat is 0.5
        WordTimestamp(word="world", start_s=0.10),  # nearest beat is 0.0 but regresses
    ]

    out = map_words_to_lyrics_aligned(words, beat_grid=beat_grid)

    # "world" should be skipped to keep non-regressing time_seconds.
    assert len(out) == 1
    assert out[0]["word"] == "hello"
    assert out[0]["time_seconds"] == 0.5
    assert out[0]["bar"] == 0
    assert out[0]["beat"] == 1


def test_map_words_to_lyrics_aligned_bar_and_beat_indexing():
    # 8 beats => 2 bars (4 beats per bar).
    beat_grid = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    words = [
        WordTimestamp(word="a", start_s=2.49),  # snap to 2.5 => beat idx 5 => bar 1 beat 1
        WordTimestamp(word="b", start_s=3.51),  # snap to 3.5 => beat idx 7 => bar 1 beat 3
    ]

    out = map_words_to_lyrics_aligned(words, beat_grid=beat_grid)
    assert len(out) == 2

    assert out[0]["bar"] == 1
    assert out[0]["beat"] == 1
    assert out[0]["time_seconds"] == 2.5

    assert out[1]["bar"] == 1
    assert out[1]["beat"] == 3
    assert out[1]["time_seconds"] == 3.5

