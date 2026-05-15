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

#### Checkpoint: Analyze polling sanity check (BUG-01)

After submitting a YouTube URL for analysis:
- Open browser DevTools Network tab
- Confirm GET /analyze/{id} fires at most every 2–5 seconds (backoff)
- Confirm polling stops **immediately** when status shows "complete" — zero additional requests after terminal status
- FAIL if you see more than 10 requests before the ML pipeline starts (resampy/TF load is visible in the terminal)
- FAIL if any `/analyze/{id}` request fires after status transitions to `complete` or `failed` (verifies `seenCompletedOrFailed` guard — see `src/api/analyze.ts:381`)

---

### Step 2: Listen (Step 1 of 5)

1. After analysis completes, tap **Continue to session**
2. On the **Listen** screen:
   - **Playback card**: Confirm audio plays smoothly, timeline scrubber works
   - **Metronome card**: Confirm beats are audible when enabled, subdivision chips work
   - **Stems card**: Confirm stem mute/solo toggles work for each instrument
3. Tap **Watch How It's Played** button
4. Confirm modal opens with video placeholder and play button
5. Confirm orient annotation text is displayed
6. Close the modal

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

## Phase 1 E2E Completion Summary

All Phase 1 commit acceptance criteria (commits 1–97) are exercised by the above checkpoints:

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

## Known Limitations

- **Analysis timeout (>5 min)**: No push notification infrastructure. Jobs taking >5 min will timeout with a manual Retry button. Push notifications are deferred to post-Phase 1.
- **Tab catalog**: `GET /tabs/{id}/gp5` returns 501 until a licensed provider is configured.
- **Jam Mode AlphaTab**: May show "No tab available" if tab loading fails (expected until licensed provider).

---

## Regression Notes

When running E2E demos for regression testing:
- Use the same platform build, test song, and tempo for consistent comparisons
- Note any drift in AlphaTab sync timing or audio playback issues
- Report any crashes or unexpected error states
