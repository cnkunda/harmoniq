# E2E Demo — Harmoniq

End-to-end walkthrough for validating the core user flow: analyze a song, go through the 5-step session loop, and get coach feedback.

---

## Prerequisites

- Backend running: `cd backend && uvicorn app.main:app --reload`
- Frontend running: `npm start` (web) or `npx expo start` (native)
- Browser DevTools (web) or Flipper/Reactotron (native) for network/log inspection
- Test song ready: YouTube URL or audio file

---

## Core Flow: Analyze → Session Loop → Review

### Step 1: Analyze a song

1. Navigate to **Add Song** (web) or use the add song flow (native)
2. Paste a YouTube URL or upload an audio file
3. Tap **Analyze**
4. Wait for analysis to complete (typically 1–4 minutes)

#### Checkpoint: Analyze progress stream sanity check (BUG-01)

After submitting a song for analysis:
- Open browser DevTools Network tab, filter by `/analyze/`
- Expect exactly one `POST /analyze` and one `GET /analyze/{id}/stream` (EventStream) — no plain `GET /analyze/{id}` polling
- The stream stays open across the whole job; stage labels update live from pushed `status` events: `initializing` → `stems_separating` → `chords_inferring` → `mt3_inferring` → `building_musicxml` → `complete`
- On terminal status the client receives `complete` (or `failed`) and closes the stream — zero reconnects, zero further `/analyze` requests
- FAIL if more than 10 requests appear before the ML pipeline starts (resampy/TF load is visible in the terminal)
- FAIL if any plain `/analyze/{id}` request fires before or after terminal status, if the EventSource reconnects after terminal, or if the WebSocket fallback (`/analyze/{id}/ws`) opens while SSE is healthy

---

### Step 2: Listen (Step 1 of 5)

1. After analysis completes, tap **Continue to session**
2. On the **Listen** screen:
   - **Playback card**: Confirm audio plays smoothly, timeline scrubber works
   - **Metronome card**: Confirm beats are audible when enabled, subdivision chips work
   - **Beat grid editor**: Expand the beat grid panel — confirm timeline renders, BPM and time signature are editable
   - **Stems card**: Confirm stem mute/solo toggles work for each instrument
3. Tap **Watch How It's Played** button
4. Confirm modal opens with video placeholder and play button
5. Confirm orient annotation text is displayed
6. Close the modal

#### Checkpoint: Beat grid editor (commit 109)

1. In the Listen screen, expand the **Beat Grid** panel (below metronome controls)
2. Confirm the beat grid timeline renders with beat ticks, downbeat accents, and bar lines
3. Tap **+0.5** three times on the BPM editor → confirm BPM increases by 1.5 and timeline spacing adjusts in real-time
4. Tap **−5** → confirm BPM decreases by 5
5. Tap **Reset** → confirm BPM returns to the auto-detected value and the dirty indicator clears
6. Change the time signature to 3/4 → confirm timeline re-renders with 3 beats per bar
7. Change the time signature to 6/8 → confirm 6 beats per bar
8. Tap **Undo** → confirm previous state is restored
9. Tap **Redo** → confirm forward state is restored
10. Edit BPM, then tap **Apply** → confirm a progress bar appears; chord timeline, solo notes, and MusicXML all update when complete
11. FAIL if timeline does not update in real-time during BPM edits
12. FAIL if Apply does not trigger recompute or if chord/solo/MusicXML do not update

#### Checkpoint: Predictive UI rendering (commit 89)

During Listen playback with DevTools active:
- Confirm AlphaTab cursor highlights notes approximately **50ms before** audio reaches that position
- Confirm SmartScroll advances slightly ahead of the playback cursor
- FAIL if cursor appears to lag behind audio (indicates look-ahead buffer is not engaged)

---

### Step 3: Slow (Step 2 of 5)

1. Tap **Slow** in the session flow
2. Confirm playback slows to ~0.65×
3. Tap a section to create a loop
4. Confirm loop plays smoothly
5. Tap **Clear loop** to remove the loop
6. Confirm fretboard diagram is displayed between stems and tab

---

### Step 4: Study (Step 3 of 5)

