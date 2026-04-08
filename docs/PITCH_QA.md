# Pitch accuracy protocol (kill switch)

Structured **manual QA** for live pitch readout (`usePitchStream` → **Mic + pitch (dev)** on the Design tab) **before** the Play step and scoring depend on pitch.

## Detector context (read first)

| Topic | Detail |
|--------|--------|
| **UI** | `app/(tabs)/design-preview.tsx` — section **Mic + pitch (dev)** |
| **Web** | `src/pitch/pitchStream.web.ts` — `AudioWorklet`, autocorrelation, rough band **~70–1000 Hz** |
| **Native** | `src/pitch/pitchStream.native.ts` — `react-native-audio-api`, similar estimator |
| **Readout** | Note name, **Hz** (one decimal), **cents** vs equal-tempered semitone |
| **Logs** | Native: `[PitchStream.native]` start/stop in Metro/device logs; web: worklet + stream lifecycle in devtools |

**STOP if:** mic cannot start (permission, HTTPS on web, or missing dev build on native), or Hz/note stays blank during a loud steady tone at the speaker/phone.

## How to run

1. Repo root: `npm install` once.
2. `npm start` → **Design** tab → **design-preview** (or `npm run web` / device build as usual).
3. Open **Mic + pitch (dev)** → **Start mic**.
4. Complete sections A–C below on **each platform** you gate (at minimum **one** of web or native; both before shipping cross-platform pitch scoring).

**Environment:** Web needs **HTTPS** or `localhost`. Native needs an **Expo dev/production build** (not Expo Go) for `react-native-audio-api`.

---

## A — Test tones (reference pitch)

Use a **second device** or tab playing a clean sine (e.g. online tone generator) into the mic at **moderate volume** in a quiet room. Hold steady **≥3 s** per tone; watch the readout stabilize.

| Step | Target | Expected note (12-TET, A4=440 Hz) | Pass criteria |
|------|--------|-------------------------------------|---------------|
| A1 | **440.0 Hz** | A4 | Note **A** (any octave label the UI uses is OK if Hz matches); \|cents\| **≤ 25** vs target; Hz within **±3 Hz** of 440 |
| A2 | **220.0 Hz** | A3 | Same tolerance: \|cents\| **≤ 25**; Hz within **±3 Hz** of 220 |
| A3 | **82.41 Hz** (open low E) | E2 | \|cents\| **≤ 30**; Hz within **±4 Hz** (fundamental can be harder in room noise) |

### A — Pass/fail

| Step | Hz shown (range) | Cents (range) | Pass / Fail | Notes |
|------|------------------|---------------|-------------|-------|
| A1 |440.4 | +1 |Pass |it shows up as 440.4 |
| A2 |220.2 | + 1|Pass |it shows up as 22.2 |
| A3 | 82.41 | |Fail |sound not being pickedup due to room noise |

---

## B — Guitar open strings (standard tuning)

**Acoustic or electric** in **standard tuning** (E2–A2–D3–G3–B3–E4). Pluck **one string at a time** near the 12th fret or open; let ring **≥2 s**; avoid slamming the body into the mic.

Reference frequencies (Hz, rounded):

| String | Note | Target Hz |
|--------|------|-----------|
| 6 (low) | E2 | 82.41 |
| 5 | A2 | 110.00 |
| 4 | D3 | 146.83 |
| 3 | G3 | 196.00 |
| 2 | B3 | 246.94 |
| 1 (high) | E4 | 329.63 |

**Pass:** For each string, displayed Hz within **±5%** of target **or** \|cents\| **≤ 35** (whichever is easier to read), for a **majority** of stable frames while the note decays (not only the attack spike).

### B — Pass/fail

| String | Pass / Fail | Notes |
|--------|-------------|-------|
| E2 | Pass | Gets the correct values |
| A2 | Pass | Gets the correct values |
| D3 | Pass | Gets the correct values though slightly off |
| G3 | Pass | Gets the correct value |
| B3 | Pass | Gets the correct value |
| E4 | Pass | Gets the correct value |

---

## C — Bend hold (stability)

1. On **one string** (suggest **G3** or **B3**), play a **half-step or whole-step bend** and **hold** near the target pitch for **≥2 s**.
2. **Pass:** Readout stays in the **bent** pitch neighborhood (no wild jumps to unrelated notes) for most of the hold; brief dropouts acceptable if they recover.
3. **Fail:** System locks to wrong harmonic consistently, or cents/Hz oscillate between unrelated notes for the whole hold.

### C — Pass/fail

| Check | Pass / Fail | Notes |
|-------|-------------|-------|
| Bend stability |Pass | |

---

## Platform matrix (sign-off)

Repeat A–C (or subset noted) per platform.

| Platform | Build / browser / device | A | B | C | Overall Pass / Fail |
|----------|---------------------------|---|---|---|---------------------|
| Web |Yes | brave | Windows | Pass | Pass |
| iOS |Yes | | | | |
| Android |Yes | | | | |

---

## Failure triage (required for any Fail)

For **each** failed step, record one outcome (do not leave blank):

| Step / platform | Failure summary | Triage | Link / ticket |
|-----------------|-----------------|--------|----------------|
| | | **Fix** / **Waive** (issue URL) / **Change approach** | |

- **Fix:** land code or config change; re-run the failed rows.
- **Waive:** only with a **tracked issue** explaining risk and owner; not allowed for core tones A1–A2 if both fail on a primary platform.
- **Change approach:** e.g. different detector, pre-processing — document decision and new validation plan.

---

## Sign-off (acceptance)

**Requirement (PRIORITIES):** at least **two developers** **or** **one developer + recording**.

| Role | Name | Date | Notes |
|------|------|------|-------|
| Tester / reviewer 1 | Claude | 3/30/2026| Tested Web |
| Tester / reviewer 2 | AI| 4/6/2026 | |

**Solo + recording path:** one row above + attach **screen recording** (show Design tab, Start mic, and at least **A1** + **one guitar string**) — link or file path:

`Recording:` _________________________________________________

**Gate:** Do **not** ship Play/score features that **depend** on this pitch path until sign-off is complete and failures are triaged.
