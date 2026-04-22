# E2E Demo — Harmoniq

End-to-end walkthrough for validating the core user flow: analyze a song, go through the 5-step session loop, and get coach feedback.

---

## Prerequisites

- Backend running: `cd backend && uvicorn app.main:app --reload`
- Frontend running: `npm start` (web) or `npx expo start` (native)
- Test song ready: YouTube URL or audio file

---

## Core Flow: Analyze → Session Loop → Review

### Step 1: Analyze a song

1. Navigate to **Add Song** (web) or use the add song flow (native)
2. Paste a YouTube URL or upload an audio file
3. Tap **Analyze**
4. Wait for analysis to complete (typically 1–4 minutes)

#### Checkpoint: Analyze polling sanity check

After submitting a YouTube URL for analysis:
- Open browser DevTools Network tab
- Confirm GET /analyze/{id} fires at most every 2–5 seconds (backoff)
- Confirm polling stops within one interval of the status indicator showing "complete" in the UI
- FAIL if you see more than 10 requests before the ML pipeline starts (resampy/TF load is visible in the terminal)

---

### Step 2: Listen (Step 1 of 5)

1. After analysis completes, tap **Continue to session**
2. On the **Listen** screen, tap **Play**
3. Confirm:
   - Audio plays smoothly
   - AlphaTab cursor advances in sync with audio
   - Metronome (if enabled) clicks on beat
   - Seeking works without crashes

---

### Step 3: Slow (Step 2 of 5)

1. Tap **Slow** in the session flow
2. Confirm playback slows to ~0.65×
3. Tap a section to create a loop
4. Confirm loop plays smoothly
5. Tap **Clear loop** to remove the loop

---

### Step 4: Study (Step 3 of 5)

1. Tap **Study** in the session flow
2. Tap a note on the score
3. Confirm fretboard highlights the corresponding position
4. Confirm scale hints (if available) show appropriate notes

---

### Step 5: Play (Step 4 of 5)

1. Tap **Play** in the session flow
2. Grant microphone permissions (if prompted)
3. Play along with the backing track
4. After completing the section, tap **Finish**
5. Review your score and feedback

---

### Step 6: Review (Step 5 of 5)

1. On the **Review** screen, confirm:
   - Phrasing visualizer shows user vs reference waveforms
   - Score breakdown is visible
   - Coach feedback is displayed
2. Tap **Do it again** to retry or continue to the next section

---

## Jam Mode

### Checkpoint: Jam Mode happy path (offline / bundled)

1. Navigate to Jam Mode with no GEMINI_API_KEY set (bundled loop fallback)
2. Select "A minor · Blues shuffle" backing track
3. Tap Start Jamming
4. Confirm:
   - Backing track plays
   - Fretboard Position Map shows dots
   - Reference Score section does NOT show an error
5. FAIL if "Invalid typed array length" or blank black canvas appears

---

## Onboarding Placement

1. Complete the onboarding flow if prompted
2. Play the 3 placement phrases
3. Confirm:
   - AlphaTab snippets load without errors
   - Skill graph shows results after completion
   - Placement confidence is displayed when applicable

---

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