1. Tap **Study** in the session flow
2. Tap a note on the score
3. Confirm SVG fretboard highlights the corresponding position
4. Confirm scale hints (if available) show appropriate notes
5. Confirm chord voicing circles display on the fretboard during playback

---

### Step 5: Play (Step 4 of 5)

1. Tap **Play** in the session flow
2. Grant microphone permissions (if prompted)
3. Play along with the backing track
4. Confirm fretboard shows hit/miss feedback rings during playback
5. After completing the section, tap **Finish**
6. Review your score and feedback

#### Checkpoint: Musical Tolerance scoring modes (commit 92)

Run this checkpoint twice, once per mode:
1. Before tapping **Play**, locate the scoring mode toggle (Expressive / Technique)
2. Set to **Expressive** mode:
   - Play with relaxed timing (±50–100ms tolerance)
   - Confirm scoring feedback acknowledges musical feel (not strict timing)
3. Set to **Technique** mode:
   - Play with precise timing (±20ms tolerance)
   - Confirm scoring feedback is stricter on timing accuracy
4. Confirm mode preference survives navigating away and back
5. FAIL if scoring feedback does not reflect the selected mode

---

### Step 6: Review (Step 5 of 5)

1. On the **Review** screen, confirm:
   - Phrasing visualizer shows user vs reference waveforms
   - Score breakdown is visible
   - Coach feedback is displayed
2. Tap **Do it again** to retry or continue to the next section

#### Checkpoint: Coach variation across sessions (commit 90)

1. Complete one full session through Play → Review on a song
2. Note the coach feedback focus area (e.g., Timing, Vibrato, Dynamics, Phrasing, Bending, Rhythm, Expression)
3. Start a **new** session on the **same** song and complete Play → Review again
4. Confirm the focus area differs from the first session
5. Repeat for a third session and verify a different focus area again
6. FAIL if the same focus area appears three times in a row

#### Checkpoint: Global Audio Manager & Seek-to-start sync (commits 87, 97)

1. After completing Review, tap **Do it again** once, play a section, then exit back to Home
2. Start a **new session on a different song** (or re-analyze if needed)
3. In the new session:
   - Confirm **no ghost tracks** — no audio from the previous song is audible
   - Confirm **no audio stutter or context bloat** — playback starts cleanly
   - Tap **Seek to start** — confirm cursor and audio sync within ~50ms
   - Toggle **tab variant** and **lyrics strip** — exit and re-enter to confirm preferences persisted (AsyncStorage)
4. FAIL if any audio from the first song persists (Global Audio Manager context not cleaned)
5. FAIL if Seek-to-start is visibly out of sync

#### Checkpoint: Cross-step Unified UX layout (commit 96)

1. Navigate through **Listen** → **Slow** → **Study** → **Play** in sequence
2. At each step, confirm:
   - Header, controls, and lyrics strip have consistent positioning
   - Tab variant toggle behaves identically across steps
   - Lyrics strip toggle does not cause layout shifting
3. FAIL if any step has noticeably different card padding, header alignment, or layout jump on toggle

---

## Chord Model & Transcription Quality (Commits 98-100)

### Checkpoint: Extended chord recognition (commit 98)

1. Analyze a jazz or blues song with known extended chords (e.g., "All of Me" with 7ths, "Autumn Leaves" with maj7/min7)
2. After analysis completes, navigate to the chord timeline in the session
3. Confirm extended chord symbols appear: D7, Cmaj7, Am7, G9, etc. (not just major/minor)
4. Confirm chord symbols match the expected harmony of the song
5. FAIL if only major/minor chords appear for a song with known extended harmony

### Checkpoint: Viterbi chord smoothing (commit 99)

