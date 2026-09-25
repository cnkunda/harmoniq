# Harmoniq — Priorities Archive

Completed commits moved from `PRIORITIES.md`.

---

## Commit 123: Solo Harmony Enrichment — Chord-Tone Classification & Position Inference

**Goal:** Post-process raw Basic Pitch solo notes through a harmony analysis layer that labels every note with its role in the current chord (root, 3rd, 5th, tension, chromatic) and infers the fretboard position (CAGED shape) per bar — making solo output "make sense" as a musical narrative, not just raw MIDI events.

**Current State:** Solo inference via Basic Pitch (`solo_inference.py:283`) runs independently of chord inference. The two outputs are stored as sibling fields in LessonJSON (`chord_timeline` vs `solo_notes`) with zero cross-referencing. A user sees "MIDI 59, 62, 64" instead of "B2, D3, E4 over G:maj7 — that's the 3rd and 5th of the chord resolving to the root." No position/CAGED inference exists — `guitar_position.py` only converts individual MIDI notes to string/fret for MusicXML rendering, with no per-bar shape awareness.

**Scope:**

- **New module: `backend/app/solo_harmony_analyzer.py`:**
  - `ChordToneClassifier`: takes chord `(root, quality)` + MIDI pitch → `{ scale_degree, scale_degree_name, chord_tone_type, semitone_distance }`
    - Parse chord string (e.g. `"G:maj7"`) into root pitch class + interval set using existing `chord_vocab.py`
    - Normalize MIDI pitch to pitch class (0–11)
    - Match against chord intervals → "chord_tone" (exact match), "tension" (in key via Krumhansl-Schmuckler root but not in chord), "chromatic" (outside key)
    - Return human-readable label: `"R"`, `"b3"`, `"3"`, `"5"`, `"b7"`, `"7"`, etc.
  - `PositionInferenceEngine`: given MIDI notes + chord + key → inferred CAGED position label
    - For each of 5 CAGED shapes of the current chord, check if played notes are reachable within a 4-fret span on adjacent strings
    - Score each shape: hit rate × span tightness
    - Winner → label like `"position 2 (CAGED: E-form)"`
    - Uses existing `guitar_position.py` for string/fret mapping
  - `SoloHarmonizer`: orchestrator — takes `ChordTimeline` + `SoloNotes` + `BeatGrid` + key
    - Per solo note: look up active chord from timeline, classify tone, attach context
    - Per bar: collect notes, infer position, suggest scale(s)
    - Aggregate into enriched output structures

- **New schemas in `backend/app/schemas.py`:**
  - `ChordToneAnalysis`: `{ scale_degree: int, scale_degree_name: str (e.g. "b7", "3"), chord_tone_type: Literal["chord_tone", "tension", "chromatic", "pedal"], semitone_distance: int }`
  - `BarScope`: `{ bar_index: int, start_time: float, end_time: float, chord: str | None, suggested_scales: list[str], primary_position: str | None, notes: list[int] }`
  - `HarmonizedSoloNotes`: `{ notes: list[ { start_time, duration, pitch, velocity, chord: str | None, chord_analysis: ChordToneAnalysis | None } ], note_count: int, chord_tone_pct: float, tension_note_pct: float, chromatic_pct: float }`

- **Add to `LessonJSON` schema:**
  - `harmonized_solo: HarmonizedSoloNotes | None = None`
  - `per_bar_analysis: list[BarScope] | None = None`
  - Both optional with `None` fallback (no regression when analysis is unavailable)

- **Pipeline integration in `backend/app/analyze_audio.py`:**
  - After both `infer_chords` and `infer_solo` complete (after line 287), call `SoloHarmonizer`:
    ```python
    harmonized_solo = None
    per_bar = None
    if chord_timeline and solo_notes and chord_timeline.events and solo_notes.notes:
        try:
            harmonizer = SoloHarmonizer(chord_timeline, solo_notes, beat_grid, summary.key_name)
            harmonized_solo = harmonizer.harmonized_solo
            per_bar = harmonizer.per_bar_analysis
        except Exception:
            logger.exception("solo harmony analysis failed for job_id=%s; skipping", job_id)
    ```
  - Pass into `LessonJSON` constructor
  - Falls back silently (no regression) when chords, solo, or key are unavailable

- **Frontend types in `src/types/soloHarmony.ts`:**
  - TypeScript mirrors of `ChordToneAnalysis`, `BarScope`, `HarmonizedSoloNotes`
  - `chord_tone_type` as `'chord_tone' | 'tension' | 'chromatic' | 'pedal'`

- **Tests in `backend/tests/test_solo_harmony_analyzer.py`:**
  - Pitch 60 (C4) against "C:maj" → root, scale_degree=1, chord_tone
  - Pitch 64 (E4) against "C:maj" → 3rd, scale_degree=3, chord_tone
  - Pitch 65 (F4) against "C:maj" → 4th, tension (in G major scale, not in C chord)
  - Pitch 66 (F#4) against "C:maj" → chromatic (outside key)
  - Position inference: known solo phrase against known chord → correct CAGED label
  - Edge: no chord at note time → chord_analysis = null
  - Edge: "N" (no-chord) beats → skip analysis
  - Edge: empty chord_timeline or solo_notes → graceful None return

**Not in scope (follow-up commits):**
- Frontend display of enriched data (Study fretboard overlay, Review feedback) — Commit 126 already covers theory overlay
- Claude coaching prompt changes to reference chord-tone data — belongs in coach prompt tuning
- Position inference refinement (beyond CAGED) — can be iterated later

**Acceptance Criteria:**

- [x] `ChordToneClassifier` correctly classifies a pitch against any of the 277 chord types
- [x] `PositionInferenceEngine` returns CAGED label for known solos with ≥70% accuracy
- [x] `SoloHarmonizer` runs silently after chord+solo inference; never blocks the pipeline
- [x] `HarmonizedSoloNotes` contains per-note chord context for every note with a matching chord
- [x] `per_bar_analysis` contains per-bar position inference for bars with active solo notes
- [x] Both fields are `None` when chord_timeline or solo_notes is empty (no regression)
- [x] All backend tests pass (`python -m pytest -q`)
- [x] No new dependencies required (uses existing `chord_vocab.py`, `guitar_position.py`, `schemas.py`)
- [x] Integration test: full song analysis → harmonized solo output with chord-tone percentages

**Files:**
- `backend/app/solo_harmony_analyzer.py` — ChordToneClassifier, PositionInferenceEngine, SoloHarmonizer
- `backend/app/schemas.py` — ChordToneAnalysis, HarmonizedSoloNote, HarmonizedSoloNotes, BarScope
- `backend/app/analyze_audio.py` — pipeline integration
- `src/types/soloHarmony.ts` — frontend type mirrors
- `backend/tests/test_solo_harmony_analyzer.py` — 50 tests, all passing
