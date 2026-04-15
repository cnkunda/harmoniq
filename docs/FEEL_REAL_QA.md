# Feel Real — Phase 5 manual QA gate

Fast **release sign-off** for Harmoniq **Phase 5** realism (sync, notation, sound, coach, practice UX). A second developer should complete this pass in **about 20–30 minutes** after the stack is running (see [E2E_DEMO.md](./E2E_DEMO.md) for cold start).

**Regression discipline:** Use the same **platform build**, **test song**, and **tempo** across runs when comparing results. Record the run metadata below so FAIL rows are reproducible.

| Field | Value |
|-------|--------|
| Date | |
| Runner | |
| App (web / iOS / Android + version) | |
| Backend rev (git SHA or tag) | |
| Test song (title + source) | |

---

## STOP rule — external media sync (Commit 45)

**If any check in Section A is `FAIL` and you do not have a linked issue plus written waiver, stop here.** Do not treat Phase 5 as shippable until sync matches Commit 45 acceptance criteria or the waiver is approved.

Commit 45 bar: **guitar stem audio** is the playback clock (`IExternalMediaHandler` / `PlayerMode.EnabledExternalMedia`); **no** timer-driven SmartScroll competing with the cursor.

---

## How to record results

For each row, set **Result** to exactly one of: `PASS` | `FAIL` | `WAIVE`.

- **`FAIL`:** Required: link to a tracking issue **or** one-line waiver rationale + approver (same cell).
- **`WAIVE`:** Required: explicit rationale (environment limitation, known P2, stub backend, etc.) + approver or issue link.

Leave blank cells only before the run; every row must be filled before sign-off.

---

## A. External media sync (Commit 45)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| A1 | **Listen:** Tab cursor tracks **guitar stem** within **±80 ms** vs audible note attacks on a known test song | PASS | Scroller is working and following the notes |
| A2 | **Slow:** Playback at **~65%** speed: stem rate and AlphaTab cursor stay **locked** (no drifting separation) | PASS | Small lag on slow speeds and animation speeds up a little in between bars |
| A3 | **Seek:** Section chip (or equivalent seek) updates **both** harness audio position and cursor **without** a visible lag spike | PASS | Seeking works as intented when you click a section or use the bar buttons |
| A4 | No duplicate scroll/sync timers: `smartScroll`-style path is **not** fighting external-media position updates | PASS | Scrolling works even on seek |

---

## B. Note highlight & Play target (Commit 46)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| B1 | **Listen:** Active note highlight visible in AlphaTab during stem-driven playback | PASS | Highlight and cursor work as intended |
| B2 | **Play:** Pitch target advances **note-by-note** with score (not a static single target) | PASS | Note target working as intented|
| B3 | **Study:** Fretboard dot pulses/updates from note events in sync with perception | PASS | Notes are being highlighted on the board |
| B4 | Bridge `noteEvent` traffic stays **≤ ~33 Hz** (spot-check in dev tools if web) | PASS | Note events working |

**B4 spot-check (web):** In Chrome DevTools → Network filter off; open the Performance panel or add a temporary `console.count` on `onNoteEvent` if needed. Playback uses a **~31 ms** min interval with a **pending flush** so dense passages still deliver the latest note without exceeding the rate cap on average.

---

## C. Soundfont quality (Commit 47)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| C1 | AlphaTab playback timbre is **audibly guitar-like** (not sine-test tone) | PASS | Using the actual file for playback. |
| C2 | Tab surface shows **loading state** until soundfont ready — no long white flash | PASS | `AlphaTabWeb.web.tsx` and harness both emit soundfont loading status and render loading UI (`Loading guitar soundfont…`) before ready. |
| C3 | Jam backing loops play **without** obvious click at loop seam (spot-check 2–3 tracks) | WAIVE | Requires human listening spot-check across at least 2–3 tracks; automation here cannot assess audible seam clicks. |

---

## D. Adaptive coach (Commit 48)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| D1 | Same song: analyze **with** a profile weak-area hint vs **without** yields **visibly different** coach copy (when API path used) | | |
| D2 | Lesson payload includes **`style_label`** when style detection is enabled (or document WAIVE if skipped via env) | | |
| D3 | Missing profile / offline-style path **completes** with generic coach — no crash, no empty critical UI | | |