1. Analyze a song with a known progression (e.g., ii-V-I in jazz)
2. Inspect the chord timeline for the progression section
3. Confirm:
   - Chord symbols transition smoothly (no rapid flickering between adjacent beats)
   - Chord changes land on beat boundaries (>90% alignment)
   - No improbable chord movements (e.g., C → F# → C in key of C major)
4. FAIL if chord symbols flicker rapidly (change every 1-2 beats)
5. FAIL if >10% of chord changes fall off beat boundaries

### Checkpoint: Half-beat chord resolution (commit 99)

1. Analyze a song with 8th-note chord changes (e.g., bossa nova, fast swing)
2. Inspect chord timeline at a section with rapid changes
3. Confirm two chord events are emitted per beat where appropriate
4. Confirm timestamps are correctly spaced at half-beat intervals
5. FAIL if rapid chord changes are collapsed into a single event

### Checkpoint: Segment boundary continuity — chords (commit 100)

1. Analyze a song longer than 30 seconds (triggers segmentation)
2. Identify a chord that spans a segment boundary (listen for sustained chord)
3. Inspect chord timeline at the boundary
4. Confirm:
   - The chord is emitted as a **single** event, not duplicated
   - No gap or silence in chord coverage at the boundary
   - Confidence is slightly reduced near the boundary (visible in dev mode)
5. FAIL if chord is duplicated or dropped at segment boundary

### Checkpoint: Segment boundary continuity — solo (commit 100)

1. Analyze a song with a sustained solo note crossing a segment boundary
2. Inspect the solo notation in the score (Study step or MusicXML export)
3. Confirm the note continues across the boundary without:
   - Duplicate note onset at boundary
   - Premature note offset at boundary
4. FAIL if note is split or dropped at segment boundary

---

## Analysis Persistence & Correction Editor (Commit 110)

### Checkpoint: Chord correction (backend)

1. After analysis completes, note the job_id from the response
2. `PATCH /analyze/{job_id}/chord/0` with body `{"chord": "F:maj"}`
3. Confirm response shows `original_chord` and `corrected_chord`
4. Confirm `chord_timeline.events[0].chord` is "F:maj" and `confidence` is 1.0
5. `GET /analyze/{job_id}/corrections` — confirm correction appears in history
6. FAIL if chord is not updated or confidence is not 1.0

### Checkpoint: Chord correction (frontend — Listen)

1. Navigate to the Listen screen after analysis
2. Locate the chord strip below the metronome card
3. Tap a chord symbol → chord correction modal opens
4. Confirm diatonic chords are shown (filtered by song key)
5. Tap "Show all chords…" → chromatic grid appears
6. Select a new chord → fretboard preview updates
7. Tap Confirm → chord strip updates with new chord
8. FAIL if modal does not open or chord does not update

### Checkpoint: Chord correction (frontend — Study)

1. Navigate to the Study screen
2. Tap a chord symbol in the chord sheet (ChordsAndLyrics)
3. Confirm chord correction modal opens with the tapped chord
4. Select a diatonic chord → confirm → chord sheet updates
5. FAIL if chord sheet does not reflect the correction

### Checkpoint: Note correction (frontend)

1. Navigate to the Study screen with a song that has solo notes
2. During playback, tap a red note on the fretboard
3. Note correction panel opens with pitch, string, fret, duration
4. Tap +1 on pitch stepper → pitch increments by 1 semitone
5. Tap a different string chip → fret auto-updates
6. Tap Confirm → note updates on fretboard
7. FAIL if panel does not open or note does not update

### Checkpoint: Correction persistence

1. Apply a chord correction in the Listen screen
2. Navigate away from the session (back to Home)
3. Re-enter the session → chord correction is still applied
4. FAIL if correction is lost on navigation

### Checkpoint: Correction history & revert

1. Apply 2-3 corrections (chord + note)
2. Open the CorrectionHistory component (if visible)
3. Confirm each correction is listed with original → corrected
4. Tap Revert on one correction → it is removed, lesson reverts
5. FAIL if revert does not restore original value

### Checkpoint: Correction metrics

1. After applying corrections, check lesson metadata
2. Confirm `correction_count` matches the number of corrections
3. Confirm `correction_coverage` is > 0 and <= 1.0
4. FAIL if metrics are missing or incorrect

---

## Jam Mode

### Checkpoint: Jam Mode happy path (offline / bundled) — BUG-02 resolved

1. Navigate to Jam Mode with no GEMINI_API_KEY set (bundled loop fallback)
2. Select "A minor · Blues shuffle" backing track
3. Tap Start Jamming
4. Confirm:
   - Backing track plays
   - Fretboard Position Map shows dots
   - Reference Score section does NOT show an error
   - AlphaTab tab renders without crash
5. FAIL if "Invalid typed array length", blank black canvas, or "No tab available" appears
6. Repeat with a second backing track to confirm no crash on switch

---

## Onboarding Placement

1. Complete the onboarding flow if prompted
2. Play the 3 placement phrases
3. Confirm:
   - AlphaTab snippets load without errors
   - Skill graph shows **real scores** from placement (not mock data)
   - Placement confidence is displayed when applicable
4. FAIL if skill graph shows placeholder/default values

---

## Phase 1 & 2 E2E Completion Summary

All Phase 1 commit acceptance criteria (commits 1-97) are exercised by the above checkpoints. Commits 98-100 (chord model expansion, Viterbi decoding, boundary tie) have dedicated checkpoints in the [Chord Model & Transcription Quality](#chord-model--transcription-quality-commits-98-100) section. Commit 109 (beat grid editor) has dedicated checkpoints in the [Beat Grid Editor](#checkpoint-beat-grid-editor-commit-109) section. Commit 110 (correction editor) has dedicated checkpoints in the [Analysis Persistence & Correction Editor](#analysis-persistence--correction-editor-commit-110) section.

| Commit | Feature | Checkpoint |
|--------|---------|------------|
| 86 | Placement session logic | Onboarding Placement |
| 87 | Global Audio Manager | Global Audio Manager & Seek-to-start |
| 88 | Versioned database migrations | (handled by automated test suite) |
| 89 | Predictive UI rendering | Predictive UI rendering |
| 90 | AI Coach variation agents | Coach variation across sessions |
| 91 | Harmonic similarity discovery | See [MANUAL_QA.md](./MANUAL_QA.md) regression smokes |
| 92 | Musical Tolerance scoring modes | Musical Tolerance scoring modes |
| 93 | Backend API modularization | (implicit — all API routes work) |
| 94 | Automated job data cleanup | (backend startup behavior) |
| 95 | ML inference stability & diagnostics | (backend — no model warnings in logs) |
| 96 | Unified Player UX parity | Cross-step Unified UX layout |
| 97 | Orient-as-hint / AsyncStorage / seek sync | Global Audio Manager & Seek-to-start |
| 98 | Advanced Extension Recognition | Extended chord recognition |
| 98a-d | Chord model architecture (CQT, CRNN, Attention) | (backend — chord accuracy metrics) |
| 99 | Viterbi Decoding | Viterbi chord smoothing + half-beat resolution |
| 100 | Segment Boundary Tie | Segment boundary continuity — chords + solo |
| 109 | Beat Grid Editor | Beat grid editor (timeline, BPM, time sig, recompute) |
| 110 | Correction Editor | Chord/note/voicing correction + persistence + history |

## Known Limitations

- **Analysis timeout (>5 min)**: No push notification infrastructure. Jobs taking >5 min will timeout with a manual Retry button. Push notifications are deferred to post-Phase 1.
- **Tab catalog**: `GET /tabs/{id}/gp5` returns 501 until a licensed provider is configured.
- **Jam Mode AlphaTab**: May show "No tab available" if tab loading fails (expected until licensed provider).
- **Chord model on-device**: TFLite model with SELECT_TF_OPS requires Flex delegate on Android for BiLSTM + attention layers (commit 106 — INT8 conversion uses `TFLITE_BUILTINS_INT8` + `SELECT_TF_OPS`; 98c is archived/superseded).
- **Beat grid editor persistence**: ✅ Resolved (commit 110). Overrides persist via `app_prefs` key-value store.
- **Beat grid editor scope**: Single-section editing only. Variable BPM per section is deferred to commit 140.
- **Correction MusicXML sync**: Backend endpoints rebuild MusicXML after corrections, but frontend-applied corrections do not automatically trigger MusicXML re-export (follow-up).
- **Voicing overrides (frontend)**: Backend endpoint exists but frontend VoicingSelector UI is not yet wired into session screens (follow-up).

---

## Regression Notes

When running E2E demos for regression testing:
- Use the same platform build, test song, and tempo for consistent comparisons
- Note any drift in AlphaTab sync timing or audio playback issues
- Report any crashes or unexpected error states
