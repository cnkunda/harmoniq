# Playback matrix (kill switch)

Manual verification checklist for **`expo-av`** playback before layering session logic on top. Targets the smoke screen in `app/(tabs)/index.tsx` (bundled `am-blues-70bpm.mp3`).

## How to run

- Repo root: `npm install` once.
- Dev server: `npm start`, then open iOS simulator, Android emulator, or press `w` for web (Chrome).
- `npm run web` — same as Expo web.
- **STOP if:** the home tab fails to load, or the console shows `Failed to initialize playback test track` (asset or AV init failure).

## Behaviour locked by the smoke screen

| Topic | Implementation |
|--------|----------------|
| **API** | `expo-av` `Audio.Sound` |
| **Rate range** | 50%–100% (`0.5`–`1.0`), slider `step` `0.05` (5% steps) |
| **Default rate** | 75% on load |
| **Rate application** | Applied on slider **release** (`onSlidingComplete`), not on every drag tick |
| **Pitch** | `shouldCorrectPitch: true` on create and on `setStatusAsync` |
| **Loop** | Toggle via **Loop: ON / OFF** (`setIsLoopingAsync`) |
| **Status** | `onPlaybackStatusUpdate` every 250ms — UI should reflect play/pause, loop, and rate when the native layer reports them |

### Rate steps to exercise (explicit)

Move the slider to each value and confirm the on-screen **Rate:** label matches after release:

`50%`, `55%`, `60%`, `65%`, `70%`, `75%`, `80%`, `85%`, `90%`, `95%`, `100%`.

### Loop boundary — what to check

With **Loop: ON** and playback running:

1. **Seam / click:** At wrap from end → start, note any audible click, gap, or level dip (MP3 padding can cause a small artefact; file is a short loop-style asset).
2. **Continuity:** Playback should restart without requiring another press of Play.
3. **With Loop: OFF:** Track should stop at end (no auto-restart). Toggle Loop back ON and confirm looping resumes as expected.

### Background audio (current app config)

`app.config.ts` does **not** yet declare iOS **Audio, AirPlay, and Picture in Picture** background mode or Android foreground-service audio. Expect:

- **Likely:** Playback **pauses or stops** when the app is backgrounded or the device locks, depending on OS defaults.
- **Action:** Record what you actually observe per platform below. Product follow-up: enable background audio only when the session loop requires it.

## Known issues and workarounds

| Issue | Platforms | Workaround / note |
|--------|-----------|-------------------|
| Pitch correction quality varies | **Chrome (web)** | Browser `HTMLMediaElement` / stack may not match native quality; UI shows a short web note. Accept for smoke testing, or compare timbre to iOS/Android at the same rate. |
| Pitch / rate quirks | Any | If rate jumps or pitch sounds wrong, confirm you **released** the slider (rate applies on complete, not while dragging). |
| Loop seam | Any | If seam is distracting, note file/format; future stems should be edited for zero-crossing loops. |
| Background playback | iOS / Android | Not configured in this commit — document observed behaviour; do not assume continuous audio when switching apps. |
| Init failure | Any | Check Metro console for `Failed to initialize playback test track`; verify asset path and clean rebuild if needed. |

---

## Tester checklist — iOS

- [ ] Play / Pause toggles and sound is audible.
- [ ] All **rate steps** (50%→100%) update the label and **audibly** change tempo; pitch stays “musical” (not chipmunk) with correction on.
- [ ] **Loop ON:** seamless enough for practice; **no stuck** playhead after wrap.
- [ ] **Loop OFF:** playback stops at end.
- [ ] **Background:** note whether audio continues, pauses, or stops when home-buttoning / app switching / lock screen.

**Tester / build / date:** _______________________

---

## Tester checklist — Android

- [ ] Play / Pause toggles and sound is audible.
- [ ] All **rate steps** (50%→100%) update the label and **audibly** change tempo; pitch stays “musical” with correction on.
- [ ] **Loop ON:** wrap behaviour acceptable; no freeze after wrap.
- [ ] **Loop OFF:** playback stops at end.
- [ ] **Background:** note behaviour when leaving the app or locking the device.

**Tester / build / date:** _______________________

---

## Tester checklist — Chrome (Expo web)

- [ ] Play / Pause toggles and sound is audible.
- [ ] All **rate steps** (50%→100%) update the label and tempo changes; compare pitch stability to native if disputed.
- [ ] **Loop ON / OFF** matches native expectations.
- [ ] **Web pitch note** on screen acknowledged — timbre may differ from iOS/Android at the same rate.
- [ ] **Tab background:** note whether playback continues or is throttled when the tab is hidden (browser-dependent).

**Tester / build / date:** _______________________

---

## Multi-stem mixer dev (Design tab)

Exercise **`StemMixerDevSection`** on the **Design** tab (`app/(tabs)/design-preview.tsx`). Implementation: `src/audio/Mixer.native.ts` (parallel `expo-av` `Sound` loops) and `Mixer.web.ts` (`AudioContext`, one `GainNode` per stem). Bundled dev stems: `assets/stem-mixer-dev/*.wav` (44.1 kHz mono sine tones).

**CPU (subjective):** On a mid-range phone, two short looping tones should feel comparable to one `expo-av` loop. If mute toggles or playback cause sustained UI jank or obvious battery heat during a short test, note the device model and follow up.

### Quick check (iOS, Android, Chrome)

- [ ] Section reaches **Loaded — press Play** without a load error in the console (`StemMixer.native` / `StemMixer.web` logs).
- [ ] **Play:** both stems audible together; **Guitar** off removes the higher sine; **Drums** off removes the lower sine.
- [ ] Toggle each switch **while playing** — no crash; **Pause** / **Play** still works.