---

## E. Play accuracy & quick feedback (Commit 49)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| E1 | In-tune window shows **sage** flash on pitch ladder; near-miss **amber**; clear miss **terracotta/red** (per design) | | |
| E2 | **`NoteAccuracyBar`** shows **≥ 4** colored beat blocks in a short captured pass | | |
| E3 | After section stop: coach bubble or fallback text within **~2 s** — no hang when key missing | | |

---

## Timing data vs metronome (triage)

Use this when the **tab cursor** tracks the stem but **metronome clicks** sound consistently early/late: the Web Audio transport is probably correct and the **lesson timing fields** need verification.

| Field | Role |
|-------|------|
| `beat_grid` | Beat times (seconds) used for click scheduling |
| `bar_timestamps` | Bar starts; anchors downbeats with `tempo` |
| `tempo` | Nominal BPM when the grid is sparse |
| `beat_align_offset_sec` | Shifts metronome vs stem clock (seconds; signed). Prefer backend calibration over ad-hoc client hacks. |

**Listen / web checklist (manual):** full-file loop **lap 1 vs lap 2** with metronome on; optional bar loop + scrub; **1.0×** and **~0.65×**; subdivision toggles. In dev builds, a backward transport jump logs `[ListenTransport] position wrap/jump` to the console.

---

## F. Metronome (Commit 50)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| F1 | **Web:** Metronome at **120 BPM** — clicks feel steady over **60 beats** (no obvious drift) | | |
| F2 | **Native:** Clicks **audibly on beat**; note any documented jitter in waiver if annoying | | |
| F3 | **Beat flash** visible during Listen when metronome enabled | | |
| F4 | **Subdivision** change alters click density **without** requiring full session restart | | |
| F5 | **Listen (web):** Full-file loop — metronome vs stems on **lap 2** is **no worse** than lap 1 (no extra drift / double-click seam) | | |
| F6 | **Listen:** Metronome on at **1.0×** and **~0.65×** — no useless **phase jump** when changing speed (rate applied via transport, not by restarting the scheduler) | | |

---

## G. Loop precision — Slow (Commit 51)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| G1 | **Two-bar loop** at Slow rate: wrap points stay within **±50 ms** of bar boundaries over **10** consecutive wraps | | |
| G2 | Dragging loop handles updates harness **loop overlay** within **one frame** of release | | |
| G3 | Default loop region prefers **low-confidence** section when lesson provides confidence bars (not arbitrary) | | |

---

## H. Study mapping (Commits 52–53)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| H1 | Tap/select score note → fretboard **exact cell** within **one frame** | | |
| H2 | **`NoteDetailCard`** shows note name, scale degree, and **non-empty** coach line | | |
| H3 | When tab gives **string+fret**, highlight matches **notated** position (not MIDI guess) | | |
| H4 | When alternates exist, card shows **≥ 1** alternate position line | | |

---

## I. Jam scale overlay (Commit 54)

| # | Check | Result | Issue link or waiver (if FAIL/WAIVE) |
|---|--------|--------|----------------------------------------|
| I1 | **A minor pentatonic** (or blues) phrase → label matches expectation and **fretboard** highlights scale degrees | | |
| I2 | **Web** with score: matching note heads **tint** for scale; **`clearScaleHighlight`** on stop resets cleanly | | |
| I3 | **Stop & Save** clears histogram / overlay state — no stale scale ring on next start | | |
| I4 | Jam header shows selected backing-track context (**label/key/BPM**) while AlphaTab is explicitly labeled as **generic reference tab** | | |
| I5 | Corrupted / malformed GP5 base64 does **not** crash Jam tab (error banner shown instead of runtime typed-array crash) | | |

---

## Sign-off

| Role | Name | Date | Phase 5 Feel Real — GO / NO-GO |
|------|------|------|--------------------------------|
| Engineering | | | |
| Product / QA | | | |

**NO-GO** if any `FAIL` lacks issue + resolution plan, or Section A is failed without approved waiver.

---

## Related docs

- [E2E_DEMO.md](./E2E_DEMO.md) — cold start, full session path, go/no-go checklist
- [ERROR_QA.md](./ERROR_QA.md) — error banner interpretation
- [PRIORITIES.md](../PRIORITIES.md) — commits 45–54 specifications
